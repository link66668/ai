from flask import Blueprint, request
from models.task import Task
from models.course import Course
from .utils import token_required, success_response, error_response

task_bp = Blueprint('task', __name__, url_prefix='/api/tasks')

@task_bp.route('/', methods=['GET'])
@token_required
def list_tasks(current_user):
    """获取任务列表"""
    status = request.args.get('status')
    course_id = request.args.get('course_id', type=int)

    tasks = Task.find_by_user(current_user['id'], status, course_id)

    for t in tasks:
        t['created_at'] = str(t['created_at'])
        t['updated_at'] = str(t['updated_at'])
        if t.get('due_date'):
            t['due_date'] = str(t['due_date'])

    return success_response(tasks)

@task_bp.route('/', methods=['POST'])
@token_required
def create_task(current_user):
    """创建任务"""
    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    title = data.get('title', '').strip()
    if not title:
        return error_response('任务标题不能为空')

    course_id = data.get('course_id')

    # 如果指定了课程，检查权限
    if course_id:
        course = Course.find_by_id(course_id)
        if not course or course['user_id'] != current_user['id']:
            return error_response('无权访问该课程', 403)

    task_id = Task.create(
        user_id=current_user['id'],
        title=title,
        description=data.get('description', ''),
        course_id=course_id,
        task_type=data.get('task_type', '其他'),
        priority=data.get('priority', '中'),
        due_date=data.get('due_date'),
        parent_task_id=data.get('parent_task_id'),
        estimated_hours=data.get('estimated_hours')
    )

    return success_response({'id': task_id}, '创建成功')

@task_bp.route('/<int:task_id>', methods=['GET'])
@token_required
def get_task(current_user, task_id):
    """获取任务详情"""
    task = Task.find_by_id(task_id)
    if not task:
        return error_response('任务不存在', 404)

    if task['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    task['created_at'] = str(task['created_at'])
    task['updated_at'] = str(task['updated_at'])
    if task.get('due_date'):
        task['due_date'] = str(task['due_date'])

    # 获取子任务
    subtasks = Task.find_subtasks(task_id)
    task['subtasks'] = subtasks

    return success_response(task)

@task_bp.route('/<int:task_id>', methods=['PUT'])
@token_required
def update_task(current_user, task_id):
    """更新任务"""
    task = Task.find_by_id(task_id)
    if not task:
        return error_response('任务不存在', 404)

    if task['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    update_data = {}
    for field in ['title', 'description', 'task_type', 'priority', 'due_date', 'status', 'course_id', 'estimated_hours']:
        if field in data:
            update_data[field] = data[field]

    if not update_data:
        return error_response('没有可更新的字段')

    Task.update(task_id, **update_data)
    return success_response(msg='更新成功')

@task_bp.route('/<int:task_id>', methods=['DELETE'])
@token_required
def delete_task(current_user, task_id):
    """删除任务"""
    task = Task.find_by_id(task_id)
    if not task:
        return error_response('任务不存在', 404)

    if task['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    Task.delete(task_id)
    return success_response(msg='删除成功')

@task_bp.route('/<int:task_id>/complete', methods=['POST'])
@token_required
def complete_task(current_user, task_id):
    """完成任务"""
    task = Task.find_by_id(task_id)
    if not task:
        return error_response('任务不存在', 404)

    if task['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    Task.complete(task_id)
    return success_response(msg='已完成')

@task_bp.route('/decompose/<int:task_id>', methods=['POST'])
@token_required
def decompose_task(current_user, task_id):
    """任务分解（调用Agent）"""
    from services.ai_service import ai_service

    task = Task.find_by_id(task_id)
    if not task:
        return error_response('任务不存在', 404)

    if task['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    # 调用AI分解任务
    from models.user_ai_config import UserAIConfig
    ai_config = UserAIConfig.get_effective_config(current_user['id'])

    subtasks_data = ai_service.decompose_task(
        task['title'],
        task.get('description', ''),
        ai_config=ai_config,
    )

    # 创建子任务
    subtask_ids = []
    for st in subtasks_data:
        st_id = Task.create(
            user_id=current_user['id'],
            title=st['title'],
            course_id=task['course_id'],
            task_type=task['task_type'],
            priority=task['priority'],
            due_date=st.get('due_date'),
            parent_task_id=task_id
        )
        subtask_ids.append(st_id)

    return success_response({'subtask_ids': subtask_ids}, '任务分解成功')
