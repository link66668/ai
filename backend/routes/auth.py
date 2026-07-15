from flask import Blueprint, request
import jwt
import datetime
import base64
import uuid
import os
import re
import json
from config import Config
from models.user import User
from models.course import Course
from models.document import Document
from models.chat import Conversation, Message
from .utils import token_required, success_response, error_response

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    email = data.get('email', '').strip()

    if not username or not password:
        return error_response('用户名和密码不能为空')

    if len(username) < 3 or len(username) > 20:
        return error_response('用户名长度需在3-20之间')

    if len(password) < 6:
        return error_response('密码长度不能少于6位')

    # 检查用户名是否已存在
    existing = User.find_by_username(username)
    if existing:
        return error_response('用户名已存在')

    # 创建用户
    user_id = User.create(username, password, email)
    if user_id:
        return success_response({'user_id': user_id}, '注册成功')
    else:
        return error_response('注册失败')

@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return error_response('用户名和密码不能为空')

    # 查找用户
    user = User.find_by_username(username)
    if not user:
        return error_response('用户名或密码错误')

    # 验证密码
    if not User.verify_password(user, password):
        return error_response('用户名或密码错误')

    # 生成JWT Token
    token = jwt.encode({
        'user_id': user['id'],
        'username': user['username'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=Config.JWT_EXPIRATION_HOURS)
    }, Config.SECRET_KEY, algorithm='HS256')

    return success_response({
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'avatar': user['avatar']
        }
    }, '登录成功')

@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user(current_user):
    """获取当前用户信息"""
    return success_response({
        'id': current_user['id'],
        'username': current_user['username'],
        'email': current_user['email'],
        'avatar': current_user['avatar'],
        'created_at': str(current_user['created_at'])
    })

@auth_bp.route('/me', methods=['PUT'])
@token_required
def update_user(current_user):
    """更新用户信息"""
    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    update_data = {}
    if 'username' in data:
        update_data['username'] = data['username'].strip()
    if 'email' in data:
        update_data['email'] = data['email'].strip()
    if 'password' in data and data['password']:
        update_data['password'] = data['password']

    if not update_data:
        return error_response('没有可更新的字段')

    # 检查用户名是否已存在
    if 'username' in update_data:
        existing = User.find_by_username(update_data['username'])
        if existing and existing['id'] != current_user['id']:
            return error_response('用户名已被使用')

    User.update(current_user['id'], **update_data)
    return success_response(msg='更新成功')


# ==================== 导出/导入 ====================

def _read_file_as_base64(file_path):
    """读取文件并返回 base64 字典，文件不存在时返回 None"""
    if not file_path or not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        return {
            'filename': os.path.basename(file_path),
            'data': base64.b64encode(content).decode('utf-8')
        }
    except Exception:
        return None


def _write_file_from_base64(base64_data, dest_path):
    """将 base64 数据解码并写入磁盘"""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    content = base64.b64decode(base64_data)
    with open(dest_path, 'wb') as f:
        f.write(content)


def _safe_course_dir(course_name):
    """将课程名转为安全的目录名"""
    safe = re.sub(r'[\\/:*?"<>|]', '_', str(course_name)).strip()
    return safe or 'unnamed'


@auth_bp.route('/export', methods=['GET'])
@token_required
def export_user_data(current_user):
    """导出当前用户的全部数据"""
    from database import db
    from models.user_ai_config import UserAIConfig

    user_id = current_user['id']

    # 1. 用户信息（排除密码）
    user_info = {k: v for k, v in current_user.items() if k != 'password_hash'}
    user_info['created_at'] = str(user_info.get('created_at', ''))
    user_info['updated_at'] = str(user_info.get('updated_at', ''))

    # 2. 课程（只导活跃课程，已归档/删除的不导出）
    courses = Course.find_by_user(user_id) or []
    for c in courses:
        c['created_at'] = str(c.get('created_at', ''))
        c['updated_at'] = str(c.get('updated_at', ''))

    course_ids = [c['id'] for c in courses]

    # 3. 文档（含文件内容）
    documents = []
    doc_ids = []
    for c in courses:
        docs = Document.find_by_course(c['id']) or []
        for d in docs:
            d['created_at'] = str(d.get('created_at', ''))
            doc_ids.append(d['id'])
            source_file = _read_file_as_base64(d.get('file_path'))
            md_file = _read_file_as_base64(d.get('md_path'))
            documents.append({
                'row': dict(d),
                'source_file': source_file,
                'md_file': md_file,
            })

    # 4. 对话
    conversations = Conversation.find_by_user(user_id) or []
    for c in conversations:
        c['created_at'] = str(c.get('created_at', ''))
        c['updated_at'] = str(c.get('updated_at', ''))
    conv_ids = [c['id'] for c in conversations]

    # 5. 消息
    messages = []
    for conv_id in conv_ids:
        msgs = Message.find_by_conversation(conv_id) or []
        for m in msgs:
            m['created_at'] = str(m.get('created_at', ''))
        messages.extend(msgs)

    # 6. 任务
    tasks = db.fetch_all("SELECT * FROM tasks WHERE user_id = ? ORDER BY id", (user_id,)) or []
    for t in tasks:
        for field in ('due_date', 'created_at', 'updated_at'):
            if t.get(field):
                t[field] = str(t[field])
        # estimated_hours 如果是 Decimal 转 float
        if 'estimated_hours' in t and t['estimated_hours'] is not None:
            t['estimated_hours'] = float(t['estimated_hours'])
        if 'credit' in t and t['credit'] is not None:
            t['credit'] = float(t['credit'])

    # 7. AI 配置
    ai_config = UserAIConfig.find_by_user(user_id)
    if ai_config:
        ai_config = dict(ai_config)
        # 移除二进制字段和 id/user_id
        ai_config.pop('id', None)
        ai_config.pop('user_id', None)
        ai_config.pop('updated_at', None)
        # providers 如果是 JSON 字符串，保持原样

    # 8. 文档分块
    document_chunks = []
    if course_ids:
        placeholders = ','.join('?' * len(course_ids))
        document_chunks = db.fetch_all(
            f"SELECT * FROM document_chunks WHERE course_id IN ({placeholders}) ORDER BY document_id, chunk_index",
            course_ids
        ) or []

    # 9. 课程知识
    course_knowledge = []
    if course_ids:
        placeholders = ','.join('?' * len(course_ids))
        course_knowledge = db.fetch_all(
            f"SELECT * FROM course_knowledge WHERE course_id IN ({placeholders}) ORDER BY id",
            course_ids
        ) or []
        for k in course_knowledge:
            k['created_at'] = str(k.get('created_at', ''))

    # 10. 文档处理日志
    processing_logs = []
    if doc_ids:
        placeholders = ','.join('?' * len(doc_ids))
        processing_logs = db.fetch_all(
            f"SELECT * FROM document_processing_log WHERE document_id IN ({placeholders}) ORDER BY id",
            doc_ids
        ) or []
        for log in processing_logs:
            log['created_at'] = str(log.get('created_at', ''))

    # 11. 临时文件会话
    temp_sessions = []
    if conv_ids:
        placeholders = ','.join('?' * len(conv_ids))
        temp_sessions = db.fetch_all(
            f"SELECT * FROM temp_file_sessions WHERE conversation_id IN ({placeholders}) ORDER BY id",
            conv_ids
        ) or []
        for s in temp_sessions:
            s['created_at'] = str(s.get('created_at', ''))
            s['destroyed_at'] = str(s.get('destroyed_at', '')) if s.get('destroyed_at') else None

    export_data = {
        'version': 1,
        'exported_at': datetime.datetime.utcnow().isoformat(),
        'user': user_info,
        'courses': courses,
        'documents': documents,
        'conversations': conversations,
        'messages': messages,
        'tasks': tasks,
        'user_ai_config': ai_config,
        'document_chunks': document_chunks,
        'course_knowledge': course_knowledge,
        'document_processing_logs': processing_logs,
        'temp_file_sessions': temp_sessions,
    }

    return success_response(export_data, '导出成功')


@auth_bp.route('/import', methods=['POST'])
@token_required
def import_user_data(current_user):
    """导入用户数据（恢复到当前用户）"""
    from database import db
    from models.user_ai_config import UserAIConfig

    data = request.get_json()
    if not data:
        return error_response('请求数据为空')

    # 基本校验
    if not data.get('version') or not data.get('user'):
        return error_response('无效的备份文件格式')

    user_id = current_user['id']
    conn = db.get_connection()

    # ID 映射表
    course_map = {}   # old_id -> new_id
    doc_map = {}      # old_id -> new_id
    conv_map = {}     # old_id -> new_id
    task_map = {}     # old_id -> new_id

    try:
        conn.execute("BEGIN")

        # ===== 2. 课程（已存在同名课程则跳过）=====
        existing_courses = conn.execute(
            "SELECT name FROM courses WHERE user_id = ?", (user_id,)
        ).fetchall()
        existing_names = {row[0] for row in existing_courses}

        skip_course_old_ids = set()  # 被跳过的课程，其关联数据也跳过
        for course in data.get('courses', []):
            old_id = course['id']
            course_name = course.get('name', '')

            if course_name in existing_names:
                # 同名课程已存在——跳过创建，查找其 ID 用于映射
                existing = conn.execute(
                    "SELECT id FROM courses WHERE user_id = ? AND name = ?",
                    (user_id, course_name)
                ).fetchone()
                if existing:
                    course_map[old_id] = existing[0]
                    skip_course_old_ids.add(old_id)
                continue

            sql = '''INSERT INTO courses
                (user_id, name, teacher, semester, credit, description, status, kb_enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
            params = (
                user_id, course_name, course.get('teacher', ''),
                course.get('semester', ''), course.get('credit', 0),
                course.get('description', ''), course.get('status', 'active'),
                course.get('kb_enabled', 0), course.get('created_at'),
                course.get('updated_at')
            )
            curs = conn.execute(sql, params)
            new_id = curs.lastrowid
            course_map[old_id] = new_id

        # ===== 3. 文档（跳过已存在课程的文档）=====
        for doc in data.get('documents', []):
            row = doc['row']
            old_id = row['id']
            if row.get('course_id') in skip_course_old_ids:
                # 课程已存在，其文档也跳过
                continue
            new_course_id = course_map.get(row['course_id'])
            if not new_course_id:
                continue

            # 获取课程名用于目录
            course_row = conn.execute("SELECT name FROM courses WHERE id = ?", (new_course_id,)).fetchone()
            course_name = course_row[0] if course_row else 'unnamed'
            safe_dir = _safe_course_dir(course_name)

            # 还原源文件
            new_file_path = ''
            if doc.get('source_file'):
                ext = row.get('filename', '').rsplit('.', 1)[-1].lower() if '.' in row.get('filename', '') else ''
                new_filename = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
                dest_dir = os.path.join(Config.UPLOAD_FOLDER, safe_dir, 'source')
                dest_path = os.path.join(dest_dir, new_filename)
                _write_file_from_base64(doc['source_file']['data'], dest_path)
                new_file_path = dest_path

            # 还原 Markdown 文件
            new_md_path = ''
            if doc.get('md_file'):
                # 新文档 ID 尚不知道，先用占位；插入后更新
                orig_name = os.path.splitext(row.get('original_name', 'document'))[0]
                safe_name = re.sub(r'[\\/:*?"<>|]', '_', orig_name).strip() or 'document'

            # 先插入文档（md_path 后面更新）
            doc_sql = '''INSERT INTO documents
                (course_id, user_id, filename, original_name, file_path, file_type, file_size,
                 category, content_text, processing_status, processing_progress, processing_error,
                 structured_content, toc_tree, page_count, chunk_count, metadata_json, md_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
            doc_params = (
                new_course_id, user_id,
                row.get('filename', ''), row.get('original_name', ''),
                new_file_path, row.get('file_type', ''), row.get('file_size', 0),
                row.get('category', '其他'), row.get('content_text', ''),
                row.get('processing_status', 'pending'), row.get('processing_progress', 0.0),
                row.get('processing_error', ''),
                row.get('structured_content'), row.get('toc_tree'),
                row.get('page_count', 0), row.get('chunk_count', 0),
                row.get('metadata_json'), '', row.get('created_at')
            )
            curs = conn.execute(doc_sql, doc_params)
            new_doc_id = curs.lastrowid
            doc_map[old_id] = new_doc_id

            # 写 Markdown 文件（现在知道 new_doc_id）
            if doc.get('md_file'):
                orig_name = os.path.splitext(row.get('original_name', 'document'))[0]
                safe_name = re.sub(r'[\\/:*?"<>|]', '_', orig_name).strip() or 'document'
                md_filename = f"{safe_name}_{new_doc_id}.md"
                md_dir = os.path.join(Config.UPLOAD_FOLDER, safe_dir)
                md_path = os.path.join(md_dir, md_filename)
                _write_file_from_base64(doc['md_file']['data'], md_path)
                conn.execute("UPDATE documents SET md_path = ? WHERE id = ?", (md_path, new_doc_id))

        # ===== 4. 对话 =====
        for conv in data.get('conversations', []):
            old_id = conv['id']
            new_course_id = course_map.get(conv.get('course_id')) if conv.get('course_id') else None
            sql = '''INSERT INTO conversations
                (user_id, course_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)'''
            curs = conn.execute(sql, (user_id, new_course_id, conv.get('title', '新对话'),
                                      conv.get('created_at'), conv.get('updated_at')))
            conv_map[old_id] = curs.lastrowid

        # ===== 5. 消息 =====
        for msg in data.get('messages', []):
            new_conv_id = conv_map.get(msg['conversation_id'])
            if not new_conv_id:
                continue
            # references 已作为字符串从 DB 导出，直接写入即可
            refs = msg.get('references')
            if refs is not None and not isinstance(refs, str):
                refs = json.dumps(refs, ensure_ascii=False)
            sql = '''INSERT INTO messages
                (conversation_id, role, content, "references", created_at)
                VALUES (?, ?, ?, ?, ?)'''
            conn.execute(sql, (new_conv_id, msg['role'], msg['content'],
                               refs, msg.get('created_at')))

        # ===== 6. 任务（第一遍：插入所有，parent_task_id 置 NULL）=====
        task_list = data.get('tasks', [])
        for task in task_list:
            old_id = task['id']
            new_course_id = course_map.get(task.get('course_id')) if task.get('course_id') else None
            sql = '''INSERT INTO tasks
                (user_id, course_id, title, description, task_type, priority,
                 due_date, status, estimated_hours, parent_task_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)'''
            curs = conn.execute(sql, (
                user_id, new_course_id, task['title'], task.get('description', ''),
                task.get('task_type', '其他'), task.get('priority', '中'),
                task.get('due_date'), task.get('status', '待办'),
                task.get('estimated_hours'), task.get('created_at'), task.get('updated_at')
            ))
            task_map[old_id] = curs.lastrowid

        # 任务第二遍：更新 parent_task_id
        for task in task_list:
            if task.get('parent_task_id') and task['id'] in task_map:
                new_parent_id = task_map.get(task['parent_task_id'])
                new_task_id = task_map[task['id']]
                if new_parent_id:
                    conn.execute("UPDATE tasks SET parent_task_id = ? WHERE id = ?",
                                 (new_parent_id, new_task_id))

        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK")
        import traceback
        traceback.print_exc()
        return error_response(f'导入失败: {str(e)}')

    # ===== 以下操作在事务外执行（各自 auto-commit）=====
    try:
        # ===== 7. AI 配置 =====
        ai_config = data.get('user_ai_config')
        if ai_config:
            UserAIConfig.upsert(user_id, **ai_config)

        # ===== 8. 文档分块 =====
        for chunk in data.get('document_chunks', []):
            new_doc_id = doc_map.get(chunk['document_id'])
            new_course_id = course_map.get(chunk['course_id'])
            if not new_doc_id or not new_course_id:
                continue
            sql = '''INSERT INTO document_chunks
                (document_id, course_id, chunk_index, chunk_type, content,
                 token_count, page_start, page_end, heading_path, metadata_json, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
            conn.execute(sql, (
                new_doc_id, new_course_id, chunk['chunk_index'],
                chunk.get('chunk_type', 'text'), chunk['content'],
                chunk.get('token_count', 0), chunk.get('page_start', 0),
                chunk.get('page_end', 0), chunk.get('heading_path'),
                chunk.get('metadata_json'), chunk.get('content_hash', '')
            ))

        # ===== 9. 课程知识（跳过已存在课程的）=====
        for knowledge in data.get('course_knowledge', []):
            if knowledge['course_id'] in skip_course_old_ids:
                continue
            new_course_id = course_map.get(knowledge['course_id'])
            if not new_course_id:
                continue
            sql = '''INSERT INTO course_knowledge
                (course_id, type, content, source_count, created_at)
                VALUES (?, ?, ?, ?, ?)'''
            conn.execute(sql, (
                new_course_id, knowledge['type'], knowledge['content'],
                knowledge.get('source_count', 0), knowledge.get('created_at')
            ))

        # ===== 10. 文档处理日志 =====
        for log in data.get('document_processing_logs', []):
            new_doc_id = doc_map.get(log['document_id'])
            if not new_doc_id:
                continue
            sql = '''INSERT INTO document_processing_log
                (document_id, stage, status, message, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?)'''
            conn.execute(sql, (
                new_doc_id, log['stage'], log.get('status', 'started'),
                log.get('message'), log.get('duration_ms'), log.get('created_at')
            ))

        # ===== 11. 临时文件会话 =====
        for sess in data.get('temp_file_sessions', []):
            new_conv_id = conv_map.get(sess.get('conversation_id')) if sess.get('conversation_id') else None
            sql = '''INSERT INTO temp_file_sessions
                (session_id, conversation_id, file_name, file_type, file_size, destroyed_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)'''
            conn.execute(sql, (
                sess['session_id'], new_conv_id, sess.get('file_name', ''),
                sess.get('file_type', ''), sess.get('file_size', 0),
                sess.get('destroyed_at'), sess.get('created_at')
            ))

    except Exception as e:
        print(f'[导入] 非核心数据写入失败（不影响主数据）: {e}')

    # ===== 后处理：重建 BM25 索引 =====
    from services.bm25_manager import bm25_manager
    rebuilt_count = 0
    for new_course_id in course_map.values():
        try:
            chunks = db.fetch_all(
                "SELECT * FROM document_chunks WHERE course_id = ? ORDER BY document_id, chunk_index",
                (new_course_id,)
            )
            if chunks:
                bm25_manager.build_index(new_course_id, chunks)
                rebuilt_count += 1
        except Exception as e:
            print(f'[导入] 重建 BM25 索引失败 (course {new_course_id}): {e}')

    imported_courses = len(course_map) - len(skip_course_old_ids)
    return success_response({
        'courses': imported_courses,
        'courses_skipped': len(skip_course_old_ids),
        'documents': len(doc_map),
        'conversations': len(conv_map),
        'tasks': len(task_map),
        'chunks': len(data.get('document_chunks', [])),
        'knowledge': len(data.get('course_knowledge', [])),
        'bm25_rebuilt': rebuilt_count,
    }, '导入成功')
