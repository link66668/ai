import json
from database import db

class Task:
    """学习任务模型"""

    @staticmethod
    def create(user_id, title, description='', course_id=None, task_type='其他', priority='中', due_date=None, parent_task_id=None):
        """创建任务"""
        sql = """INSERT INTO tasks (user_id, course_id, title, description, task_type, priority, due_date, parent_task_id)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        return db.insert(sql, (user_id, course_id, title, description, task_type, priority, due_date, parent_task_id))

    @staticmethod
    def find_by_id(task_id):
        """根据ID查找任务"""
        sql = "SELECT * FROM tasks WHERE id = ?"
        return db.fetch_one(sql, (task_id,))

    @staticmethod
    def find_by_user(user_id, status=None, course_id=None):
        """查找用户的任务列表"""
        sql = "SELECT t.*, c.name as course_name FROM tasks t LEFT JOIN courses c ON t.course_id = c.id WHERE t.user_id = ?"
        params = [user_id]

        if status:
            sql += " AND t.status = ?"
            params.append(status)

        if course_id:
            sql += " AND t.course_id = ?"
            params.append(course_id)

        # priority ENUM('高','中','低') 索引为1,2,3 → ASC才是高优先在前
        sql += " ORDER BY CASE t.status WHEN '进行中' THEN 0 WHEN '待办' THEN 1 ELSE 2 END, t.priority ASC, t.due_date ASC"
        return db.fetch_all(sql, tuple(params))

    @staticmethod
    def find_subtasks(task_id):
        """查找子任务"""
        sql = "SELECT * FROM tasks WHERE parent_task_id = ? ORDER BY created_at ASC"
        return db.fetch_all(sql, (task_id,))

    @staticmethod
    def update(task_id, **kwargs):
        """更新任务"""
        allowed_fields = {'title', 'description', 'task_type', 'priority', 'due_date', 'status', 'course_id'}
        updates = []
        values = []

        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                values.append(value)

        if not updates:
            return False

        values.append(task_id)
        sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
        return db.update(sql, values)

    @staticmethod
    def complete(task_id):
        """完成任务"""
        sql = "UPDATE tasks SET status = '已完成' WHERE id = ?"
        return db.update(sql, (task_id,))

    @staticmethod
    def delete(task_id):
        """删除任务"""
        sql = "DELETE FROM tasks WHERE id = ?"
        return db.delete(sql, (task_id,))

    @staticmethod
    def count_pending(user_id):
        """统计待办任务数"""
        sql = "SELECT COUNT(*) as count FROM tasks WHERE user_id = ? AND status != '已完成'"
        result = db.fetch_one(sql, (user_id,))
        return result['count'] if result else 0

    @staticmethod
    def count_by_status(user_id):
        """按状态统计任务数"""
        sql = """SELECT status, COUNT(*) as count FROM tasks
                 WHERE user_id = ? GROUP BY status"""
        return db.fetch_all(sql, (user_id,))


class StudyPlan:
    """学习计划模型"""

    @staticmethod
    def create(user_id, course_id, title, goal='', exam_date=None, daily_hours=2.0, plan_data=None):
        """创建学习计划"""
        plan_json = json.dumps(plan_data, ensure_ascii=False) if plan_data else None
        sql = """INSERT INTO study_plans (user_id, course_id, title, goal, exam_date, daily_hours, plan_data)
                 VALUES (?, ?, ?, ?, ?, ?, ?)"""
        return db.insert(sql, (user_id, course_id, title, goal, exam_date, daily_hours, plan_json))

    @staticmethod
    def find_by_id(plan_id):
        """根据ID查找计划"""
        sql = "SELECT * FROM study_plans WHERE id = ?"
        result = db.fetch_one(sql, (plan_id,))
        if result and result['plan_data']:
            result['plan_data'] = json.loads(result['plan_data'])
        return result

    @staticmethod
    def find_by_user(user_id):
        """查找用户的所有计划"""
        sql = "SELECT * FROM study_plans WHERE user_id = ? ORDER BY created_at DESC"
        results = db.fetch_all(sql, (user_id,))
        for r in results:
            if r['plan_data']:
                r['plan_data'] = json.loads(r['plan_data'])
        return results

    @staticmethod
    def find_by_course(course_id):
        """查找课程的学习计划"""
        sql = "SELECT * FROM study_plans WHERE course_id = ? ORDER BY created_at DESC"
        results = db.fetch_all(sql, (course_id,))
        for r in results:
            if r['plan_data']:
                r['plan_data'] = json.loads(r['plan_data'])
        return results

    @staticmethod
    def update(plan_id, **kwargs):
        """更新计划"""
        allowed_fields = {'title', 'goal', 'exam_date', 'daily_hours'}
        updates = []
        values = []

        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                values.append(value)

        if 'plan_data' in kwargs:
            updates.append("plan_data = ?")
            values.append(json.dumps(kwargs['plan_data'], ensure_ascii=False))

        if not updates:
            return False

        values.append(plan_id)
        sql = f"UPDATE study_plans SET {', '.join(updates)} WHERE id = ?"
        return db.update(sql, values)

    @staticmethod
    def delete(plan_id):
        """删除计划"""
        sql = "DELETE FROM study_plans WHERE id = ?"
        return db.delete(sql, (plan_id,))
