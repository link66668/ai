# 开发规范

本文件列出项目开发中必须遵守的约定。

---

## 数据库

- **新增表或列，直接在 `database.py` 的 `_init_db()` 中修改 `CREATE TABLE` 语句**，禁止使用 `ALTER TABLE` 迁移方法
- 不编写独立的迁移脚本，不做幂等迁移逻辑
- 需要新字段时直接加到对应的 `CREATE TABLE` 里，删库重建

## AI 配置

- 所有 AI 模型参数（对话/嵌入/识图/文档处理）按用户隔离存储，存放在 `user_ai_config` 表
- 用户自定义配置优先，未配置时回退到系统默认值（`config.py` / `.env`）
- **所有 AI 调用统一使用用户在「AI 配置」页面配置的模型，不单独新建其他 AI 接口**
- 路由层负责获取用户配置（`UserAIConfig.get_effective_config(user_id)`），以 `ai_config` 参数传给 service 层
- service 层不直接查数据库获取用户配置
- 后台任务（如文档处理管线）从文档所属用户获取配置

## 前端

- 纯 HTML/CSS/JS，不引入前端框架
- 新增页面必须包含完整的侧边栏导航，保持与其他页面一致
- API 调用统一通过 `api.js` 的 `ApiClient` 类
- 表单中密码类字段（API Key 等）返回时需脱敏（前4后4，中间 `***`）

## 后端

- 路由层（`routes/`）：Flask Blueprint，使用 `@token_required` + `success_response()` / `error_response()`
- 模型层（`models/`）：全部使用 `@staticmethod`，不引入 ORM
- 服务层（`services/`）：在 `services/__init__.py` 中注册延迟导入（`__getattr__`）
- 新增蓝图必须同时在 `routes/__init__.py` 导出、`app.py` 中 `register_blueprint`
- 环境变量不强制要求，启动时缺失仅打印警告，不阻断启动

## 通用

- API 响应统一格式：`{code: int, msg: str, data: ...}`
- 不写单元测试（课程项目）
- 代码注释和 UI 文案使用中文
