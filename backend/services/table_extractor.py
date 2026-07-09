"""
表格提取服务

功能：
- 从版面分析结果中提取表格块
- 识别有线/无线表格
- 保留行列结构
- 处理跨页表格合并
- 转换为结构化格式

依赖：版面分析（PP-Structure 或 PyMuPDF 规则）
"""
import re
import logging

logger = logging.getLogger(__name__)


class TableExtractor:
    """
    表格提取器

    从文档版面分析结果中提取和结构化表格数据
    """

    def extract_tables(self, layout_blocks):
        """
        从版面块列表中提取所有表格

        Args:
            layout_blocks: 版面分析结果列表

        Returns:
            list[dict]: 提取的表格列表，每个表格包含结构化数据
        """
        tables = []

        for block in layout_blocks:
            if block.get('type') == 'table':
                table = self._extract_single_table(block)
                if table:
                    tables.append(table)

        return tables

    def _extract_single_table(self, block):
        """
        提取单个表格块的结构

        Args:
            block: 表格类型的版面块

        Returns:
            dict: {'headers': [...], 'rows': [[...], ...], 'page': int}
        """
        content = block.get('content', '')
        page = block.get('page', 0)

        # 按行分割
        lines = content.strip().split('\n')
        if len(lines) < 2:
            return None

        rows = []
        for line in lines:
            # 按 | 分割单元格
            cells = [c.strip() for c in line.split('|')]
            # 过滤纯空行
            if any(cells):
                rows.append(cells)

        if not rows:
            return None

        # 判断第一行是否为表头
        # 启发式：如果第一行之后有分隔行（包含 ---），或有明显的数据行
        headers = rows[0]
        data_rows = rows[1:]

        # 去掉分隔行（如 |---|---|）
        data_rows = [r for r in data_rows if not all(
            re.match(r'^[-—:=]+$', c) for c in r if c
        )]

        return {
            'headers': headers,
            'rows': data_rows,
            'page': page,
            'row_count': len(data_rows),
            'col_count': len(headers),
        }

    def merge_cross_page_tables(self, tables, max_gap_pages=1):
        """
        合并跨页表格

        检测相邻页面中具有相同列结构（表头匹配）的表格，进行合并。

        Args:
            tables: 表格列表
            max_gap_pages: 允许的最大跨页间隔

        Returns:
            list[dict]: 合并后的表格列表
        """
        if len(tables) <= 1:
            return tables

        merged = []
        i = 0

        while i < len(tables):
            current = tables[i].copy()
            current['rows'] = list(current['rows'])
            current['pages'] = [current['page']]

            j = i + 1
            while j < len(tables):
                next_table = tables[j]

                # 检查是否跨页
                page_gap = next_table['page'] - tables[j - 1]['page']
                if page_gap > max_gap_pages:
                    break

                # 检查列结构是否匹配
                if self._headers_match(current['headers'], next_table['headers']):
                    current['rows'].extend(next_table['rows'])
                    current['pages'].append(next_table['page'])
                    current['row_count'] += next_table['row_count']
                    j += 1
                else:
                    break

            merged.append(current)
            i = j

        return merged

    def _headers_match(self, headers_a, headers_b):
        """判断两个表头是否匹配（相同或高度相似）"""
        if len(headers_a) != len(headers_b):
            return False

        match_count = 0
        for a, b in zip(headers_a, headers_b):
            a_clean = re.sub(r'\s+', '', a)
            b_clean = re.sub(r'\s+', '', b)
            if a_clean == b_clean:
                match_count += 1

        # 80% 以上的表头匹配即认为是同一表格
        return match_count / len(headers_a) >= 0.8

    def to_structured_format(self, table):
        """
        转换为标准化结构化格式

        Args:
            table: 提取的表格 dict

        Returns:
            dict: 结构化格式
        """
        return {
            'type': 'table',
            'headers': table.get('headers', []),
            'rows': table.get('rows', []),
            'row_count': table.get('row_count', 0),
            'col_count': table.get('col_count', 0),
            'pages': table.get('pages', [table.get('page', 0)]),
            'text_representation': self._table_to_text(table),
        }

    def _table_to_text(self, table):
        """将表格转换为可读文本表示"""
        headers = table.get('headers', [])
        rows = table.get('rows', [])

        lines = []
        lines.append(' | '.join(headers))
        lines.append(' | '.join(['---'] * len(headers)))
        for row in rows:
            # 补齐列数
            padded = list(row) + [''] * (len(headers) - len(row))
            lines.append(' | '.join(padded[:len(headers)]))

        return '\n'.join(lines)

    def extract_tables_from_text(self, text):
        """
        从纯文本中提取表格（基于 Markdown 表格语法检测）

        Args:
            text: 纯文本内容

        Returns:
            list[dict]: 发现的表格列表
        """
        tables = []
        lines = text.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # 检测表格起始（包含 | 且至少 2 列）
            if line.count('|') >= 2 and '|' in line:
                table_lines = [line]

                # 检查下一行是否为分隔行
                if i + 1 < len(lines):
                    sep_line = lines[i + 1].strip()
                    if re.match(r'^[\|\s\-:]+$', sep_line):
                        table_lines.append(sep_line)
                        i += 1

                # 收集后续表格行
                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()
                    if next_line.count('|') >= 1 and '|' in next_line:
                        table_lines.append(next_line)
                        j += 1
                    else:
                        break

                if len(table_lines) >= 2:
                    table_text = '\n'.join(table_lines)
                    table = self._extract_single_table({
                        'content': table_text,
                        'page': 0,
                        'type': 'table',
                    })
                    if table:
                        tables.append(table)

                i = j
            else:
                i += 1

        return tables
