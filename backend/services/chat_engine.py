"""
Chat Engine — 对话引擎服务（仿 cherry-studio Agent 模式）

流程:
  routes/chat.py
    → chat_engine.process(message, course_id, ...)
      → 构建 messages（含 kb_search 工具定义）
      → streaming_service.stream_with_tools(
           messages, tools=[kb_search],
           tool_executor=executor,        ← LLM 调工具时执行知识库搜索
         )
      → 流式输出 SSE 事件（text / tool_call / tool_result 混合）
    ← (SSE generator, citations)

  routes/chat.py 消费 SSE:
    tool_call_start  → 前端显示"正在搜索..."
    tool_call_end    → 前端显示"找到 N 条结果"
    text             → 前端渲染增量文本
    done             → 引用验证 + 保存 DB
"""
import json
import base64
import threading
import logging

logger = logging.getLogger(__name__)


class ChatEngine:
    """对话引擎 — 工具循环 + SSE 流式输出"""

    # kb_search 工具定义（OpenAI function calling 格式）
    KB_SEARCH_TOOL = {
        'type': 'function',
        'function': {
            'name': 'kb_search',
            'description': '搜索课程知识库，获取与问题相关的参考资料。'
                           '你可以用不同关键词多次调用此工具，'
                           '从多篇文档中找到全面信息。',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': '搜索关键词，建议用中文原文搜索。'
                                       '比如想找不同章节的内容，可以分别搜索',
                    },
                },
                'required': ['query'],
            },
        },
    }

    _stream_lock = threading.Lock()

    def process(self, message, course_id=None, conversation_history=None,
                temp_file_session_id=None, ai_config=None, conversation_id=None):
        """
        完整对话管线 — 工具循环 + 流式输出

        Args:
            message: 用户消息
            course_id: 知识库课程 ID（None=不启用知识库）
            conversation_history: 对话历史
            temp_file_session_id: 临时文件会话 ID
            ai_config: AI 配置
            conversation_id: 对话 ID

        Returns:
            (SSE generator, citations_list)
            citations_list 在流开始前为空，工具执行后自动填充，
            路由层在流结束后读取即可。
        """
        from services.streaming_service import streaming_service
        from services.knowledge_service import knowledge_service

        messages = self._build_messages(
            message=message,
            course_id=course_id,
            conversation_history=conversation_history,
            temp_file_session_id=temp_file_session_id,
            ai_config=ai_config,
        )

        tools = [self.KB_SEARCH_TOOL] if course_id else []

        # 引用列表容器 — 工具执行时填充，路由层在流结束后读取
        captured_citations = []

        # 可用文档列表（只需查询一次）
        available_docs = knowledge_service.get_available_docs(course_id) if course_id else []

        def tool_executor(func_name, func_args):
            """工具执行器 — 执行知识库搜索并填充 captured_citations"""
            if func_name == 'kb_search':
                query = func_args.get('query', message)
                # max_per_document=3 确保结果来自多篇文档
                results = knowledge_service.search(
                    course_id, query, ai_config=ai_config,
                    top_k=8, max_per_document=3,
                )
                cites = knowledge_service.format_citations(results)
                captured_citations[:] = cites

                response = {
                    'results': [
                        {
                            'num': r['num'],
                            'content': (r.get('content') or '')[:500],
                            'doc_name': r['doc_name'],
                            'heading_path': r['heading_path'],
                            'score': r['score'],
                        }
                        for r in results
                    ],
                    'citations': cites,
                }

                # 告诉 LLM 知识库有哪些文档可用，方便它决定是否继续搜索
                if available_docs:
                    response['available_docs'] = [
                        d['name'] for d in available_docs
                    ]

                return response
            return {'error': f'未知工具: {func_name}'}

        gen = streaming_service.stream_with_tools(
            messages=messages,
            tools=tools,
            tool_executor=tool_executor,
            conversation_id=conversation_id,
            ai_config=ai_config,
        )

        return gen, captured_citations

    # ==================== 消息构建 ====================

    def _build_messages(self, message, course_id=None,
                        conversation_history=None, temp_file_session_id=None,
                        ai_config=None):
        """构建 messages，包含 system prompt + 知识库提示 + 历史"""
        from services.knowledge_service import knowledge_service

        temp_text = ''
        image_data = []
        if temp_file_session_id:
            temp_text = self._get_temp_file_text(temp_file_session_id)
            image_data = self._get_temp_file_images(temp_file_session_id)

        # ② 图片预处理：有视觉配置时尝试走视觉模型，失败则回退多模态
        vision_text = ''
        if image_data and ai_config and ai_config.get('vision_api_key'):
            vision_text = self._vision_preprocess_images(image_data, ai_config)
            if vision_text:
                # 视觉预处理成功 → 图片不再直接传给对话模型
                image_data = []

        messages = []

        # ① System prompt
        system_prompt = self._build_system_prompt(
            has_kb=bool(course_id),
            has_temp_file=bool(temp_text or vision_text),
            has_images=bool(image_data),  # 有图片且未走视觉预处理 → 多模态
            course_id=course_id,
        )
        if vision_text:
            system_prompt += (
                '用户上传的图片已经过视觉模型分析，分析结果在下方附件中。\n'
                '请根据分析结果回答用户问题。\n'
            )
        messages.append({'role': 'system', 'content': system_prompt})

        # ③ 附件上下文（非图片文本 + 视觉分析结果）
        attachment_parts = []
        if temp_text:
            attachment_parts.append(f'【附件内容】（仅限本次对话有效）\n\n{temp_text}')
        if vision_text:
            attachment_parts.append(f'【图片分析结果】（视觉模型预处理）\n\n{vision_text}')
        if attachment_parts:
            messages.append({
                'role': 'user',
                'content': '\n\n'.join(attachment_parts),
            })
            messages.append({
                'role': 'assistant',
                'content': '好的，我已阅读附件内容。',
            })

        # ④ 对话历史
        if conversation_history:
            messages.extend(conversation_history[-10:])

        # ⑤ 用户消息（有图片且未走视觉 → 多模态；否则纯文本）
        messages.append(self._build_user_message(message, image_data))

        return messages

    def _build_system_prompt(self, has_kb=False, has_temp_file=False,
                              has_images=False, course_id=None):
        """构建系统提示"""
        from services.knowledge_service import knowledge_service

        prompt = (
            '你是课程学习助手AI，用中文回答。回答简洁准确。\n'
            '请用与用户相同的语言回答。\n'
        )

        if has_kb:
            prompt += (
                '你可以调用 kb_search 工具来搜索课程知识库获取参考资料。\n'
                '当你需要使用知识库时，请调用此工具。你可以多次调用 kb_search '
                '（使用不同的搜索词）来从多篇文档中找到相关信息。\n'
            )

            # 告知 LLM 知识库中有哪些文档可用
            available_docs = knowledge_service.get_available_docs(course_id)
            if available_docs:
                doc_list = '\n'.join(
                    f'  - {d["name"]}' for d in available_docs
                )
                prompt += (
                    '当前知识库包含以下文档：\n'
                    f'{doc_list}\n'
                    '回答问题时，尽量引用多篇文档的信息，不要只用单一来源。\n'
                )

            prompt += (
                '【引用规则】\n'
                '1. 引用知识库内容时，必须在句子末尾标注编号，格式如 [1]。\n'
                '2. 如果一句话来自多个来源，请全部标出，格式如 [1][2]。\n'
                '3. 禁止编造回答中未出现的来源编号。\n'
                '4. 回答最后必须列出「参考资料」章节，列出你实际引用的来源编号和文档名。\n'
            )

        if has_temp_file:
            prompt += '附件内容已提取为文字，引用时标注(临时文件)。\n'
        if has_images:
            prompt += '用户上传了图片，请仔细分析图片内容并回答。\n'

        prompt += '如果资料不足以回答，请诚实说明。\n'
        return prompt

    def _build_user_message(self, message, image_data):
        """构建用户消息（纯文本 or 多模态）"""
        if not image_data:
            return {'role': 'user', 'content': message}

        parts = []
        for img in image_data:
            try:
                b64 = base64.b64encode(img['image_bytes']).decode('utf-8')
                parts.append({
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:{img["mime_type"]};base64,{b64}',
                        'detail': 'high',
                    },
                })
            except Exception as e:
                logger.warning(f"[ChatEngine] 图片编码失败: {img.get('filename', '?')}: {e}")

        parts.append({'type': 'text', 'text': message})
        return {'role': 'user', 'content': parts}

    # ==================== 视觉模型预处理 ====================

    def _vision_preprocess_images(self, image_data, ai_config):
        """
        将图片发给视觉模型识别，返回识别的文字描述

        如果视觉服务不可用或识别失败，回退到多模态模式（保留 image_data）。
        调用方检测到返回值非空则用文本，为空则走原有多模态逻辑。
        """
        from services.vision_service import vision_service

        descriptions = []
        for img in image_data:
            try:
                # 使用视觉模型识别
                text = vision_service.recognize_bytes(
                    img['image_bytes'],
                    mime_type=img['mime_type'],
                    ai_config=ai_config,
                )
                if text and not text.startswith('[视觉'):
                    descriptions.append(
                        f'--- {img["filename"]} ---\n{text}'
                    )
                else:
                    logger.warning(f"[ChatEngine] 视觉识别无结果: {img['filename']}: {text}")
                    # 视觉失败 → 保留原始图片走多模态
                    return ''
            except Exception as e:
                logger.warning(f"[ChatEngine] 视觉识别失败: {img['filename']}: {e}")
                return ''

        return '\n\n'.join(descriptions)

    # ==================== 临时文件 ====================

    def _get_temp_file_text(self, session_id):
        try:
            from services.temp_file_service import temp_file_manager
            return temp_file_manager.get_context(session_id, wait_timeout=30) or ''
        except Exception as e:
            logger.warning(f"[ChatEngine] 获取临时文件文本失败: {e}")
            return ''

    def _get_temp_file_images(self, session_id):
        try:
            from services.temp_file_service import temp_file_manager
            return temp_file_manager.get_image_data(session_id) or []
        except Exception as e:
            logger.warning(f"[ChatEngine] 获取临时文件图片失败: {e}")
            return []


# 全局单例
chat_engine = ChatEngine()
