# 课程学习助手Agent平台

一个面向大学生的智能课程学习助手平台，基于 **Python Flask + SQLite + HTML/JS** 构建。平台提供课程管理、资料管理、AI对话答疑、学习任务管理、学习计划生成等功能，帮助学生高效管理课程资源、提升学习效率。

## 功能特性

### 基本要求
- **课程管理**：创建、编辑、归档课程，录入课程名称、教师、学期、学分、简介
- **课程资料管理**：分课程上传课件、笔记、作业等资料，支持在线预览和分类检索
- **Agent对话**：绑定课程知识库，AI课程答疑，对话上下文留存，课程隔离
- **学习计划**：录入目标、考试日期、每日学习时长，AI自动生成阶段性学习日程
- **个人中心**：账号管理、数据统计、数据备份导出
- **AI模型配置**：每个用户可独立配置自己的 API Key（对话/视觉/嵌入模型），优先级高于全局配置

### 高级功能
- **资料来源溯源**：AI回答自动标注参考文档，可追溯原始资料
- **知识点提取**：自动提取课件、笔记中的关键知识点
- **任务分解**：长周期任务自动拆解为周/日子任务
- **全文检索**：按关键词、课程、文件类型检索学习资料
- **RAG文档处理**：支持 PDF/Word/PPT/Excel 等多种格式的文档解析与向量化

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | HTML5 + CSS3 + JavaScript (原生，无框架) |
| 后端 | Python 3.10+ / Flask 3.0 |
| 数据库 | SQLite (文件型数据库) |
| 认证 | JWT (PyJWT) + bcrypt 密码加密 |
| 文件存储 | 本地文件系统 |
| AI服务 | DeepSeek API（支持 Mock/真实双模式） |
| 文档处理 | PyMuPDF · python-docx · python-pptx · EasyOCR |
| 检索增强 | BM25 · 向量嵌入 (OpenAI 兼容 API) |

## 快速开始

### 方式一：一键启动（Windows）

1. **安装依赖并启动**：双击运行 `start.bat`
2. 浏览器打开 `http://localhost:5000`
3. 使用演示账号登录：`demo / 123456`

### 方式二：手动启动

#### 1. 环境准备

确保已安装：
- Python 3.10+
- pip

#### 2. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

#### 3. 配置环境变量

在 `backend/` 目录下创建 `.env` 文件：

```env
# 必需配置
SECRET_KEY=your-random-secret-key-change-in-production

# AI服务配置（可选，不配置则使用 Mock 模式）
AI_API_KEY=sk-your-api-key
AI_API_URL=https://api.deepseek.com
AI_MODEL=deepseek-chat

# 视觉模型配置（可选）
VISION_API_KEY=sk-your-vision-key
VISION_API_URL=https://your-vision-api.com
VISION_MODEL=qwen-vl-max

# 嵌入模型配置（可选）
EMBEDDING_API_KEY=sk-your-embedding-key
EMBEDDING_API_URL=https://your-embedding-api.com
EMBEDDING_MODEL=text-embedding-v3
```

#### 4. 启动后端服务

```bash
cd backend
python app.py
```

服务默认运行在 `http://localhost:5000`

### 测试账号

- 用户名：`demo`
- 密码：`123456`

（也可注册新账号）

## 用户 AI 模型配置

### 功能说明

每个用户可以配置自己的 AI 模型 API Key，独立于全局配置。配置优先级：

```
用户配置 > 全局配置 (.env 文件)
```

### 配置方式

1. 登录后点击左侧导航栏的 **🔧 AI 模型配置**
2. 填写对应模型的 API Key、API 地址、模型名称
3. 点击"测试连接"验证配置有效性
4. 点击"保存配置"完成设置

### 降级策略

- 用户未配置 → 使用 `.env` 中的全局配置
- 用户部分配置 → 已配置的字段用用户的，未配置的字段用全局的
- 用户删除配置 → 回退到全局配置

## 项目结构

```
ai/
├── backend/                    # 后端代码
│   ├── app.py                  # Flask主应用入口
│   ├── config.py               # 全局配置
│   ├── database.py             # 数据库连接与表创建
│   ├── requirements.txt        # Python依赖
│   ├── models/                 # 数据模型层
│   │   ├── user.py             #   用户模型
│   │   ├── course.py           #   课程模型
│   │   ├── document.py         #   文档模型
│   │   ├── chat.py             #   对话/消息模型
│   │   ├── task.py             #   任务/计划模型
│   │   └── user_ai_config.py   #   用户AI配置模型
│   ├── routes/                 # API路由层
│   │   ├── auth.py             #   认证接口
│   │   ├── course.py           #   课程接口
│   │   ├── document.py         #   资料接口
│   │   ├── chat.py             #   对话接口
│   │   ├── task.py             #   任务接口
│   │   ├── plan.py             #   计划接口
│   │   ├── agent.py            #   Agent接口
│   │   ├── user_ai_config.py   #   用户AI配置接口
│   │   └── utils.py            #   工具函数(JWT装饰器等)
│   ├── services/               # 业务逻辑层
│   │   ├── ai_service.py       #   AI服务(对话/摘要/计划生成)
│   │   ├── search_service.py   #   文档全文搜索
│   │   ├── user_context.py     #   用户上下文管理
│   │   ├── streaming_service.py #  SSE流式输出
│   │   ├── vision_service.py   #   视觉模型调用
│   │   ── embedding_service.py #  嵌入模型调用
│   └── uploads/                # 上传文件存储
├── frontend/                   # 前端代码
│   ├── index.html              # 登录/注册页
│   ├── dashboard.html          # 仪表盘
│   ├── courses.html            # 课程管理
│   ├── course_detail.html      # 课程详情
│   ├── chat.html               # AI对话
│   ├── tasks.html              # 任务管理
│   ├── plan.html               # 学习计划
│   ├── profile.html            # 个人中心
│   ├── ai_settings.html        # AI模型配置
│   ├── css/
│   │   ── style.css           # 全局样式
│   └── js/
│       ├── api.js              # API封装
│       └── utils.js            # 工具函数
├── CLAUDE.md                   # AI上下文文档
├── PROJECT_PLAN.md             # 项目规划文档
└── README.md                   # 本文件
```

## API接口文档

### 认证模块 `/api/auth`

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /register | 用户注册 | ✗ |
| POST | /login | 用户登录 | ✗ |
| GET | /me | 获取当前用户 | ✓ |
| PUT | /me | 更新用户信息 | ✓ |

### 课程模块 `/api/courses`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 课程列表 |
| POST | / | 创建课程 |
| GET | /<id> | 课程详情 |
| PUT | /<id> | 更新课程 |
| DELETE | /<id> | 删除课程 |
| POST | /<id>/archive | 归档课程 |

### 资料模块 `/api/documents`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 资料列表 |
| POST | / | 上传资料 |
| GET | /<id> | 资料详情 |
| GET | /<id>/preview | 预览资料 |
| DELETE | /<id> | 删除资料 |
| GET | /search | 搜索资料 |

### 对话模块 `/api/conversations`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 对话列表 |
| POST | / | 创建对话 |
| GET | /<id> | 对话详情 |
| DELETE | /<id> | 删除对话 |
| GET | /<id>/messages | 获取消息 |
| POST | /<id>/messages | 发送消息 |

### 任务模块 `/api/tasks`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 任务列表 |
| POST | / | 创建任务 |
| GET | /<id> | 任务详情 |
| PUT | /<id> | 更新任务 |
| DELETE | /<id> | 删除任务 |
| POST | /<id>/complete | 完成任务 |
| POST | /decompose/<id> | 任务分解 |

### 计划模块 `/api/plans`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 计划列表 |
| POST | / | 创建计划 |
| GET | /<id> | 计划详情 |
| PUT | /<id> | 更新计划 |
| DELETE | /<id> | 删除计划 |
| POST | /generate | AI生成计划 |

### Agent模块 `/api/agent`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /chat | 课程问答 |
| POST | /summarize | 文本摘要 |
| POST | /extract-knowledge | 提取知识点 |
| POST | /generate-plan | 生成学习计划 |
| POST | /decompose-task | 任务分解 |

### 用户AI配置模块 `/api/user/ai-config`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 获取当前用户的AI配置 |
| PUT | / | 更新当前用户的AI配置 |
| POST | /test | 测试AI配置连接 |
| DELETE | / | 删除用户配置(恢复默认) |

## 数据库设计

共 8 张数据表：

| 表名 | 说明 |
|------|------|
| users | 用户表 |
| courses | 课程表 |
| documents | 课程资料表 |
| conversations | 对话表 |
| messages | 消息表 |
| tasks | 学习任务表 |
| study_plans | 学习计划表 |
| user_ai_configs | 用户AI配置表 |

数据库文件：`backend/course_agent.db`（首次运行自动创建）

## 开发说明

### 后端开发

- 后端采用 Flask 框架，MVC 分层架构
- 路由层 (`routes/`) 负责HTTP请求处理
- 模型层 (`models/`) 负责数据库操作
- 服务层 (`services/`) 负责业务逻辑（AI、检索等）
- JWT 认证，所有API（除登录/注册）需携带 `Authorization: Bearer <token>`

### 前端开发

- 纯 HTML/CSS/JS，无框架依赖
- `js/api.js` 封装所有API调用
- `js/utils.js` 提供通用工具函数
- 响应式设计，支持移动端

### AI服务

- **双模式**：`USE_REAL_LLM=true` 调用真实 LLM API；`false` 使用关键词匹配的 Mock 引擎
- **用户隔离**：每个用户可配置独立的 API Key，优先级高于全局配置
- **降级链**：RAG 失败 → Mock 检索 → LLM 失败 → 伪流式 → 阻塞 → 最终回退

## 注意事项

1. 首次运行会自动创建数据库和演示数据
2. 生产环境请修改 `SECRET_KEY` 为安全值
3. 上传文件默认存储在 `backend/uploads/` 目录
4. 文件上传限制：单文件最大 200MB
5. 支持的文件类型：txt, pdf, doc, docx, ppt, pptx, xls, xlsx, png, jpg, gif

## 团队

4人团队项目
