"""
混合检索服务

结合向量检索和 BM25 关键词检索：
- RRF (Reciprocal Rank Fusion) 融合排序
- 元数据过滤支持
- 引用编号自动分配
- 上下文窗口管理
"""
import logging

logger = logging.getLogger(__name__)


class RetrievalService:
    """混合检索引擎"""

    RRF_K = 60  # RRF 融合参数

    def hybrid_search(self, course_id, query, top_k=10, metadata_filter=None, ai_config=None):
        """
        混合检索 — 有嵌入模型时走向量+BM25 RRF融合，否则纯BM25

        Args:
            course_id: 课程 ID
            query: 查询文本
            top_k: 返回结果数
            metadata_filter: 元数据过滤条件（保留接口，当前未使用）
            ai_config: 用户AI配置 dict（可选，含 embedding_api_key/url/model）

        Returns:
            list[dict]: 检索结果
        """
        from services.bm25_manager import bm25_manager

        # BM25 关键词检索（始终可用）
        bm25_results = bm25_manager.search(course_id, query, top_k=top_k * 2)

        # 向量检索（嵌入模型已配置时）
        vector_results = []
        if self._has_embedding(ai_config):
            try:
                from services.embedding_service import embedding_service
                from services.vector_store import vector_store

                query_embeddings = embedding_service.embed_texts([query], ai_config=ai_config)
                if query_embeddings and query_embeddings[0]:
                    vector_results = vector_store.search(
                        course_id, query_embeddings[0], top_k=top_k * 2, metadata_filter=metadata_filter
                    )
                    if vector_results:
                        logger.info(f"[检索] 向量检索返回 {len(vector_results)} 条, BM25 {len(bm25_results)} 条 → RRF 融合")
            except Exception as e:
                logger.warning(f"[检索] 向量检索失败，降级到纯 BM25: {e}")

        # 融合或单路返回
        if vector_results and bm25_results:
            results = self._rrf_fusion(vector_results, bm25_results, top_k)
        elif vector_results:
            results = vector_results[:top_k]
        else:
            results = bm25_results

        return results[:top_k]

    def _has_embedding(self, ai_config):
        """检查是否配置了嵌入模型"""
        if not ai_config:
            return False
        key = (ai_config.get('embedding_api_key') or '').strip()
        url = (ai_config.get('embedding_api_url') or '').strip()
        return bool(key and url)

    def _rrf_fusion(self, vector_results, bm25_results, top_k):
        """
        RRF (Reciprocal Rank Fusion) 融合排序

        公式: score(d) = sum(1 / (k + rank_i(d)) for each retriever i)
        k = 60 降低高排名项的权重差异

        使用内容摘要作为融合 key，确保相同内容的向量和 BM25 结果真正融合。
        """
        import hashlib

        def content_key(text):
            return hashlib.md5(text.encode('utf-8')).hexdigest()

        scores = {}       # content_hash -> rrf_score
        best_item = {}    # content_hash -> best item dict

        # 向量检索排名
        for rank, item in enumerate(vector_results):
            content = item.get('content', '')
            if not content:
                continue
            ck = content_key(content)
            scores[ck] = scores.get(ck, 0) + 1.0 / (self.RRF_K + rank + 1)
            meta = item.get('metadata', {})
            if ck not in best_item:
                best_item[ck] = {
                    'content': content,
                    'document_id': meta.get('document_id', ''),
                    'heading_path': meta.get('heading_path', ''),
                    'metadata': meta,
                    'chunk_id': item.get('chunk_id', ''),
                    'source': 'vector',
                }

        # BM25 检索排名
        for rank, item in enumerate(bm25_results):
            content = item.get('content', '')
            if not content:
                continue
            ck = content_key(content)
            scores[ck] = scores.get(ck, 0) + 1.0 / (self.RRF_K + rank + 1)
            if ck not in best_item:
                best_item[ck] = {
                    'content': content,
                    'document_id': str(item.get('document_id', '')),
                    'heading_path': item.get('heading_path', ''),
                    'metadata': {
                        'chunk_index': item.get('chunk_index'),
                        'document_id': str(item.get('document_id', '')),
                        'heading_path': item.get('heading_path', ''),
                    },
                    'chunk_id': f"bm25_{item.get('chunk_index', 0)}",
                    'source': 'bm25',
                }
            elif best_item[ck]['source'] == 'vector':
                # 补充 BM25 特有的字段（如 document_id 可能更完整）
                if not best_item[ck].get('document_id'):
                    best_item[ck]['document_id'] = str(item.get('document_id', ''))
                if not best_item[ck].get('heading_path'):
                    best_item[ck]['heading_path'] = item.get('heading_path', '')

        # 构建融合结果
        fused_list = []
        for ck, score in scores.items():
            item = best_item.get(ck, {})
            item['score'] = score
            fused_list.append(item)

        # 按 RRF 分数排序
        fused_list.sort(key=lambda x: x['score'], reverse=True)
        return fused_list[:top_k]

