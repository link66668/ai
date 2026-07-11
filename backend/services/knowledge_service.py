"""
Knowledge Service — 知识库检索的统一入口

职责单一:
1. 调用混合检索获取结果
2. 标准化结果格式（统一字段名）
3. 构建 LLM 上下文块
4. 构建前端引用列表

对应 cherry-studio 的 KnowledgeService + KnowledgeSearchTool:
  - 所有 KB 操作走这一个类
  - 返回格式统一的 KnowledgeResult[]
  - 引用构建和上下文格式化都在这里完成
"""
import logging

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识库服务 — 搜索 + 格式化 + 引用构建"""

    def search(self, course_id, query, ai_config=None, top_k=8):
        """
        知识库检索 — 返回标准化结果

        Args:
            course_id: 课程 ID
            query: 用户问题
            ai_config: AI 配置（含嵌入 API 设置）
            top_k: 返回结果数

        Returns:
            KnowledgeResult[] — 每个元素:
                {num, content, doc_name, heading_path, score, document_id, source}
        """
        if not course_id:
            return []

        from services.retrieval_service import RetrievalService

        try:
            retrieval = RetrievalService()
            raw_results = retrieval.hybrid_search(
                course_id, query, top_k=top_k, ai_config=ai_config,
            )
        except Exception as e:
            logger.warning(f"[KnowledgeService] 检索失败: {e}")
            return []

        if not raw_results:
            return []

        # 加载文档名映射（一次查询，供所有结果使用）
        doc_names = self._load_doc_names(course_id)

        # 标准化结果
        results = []
        for i, r in enumerate(raw_results):
            doc_id = r.get('document_id') or ''
            # 兼容两种字段位置：root 或 metadata 内
            if not doc_id and 'metadata' in r:
                doc_id = r['metadata'].get('document_id', '')

            heading = r.get('heading_path') or ''
            if not heading and 'metadata' in r:
                heading = r['metadata'].get('heading_path', '')

            doc_name = '未知文档'
            if doc_id:
                try:
                    doc_name = doc_names.get(int(doc_id), '未知文档')
                except (ValueError, TypeError):
                    doc_name = '未知文档'

            results.append({
                'num': i + 1,
                'content': r.get('content', ''),
                'doc_name': doc_name,
                'heading_path': heading,
                'score': round(float(r.get('score', 0)), 4),
                'document_id': str(doc_id),
                'source': 'course_kb',
            })

        logger.info(f"[KnowledgeService] 检索 {len(results)} 条结果 for course={course_id}")
        return results

    def format_context(self, results, temp_text=''):
        """
        将知识库结果格式化为 LLM 上下文文本块

        Args:
            results: KnowledgeResult[]（来自 search()）
            temp_text: 临时文件文本（可选）

        Returns:
            str — 上下文文本，或 None（无上下文时）
        """
        parts = []

        if temp_text:
            parts.append('【附件内容】（仅限本次对话有效）')
            parts.append(temp_text)
            parts.append('')

        if results:
            parts.append('【课程知识库参考资料】')
            for r in results:
                source = f'[{r["num"]}] 来源: {r["doc_name"]}'
                if r['heading_path']:
                    source += f' > {r["heading_path"]}'
                score_label = f'（相关度: {r["score"]:.2f}）' if r.get('score') else ''
                content = (r.get('content') or '')[:500]
                parts.append(f'{source} {score_label}\n{content}')
            parts.append('')
            parts.append(
                '请根据以上资料回答。引用时在句子末尾标注编号如 [1]，'
                '回答末尾列出你实际引用的「参考资料」章节。'
            )

        return '\n\n'.join(parts) if parts else None

    def format_citations(self, results):
        """
        将知识库结果格式化为前端引用列表

        Args:
            results: KnowledgeResult[]（来自 search()）

        Returns:
            list[dict] — 前端用的 citation 格式
        """
        if not results:
            return []

        return [
            {
                'num': r['num'],
                'doc_name': r['doc_name'],
                'heading_path': r['heading_path'],
                'document_id': r['document_id'],
                'score': r['score'],
                'source': r['source'],
            }
            for r in results
        ]

    @staticmethod
    def verify_citations(response_text, citations):
        """
        验证回答中实际引用了哪些来源

        对应 cherry-studio normalizeCitations:
          扫描 text 中的 [N] 标记 → 只保留实际引用的

        Returns:
            list[dict]: 实际被引用的 citation 子集
        """
        if not response_text or not citations:
            return citations or []

        import re
        used_nums = set()
        for m in re.finditer(r'\[(\d+)\]', response_text):
            used_nums.add(int(m.group(1)))

        if not used_nums:
            return []

        return [c for c in citations if c.get('num') in used_nums]

    @staticmethod
    def _load_doc_names(course_id):
        """加载课程文档 ID → 文件名映射"""
        try:
            from database import db
            rows = db.fetch_all(
                "SELECT id, original_name FROM documents WHERE course_id = ?",
                (course_id,)
            )
            return {r['id']: r['original_name'] for r in rows} if rows else {}
        except Exception:
            return {}


# 全局单例
knowledge_service = KnowledgeService()
