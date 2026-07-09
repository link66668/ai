from flask import Blueprint, request
from models.user_ai_config import UserAIConfig
from config import Config
from .utils import token_required, success_response, error_response

user_ai_config_bp = Blueprint('user_ai_config', __name__, url_prefix='/api/ai-config')


@user_ai_config_bp.route('/', methods=['GET'])
@token_required
def get_config(current_user):
    """获取当前用户的AI配置（API Key 脱敏返回）"""
    config = UserAIConfig.find_by_user(current_user['id'])

    if not config:
        return success_response({
            # 对话模型
            'ai_api_key': _mask_key(Config.AI_API_KEY),
            'ai_api_url': Config.AI_API_URL,
            'ai_model': Config.AI_MODEL,
            'use_real_llm': Config.USE_REAL_LLM,
            # 嵌入模型
            'embedding_api_key': _mask_key(Config.EMBEDDING_API_KEY),
            'embedding_api_url': Config.EMBEDDING_API_URL,
            'embedding_model': Config.EMBEDDING_MODEL,
            # 识图模型
            'vision_api_key': _mask_key(Config.VISION_API_KEY),
            'vision_api_url': Config.VISION_API_URL,
            'vision_model': Config.VISION_MODEL,
            'vision_enabled': Config.VISION_ENABLED,
            # 文档处理
            'doc_api_key': '',
            'doc_api_url': '',
            'doc_model': 'vlm',
            # 标记
            'is_custom': False,
        })

    return success_response({
        # 对话模型
        'ai_api_key': _mask_key(config.get('ai_api_key', '')),
        'ai_api_url': config.get('ai_api_url', ''),
        'ai_model': config.get('ai_model', ''),
        'use_real_llm': bool(config.get('use_real_llm', 1)),
        # 嵌入模型
        'embedding_api_key': _mask_key(config.get('embedding_api_key', '')),
        'embedding_api_url': config.get('embedding_api_url', ''),
        'embedding_model': config.get('embedding_model', ''),
        # 识图模型
        'vision_api_key': _mask_key(config.get('vision_api_key', '')),
        'vision_api_url': config.get('vision_api_url', ''),
        'vision_model': config.get('vision_model', ''),
        'vision_enabled': bool(config.get('vision_enabled', 1)),
        # 文档处理
        'doc_api_key': _mask_key(config.get('doc_api_key', '')),
        'doc_api_url': config.get('doc_api_url', ''),
        'doc_model': config.get('doc_model', 'vlm'),
        # 标记
        'is_custom': True,
    })


@user_ai_config_bp.route('/', methods=['PUT'])
@token_required
def update_config(current_user):
    """更新当前用户的AI配置"""
    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    # 提取所有可配置字段
    fields = {}

    # 对话模型
    fields['ai_api_key'] = data.get('ai_api_key', '').strip()
    fields['ai_api_url'] = data.get('ai_api_url', '').strip()
    fields['ai_model'] = data.get('ai_model', '').strip()
    fields['use_real_llm'] = 1 if data.get('use_real_llm', True) else 0

    # 嵌入模型
    fields['embedding_api_key'] = data.get('embedding_api_key', '').strip()
    fields['embedding_api_url'] = data.get('embedding_api_url', '').strip()
    fields['embedding_model'] = data.get('embedding_model', '').strip()

    # 识图模型
    fields['vision_api_key'] = data.get('vision_api_key', '').strip()
    fields['vision_api_url'] = data.get('vision_api_url', '').strip()
    fields['vision_model'] = data.get('vision_model', '').strip()
    fields['vision_enabled'] = 1 if data.get('vision_enabled', True) else 0

    # 文档处理
    fields['doc_api_key'] = data.get('doc_api_key', '').strip()
    fields['doc_api_url'] = data.get('doc_api_url', '').strip()
    fields['doc_model'] = data.get('doc_model', 'vlm').strip()

    # 如果 key 字段包含脱敏标记 ***，说明用户没改，保留原值
    existing = UserAIConfig.find_by_user(current_user['id'])
    for key_field in ['ai_api_key', 'embedding_api_key', 'vision_api_key', 'doc_api_key']:
        if '***' in fields.get(key_field, ''):
            fields[key_field] = existing.get(key_field, '') if existing else ''

    UserAIConfig.upsert(user_id=current_user['id'], **fields)
    return success_response(msg='AI配置已保存')


@user_ai_config_bp.route('/', methods=['DELETE'])
@token_required
def reset_config(current_user):
    """重置为系统默认配置"""
    UserAIConfig.delete(current_user['id'])
    return success_response(msg='已恢复系统默认配置')


@user_ai_config_bp.route('/test', methods=['POST'])
@token_required
def test_config(current_user):
    """测试指定模型的连接"""
    data = request.get_json() or {}
    model_type = data.get('type', 'chat')  # chat / embedding / vision / doc

    effective = UserAIConfig.get_effective_config(current_user['id'])

    if model_type == 'chat':
        return _test_openai_chat(
            effective['ai_api_url'],
            effective['ai_api_key'],
            effective['ai_model'],
        )
    elif model_type == 'embedding':
        return _test_openai_embedding(
            effective['embedding_api_url'],
            effective['embedding_api_key'],
            effective['embedding_model'],
        )
    elif model_type == 'vision':
        return _test_openai_chat(
            effective['vision_api_url'],
            effective['vision_api_key'],
            effective['vision_model'],
        )
    elif model_type == 'doc':
        return _test_doc_api(
            effective['doc_api_url'],
            effective['doc_api_key'],
        )
    else:
        return error_response(f'未知的模型类型: {model_type}')


def _test_openai_chat(api_url, api_key, model):
    """测试 OpenAI 兼容的对话 API"""
    if not api_key:
        return error_response('API Key 未配置')
    try:
        import requests as req
        resp = req.post(
            f"{api_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5},
            timeout=15,
        )
        if resp.status_code == 200:
            return success_response({'status': 'ok', 'message': f'连接成功，模型 {model} 可用'})
        else:
            return error_response(f'API 返回错误 {resp.status_code}: {resp.text[:200]}')
    except Exception as e:
        return error_response(f'连接失败: {str(e)}')


def _test_openai_embedding(api_url, api_key, model):
    """测试 OpenAI 兼容的嵌入 API"""
    if not api_key:
        return error_response('API Key 未配置')
    try:
        import requests as req
        resp = req.post(
            f"{api_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": "测试文本"},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            dim = len(data.get('data', [{}])[0].get('embedding', []))
            return success_response({'status': 'ok', 'message': f'连接成功，维度: {dim}'})
        else:
            return error_response(f'API 返回错误 {resp.status_code}: {resp.text[:200]}')
    except Exception as e:
        return error_response(f'连接失败: {str(e)}')


def _test_doc_api(api_url, api_key):
    """测试文档处理 API（MinerU 等）"""
    if not api_url:
        return error_response('文档处理 API 地址未配置')
    try:
        import requests as req

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        # 依次尝试常见端点
        for path in ['/api/v4/extract/task', '/health', '/api/health', '/']:
            try:
                url = f"{api_url.rstrip('/')}{path}"
                resp = req.get(url, headers=headers, timeout=10, allow_redirects=True)
                if resp.status_code < 500:
                    return success_response({
                        'status': 'ok',
                        'message': f'文档处理服务连接成功 ({path} → HTTP {resp.status_code})'
                    })
            except req.exceptions.ConnectionError:
                continue

        return error_response('无法连接到文档处理服务，请检查地址是否正确')
    except Exception as e:
        return error_response(f'连接失败: {str(e)}')


def _mask_key(key):
    """脱敏 API Key：只显示前4位和后4位"""
    if not key or len(key) <= 8:
        return key[:2] + '***' if key else ''
    return key[:4] + '***' + key[-4:]
