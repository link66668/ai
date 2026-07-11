"""
SSE 流式输出服务 — 支持 tool calling（仿 cherry-studio）

核心方法:
  stream_with_tools() — 带 tool calling 的流式聊天
    检测 LLM 的 tool_call → 执行工具 → 继续流式回复

SSE 事件格式:
  {"type": "text", "content": "hello", "done": false}
  {"type": "tool_call_start", "tool_call_id": "call_xxx", "function": "kb_search", "arguments": {...}}
  {"type": "tool_call_end", "tool_call_id": "call_xxx", "result_count": 5}
  {"type": "text", "content": "", "done": true, "full_response": "..."}
"""
import json
import logging
from config import Config

logger = logging.getLogger(__name__)

_interrupted_conversations = set()


class StreamingService:
    """SSE 流式生成器 — 支持工具调用"""

    def __init__(self):
        self._clients = {}  # (api_url, api_key) → OpenAI client

    def _get_client(self, ai_config=None):
        cfg = ai_config or {}
        api_url = cfg.get('ai_api_url') or Config.AI_API_URL
        api_key = cfg.get('ai_api_key') or Config.AI_API_KEY
        cache_key = (api_url, api_key)
        if cache_key not in self._clients:
            from openai import OpenAI
            self._clients[cache_key] = OpenAI(
                base_url=api_url,
                api_key=api_key,
                timeout=90.0,
            )
        return self._clients[cache_key]

    # ==================== 中断 ====================

    def mark_interrupted(self, conversation_id):
        _interrupted_conversations.add(conversation_id)

    def clear_interrupted(self, conversation_id):
        _interrupted_conversations.discard(conversation_id)

    def is_interrupted(self, conversation_id):
        return conversation_id in _interrupted_conversations

    # ==================== 带 tool calling 的流式 ====================

    def stream_with_tools(self, messages, tools, tool_executor,
                          conversation_id=None, temperature=0.7, ai_config=None):
        """
        带 tool calling 的流式聊天

        流程（仿 cherry-studio Agent loop）:
          1. 调 LLM（带 tools 定义）
          2. 如果 LLM 返回 tool_call → 执行工具 → 继续调 LLM
          3. 流式输出最终文本

        Args:
            messages: LLM 消息列表
            tools: 工具定义列表（OpenAI function calling 格式）
            tool_executor: 可调用对象，接收 (tool_name, arguments) 返回结果 dict
            conversation_id: 对话 ID
            temperature: 温度
            ai_config: AI 配置

        Yields: SSE 字符串
        """
        cfg = ai_config or {}
        use_real_llm = cfg.get('use_real_llm', Config.USE_REAL_LLM)

        if not Config.STREAMING_ENABLED or not use_real_llm:
            yield from self._fallback_blocking(messages, conversation_id, ai_config)
            return

        # 最多允许 N 轮工具调用（防止死循环）
        max_rounds = 3
        current_messages = list(messages)
        current_tools = list(tools)

        for _round in range(max_rounds):
            try:
                client = self._get_client(ai_config)
                if conversation_id:
                    self.clear_interrupted(conversation_id)

                stream = client.chat.completions.create(
                    model=cfg.get('ai_model') or Config.AI_MODEL,
                    messages=current_messages,
                    tools=current_tools if current_tools else None,
                    stream=True,
                    temperature=temperature,
                    max_tokens=2048,
                )

                # 收集本次流的所有 chunk
                tool_calls = {}    # index → {id, function: {name, arguments}}
                full_response = ''

                for chunk in stream:
                    if conversation_id and self.is_interrupted(conversation_id):
                        yield self._event({'type': 'text', 'content': '', 'done': True, 'interrupted': True})
                        return

                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue

                    # 检测 tool_call
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls:
                                tool_calls[idx] = {
                                    'id': tc.id or '',
                                    'function': {'name': '', 'arguments': ''},
                                }
                            if tc.id:
                                tool_calls[idx]['id'] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls[idx]['function']['name'] = tc.function.name
                                if tc.function.arguments:
                                    tool_calls[idx]['function']['arguments'] += tc.function.arguments

                    # 检测文本
                    if delta.content:
                        full_response += delta.content
                        yield self._event({'type': 'text', 'content': delta.content, 'done': False})

                # ---- 处理 tool_call ----
                if not tool_calls:
                    # 本次没有 tool_call → 完成
                    yield self._event({
                        'type': 'text', 'content': '', 'done': True,
                        'full_response': full_response,
                    })
                    return

                # 执行工具
                assistant_msg = {'role': 'assistant', 'content': full_response or None}
                tool_messages = []

                for idx in sorted(tool_calls.keys()):
                    tc = tool_calls[idx]
                    tc_id = tc['id']
                    func_name = tc['function']['name']
                    try:
                        func_args = json.loads(tc['function']['arguments'])
                    except json.JSONDecodeError:
                        func_args = {}

                    # 发出 tool_call_start 事件
                    yield self._event({
                        'type': 'tool_call_start',
                        'tool_call_id': tc_id,
                        'function': func_name,
                        'arguments': func_args,
                    })

                    # 执行工具
                    try:
                        result = tool_executor(func_name, func_args)
                    except Exception as e:
                        result = {'error': str(e)}

                    # 发出 tool_call_end 事件
                    result_count = 0
                    if isinstance(result, dict):
                        result_count = len(result.get('results', result.get('citations', [])))
                    elif isinstance(result, list):
                        result_count = len(result)

                    yield self._event({
                        'type': 'tool_call_end',
                        'tool_call_id': tc_id,
                        'function': func_name,
                        'result_count': result_count,
                    })

                    # 收集 tool 消息（不回传给前端，仅用于下一轮 LLM 调用）
                    assistant_msg['tool_calls'] = [
                        {'id': tc_id, 'type': 'function', 'function': tc['function']}
                    ]
                    tool_messages.append({
                        'role': 'tool',
                        'tool_call_id': tc_id,
                        'content': json.dumps(result, ensure_ascii=False),
                    })

                # 将 assistant 消息 + tool 结果追加到对话，准备下一轮
                current_messages.append(assistant_msg)
                current_messages.extend(tool_messages)
                # 第二轮不再给 tools（模型已经搜到结果，直接回答）
                current_tools = []

                # 继续下一轮循环
                continue

            except Exception as e:
                logger.error(f"LLM 流式调用失败 (round {_round + 1}): {e}")
                yield from self._fallback_blocking(current_messages, conversation_id, ai_config)
                return

        # 超过最大轮数，直接给 fallback
        logger.warning(f"工具调用超过最大轮数 ({max_rounds})，走降级")
        yield from self._fallback_blocking(current_messages, conversation_id, ai_config)

    # ==================== 阻塞 + 伪流式（降级） ====================

    def blocking_chat(self, messages, temperature=0.7, ai_config=None):
        cfg = ai_config or {}
        try:
            client = self._get_client(ai_config)
            response = client.chat.completions.create(
                model=cfg.get('ai_model') or Config.AI_MODEL,
                messages=messages,
                stream=False,
                temperature=temperature,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM 阻塞调用失败: {e}")
            raise

    def pseudo_stream(self, text, conversation_id=None):
        chunk_size = 3
        for i in range(0, len(text), chunk_size):
            if conversation_id and self.is_interrupted(conversation_id):
                yield self._event({'type': 'text', 'content': '', 'done': True, 'interrupted': True})
                return
            chunk = text[i:i + chunk_size]
            yield self._event({'type': 'text', 'content': chunk, 'done': False})
            import time
            time.sleep(0.05)
        yield self._event({'type': 'text', 'content': '', 'done': True, 'full_response': text})

    def _fallback_blocking(self, messages, conversation_id=None, ai_config=None):
        try:
            response_text = self.blocking_chat(messages, ai_config=ai_config)
            yield from self.pseudo_stream(response_text, conversation_id)
        except Exception as e:
            yield self._event({
                'type': 'text', 'content': f'\n\n[AI 服务暂时不可用: {str(e)}]',
                'done': True, 'error': str(e),
            })

    @staticmethod
    def _event(data):
        """格式化 SSE 事件"""
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# 全局单例
streaming_service = StreamingService()
