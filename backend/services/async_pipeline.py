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

        # Stage 1: 解析
        self._update_stage(doc_id, 'parsing', 0.05)
        t0 = time.time()
        parser = DocumentParser()
        parse_result = parser.parse(file_path, file_type, ai_config=ai_config)
        full_text = parse_result['text']
        pages = parse_result.get('pages', [full_text])
        metadata = parse_result['metadata']
        # 立即回写 content_text，确保解析后的文本可被搜索和预览
        Document.update_processing(doc_id,
            content_text=full_text[:10000],  # 截断到 10000 字符用于搜索/预览
            page_count=metadata.get('page_count', 1),
        )
        self._log_stage(doc_id, 'parsing', 'success',
                        f'解析完成, {len(full_text)} 字符, {metadata["page_count"]} 页',
                        int((time.time() - t0) * 1000))

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

    def shutdown(self):
        """关闭线程池"""
        print("[Pipeline] 正在关闭异步处理管线...")
        self._executor.shutdown(wait=True, cancel_futures=False)
        print("[Pipeline] 异步处理管线已关闭")


# 全局单例
pipeline = AsyncPipeline()
