"""
多格式文档解析器

提供两套解析能力：
- DocumentParser: 持久化全流水线解析（含元数据、页面信息）
- LightweightParser: 临时文件轻量解析（仅文本提取，无布局分析）
"""
import os
import re
from config import Config


class DocumentParser:
    """全格式文档解析器 —— 持久化处理管线使用"""

    # 支持的文件格式映射
    FORMAT_MAP = {
        'pdf': '_parse_pdf',
        'doc': '_parse_docx',
        'docx': '_parse_docx',
        'ppt': '_parse_pptx',
        'pptx': '_parse_pptx',
        'xls': '_parse_xlsx',
        'xlsx': '_parse_xlsx',
        'png': '_parse_image',
        'jpg': '_parse_image',
        'jpeg': '_parse_image',
        'gif': '_parse_image',
        'bmp': '_parse_image',
        'html': '_parse_html',
        'htm': '_parse_html',
        'md': '_parse_markdown',
        'markdown': '_parse_markdown',
        'txt': '_parse_txt',
    }

    def parse(self, file_path, file_type=None):
        """
        解析文档，返回结构化结果

        Args:
            file_path: 文件路径
            file_type: 文件类型（可选，从扩展名自动检测）

        Returns:
            {
                'text': str,           # 全文文本（按页分隔）
                'pages': [str],        # 每页文本列表
                'metadata': {
                    'page_count': int,
                    'has_tables': bool,
                    'has_images': bool,
                    'needs_ocr': bool,  # 是否需要 OCR
                    'file_type': str,
                }
            }
        """
        if file_type is None:
            file_type = os.path.splitext(file_path)[1].lower().lstrip('.')

        if file_type not in self.FORMAT_MAP:
            raise ValueError(f"不支持的文件格式: {file_type}")

        method_name = self.FORMAT_MAP[file_type]
        method = getattr(self, method_name)
        return method(file_path)

    def _parse_pdf(self, file_path):
        """解析 PDF 文件（电子版 + 扫描版标记）"""
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        pages = []
        full_text_parts = []
        has_images = False

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            pages.append(text)
            full_text_parts.append(f"[第{page_num + 1}页]\n{text}")

            # 检测是否有图片
            if not has_images:
                images = page.get_images()
                if images:
                    has_images = True

        doc.close()

        full_text = '\n\n'.join(full_text_parts)
        needs_ocr = len(full_text.strip()) < 50 and has_images

        return {
            'text': full_text,
            'pages': pages,
            'metadata': {
                'page_count': len(pages),
                'has_tables': False,  # 由 layout_analyzer 进一步检测
                'has_images': has_images,
                'needs_ocr': needs_ocr,
                'file_type': 'pdf',
            }
        }

    def _parse_docx(self, file_path):
        """解析 Word 文档"""
        from docx import Document

        doc = Document(file_path)
        paragraphs = []
        has_tables = len(doc.tables) > 0

        # 提取段落
        for para in doc.paragraphs:
            style = para.style.name if para.style else ''
            text = para.text.strip()
            if text:
                # 标记标题
                if 'Heading' in style or 'heading' in style or '标题' in style:
                    level = 1
                    match = re.search(r'(\d+)', style)
                    if match:
                        level = int(match.group(1))
                    paragraphs.append('#' * level + ' ' + text)
                else:
                    paragraphs.append(text)

        # 提取表格
        if has_tables:
            paragraphs.append('\n---\n')
            for ti, table in enumerate(doc.tables):
                paragraphs.append(f'[表格{ti + 1}]')
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    paragraphs.append(' | '.join(cells))
                paragraphs.append('')

        full_text = '\n\n'.join(paragraphs)

        return {
            'text': full_text,
            'pages': [full_text],
            'metadata': {
                'page_count': 1,
                'has_tables': has_tables,
                'has_images': False,
                'needs_ocr': False,
                'file_type': 'docx',
            }
        }

    def _parse_pptx(self, file_path):
        """解析 PPT 演示文稿（含图片型 PPTX OCR 降级）"""
        from pptx import Presentation

        prs = Presentation(file_path)
        slides_text = []
        has_tables = False

        for si, slide in enumerate(prs.slides):
            slide_parts = [f'[幻灯片{si + 1}]']
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text:
                            slide_parts.append(text)
                if shape.has_table:
                    has_tables = True
                    table = shape.table
                    slide_parts.append('[表格]')
                    for row in table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        slide_parts.append(' | '.join(cells))
            slides_text.append('\n'.join(slide_parts))

        full_text = '\n\n'.join(slides_text)

        # 纯图片型 PPTX 降级
        if not full_text.strip().replace('[幻灯片', '').replace(']', '').replace('\n', '').strip():
            # 没有提取到任何文字内容，尝试 OCR 背景图片
            from services.document_parser import LightweightParser
            light = LightweightParser()
            ocr_text = light._ocr_pptx_images(file_path, prs)
            if ocr_text.strip():
                ocr_slides = ocr_text.split('\n\n')
                return {
                    'text': ocr_text,
                    'pages': ocr_slides,
                    'metadata': {
                        'page_count': len(ocr_slides),
                        'has_tables': has_tables,
                        'has_images': True,
                        'needs_ocr': True,
                        'file_type': 'pptx',
                    }
                }

        return {
            'text': full_text,
            'pages': slides_text,
            'metadata': {
                'page_count': len(slides_text),
                'has_tables': has_tables,
                'has_images': True,
                'needs_ocr': False,
                'file_type': 'pptx',
            }
        }

    def _parse_xlsx(self, file_path):
        """解析 Excel 表格"""
        from openpyxl import load_workbook

        wb = load_workbook(file_path, read_only=True, data_only=True)
        sheets_text = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            sheet_parts = [f'[工作表: {sheet_name}]']

            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue

            # 最多读取 2000 行
            for ri, row in enumerate(rows[:2000]):
                cells = [str(cell) if cell is not None else '' for cell in row]
                if any(cells):  # 跳过空行
                    sheet_parts.append(' | '.join(cells))

            sheets_text.append('\n'.join(sheet_parts))

        wb.close()
        full_text = '\n\n'.join(sheets_text)

        return {
            'text': full_text,
            'pages': sheets_text,
            'metadata': {
                'page_count': len(sheets_text),
                'has_tables': True,
                'has_images': False,
                'needs_ocr': False,
                'file_type': 'xlsx',
            }
        }

    def _parse_image(self, file_path):
        """解析图片文件（标记为需要 OCR）"""
        return {
            'text': '',
            'pages': [''],
            'metadata': {
                'page_count': 1,
                'has_tables': False,
                'has_images': True,
                'needs_ocr': True,
                'file_type': 'image',
            }
        }

    def _parse_html(self, file_path):
        """解析 HTML 文件"""
        from bs4 import BeautifulSoup

        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            html = f.read()

        soup = BeautifulSoup(html, 'lxml')

        # 移除 script/style 标签
        for tag in soup(['script', 'style', 'nav', 'footer']):
            tag.decompose()

        text = soup.get_text(separator='\n')
        # 清理多余空行
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        full_text = '\n'.join(lines)

        return {
            'text': full_text,
            'pages': [full_text],
            'metadata': {
                'page_count': 1,
                'has_tables': bool(soup.find_all('table')),
                'has_images': bool(soup.find_all('img')),
                'needs_ocr': False,
                'file_type': 'html',
            }
        }

    def _parse_markdown(self, file_path):
        """解析 Markdown 文件"""
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()

        return {
            'text': text,
            'pages': [text],
            'metadata': {
                'page_count': 1,
                'has_tables': '|' in text and '---' in text,
                'has_images': '![' in text,
                'needs_ocr': False,
                'file_type': 'markdown',
            }
        }

    def _parse_txt(self, file_path):
        """解析纯文本文件（支持多编码检测）"""
        # 尝试多种编码
        for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    text = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        else:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()

        return {
            'text': text,
            'pages': [text],
            'metadata': {
                'page_count': 1,
                'has_tables': False,
                'has_images': False,
                'needs_ocr': False,
                'file_type': 'txt',
            }
        }


class LightweightParser:
    """
    轻量解析器 —— 用于对话临时文件即时解析

    特点：
    - 快速同步提取文本
    - 无布局分析、无 OCR（图片调用 OCR 同步）
    - 大文件自动截断
    - 不写磁盘
    """

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    MAX_PDF_PAGES = 50                 # PDF 最大读取页数

    def parse(self, file_path, file_type=None):
        """
        轻量解析文件，返回纯文本

        Args:
            file_path: 文件路径
            file_type: 文件类型（可选）

        Returns:
            str: 提取的纯文本内容
        """
        if file_type is None:
            file_type = os.path.splitext(file_path)[1].lower().lstrip('.')

        # 检查文件大小
        file_size = os.path.getsize(file_path)
        if file_size > self.MAX_FILE_SIZE:
            return f"[文件过大（{file_size / 1024 / 1024:.1f}MB），仅提取前50页/部分内容]\n\n"

        try:
            if file_type in ('pdf',):
                return self._parse_pdf_light(file_path)
            elif file_type in ('docx', 'doc'):
                return self._parse_docx_light(file_path)
            elif file_type in ('pptx', 'ppt'):
                return self._parse_pptx_light(file_path)
            elif file_type in ('xlsx', 'xls'):
                return self._parse_xlsx_light(file_path)
            elif file_type in ('png', 'jpg', 'jpeg', 'gif', 'bmp'):
                return self._parse_image_light(file_path)
            elif file_type in ('html', 'htm'):
                return self._parse_html_light(file_path)
            elif file_type in ('md', 'markdown'):
                return self._parse_md_light(file_path)
            elif file_type in ('txt',):
                return self._parse_txt_light(file_path)
            else:
                return f"[不支持的文件格式: {file_type}]"
        except Exception as e:
            return f"[文件解析失败: {str(e)}]"

    def _parse_pdf_light(self, file_path):
        """轻量 PDF 解析"""
        import fitz
        doc = fitz.open(file_path)
        texts = []
        max_pages = min(len(doc), self.MAX_PDF_PAGES)
        truncated = len(doc) > self.MAX_PDF_PAGES

        for i in range(max_pages):
            text = doc[i].get_text()
            if text.strip():
                texts.append(text)

        doc.close()

        result = '\n\n'.join(texts)
        if truncated:
            result += f'\n\n[共{len(doc)}页，仅显示前{self.MAX_PDF_PAGES}页]'
        return result

    def _parse_docx_light(self, file_path):
        """轻量 Word 解析"""
        from docx import Document
        doc = Document(file_path)
        parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text.strip())
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                parts.append(' | '.join(cells))
        return '\n'.join(parts)

    def _parse_pptx_light(self, file_path):
        """轻量 PPT 解析（含图片型 PPTX OCR 降级）"""
        from pptx import Presentation
        prs = Presentation(file_path)
        parts = []
        for si, slide in enumerate(prs.slides):
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        if para.text.strip():
                            parts.append(para.text.strip())
                if shape.has_table:
                    for row in shape.table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        parts.append(' | '.join(cells))

        result = '\n'.join(parts)

        # 纯图片型 PPTX 降级：提取背景图片并 OCR
        if not result.strip():
            result = self._ocr_pptx_images(file_path, prs)

        return result

    def _ocr_pptx_images(self, file_path, prs=None):
        """
        提取 PPTX 中的嵌入图片并通过视觉模型 API 识别/理解

        处理纯图片型 PPTX（如 PDF 转 PPTX、扫描件等）：
        - 每页幻灯片仅包含背景图片，无文字形状
        - 从 ZIP 中提取图片 → 批量调用 Vision API → 并发处理
        - Vision API 不可用时自动降级到本地 OCR
        """
        import zipfile
        import os
        import tempfile
        import lxml.etree as ET

        NS = {
            'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
            'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
        }
        NS_R = {'ns': 'http://schemas.openxmlformats.org/package/2006/relationships'}

        tmp_dir = tempfile.mkdtemp(prefix='pptx_vision_')

        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                slide_files = sorted([
                    f for f in zf.namelist()
                    if f.startswith('ppt/slides/slide') and f.endswith('.xml')
                ], key=lambda x: int(''.join(c for c in x if c.isdigit()) or '0'))

                if not slide_files:
                    return ''

                # ---- 第 1 遍：提取所有幻灯片图片到临时文件 ----
                # slide_image_map: {slide_index: [(image_path, label)]}
                slide_image_map = {}
                all_img_paths = []

                for sfi, slide_file in enumerate(slide_files):
                    slide_xml = zf.read(slide_file)
                    slide_elem = ET.fromstring(slide_xml)
                    blips = slide_elem.findall('.//a:blip', NS)

                    slide_images = []
                    for blip in blips:
                        embed_id = blip.get(
                            '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'
                        )
                        if not embed_id:
                            continue

                        # 解析 rels 文件获取实际图片路径
                        rels_file = (
                            slide_file.replace('ppt/slides/', 'ppt/slides/_rels/')
                            .replace('.xml', '.xml.rels')
                        )
                        try:
                            rels_xml = zf.read(rels_file)
                            rels_elem = ET.fromstring(rels_xml)
                        except (KeyError, ET.ParseError):
                            continue

                        for rel in rels_elem.findall('ns:Relationship', NS_R):
                            if rel.get('Id') != embed_id:
                                continue
                            target = rel.get('Target')
                            slide_dir = '/'.join(slide_file.split('/')[:-1])
                            img_path = os.path.normpath(
                                os.path.join(slide_dir, target)
                            ).replace('\\', '/')

                            try:
                                img_data = zf.read(img_path)
                            except KeyError:
                                alt_path = 'ppt/media/' + os.path.basename(target)
                                try:
                                    img_data = zf.read(alt_path)
                                except KeyError:
                                    continue

                            ext = os.path.splitext(target)[1] or '.png'
                            tmp_img = os.path.join(
                                tmp_dir, f'slide{sfi+1}_{embed_id}{ext}'
                            )
                            with open(tmp_img, 'wb') as f:
                                f.write(img_data)

                            all_img_paths.append(tmp_img)
                            slide_images.append(tmp_img)

                    slide_image_map[sfi] = slide_images

                # ---- 第 2 遍：批量调用 Vision API（并发） ----
                if all_img_paths:
                    from services.vision_service import vision_service
                    all_results = vision_service.describe_images(all_img_paths)
                    # 建立 path → result 映射
                    path_to_text = dict(zip(all_img_paths, all_results))
                else:
                    path_to_text = {}

                # ---- 第 3 遍：按幻灯片组装输出 ----
                slides_text = []
                for sfi in range(len(slide_files)):
                    slide_images = slide_image_map.get(sfi, [])
                    image_texts = []
                    for img_path in slide_images:
                        text = path_to_text.get(img_path, '')
                        if text and text.strip():
                            image_texts.append(text.strip())

                    if image_texts:
                        slides_text.append(
                            f'[幻灯片{sfi + 1}]\n' + '\n'.join(image_texts)
                        )
                    else:
                        slides_text.append(f'[幻灯片{sfi + 1}]')

        except Exception as e:
            return f'[PPTX图片提取失败: {e}]'
        finally:
            # 清理临时目录
            try:
                import shutil
                shutil.rmtree(tmp_dir)
            except Exception:
                pass

        return '\n\n'.join(slides_text)

    def _parse_xlsx_light(self, file_path):
        """轻量 Excel 解析"""
        from openpyxl import load_workbook
        wb = load_workbook(file_path, read_only=True, data_only=True)
        parts = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            parts.append(f'[{sheet_name}]')
            for ri, row in enumerate(ws.iter_rows(values_only=True)):
                if ri > 500:
                    parts.append('[行数过多，已截断]')
                    break
                cells = [str(c) if c is not None else '' for c in row]
                if any(cells):
                    parts.append(' | '.join(cells))
        wb.close()
        return '\n'.join(parts)

    def _parse_image_light(self, file_path):
        """轻量图片解析 —— 调用视觉模型 API"""
        try:
            from services.vision_service import vision_service
            text = vision_service.recognize(file_path)
            return f'（以下内容已通过视觉识别从图片中提取，请直接阅读和使用：）\n\n{text}'
        except Exception as e:
            return f"[图片识别失败: {str(e)}]"

    def _parse_html_light(self, file_path):
        """轻量 HTML 解析"""
        from bs4 import BeautifulSoup
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            html = f.read()
        soup = BeautifulSoup(html, 'lxml')
        for tag in soup(['script', 'style']):
            tag.decompose()
        return soup.get_text(separator='\n')

    def _parse_md_light(self, file_path):
        """轻量 Markdown 解析"""
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()

    def _parse_txt_light(self, file_path):
        """轻量纯文本解析"""
        for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeError:
                continue
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
