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

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    task_title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    total_days = data.get('total_days', 7)
    daily_hours = float(data.get('daily_hours', 0) or 0)

    if not task_title:
        return error_response('任务标题不能为空')

    # 课程别名预处理（解决简称匹配问题）
    import re
    _route_aliases = {
        '高数': '高等数学', '大英': '大学英语', '线代': '线性代数',
        '大物': '大学物理', '计网': '计算机网络', '马原': '马克思主义',
        'DB': '数据库', 'OS': '操作系统', 'ML': '机器学习',
        'DL': '深度学习', 'DS': '数据结构',
    }
    _route_kw = {'高等数学','线性代数','概率论','大学英语','英语',
        'Python','C语言','Java','数据结构','算法',
        '计算机网络','操作系统','数据库','机器学习','深度学习',
        '大学物理','电路分析','信号与系统',
        '微观经济学','宏观经济学','管理学',
        '马克思主义','毛概','思修','近代史'}
    _skip_words = {'我要','两周','一周','三天','七天','每天','小时','复习','学完','考试',
        '准备','预习','学习','今天','明天','开始','完成','怎么','如何',
        '好好','帮忙','帮我','需要','一个','这个','那个','什么','或者',
        '还有','以及','是否','可以','应该','能够','不能','已经','没有',
        '计划','任务','时间','分钟','之内','期末','期中','之内',
        '我想','想学','学点','东西','知道','学什','但不','不知'}
    _skip_prefixes = {'学','用','做','写','看','读','上','去','来','在','要','给','把','被','从','让'}
    remaining = task_title
    for alias, full in _route_aliases.items():
        if alias in remaining:
            remaining = remaining.replace(alias, full)
    if not any(kw in remaining for kw in _route_kw):
        cands = re.findall(r'[\u4e00-\u9fff]{2,4}', remaining)
        for c in cands:
            if c not in _skip_words and not any(c.startswith(p) for p in _skip_prefixes):
                remaining = remaining.replace(c, f'学习{c} ')
                break
    task_title = remaining.strip()

    from services.ai_service import ai_service
    from models.user_ai_config import UserAIConfig
    ai_config = UserAIConfig.get_effective_config(current_user['id'])

    result = ai_service.decompose_task(task_title, description, total_days, ai_config=ai_config, daily_hours=daily_hours)
    return success_response({'subtasks': result, 'daily_hours': daily_hours if daily_hours > 0 else None})
