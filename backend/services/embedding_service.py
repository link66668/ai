"""
嵌入服务（纯 API 模式）

文本向量化完全通过 API 调用：
- 主：OpenAI 兼容 Embeddings API（MaaS 端点）
- 兜底：字符 n-gram 哈希向量（零依赖，离线可用）
"""
import logging
from config import Config

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    嵌入服务单例

    降级链：API 嵌入 → 哈希向量（纯本地兜底）
    """

    def __init__(self):
        self._client = None
        self._init_failed = False
        self._dimension = Config.EMBEDDING_DIMENSION

    def embed_texts(self, texts):
        """
        批量文本向量化

        Args:
            texts: 文本列表

        Returns:
            list[list[float]]: 向量列表
        """
        if not texts:
            return []

        # 尝试 API
        try:
            return self._embed_via_api(texts)
        except Exception as e:
            logger.warning(f"[Embedding] API 嵌入失败: {e}，降级到哈希向量")
            return self._embed_hash(texts)

    def embed_query(self, text):
        """
        查询文本向量化（单条）
        """
        result = self.embed_texts([text])
        return result[0] if result else []

    def _embed_via_api(self, texts):
        """
        通过 OpenAI 兼容 Embeddings API 向量化
        """
        from openai import OpenAI
        from models.user_ai_config import UserAIConfig
        from services.user_context import get_current_user_id

        # 获取用户配置
        user_id = get_current_user_id()
        if user_id:
            config = UserAIConfig.get_effective_config(user_id)
        else:
            config = {
                'embedding_api_key': Config.EMBEDDING_API_KEY,
                'embedding_api_url': Config.EMBEDDING_API_URL,
                'embedding_model': Config.EMBEDDING_MODEL,
            }

        # 每次调用都创建新客户端以支持用户配置
        client = OpenAI(
            base_url=config['embedding_api_url'],
            api_key=config['embedding_api_key'],
            timeout=30.0,
        )

        response = client.embeddings.create(
            model=config['embedding_model'],
            input=texts,
        )
        embeddings = [item.embedding for item in response.data]

        # 动态更新维度（首次调用时可能未知）
        if embeddings:
            actual_dim = len(embeddings[0])
            if actual_dim != self._dimension:
                self._dimension = actual_dim
                logger.info(f"[Embedding] 实际嵌入维度: {actual_dim}")

        return embeddings

    def _embed_hash(self, texts):
        """
        哈希降级向量化（零依赖，纯本地兜底）

        使用字符 n-gram 哈希生成伪向量。相同文本产生相同向量，
        保证基本的关键词匹配能力。
        """
        import hashlib
        import struct

        logger.info(f"[Embedding] 使用哈希降级向量（{self._dimension}维）")

        vectors = []
        for text in texts:
            vec = [0.0] * self._dimension
            text_lower = text.lower()
            for i in range(len(text_lower) - 1):
                bigram = text_lower[i:i + 2]
                h = hashlib.md5(bigram.encode('utf-8')).digest()
                for j in range(0, len(h), 4):
                    idx = struct.unpack('<I', h[j:j + 4])[0] % self._dimension
                    vec[idx] += 0.01

            import math
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            vectors.append(vec)

        return vectors

    def get_dimension(self):
        """返回当前嵌入维度"""
        return self._dimension

    def is_ready(self):
        """检查嵌入服务是否可用（API 模式始终认为可用）"""
        return True


# 全局单例
embedding_service = EmbeddingService()
