import sqlite3
import threading
from config import Config

class Database:
    """数据库连接管理类 - SQLite线程安全版本"""

    def __init__(self):
        self.config = Config()
        self._local = threading.local()  # 线程本地存储
        self._init_db()  # 初始化数据库表

    def _init_db(self):
        """初始化数据库表结构"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            # 用户表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    email VARCHAR(100) DEFAULT '',
                    avatar VARCHAR(255) DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 课程表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    teacher VARCHAR(50) DEFAULT '',
                    semester VARCHAR(20) DEFAULT '',
                    credit DECIMAL(3,1) DEFAULT 0,
                    description TEXT,
                    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')

            # 课程资料表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    original_name VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    file_type VARCHAR(20) DEFAULT '',
                    file_size INT DEFAULT 0,
                    category TEXT DEFAULT '其他' CHECK(category IN ('课件', '实验指导', '作业', '笔记', '其他')),
                    content_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')

            # 对话表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER DEFAULT NULL,
                    title VARCHAR(200) DEFAULT '新对话',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
                )
            ''')

            # 对话消息表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    "references" TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            ''')

            # 学习任务表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER DEFAULT NULL,
                    title VARCHAR(200) NOT NULL,
                    description TEXT,
                    task_type TEXT DEFAULT '其他' CHECK(task_type IN ('日常作业', '实验任务', '复习计划', '考试准备', '其他')),
                    priority TEXT DEFAULT '中' CHECK(priority IN ('高', '中', '低')),
                    due_date DATETIME DEFAULT NULL,
                    status TEXT DEFAULT '待办' CHECK(status IN ('待办', '进行中', '已完成')),
                    parent_task_id INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL,
                    FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            ''')

            # 学习计划表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS study_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    course_id INTEGER NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    goal TEXT,
                    exam_date DATE DEFAULT NULL,
                    daily_hours DECIMAL(3,1) DEFAULT 2.0,
                    plan_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
                )
            ''')

            conn.commit()
        except Exception as e:
            print(f"[数据库初始化错误] {e}")
        finally:
            cursor.close()

    def get_connection(self):
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.config.SQLITE_DB_PATH,
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
            # 启用外键约束
            self._local.connection.execute("PRAGMA foreign_keys = ON")
        return self._local.connection

    def close_connection(self):
        """关闭当前线程的数据库连接"""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None

    def fetch_one(self, sql, params=None):
        """查询单条记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or ())
            result = cursor.fetchone()
            return dict(result) if result else None
        except Exception as e:
            raise
        finally:
            cursor.close()

    def fetch_all(self, sql, params=None):
        """查询多条记录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or ())
            results = cursor.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            raise
        finally:
            cursor.close()

    def insert(self, sql, params=None):
        """插入数据并返回ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params or ())
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def update(self, sql, params=None):
        """更新数据，返回影响行数"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            affected = cursor.execute(sql, params or ())
            conn.commit()
            return affected
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def delete(self, sql, params=None):
        """删除数据，返回影响行数"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            affected = cursor.execute(sql, params or ())
            conn.commit()
            return affected
        except Exception as e:
            conn.rollback()
            raise
        finally:
            cursor.close()

# 创建全局数据库实例
db = Database()
