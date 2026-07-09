"""
异步文档处理管线

使用 ThreadPoolExecutor 后台处理文档：
解析 → OCR → 版面分析 → 表格提取 → 结构抽取 → 分块 → 嵌入 → 索引

特性：
- 上传后异步触发
- 进度可查询（0.0 ~ 1.0）
- 失败自动重试
- 线程安全（每个工作线程独立的数据库连接）
"""
import os
import re
import time
import json
import atexit
import logging
from concurrent.futures import ThreadPoolExecutor
from config import Config

logger = logging.getLogger(__name__)


class AsyncPipeline:
    """
    异步文档处理管线

    单例模式，全局线程池
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(
            max_workers=Config.MAX_PROCESSING_WORKERS,
            thread_name_prefix='doc-processor',
        )
        self._futures = {}  # doc_id -> Future
        atexit.register(self.shutdown)
        print(f"[Pipeline] 异步处理管线已启动，工作线程数: {Config.MAX_PROCESSING_WORKERS}")

    def process_document(self, doc_id):
        """
        提交文档处理任务到线程池

        Args:
            doc_id: 文档 ID
        """
        if doc_id in self._futures and not self._futures[doc_id].done():
            print(f"[Pipeline] 文档 {doc_id} 已在处理中，跳过")
            return

        future = self._executor.submit(self._process_worker, doc_id)
        self._futures[doc_id] = future
        print(f"[Pipeline] 文档 {doc_id} 已提交处理")

    def _process_worker(self, doc_id):
        """
        处理管线工作线程

        每个阶段更新数据库进度和日志
        """
        from database import db
        from models.document import Document
        from models.user_ai_config import UserAIConfig

        stages = [
            ('parsing', 0.0, 0.1),
            ('ocr', 0.1, 0.3),
            ('layout', 0.3, 0.5),
            ('extract', 0.5, 0.65),
            ('chunking', 0.65, 0.75),
            ('embedding', 0.75, 0.9),
            ('indexing', 0.9, 0.95),
        ]

        doc = Document.find_by_id(doc_id)
        if not doc:
            logger.error(f"[Pipeline] 文档不存在: {doc_id}")
            return

        file_path = doc['file_path']
        file_type = doc['file_type']
        course_id = doc['course_id']

        # 获取文档所属用户的AI配置
        user_id = doc.get('user_id')
        ai_config = UserAIConfig.get_effective_config(user_id) if user_id else None

        retry_count = 0

        while retry_count <= Config.PROCESSING_RETRY_COUNT:
            try:
                self._run_stages(doc_id, course_id, file_path, file_type, stages, ai_config)
                # 成功
                self._update_progress(doc_id, 'completed', 1.0)
                self._log_stage(doc_id, 'completed', 'success',
                                f'处理完成: {doc["original_name"]}')
                print(f"[Pipeline] 文档 {doc_id} 处理完成")
                return
            except Exception as e:
                retry_count += 1
                error_msg = f'{type(e).__name__}: {str(e)}'
                logger.error(f"[Pipeline] 文档 {doc_id} 处理失败 (尝试 {retry_count}/{Config.PROCESSING_RETRY_COUNT}): {error_msg}")

                if retry_count > Config.PROCESSING_RETRY_COUNT:
                    self._update_progress(doc_id, 'failed', 0.0, error_msg)
                    self._log_stage(doc_id, 'failed', 'error', error_msg)
                    print(f"[Pipeline] 文档 {doc_id} 处理失败，已达最大重试次数")
                else:
                    time.sleep(2 * retry_count)  # 递增等待

    def _run_stages(self, doc_id, course_id, file_path, file_type, stages, ai_config=None):
        """按顺序执行处理阶段"""
        from services.document_parser import DocumentParser
        from services.layout_analyzer import LayoutAnalyzer
        from services.table_extractor import TableExtractor
        from services.document_structure import DocumentStructureExtractor
        from services.chunking_service import ChunkingService
        from services.embedding_service import embedding_service
        from services.vector_store import vector_store
        from services.bm25_manager import bm25_manager
        from models.document import Document
        from models.course import Course

        # Stage 1: 解析（MinerU 优先，降级到本地解析器）
        self._update_stage(doc_id, 'parsing', 0.05)
        t0 = time.time()

        mineru_used = False
        full_text = ''
        pages = []
        metadata = {'page_count': 1, 'has_tables': False,
                    'has_images': False, 'needs_ocr': False, 'file_type': file_type}

        # 尝试 MinerU 转换
        if ai_config and self._should_use_mineru(ai_config, file_type):
            try:
                from services.mineru_service import mineru_service
                course = Course.find_by_id(course_id)
                course_name = course['name'] if course else 'unnamed'
                output_dir = self._build_md_output_dir(course_name)

                # 生成文档名（去除扩展名）
                doc = Document.find_by_id(doc_id)
                doc_name = doc['original_name'] if doc else 'document'
                if '.' in doc_name:
                    doc_name = doc_name.rsplit('.', 1)[0]
                # 追加 doc_id 避免重名
                doc_name = f'{doc_name}_{doc_id}'

                result = mineru_service.convert(
                    file_path, file_type, ai_config, output_dir, doc_name
                )
                full_text = result['markdown_text']
                pages = [full_text]
                metadata['page_count'] = result.get('metadata', {}).get('page_count', 1)
                metadata['has_tables'] = '|' in full_text and '---' in full_text
                metadata['has_images'] = result['image_count'] > 0
                metadata['needs_ocr'] = False
                mineru_used = True

                Document.update_processing(doc_id, md_path=result['md_file_path'])
                self._log_stage(doc_id, 'parsing', 'success',
                                f'MinerU: {len(full_text)} 字符, {result["image_count"]} 张图片',
                                int((time.time() - t0) * 1000))
            except Exception as e:
                logger.warning(f"[Pipeline] MinerU 转换失败，降级到本地解析: {e}")

        # 降级：本地解析器（现有逻辑）
        if not mineru_used:
            parser = DocumentParser()
            parse_result = parser.parse(file_path, file_type)
            full_text = parse_result['text']
            pages = parse_result.get('pages', [full_text])
            metadata = parse_result['metadata']
            self._log_stage(doc_id, 'parsing', 'success',
                            f'本地解析: {len(full_text)} 字符, {metadata.get("page_count", 1)} 页',
                            int((time.time() - t0) * 1000))

            # 本地解析也生成 .md 文件存入知识库
            if full_text.strip():
                try:
                    course = Course.find_by_id(course_id)
                    course_name = course['name'] if course else 'unnamed'
                    output_dir = self._build_md_output_dir(course_name)
                    doc = Document.find_by_id(doc_id)
                    doc_name = doc['original_name'] if doc else 'document'
                    if '.' in doc_name:
                        doc_name = doc_name.rsplit('.', 1)[0]
                    doc_name = f'{doc_name}_{doc_id}'
                    md_path = self._save_text_as_markdown(full_text, output_dir, doc_name)
                    Document.update_processing(doc_id, md_path=md_path)
                except Exception as e:
                    logger.warning(f"[Pipeline] 保存知识库 .md 失败: {e}")

        # 回写 content_text，确保解析后的文本可被搜索和预览
        Document.update_processing(doc_id,
            content_text=full_text[:10000],
            page_count=metadata.get('page_count', 1),
        )

        # Stages 2-4: OCR / 版面分析 / 结构提取
        if mineru_used:
            # MinerU 已处理 OCR、版面和结构，跳过这些阶段
            self._log_stage(doc_id, 'ocr', 'skipped', 'MinerU 已处理图片识别')
            self._log_stage(doc_id, 'layout', 'skipped', 'MinerU 已处理版面分析')
            self._log_stage(doc_id, 'extract', 'skipped', 'MinerU 已处理结构提取')
            structure = self._extract_structure_from_markdown(full_text)
            all_tables = []
        else:
            # Stage 2: 图片识别（视觉模型 API，自动降级到 OCR）
            self._update_stage(doc_id, 'ocr', 0.15)
            ocr_text = ''
            if metadata.get('needs_ocr'):
                t0 = time.time()
                from services.vision_service import vision_service
                ocr_text = vision_service.recognize(file_path, ai_config=ai_config)
                engine = vision_service.get_active_engine_name()
                if ocr_text:
                    full_text = ocr_text
                    pages = [ocr_text]
                self._log_stage(doc_id, 'ocr', 'success',
                                f'图片识别完成 ({engine}), {len(ocr_text)} 字符',
                                int((time.time() - t0) * 1000))
            else:
                self._log_stage(doc_id, 'ocr', 'skipped', '无需图片识别')

            # Stage 3: 版面分析
            self._update_stage(doc_id, 'layout', 0.35)
            t0 = time.time()
            layout_analyzer = LayoutAnalyzer()
            layout_blocks = layout_analyzer.analyze(file_path, file_type)
            self._log_stage(doc_id, 'layout', 'success',
                            f'版面分析完成, {len(layout_blocks)} 个块',
                            int((time.time() - t0) * 1000))

            # Stage 4: 表格提取 + 结构抽取
            self._update_stage(doc_id, 'extract', 0.55)
            t0 = time.time()
            table_extractor = TableExtractor()
            tables = table_extractor.extract_tables(layout_blocks)
            merged_tables = table_extractor.merge_cross_page_tables(tables)
            structure_extractor = DocumentStructureExtractor()
            structure = structure_extractor.extract(full_text, layout_blocks)
            str_tables = table_extractor.extract_tables_from_text(full_text)
            all_tables = merged_tables + str_tables
            self._log_stage(doc_id, 'extract', 'success',
                            f'结构提取完成, {len(structure["headings"])} 个标题, {len(all_tables)} 个表格',
                            int((time.time() - t0) * 1000))

        # Stage 5: 分块
        self._update_stage(doc_id, 'chunking', 0.7)
        t0 = time.time()
        chunking = ChunkingService()
        chunks = chunking.chunk_document(full_text, pages, structure)
        for chunk in chunks:
            chunk['document_id'] = doc_id
            chunk['course_id'] = course_id
        self._log_stage(doc_id, 'chunking', 'success',
                        f'分块完成, {len(chunks)} 个块',
                        int((time.time() - t0) * 1000))

        # Stage 6: 嵌入（API 模式，失败自动降级到哈希向量）
        self._update_stage(doc_id, 'embedding', 0.8)
        t0 = time.time()
        chunk_texts = [c['content'] for c in chunks]
        embeddings = embedding_service.embed_texts(chunk_texts, ai_config=ai_config)
        msg = f'嵌入完成, {len(embeddings)} 个向量, {embedding_service.get_dimension()}维'
        self._log_stage(doc_id, 'embedding', 'success',
                        msg, int((time.time() - t0) * 1000))

        # Stage 7: 索引
        self._update_stage(doc_id, 'indexing', 0.9)
        t0 = time.time()
        # 向量存储
        vector_store.add_chunks(course_id, chunks, embeddings)
        # BM25 索引（始终可用，纯本地无网络依赖）
        bm25_manager.build_index(course_id, chunks)
        self._log_stage(doc_id, 'indexing', 'success',
                        f'索引完成, BM25+向量', int((time.time() - t0) * 1000))

        # 保存分块到数据库
        self._save_chunks_to_db(doc_id, course_id, chunks, embeddings)

        # 保存文档元数据
        Document.update_processing(doc_id,
            page_count=metadata.get('page_count', 1),
            chunk_count=len(chunks),
            structured_content=json.dumps({
                'tables': [t.to_structured_format() if hasattr(t, 'to_structured_format') else t
                          for t in all_tables],
            }, ensure_ascii=False),
            toc_tree=json.dumps(structure.get('toc_tree', []), ensure_ascii=False),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )

        # 保存 chroma_id 关联
        for chunk, embedding in zip(chunks, embeddings):
            # 更新数据库中块的 chroma_id
            from database import db
            db.update(
                "UPDATE document_chunks SET chroma_id = ? WHERE id = ?",
                (f"chunk_{course_id}_{doc_id}_{chunk['index']}", 0)  # placeholder
            )

    def _save_chunks_to_db(self, doc_id, course_id, chunks, embeddings):
        """将分块保存到 document_chunks 表"""
        from database import db

        # 先清除旧的块
        db.delete("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))

        for chunk, embedding in zip(chunks, embeddings):
            chroma_id = f"chunk_{course_id}_{doc_id}_{chunk['index']}"
            chunk_id = db.insert(
                """INSERT INTO document_chunks
                   (document_id, course_id, chunk_index, chunk_type, content,
                    token_count, page_start, page_end, heading_path, metadata_json, chroma_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc_id,
                    course_id,
                    chunk['index'],
                    chunk.get('chunk_type', 'text'),
                    chunk['content'],
                    chunk.get('token_count', 0),
                    chunk.get('page_start', 1),
                    chunk.get('page_end', 1),
                    chunk.get('heading_path', ''),
                    json.dumps(chunk.get('metadata', {}), ensure_ascii=False),
                    chroma_id,
                )
            )

    def _update_stage(self, doc_id, stage_name, progress):
        """更新处理阶段"""
        self._update_progress(doc_id, stage_name, progress)

    def _update_progress(self, doc_id, status, progress, error=None):
        """更新处理进度到数据库"""
        from models.document import Document
        try:
            kwargs = {
                'processing_status': status,
                'processing_progress': progress,
            }
            if error is not None:
                kwargs['processing_error'] = error
            Document.update_processing(doc_id, **kwargs)
        except Exception as e:
            logger.error(f"更新进度失败: {e}")

    def _log_stage(self, doc_id, stage, status, message, duration_ms=0):
        """记录处理日志到数据库"""
        from database import db
        try:
            db.insert(
                """INSERT INTO document_processing_log
                   (document_id, stage, status, message, duration_ms)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc_id, stage, status, message, duration_ms)
            )
        except Exception as e:
            logger.error(f"记录日志失败: {e}")

    def get_progress(self, doc_id):
        """查询文档处理进度"""
        from models.document import Document
        doc = Document.find_by_id(doc_id)
        if not doc:
            return {'status': 'not_found', 'progress': 0, 'error': None}
        return {
            'status': doc.get('processing_status', 'pending'),
            'progress': doc.get('processing_progress', 0),
            'error': doc.get('processing_error'),
            'page_count': doc.get('page_count', 0),
            'chunk_count': doc.get('chunk_count', 0),
        }

    def reprocess_document(self, doc_id):
        """重新处理文档"""
        from models.document import Document
        from services.vector_store import vector_store
        from services.bm25_manager import bm25_manager
        from database import db

        doc = Document.find_by_id(doc_id)
        if not doc:
            return

        # 清除旧数据
        course_id = doc['course_id']
        vector_store.delete_document(course_id, doc_id)
        db.delete("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))
        db.delete("DELETE FROM document_processing_log WHERE document_id = ?", (doc_id,))

        # 清理旧的 MinerU .md 文件
        md_path = doc.get('md_path', '')
        if md_path and os.path.exists(md_path):
            os.remove(md_path)
            # 清理空 images/ 目录
            images_dir = os.path.join(os.path.dirname(md_path), 'images')
            if os.path.isdir(images_dir) and not os.listdir(images_dir):
                os.rmdir(images_dir)
        Document.update_processing(doc_id, md_path='')

        # 重置状态
        Document.update_processing(doc_id,
            processing_status='pending',
            processing_progress=0.0,
            processing_error=None,
        )

        # 重新处理
        self.process_document(doc_id)

        # BM25 需要重建（因为当前 BM25 按课程全局索引）
        # 这里简单标记，实际重建在下次索引时
        bm25_manager.remove_course(course_id)

    def _should_use_mineru(self, ai_config, file_type):
        """检查是否应使用 MinerU（纯文本类型跳过）"""
        SKIP_TYPES = {'txt', 'md', 'markdown', 'html', 'htm'}
        if file_type in SKIP_TYPES:
            return False
        doc_url = (ai_config.get('doc_api_url') or '').strip()
        doc_key = (ai_config.get('doc_api_key') or '').strip()
        return bool(doc_url or doc_key)

    def _build_md_output_dir(self, course_name):
        """构建 MinerU 输出目录: backend/uploads/{safe_course_name}/"""
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', course_name).strip()
        if not safe_name:
            safe_name = 'unnamed'
        output_dir = os.path.join(Config.UPLOAD_FOLDER, safe_name)
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def _extract_structure_from_markdown(self, markdown_text):
        """从 Markdown 提取标题结构，供分块阶段使用"""
        headings = []
        for m in re.finditer(r'^(#{1,6})\s+(.+)$', markdown_text, re.MULTILINE):
            headings.append({
                'level': len(m.group(1)),
                'text': m.group(2).strip(),
                'path': m.group(2).strip(),
            })
        return {'headings': headings, 'toc_tree': []}

    def _save_text_as_markdown(self, text, output_dir, doc_name):
        """将解析文本保存为 .md 文件到知识库目录"""
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', doc_name).strip() or 'document'
        md_path = os.path.join(output_dir, f'{safe_name}.md')
        if os.path.exists(md_path):
            md_path = os.path.join(output_dir, f'{safe_name}_{int(time.time())}.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(text)
        return md_path

    def shutdown(self):
        """关闭线程池"""
        print("[Pipeline] 正在关闭异步处理管线...")
        self._executor.shutdown(wait=True, cancel_futures=False)
        print("[Pipeline] 异步处理管线已关闭")


# 全局单例
pipeline = AsyncPipeline()
