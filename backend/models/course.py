from database import db

class Course:
    """课程模型"""

    @staticmethod
    def create(user_id, name, teacher='', semester='', credit=0, description=''):
        """创建课程"""
        sql = """INSERT INTO courses (user_id, name, teacher, semester, credit, description)
                 VALUES (?, ?, ?, ?, ?, ?)"""
        return db.insert(sql, (user_id, name, teacher, semester, credit, description))

    @staticmethod
    def find_by_id(course_id):
        """根据ID查找课程"""
        sql = "SELECT * FROM courses WHERE id = ?"
        return db.fetch_one(sql, (course_id,))

    @staticmethod
    def find_by_user(user_id, status='active'):
        """查找用户的所有课程"""
        sql = "SELECT * FROM courses WHERE user_id = ? AND status = ? ORDER BY created_at DESC"
        return db.fetch_all(sql, (user_id, status))

    @staticmethod
    def find_all_by_user(user_id):
        """查找用户的所有课程（包含归档）"""
        sql = "SELECT * FROM courses WHERE user_id = ? ORDER BY created_at DESC"
        return db.fetch_all(sql, (user_id,))

    @staticmethod
    def update(course_id, **kwargs):
        """更新课程信息"""
        allowed_fields = {'name', 'teacher', 'semester', 'credit', 'description', 'status', 'kb_enabled'}
        updates = []
        values = []

        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                values.append(value)

        if not updates:
            return False

        values.append(course_id)
        sql = f"UPDATE courses SET {', '.join(updates)} WHERE id = ?"
        return db.update(sql, values)

    @staticmethod
    def archive(course_id):
        """归档课程"""
        sql = "UPDATE courses SET status = 'archived' WHERE id = ?"
        return db.update(sql, (course_id,))

    @staticmethod
    def delete(course_id):
        """删除课程"""
        sql = "DELETE FROM courses WHERE id = ?"
        return db.delete(sql, (course_id,))

    @staticmethod
    def count_by_user(user_id):
        """统计用户的课程数量"""
        sql = "SELECT COUNT(*) as count FROM courses WHERE user_id = ? AND status = 'active'"
        result = db.fetch_one(sql, (user_id,))
        return result['count'] if result else 0

    @staticmethod
    def find_by_name_and_user(name, user_id):
        """根据课程名和用户ID查找课程（用于去重）"""
        sql = "SELECT * FROM courses WHERE name = ? AND user_id = ?"
        return db.fetch_one(sql, (name, user_id))

    @staticmethod
    def toggle_kb_enabled(course_id):
        """切换知识库启用状态"""
        sql = "UPDATE courses SET kb_enabled = CASE WHEN kb_enabled = 1 THEN 0 ELSE 1 END WHERE id = ?"
        return db.update(sql, (course_id,))

    @staticmethod
    def enable_kb(course_id):
        """启用知识库"""
        sql = "UPDATE courses SET kb_enabled = 1 WHERE id = ? AND kb_enabled = 0"
        return db.update(sql, (course_id,))

    @staticmethod
    def batch_create(user_id, courses_data):
        """
        批量创建课程（跳过同名已存在的课程）

        参数:
            user_id: 用户ID
            courses_data: [{'name', 'teacher', 'semester', 'description'}, ...]

        返回:
            {'success': N, 'skipped': N, 'courses': [...], 'errors': [...]}
        """
        result = {'success': 0, 'skipped': 0, 'courses': [], 'errors': []}

        for i, item in enumerate(courses_data):
            name = item.get('name', '').strip()
            if not name:
                result['errors'].append(f'第{i+1}条：课程名称为空，已跳过')
                continue

            # 检查是否已存在同名课程
            existing = Course.find_by_name_and_user(name, user_id)
            if existing:
                result['skipped'] += 1
                continue

            try:
                course_id = Course.create(
                    user_id=user_id,
                    name=name,
                    teacher=item.get('teacher', ''),
                    semester=item.get('semester', ''),
                    credit=item.get('credit', 0),
                    description=item.get('description', '')
                )
                result['success'] += 1
                result['courses'].append({
                    'id': course_id,
                    'name': name,
                    'teacher': item.get('teacher', ''),
                    'semester': item.get('semester', '')
                })
            except Exception as e:
                result['errors'].append(f'第{i+1}条「{name}」：{str(e)}')

        return result
