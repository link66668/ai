import json
from database import db
from config import Config


class UserAIConfig:
    """用户AI配置 — providers 列表以 JSON 存储"""

    @staticmethod
    def find_by_user(user_id):
        sql = "SELECT * FROM user_ai_config WHERE user_id = ?"
        return db.fetch_one(sql, (user_id,))

    @staticmethod
    def upsert(user_id, **kwargs):
        existing = UserAIConfig.find_by_user(user_id)
        if existing:
            sets = []
            values = []
            for k, v in kwargs.items():
                sets.append(f"{k} = ?")
                values.append(json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
            sets.append("updated_at = CURRENT_TIMESTAMP")
            values.append(user_id)
            sql = f"UPDATE user_ai_config SET {', '.join(sets)} WHERE user_id = ?"
            db.update(sql, values)
        else:
            cols = ['user_id'] + list(kwargs.keys())
            placeholders = ', '.join(['?'] * len(cols))
            values = [user_id]
            for v in kwargs.values():
                values.append(json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
            sql = f"INSERT INTO user_ai_config ({', '.join(cols)}) VALUES ({placeholders})"
            db.insert(sql, values)

    @staticmethod
    def delete(user_id):
        sql = "DELETE FROM user_ai_config WHERE user_id = ?"
        return db.delete(sql, (user_id,))

    @staticmethod
    def get_effective_config(user_id):
        """
        获取有效配置（用户配置优先，系统默认兜底）
        兼容旧版 flat 字段 + 新版 providers JSON
        """
        uc = UserAIConfig.find_by_user(user_id) or {}
        providers = {}

        # 新版：从 providers JSON 中解析
        if uc and uc.get('providers'):
            try:
                raw = uc['providers']
                plist = json.loads(raw) if isinstance(raw, str) else raw
                for p in plist:
                    providers[p['type']] = p
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # 旧版兼容：从 flat 字段读取（providers 为空时兜底）
        def _legacy(provider_key, api_key_field, api_url_field, model_field, enabled_field=None):
            if provider_key in providers:
                return None  # 新版优先
            if not uc:
                return None
            api_key = uc.get(api_key_field, '') or ''
            api_url = uc.get(api_url_field, '') or ''
            model = uc.get(model_field, '') or ''
            if not api_key and not api_url and not model:
                return None
            p = {'api_key': api_key, 'api_url': api_url, 'model': model}
            if enabled_field:
                p['enabled'] = bool(uc.get(enabled_field, 1))
            return p

        for legacy_type, info in [
            ('chat',      ('ai_api_key', 'ai_api_url', 'ai_model', 'use_real_llm')),
            ('embedding', ('embedding_api_key', 'embedding_api_url', 'embedding_model', None)),
            ('vision',    ('vision_api_key', 'vision_api_url', 'vision_model', 'vision_enabled')),
            ('doc',       ('doc_api_key', 'doc_api_url', 'doc_model', None)),
            ('rerank',    ('rerank_api_key', 'rerank_api_url', 'rerank_model', None)),
        ]:
            p = _legacy(legacy_type, *info)
            if p:
                providers[legacy_type] = p

        def _resolve(provider_key, field_key, default):
            if provider_key in providers:
                val = providers[provider_key].get(field_key, '')
                if isinstance(val, str) and val.strip():
                    return val.strip()
                if isinstance(val, bool):
                    return val
            return default

        return {
            'ai_api_key': _resolve('chat', 'api_key', Config.AI_API_KEY),
            'ai_api_url': _resolve('chat', 'api_url', Config.AI_API_URL),
            'ai_model': _resolve('chat', 'model', Config.AI_MODEL),
            'use_real_llm': bool(_resolve('chat', 'enabled', Config.USE_REAL_LLM)),

            'embedding_api_key': _resolve('embedding', 'api_key', Config.EMBEDDING_API_KEY),
            'embedding_api_url': _resolve('embedding', 'api_url', Config.EMBEDDING_API_URL),
            'embedding_model': _resolve('embedding', 'model', Config.EMBEDDING_MODEL),

            'vision_api_key': _resolve('vision', 'api_key', Config.VISION_API_KEY),
            'vision_api_url': _resolve('vision', 'api_url', Config.VISION_API_URL),
            'vision_model': _resolve('vision', 'model', Config.VISION_MODEL),
            'vision_enabled': bool(_resolve('vision', 'enabled', Config.VISION_ENABLED)),

            'doc_api_key': _resolve('doc', 'api_key', ''),
            'doc_api_url': _resolve('doc', 'api_url', ''),
            'doc_model': _resolve('doc', 'model', 'vlm'),

            'rerank_api_key': _resolve('rerank', 'api_key', Config.RERANK_API_KEY),
            'rerank_api_url': _resolve('rerank', 'api_url', Config.RERANK_API_URL),
            'rerank_model': _resolve('rerank', 'model', Config.RERANK_MODEL),
        }
