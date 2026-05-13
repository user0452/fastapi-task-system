# ````markdown

# \# FastAPI Task System

# 

# 一个基于 \*\*FastAPI + MySQL + JWT\*\* 的多用户任务管理系统，支持用户注册登录、任务 CRUD、分页查询、状态筛选、前后端联调，并预留 AI 命令接口用于后续扩展智能任务管理能力。

# 

# \## 技术栈

# 

# \- Python

# \- FastAPI

# \- MySQL

# \- PyMySQL

# \- Pydantic

# \- JWT（python-jose）

# \- Passlib + bcrypt

# \- python-dotenv

# \- Uvicorn

# \- HTML / CSS / JavaScript

# 

# \## 核心功能

# 

# \### 用户模块

# 

# \- 用户注册

# \- 用户登录

# \- 密码哈希存储

# \- 登录成功后返回 JWT Token

# 

# \### 任务模块

# 

# \- 创建任务

# \- 查询任务列表

# \- 查询单个任务

# \- 更新任务

# \- 删除任务

# \- 分页查询

# \- 按任务状态筛选

# \- 支持任务优先级

# 

# \### 权限控制

# 

# \- 使用 JWT 进行身份认证

# \- 请求通过 `Authorization: Bearer <token>` 携带登录状态

# \- 后端解析 token 获取当前用户

# \- 使用 `user\_id` 实现多用户数据隔离

# \- 用户只能操作自己的任务

# 

# \### 前端页面

# 

# 项目包含一个静态前端页面，支持：

# 

# \- 注册

# \- 登录

# \- 任务列表展示

# \- 创建任务

# \- 修改任务

# \- 删除任务

# \- 分页查询

# \- 状态筛选

# \- AI 命令输入

# 

# \### AI 命令接口（规则版）

# 

# 当前项目包含规则版 AI 命令接口，支持部分固定自然语言指令，例如：

# 

# \- 创建任务

# \- 批量修改任务状态

# \- 删除指定状态任务

# 

# 当前版本不是接入真实大模型，而是通过规则解析实现。后续计划升级为真实大模型结构化输出。

# 

# \## 项目结构

# 

# ```text

# fastapi\_study/

# ├── main.py

# ├── db.py

# ├── models.py

# ├── utils.py

# ├── routers/

# │   ├── users.py

# │   ├── tasks.py

# │   └── ai.py

# ├── static/

# │   ├── index.html

# │   ├── css/

# │   │   └── style.css

# │   └── js/

# │       └── app.js

# ├── .env.example

# ├── pyproject.toml

# └── README.md

# ````

# 

# \## 环境变量配置

# 

# 项目使用 `.env` 管理数据库和 JWT 配置。

# 

# 请在项目根目录创建 `.env` 文件：

# 

# ```env

# DB\_HOST=127.0.0.1

# DB\_PORT=3306

# DB\_USER=root

# DB\_PASSWORD=your\_password

# DB\_NAME=task\_db2

# 

# SECRET\_KEY=your\_secret\_key

# ALGORITHM=HS256

# ACCESS\_TOKEN\_EXPIRE\_HOURS=2

# ```

# 

# `.env` 文件包含数据库密码和密钥信息，不应提交到 GitHub。

# 

# \## 启动方式

# 

# \### 1. 安装依赖

# 

# ```bash

# uv sync

# ```

# 

# \### 2. 配置环境变量

# 

# 复制 `.env.example`，创建 `.env`，并填写本地 MySQL 配置。

# 

# \### 3. 启动后端服务

# 

# ```bash

# uvicorn main:app --reload

# ```

# 

# 启动后访问：

# 

# ```text

# http://127.0.0.1:8000

# ```

# 

# Swagger 接口文档：

# 

# ```text

# http://127.0.0.1:8000/docs

# ```

# 

# \## 主要接口

# 

# \### 用户注册

# 

# ```http

# POST /users/register

# ```

# 

# 请求示例：

# 

# ```json

# {

# &#x20; "username": "testuser",

# &#x20; "password": "123456"

# }

# ```

# 

# \### 用户登录

# 

# ```http

# POST /users/login

# ```

# 

# 请求示例：

# 

# ```json

# {

# &#x20; "username": "testuser",

# &#x20; "password": "123456"

# }

# ```

# 

# 响应示例：

# 

# ```json

# {

# &#x20; "code": 200,

# &#x20; "message": "登录成功",

# &#x20; "data": {

# &#x20;   "token": "jwt\_token"

# &#x20; }

# }

# ```

# 

# \### 查询任务列表

# 

# ```http

# GET /tasks?page=1\&size=10

# ```

# 

# 请求头：

# 

# ```http

# Authorization: Bearer <token>

# ```

# 

# \### 查询单个任务

# 

# ```http

# GET /tasks/{task\_id}

# ```

# 

# 请求头：

# 

# ```http

# Authorization: Bearer <token>

# ```

# 

# \### 创建任务

# 

# ```http

# POST /tasks

# ```

# 

# 请求头：

# 

# ```http

# Authorization: Bearer <token>

# ```

# 

# 请求示例：

# 

# ```json

# {

# &#x20; "title": "复习 MySQL",

# &#x20; "description": "练习 join 和 group by",

# &#x20; "status": "todo",

# &#x20; "priority": "high"

# }

# ```

# 

# \### 更新任务

# 

# ```http

# PUT /tasks/{task\_id}

# ```

# 

# 请求头：

# 

# ```http

# Authorization: Bearer <token>

# ```

# 

# 请求示例：

# 

# ```json

# {

# &#x20; "status": "doing"

# }

# ```

# 

# \### 删除任务

# 

# ```http

# DELETE /tasks/{task\_id}

# ```

# 

# 请求头：

# 

# ```http

# Authorization: Bearer <token>

# ```

# 

# \### AI 命令接口

# 

# ```http

# POST /ai/command

# ```

# 

# 请求头：

# 

# ```http

# Authorization: Bearer <token>

# ```

# 

# 请求示例：

# 

# ```json

# {

# &#x20; "text": "创建任务：复习数据库，优先级高"

# }

# ```

# 

# \## 返回格式示例

# 

# 任务列表接口返回示例：

# 

# ```json

# {

# &#x20; "code": 200,

# &#x20; "message": "success",

# &#x20; "data": {

# &#x20;   "list": \[

# &#x20;     {

# &#x20;       "id": 1,

# &#x20;       "title": "复习 MySQL",

# &#x20;       "description": "练习 join 和 group by",

# &#x20;       "status": "todo",

# &#x20;       "priority": "medium"

# &#x20;     }

# &#x20;   ],

# &#x20;   "total": 1,

# &#x20;   "page": 1,

# &#x20;   "size": 10

# &#x20; }

# }

# ```

# 

# \## 项目亮点

# 

# \* 使用 FastAPI 构建 RESTful API

# \* 使用 MySQL 持久化任务和用户数据

# \* 使用 JWT 实现登录认证

# \* 使用密码哈希保护用户密码

# \* 使用 `user\_id` 实现多用户数据隔离

# \* 支持分页查询和任务状态筛选

# \* 使用 `.env` 管理数据库密码和 JWT 密钥

# \* 已接入静态前端页面，完成基础前后端联调

# \* 预留 AI 命令接口，后续可扩展为 AI 任务拆分和 Agent 工具调用

# 

# \## 后续优化计划

# 

# \### 后端工程化

# 

# \* 使用 HTTPBearer + Depends 优化认证逻辑

# \* 使用 Pydantic Field / Literal 完善参数校验

# \* 为 tasks 表增加 created\_at、updated\_at 字段

# \* 隐藏响应中的内部字段，如 user\_id

# \* 增加统一异常处理

# \* 增加 logging 日志

# \* 增加 operation\_logs 操作日志表

# \* 拆分 service / crud 层

# \* 增加数据库初始化脚本

# 

# \### AI / Agent 方向

# 

# \* 接入真实大模型 API

# \* 实现 AI 任务拆分和任务低阻力重写

# \* 让模型输出结构化 JSON

# \* 后端进行字段校验、权限校验和白名单校验

# \* 高风险操作增加预览和二次确认

# \* 支持导入考试安排文本/截图，自动生成复习任务

# \* 后续扩展为 Agent 工具调用流程

# 

# \### 部署与测试

# 

# \* 增加基础测试

# \* 编写 Dockerfile

# \* 使用 docker-compose 管理 MySQL 和后端服务

# \* 部署到 Linux 服务器

# 

# \## 当前状态

# 

# 项目已完成核心后端功能和基础前端联调，适合作为 Python 后端实习方向的练习项目。当前重点是继续增强工程化能力，并逐步接入 AI / Agent 功能，形成更有区分度的智能任务管理系统。

# 

# ```

# ```

# 

