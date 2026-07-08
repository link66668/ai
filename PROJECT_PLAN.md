# 课程学习助手Agent平台 - 项目实现计划

## 一、技术栈
- **前端**：HTML5 + CSS3 + JavaScript (原生)
- **后端**：Python 3.10+ + Flask
- **数据库**：MySQL 8.0+
- **文件存储**：本地文件系统
- **AI服务**：模拟API接口

## 二、项目目录结构
```
xm/
├── backend/                 # 后端代码
│   ├── app.py              # Flask主应用
│   ├── config.py           # 配置文件
│   ├── requirements.txt    # Python依赖
│   ├── database.py         # 数据库连接
│   ├── models/             # 数据模型
│   │   ├── user.py
│   │   ├── course.py
│   │   ├── document.py
│   │   ├── chat.py
│   │   └── task.py
│   ├── routes/             # API路由
│   │   ├── auth.py
│   │   ├── course.py
│   │   ├── document.py
│   │   ├── chat.py
│   │   ├── task.py
│   │   └── agent.py
│   ├── services/           # 业务逻辑
│   │   ├── ai_service.py
│   │   ├── search_service.py
│   │   └── scheduler.py
│   └── uploads/            # 文件上传目录
├── frontend/               # 前端代码
│   ├── index.html          # 登录页
│   ├── dashboard.html      # 主页/仪表盘
│   ├── courses.html        # 课程管理
│   ├── course_detail.html  # 课程详情
│   ├── chat.html           # Agent对话
│   ├── plan.html           # 学习计划
│   ├── tasks.html          # 任务管理
│   ├── profile.html        # 个人中心
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── api.js          # API调用封装
│       ├── auth.js         # 认证逻辑
│       ├── course.js       # 课程相关
│       ├── chat.js         # 对话相关
│       └── utils.js        # 工具函数
└── database/
    ├── init.sql            # 数据库初始化脚本
    └── README.md           # 数据库说明
```

## 三、数据库设计

### 3.1 用户表 (users)
```sql
- id: INT PRIMARY KEY AUTO_INCREMENT
- username: VARCHAR(50) UNIQUE NOT NULL
- password_hash: VARCHAR(255) NOT NULL
- email: VARCHAR(100)
- avatar: VARCHAR(255)
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
```

### 3.2 课程表 (courses)
```sql
- id: INT PRIMARY KEY AUTO_INCREMENT
- user_id: INT FOREIGN KEY
- name: VARCHAR(100) NOT NULL
- teacher: VARCHAR(50)
- semester: VARCHAR(20)
- credit: DECIMAL(3,1)
- description: TEXT
- status: ENUM('active', 'archived') DEFAULT 'active'
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
```

### 3.3 课程资料表 (documents)
```sql
- id: INT PRIMARY KEY AUTO_INCREMENT
- course_id: INT FOREIGN KEY
- user_id: INT FOREIGN KEY
- filename: VARCHAR(255) NOT NULL
- original_name: VARCHAR(255) NOT NULL
- file_path: VARCHAR(500) NOT NULL
- file_type: VARCHAR(20)
- file_size: INT
- category: ENUM('课件', '实验指导', '作业', '笔记', '其他')
- content_text: TEXT  # 用于全文检索
- created_at: TIMESTAMP
```

### 3.4 对话表 (conversations)
```sql
- id: INT PRIMARY KEY AUTO_INCREMENT
- user_id: INT FOREIGN KEY
- course_id: INT FOREIGN KEY NULL
- title: VARCHAR(200)
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
```

### 3.5 对话消息表 (messages)
```sql
- id: INT PRIMARY KEY AUTO_INCREMENT
- conversation_id: INT FOREIGN KEY
- role: ENUM('user', 'assistant')
- content: TEXT NOT NULL
- references: JSON  # 引用的资料信息
- created_at: TIMESTAMP
```

### 3.6 学习任务表 (tasks)
```sql
- id: INT PRIMARY KEY AUTO_INCREMENT
- user_id: INT FOREIGN KEY
- course_id: INT FOREIGN KEY
- title: VARCHAR(200) NOT NULL
- description: TEXT
- task_type: ENUM('日常作业', '实验任务', '复习计划', '考试准备', '其他')
- priority: ENUM('高', '中', '低') DEFAULT '中'
- due_date: DATETIME
- status: ENUM('待办', '进行中', '已完成') DEFAULT '待办'
- parent_task_id: INT FOREIGN KEY NULL  # 支持任务分解
- created_at: TIMESTAMP
- updated_at: TIMESTAMP
```

### 3.7 学习计划表 (study_plans)
```sql
- id: INT PRIMARY KEY AUTO_INCREMENT
- user_id: INT FOREIGN KEY
- course_id: INT FOREIGN KEY
- title: VARCHAR(200) NOT NULL
- goal: TEXT
- exam_date: DATE
- daily_hours: DECIMAL(3,1)
- plan_data: JSON  # 详细的计划安排
- created_at: TIMESTAMP
```

## 四、后端API设计

### 4.1 认证模块 /api/auth
- POST /register - 用户注册
- POST /login - 用户登录，返回JWT
- POST /logout - 用户登出
- GET /me - 获取当前用户信息
- PUT /me - 更新用户信息

### 4.2 课程模块 /api/courses
- GET / - 获取课程列表
- POST / - 创建课程
- GET /<id> - 获取课程详情
- PUT /<id> - 更新课程
- DELETE /<id> - 删除课程
- POST /<id>/archive - 归档课程

### 4.3 资料模块 /api/documents
- GET /?course_id= - 获取资料列表
- POST / - 上传资料（multipart/form-data）
- GET /<id> - 获取资料详情
- GET /<id>/preview - 预览资料
- DELETE /<id> - 删除资料
- GET /search?q=&course_id= - 搜索资料

### 4.4 对话模块 /api/conversations
- GET /?course_id= - 获取对话列表
- POST / - 创建对话
- GET /<id> - 获取对话详情
- GET /<id>/messages - 获取对话消息
- POST /<id>/messages - 发送消息（调用Agent）
- DELETE /<id> - 删除对话

### 4.5 任务模块 /api/tasks
- GET /?course_id=&status= - 获取任务列表
- POST / - 创建任务
- GET /<id> - 获取任务详情
- PUT /<id> - 更新任务
- DELETE /<id> - 删除任务
- POST /<id>/complete - 完成任务
- POST /decompose/<id> - 任务分解（调用Agent）

### 4.6 学习计划模块 /api/plans
- GET / - 获取计划列表
- POST / - 创建计划
- GET /<id> - 获取计划详情
- PUT /<id> - 更新计划
- DELETE /<id> - 删除计划
- POST /generate - 生成学习计划（调用Agent）

### 4.7 Agent模块 /api/agent
- POST /chat - 课程问答
- POST /summarize - 文本摘要
- POST /extract-knowledge - 提取知识点
- POST /generate-plan - 生成学习计划
- POST /decompose-task - 任务分解

## 五、前端页面功能

### 5.1 登录页 (index.html)
- 用户登录表单
- 注册链接
- 基础表单验证

### 5.2 仪表盘 (dashboard.html)
- 课程概览（活跃课程数量、最近活动）
- 待办任务提醒
- 学习计划进度
- 快捷入口

### 5.3 课程管理 (courses.html)
- 课程列表展示（卡片式）
- 创建课程表单
- 编辑/删除课程
- 归档课程
- 课程搜索

### 5.4 课程详情 (course_detail.html)
- 课程基本信息
- 资料列表（分类展示）
- 资料上传
- 资料预览
- 进入该课程的Agent对话
- 相关任务列表

### 5.5 Agent对话 (chat.html)
- 对话列表（按课程分类）
- 新建对话
- 聊天界面
- 消息展示（支持引用展示）
- 输入框
- 上下文切换

### 5.6 学习计划 (plan.html)
- 计划列表
- 创建计划（录入目标、考试时间、每日时长）
- 计划详情（日程展示）
- 自动生成计划

### 5.7 任务管理 (tasks.html)
- 任务列表（支持筛选）
- 创建任务
- 任务状态更新
- 任务分解
- 按课程/状态筛选

### 5.8 个人中心 (profile.html)
- 用户信息展示与编辑
- 修改密码
- 课程台账管理
- 历史对话记录
- 数据备份

## 六、实现步骤

### 阶段1：项目初始化（第1天）
1. 创建项目目录结构
2. 编写数据库初始化SQL脚本
3. 配置Flask项目，安装依赖
4. 创建数据库连接模块

### 阶段2：后端基础功能（第2-3天）
1. 实现用户认证（注册、登录、JWT）
2. 实现课程CRUD接口
3. 实现资料上传、下载、删除
4. 实现文件存储逻辑

### 阶段3：Agent与高级功能（第4-5天）
1. 实现模拟AI服务
2. 实现对话管理
3. 实现任务管理
4. 实现学习计划生成
5. 实现全文检索

### 阶段4：前端开发（第6-8天）
1. 搭建页面框架和样式
2. 实现登录注册页面
3. 实现课程管理页面
4. 实现资料管理页面
5. 实现Agent对话页面
6. 实现任务和学习计划页面
7. 实现个人中心

### 阶段5：集成测试（第9-10天）
1. 前后端联调
2. 功能测试
3. Bug修复
4. 性能优化

## 七、关键技术点

### 7.1 JWT认证
- 使用PyJWT库
- Token有效期24小时
- 前端存储到localStorage
- 每次请求携带Authorization头

### 7.2 文件上传
- 使用Flask的request.files
- 限制文件大小（10MB）
- 限制文件类型（PDF、Word、PPT、TXT、图片）
- 文件重命名（UUID + 原始扩展名）

### 7.3 全文检索
- 提取文档文本内容
- 使用MySQL的LIKE或FULLTEXT索引
- 支持关键词高亮

### 7.4 模拟AI服务
- 预设问答模板
- 基于关键词匹配
- 返回格式化的回答
- 支持资料引用标记

## 八、交付物清单
- [x] 完整的源代码
- [x] 数据库初始化脚本
- [x] 项目配置文件
- [x] README文档
- [x] API接口文档
- [x] 部署说明

## 九、注意事项
1. 所有API接口需要JWT认证（登录、注册除外）
2. 文件上传需要验证文件类型和大小
3. 敏感信息（密码）需要加密存储
4. 前端需要处理CORS跨域问题
5. 数据库操作需要事务管理
6. 错误处理需要统一格式
