import json
from database import db

class Conversation:
    """对话模型"""

    @staticmethod
    def create(user_id, course_id=None, title='新对话'):
        """创建对话"""
        sql = "INSERT INTO conversations (user_id, course_id, title) VALUES (?, ?, ?)"
        return db.insert(sql, (user_id, course_id, title))

    @staticmethod
    def find_by_id(conv_id):
        """根据ID查找对话"""
        sql = "SELECT * FROM conversations WHERE id = ?"
        return db.fetch_one(sql, (conv_id,))

    @staticmethod
    def find_by_user(user_id, course_id=None):
        """查找用户的对话列表"""
        if course_id:
            sql = "SELECT * FROM conversations WHERE user_id = ? AND course_id = ? ORDER BY updated_at DESC"
            return db.fetch_all(sql, (user_id, course_id))
        else:
            sql = "SELECT * FROM conversations WHERE user_id = ? ORDER BY updated_at DESC"
            return db.fetch_all(sql, (user_id,))

    @staticmethod
    def update_title(conv_id, title):
        """更新对话标题"""
        sql = "UPDATE conversations SET title = ? WHERE id = ?"
        return db.update(sql, (title, conv_id))

    @staticmethod
    def delete(conv_id):
        """删除对话"""
        sql = "DELETE FROM conversations WHERE id = ?"
        return db.delete(sql, (conv_id,))


class Message:
    """消息模型"""

    @staticmethod
    def create(conversation_id, role, content, references=None):
        """创建消息"""
        refs_json = json.dumps(references, ensure_ascii=False) if references else None
        sql = "INSERT INTO messages (conversation_id, role, content, \"references\") VALUES (?, ?, ?, ?)"
        return db.insert(sql, (conversation_id, role, content, refs_json))

    @staticmethod
    def find_by_conversation(conv_id):
        """查找对话的所有消息"""
        sql = "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC"
        return db.fetch_all(sql, (conv_id,))
