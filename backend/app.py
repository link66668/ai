from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
import os
import traceback
from dotenv import load_dotenv

# 加载 .env（必须在导入 config 之前）
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from config import Config
from database import db
from routes import auth_bp, course_bp, document_bp, chat_bp, task_bp, plan_bp, agent_bp, user_ai_config_bp

def create_app():
    """创建Flask应用"""
    # 启动时校验必需的环境变量
    required_vars = ['SECRET_KEY']
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f'缺少必需的环境变量: {", ".join(missing)}，'
            f'请检查 backend/.env 文件是否存在且配置正确'
        )

    # 可选：检查 AI 配置
    if not os.environ.get('AI_API_KEY'):
        print('[WARNING] AI_API_KEY not configured, AI features will use Mock mode')
        print('[INFO] To enable real AI, configure AI_API_KEY in backend/.env')

    app = Flask(__name__, static_folder='../frontend', static_url_path='')

    # 加载配置
    app.config.from_object(Config)

    # 启用CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # 每个请求结束后关闭当前线程的数据库连接
    @app.teardown_appcontext
    def close_db_connection(exception):
        db.close_connection()

    # 注册蓝图
    app.register_blueprint(auth_bp)
    app.register_blueprint(course_bp)
    app.register_blueprint(document_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(plan_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(user_ai_config_bp)

    # ---- 全局错误处理（API统一返回JSON） ----
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'code': 404, 'msg': '接口不存在'}), 404
        # 非API路径 → 返回前端页面
        return send_from_directory(app.static_folder, 'index.html')

    @app.errorhandler(500)
    def server_error(e):
        print(f'\n[500 ERROR] {request.method} {request.path}')
        print(f'  Exception: {e}')
        traceback.print_exc()
        if request.path.startswith('/api/'):
            return jsonify({'code': 500, 'msg': f'服务器内部错误: {str(e)}'}), 500
        return jsonify({'error': 'Internal Server Error'}), 500

    @app.errorhandler(405)
    def method_not_allowed(e):
        if request.path.startswith('/api/'):
            return jsonify({'code': 405, 'msg': '请求方法不允许'}), 405
        return jsonify({'error': 'Method Not Allowed'}), 405

    @app.errorhandler(413)
    def request_entity_too_large(e):
        if request.path.startswith('/api/'):
            return jsonify({'code': 413, 'msg': '文件太大，请上传50MB以内的文件'}), 413
        return jsonify({'error': 'Request Entity Too Large'}), 413

    @app.errorhandler(Exception)
    def handle_exception(e):
        """捕获所有未处理异常"""
        print(f'\n[UNHANDLED ERROR] {request.method} {request.path}')
        print(f'  Exception type: {type(e).__name__}')
        print(f'  Exception: {e}')
        traceback.print_exc()
        if request.path.startswith('/api/'):
            return jsonify({'code': 500, 'msg': f'服务器错误: {str(e)}'}), 500
        return jsonify({'error': 'Internal Server Error'}), 500

    # ---- 静态文件服务 ----
    @app.route('/')
    def serve_index():
        return send_from_directory(app.static_folder, 'index.html')

    # 健康检查
    @app.route('/api/health')
    def health_check():
        from services.vision_service import vision_service
        return {
            'status': 'ok',
            'message': '课程学习助手Agent平台运行中',
            'vision_engine': vision_service.get_active_engine_name(),
            'vision_enabled': Config.VISION_ENABLED,
            'streaming_enabled': Config.STREAMING_ENABLED,
        }

    # 静态资源(css/js)和前端页面（放在最后，优先级最低）
    @app.route('/<path:path>')
    def serve_static(path):
        # 防止拦截API请求
        if path.startswith('api/') or path.startswith('api'):
            return jsonify({'code': 404, 'msg': f'接口不存在: /{path}'}), 404
        # 先尝试作为静态文件返回
        file_path = os.path.join(app.static_folder, path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return send_from_directory(app.static_folder, path)
        # 否则返回前端入口页（支持前端路由）
        return send_from_directory(app.static_folder, 'index.html')

    return app


def init_demo_data():
    """初始化演示数据"""
    try:
        from models.user import User
        from models.course import Course
        from models.document import Document

        # 创建测试用户（如果不存在）
        existing = User.find_by_username('demo')
        if not existing:
            user_id = User.create('demo', '123456', 'demo@example.com')
            print(f'[初始化] 创建测试用户 demo (密码: 123456)')
        else:
            user_id = existing['id']

        # 创建测试课程（如果不存在）
        from database import db
        count_sql = "SELECT COUNT(*) as cnt FROM courses WHERE user_id = ?"
        result = db.fetch_one(count_sql, (user_id,))
        if result and result['cnt'] == 0:
            Course.create(user_id, '高等数学', '张教授', '2024春季', 5.0, '微积分、线性代数基础')
            Course.create(user_id, '大学英语', '李老师', '2024春季', 4.0, '英语听说读写综合能力培养')
            Course.create(user_id, 'Python程序设计', '王教授', '2024春季', 3.0, 'Python编程基础与实践')
            print(f'[初始化] 创建3个测试课程')

            # 创建测试资料
            os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

            doc_contents = [
                (1, '高等数学第一章.txt', '课件',
                 '函数与极限\n\n一、函数的概念\n函数是数学中最重要的概念之一。设D是一个非空实数集合，如果对于D中的每一个元素x，按照某个对应法则f，都有唯一确定的实数y与之对应，则称f为定义在D上的函数。\n\n二、极限的定义\n极限是微积分的基础概念。 intuitively，当自变量x无限接近某个值a时，函数f(x)的值无限接近某个确定的数L，则称L为f(x)当x→a时的极限。\n\n三、极限的运算法则\n1. 两个函数的和的极限等于它们极限的和\n2. 两个函数的积的极限等于它们极限的积\n3. 常数可以提到极限符号外面'),

                (2, '英语课文Unit1.txt', '课件',
                 'Unit 1: The Power of Language\n\nLanguage is one of the most remarkable gifts that human beings possess. It allows us to communicate our thoughts, feelings, and ideas to others. Through language, we can share knowledge, build relationships, and create understanding across cultures.\n\nReading Comprehension:\n1. What is the main topic of this passage?\n2. How does language help human beings?\n3. What can we do through language?\n\nVocabulary:\n- remarkable: extraordinary, worthy of attention\n- possess: to have, to own\n- communicate: to share information or ideas'),

                (3, 'Python基础语法.txt', '课件',
                 'Python编程基础\n\n一、变量和数据类型\nPython支持多种数据类型：\n- 整数(int): 如 1, 42, -7\n- 浮点数(float): 如 3.14, -0.5\n- 字符串(str): 如 "Hello", \'World\'\n- 布尔值(bool): True, False\n- 列表(list): 如 [1, 2, 3]\n- 字典(dict): 如 {"name": "Tom", "age": 20}\n\n二、运算符\n算术运算符: +, -, *, /, //, %, **\n比较运算符: ==, !=, >, <, >=, <=\n逻辑运算符: and, or, not\n\n三、条件语句\nif condition:\n    # 代码块\nelif condition:\n    # 代码块\nelse:\n    # 代码块\n\n四、循环语句\nfor i in range(10):\n    print(i)\n\nwhile condition:\n    # 代码块')
            ]

            for course_id, filename, category, content in doc_contents:
                filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)

                Document.create(
                    course_id=course_id,
                    user_id=user_id,
                    filename=filename,
                    original_name=filename,
                    file_path=filepath,
                    file_type='txt',
                    file_size=len(content.encode('utf-8')),
                    category=category,
                    content_text=content
                )
            print(f'[初始化] 创建3个测试资料文件')

    except Exception as e:
        print(f'[警告] 初始化演示数据失败: {e}')


if __name__ == '__main__':
    app = create_app()

    # 确保上传目录和其他数据目录存在
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(Config.CHROMA_DATA_PATH, exist_ok=True)
    os.makedirs(Config.BM25_INDEX_PATH, exist_ok=True)

    # 初始化演示数据
    with app.app_context():
        init_demo_data()
        # 初始化异步处理管线
        from services.async_pipeline import pipeline
        print(f'[启动] 异步处理管线已就绪')
        # 预热嵌入 API（后台线程，验证连通性，不阻塞启动）
        print('[启动] 后台验证嵌入 API 连通性...')
        import threading
        def warmup_embedding():
            try:
                from services.embedding_service import embedding_service
                _ = embedding_service.embed_texts(['预热'])
                print(f'[启动] 嵌入 API 就绪（维度: {embedding_service._dimension}）')
            except Exception as e:
                print(f'[启动] 嵌入 API 预热失败（将在首次处理时使用哈希降级）: {e}')
        threading.Thread(target=warmup_embedding, daemon=True).start()

    print()
    print('=' * 50)
    print('  Server running at: http://localhost:5000')
    print('  Test account: demo / 123456')
    print('=' * 50)
    print()

    app.run(host='0.0.0.0', port=5000, debug=True)
