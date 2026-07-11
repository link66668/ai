"""
语义分块服务

将文档内容按语义单元分割为适合检索的块：
- 以句子边界分割，合并至接近目标 token 数
- 保护特殊块（表格、公式、代码）
- 重叠 128 tokens 保证上下文连续性
- 每个块附带元数据（页码、标题路径、块类型）
"""
import re
from config import Config


class ChunkingService:
    """语义分块器"""

    def __init__(self, chunk_size=None, chunk_overlap=None):
        self.chunk_size = chunk_size or Config.CHUNK_SIZE       # 默认 512
        self.chunk_overlap = chunk_overlap or Config.CHUNK_OVERLAP  # 默认 128
        # 使用共享 token 计数器，避免重复初始化 tiktoken
        from services.token_counter import token_counter as _tc
        self._tc = _tc

    def count_tokens(self, text):
        """计算文本的 token 数量（委托给共享计数器）"""
        return self._tc.count(text)

    def chunk_document(self, full_text, pages_texts=None, structure_data=None):
        """
        将文档分割为语义块

        Args:
            full_text: 全文文本
            pages_texts: 每页文本列表（可选，用于定位页码）
            structure_data: 文档结构数据（可选，用于标题路径）

        Returns:
            list[dict]: 分块列表
                {
                    'index': int,          # 块序号
                    'content': str,        # 块文本内容
                    'token_count': int,    # token 数量
                    'page_start': int,     # 起始页码（从1开始）
                    'page_end': int,       # 结束页码
                    'heading_path': str,   # 所属标题路径
                    'chunk_type': str,     # 'text' | 'table' | 'heading'
                    'metadata': dict,      # 额外元数据
                }
        """
        # 1. 按页面分割并标记
        if pages_texts:
            page_map = self._build_page_map(pages_texts)
        else:
            page_map = {0: 1}  # 所有内容默认第1页

        # 2. 分离特殊块（表格、公式、代码）
        protected_blocks = self._extract_protected_blocks(full_text)
        segments = self._split_into_segments(full_text, protected_blocks)

        # 3. 合并短片段直到接近目标 token 数
        chunks = self._merge_segments(segments, page_map)

        # 4. 添加重叠内容
        chunks = self._add_overlap(chunks)

        # 5. 注入结构信息
        if structure_data:
            chunks = self._inject_structure(chunks, structure_data)

        # 6. 按顺序编号
        for i, chunk in enumerate(chunks):
            chunk['index'] = i

        return chunks

    def _build_page_map(self, pages_texts):
        """构建字符偏移 → 页码的映射"""
        page_map = {}
        offset = 0
        for page_idx, page_text in enumerate(pages_texts):
            page_map[offset] = page_idx + 1  # 1-based
            offset += len(page_text) + 2     # +2 for page separator
        return page_map

    def _get_page_number(self, pos, page_map):
        """根据字符位置获取页码"""
        current_page = 1
        for offset, page in sorted(page_map.items()):
            if pos >= offset:
                current_page = page
            else:
                break
        return current_page

    def _extract_protected_blocks(self, text):
        """
        提取受保护块（表格、代码块、公式）

        返回 list[(start, end, type, content)]
        """
        protected = []

        # 检测 Markdown 表格
        for match in re.finditer(r'(\|[^\n]+\|\n\|[\s\-:\|]+\|\n(?:\|[^\n]+\|\n?)*)', text):
            protected.append((match.start(), match.end(), 'table', match.group()))

        # 检测代码块
        for match in re.finditer(r'```[^`]*```', text):
            if not any(p[0] <= match.start() < p[1] for p in protected):
                protected.append((match.start(), match.end(), 'code', match.group()))

        # 检测数学公式块 $$...$$
        for match in re.finditer(r'\$\$[^$]+\$\$', text):
            if not any(p[0] <= match.start() < p[1] for p in protected):
                protected.append((match.start(), match.end(), 'formula', match.group()))

        return sorted(protected, key=lambda x: x[0])

    def _split_into_segments(self, text, protected_blocks):
        """
        将文本分割为片段序列（受保护块保持完整）

        返回 list[{'text': str, 'type': str, 'page': int}]
        """
        segments = []
        pos = 0

        for start, end, block_type, content in protected_blocks:
            # 添加受保护块之前的文本
            if pos < start:
                before_text = text[pos:start].strip()
                if before_text:
                    # 按句子继续分割
                    sentences = self._split_sentences(before_text)
                    for sent in sentences:
                        if sent.strip():
                            segments.append({
                                'text': sent.strip(),
                                'type': 'text',
                            })

            # 添加受保护块
            segments.append({
                'text': content,
                'type': block_type,
            })
            pos = end

        # 添加最后一段文本
        if pos < len(text):
            remaining = text[pos:].strip()
            if remaining:
                sentences = self._split_sentences(remaining)
                for sent in sentences:
                    if sent.strip():
                        segments.append({
                            'text': sent.strip(),
                            'type': 'text',
                        })

        return segments

    def _split_sentences(self, text):
        """
        按句子边界分割文本

        中文：。！？\n
        英文：. ! ? 后跟空格或换行
        """
        # 正则：中英文句子结束符号
        sentence_end = r'[。！？\.!\?\n]+'
        parts = re.split(f'({sentence_end})', text)

        sentences = []
        buffer = ''
        for part in parts:
            if re.match(f'^{sentence_end}$', part):
                buffer += part
                if len(buffer.strip()) > 5:  # 避免过短的句子
                    sentences.append(buffer)
                    buffer = ''
            else:
                buffer += part

        if buffer.strip():
            sentences.append(buffer)

        return sentences

    def _merge_segments(self, segments, page_map):
        """
        合并短片段直到接近 CHUNK_SIZE

        规则：
        - 受保护块（表格/公式/代码）尽量保持完整，最大 2048 tokens
        - 文本块合并至接近 512 tokens
        - 以句子边界作为合并点
        """
        chunks = []
        current_chunk = {
            'text_parts': [],
            'type': 'text',
            'token_count': 0,
            'seg_start': 0,
        }

        seg_pos = 0
        for seg in segments:
            seg_tokens = self.count_tokens(seg['text'])

            # 受保护块：保持独立（除非太小）
            if seg['type'] in ('table', 'code', 'formula'):
                # 先保存当前块
                if current_chunk['text_parts']:
                    chunks.append(self._finalize_chunk(current_chunk))
                    current_chunk = {
                        'text_parts': [],
                        'type': 'text',
                        'token_count': 0,
                        'seg_start': seg_pos,
                    }

                # 表格最大 2048 tokens（超过则截断）
                if seg_tokens > 2048:
                    seg['text'] = seg['text'][:4096]  # ~2048 tokens
                    seg_tokens = self.count_tokens(seg['text'])

                chunks.append({
                    'content': seg['text'],
                    'token_count': seg_tokens,
                    'chunk_type': seg['type'],
                    'page_start': 1,
                    'page_end': 1,
                    'heading_path': '',
                    'metadata': {},
                })
                seg_pos += 1
                continue

            # 文本块：合并至目标 token 数
            if current_chunk['token_count'] + seg_tokens > self.chunk_size and current_chunk['text_parts']:
                chunks.append(self._finalize_chunk(current_chunk))
                # 新块从重叠区域开始（保留最后几个片段作为重叠）
                overlap_parts = self._get_overlap_parts(current_chunk['text_parts'])
                current_chunk = {
                    'text_parts': overlap_parts,
                    'type': 'text',
                    'token_count': sum(self.count_tokens(p) for p in overlap_parts),
                    'seg_start': seg_pos - len(overlap_parts),
                }

            current_chunk['text_parts'].append(seg['text'])
            current_chunk['token_count'] += seg_tokens
            seg_pos += 1

        # 保存最后一个块
        if current_chunk['text_parts']:
            chunks.append(self._finalize_chunk(current_chunk))

        return chunks

    def _finalize_chunk(self, chunk):
        """将块字典转换为最终格式"""
        content = '\n'.join(chunk['text_parts'])
        return {
            'content': content,
            'token_count': self.count_tokens(content),
            'chunk_type': chunk.get('type', 'text'),
            'page_start': 1,
            'page_end': 1,
            'heading_path': '',
            'metadata': {},
        }

    def _get_overlap_parts(self, text_parts, target_overlap_tokens=128):
        """获取最后几个片段作为重叠内容"""
        overlap_parts = []
        overlap_tokens = 0
        for part in reversed(text_parts):
            part_tokens = self.count_tokens(part)
            if overlap_tokens + part_tokens > target_overlap_tokens and overlap_parts:
                break
            overlap_parts.insert(0, part)
            overlap_tokens += part_tokens
        return overlap_parts

    def _add_overlap(self, chunks):
        """为相邻块添加重叠内容"""
        if self.chunk_overlap <= 0:
            return chunks

        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            if prev_chunk.get('chunk_type') != 'text':
                continue
            if chunks[i].get('chunk_type') != 'text':
                continue

            prev_text = prev_chunk['content']
            # 取前一个块的末尾部分作为当前块的前缀
            overlap_text = self._extract_tail(prev_text, self.chunk_overlap)
            if overlap_text:
                chunks[i]['content'] = overlap_text + '\n' + chunks[i]['content']
                chunks[i]['token_count'] = self.count_tokens(chunks[i]['content'])

        return chunks

    def _extract_tail(self, text, target_tokens):
        """从文本末尾提取约 target_tokens 个 token 的内容"""
        # 从后往前数句子
        sentences = self._split_sentences(text)
        tail = []
        tokens = 0
        for sent in reversed(sentences):
            sent_tokens = self.count_tokens(sent)
            if tokens + sent_tokens > target_tokens and tail:
                break
            tail.insert(0, sent)
            tokens += sent_tokens
        return ''.join(tail)

    def _inject_structure(self, chunks, structure_data):
        """
        注入文档结构信息（标题路径）— 基于位置映射，而非文本匹配

        使用标题在全文中的字符偏移量来确定每个块所属的标题路径。
        如果 structure_data 包含 heading_positions，则使用精确位置映射；
        否则回退到文本匹配。
        """
        headings = structure_data.get('headings', []) if structure_data else []
        if not headings:
            return chunks

        # === 优先使用位置映射 ===
        heading_positions = structure_data.get('heading_positions', [])
        if heading_positions:
            # heading_positions: [(start_char, end_char, heading_text, level, path), ...]
            # 为每个块计算其在全文中的大致位置范围，映射到对应标题
            char_offset = 0
            chunk_heading_map = []  # (chunk_index, heading_path)

            # 先建立标题位置索引
            heading_path_at_pos = []  # (start, end, path)
            for hp in heading_positions:
                if len(hp) >= 5:
                    start, end, text, level, path = hp[:5]
                    heading_path_at_pos.append((start, end, path))

            # 如果没有精确位置信息，用累计字符偏移
            if not heading_path_at_pos:
                heading_path_at_pos = self._build_heading_position_map(
                    chunks, headings
                )

            # 为每个块分配标题路径
            for chunk in chunks:
                chunk_start = char_offset
                chunk_end = char_offset + len(chunk['content'])
                char_offset = chunk_end + 1  # +1 for separator

                # 查找覆盖此块范围的最后一个标题
                assigned_path = ''
                for hs, he, hp in heading_path_at_pos:
                    # 标题起始位置在块结束之前（即标题在块之前或块内）
                    if hs < chunk_end:
                        assigned_path = hp
                chunk['heading_path'] = assigned_path

            return chunks

        # === 回退：文本匹配（原逻辑，修复 false positive）===
        # 使用精确匹配 + 排除短文本误匹配
        for chunk in chunks:
            best_heading = ''
            best_pos = -1
            for heading in headings:
                heading_text = heading.get('text', '')
                if not heading_text or len(heading_text) < 2:
                    continue
                pos = chunk['content'].find(heading_text)
                # 取匹配到的最靠后的标题（嵌套标题中最深层级）
                if pos != -1 and pos > best_pos:
                    # 标题文本应在块的开头附近（前 1/3 区域）
                    if pos < len(chunk['content']) * 0.33:
                        best_pos = pos
                        best_heading = heading.get('path', heading_text)
            if best_heading:
                chunk['heading_path'] = best_heading

        return chunks

    def _build_heading_position_map(self, chunks, headings):
        """
        从标题文本在全文中的位置构建 heading position map

        回退策略：通过文本匹配找到标题文本在块中的位置，
        累计字符偏移来估算标题在原文中的位置。
        """
        from itertools import chain
        full_text_parts = []
        heading_map = []

        for i, heading in enumerate(headings):
            heading_text = heading.get('text', '')
            if not heading_text:
                continue
            path = heading.get('path', heading_text)

            # 在 chunks 中查找此标题文本
            found = False
            char_offset = 0
            for chunk in chunks:
                pos = chunk['content'].find(heading_text)
                if pos != -1:
                    start = char_offset + pos
                    end = start + len(heading_text)
                    heading_map.append((start, end, path))
                    found = True
                    break
                char_offset += len(chunk['content']) + 1

        return heading_map
