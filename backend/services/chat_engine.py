"""
Chat Engine — 对话引擎服务

仿照 chat-app 的 ai.ts + useChat.ts 架构，提供清晰的对话处理管线：

  ┌───────────────────────────────────────────────────┐
  │  routes/chat.py (HTTP 编排层，对应 useChat.ts)      │
  │    保存用户消息 → 获取历史 → chat_engine → 保存回复    │
  └──────────────┬────────────────────────────────────┘
                 ▼
  ┌───────────────────────────────────────────────────┐
  │  ChatEngine (对话引擎，对应 ai.ts)                    │
  │                                                     │
  │  1. resolve_context()   ← 获取上下文 (临时文件 + RAG) │
  │  2. build_messages()    ← 构建 LLM 消息 (多模态)      │
  │  3. stream()            ← 流式调用 (优雅降级链)        │
  └───────────────────────────────────────────────────┘
                 ▼
  ┌───────────────────────────────────────────────────┐
  │  StreamingService (SSE 传输层)                       │
  │  streaming_service.stream_chat() / pseudo_stream() │
  └───────────────────────────────────────────────────┘

每个步骤职责单一、可独立测试，降级逻辑集中在 _call_with_fallback()。
"""
import json
import base64
import logging

logger = logging.getLogger(__name__)


class ChatEngine:
    """对话引擎 — 从用户输入到 SSE 流式响应的完整管线"""

    # ==================== Step 1: 上下文解析 ====================

    def resolve_context(self, message, course_id=None, temp_file_session_id=None,
                        conversation_history=None, ai_config=None):
        """
        解析对话上下文：临时文件 + 知识库检索 + 图片数据

        对应 chat-app 的:
          - useChat 中处理 attachments (processFileContent)
          - searchKnowledgeBases() 知识库搜索

        Args:
            message: 用户消息文本
            course_id: 课程 ID（有值时触发 RAG 检索）
            temp_file_session_id: 临时文件会话 ID
            conversation_history: 对话历史 [{'role', 'content'}]
            ai_config: 用户 AI 配置 dict

        Returns:
            ChatContext 对象
        """
        ctx = ChatContext()

        # 1a. 临时文件文本
        if temp_file_session_id:
            ctx.temp_text = self._get_temp_file_text(temp_file_session_id)

        # 1b. 临时文件图片（用于多模态）
        if temp_file_session_id:
            ctx.image_data = self._get_temp_file_images(temp_file_session_id)

        # 1c. RAG 检索（有课程时）
        if course_id:
            rag = self._retrieve_knowledge(course_id, message, ctx.temp_text,
                                           conversation_history, ai_config)
            ctx.citations = rag.get('citations', [])
            ctx.rag_messages = rag.get('messages', [])
            ctx.has_rag = True
        else:
            ctx.has_rag = False

        return ctx

    # ==================== Step 2: 构建 LLM 消息 ====================

    def build_messages(self, message, ctx, conversation_history=None):
        """
        构建发给 LLM 的消息列表

        对应 chat-app 的 toModelMessages() + buildSystemPrompt()

        输出格式 (OpenAI Messages API):
          [system, system(context?), ...history, user(text|multimodal)]

        Args:
            message: 用户消息文本
            ctx: ChatContext（来自 resolve_context）
            conversation_history: 对话历史

        Returns:
            list[dict]: LLM 消息列表
        """
        if ctx.has_rag and ctx.rag_messages:
            # RAG 管线已构建完整消息列表 (system + context + history + user)
            messages = list(ctx.rag_messages)

            # 有图片时，将图片附加到最后一条 user 消息
            if ctx.image_data:
                messages = self._attach_images(messages, ctx.image_data)
            return messages

        # 无 RAG — 手动构建 (对应 chat-app 的 buildSystemPrompt + toModelMessages)
        system_prompt = self._build_system_prompt(
            has_temp_file=bool(ctx.temp_text),
            has_images=bool(ctx.image_data),
        )
        messages = [{'role': 'system', 'content': system_prompt}]

        # 对话历史
        if conversation_history:
            messages.extend(conversation_history[-10:])

        # 用户消息（多模态 or 纯文本）
        user_msg = self._build_user_message(message, ctx.temp_text, ctx.image_data)
        messages.append(user_msg)

        return messages

    # ==================== Step 3: 流式调用 ====================

    def stream(self, messages, citations=None, ai_config=None):
        """
        流式聊天 — 返回 SSE 事件生成器

        对应 chat-app 的 streamChat() (ai.ts)
        降级链: 多模态LLM → 纯文本LLM → Mock

        Args:
            messages: LLM 消息列表
            citations: 引用列表（注入到 done 事件中）
            ai_config: 用户 AI 配置

        Yields:
            str: SSE 格式事件 "data: {...}\\n\\n"
        """
        from services.streaming_service import streaming_service

        has_images = self._messages_have_images(messages)

        def generator():
            error_occurred = False

            # 尝试 1: 正常流式调用
            for event in streaming_service.stream_chat(messages, ai_config=ai_config):
                # 检测 SSE 错误事件（streaming_service 不抛异常，而是 yield 错误）
                if event.startswith('data: '):
                    try:
                        data = json.loads(event[6:])
                        if data.get('done') and data.get('error'):
                            error_occurred = True
                            break  # 停止消费，进入降级链
                    except json.JSONDecodeError:
                        pass
                yield event

            if not error_occurred:
                return  # 正常结束

            # ---- 降级链 ----
            logger.warning("[ChatEngine] 流式调用检测到错误，进入降级链")

            # 尝试 2: 多模态失败 → 纯文本
            if has_images:
                logger.info("[ChatEngine] 回退到纯文本模式（移除图片）")
                text_messages = self._strip_images(messages)
                try:
                    response_text = streaming_service.blocking_chat(
                        text_messages, ai_config=ai_config,
                    )
                    yield from streaming_service.pseudo_stream(response_text)
                    return
                except Exception as e2:
                    logger.warning(f"[ChatEngine] 纯文本回退也失败: {e2}")

            # 尝试 3: 最终降级 → Mock
            logger.info("[ChatEngine] 回退到 Mock 模式")
            yield from self._mock_stream(messages)

        # 包装：在 done 事件中注入 citations
        yield from self._inject_citations(generator(), citations)

    # ==================== 完整管线 (一步到位) ====================

    def process(self, message, course_id=None, conversation_history=None,
                temp_file_session_id=None, ai_config=None):
        """
        完整对话管线 — resolve_context → build_messages → stream

        对应 chat-app 的 useChat.send() 完整流程

        Args:
            message: 用户消息文本
            course_id: 课程 ID
            conversation_history: 对话历史
            temp_file_session_id: 临时文件会话 ID
            ai_config: 用户 AI 配置

        Returns:
            (generator, citations) 元组
              generator: SSE 事件生成器
              citations: 引用列表（用于保存到数据库）
        """
        # Step 1: 上下文
        ctx = self.resolve_context(
            message, course_id, temp_file_session_id,
            conversation_history, ai_config,
        )

        # Step 2: 消息
        messages = self.build_messages(message, ctx, conversation_history)

        # Step 3: 流式
        gen = self.stream(messages, ctx.citations, ai_config)

        return gen, ctx.citations

    def process_blocking(self, message, course_id=None, conversation_history=None,
                         temp_file_session_id=None, ai_config=None):
        """
        阻塞式对话管线 — 非流式，返回完整文本

        对应 chat-app 的 streamChat 但等待完整结果

        Returns:
            dict: {'response': str, 'citations': list}
        """
        # Step 1: 上下文
        ctx = self.resolve_context(
            message, course_id, temp_file_session_id,
            conversation_history, ai_config,
        )

        # Step 2: 消息
        messages = self.build_messages(message, ctx, conversation_history)

        # Step 3: 阻塞调用
        from services.streaming_service import streaming_service

        has_images = self._messages_have_images(messages)

        try:
            response_text = streaming_service.blocking_chat(messages, ai_config=ai_config)
        except Exception as e:
            logger.warning(f"[ChatEngine] 阻塞调用失败: {e}")
            if has_images:
                logger.info("[ChatEngine] 回退纯文本")
                text_messages = self._strip_images(messages)
                try:
                    response_text = streaming_service.blocking_chat(text_messages, ai_config=ai_config)
                except Exception:
                    response_text = self._mock_response(message)
            else:
                response_text = self._mock_response(message)

        return {'response': response_text, 'citations': ctx.citations}

    # ==================== 内部方法 ====================

    def _get_temp_file_text(self, session_id):
        """获取临时文件文本上下文"""
        try:
            from services.temp_file_service import temp_file_manager
            return temp_file_manager.get_context(session_id, wait_timeout=30) or ''
        except Exception as e:
            logger.warning(f"[ChatEngine] 获取临时文件文本失败: {e}")
            return ''

    def _get_temp_file_images(self, session_id):
        """获取临时文件中的图片数据"""
        try:
            from services.temp_file_service import temp_file_manager
            return temp_file_manager.get_image_data(session_id) or []
        except Exception as e:
            logger.warning(f"[ChatEngine] 获取临时文件图片失败: {e}")
            return []

    def _retrieve_knowledge(self, course_id, query, temp_text,
                            conversation_history, ai_config):
        """
        RAG 知识库检索

        对应 chat-app 的 searchKnowledgeBases()
        """
        try:
            from services.retrieval_service import RetrievalService
            retrieval = RetrievalService()
            result = retrieval.build_rag_context(
                course_id=course_id,
                query=query,
                temp_file_text=temp_text,
                conversation_history=conversation_history,
                ai_config=ai_config,
            )
            logger.info(
                f"[ChatEngine] RAG 检索完成: "
                f"{len(result.get('citations', []))} 条引用, "
                f"{result.get('token_count', 0)} tokens"
            )
            return result
        except Exception as e:
            logger.warning(f"[ChatEngine] RAG 检索失败: {e}")
            return {'messages': [], 'citations': []}

    def _build_system_prompt(self, has_temp_file=False, has_images=False):
        """
        构建系统提示

        对应 chat-app 的 buildSystemPrompt() in ai.ts
        """
        prompt = (
            '你是课程学习助手AI，用中文回答。回答简洁准确。\n'
            '请用与用户相同的语言回答。\n'
        )
        if has_temp_file:
            prompt += '临时文件内容已提取为文字，可直接引用，标注(临时文件)。\n'
        if has_images:
            prompt += '用户上传了图片，请仔细分析图片内容并回答。\n'
        prompt += '如果资料不足以回答，请诚实说明。\n'
        return prompt

    def _build_user_message(self, message, temp_text, image_data):
        """
        构建用户消息（纯文本 or 多模态）

        对应 chat-app 的 toModelMessages() 中处理 image/text 部分
        """
        if not image_data:
            # 纯文本
            text = ''
            if temp_text:
                text += f'[附件内容]\n{temp_text}\n\n'
            text += message
            return {'role': 'user', 'content': text}

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

        text = ''
        if temp_text:
            text += f'[附件内容]\n{temp_text}\n\n'
        text += message
        parts.append({'type': 'text', 'text': text})

        return {'role': 'user', 'content': parts}

    def _attach_images(self, messages, image_data):
        """将图片附加到最后一条 user 消息"""
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get('role') == 'user':
                original = messages[i].get('content', '')
                if isinstance(original, str):
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
                        except Exception:
                            pass
                    parts.append({'type': 'text', 'text': original})
                    messages[i] = {'role': 'user', 'content': parts}
                break
        return messages

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
        """移除消息中的图片部分，降级为纯文本"""
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

    def _mock_stream(self, messages):
        """Mock 模式流式输出（最终降级）"""
        from services.streaming_service import streaming_service
        user_text = ''
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                user_text = content if isinstance(content, str) else str(content)
                break

        mock_response = self._mock_response(user_text)
        yield from streaming_service.pseudo_stream(mock_response)

    @staticmethod
    def _mock_response(user_text=''):
        """Mock 模式文本回复（最终降级）"""
        preview = (user_text or '')[:200]
        return (
            '你好！我是课程学习助手。\n\n'
            '目前 AI 服务暂时不可用，我已收到你的问题：\n\n'
            f'> {preview}\n\n'
            '请在 **AI 配置** 页面检查模型配置是否正确。'
        )

    @staticmethod
    def _inject_citations(event_gen, citations):
        """
        在 SSE done 事件中注入 citations 数据

        这样前端可以在流结束时获取引用来源信息
        """
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
    """对话上下文数据对象 — 承载 resolve_context 的结果"""

    def __init__(self):
        self.temp_text = ''         # 临时文件提取的文本
        self.image_data = []        # 临时文件中的图片 [{filename, image_bytes, mime_type}]
        self.citations = []         # RAG 引用列表
        self.rag_messages = []      # RAG 管线构建的完整消息列表
        self.has_rag = False        # 是否使用了 RAG 检索


# 全局单例
chat_engine = ChatEngine()
