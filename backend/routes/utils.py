import functools
import jwt
from flask import request, jsonify
from config import Config
from models.user import User
from services.user_context import set_current_user_id, clear_current_user_id

def token_required(f):
    """JWT认证装饰器"""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # 从Authorization头获取Token
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(' ')[1]  # Bearer <token>
            except IndexError:
                return jsonify({'code': 401, 'msg': 'Token格式错误'}), 401

        if not token:
            return jsonify({'code': 401, 'msg': '缺少认证Token'}), 401

        try:
            data = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
            current_user = User.find_by_id(data['user_id'])
            if not current_user:
                return jsonify({'code': 401, 'msg': '用户不存在'}), 401

            # 设置用户上下文，供服务层使用
            set_current_user_id(current_user['id'])

        except jwt.ExpiredSignatureError:
            return jsonify({'code': 401, 'msg': 'Token已过期'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'code': 401, 'msg': '无效的Token'}), 401

        try:
            return f(current_user, *args, **kwargs)
        finally:
            # 请求结束后清除用户上下文
            clear_current_user_id()

    return decorated

def success_response(data=None, msg='success', code=200):
    """成功响应"""
    response = {'code': code, 'msg': msg}
    if data is not None:
        response['data'] = data
    return jsonify(response), code

def error_response(msg='error', code=400):
    """错误响应"""
    return jsonify({'code': code, 'msg': msg}), code
