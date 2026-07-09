# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# 课程学习助手Agent平台 — 项目上下文

> 本文件供 AI 快速理解项目全貌。每次打开项目时读取此文件即可。

---

## 项目简介

基于 Flask + SQLite 的 AI 课程学习助手平台。用户可管理课程、上传文档、与 AI 对话、创建任务并智能分解、生成学习计划。

- **服务地址：** `http://localhost:5000`
- **演示账号：** `demo / 123456`
- **语言：** 全中文 UI
- **注意：** README.md 中提到 MySQL 是过时的，实际使用 SQLite。

---

## 技术栈

| 层面 | 技术 |
|---|---|
| 后端 | Python 3.10+ · Flask 3.0 |
| 数据库 | SQLite（线程本地连接，单例 `db`） |
| 前端 | 原生 HTML/CSS/JS（无框架、无构建工具） |
| AI | DeepSeek API（OpenAI兼容），支持 Mock/真实双模式 |
| 文档处理 | PyMuPDF · python-docx · python-pptx · EasyOCR |
| 检索 | BM25（rank-bm25）· 向量嵌入（OpenAI Embeddings API） |
| 认证 | JWT（PyJWT）+ bcrypt |

---

## 启动与开发命令

```bash
# 一键启动（Windows）
start.bat

# 手动启动
cd backend && pip install -r requirements.txt && python app.py

# 查看路由
python -c "from app import app; print([r.rule for r in app.url_map.iter_rules()])"

# 查数据库
python -c "from database import db; print(db.fetch_all('SELECT name FROM sqlite_master WHERE type=\"table\"'))"
```

**必需配置：** 仅需 `SECRET_KEY` 即可启动，AI 自动降级为 Mock。在 `backend/.env` 中配置 `AI_API_KEY` 启用真实 AI。

**无测试框架、无 linter、无代码格式化工具。** 修改后需手动启动服务器验证。

---

## 目录结构

```
ai/
├── docs/
│   └── task.md               # 详细实施规格书（RAG管线/流式/临时文件/技术选型/风险）
├── backend/
│   ├── .env.example          # 环境变量模板
│   ├── app.py                  # Flask 入口 + Demo 数据初始化 + 嵌入API预热
│   ├── config.py               # 全局配置（从 .env / 环境变量加载）
│   ├── database.py             # SQLite 线程安全管理器（单例 db）
│   ├── models/                 # 数据访问层（全静态方法，无实例化）
│   │   ├── user.py             #   用户 CRUD + 密码验证
│   │   ├── course.py           #   课程 CRUD
│   │   ├── document.py         #   文档 CRUD + 处理状态更新 + 分块查询
│   │   ├── chat.py             #   对话 + 消息 CRUD
│   │   ├── task.py             #   任务 CRUD（含子任务）
│   │   └── user_ai_config.py   #   用户 AI 配置 CRUD
│   ├── routes/                 # API 蓝图（8 模块 + utils）
│   │   ├── utils.py            #   token_required 装饰器 + success/error_response
│   │   ├── auth.py             #   /api/auth/*
│   │   ├── course.py           #   /api/courses/*
│   │   ├── document.py         #   /api/documents/*（含异步处理端点）
│   │   ├── chat.py             #   /api/conversations/*（含 SSE 流式 + 临时文件 + 中断）
│   │   ├── task.py             #   /api/tasks/*
│   │   ├── plan.py             #   /api/plans/*
│   │   ├── agent.py            #   /api/agent/*
│   │   └── user_ai_config.py   #   /api/user/ai-config/*
│   ├── services/               # 业务逻辑层
│   │   ├── ai_service.py       #   AI 核心（对话/摘要/知识提取/RAG/chat_rag）
│   │   ├── async_pipeline.py   #   异步文档处理管线（ThreadPoolExecutor）
│   │   ├── document_parser.py  #   多格式文档文本提取
│   │   ├── chunking_service.py #   文档分块
│   │   ├── embedding_service.py#   向量嵌入（支持用户配置）
│   │   ├── vector_store.py     #   向量存储/检索
│   │   ├── bm25_manager.py     #   BM25 索引管理
│   │   ├── retrieval_service.py#   混合检索（向量+BM25 → RRF融合）
│   │   ├── search_service.py   #   文档全文搜索
│   │   ├── streaming_service.py#   SSE 流式输出（支持中断+心跳）
│   │   ├── vision_service.py   #   视觉模型调用
│   │   ├── ocr_service.py      #   OCR 文字识别
│   │   ├── layout_analyzer.py  #   版面分析
│   │   ├── table_extractor.py  #   表格提取
│   │   ├── document_structure.py#  文档结构抽取
│   │   ├── temp_file_service.py#   对话临时文件异步处理
│   │   ├── course_import_service.py # 课程CSV导入
│   │   └── user_context.py     #   线程本地用户上下文
│   └── uploads/                # 上传文件存储（UUID重命名）
├── frontend/
│   ├── index.html              # 登录/注册（入口页，SPA fallback）
│   ├── dashboard.html          # 仪表盘
│   ├── courses.html            # 课程管理
│   ├── course_detail.html      # 课程详情（文档+任务标签页）
│   ├── chat.html               # AI 对话（SSE流式）
│   ├── tasks.html              # 任务管理
│   ├── plan.html               # 学习计划
│   ├── profile.html            # 个人中心
│   ├── ai_settings.html        # AI 模型配置
│   ├── css/style.css           # 全局 CSS（CSS变量设计系统）
│   └── js/
│       ├── api.js              # API 客户端（单例 api，JWT自动注入，SSE流式）
│       └── utils.js            # Toast/日期格式化/Markdown渲染/认证检查
├── README.md                   # 详细说明（API表格/数据库设计/环境配置）
├── 任务.md                      # 课程设计要求与任务清单
├── CLAUDE.md                   # 本文件
└── start.bat                   # Windows 一键启动
```

---

## 核心架构模式

### 请求生命周期

```
HTTP请求 → Flask路由 → @token_required装饰器
                          ├─ 解析 JWT → 查 User → set_current_user_id(user_id)
                          └─ 注入 current_user 参数
                       → 路由函数（权限校验：course.user_id == current_user.id）
                          → Model 静态方法 → db.fetch_one/fetch_all/insert/update/delete
                          → Service（从 user_context 获取 user_id → 查用户AI配置 → 调用API）
                       → teardown_appcontext → db.close_connection()
                       → clear_current_user_id()
```

### 统一响应格式

所有 API 返回 `{code: int, msg: str, data?: any}`。使用 `routes/utils.py` 中的辅助函数：
- `success_response(data, msg, code)` → 200
- `error_response(msg, code)` → 400/401/403/404/500

### token_required 装饰器模式

```python
@chat_bp.route('/<int:conv_id>', methods=['GET'])
@token_required
def get_conversation(current_user, conv_id):  # current_user 由装饰器注入
    conv = Conversation.find_by_id(conv_id)
    if conv['user_id'] != current_user['id']:  # 权限校验
        return error_response('无权访问', 403)
    ...
```

### 数据库层

- **单例 `db`**（`database.py`）：线程本地连接，`row_factory=sqlite3.Row`
- **方法**：`fetch_one(sql, params)` / `fetch_all(sql, params)` / `insert(sql, params)` → lastrowid / `update(sql, params)` → rowcount / `delete(sql, params)` → rowcount
- **Models**：纯静态方法类，直接调用 `db.xxx()`，不实例化
- **外键**：`PRAGMA foreign_keys = ON`，CASCADE/SET NULL 级联
- **修改表结构**：直接改 `database.py` 的 `_init_db()`，然后删除 `backend/course_agent.db` 重启重建

### Flask 双重角色

Flask 同时服务 API 和前端静态文件：
- `static_folder='../frontend'`，`static_url_path=''`
- `/<path:path>` 兜底路由：先尝试静态文件，否则返回 `index.html`（SPA 前端路由）
- `/api/*` 路径永远不会被兜底拦截

### 服务层延迟导入

`services/__init__.py` 使用 `__getattr__` 实现延迟导入，避免循环依赖。直接 `from services import ai_service` 或 `from services.ai_service import ai_service` 均可。

**⚠️ 新增 Service 文件时必须同步更新 `services/__init__.py`**：在 `_imports` dict 中添加模块映射，在 `__all__` 列表中添加导出名。否则 `from services import YourNewService` 会抛出 `AttributeError`。这是本项目的 #1 易错点。

### 优雅降级链

系统有多层降级策略，确保在无外部API时仍可运行：

| 功能 | 首选 | 降级1 | 降级2 |
|---|---|---|---|
| AI 对话 | DeepSeek API（OpenAI兼容） | Mock 关键词引擎 | — |
| 流式输出 | SSE（真实API stream） | 伪流式（一次性返回，逐token yield） | — |
| 向量嵌入 | OpenAI Embeddings API | 哈希降级（固定维度伪向量） | — |
| 向量检索 | 向量相似度 + BM25 RRF融合 | 纯 BM25 | — |
| OCR | PaddleOCR | EasyOCR | — |
| Token计数 | tiktoken | 字符级估算（len/2） | — |

### 用户上下文传递（线程本地）

`services/user_context.py` 使用 `threading.local()` 在请求中传递 `user_id`：
- `token_required` 装饰器：请求开始 → `set_current_user_id()`，请求结束 → `clear_current_user_id()`（在 finally 中）
- Service 层：`get_current_user_id()` → 查询 `UserAIConfig` → 用用户配置或回退全局配置
- 这避免了在所有函数签名中显式传递 `user_id`

### 用户 AI 配置优先级

`用户配置(user_ai_configs表) > 全局配置(.env) > 默认值`

Service 层统一模式：
```python
from services.user_context import get_current_user_id
from models.user_ai_config import UserAIConfig

user_id = get_current_user_id()
config = UserAIConfig.get_by_user(user_id) if user_id else None
api_key = config.ai_api_key if config and config.ai_api_key else Config.AI_API_KEY
```

### 异步文档处理管线

`services/async_pipeline.py` — 单例 `pipeline`，`ThreadPoolExecutor`（max_workers=2）

```
上传文档 → pipeline.process_document(doc_id)
         → _process_worker:
            1. document_parser    → 文本提取（PDF/Word/PPT/Excel/图片）
            2. ocr_service        → OCR（图片/PDF扫描件）
            3. layout_analyzer    → 版面分析
            4. table_extractor    → 表格提取
            5. document_structure → 结构抽取（标题层级/段落）
            6. chunking_service   → 分块（CHUNK_SIZE=512, OVERLAP=128）
            7. embedding_service  → 向量嵌入
            8. vector_store       → 向量入库
            9. bm25_manager       → BM25索引
         → 每阶段更新 documents.processing_progress (0.0~1.0)
         → 前端轮询 GET /api/documents/<id>/processing
```

### SSE 流式对话

`routes/chat.py` → `send_message_stream` 端点：
- 调用 `ai_service.chat_rag(stream=True)` 生成 SSE 事件流
- 使用 `Queue + 后台线程` 模式：生产者线程读取LLM流放入队列，主线程从队列取事件 yield
- 每 15 秒发送 `: heartbeat` SSE 注释，防止代理/浏览器超时断连
- 支持中断：`streaming_service.mark_interrupted(conv_id)` → 生成器检测后停止
- 流结束后保存 AI 回复到 messages 表（即使被中断也保存部分内容）

前端 `api.js` → `streamMessage()`：`fetch + ReadableStream`，解析 `data: {...}` SSE 事件，通过回调 `onChunk/onDone/onError` 更新 UI。返回 `AbortController` 支持取消。

---

## API 端点（完整列表见 README.md）

8 个蓝图，前缀 `/api/`：`auth` · `courses` · `documents` · `conversations` · `tasks` · `plans` · `agent` · `user/ai-config`

关键端点（非标准 CRUD）：
- `POST /api/conversations/<id>/messages/stream` — SSE 流式对话
- `POST /api/conversations/<id>/interrupt` — 中断流式生成
- `POST /api/conversations/<id>/upload-temp` — 上传临时文件（异步处理）
- `GET /api/documents/<id>/processing` — 查询文档处理进度
- `POST /api/documents/<id>/reprocess` — 重新处理文档
- `GET /api/documents/<id>/chunks` — 查看文档分块
- `POST /api/tasks/decompose/<id>` — AI 分解任务
- `POST /api/plans/generate` — AI 生成学习计划
- `POST /api/user/ai-config/test` — 测试 AI 配置连接
- `GET /api/health` — 健康检查（无需认证）

---

## 数据库（11 张表）

| 表名 | 说明 |
|---|---|
| `users` | 用户（username, password_hash, email, avatar） |
| `courses` | 课程（name, teacher, semester, credit, status=active/archived） |
| `documents` | 课程资料（含 processing_status/progress/error, structured_content, toc_tree 等处理字段） |
| `conversations` | AI 对话（可绑定 course_id） |
| `messages` | 对话消息（role=user/assistant, content, references） |
| `tasks` | 学习任务（支持 parent_task_id 自引用子任务，priority=高/中/低） |
| `study_plans` | 学习计划（goal, exam_date, daily_hours, plan_data JSON） |
| `document_chunks` | 文档分块（chunk_index, content, token_count, page_start/end, heading_path, chroma_id） |
| `document_processing_log` | 文档处理日志（stage, status, duration_ms） |
| `temp_file_sessions` | 对话临时文件会话元数据（不含文件内容，内容仅存内存） |
| `user_ai_configs` | 用户 AI 配置（9字段：对话/视觉/嵌入 × api_key/api_url/model） |

所有表定义在 `database.py` 的 `_init_db()` 中，`PRAGMA foreign_keys = ON`，支持 CASCADE/SET NULL 级联。

---

## 前端模式

- **SPA 风格**：每个页面是独立 HTML，通过 Flask 兜底路由返回 `index.html`
- **API 封装**：`js/api.js` 导出全局 `api` 单例（`ApiClient` 类），自动注入 JWT Bearer token
- **认证**：JWT 存在 `localStorage('token')`，401 响应自动清除并跳转登录页
- **CSS 变量**：`css/style.css` 使用 `:root` 定义设计系统（`--primary`, `--gray-*`, `--shadow`, `--radius`）
- **布局**：侧边栏固定（`.sidebar` 240px），主内容区 `.main-content`
- **通用工具**：`js/utils.js` — `showToast()`, `formatDate()`, `formatFileSize()`, `getFileIcon()`, `checkAuth()`
- **Markdown 渲染**：对话消息支持 Markdown（`renderMarkdown()` in utils.js）

---

## 常见修改指引

| 需求 | 修改文件 |
|---|---|
| 新增 API 接口 | `backend/routes/` 新建或修改蓝图 + `app.py` 注册 |
| 新增数据表 | `backend/database.py` 的 `_init_db()` |
| 新增 Service | ① 在 `backend/services/` 新建 .py ② 在 `services/__init__.py` 的 `_imports` dict 和 `__all__` 中添加条目 |
| 修改 AI 对话行为 | `backend/services/ai_service.py`（`chat()` / `chat_rag()`） |
| 修改文档解析 | `backend/services/document_parser.py` |
| 修改分块策略 | `backend/services/chunking_service.py` + `config.py` CHUNK_SIZE |
| 修改检索/排序 | `backend/services/retrieval_service.py`（RRF 融合参数） |
| 修改流式输出 | `backend/services/streaming_service.py` |
| 修改页面样式 | `frontend/css/style.css`（CSS 变量） |
| 新增前端页面 | `frontend/` 新建 HTML + `js/api.js` 添加方法 |
| 修改认证逻辑 | `backend/routes/utils.py`（`token_required` 装饰器） |
| 切换 Mock/真实 AI | `config.py` 的 `USE_REAL_LLM` 或 `.env` |
| 添加新 AI 模型类型 | ① `user_ai_configs` 加列 ② `UserAIConfig` 模型更新 ③ 前端表单 ④ Service 层读取 |

---

## 调试提示

- **详细实施规格**：`docs/task.md` 包含 RAG 管线、流式协议、临时文件、技术选型、风险缓解等完整设计文档
- **重置数据库**：删除 `backend/course_agent.db` 重启即可重建所有表（演示数据也会重新初始化）
- **Flask 日志**：控制台直接输出，`FLASK_DEBUG=1` 启用调试模式
- **数据库检查**：`python -c "from database import db; print(db.fetch_all('SQL'))"`
- **API 测试**：先 `POST /api/auth/login` 获取 token，再带 `Authorization: Bearer <token>` 请求
- **前端调试**：F12 → Network 看 API 请求，Console 看 JS 错误
- **文档处理调试**：查 `document_processing_log` 表 + `documents.processing_error` 字段
- **AI 降级测试**：将 `USE_REAL_LLM` 设为 `false`，系统使用 Mock 引擎（关键词匹配）
