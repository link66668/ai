"""
结构感知分块服务（仿 cherry-studio）

按章节标题切分文档，每个标题+内容作为一个语义块。
保证标题和其正文在同一块中，检索时匹配标题即能拿到内容。

分块策略:
  1. 从全文解析标题层级（支持 Markdown ## / 中文"第X章" / 数字 1.1）
  2. 按标题边界分割为章节
  3. 章节大小适中则保持独立；过大（> CHUNK_SIZE）则句子边界拆分
  4. 每个块继承所属标题的 heading_path
"""
import re
from config import Config


class ChunkingService:
    """结构感知分块器"""

    # 标题检测模式（与 document_structure.py 一致）
    HEADING_PATTERNS = [
        re.compile(r'^第([一二三四五六七八九十\d]+)章\s*(.*)'),
        re.compile(r'^第([一二三四五六七八九十\d]+)节\s*(.*)'),
        re.compile(r'^(\d+)\.\s+(.+)'),
        re.compile(r'^(\d+\.\d+)\s+(.+)'),
        re.compile(r'^(\d+\.\d+\.\d+)\s+(.+)'),
        re.compile(r'^([一二三四五六七八九十]+)[、\．]\s*(.+)'),
        re.compile(r'^(#{1,6})\s+(.+)'),
    ]

    def __init__(self, chunk_size=None, chunk_overlap=None):
        self.chunk_size = chunk_size or Config.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or Config.CHUNK_OVERLAP
        from services.token_counter import token_counter as _tc
        self._tc = _tc

    def count_tokens(self, text):
        return self._tc.count(text)

    def chunk_document(self, full_text, pages_texts=None, structure_data=None):
        """
        结构感知分块 — 按标题切分，保留标题上下文

        Args:
            full_text: 全文文本
            pages_texts: 每页文本列表（可选，暂用于页码）
            structure_data: 文档结构（含 heading_positions）

        Returns:
            list[dict]:
                {index, content, token_count, heading_path,
                 page_start, page_end, chunk_type, metadata}
        """
        if not full_text or not full_text.strip():
            return []

        # 1. 解析标题位置
        headings = self._parse_headings(full_text)

        # 2. 按标题边界切分为章节
        sections = self._split_by_headings(full_text, headings)

        # 3. 每章分块（大章内部再拆）
        chunks = []
        for heading_text, heading_path, section_text in sections:
            section_chunks = self._chunk_section(
                section_text, heading_text, heading_path
            )
            chunks.extend(section_chunks)

        # 4. 编号
        for i, chunk in enumerate(chunks):
            chunk['index'] = i

        logger.info(
            f"[Chunking] {len(chunks)} 块, "
            f"来自 {len(sections)} 个章节"
        )
        return chunks

    # ==================== 阶段 1: 解析标题 ====================

    def _parse_headings(self, text):
        """
        解析全文中的标题，返回 [(line_index, level, text, path), ...]

        path = 完整标题路径，如 "第一章 > 第一节 > 毛泽东思想"
        """
        lines = text.split('\n')
        raw_headings = []  # [(line_idx, level, text)]

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or len(stripped) > 100:
                continue

            for pattern in self.HEADING_PATTERNS:
                match = pattern.match(stripped)
                if match:
                    last = match.lastindex or 1
                    title = match.group(last).strip()
                    if not title:
                        continue
                    if pattern.pattern.startswith(r'^(#{1,6})'):
                        level = len(match.group(1))
                    elif pattern.pattern.startswith(r'^第.*章'):
                        level = 1
                    elif pattern.pattern.startswith(r'^第.*节'):
                        level = 2
                    elif pattern.pattern.startswith(r'^(\d+\.\d+\.\d+)'):
                        level = 3
                    elif pattern.pattern.startswith(r'^(\d+\.\d+)'):
                        level = 2
                    elif pattern.pattern.startswith(r'^(\d+)\.'):
                        level = 1
                    elif pattern.pattern.startswith(r'^([一二三四五六七八九十]+)'):
                        level = 1
                    else:
                        level = 1

                    raw_headings.append((i, min(level, 6), title))
                    break

        # 构建标题路径
        result = []
        path_stack = []  # [(level, text)]
        for idx, level, text in raw_headings:
            # 弹出同级或更深级的标题
            while path_stack and path_stack[-1][0] >= level:
                path_stack.pop()
            path_stack.append((level, text))
            path = ' > '.join(p[1] for p in path_stack)
            result.append((idx, level, text, path))

        return result

    # ==================== 阶段 2: 按标题切分章节 ====================

    def _split_by_headings(self, text, headings):
        """
        按标题边界将全文切分为章节

        Returns:
            [(heading_text, heading_path, section_text), ...]
            第一个章节可能是标题前的引言（heading_text=''）
        """
        lines = text.split('\n')
        sections = []

        # 构建行号 → heading 映射
        heading_at_line = {}
        for idx, level, text, path in headings:
            heading_at_line[idx] = (text, path)

        current_heading = ('', '')  # (text, path)
        current_lines = []

        for i, line in enumerate(lines):
            if i in heading_at_line:
                # 保存上一节
                if current_lines:
                    section_text = '\n'.join(current_lines).strip()
                    if section_text:
                        sections.append((*current_heading, section_text))

                # 新章节开始
                current_heading = heading_at_line[i]
                current_lines = []
            else:
                current_lines.append(line)

        # 最后一个章节
        if current_lines:
            section_text = '\n'.join(current_lines).strip()
            if section_text:
                sections.append((*current_heading, section_text))

        return sections

    # ==================== 阶段 3: 单章分块 ====================

    def _chunk_section(self, section_text, heading_text, heading_path):
        """
        将一个章节拆分为块

        小章节（< CHUNK_SIZE）保持独立
        大章节按句子拆分
        """
        if not section_text or not section_text.strip():
            return []

        # 小章节直接作为一个块（含标题）
        content = self._build_chunk_content(heading_text, section_text)
        tokens = self.count_tokens(content)

        if tokens <= self.chunk_size:
            return [self._make_chunk(content, tokens, heading_path)]

        # 大章节：按句子拆分
        chunks = []
        sentences = self._split_sentences(section_text)
        buffer = []
        buffer_tokens = 0
        heading_prefix = (heading_text + '\n\n') if heading_text else ''

        for sent in sentences:
            sent_tokens = self.count_tokens(sent)
            if buffer_tokens + sent_tokens > self.chunk_size and buffer:
                chunk_text = heading_prefix + ''.join(buffer)
                chunks.append(self._make_chunk(chunk_text.strip(),
                                                self.count_tokens(chunk_text),
                                                heading_path))
                # 带重叠
                overlap = self._get_overlap(buffer)
                buffer = overlap
                buffer_tokens = self.count_tokens(''.join(overlap))

            buffer.append(sent)
            buffer_tokens += sent_tokens

        if buffer:
            chunk_text = heading_prefix + ''.join(buffer)
            chunks.append(self._make_chunk(chunk_text.strip(),
                                            self.count_tokens(chunk_text),
                                            heading_path))

        return chunks

    def _build_chunk_content(self, heading_text, section_text):
        """构建块内容：标题 + 正文"""
        if heading_text:
            return f'{heading_text}\n\n{section_text}'
        return section_text

    def _make_chunk(self, content, token_count, heading_path):
        return {
            'content': content,
            'token_count': token_count,
            'chunk_type': 'text',
            'page_start': 1,
            'page_end': 1,
            'heading_path': heading_path or '',
            'metadata': {},
        }

    # ==================== 工具方法 ====================

    def _split_sentences(self, text):
        """按句子边界分割"""
        sentence_end = r'[。！？\.!\?\n]+'
        parts = re.split(f'({sentence_end})', text)
        sentences = []
        buffer = ''
        for part in parts:
            if re.match(f'^{sentence_end}$', part):
                buffer += part
                if len(buffer.strip()) > 5:
                    sentences.append(buffer)
                    buffer = ''
            else:
                buffer += part
        if buffer.strip():
            sentences.append(buffer)
        return sentences

    def _get_overlap(self, parts, target_tokens=128):
        """取最后若干片段作为重叠"""
        overlap = []
        tokens = 0
        for part in reversed(parts):
            t = self.count_tokens(part)
            if tokens + t > target_tokens and overlap:
                break
            overlap.insert(0, part)
            tokens += t
        return overlap


import logging
logger = logging.getLogger(__name__)
