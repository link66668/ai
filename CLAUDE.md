# 课程学习助手Agent平台 — 项目上下文

> 本文件供 AI 快速理解项目全貌。每次打开项目时读取此文件即可。

---

## 项目简介

基于 Flask + SQLite 的 AI 课程学习助手平台。用户可管理课程、上传文档、与 AI 对话、创建任务并智能分解、生成学习计划。

- **服务地址：** `http://localhost:5000`
- **演示账号：** `demo / 123456`
- **语言：** 全中文 UI

---

## 技术栈

| 层面 | 技术 |
|---|---|
| 后端 | Python 3.10+ · Flask 3.0 |
| 数据库 | SQLite（文件：`backend/course_agent.db`） |
| 前端 | 原生 HTML/CSS/JS（无框架、无构建工具） |
| AI | DeepSeek LLM API（`services/ai_service.py`），支持 Mock/真实双模式 |
| 认证 | JWT（PyJWT）+ bcrypt 密码哈希 |
| 依赖 | 7 个 Python 包，见 `backend/requirements.txt` |

---

## 目录结构

```
sqllite/
├── backend/
│   ├── app.py              # Flask 入口 + Demo 数据初始化
│   ├── config.py           # 全局配置（SQLite路径、JWT、AI、上传）
│   ├── database.py         # 线程安全 SQLite 管理器（单例 + thread-local）
│   ├── requirements.txt    # Python 依赖
│   ├── models/             # 数据访问层（5 个模型）
│   │   ├── user.py         #   用户 CRUD
│   │   ├── course.py       #   课程 CRUD
│   │   ├── document.py     #   文档 CRUD
│   │   ├── chat.py         #   对话 + 消息 CRUD
│   │   └── task.py         #   任务 CRUD（含子任务）
│   ├── routes/             # API 蓝图（7 个路由模块）
│   │   ├── auth.py         #   /api/auth/*
│   │   ├── course.py       #   /api/courses/*
│   │   ├── document.py     #   /api/documents/*
│   │   ├── chat.py         #   /api/conversations/*
│   │   ├── task.py         #   /api/tasks/*
│   │   ├── plan.py         #   /api/plans/*
│   │   ├── agent.py        #   /api/agent/*
│   │   └── utils.py        #   JWT 验证装饰器
│   ├── services/
│   │   ├── ai_service.py   #   AI 服务（对话/摘要/知识提取/计划生成/任务分解）
│   │   └── search_service.py #  文档全文搜索
│   └── uploads/            # 用户上传文件存储（UUID 重命名）
├── frontend/
│   ├── index.html          # 登录/注册页
│   ├── dashboard.html      # 仪表盘（统计卡片 + 快捷操作）
│   ├── courses.html        # 课程管理（筛选/搜索/创建/归档）
│   ├── course_detail.html  # 课程详情（文档标签页 + 任务标签页）
│   ├── chat.html           # AI 对话界面（会话列表 + 消息流）
│   ├── tasks.html          # 任务管理（智能分解 + 课表视图 + 列表视图）
│   ├── plan.html           # 学习计划（AI生成 + 阶段时间线）
│   ├── profile.html        # 用户资料（编辑/改密/数据导出）
│   ├── css/style.css       # 全局 CSS 设计系统（CSS 变量）
│   └── js/
│       ├── api.js          # REST API 客户端（fetch + JWT 自动注入）
│       └── utils.js        # 工具函数（认证检查/Toast/Markdown渲染等）
├── PROJECT_PLAN.md         # 项目计划文档
├── README.md               # 项目说明文档
├── 任务.md                  # 任务清单
├── CLAUDE.md               # 本文件 — AI 上下文
└── start.bat               # Windows 一键启动脚本
```

---

## 数据库（7 张表）

| 表名 | 用途 | 关键字段 |
|---|---|---|
| `users` | 用户 | username, password_hash, email, avatar |
| `courses` | 课程 | user_id→users, name, teacher, semester, credit, status(active/archived) |
| `documents` | 文档 | course_id→courses, filename(UUID), original_name, file_path, category(课件/实验指导/作业/笔记/其他), content_text |
| `conversations` | 对话 | user_id→users, course_id→courses, title |
| `messages` | 消息 | conversation_id→conversations, role(user/assistant), content, references(JSON) |
| `tasks` | 任务 | user_id→users, course_id→courses, title, task_type(日常作业/实验任务/复习计划/考试准备/其他), priority(高/中/低), status(待办/进行中/已完成), parent_task_id→tasks(自引用) |
| `study_plans` | 学习计划 | user_id→users, course_id→courses, title, goal, exam_date, daily_hours, plan_data(JSON) |

**特性：** 线程本地连接、外键级联删除、首次运行自动建表

---

## API 接口总览

### 认证 `/api/auth`
- `POST /register` — 注册
- `POST /login` — 登录（返回 JWT token）
- `GET /me` — 获取当前用户 🔒
- `PUT /me` — 更新用户信息 🔒

### 课程 `/api/courses`
- `GET /` — 课程列表（?status=active|archived|all）🔒
- `POST /` — 创建课程 🔒
- `GET /<id>` — 课程详情 🔒
- `PUT /<id>` — 更新课程 🔒
- `DELETE /<id>` — 删除课程 🔒
- `POST /<id>/archive` — 归档课程 🔒

### 文档 `/api/documents`
- `GET /` — 文档列表（?course_id, ?category）🔒
- `POST /` — 上传文件（multipart）🔒
- `GET /<id>` — 文档详情 🔒
- `GET /<id>/preview` — 预览文档 🔒
- `DELETE /<id>` — 删除文档 🔒
- `GET /search` — 搜索文档（?q, ?course_id, ?file_type）🔒

### 对话 `/api/conversations`
- `GET /` — 对话列表（?course_id）🔒
- `POST /` — 创建对话 🔒
- `GET /<id>` — 对话详情 🔒
- `DELETE /<id>` — 删除对话 🔒
- `GET /<id>/messages` — 获取消息列表 🔒
- `POST /<id>/messages` — 发送消息（调用 AI）🔒

### 任务 `/api/tasks`
- `GET /` — 任务列表（?status, ?course_id）🔒
- `POST /` — 创建任务 🔒
- `GET /<id>` — 任务详情（含子任务）🔒
- `PUT /<id>` — 更新任务 🔒
- `DELETE /<id>` — 删除任务 🔒
- `POST /<id>/complete` — 标记完成 🔒
- `POST /decompose/<id>` — AI 分解任务 🔒

### 学习计划 `/api/plans`
- `GET /` — 计划列表 🔒
- `POST /` — 创建计划 🔒
- `GET /<id>` — 计划详情 🔒
- `PUT /<id>` — 更新计划 🔒
- `DELETE /<id>` — 删除计划 🔒
- `POST /generate` — AI 生成计划 🔒

### AI Agent `/api/agent`
- `POST /chat` — AI 课程问答（message, course_id）🔒
- `POST /summarize` — 文本摘要 🔒
- `POST /extract-knowledge` — 知识提取 🔒
- `POST /generate-plan` — 生成学习计划 🔒
- `POST /decompose-task` — 分解任务 🔒

> 🔒 = 需要 `Authorization: Bearer <token>` 请求头

---

## 关键配置（config.py）

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `SQLITE_DB_PATH` | `backend/course_agent.db` | 数据库文件路径 |
| `SECRET_KEY` | `'your-secret-key-change-in-production'` | JWT 签名密钥 |
| `JWT_EXPIRATION_HOURS` | `24` | Token 有效期（小时） |
| `UPLOAD_FOLDER` | `backend/uploads/` | 上传文件目录 |
| `MAX_CONTENT_LENGTH` | `50MB` | 最大上传大小 |
| `AI_API_URL` | `https://api.deepseek.com` | AI 接口地址 |
| `AI_API_KEY` | 环境变量 `AI_API_KEY` | DeepSeek API Key |
| `AI_MODEL` | `deepseek-chat` | AI 模型名称 |
| `USE_REAL_LLM` | `true` | `true`=调用真实LLM，`false`=使用Mock |

---

## 启动方式

```bash
# Windows 一键启动
start.bat

# 或手动启动
cd backend
pip install -r requirements.txt
python app.py
```

---

## 架构要点

1. **API 响应格式统一：** `{code: 200, msg: '...', data: {...}}`
2. **Flask 同时提供 API 和静态文件：** `static_folder='../frontend'`，非 API 路由回退到 `index.html`
3. **AI 双模式：** `USE_REAL_LLM=true` 调用 DeepSeek API；`false` 使用关键词匹配的 Mock 引擎
4. **自然语言任务分解：** 解析中文描述（如"两周内复习完高等数学"），自动提取课程、时长、目标类型
5. **Demo 数据自动初始化：** 首次运行创建 `demo/123456` 用户、3 门课程、3 个示例文档
6. **文件上传：** UUID 重命名存储，支持 txt/pdf/doc/ppt/xls/图片
7. **前端路由：** 所有非 API、非静态文件路径回退到 `index.html`（SPA 风格）

---

## 常见修改指引

| 需求 | 修改文件 |
|---|---|
| 新增 API 接口 | `backend/routes/` 新建或修改蓝图 + `app.py` 注册 |
| 新增数据表 | `backend/database.py` 的 `_create_tables()` |
| 修改 AI 行为 | `backend/services/ai_service.py` |
| 修改页面样式 | `frontend/css/style.css` |
| 新增前端页面 | `frontend/` 新建 HTML + `js/api.js` 添加接口调用 |
| 修改认证逻辑 | `backend/routes/utils.py`（JWT 装饰器） |
| 切换 Mock/真实 AI | `backend/config.py` 的 `USE_REAL_LLM` 或环境变量 |
