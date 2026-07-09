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
        self._tokenizer = None

    @property
    def tokenizer(self):
        """懒加载 tiktoken tokenizer"""
        if self._tokenizer is None:
            import tiktoken
            try:
                self._tokenizer = tiktoken.get_encoding('cl100k_base')
            except Exception:
                # 降级到简单编码
                self._tokenizer = tiktoken.get_encoding('o200k_base')
        return self._tokenizer

    def count_tokens(self, text):
        """计算文本的 token 数量"""
        try:
            return len(self.tokenizer.encode(text))
        except Exception:
            # 降级：按字符数估算（中文约 1.5 字/token，英文约 4 字/token）
            return len(text) // 2

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
        """注入文档结构信息（标题路径）"""
        headings = structure_data.get('headings', []) if structure_data else []

        if not headings:
            return chunks

        # 简单策略：根据块内容中的标题标记匹配
        for chunk in chunks:
            for heading in headings:
                heading_text = heading.get('text', '')
                if heading_text and heading_text in chunk['content']:
                    chunk['heading_path'] = heading.get('path', heading_text)
                    chunk['chunk_type'] = 'heading'
                    break

        return chunks
