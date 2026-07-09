"""
SSE 流式输出服务

提供 LLM 流式响应生成：
- 调用 DeepSeek API (OpenAI 兼容) stream 模式
- SSE 格式化输出
- 速率控制
- 中断检测
- 伪流式降级
"""
import time
import json
import logging
from config import Config

logger = logging.getLogger(__name__)

# 全局中断集合：conversation_id 被中断时添加到此集合
_interrupted_conversations = set()


class StreamingService:
    """SSE 流式生成器"""

    def __init__(self):
        self._token_interval = 1.0 / max(Config.TOKEN_RATE, 1)  # 每个 token 的间隔

    def mark_interrupted(self, conversation_id):
        """标记对话为已中断"""
        _interrupted_conversations.add(conversation_id)

    def clear_interrupted(self, conversation_id):
        """清除中断标记"""
        _interrupted_conversations.discard(conversation_id)

    def is_interrupted(self, conversation_id):
        """检查是否已中断"""
        return conversation_id in _interrupted_conversations

    @staticmethod
    def _normalize_base_url(url: str) -> str:
        """去掉 URL 末尾的 /v1，OpenAI SDK 会自动追加"""
        url = url.rstrip('/')
        if url.endswith('/v1'):
            url = url[:-3]
        return url

    def stream_chat(self, messages, conversation_id=None, temperature=0.7):
        """
        SSE 流式聊天生成器

        Args:
            messages: LLM 消息列表
            conversation_id: 对话 ID（用于中断检测）
            temperature: 温度参数

        Yields:
            str: SSE 格式的事件数据
        """
        if not Config.STREAMING_ENABLED or not Config.USE_REAL_LLM:
            # 降级到伪流式
            yield from self._fallback_blocking(messages, conversation_id)
            return

        try:
            from openai import OpenAI
            from models.user_ai_config import UserAIConfig
            from services.user_context import get_current_user_id

            # 获取用户配置
            user_id = get_current_user_id()
            if user_id:
                config = UserAIConfig.get_effective_config(user_id)
            else:
                config = {
                    'ai_api_key': Config.AI_API_KEY,
                    'ai_api_url': Config.AI_API_URL,
                    'ai_model': Config.AI_MODEL,
                }

            client = OpenAI(
                base_url=self._normalize_base_url(config['ai_api_url']),
                api_key=config['ai_api_key'],
                timeout=90.0,
            )

            # 清除中断标记
            if conversation_id:
                self.clear_interrupted(conversation_id)

            stream = client.chat.completions.create(
                model=config['ai_model'],
                messages=messages,
                stream=True,
                temperature=temperature,
                max_tokens=2048,
            )

            full_response = ''
            for chunk in stream:
                # 检查中断
                if conversation_id and self.is_interrupted(conversation_id):
                    yield self._sse_event({
                        'content': '',
                        'done': True,
                        'interrupted': True,
                    })
                    return

                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    full_response += delta
                    yield self._sse_event({
                        'content': delta,
                        'done': False,
                    })
                    # 速率控制
                    time.sleep(self._token_interval)

            # 流结束
            yield self._sse_event({
                'content': '',
                'done': True,
                'full_response': full_response,
            })

        except Exception as e:
            logger.error(f"LLM 流式调用失败: {e}")
            # 降级到伪流式
            yield from self._fallback_blocking(messages, conversation_id)

    def blocking_chat(self, messages, temperature=0.7):
        """
        阻塞模式聊天（非流式）

        Args:
            messages: LLM 消息列表
            temperature: 温度参数

        Returns:
            str: 完整回复文本
        """
        try:
            from openai import OpenAI
            from models.user_ai_config import UserAIConfig
            from services.user_context import get_current_user_id

            # 获取用户配置
            user_id = get_current_user_id()
            if user_id:
                config = UserAIConfig.get_effective_config(user_id)
            else:
                config = {
                    'ai_api_key': Config.AI_API_KEY,
                    'ai_api_url': Config.AI_API_URL,
                    'ai_model': Config.AI_MODEL,
                }

            client = OpenAI(
                base_url=self._normalize_base_url(config['ai_api_url']),
                api_key=config['ai_api_key'],
                timeout=90.0,
            )

            response = client.chat.completions.create(
                model=config['ai_model'],
                messages=messages,
                stream=False,
                temperature=temperature,
                max_tokens=2048,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"LLM 阻塞调用失败: {e}")
            raise

    def pseudo_stream(self, text, conversation_id=None):
        """
        伪流式输出（分句模拟打字机效果）

        Args:
            text: 完整回复文本
            conversation_id: 对话 ID

        Yields:
            str: SSE 格式的事件数据
        """
        # 按字符分块发送，模拟流式效果
        chunk_size = 3  # 每次发送 3 个字符
        for i in range(0, len(text), chunk_size):
            # 检查中断
            if conversation_id and self.is_interrupted(conversation_id):
                yield self._sse_event({
                    'content': '',
                    'done': True,
                    'interrupted': True,
                })
                return

            chunk = text[i:i + chunk_size]
            yield self._sse_event({
                'content': chunk,
                'done': False,
            })
            time.sleep(0.05)  # 50ms 间隔

        # 完成
        yield self._sse_event({
            'content': '',
            'done': True,
            'full_response': text,
        })

    def _fallback_blocking(self, messages, conversation_id=None):
        """
        降级方案：阻塞模式 + 伪流式输出
        """
        try:
            response_text = self.blocking_chat(messages)
            yield from self.pseudo_stream(response_text, conversation_id)
        except Exception as e:
            yield self._sse_event({
                'content': f'\n\n[AI 服务暂时不可用: {str(e)}]',
                'done': True,
                'error': str(e),
            })

    def _sse_event(self, data):
        """格式化 SSE 事件"""
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# 全局单例
streaming_service = StreamingService()
