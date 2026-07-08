from flask import Blueprint, request
import jwt
import datetime
from config import Config
from models.user import User
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
