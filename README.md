# A3 Learning Agent System

面向高校课程学习场景的个性化学习工作台。后端基于 FastAPI + MySQL，前端基于 Vue 3 + Vite，围绕学生画像、课程知识库 RAG、学习资源生成、练习题生成、学习计划、联网资源搜索和 AI 学习助手提供一套可演示、可扩展的学习支持系统。

当前分支：`feature/a3-learning-agent`

## 功能概览

- 用户注册、登录、JWT Bearer Token 鉴权和多用户数据隔离
- 学生画像生成与查询
- 课程资料上传、知识库分块和 RAG 检索
- 个性化学习资源生成
- 练习题生成、答题和评估
- 学习计划预览与导入任务中心
- AI 学习助手，支持非流式和流式对话
- 联网搜索外部学习资源，工具名为 `search_external_learning_resources`
- Vue 工作台前端，构建产物输出到 `static/vue`

## 技术栈

- Python 3.13
- FastAPI
- MySQL / PyMySQL
- Pydantic
- JWT
- LangChain / langchain-openai
- sentence-transformers
- FAISS
- Vue 3
- Vite
- Pinia
- Vue Router
- lucide-vue-next

## 项目结构

```text
fastapi_study/
├── agents/                      # 多智能体逻辑
│   ├── orchestrator_agent.py
│   ├── resource_agent.py
│   ├── quiz_agent.py
│   └── planner_agent.py
├── routers/                     # FastAPI 路由
│   ├── agent.py
│   ├── external_resources.py
│   ├── materials.py
│   ├── profiles.py
│   ├── quizzes.py
│   ├── resources.py
│   └── plans.py
├── services/                    # RAG、外部搜索等服务
├── frontend/                    # Vue 3 + Vite 前端源码
├── static/                      # 后端静态文件目录
│   ├── index.html               # 原静态入口
│   ├── css/
│   ├── js/
│   └── vue/                     # Vue 构建产物
├── sql/
├── main.py
├── models.py
├── requirements.txt
├── pyproject.toml
└── README.md
```

`ai_playground/` 是本地实验目录，已加入 `.gitignore`，不进入版本控制。

## 环境变量

复制 `.env.example` 为 `.env`，按本地环境填写：

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

TAVILY_API_KEY=your_tavily_api_key
```

`TAVILY_API_KEY` 用于联网搜索外部学习资源。如果不配置，外部搜索能力会受限。

## 后端运行

推荐使用 `uv`：

```bash
uv sync
uv run uvicorn main:app --reload
```

也可以使用 `requirements.txt`：

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

初始化数据库：

```bash
mysql -u root -p < sql/init.sql
```

启动后访问：

- 后端首页：`http://127.0.0.1:8000`
- Vue 前端：`http://127.0.0.1:8000/static/vue/index.html`
- Swagger：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`

## 前端运行

前端源码位于 `frontend/`：

```bash
cd frontend
npm install
npm run dev
```

开发服务默认运行在：

```text
http://127.0.0.1:5173
```

Vite 已配置代理到 `http://127.0.0.1:8000`。

构建生产产物：

```bash
cd frontend
npm run build
```

构建结果输出到：

```text
static/vue/
```

## AI 助手能力

主要接口：

- `POST /agent/chat`
- `POST /agent/chat/stream`

AI 助手会先由总控智能体解析用户需求，再按需调用工具：

- `generate_resource`
- `generate_quiz`
- `generate_plan`
- `search_external_learning_resources`

流式接口返回 NDJSON 事件：

- `status`
- `reply_delta`
- `result`
- `error`
- `done`

前端会把 AI 回复逐段显示，并在右侧展示本次工具结果。

## 联网搜索

独立接口：

```text
POST /external-resources/search
```

聊天工具和独立搜索页统一使用后端服务 `search_external_learning_resources`。搜索结果会包含标题、链接、来源、资源类型、摘要、推荐理由和预估学习时间。

## 验证

常用检查命令：

```bash
uv run python -m py_compile agents\quiz_agent.py agents\orchestrator_agent.py routers\agent.py
cd frontend
npm run build
```

本次前端构建产物已经生成到 `static/vue/`，可直接由 FastAPI 静态目录访问。
