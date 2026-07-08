import bcrypt
from database import db

class User:
    """用户模型"""

    @staticmethod
    def create(username, password, email=''):
        """创建用户"""
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        sql = "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)"
        return db.insert(sql, (username, password_hash, email))

    @staticmethod
    def find_by_username(username):
        """根据用户名查找用户"""
        sql = "SELECT * FROM users WHERE username = ?"
        return db.fetch_one(sql, (username,))

    @staticmethod
    def find_by_id(user_id):
        """根据ID查找用户"""
        sql = "SELECT * FROM users WHERE id = ?"
        return db.fetch_one(sql, (user_id,))

    @staticmethod
    def verify_password(user, password):
        """验证密码"""
        return bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8'))

    @staticmethod
    def update(user_id, **kwargs):
        """更新用户信息"""
        allowed_fields = {'username', 'email', 'avatar'}
        updates = []
        values = []

        for key, value in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                values.append(value)

        if 'password' in kwargs and kwargs['password']:
            password_hash = bcrypt.hashpw(kwargs['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            updates.append("password_hash = ?")
            values.append(password_hash)

        if not updates:
            return False

        values.append(user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        return db.update(sql, values)

    @staticmethod
    def delete(user_id):
        """删除用户"""
        sql = "DELETE FROM users WHERE id = ?"
        return db.delete(sql, (user_id,))
