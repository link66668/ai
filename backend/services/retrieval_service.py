"""
混合检索服务

结合向量检索和 BM25 关键词检索：
- RRF (Reciprocal Rank Fusion) 融合排序
- 元数据过滤支持
- 引用编号自动分配
- 上下文窗口管理
"""
import logging
from config import Config

logger = logging.getLogger(__name__)


class RetrievalService:
    """混合检索引擎"""

    RRF_K = 60  # RRF 融合参数

    def __init__(self):
        self._tokenizer = None

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            import tiktoken
            try:
                self._tokenizer = tiktoken.get_encoding('cl100k_base')
            except Exception:
                self._tokenizer = tiktoken.get_encoding('o200k_base')
        return self._tokenizer

    def count_tokens(self, text):
        """计算 token 数量"""
        try:
            return len(self.tokenizer.encode(text))
        except Exception:
            return len(text) // 2

    def hybrid_search(self, course_id, query, top_k=10, metadata_filter=None, ai_config=None):
        """
        混合检索：向量 + BM25 → RRF 融合

        Args:
            course_id: 课程 ID
            query: 查询文本
            top_k: 返回结果数
            metadata_filter: 元数据过滤条件
            ai_config: 用户AI配置 dict（可选）

        Returns:
            list[dict]: 排序后的检索结果
        """
        from services.embedding_service import embedding_service
        from services.vector_store import vector_store
        from services.bm25_manager import bm25_manager

        # 1. 向量检索
        query_embedding = embedding_service.embed_query(query, ai_config=ai_config)
        vector_results = vector_store.search(
            course_id, query_embedding, top_k=top_k * 2,
            metadata_filter=metadata_filter
        )

        # 2. BM25 检索
        bm25_results = bm25_manager.search(course_id, query, top_k=top_k * 2)

        # 3. RRF 融合
        fused = self._rrf_fusion(vector_results, bm25_results, top_k)
        return fused

    def _rrf_fusion(self, vector_results, bm25_results, top_k):
        """
        RRF (Reciprocal Rank Fusion) 融合排序

        公式: score(d) = sum(1 / (k + rank_i(d)) for each retriever i)
        k = 60 降低高排名项的权重差异
        """
        scores = {}

        # 向量检索排名
        for rank, item in enumerate(vector_results):
            key = item.get('chunk_id', item.get('content', str(rank)))
            scores[key] = scores.get(key, 0) + 1.0 / (self.RRF_K + rank + 1)
            if key not in [i.get('chunk_id', i.get('content', '')) for i in getattr(self, '_vec_items', [])]:
                pass  # Will merge content below

        # BM25 检索排名
        for rank, item in enumerate(bm25_results):
            key = f"bm25_{item.get('chunk_index', rank)}"
            scores[key] = scores.get(key, 0) + 1.0 / (self.RRF_K + rank + 1)

        # 构建融合结果
        fused_list = []

        # 添加向量检索结果（带融合分数）
        seen_contents = set()
        for item in vector_results:
            key = item.get('chunk_id', '')
            content = item.get('content', '')
            if content in seen_contents:
                continue
            seen_contents.add(content)
            fused_list.append({
                'content': content,
                'score': scores.get(key, 0),
                'source': 'vector',
                'metadata': item.get('metadata', {}),
                'chunk_id': key,
            })

        # 添加 BM25 结果（去重）
        for item in bm25_results:
            content = item.get('content', '')
            if content in seen_contents:
                continue
            seen_contents.add(content)
            key = f"bm25_{item.get('chunk_index', 0)}"
            fused_list.append({
                'content': content,
                'score': scores.get(key, 0),
                'source': 'bm25',
                'metadata': {
                    'chunk_index': item.get('chunk_index'),
                    'document_id': str(item.get('document_id', '')),
                    'heading_path': item.get('heading_path', ''),
                },
                'chunk_id': key,
            })

        # 按分数排序
        fused_list.sort(key=lambda x: x['score'], reverse=True)
        return fused_list[:top_k]

    def build_rag_context(self, course_id, query, temp_file_text='',
                          conversation_history=None, top_k=8, ai_config=None):
        """
        构建完整的 RAG 上下文

        Args:
            course_id: 课程 ID（可选）
            query: 用户查询
            temp_file_text: 临时文件文本内容
            conversation_history: 对话历史
            top_k: 检索结果数

        Returns:
            dict: {
                'messages': [...],       # LLM messages格式
                'citations': [...],      # 引用列表
                'has_temp_file': bool,   # 是否包含临时文件
                'token_count': int,      # 上下文 token 总数
            }
        """
        citations = []
        context_parts = []
        total_tokens = 0

        # 1. 课程知识库检索
        if course_id:
            search_results = self.hybrid_search(course_id, query, top_k=top_k, ai_config=ai_config)

            if search_results:
                context_parts.append('【课程资料】')
                for i, result in enumerate(search_results):
                    citation_num = i + 1
                    content = result['content']
                    context_parts.append(f'[{citation_num}] {content}')
                    citations.append({
                        'num': citation_num,
                        'content': content[:200],
                        'chunk_id': result.get('chunk_id', ''),
                        'document_id': result.get('metadata', {}).get('document_id', ''),
                        'heading_path': result.get('metadata', {}).get('heading_path', ''),
                        'score': round(result['score'], 4),
                    })
                    total_tokens += self.count_tokens(content)

        # 2. 临时文件上下文
        has_temp_file = bool(temp_file_text)
        if temp_file_text:
            context_parts.insert(0, '【临时文件】（仅限本次对话有效）')
            context_parts.insert(1, temp_file_text)
            citations.append({
                'num': 0,
                'content': '(临时文件)',
                'source': 'temp_file',
                'note': '来自当前对话上传的临时文件，不保存到知识库',
            })
            total_tokens += self.count_tokens(temp_file_text)

        # 3. 构建系统提示
        system_prompt = self._build_system_prompt(
            has_course_kb=bool(course_id and search_results),
            has_temp_file=has_temp_file,
        )

        # 4. 构建消息列表
        messages = [{'role': 'system', 'content': system_prompt}]

        # 添加上下文
        if context_parts:
            context_text = '\n\n'.join(context_parts)
            messages.append({
                'role': 'system',
                'content': f'以下是可以用来回答问题的参考资料：\n\n{context_text}\n\n请根据以上资料回答用户问题。引用课程资料时请标注编号如[1]，引用临时文件时标注(临时文件)。'
            })

        # 5. 添加对话历史（在 token 限制内）
        if conversation_history:
            max_history_tokens = Config.MAX_CONTEXT_TOKENS - total_tokens - 1000  # 留 1000 给回答
            history_messages = self._truncate_history(
                conversation_history, max_history_tokens
            )
            messages.extend(history_messages)

        # 6. 添加当前用户消息
        messages.append({'role': 'user', 'content': query})

        return {
            'messages': messages,
            'citations': citations,
            'has_temp_file': has_temp_file,
            'token_count': sum(self.count_tokens(m['content']) for m in messages),
        }

    def _build_system_prompt(self, has_course_kb=False, has_temp_file=False):
        """构建系统提示"""
        prompt = '你是课程学习助手AI，帮助学生学习课程内容。回答问题时：\n'
        prompt += '1. 请用中文回答\n'
        prompt += '2. 回答应准确、简洁、有组织\n'

        if has_course_kb:
            prompt += '3. 引用课程资料时使用编号标注，如[1]、[2]\n'
        if has_temp_file:
            prompt += '4. 临时文件中的图片内容已经过视觉识别提取为文字，你可以直接阅读和分析这些文字内容。引用临时文件内容时标注(临时文件)\n'

        prompt += '5. 如果参考资料不足以回答问题，请诚实说明\n'
        prompt += '6. 可以结合你的知识进行补充，但要明确区分资料来源和你的推断\n'

        return prompt

    def _truncate_history(self, history, max_tokens):
        """
        截断对话历史以符合 token 限制

        保留最近的对话，从后往前截取
        """
        if not history:
            return []

        truncated = []
        token_count = 0

        for msg in reversed(history):
            msg_tokens = self.count_tokens(msg.get('content', ''))
            if token_count + msg_tokens > max_tokens:
                # 如果已经有一定历史，停止
                if truncated:
                    break
                # 如果这是第一条，截断内容
                content = msg.get('content', '')
                # 粗略截断
                cutoff = int(len(content) * max_tokens / msg_tokens) if msg_tokens > 0 else len(content)
                truncated.insert(0, {
                    'role': msg['role'],
                    'content': content[:cutoff] + '...',
                })
                break

            truncated.insert(0, msg)
            token_count += msg_tokens

        return truncated
