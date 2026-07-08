from flask import Blueprint, request
from models.chat import Conversation, Message
from models.course import Course
from .utils import token_required, success_response, error_response

chat_bp = Blueprint('chat', __name__, url_prefix='/api/conversations')

@chat_bp.route('/', methods=['GET'])
@token_required
def list_conversations(current_user):
    """获取对话列表"""
    course_id = request.args.get('course_id', type=int)

    conversations = Conversation.find_by_user(current_user['id'], course_id)

    for c in conversations:
        c['created_at'] = str(c['created_at'])
        c['updated_at'] = str(c['updated_at'])

    return success_response(conversations)

@chat_bp.route('/', methods=['POST'])
@token_required
def create_conversation(current_user):
    """创建对话"""
    data = request.get_json() or {}

    course_id = data.get('course_id')
    title = data.get('title', '新对话')

    # 如果指定了课程，检查权限
    if course_id:
        course = Course.find_by_id(course_id)
        if not course or course['user_id'] != current_user['id']:
            return error_response('无权访问该课程', 403)

    conv_id = Conversation.create(current_user['id'], course_id, title)
    return success_response({'id': conv_id}, '创建成功')

@chat_bp.route('/<int:conv_id>', methods=['GET'])
@token_required
def get_conversation(current_user, conv_id):
    """获取对话详情"""
    conv = Conversation.find_by_id(conv_id)
    if not conv:
        return error_response('对话不存在', 404)

    if conv['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    conv['created_at'] = str(conv['created_at'])
    conv['updated_at'] = str(conv['updated_at'])

    return success_response(conv)

@chat_bp.route('/<int:conv_id>', methods=['DELETE'])
@token_required
def delete_conversation(current_user, conv_id):
    """删除对话"""
    conv = Conversation.find_by_id(conv_id)
    if not conv:
        return error_response('对话不存在', 404)

    if conv['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    Conversation.delete(conv_id)
    return success_response(msg='删除成功')

@chat_bp.route('/<int:conv_id>/messages', methods=['GET'])
@token_required
def get_messages(current_user, conv_id):
    """获取对话消息"""
    conv = Conversation.find_by_id(conv_id)
    if not conv:
        return error_response('对话不存在', 404)

    if conv['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    messages = Message.find_by_conversation(conv_id)

    for m in messages:
        m['created_at'] = str(m['created_at'])
        # 解析references
        import json
        if m.get('references'):
            if isinstance(m['references'], str):
                try:
                    m['references'] = json.loads(m['references'])
                except:
                    m['references'] = []
        else:
            m['references'] = []

    return success_response(messages)

@chat_bp.route('/<int:conv_id>/messages', methods=['POST'])
@token_required
def send_message(current_user, conv_id):
    """发送消息（调用Agent）"""
    from services.ai_service import ai_service

    conv = Conversation.find_by_id(conv_id)
    if not conv:
        return error_response('对话不存在', 404)

    if conv['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    content = data.get('content', '').strip()
    if not content:
        return error_response('消息内容不能为空')

    # 保存用户消息
    Message.create(conv_id, 'user', content)

    # 获取历史消息作为上下文
    history = Message.find_by_conversation(conv_id)
    history_list = [{'role': m['role'], 'content': m['content']} for m in history[-10:]]

    # 调用AI服务
    result = ai_service.chat(
        message=content,
        course_id=conv.get('course_id'),
        conversation_history=history_list
    )

    # 保存AI回复
    msg_id = Message.create(
        conv_id,
        'assistant',
        result['response'],
        result.get('references')
    )

    # 更新对话标题（如果是第一条消息）
    if len(history) <= 1:
        title = content[:20] + ('...' if len(content) > 20 else '')
        Conversation.update_title(conv_id, title)

    return success_response({
        'id': msg_id,
        'content': result['response'],
        'references': result.get('references', [])
    })
