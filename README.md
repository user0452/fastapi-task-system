# FastAPI Task System

一个基于 **FastAPI + MySQL + JWT** 的多用户任务管理系统，支持用户注册登录、任务 CRUD、分页查询、状态筛选、优先级管理、静态前端页面，以及 AI 命令和复习计划相关扩展接口。

> 前端说明：当前 `static/` 下的前端工作台界面由 **OpenAI Codex** 辅助设计和实现，包括玻璃质感 UI、任务面板、筛选搜索、AI 复习计划页面和交互脚本。

## 功能概览

- 用户注册、登录、密码哈希存储
- JWT Bearer Token 身份认证
- 多用户任务数据隔离
- 任务创建、查询、更新、删除
- 任务分页查询、状态筛选、优先级筛选和前端搜索
- 前端统计卡片：全部、待办、进行中、已完成
- 规则版 AI 命令：创建任务、批量修改状态、删除指定状态任务
- 考试安排解析接口
- 复习计划预览接口
- 前端支持将复习计划预览导入为任务

## 技术栈

- Python 3.13
- FastAPI
- Uvicorn
- MySQL
- PyMySQL
- Pydantic
- python-jose
- Passlib + bcrypt
- python-dotenv
- LangChain + langchain-openai
- HTML / CSS / JavaScript
- uv

## 项目结构

```text
fastapi_study/
├── main.py
├── db.py
├── models.py
├── utils.py
├── llm_client.py
├── routers/
│   ├── users.py
│   ├── tasks.py
│   └── ai.py
├── static/
│   ├── index.html      # Codex 辅助重构的前端页面
│   ├── css/style.css   # 玻璃质感 UI 样式
│   └── js/app.js       # 前端交互逻辑
├── sql/init.sql
├── ai_playground/
│   └── test_langchain_llm.py
├── .env.example
├── pyproject.toml
├── uv.lock
└── README.md
```

## 环境准备

### 1. 安装依赖

```bash
uv sync
```

### 2. 初始化数据库

确保本机 MySQL 服务已启动，然后执行：

```bash
mysql -u root -p < sql/init.sql
```

初始化脚本会创建 `task_db2` 数据库，以及 `users`、`tasks`、`operation_logs` 三张表。

### 3. 配置环境变量

复制 `.env.example` 为 `.env`，并按本地环境修改：

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=task_db2

SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_HOURS=2

DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

`DEEPSEEK_*` 配置只在调用考试安排解析和复习计划预览接口时需要。基础用户、任务和规则版 AI 命令不依赖大模型配置。

## 启动项目

```bash
uv run uvicorn main:app --reload
```

启动后访问：

- 前端页面：<http://127.0.0.1:8000>
- Swagger 文档：<http://127.0.0.1:8000/docs>
- ReDoc 文档：<http://127.0.0.1:8000/redoc>

## 前端页面

当前前端为 Codex 辅助实现的静态工作台，主要包含：

- 登录 / 注册页
- 侧边导航和玻璃质感工作台布局
- 任务统计卡片
- 任务列表、分页、搜索、状态筛选、优先级筛选
- 新建、编辑、删除任务弹窗
- 规则命令面板
- 考试安排解析面板
- 复习计划预览和导入任务面板

前端文件位于：

- `static/index.html`
- `static/css/style.css`
- `static/js/app.js`

## API 说明

接口统一返回类似下面的结构：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

需要登录的接口请携带请求头：

```http
Authorization: Bearer <token>
```

### 用户注册

```http
POST /users/register
```

```json
{
  "username": "testuser",
  "password": "123456"
}
```

### 用户登录

```http
POST /users/login
```

```json
{
  "username": "testuser",
  "password": "123456"
}
```

响应中的 `data.token` 用于后续鉴权。

### 查询任务列表

```http
GET /tasks?page=1&size=10
GET /tasks?page=1&size=10&status=todo
```

`status` 可选值：

- `todo`
- `doing`
- `done`

### 查询单个任务

```http
GET /tasks/{task_id}
```

### 创建任务

```http
POST /tasks
```

```json
{
  "title": "复习 MySQL",
  "description": "练习 join 和 group by",
  "status": "todo",
  "priority": "high"
}
```

### 更新任务

```http
PUT /tasks/{task_id}
```

```json
{
  "status": "doing",
  "priority": "medium"
}
```

### 删除任务

```http
DELETE /tasks/{task_id}
```

### 规则版 AI 命令

```http
POST /ai/command
```

```json
{
  "text": "创建任务：复习数据库，优先级高"
}
```

当前规则版命令主要用于演示任务创建、批量状态修改、按状态删除等动作。

### 考试安排解析

```http
POST /ai/parse-exam-shedule
```

> 路由名称目前按代码实现为 `shedule`，不是 `schedule`。

```json
{
  "text": "高数 2026-06-10 09:00\n英语 2026-06-13 15:00"
}
```

该接口依赖 `.env` 中的 `DEEPSEEK_*` 配置。

### 复习计划预览

```http
POST /ai/preview-review-plan
```

```json
{
  "exams": [
    {
      "course": "高数",
      "exam_date": "2026-06-10",
      "exam_time": "09:00"
    }
  ]
}
```

该接口会根据考试安排生成待办任务预览，依赖 `.env` 中的 `DEEPSEEK_*` 配置。

## 数据库表

`users`

- `id`
- `username`
- `password`

`tasks`

- `id`
- `user_id`
- `title`
- `description`
- `status`
- `priority`
- `created_at`
- `updated_at`

`operation_logs`

- `id`
- `user_id`
- `action`
- `target_type`
- `target_id`
- `detail`
- `created_at`

## 本地检查

后端语法检查：

```bash
uv run python -m py_compile main.py db.py models.py utils.py llm_client.py routers/users.py routers/tasks.py routers/ai.py
```

前端脚本语法检查：

```bash
node --check static/js/app.js
```

查看已注册路由：

```bash
uv run python -c "from main import app; [print(r.path, getattr(r, 'methods', None)) for r in app.routes]"
```

## 当前状态

项目已经具备用户认证、任务管理、静态前端和 AI 扩展接口的基础闭环。当前前端由 Codex 辅助完成了一次工作台式 UI 重构；后端保持原有 FastAPI 接口设计，可继续围绕测试、异常处理、操作日志落库、Docker 部署和真实大模型工具调用方向迭代。
