from flask import Blueprint, request
from .utils import token_required, success_response, error_response

agent_bp = Blueprint('agent', __name__, url_prefix='/api/agent')

@agent_bp.route('/chat', methods=['POST'])
@token_required
def chat(current_user):
    """Agent课程问答（RAG 增强）"""
    from services.ai_service import ai_service

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    message = data.get('message', '').strip()
    if not message:
        return error_response('消息不能为空')

    course_id = data.get('course_id')
    temp_file_session_id = data.get('temp_file_session_id')

    # 获取用户AI配置
    from models.user_ai_config import UserAIConfig
    ai_config = UserAIConfig.get_effective_config(current_user['id'])

    # 使用 RAG 增强对话
    result = ai_service.chat_rag(
        message=message,
        course_id=course_id,
        temp_file_session_id=temp_file_session_id,
        stream=False,
        ai_config=ai_config,
    )
    return success_response(result)

@agent_bp.route('/summarize', methods=['POST'])
@token_required
def summarize(current_user):
    """文本摘要"""
    from services.ai_service import ai_service

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    text = data.get('text', '').strip()
    if not text:
        return error_response('文本不能为空')

    result = ai_service.summarize_text(text)
    return success_response({'summary': result})

@agent_bp.route('/extract-knowledge', methods=['POST'])
@token_required
def extract_knowledge(current_user):
    """提取知识点"""
    from services.ai_service import ai_service

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    text = data.get('text', '').strip()
    if not text:
        return error_response('文本不能为空')

    points = ai_service.extract_knowledge_points(text)
    return success_response({'knowledge_points': points})

@agent_bp.route('/generate-plan', methods=['POST'])
@token_required
def generate_plan(current_user):
    """生成学习计划"""
    from services.ai_service import ai_service

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    course_name = data.get('course_name', '').strip()
    goal = data.get('goal', '').strip()
    exam_date = data.get('exam_date')
    daily_hours = data.get('daily_hours', 2.0)

    if not course_name:
        return error_response('课程名称不能为空')

    result = ai_service.generate_study_plan(course_name, goal, exam_date, daily_hours)
    return success_response(result)

@agent_bp.route('/decompose-task', methods=['POST'])
@token_required
def decompose_task(current_user):
    """任务分解"""
    from services.ai_service import ai_service

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    task_title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    total_days = data.get('total_days', 7)

    if not task_title:
        return error_response('任务标题不能为空')

    from models.user_ai_config import UserAIConfig
    ai_config = UserAIConfig.get_effective_config(current_user['id'])

    result = ai_service.decompose_task(task_title, description, total_days, ai_config=ai_config)
    return success_response({'subtasks': result})
