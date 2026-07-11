"""
共享 Token 计数器

集中管理 tiktoken tokenizer 实例，避免各服务重复初始化。
提供统一的 token 估算接口，确保计数一致性。
"""
import logging

logger = logging.getLogger(__name__)


class TokenCounter:
    """
    Token 计数器单例

    延迟加载 tiktoken，失败时自动降级到字符估算。
    """

    def __init__(self):
        self._tokenizer = None

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            try:
                import tiktoken
                try:
                    self._tokenizer = tiktoken.get_encoding('cl100k_base')
                except Exception:
                    self._tokenizer = tiktoken.get_encoding('o200k_base')
            except ImportError:
                logger.warning("[TokenCounter] tiktoken 不可用，降级到字符估算")
                self._tokenizer = False
        return self._tokenizer if self._tokenizer is not False else None

    def count(self, text):
        """
        计算文本的 token 数量

        Args:
            text: 要计数的文本

        Returns:
            int: token 数量
        """
        if not text:
            return 0

        tok = self.tokenizer
        if tok is not None:
            try:
                return len(tok.encode(text))
            except Exception:
                pass

        # 降级：按字符估算（中文约 1.5 字/token，英文约 4 字/token）
        return len(text) // 2

    def truncate(self, text, max_tokens):
        """
        按 token 数截断文本

        Args:
            text: 输入文本
            max_tokens: 最大 token 数

        Returns:
            str: 截断后的文本
        """
        if max_tokens <= 0:
            return ''
        if self.count(text) <= max_tokens:
            return text

        tok = self.tokenizer
        if tok is not None:
            try:
                encoded = tok.encode(text)
                return tok.decode(encoded[:max_tokens])
            except Exception:
                pass

        # 降级：按比例粗略截断
        ratio = max_tokens * 2 / max(len(text), 1)
        cutoff = int(len(text) * min(ratio, 1.0))
        return text[:cutoff] + '...'


# 全局单例
token_counter = TokenCounter()
