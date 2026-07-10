"""
Chat Engine — 对话引擎服务

仿照 chat-app 的 ai.ts + useChat.ts 架构：

  ai.ts:
    buildSystemPrompt(knowledgeResults)  →  system prompt + KB context
    toModelMessages(messages)            →  API format (text / multimodal)
    streamText({model, system, messages})→  LLM streaming

  对应本模块:
    resolve_context()   →  ChatContext (temp files + search results + images)
    build_messages()    →  [system, context, ...history, user]  ← 统一构建器
    stream()            →  SSE generator (graceful degradation)

  ┌───────────────────────────────────────────────────┐
  │  routes/chat.py (HTTP 编排层)                       │
  │    保存用户消息 → 获取历史 → chat_engine → 保存回复    │
  └──────────────┬────────────────────────────────────┘
                 ▼
  ┌───────────────────────────────────────────────────┐
  │  ChatEngine                                         │
  │                                                     │
  │  1. resolve_context()  → ChatContext                │
  │     · _get_temp_file_text()     (附件文本)           │
  │     · _get_temp_file_images()   (附件图片)           │
  │     · _search_knowledge()       (hybrid_search)     │
  │       ↑ 只返回结构化搜索结果，不构建消息               │
  │                                                     │
  │  2. build_messages(message, ctx, history)           │
  │     · _build_system_prompt(citations)               │
  │     · _build_context_block(search_results, temp)    │
  │     · history truncation                            │
  │     · _build_user_message(text, temp, images)       │
  │       ↑ 所有路径(有/无RAG)走同一套构建逻辑             │
  │                                                     │
  │  3. stream(messages, citations, ai_config)          │
  │     · streaming_service.stream_chat()               │
  │     · fallback: multimodal → text → mock            │
  │     · _inject_citations() into done event           │
  └──────────────┬────────────────────────────────────┘
                 ▼
  ┌───────────────────────────────────────────────────┐
  │  StreamingService (SSE 传输层)                       │
  │  streaming_service.stream_chat() / pseudo_stream() │
  └───────────────────────────────────────────────────┘
"""
import json
import base64
import logging

logger = logging.getLogger(__name__)


class ChatEngine:
    """对话引擎 — 从用户输入到 SSE 流式响应的完整管线"""

    # ==================== Step 1: 上下文解析 ====================

    def resolve_context(self, message, course_id=None, temp_file_session_id=None,
                        ai_config=None):
        """
        解析对话上下文 — 返回结构化数据，不构建消息

        对应 chat-app:
          - useChat: processFileContent() — 处理附件
          - useChat: searchKnowledgeBases() — 知识库搜索
          - 返回 KnowledgeSearchResult[]，而非预构建的 messages

        Returns:
            ChatContext — 包含 temp_text, image_data, search_results, citations
        """
        ctx = ChatContext()

        # 1a. 临时文件文本
        if temp_file_session_id:
            ctx.temp_text = self._get_temp_file_text(temp_file_session_id)

        # 1b. 临时文件图片（用于多模态）
        if temp_file_session_id:
            ctx.image_data = self._get_temp_file_images(temp_file_session_id)

        # 1c. 知识库检索 — 只返回结构化搜索结果 (对应 chat-app searchKnowledgeBases)
        if course_id:
            ctx.search_results = self._search_knowledge(
                course_id, message, ai_config,
            )
            # 从搜索结果构建引用列表 (对应 chat-app KnowledgeSearchResult.score)
            ctx.citations = self._build_citations(ctx.search_results, course_id)
            ctx.has_rag = True
        else:
            ctx.has_rag = False

        return ctx

    # ==================== Step 2: 构建 LLM 消息 ====================

    def build_messages(self, message, ctx, conversation_history=None):
        """
        统一消息构建器 — 所有路径(有/无RAG)走同一套逻辑

        对应 chat-app 的 buildSystemPrompt() + toModelMessages()
        这是唯一构建 LLM 消息的入口，确保一致性。

        输出格式:
          [system(prompt), context_block?(user), ...history, user(text|multimodal)]
        """
        messages = []

        # ① System prompt (对应 chat-app buildSystemPrompt)
        system_prompt = self._build_system_prompt(
            citations=ctx.citations,
            has_temp_file=bool(ctx.temp_text),
            has_images=bool(ctx.image_data),
        )
        messages.append({'role': 'system', 'content': system_prompt})

        # ② 知识库上下文块 (对应 chat-app 将 knowledgeResults 注入 system prompt)
        context_block = self._build_context_block(ctx)
        if context_block:
            messages.append({'role': 'user', 'content': context_block})
            messages.append({
                'role': 'assistant',
                'content': '好的，我已阅读以上参考资料，会根据提供的资料来回答问题。',
            })

        # ③ 对话历史
        if conversation_history:
            messages.extend(conversation_history[-10:])

        # ④ 用户消息 — 多模态 or 纯文本 (对应 chat-app toModelMessages)
        user_msg = self._build_user_message(message, ctx.image_data)
        messages.append(user_msg)

        return messages

    # ==================== Step 3: 流式调用 ====================

    def stream(self, messages, citations=None, ai_config=None):
        """
        流式聊天 — SSE 事件生成器

        对应 chat-app 的 streamChat() (ai.ts)
        降级链: 多模态LLM → 纯文本LLM → Mock
        """
        from services.streaming_service import streaming_service

        has_images = self._messages_have_images(messages)

        def generator():
            error_occurred = False

            for event in streaming_service.stream_chat(messages, ai_config=ai_config):
                if event.startswith('data: '):
                    try:
                        data = json.loads(event[6:])
                        if data.get('done') and data.get('error'):
                            error_occurred = True
                            break
                    except json.JSONDecodeError:
                        pass
                yield event

            if not error_occurred:
                return

            # ---- 降级链 ----
            logger.warning("[ChatEngine] 流式调用检测到错误，进入降级链")

            if has_images:
                logger.info("[ChatEngine] 回退到纯文本模式")
                text_messages = self._strip_images(messages)
                try:
                    response_text = streaming_service.blocking_chat(
                        text_messages, ai_config=ai_config,
                    )
                    yield from streaming_service.pseudo_stream(response_text)
                    return
                except Exception as e2:
                    logger.warning(f"[ChatEngine] 纯文本回退失败: {e2}")

            logger.info("[ChatEngine] 回退到 Mock 模式")
            yield from self._mock_stream(messages)

        yield from self._inject_citations(generator(), citations)

    # ==================== 完整管线 ====================

    def process(self, message, course_id=None, conversation_history=None,
                temp_file_session_id=None, ai_config=None):
        """
        完整对话管线 — resolve → build → stream

        对应 chat-app useChat.send() 全流程

        Returns:
            (generator, citations)
        """
        ctx = self.resolve_context(message, course_id, temp_file_session_id, ai_config)
        messages = self.build_messages(message, ctx, conversation_history)
        gen = self.stream(messages, ctx.citations, ai_config)
        return gen, ctx.citations

    def process_blocking(self, message, course_id=None, conversation_history=None,
                         temp_file_session_id=None, ai_config=None):
        """阻塞式管线 — 返回完整文本"""
        ctx = self.resolve_context(message, course_id, temp_file_session_id, ai_config)
        messages = self.build_messages(message, ctx, conversation_history)

        from services.streaming_service import streaming_service
        has_images = self._messages_have_images(messages)

        try:
            response_text = streaming_service.blocking_chat(messages, ai_config=ai_config)
        except Exception as e:
            logger.warning(f"[ChatEngine] 阻塞调用失败: {e}")
            if has_images:
                text_messages = self._strip_images(messages)
                try:
                    response_text = streaming_service.blocking_chat(text_messages, ai_config=ai_config)
                except Exception:
                    response_text = self._mock_response(message)
            else:
                response_text = self._mock_response(message)

        return {'response': response_text, 'citations': ctx.citations}

    # ==================== 内部: 上下文获取 ====================

    def _get_temp_file_text(self, session_id):
        """获取临时文件文本"""
        try:
            from services.temp_file_service import temp_file_manager
            return temp_file_manager.get_context(session_id, wait_timeout=30) or ''
        except Exception as e:
            logger.warning(f"[ChatEngine] 获取临时文件文本失败: {e}")
            return ''

    def _get_temp_file_images(self, session_id):
        """获取临时文件图片"""
        try:
            from services.temp_file_service import temp_file_manager
            return temp_file_manager.get_image_data(session_id) or []
        except Exception as e:
            logger.warning(f"[ChatEngine] 获取临时文件图片失败: {e}")
            return []

    def _search_knowledge(self, course_id, query, ai_config):
        """
        知识库检索 — 只返回结构化搜索结果

        对应 chat-app 的 searchKnowledgeBases(content, knowledgeBases, {topK: 5})
        返回 KnowledgeSearchResult[] — 不做消息构建
        """
        try:
            from services.retrieval_service import RetrievalService
            retrieval = RetrievalService()
            results = retrieval.hybrid_search(
                course_id, query, top_k=8, ai_config=ai_config,
            )
            logger.info(f"[ChatEngine] 知识库检索: {len(results)} 条结果")
            return results
        except Exception as e:
            logger.warning(f"[ChatEngine] 知识库检索失败: {e}")
            return []

    def _build_citations(self, search_results, course_id):
        """
        从搜索结果构建引用列表

        对应 chat-app 的 KnowledgeSearchResult → {chunk, score, knowledgeBaseName}
        """
        if not search_results:
            return []

        # 加载文档名称映射
        doc_names = self._load_doc_names(course_id)

        citations = []
        for i, result in enumerate(search_results):
            doc_id = result.get('document_id') or result.get('metadata', {}).get('document_id', '')
            doc_name = doc_names.get(int(doc_id), '未知文档') if doc_id else '未知文档'
            heading = result.get('heading_path', '') or result.get('metadata', {}).get('heading_path', '')

            citations.append({
                'num': i + 1,
                'content': result.get('content', '')[:200],
                'document_id': str(doc_id),
                'doc_name': doc_name,
                'heading_path': heading,
                'score': round(result.get('score', 0), 4),
                'source': 'course_kb',
            })

        return citations

    @staticmethod
    def _load_doc_names(course_id):
        """加载课程文档 ID → 文件名映射"""
        try:
            from database import db
            docs = db.fetch_all(
                "SELECT id, original_name FROM documents WHERE course_id = ?",
                (course_id,)
            )
            return {d['id']: d['original_name'] for d in docs} if docs else {}
        except Exception:
            return {}

    # ==================== 内部: 消息构建 ====================

    def _build_system_prompt(self, citations=None, has_temp_file=False, has_images=False):
        """
        构建系统提示

        对应 chat-app 的 buildSystemPrompt(knowledgeResults):
          "You are a helpful AI assistant..."
          + "[Knowledge Base Context]" + results
        """
        prompt = (
            '你是课程学习助手AI，用中文回答。回答简洁准确。\n'
            '请用与用户相同的语言回答。\n'
        )

        # 引用指令 (对应 chat-app "Cite the source document name")
        if citations:
            prompt += '引用课程知识库内容时，必须标注编号，格式如 [1]。\n'
        if has_temp_file:
            prompt += '附件内容已提取为文字，引用时标注(临时文件)。\n'
        if has_images:
            prompt += '用户上传了图片，请仔细分析图片内容并回答。\n'

        prompt += '如果资料不足以回答，请诚实说明。\n'
        return prompt

    def _build_context_block(self, ctx):
        """
        构建知识库 + 临时文件的上下文文本块

        对应 chat-app buildSystemPrompt 中注入 knowledgeResults 的部分:
          "--- Source: doc.md (relevance: 85%) ---"
          "chunk text..."

        Returns:
            str or None — 作为独立 user 消息插入
        """
        parts = []

        # 临时文件上下文
        if ctx.temp_text:
            parts.append('【附件内容】（仅限本次对话有效）')
            parts.append(ctx.temp_text)
            parts.append('')

        # 知识库检索结果 (对应 chat-app 的 "Source: xxx (relevance: N%)")
        if ctx.search_results and ctx.citations:
            parts.append('【课程知识库参考资料】')
            for cite, result in zip(ctx.citations, ctx.search_results):
                source_label = f'[{cite["num"]}] 来源: {cite["doc_name"]}'
                if cite['heading_path']:
                    source_label += f' > {cite["heading_path"]}'
                parts.append(f'{source_label}\n{result["content"]}')
            parts.append('')
            parts.append('请根据以上资料回答用户问题。引用时标注编号如 [1]。')

        if not parts:
            return None

        return '\n\n'.join(parts)

    def _build_user_message(self, message, image_data):
        """
        构建用户消息（纯文本 or 多模态）

        对应 chat-app 的 toModelMessages() 中处理 image/text 部分:
          parts.push({type: 'text', text: content})
          parts.push({type: 'image', image: base64})

        注: temp_text 已在 _build_context_block() 中作为独立上下文注入
        """
        if not image_data:
            return {'role': 'user', 'content': message}

        # 多模态 (OpenAI Vision 格式)
        parts = []
        for img in image_data:
            try:
                b64 = base64.b64encode(img['image_bytes']).decode('utf-8')
                parts.append({
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:{img["mime_type"]};base64,{b64}',
                        'detail': 'high',
                    }
                })
            except Exception as e:
                logger.warning(f"[ChatEngine] 图片编码失败: {img.get('filename', '?')}: {e}")

        parts.append({'type': 'text', 'text': message})
        return {'role': 'user', 'content': parts}

    # ==================== 内部: 消息操作 ====================

    @staticmethod
    def _messages_have_images(messages):
        """检查消息列表是否包含图片"""
        for msg in messages:
            content = msg.get('content')
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'image_url':
                        return True
        return False

    @staticmethod
    def _strip_images(messages):
        """移除图片，降级为纯文本"""
        stripped = []
        for msg in messages:
            content = msg.get('content')
            if isinstance(content, list):
                text_parts = [
                    p['text'] for p in content
                    if isinstance(p, dict) and p.get('type') == 'text'
                ]
                stripped.append({'role': msg['role'], 'content': '\n'.join(text_parts)})
            else:
                stripped.append(msg)
        return stripped

    # ==================== 内部: 降级 ====================

    def _mock_stream(self, messages):
        """Mock 流式输出（最终降级）"""
        from services.streaming_service import streaming_service
        user_text = ''
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                user_text = content if isinstance(content, str) else str(content)
                break
        yield from streaming_service.pseudo_stream(self._mock_response(user_text))

    @staticmethod
    def _mock_response(user_text=''):
        """Mock 文本回复（最终降级）"""
        preview = (user_text or '')[:200]
        return (
            '你好！我是课程学习助手。\n\n'
            '目前 AI 服务暂时不可用，我已收到你的问题：\n\n'
            f'> {preview}\n\n'
            '请在 **AI 配置** 页面检查模型配置是否正确。'
        )

    # ==================== 内部: SSE 工具 ====================

    @staticmethod
    def _inject_citations(event_gen, citations):
        """在 done 事件中注入 citations"""
        if not citations:
            yield from event_gen
            return

        for event in event_gen:
            if event.startswith('data: '):
                try:
                    data = json.loads(event[6:])
                    if data.get('done'):
                        data['citations'] = [
                            {
                                'num': c.get('num'),
                                'heading_path': c.get('heading_path', ''),
                                'document_id': c.get('document_id', ''),
                                'doc_name': c.get('doc_name', ''),
                                'source': c.get('source', 'course_kb'),
                            }
                            for c in citations
                        ]
                        event = 'data: ' + json.dumps(data, ensure_ascii=False) + '\n\n'
                except (json.JSONDecodeError, KeyError):
                    pass
            yield event


class ChatContext:
    """
    对话上下文数据对象 — 承载 resolve_context() 的结构化结果

    对应 chat-app 中 useChat.send() 里的中间变量:
      processedAttachments, knowledgeResults 等
    """

    def __init__(self):
        self.temp_text = ''         # 临时文件文本
        self.image_data = []        # 临时文件图片 [{filename, image_bytes, mime_type}]
        self.search_results = []    # 知识库搜索结果 (对应 KnowledgeSearchResult[])
        self.citations = []         # 引用列表 (从 search_results 构建)
        self.has_rag = False        # 是否使用了知识库检索


# 全局单例
chat_engine = ChatEngine()
