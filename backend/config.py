import os
from dotenv import load_dotenv
from pathlib import Path

# 加载 .env 文件（优先使用 backend/.env，其次项目根目录 .env）
_env_file = Path(__file__).parent / '.env'
if _env_file.exists():
    load_dotenv(_env_file)
else:
    load_dotenv()  # 尝试当前工作目录

# 基础配置
class Config:
    # 数据库配置（SQLite）
    SQLITE_DB_PATH = os.environ.get(
        'SQLITE_DB_PATH',
        os.path.join(os.path.dirname(__file__), 'course_agent.db')
    )

    # JWT配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
    JWT_EXPIRATION_HOURS = 24

    # 文件上传配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'}

    # AI服务配置
    AI_API_URL = os.environ.get('AI_API_URL', 'https://api.deepseek.com')
    AI_API_KEY = os.environ.get('AI_API_KEY', '')
    AI_MODEL = os.environ.get('AI_MODEL', 'deepseek-chat')
    USE_REAL_LLM = os.environ.get('USE_REAL_LLM', 'true').lower() == 'true'
