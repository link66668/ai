from flask import Blueprint, request
import os
import re
from config import Config
from models.course import Course
from models.document import Document
from .utils import token_required, success_response, error_response

course_bp = Blueprint('course', __name__, url_prefix='/api/courses')

@course_bp.route('/', methods=['GET'])
@token_required
def list_courses(current_user):
    """获取课程列表"""
    status = request.args.get('status', 'active')

    if status == 'all':
        courses = Course.find_all_by_user(current_user['id'])
    else:
        courses = Course.find_by_user(current_user['id'], status)

    # 添加资料数量
    for c in courses:
        c['doc_count'] = Document.count_by_course(c['id'])
        c['created_at'] = str(c['created_at'])
        c['updated_at'] = str(c['updated_at'])

    return success_response(courses)

@course_bp.route('/', methods=['POST'])
@token_required
def create_course(current_user):
    """创建课程"""
    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    name = data.get('name', '').strip()
    if not name:
        return error_response('课程名称不能为空')

    course_id = Course.create(
        user_id=current_user['id'],
        name=name,
        teacher=data.get('teacher', ''),
        semester=data.get('semester', ''),
        credit=data.get('credit', 0),
        description=data.get('description', '')
    )

    return success_response({'id': course_id}, '创建成功')

@course_bp.route('/import-csv', methods=['POST'])
@token_required
def import_courses_csv(current_user):
    """通过 CSV 批量导入课程（教务课表格式）"""
    if 'file' not in request.files:
        return error_response('请上传 CSV 文件')

    file = request.files['file']
    if file.filename == '':
        return error_response('未选择文件')

    if not file.filename.lower().endswith('.csv'):
        return error_response('仅支持 CSV 格式文件')

    try:
        content = file.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            content = file.read().decode('gbk')
        except Exception:
            return error_response('文件编码不支持，请使用 UTF-8 或 GBK 编码')

    from services.course_import_service import parse_schedule_csv
    parse_result = parse_schedule_csv(content)

    if parse_result['errors']:
        return error_response('；'.join(parse_result['errors']))

    if not parse_result['courses']:
        return error_response('未在课表中找到有效课程信息')

    # 批量创建
    batch_result = Course.batch_create(current_user['id'], parse_result['courses'])

    return success_response({
        'total': len(parse_result['courses']),
        'success': batch_result['success'],
        'skipped': batch_result['skipped'],
        'errors': batch_result['errors'],
        'courses': batch_result['courses'],
        'semester': parse_result['semester'],
        'period_time_map': parse_result.get('period_time_map', {})
    }, f'成功导入 {batch_result["success"]} 门课程')

@course_bp.route('/<int:course_id>', methods=['GET'])
@token_required
def get_course(current_user, course_id):
    """获取课程详情"""
    course = Course.find_by_id(course_id)
    if not course:
        return error_response('课程不存在', 404)

    if course['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    course['doc_count'] = Document.count_by_course(course['id'])
    course['created_at'] = str(course['created_at'])
    course['updated_at'] = str(course['updated_at'])

    return success_response(course)

@course_bp.route('/<int:course_id>', methods=['PUT'])
@token_required
def update_course(current_user, course_id):
    """更新课程"""
    course = Course.find_by_id(course_id)
    if not course:
        return error_response('课程不存在', 404)

    if course['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    update_data = {}
    for field in ['name', 'teacher', 'semester', 'credit', 'description', 'status']:
        if field in data:
            update_data[field] = data[field]

    if not update_data:
        return error_response('没有可更新的字段')

    Course.update(course_id, **update_data)
    return success_response(msg='更新成功')

@course_bp.route('/<int:course_id>', methods=['DELETE'])
@token_required
def delete_course(current_user, course_id):
    """删除课程"""
    course = Course.find_by_id(course_id)
    if not course:
        return error_response('课程不存在', 404)

    if course['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    Course.delete(course_id)
    return success_response(msg='删除成功')

@course_bp.route('/<int:course_id>/archive', methods=['POST'])
@token_required
def archive_course(current_user, course_id):
    """归档课程"""
    course = Course.find_by_id(course_id)
    if not course:
        return error_response('课程不存在', 404)

    if course['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    Course.archive(course_id)
    return success_response(msg='归档成功')


@course_bp.route('/<int:course_id>/knowledge-base', methods=['GET'])
@token_required
def get_knowledge_base(current_user, course_id):
    """获取课程知识库（MinerU 转换的 Markdown 文件列表）"""
    course = Course.find_by_id(course_id)
    if not course:
        return error_response('课程不存在', 404)

    if course['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    # 构建知识库目录路径: uploads/{课程名}/
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', course['name']).strip() or 'unnamed'
    kb_dir = os.path.join(Config.UPLOAD_FOLDER, safe_name)

    kb_files = []
    if os.path.isdir(kb_dir):
        for fname in sorted(os.listdir(kb_dir)):
            if fname.endswith('.md'):
                fpath = os.path.join(kb_dir, fname)
                stat = os.stat(fpath)
                # 查找关联的文档记录（通过 md_path 匹配）
                doc_info = _find_doc_by_md_path(course_id, fpath)
                kb_files.append({
                    'filename': fname,
                    'display_name': fname.rsplit('.', 1)[0],
                    'size': stat.st_size,
                    'updated_at': stat.st_mtime,
                    'doc_id': doc_info.get('doc_id') if doc_info else None,
                    'original_name': doc_info.get('original_name') if doc_info else fname,
                    'chunk_count': doc_info.get('chunk_count', 0) if doc_info else 0,
                })

    return success_response({
        'course_name': course['name'],
        'kb_dir': safe_name,
        'total': len(kb_files),
        'files': kb_files,
    })


def _find_doc_by_md_path(course_id, md_path):
    """通过 md_path 查找关联的文档记录"""
    from database import db
    doc = db.fetch_one(
        "SELECT id, original_name, chunk_count FROM documents WHERE course_id = ? AND md_path = ?",
        (course_id, md_path)
    )
    if doc:
        return {'doc_id': doc['id'], 'original_name': doc['original_name'], 'chunk_count': doc.get('chunk_count', 0)}
    return None
