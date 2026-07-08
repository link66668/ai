from database import db

class Document:
    """课程资料模型"""

    @staticmethod
    def create(course_id, user_id, filename, original_name, file_path, file_type='', file_size=0, category='其他', content_text=''):
        """创建资料记录"""
        sql = """INSERT INTO documents (course_id, user_id, filename, original_name, file_path, file_type, file_size, category, content_text)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        return db.insert(sql, (course_id, user_id, filename, original_name, file_path, file_type, file_size, category, content_text))

    @staticmethod
    def find_by_id(doc_id):
        """根据ID查找资料"""
        sql = "SELECT * FROM documents WHERE id = ?"
        return db.fetch_one(sql, (doc_id,))

    @staticmethod
    def find_by_course(course_id, category=None):
        """查找课程的所有资料"""
        if category:
            sql = "SELECT * FROM documents WHERE course_id = ? AND category = ? ORDER BY created_at DESC"
            return db.fetch_all(sql, (course_id, category))
        else:
            sql = "SELECT * FROM documents WHERE course_id = ? ORDER BY created_at DESC"
            return db.fetch_all(sql, (course_id,))

    @staticmethod
    def find_by_user(user_id):
        """查找用户上传的所有资料"""
        sql = "SELECT d.*, c.name as course_name FROM documents d JOIN courses c ON d.course_id = c.id WHERE d.user_id = ? ORDER BY d.created_at DESC"
        return db.fetch_all(sql, (user_id,))

    @staticmethod
    def search(user_id, keyword, course_id=None, file_type=None):
        """搜索资料"""
        sql = """SELECT d.*, c.name as course_name
                 FROM documents d
                 JOIN courses c ON d.course_id = c.id
                 WHERE d.user_id = ?"""
        params = [user_id]

        if keyword:
            sql += " AND (d.original_name LIKE ? OR d.content_text LIKE ?)"
            params.extend([f'%{keyword}%', f'%{keyword}%'])

        if course_id:
            sql += " AND d.course_id = ?"
            params.append(course_id)

        if file_type:
            sql += " AND d.file_type = ?"
            params.append(file_type)

        sql += " ORDER BY d.created_at DESC"
        return db.fetch_all(sql, params)

    @staticmethod
    def delete(doc_id):
        """删除资料"""
        sql = "DELETE FROM documents WHERE id = ?"
        return db.delete(sql, (doc_id,))

    @staticmethod
    def count_by_course(course_id):
        """统计课程资料数量"""
        sql = "SELECT COUNT(*) as count FROM documents WHERE course_id = ?"
        result = db.fetch_one(sql, (course_id,))
        return result['count'] if result else 0
