from database import db


class UserAIConfig:
    """用户AI配置模型 — 每个用户独立的AI设置（对话/嵌入/识图/文档处理）"""

    # 所有可配置字段及其在 Config 中的默认值 key
    FIELDS = [
        # 对话模型
        'ai_api_key', 'ai_api_url', 'ai_model', 'use_real_llm',
        # 嵌入模型
        'embedding_api_key', 'embedding_api_url', 'embedding_model',
        # 识图模型
        'vision_api_key', 'vision_api_url', 'vision_model', 'vision_enabled',
        # 文档处理
        'doc_api_key', 'doc_api_url', 'doc_model',
    ]

    @staticmethod
    def find_by_user(user_id):
        """获取用户的AI配置"""
        sql = "SELECT * FROM user_ai_config WHERE user_id = ?"
        return db.fetch_one(sql, (user_id,))

    @staticmethod
    def upsert(user_id, **kwargs):
        """创建或更新用户AI配置"""
        # 只允许已知字段
        data = {k: kwargs.get(k, '') for k in UserAIConfig.FIELDS if k in kwargs}

        existing = UserAIConfig.find_by_user(user_id)
        if existing:
            sets = []
            values = []
            for k, v in data.items():
                sets.append(f"{k} = ?")
                values.append(v)
            sets.append("updated_at = CURRENT_TIMESTAMP")
            values.append(user_id)
            sql = f"UPDATE user_ai_config SET {', '.join(sets)} WHERE user_id = ?"
            db.update(sql, values)
        else:
            cols = ['user_id'] + list(data.keys())
            placeholders = ', '.join(['?'] * len(cols))
            values = [user_id] + list(data.values())
            sql = f"INSERT INTO user_ai_config ({', '.join(cols)}) VALUES ({placeholders})"
            db.insert(sql, values)

    @staticmethod
    def delete(user_id):
        """删除用户AI配置（恢复使用系统默认）"""
        sql = "DELETE FROM user_ai_config WHERE user_id = ?"
        return db.delete(sql, (user_id,))

    @staticmethod
    def get_effective_config(user_id):
        """
        获取用户的有效AI配置（用户配置优先，系统配置兜底）

        Returns:
            dict: 所有AI相关配置项
        """
        from config import Config

        uc = UserAIConfig.find_by_user(user_id) or {}

        def _resolve(user_val, default):
            """用户值非空则用用户值，否则用系统默认"""
            if isinstance(user_val, str):
                return user_val.strip() or default
            return user_val if user_val is not None else default

        return {
            # 对话模型
            'ai_api_key': _resolve(uc.get('ai_api_key'), Config.AI_API_KEY),
            'ai_api_url': _resolve(uc.get('ai_api_url'), Config.AI_API_URL),
            'ai_model': _resolve(uc.get('ai_model'), Config.AI_MODEL),
            'use_real_llm': bool(uc.get('use_real_llm', 1)) if uc else Config.USE_REAL_LLM,

            # 嵌入模型
            'embedding_api_key': _resolve(uc.get('embedding_api_key'), Config.EMBEDDING_API_KEY),
            'embedding_api_url': _resolve(uc.get('embedding_api_url'), Config.EMBEDDING_API_URL),
            'embedding_model': _resolve(uc.get('embedding_model'), Config.EMBEDDING_MODEL),

            # 识图模型
            'vision_api_key': _resolve(uc.get('vision_api_key'), Config.VISION_API_KEY),
            'vision_api_url': _resolve(uc.get('vision_api_url'), Config.VISION_API_URL),
            'vision_model': _resolve(uc.get('vision_model'), Config.VISION_MODEL),
            'vision_enabled': bool(uc.get('vision_enabled', 1)) if uc else Config.VISION_ENABLED,

            # 文档处理
            'doc_api_key': _resolve(uc.get('doc_api_key'), ''),
            'doc_api_url': _resolve(uc.get('doc_api_url'), ''),
            'doc_model': _resolve(uc.get('doc_model'), 'vlm'),
        }
