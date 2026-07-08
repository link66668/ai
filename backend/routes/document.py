import os
import uuid
from flask import Blueprint, request, send_file, jsonify
from werkzeug.utils import secure_filename
from config import Config
from models.document import Document
from models.course import Course
from .utils import token_required, success_response, error_response

document_bp = Blueprint('document', __name__, url_prefix='/api/documents')

def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

@document_bp.route('/', methods=['GET'])
@token_required
def list_documents(current_user):
    """获取资料列表"""
    course_id = request.args.get('course_id', type=int)
    category = request.args.get('category')

    if course_id:
        # 检查课程权限
        course = Course.find_by_id(course_id)
        if not course or course['user_id'] != current_user['id']:
            return error_response('无权访问', 403)

        docs = Document.find_by_course(course_id, category)
    else:
        docs = Document.find_by_user(current_user['id'])

    for d in docs:
        d['created_at'] = str(d['created_at'])

    return success_response(docs)

@document_bp.route('/', methods=['POST'])
@token_required
def upload_document(current_user):
    """上传资料"""
    if 'file' not in request.files:
        return error_response('没有文件')

    file = request.files['file']
    if file.filename == '':
        return error_response('没有选择文件')

    if not allowed_file(file.filename):
        return error_response('不支持的文件类型')

    course_id = request.form.get('course_id', type=int)
    category = request.form.get('category', '其他')

    if not course_id:
        return error_response('请选择所属课程')

    # 检查课程权限
    course = Course.find_by_id(course_id)
    if not course or course['user_id'] != current_user['id']:
        return error_response('无权访问该课程', 403)

    # 保留原始文件名（含中文），存储用UUID
    original_name = file.filename or 'unnamed'
    ext = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else ''
    filename = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex

    # 确保上传目录存在
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    file_path = os.path.join(Config.UPLOAD_FOLDER, filename)
    file.save(file_path)

    # 获取文件信息
    file_size = os.path.getsize(file_path)
    file_type = ext

    # 提取文本内容（简单处理，txt文件直接读取）
    content_text = ''
    if ext == 'txt':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content_text = f.read()[:5000]  # 只取前5000字符
        except Exception:
            pass

    # 保存记录
    doc_id = Document.create(
        course_id=course_id,
        user_id=current_user['id'],
        filename=filename,
        original_name=original_name,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        category=category,
        content_text=content_text
    )

    return success_response({'id': doc_id}, '上传成功')

@document_bp.route('/<int:doc_id>', methods=['GET'])
@token_required
def get_document(current_user, doc_id):
    """获取资料详情"""
    doc = Document.find_by_id(doc_id)
    if not doc:
        return error_response('资料不存在', 404)

    # 检查权限
    course = Course.find_by_id(doc['course_id'])
    if not course or course['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    doc['created_at'] = str(doc['created_at'])
    return success_response(doc)

@document_bp.route('/<int:doc_id>/preview', methods=['GET'])
@token_required
def preview_document(current_user, doc_id):
    """预览资料"""
    doc = Document.find_by_id(doc_id)
    if not doc:
        return error_response('资料不存在', 404)

    # 检查权限
    course = Course.find_by_id(doc['course_id'])
    if not course or course['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    # 对于txt文件，返回文本内容
    if doc['file_type'] == 'txt' and doc.get('content_text'):
        return success_response({
            'type': 'text',
            'content': doc['content_text'],
            'filename': doc['original_name']
        })

    # 对于其他文件，返回文件路径
    if os.path.exists(doc['file_path']):
        return send_file(doc['file_path'])
    else:
        return error_response('文件不存在', 404)

@document_bp.route('/<int:doc_id>', methods=['DELETE'])
@token_required
def delete_document(current_user, doc_id):
    """删除资料"""
    doc = Document.find_by_id(doc_id)
    if not doc:
        return error_response('资料不存在', 404)

    # 检查权限
    course = Course.find_by_id(doc['course_id'])
    if not course or course['user_id'] != current_user['id']:
        return error_response('无权访问', 403)

    # 删除物理文件
    if os.path.exists(doc['file_path']):
        os.remove(doc['file_path'])

    Document.delete(doc_id)
    return success_response(msg='删除成功')

@document_bp.route('/search', methods=['GET'])
@token_required
def search_documents(current_user):
    """搜索资料"""
    from services.search_service import SearchService

    keyword = request.args.get('q', '').strip()
    course_id = request.args.get('course_id', type=int)
    file_type = request.args.get('file_type')

    if not keyword:
        return success_response([])

    search_service = SearchService()
    results = search_service.search(current_user['id'], keyword, course_id, file_type)

    for r in results:
        r['created_at'] = str(r['created_at'])

    return success_response(results)
