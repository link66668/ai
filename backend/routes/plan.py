from flask import Blueprint, request
from models.task import StudyPlan
from models.course import Course
from .utils import token_required, success_response, error_response

plan_bp = Blueprint('plan', __name__, url_prefix='/api/plans')

@plan_bp.route('/', methods=['GET'])
@token_required
def list_plans(current_user):
    """获取学习计划列表"""
    plans = StudyPlan.find_by_user(current_user['id'])

    for p in plans:
        p['created_at'] = str(p['created_at'])
        if p.get('exam_date'):
            p['exam_date'] = str(p['exam_date'])

    return success_response(plans)

@plan_bp.route('/', methods=['POST'])
@token_required
def create_plan(current_user):
    """创建学习计划"""
    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    course_id = data.get('course_id')
    if not course_id:
        return error_response('请选择关联课程')

    # 检查课程权限
    course = Course.find_by_id(course_id)
    if not course or course['user_id'] != current_user['id']:
        return error_response('无权访问该课程', 403)

    title = data.get('title', '').strip()
    if not title:
        return error_response('计划标题不能为空')

    plan_id = StudyPlan.create(
        user_id=current_user['id'],
        course_id=course_id,
        title=title,
        goal=data.get('goal', ''),
        exam_date=data.get('exam_date'),
        daily_hours=data.get('daily_hours', 2.0),
        plan_data=data.get('plan_data')
    )

    return success_response({'id': plan_id}, '创建成功')

@plan_bp.route('/<int:plan_id>', methods=['GET'])
@token_required
def get_plan(current_user, plan_id):
    """获取学习计划详情"""
    plan = StudyPlan.find_by_id(plan_id)
    if not plan:
        return error_response('计划不存在', 404)

    if plan['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    plan['created_at'] = str(plan['created_at'])
    if plan.get('exam_date'):
        plan['exam_date'] = str(plan['exam_date'])

    return success_response(plan)

@plan_bp.route('/<int:plan_id>', methods=['PUT'])
@token_required
def update_plan(current_user, plan_id):
    """更新学习计划"""
    plan = StudyPlan.find_by_id(plan_id)
    if not plan:
        return error_response('计划不存在', 404)

    if plan['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    update_data = {}
    for field in ['title', 'goal', 'exam_date', 'daily_hours', 'plan_data']:
        if field in data:
            update_data[field] = data[field]

    if not update_data:
        return error_response('没有可更新的字段')

    StudyPlan.update(plan_id, **update_data)
    return success_response(msg='更新成功')

@plan_bp.route('/<int:plan_id>', methods=['DELETE'])
@token_required
def delete_plan(current_user, plan_id):
    """删除学习计划"""
    plan = StudyPlan.find_by_id(plan_id)
    if not plan:
        return error_response('计划不存在', 404)

    if plan['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    StudyPlan.delete(plan_id)
    return success_response(msg='删除成功')

@plan_bp.route('/generate', methods=['POST'])
@token_required
def generate_plan(current_user):
    """自动生成学习计划"""
    from services.ai_service import ai_service

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    course_id = data.get('course_id')
    if not course_id:
        return error_response('请选择关联课程')

    # 检查课程权限
    course = Course.find_by_id(course_id)
    if not course or course['user_id'] != current_user['id']:
        return error_response('无权访问该课程', 403)

    goal = data.get('goal', '')
    exam_date = data.get('exam_date')
    daily_hours = data.get('daily_hours', 2.0)

    # 调用AI生成计划
    plan_data = ai_service.generate_study_plan(
        course['name'],
        goal,
        exam_date,
        daily_hours
    )

    # 保存计划
    title = f"{course['name']}学习计划"
    plan_id = StudyPlan.create(
        user_id=current_user['id'],
        course_id=course_id,
        title=title,
        goal=goal,
        exam_date=exam_date,
        daily_hours=daily_hours,
        plan_data=plan_data
    )

    return success_response({
        'id': plan_id,
        'plan_data': plan_data
    }, '计划生成成功')
