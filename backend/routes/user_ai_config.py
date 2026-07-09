from flask import Blueprint, request, jsonify
from routes.utils import token_required, success_response, error_response
from models.user_ai_config import UserAIConfig

user_ai_config_bp = Blueprint('user_ai_config', __name__, url_prefix='/api/user/ai-config')


@user_ai_config_bp.route('/', methods=['GET'])
@token_required
def get_ai_config(current_user):
    """获取当前用户的 AI 配置"""
    config = UserAIConfig.get_by_user(current_user['id'])

    if not config:
        # 返回空配置，前端显示全局默认值的占位符
        return success_response({
            'ai_api_key': '',
            'ai_api_url': '',
            'ai_model': '',
            'vision_api_key': '',
            'vision_api_url': '',
            'vision_model': '',
            'embedding_api_key': '',
            'embedding_api_url': '',
            'embedding_model': '',
            'has_custom_config': False
        })

    # 返回用户配置（隐藏 API Key 的中间部分）
    return success_response({
        'ai_api_key': _mask_api_key(config.get('ai_api_key', '')),
        'ai_api_url': config.get('ai_api_url', ''),
        'ai_model': config.get('ai_model', ''),
        'vision_api_key': _mask_api_key(config.get('vision_api_key', '')),
        'vision_api_url': config.get('vision_api_url', ''),
        'vision_model': config.get('vision_model', ''),
        'embedding_api_key': _mask_api_key(config.get('embedding_api_key', '')),
        'embedding_api_url': config.get('embedding_api_url', ''),
        'embedding_model': config.get('embedding_model', ''),
        'has_custom_config': True
    })


@user_ai_config_bp.route('/', methods=['PUT'])
@token_required
def update_ai_config(current_user):
    """更新当前用户的 AI 配置"""
    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    update_data = {}
    allowed_fields = [
        'ai_api_key', 'ai_api_url', 'ai_model',
        'vision_api_key', 'vision_api_url', 'vision_model',
        'embedding_api_key', 'embedding_api_url', 'embedding_model'
    ]

    for field in allowed_fields:
        if field in data:
            value = data[field].strip() if isinstance(data[field], str) else data[field]
            # 如果前端发送的是掩码后的 key（包含 ***），则不更新该字段
            if '***' in str(value):
                continue
            update_data[field] = value

    if not update_data:
        return error_response('没有可更新的字段')

    UserAIConfig.update(current_user['id'], **update_data)
    return success_response(msg='AI 配置更新成功')


@user_ai_config_bp.route('/test', methods=['POST'])
@token_required
def test_ai_config(current_user):
    """测试 AI 配置是否有效"""
    import requests
    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    test_type = data.get('type', 'chat')  # chat / vision / embedding

    # 获取有效配置（用户配置优先）
    config = UserAIConfig.get_effective_config(current_user['id'])

    def _build_url(base_url: str, path: str) -> str:
        """拼接 URL，避免 /v1 重复"""
        url = base_url.rstrip('/')
        # 如果 base_url 已以 /v1 结尾，去掉后再拼 path
        if url.endswith('/v1'):
            url = url[:-3]
        return f"{url}{path}"

    try:
        if test_type == 'chat':
            # 测试对话模型
            resp = requests.post(
                _build_url(config['ai_api_url'], '/v1/chat/completions'),
                headers={
                    "Authorization": f"Bearer {config['ai_api_key']}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": config['ai_model'],
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 5
                },
                timeout=10
            )
            if resp.status_code == 200:
                return success_response(msg='对话模型连接成功')
            else:
                return error_response(f'对话模型连接失败: {resp.status_code}')

        elif test_type == 'vision':
            # 测试视觉模型
            resp = requests.post(
                _build_url(config['vision_api_url'], '/v1/chat/completions'),
                headers={
                    "Authorization": f"Bearer {config['vision_api_key']}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": config['vision_model'],
                    "messages": [{"role": "user", "content": "Test"}],
                    "max_tokens": 5
                },
                timeout=10
            )
            if resp.status_code == 200:
                return success_response(msg='视觉模型连接成功')
            else:
                return error_response(f'视觉模型连接失败: {resp.status_code}')

        elif test_type == 'embedding':
            # 测试嵌入模型
            resp = requests.post(
                _build_url(config['embedding_api_url'], '/v1/embeddings'),
                headers={
                    "Authorization": f"Bearer {config['embedding_api_key']}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": config['embedding_model'],
                    "input": "test"
                },
                timeout=10
            )
            if resp.status_code == 200:
                return success_response(msg='嵌入模型连接成功')
            else:
                return error_response(f'嵌入模型连接失败: {resp.status_code}')

        else:
            return error_response('无效的测试类型')

    except requests.exceptions.Timeout:
        return error_response('连接超时')
    except Exception as e:
        return error_response(f'测试失败: {str(e)}')


@user_ai_config_bp.route('/', methods=['DELETE'])
@token_required
def delete_ai_config(current_user):
    """删除当前用户的 AI 配置（回退到全局配置）"""
    UserAIConfig.delete(current_user['id'])
    return success_response(msg='已恢复为全局默认配置')


def _mask_api_key(api_key):
    """掩码 API Key，只显示前4位和后4位"""
    if not api_key or len(api_key) < 12:
        return api_key
    return f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"
