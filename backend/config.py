import os
from dotenv import load_dotenv

# 加载 .env 文件（优先级：环境变量 > .env 文件）
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# 基础配置
class Config:
    # 数据库配置（SQLite）
    SQLITE_DB_PATH = os.environ.get(
        'SQLITE_DB_PATH',
        os.path.join(os.path.dirname(__file__), 'course_agent.db')
    )

    # JWT配置
    SECRET_KEY = os.environ.get('SECRET_KEY', '') or 'dev-default-secret-key-change-me'
    JWT_EXPIRATION_HOURS = 24

    # 文件上传配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200MB
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'md'}

    # AI服务配置（DeepSeek 对话模型）
    AI_API_URL = os.environ.get('AI_API_URL', 'https://api.deepseek.com')
    AI_API_KEY = os.environ.get('AI_API_KEY', '')
    AI_MODEL = os.environ.get('AI_MODEL', 'deepseek-chat')
    USE_REAL_LLM = os.environ.get('USE_REAL_LLM', 'true').lower() == 'true'

    # ========== 全格式文档引擎 + RAG 新增配置 ==========

    # 视觉模型配置（多模态API 识图）
    VISION_ENABLED = os.environ.get('VISION_ENABLED', 'true').lower() == 'true'
    VISION_API_URL = os.environ.get('VISION_API_URL', '')
    VISION_API_KEY = os.environ.get('VISION_API_KEY', '')
    VISION_MODEL = os.environ.get('VISION_MODEL', 'qwen-vl-max')
    VISION_MAX_IMAGE_SIZE = int(os.environ.get('VISION_MAX_IMAGE_SIZE', '2048'))
    VISION_CONCURRENCY = int(os.environ.get('VISION_CONCURRENCY', '3'))

    # 分块配置
    CHUNK_SIZE = int(os.environ.get('CHUNK_SIZE', '512'))         # 分块token数
    CHUNK_OVERLAP = int(os.environ.get('CHUNK_OVERLAP', '128'))   # 分块重叠token数

    # 嵌入配置（API 模式 — 调用兼容 OpenAI Embeddings 接口）
    EMBEDDING_BACKEND = os.environ.get('EMBEDDING_BACKEND', 'api')
    EMBEDDING_API_URL = os.environ.get('EMBEDDING_API_URL', '')
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY', '')
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'text-embedding-v3')
    EMBEDDING_DIMENSION = int(os.environ.get('EMBEDDING_DIMENSION', '1024'))

    # 流式配置
    STREAMING_ENABLED = os.environ.get('STREAMING_ENABLED', 'true').lower() == 'true'
    TOKEN_RATE = int(os.environ.get('TOKEN_RATE', '40'))          # 流式速率 (tokens/秒)
    MAX_CONTEXT_TOKENS = int(os.environ.get('MAX_CONTEXT_TOKENS', '6000'))

    # 处理配置
    MAX_PROCESSING_WORKERS = int(os.environ.get('MAX_PROCESSING_WORKERS', '2'))
    PROCESSING_RETRY_COUNT = int(os.environ.get('PROCESSING_RETRY_COUNT', '3'))

    # 新增路径
    CHROMA_DATA_PATH = os.path.join(os.path.dirname(__file__), 'chroma_data')
    BM25_INDEX_PATH = os.path.join(os.path.dirname(__file__), 'bm25_indexes')
