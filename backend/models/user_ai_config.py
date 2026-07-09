from database import db
from config import Config


class UserAIConfig:
    """用户 AI 配置模型 - 存储每个用户的 API Key 和模型配置"""

    @staticmethod
    def get_by_user(user_id):
        """获取用户的 AI 配置，如果没有则返回 None"""
        return db.fetch_one(
            "SELECT * FROM user_ai_configs WHERE user_id = ?",
            (user_id,)
        )

    @staticmethod
    def get_or_create(user_id):
        """获取用户的 AI 配置，如果没有则创建空配置"""
        config = UserAIConfig.get_by_user(user_id)
        if not config:
            UserAIConfig.create(user_id)
            config = UserAIConfig.get_by_user(user_id)
        return config

    @staticmethod
    def create(user_id, **kwargs):
        """创建用户 AI 配置"""
        sql = """
            INSERT INTO user_ai_configs
            (user_id, ai_api_key, ai_api_url, ai_model,
             vision_api_key, vision_api_url, vision_model,
             embedding_api_key, embedding_api_url, embedding_model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            user_id,
            kwargs.get('ai_api_key', ''),
            kwargs.get('ai_api_url', ''),
            kwargs.get('ai_model', ''),
            kwargs.get('vision_api_key', ''),
            kwargs.get('vision_api_url', ''),
            kwargs.get('vision_model', ''),
            kwargs.get('embedding_api_key', ''),
            kwargs.get('embedding_api_url', ''),
            kwargs.get('embedding_model', ''),
        )
        return db.insert(sql, params)

    @staticmethod
    def update(user_id, **kwargs):
        """更新用户 AI 配置"""
        allowed_fields = {
            'ai_api_key', 'ai_api_url', 'ai_model',
            'vision_api_key', 'vision_api_url', 'vision_model',
            'embedding_api_key', 'embedding_api_url', 'embedding_model'
        }

        updates = []
        values = []
        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                values.append(value)

        if not updates:
            return False

        # 如果配置不存在则创建
        existing = UserAIConfig.get_by_user(user_id)
        if not existing:
            return UserAIConfig.create(user_id, **kwargs)

        values.append(user_id)
        sql = f"""
            UPDATE user_ai_configs
            SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """
        return db.update(sql, values)

    @staticmethod
    def delete(user_id):
        """删除用户 AI 配置"""
        return db.delete("DELETE FROM user_ai_configs WHERE user_id = ?", (user_id,))

    @staticmethod
    def get_effective_config(user_id):
        """
        获取有效的 AI 配置：用户配置优先，缺失字段回退到全局配置

        Returns:
            dict: 包含所有 9 个配置项的字典
        """
        user_config = UserAIConfig.get_by_user(user_id)

        # 如果用户没有配置，全部使用全局配置
        if not user_config:
            return {
                'ai_api_key': Config.AI_API_KEY,
                'ai_api_url': Config.AI_API_URL,
                'ai_model': Config.AI_MODEL,
                'vision_api_key': Config.VISION_API_KEY,
                'vision_api_url': Config.VISION_API_URL,
                'vision_model': Config.VISION_MODEL,
                'embedding_api_key': Config.EMBEDDING_API_KEY,
                'embedding_api_url': Config.EMBEDDING_API_URL,
                'embedding_model': Config.EMBEDDING_MODEL,
            }

        # 用户配置优先，空字符串回退到全局配置
        return {
            'ai_api_key': user_config.get('ai_api_key') or Config.AI_API_KEY,
            'ai_api_url': user_config.get('ai_api_url') or Config.AI_API_URL,
            'ai_model': user_config.get('ai_model') or Config.AI_MODEL,
            'vision_api_key': user_config.get('vision_api_key') or Config.VISION_API_KEY,
            'vision_api_url': user_config.get('vision_api_url') or Config.VISION_API_URL,
            'vision_model': user_config.get('vision_model') or Config.VISION_MODEL,
            'embedding_api_key': user_config.get('embedding_api_key') or Config.EMBEDDING_API_KEY,
            'embedding_api_url': user_config.get('embedding_api_url') or Config.EMBEDDING_API_URL,
            'embedding_model': user_config.get('embedding_model') or Config.EMBEDDING_MODEL,
        }
