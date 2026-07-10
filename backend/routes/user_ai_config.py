"""AI 配置管理 — 多 Provider 模式"""
from flask import Blueprint, request
from models.user_ai_config import UserAIConfig
from config import Config
from .utils import token_required, success_response, error_response

user_ai_config_bp = Blueprint('user_ai_config', __name__, url_prefix='/api/ai-config')

PROVIDER_TYPES = {
    'chat':     {'label': '对话模型',     'fields': ['api_key', 'api_url', 'model'], 'test': 'openai-chat'},
    'embedding':{'label': '嵌入模型',     'fields': ['api_key', 'api_url', 'model'], 'test': 'openai-embedding'},
    'vision':   {'label': '识图模型',     'fields': ['api_key', 'api_url', 'model', 'enabled'], 'test': 'openai-chat'},
    'doc':      {'label': '文档处理',     'fields': ['api_key', 'api_url', 'model'], 'test': 'doc-api'},
}


@user_ai_config_bp.route('/', methods=['GET'])
@token_required
def get_config(current_user):
    """获取用户配置 — 返回 providers 列表 + 系统默认"""
    config = UserAIConfig.find_by_user(current_user['id'])
    providers = _parse_providers(config.get('providers') if config else None)
    return success_response({
        'providers': providers,
        'is_custom': bool(config),
    })


@user_ai_config_bp.route('/', methods=['PUT'])
@token_required
def save_providers(current_user):
    """保存完整 providers 列表"""
    data = request.get_json()
    if not data or 'providers' not in data:
        return error_response('请求数据为空')

    providers = data['providers']
    if not isinstance(providers, list):
        return error_response('providers 必须是数组')

    # 保留未修改的 API Key（前端传 masked 值时保留原值）
    existing = UserAIConfig.find_by_user(current_user['id'])
    existing_providers = _parse_providers(existing.get('providers') if existing else None)

    for p in providers:
        for ep in existing_providers:
            if p['id'] == ep['id'] and '***' in p.get('api_key', ''):
                p['api_key'] = ep.get('api_key', '')

    UserAIConfig.upsert(user_id=current_user['id'], providers=json.dumps(providers, ensure_ascii=False))
    return success_response(msg='配置已保存')


@user_ai_config_bp.route('/', methods=['DELETE'])
@token_required
def reset_config(current_user):
    """重置为系统默认"""
    UserAIConfig.delete(current_user['id'])
    return success_response(msg='已恢复系统默认配置')


@user_ai_config_bp.route('/test', methods=['POST'])
@token_required
def test_provider(current_user):
    """测试指定 provider 的连接"""
    data = request.get_json() or {}
    provider_type = data.get('type', 'chat')

    if provider_type not in PROVIDER_TYPES:
        return error_response(f'未知的模型类型: {provider_type}')

    # 优先用请求中传的值测试，否则从有效配置中取
    api_url = data.get('api_url', '').strip() or Config.AI_API_URL
    api_key = data.get('api_key', '').strip() or Config.AI_API_KEY
    model = data.get('model', '').strip() or Config.AI_MODEL

    if not api_key:
        return error_response('API Key 未配置')

    test_type = PROVIDER_TYPES[provider_type]['test']
    if test_type == 'openai-chat':
        return _test_chat(api_url, api_key, model)
    elif test_type == 'openai-embedding':
        return _test_embedding(api_url, api_key, model)
    elif test_type == 'doc-api':
        return _test_doc(api_url, api_key)
    return error_response('不支持的测试类型')


# ========== 内部 ==========

def _parse_providers(providers_json):
    """解析 providers JSON，空则返回系统默认列表"""
    if providers_json:
        try:
            return json.loads(providers_json) if isinstance(providers_json, str) else providers_json
        except (json.JSONDecodeError, TypeError):
            pass
    return _default_providers()


def _default_providers():
    """系统默认 provider 列表"""
    return [
        {'id': 'chat',    'type': 'chat',      'name': 'Chat',    'api_key': '', 'api_url': Config.AI_API_URL,           'model': Config.AI_MODEL,           'enabled': True},
        {'id': 'embedding','type': 'embedding', 'name': 'Embed','api_key': '', 'api_url': Config.EMBEDDING_API_URL,      'model': Config.EMBEDDING_MODEL,    'enabled': True},
        {'id': 'vision',  'type': 'vision',    'name': 'Vision','api_key': '',  'api_url': Config.VISION_API_URL,        'model': Config.VISION_MODEL,       'enabled': Config.VISION_ENABLED},
        {'id': 'doc',     'type': 'doc',       'name': 'Doc',   'api_key': '',  'api_url': '',                            'model': 'vlm',                     'enabled': True},
    ]


def _mask_key(key):
    if not key or len(key) <= 8:
        return key[:2] + '***' if key else ''
    return key[:4] + '***' + key[-4:]


def _test_chat(api_url, api_key, model):
    import requests as req
    try:
        resp = req.post(f"{api_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5},
            timeout=15)
        if resp.status_code == 200:
            return success_response({'message': f'连接成功，模型 {model} 可用'})
        return error_response(f'API 返回错误 {resp.status_code}: {resp.text[:200]}')
    except Exception as e:
        return error_response(f'连接失败: {str(e)}')


def _test_embedding(api_url, api_key, model):
    import requests as req
    try:
        resp = req.post(f"{api_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": "test"}, timeout=15)
        if resp.status_code == 200:
            dim = len(resp.json().get('data', [{}])[0].get('embedding', []))
            return success_response({'message': f'连接成功，维度: {dim}'})
        return error_response(f'API 返回错误 {resp.status_code}: {resp.text[:200]}')
    except Exception as e:
        return error_response(f'连接失败: {str(e)}')


def _test_doc(api_url, api_key):
    if not api_url:
        return error_response('服务地址未配置')
    import requests as req
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    for path in ['/api/v4/extract/task', '/health', '/api/health', '/']:
        try:
            resp = req.get(f"{api_url.rstrip('/')}{path}", headers=headers, timeout=10)
            if resp.status_code < 500:
                return success_response({'message': f'连接成功 ({path} → HTTP {resp.status_code})'})
        except:
            continue
    return error_response('无法连接到文档处理服务')

import json  # noqa: E402 — kept at bottom for clean top-level imports
