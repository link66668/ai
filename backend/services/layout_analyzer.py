"""
版面分析服务

检测文档中的表格、图片、标题等区域，重建阅读顺序。
使用 PyMuPDF 文本位置做规则分析。
"""
import logging

logger = logging.getLogger(__name__)


class LayoutBlock:
    """版面块"""

    def __init__(self, block_type, bbox, content='', page=0, metadata=None):
        self.type = block_type      # 'text', 'table', 'image', 'heading'
        self.bbox = bbox            # [x0, y0, x1, y1]
        self.content = content
        self.page = page
        self.metadata = metadata or {}

    def to_dict(self):
        return {
            'type': self.type,
            'bbox': self.bbox,
            'content': self.content,
            'page': self.page,
            'metadata': self.metadata,
        }


class LayoutAnalyzer:
    """
    版面分析器

    分析文档页面的布局结构，检测：
    - 标题层级
    - 表格区域
    - 图片区域
    - 文本块
    - 阅读顺序
    """

    def analyze(self, file_path, file_type='pdf'):
        """
        分析文档版面

        Args:
            file_path: 文件路径
            file_type: 文件类型

        Returns:
            list[dict]: 版面块列表
        """
        if file_type == 'pdf':
            return self._analyze_pdf(file_path)
        else:
            return self._analyze_generic(file_path, file_type)

    def _analyze_pdf(self, file_path):
        """使用 PyMuPDF 规则分析 PDF 版面"""
        import fitz

        doc = fitz.open(file_path)
        all_blocks = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("blocks")

            for block in blocks:
                # PyMuPDF block 格式: (x0, y0, x1, y1, text, block_no, block_type)
                x0, y0, x1, y1 = block[:4]
                text = block[4].strip() if len(block) > 4 else ''
                block_type = block[6] if len(block) > 6 else 0

                if not text:
                    continue

                # 判断块类型
                layout_type = self._classify_block(text, x0, y0, x1, y1, block_type)
                all_blocks.append(LayoutBlock(
                    block_type=layout_type,
                    bbox=[x0, y0, x1, y1],
                    content=text,
                    page=page_num,
                ))

            # 检测页面中的图片
            images = page.get_images()
            for img in images:
                all_blocks.append(LayoutBlock(
                    block_type='image',
                    bbox=[0, 0, page.rect.width, page.rect.height],
                    content='',
                    page=page_num,
                    metadata={'image_count': len(images)},
                ))

        doc.close()

        # 重建阅读顺序
        ordered_blocks = self.reconstruct_reading_order(all_blocks)
        return [b.to_dict() for b in ordered_blocks]

    def _analyze_generic(self, file_path, file_type):
        """通用版面分析（非 PDF 文件）"""
        # 对于非 PDF 文件，返回基本的文本块结构
        from services.document_parser import DocumentParser
        parser = DocumentParser()
        result = parser.parse(file_path, file_type)

        blocks = []
        # 将解析结果按段落分割为文本块
        for page_idx, page_text in enumerate(result.get('pages', [result['text']])):
            paragraphs = [p.strip() for p in page_text.split('\n\n') if p.strip()]
            y_pos = 0
            for para in paragraphs:
                lines = para.count('\n') + 1
                block_type = self._classify_block(para, 0, y_pos, 600, 0)
                blocks.append(LayoutBlock(
                    block_type=block_type,
                    bbox=[0, y_pos, 600, y_pos + lines * 14],
                    content=para,
                    page=page_idx,
                ))
                y_pos += lines * 14 + 5

        return [b.to_dict() for b in blocks]

    def _classify_block(self, text, x0, y0, x1, y1, block_type=0):
        """根据文本特征和位置判断块类型"""
        import re

        # 标题检测：短文本 + 常见标题模式
        is_heading = False
        heading_patterns = [
            r'^第[一二三四五六七八九十\d]+章',
            r'^第[一二三四五六七八九十\d]+节',
            r'^\d+[\.\、]',
            r'^[一二三四五六七八九十][\.\、\)）]',
            r'^[（(][一二三四五六七八九十\d]+[）)]',
        ]
        for pattern in heading_patterns:
            if re.match(pattern, text.strip()):
                is_heading = True
                break

        if is_heading or (len(text) < 50 and y0 < 100):
            return 'heading'

        # 表格检测：包含 | 或制表符的行结构
        if '|' in text and text.count('|') >= 2 and '\n' not in text:
            return 'table'

        return 'text'

    def reconstruct_reading_order(self, blocks):
        """
        重建阅读顺序

        按 y 轴为主、x 轴为辅排序，处理多栏布局
        """
        if not blocks:
            return blocks

        # 按页分组
        pages = {}
        for block in blocks:
            if block.page not in pages:
                pages[block.page] = []
            pages[block.page].append(block)

        ordered = []
        for page_num in sorted(pages.keys()):
            page_blocks = pages[page_num]

            # 按 y 坐标排序（同一行内按 x 排序）
            page_blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))

            # 将接近的 y 坐标聚类为行
            rows = []
            current_row = [page_blocks[0]]
            current_y = page_blocks[0].bbox[1]

            for block in page_blocks[1:]:
                if abs(block.bbox[1] - current_y) < 20:  # 同一行
                    current_row.append(block)
                else:
                    rows.append(sorted(current_row, key=lambda b: b.bbox[0]))
                    current_row = [block]
                    current_y = block.bbox[1]
            rows.append(sorted(current_row, key=lambda b: b.bbox[0]))

            # 展平行列表
            for row in rows:
                ordered.extend(row)

        return ordered
