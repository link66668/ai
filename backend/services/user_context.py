"""用户上下文管理 - 用于在请求中传递用户信息到服务层"""
import threading

# 线程本地存储
_context = threading.local()


def set_current_user_id(user_id):
    """设置当前请求的用户 ID"""
    _context.user_id = user_id


def get_current_user_id():
    """获取当前请求的用户 ID"""
    return getattr(_context, 'user_id', None)


def clear_current_user_id():
    """清除当前请求的用户 ID"""
    if hasattr(_context, 'user_id'):
        delattr(_context, 'user_id')
