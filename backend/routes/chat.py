import json
from flask import Blueprint, request, Response, stream_with_context
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


# ========== 流式 + 临时文件 + 中断端点 ==========

@chat_bp.route('/<int:conv_id>/messages/stream', methods=['POST'])
@token_required
def send_message_stream(current_user, conv_id):
    """发送消息并流式返回（SSE）"""
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

    temp_file_session_id = data.get('temp_file_session_id')

    # 保存用户消息
    Message.create(conv_id, 'user', content)

    # 获取历史消息
    history = Message.find_by_conversation(conv_id)
    history_list = [{'role': m['role'], 'content': m['content']} for m in history[-10:]]

    # 调用 RAG 流式管线
    stream_gen = ai_service.chat_rag(
        message=content,
        course_id=conv.get('course_id'),
        conversation_history=history_list,
        temp_file_session_id=temp_file_session_id,
        stream=True,
    )

    def generate():
        full_response = ''
        citations = []

        # 使用 Queue + 后台线程实现心跳，防止切标签页/代理超时断开 SSE 连接
        from queue import Queue, Empty
        import threading

        event_queue = Queue()

        def producer():
            try:
                for event in stream_gen:
                    event_queue.put(event)
            except Exception:
                pass
            event_queue.put(None)  # 哨兵：流结束

        producer_thread = threading.Thread(target=producer, daemon=True)
        producer_thread.start()

        while True:
            try:
                event = event_queue.get(timeout=15)  # 每 15 秒发一次心跳
            except Empty:
                yield ': heartbeat\n\n'  # SSE 注释，保持连接活跃
                continue

            if event is None:
                break  # 流结束

            # 解析 SSE 事件提取内容
            if event.startswith('data: '):
                try:
                    event_data = json.loads(event[6:])
                    if event_data.get('done'):
                        # 流结束，保存 AI 回复
                        citations = event_data.get('citations', [])
                        interrupted = event_data.get('interrupted', False)
                        if full_response.strip():
                            # 被中断时也保存部分内容
                            Message.create(
                                conv_id,
                                'assistant',
                                full_response,
                                citations
                            )
                        # 更新对话标题
                        if not interrupted and len(history) <= 1:
                            title = content[:20] + ('...' if len(content) > 20 else '')
                            Conversation.update_title(conv_id, title)
                    else:
                        full_response += event_data.get('content', '')
                except json.JSONDecodeError:
                    pass
            yield event

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@chat_bp.route('/<int:conv_id>/upload-temp', methods=['POST'])
@token_required
def upload_temp_file(current_user, conv_id):
    """上传临时文件到对话会话"""
    conv = Conversation.find_by_id(conv_id)
    if not conv:
        return error_response('对话不存在', 404)

    if conv['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    if 'file' not in request.files:
        return error_response('没有文件', 400)

    file = request.files['file']
    if file.filename == '':
        return error_response('没有选择文件', 400)

    # 获取文件信息
    original_name = file.filename or 'unnamed'
    ext = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else ''
    allowed = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'}

    if ext not in allowed:
        return error_response(f'不支持的文件类型: {ext}', 400)

    try:
        from services.temp_file_service import temp_file_manager

        # 获取或创建会话
        session_id = temp_file_manager.get_or_create_session(conv_id)

        # 添加文件
        result = temp_file_manager.add_file(session_id, file, original_name, ext)

        return success_response({
            'session_id': session_id,
            'file': result,
        }, '临时文件已添加')
    except Exception as e:
        return error_response(f'临时文件处理失败: {str(e)}', 500)


@chat_bp.route('/<int:conv_id>/temp-file-status/<file_id>', methods=['GET'])
@token_required
def get_temp_file_status(current_user, conv_id, file_id):
    """查询临时文件处理状态（用于异步处理轮询）"""
    conv = Conversation.find_by_id(conv_id)
    if not conv:
        return error_response('对话不存在', 404)

    if conv['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    from services.temp_file_service import temp_file_manager

    session_id = temp_file_manager.get_or_create_session(conv_id)
    if not session_id:
        return error_response('会话不存在', 404)

    result = temp_file_manager.get_file_status(session_id, file_id)
    return success_response(result)


@chat_bp.route('/<int:conv_id>/interrupt', methods=['POST'])
@token_required
def interrupt_stream(current_user, conv_id):
    """中断当前流式生成"""
    conv = Conversation.find_by_id(conv_id)
    if not conv:
        return error_response('对话不存在', 404)

    if conv['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    from services.streaming_service import streaming_service
    streaming_service.mark_interrupted(conv_id)

    return success_response(msg='已发送中断请求')
