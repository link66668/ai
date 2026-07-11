"""
文档结构提取服务

从解析后的文档中提取：
- 标题层级（章节/小节）
- 图表标题
- 树状目录结构
"""
import re
import json
import logging

logger = logging.getLogger(__name__)


class DocumentStructureExtractor:
    """文档结构提取器"""

    # 中文标题模式
    HEADING_PATTERNS = [
        # 第X章、第X节
        (re.compile(r'^第([一二三四五六七八九十\d]+)章\s*(.*)'), 1),
        (re.compile(r'^第([一二三四五六七八九十\d]+)节\s*(.*)'), 2),
        # 数字编号: 1. / 1.1 / 1.1.1
        (re.compile(r'^(\d+)\.\s+(.+)'), 2),
        (re.compile(r'^(\d+\.\d+)\s+(.+)'), 3),
        (re.compile(r'^(\d+\.\d+\.\d+)\s+(.+)'), 4),
        # 中文编号: 一、/ （一）
        (re.compile(r'^([一二三四五六七八九十]+)[、\．]\s*(.+)'), 1),
        (re.compile(r'^[（(]([一二三四五六七八九十]+)[）)]\s*(.+)'), 2),
        # Markdown 风格: ## / ###
        (re.compile(r'^(#{1,6})\s+(.+)'), None),  # level = len(match.group(1))
    ]

    # 图表标题模式
    FIGURE_TABLE_PATTERNS = [
        re.compile(r'(图|Figure|Fig\.?)\s*(\d+[\.\d]*)\s*[:：\s]?\s*(.*)'),
        re.compile(r'(表|Table)\s*(\d+[\.\d]*)\s*[:：\s]?\s*(.*)'),
    ]

    def extract(self, full_text, parsed_blocks=None):
        """
        提取文档结构

        Args:
            full_text: 全文文本
            parsed_blocks: 版面分析结果（可选）

        Returns:
            dict: {
                'toc_tree': [...],       # 树状目录
                'headings': [...],       # 标题列表
                'figures': [...],        # 图表列表
                'tables': [...],         # 表格列表
            }
        """
        headings = self._extract_headings(full_text)
        figures = self._extract_figures(full_text)
        tables = self._extract_table_captions(full_text)
        toc_tree = self._build_toc_tree(headings)

        # 构建 heading_positions: [(start, end, heading_text, level, path), ...]
        # 供 ChunkingService 做基于位置的标题路径注入
        heading_positions = []
        for i, h in enumerate(headings):
            start = h.get('position', 0)
            text = h.get('text', '')
            level = h.get('level', 1)
            # 用该标题自己的位置 +1 来构建包含自身的路径
            path = self.get_heading_path(headings, start + 1)
            end = start + len(h.get('line', text))
            heading_positions.append((start, end, text, level, path))

        return {
            'toc_tree': toc_tree,
            'headings': headings,
            'heading_positions': heading_positions,
            'figures': figures,
            'tables': tables,
        }

    def _extract_headings(self, text):
        """提取所有标题"""
        headings = []
        lines = text.split('\n')
        pos = 0

        for line in lines:
            stripped = line.strip()
            if not stripped or len(stripped) > 100:
                pos += len(line) + 1
                continue

            # 尝试匹配标题模式
            for pattern, default_level in self.HEADING_PATTERNS:
                match = pattern.match(stripped)
                if match:
                    if default_level is None:
                        # Markdown 风格：level = 井号数量
                        level = len(match.group(1))
                        title = match.group(2).strip()
                    else:
                        level = default_level
                        # 标题文本在最后一个捕获组
                        title = match.group(match.lastindex or 2).strip()

                    headings.append({
                        'text': title,
                        'level': min(level, 6),  # 最多6级
                        'position': pos,
                        'line': stripped,
                    })
                    break

            pos += len(line) + 1

        return headings

    def _extract_figures(self, text):
        """提取图片标题"""
        figures = []
        for pattern in self.FIGURE_TABLE_PATTERNS:
            for match in pattern.finditer(text):
                prefix = match.group(1)
                if prefix in ('图', 'Figure', 'Fig', 'Fig.'):
                    figures.append({
                        'type': 'figure',
                        'number': match.group(2),
                        'caption': match.group(3).strip() if match.lastindex >= 3 else '',
                        'position': match.start(),
                    })
        return figures

    def _extract_table_captions(self, text):
        """提取表格标题"""
        tables = []
        for pattern in self.FIGURE_TABLE_PATTERNS:
            for match in pattern.finditer(text):
                prefix = match.group(1)
                if prefix in ('表', 'Table'):
                    tables.append({
                        'type': 'table',
                        'number': match.group(2),
                        'caption': match.group(3).strip() if match.lastindex >= 3 else '',
                        'position': match.start(),
                    })
        return tables

    def _build_toc_tree(self, headings):
        """
        根据标题层级构建树状目录

        Args:
            headings: 标题列表

        Returns:
            list[dict]: 树状目录结构
        """
        if not headings:
            return []

        tree = []
        # stack 保存 (level, node) 用于追踪层级
        stack = [{'level': 0, 'children': tree}]

        for heading in headings:
            node = {
                'title': heading['text'],
                'level': heading['level'],
                'children': [],
            }

            # 找到合适的父节点
            while stack and stack[-1]['level'] >= heading['level']:
                stack.pop()

            if stack:
                stack[-1]['children'].append(node)
            else:
                tree.append(node)

            stack.append({'level': heading['level'], 'children': node['children']})

        return tree

    def get_heading_path(self, headings, position):
        """
        获取指定位置的标题路径

        Args:
            headings: 标题列表
            position: 字符位置

        Returns:
            str: 标题路径，如 "第一章 > 第一节 > 小节"
        """
        path_parts = []
        for heading in headings:
            if heading['position'] < position:
                # 保持同级最新
                while path_parts and path_parts[-1]['level'] >= heading['level']:
                    path_parts.pop()
                path_parts.append(heading)
            else:
                break

        return ' > '.join(h['text'] for h in path_parts) if path_parts else ''
