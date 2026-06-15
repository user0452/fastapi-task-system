# A3 Learning Agent System

基于大模型的个性化学习资源生成与学习规划多智能体系统。项目基于 FastAPI + MySQL 构建，围绕中国软件杯 A3 赛道需求，实现学生画像、课程知识库 RAG、学习资源生成、练习题生成和学习计划生成等核心能力。

当前分支：`feature/a3-learning-agent`

## 项目简介

本系统面向高校课程学习场景，用户可以通过自然语言描述自己的学习需求，例如：

```text
我想学习软件测试-A3内部课里的单因子扰动原则，给我讲解和练习题，安排三天学习计划。
```

系统会由总控智能体理解学习需求，结合学生画像和课程知识库，调用多个智能体生成个性化学习包，包括多类型学习资源、练习题和学习计划。

核心流程：

```text
自然语言输入
→ OrchestratorAgent 理解需求
→ 读取学生画像与历史对话
→ RAG 检索课程知识库
→ ResourceAgent 生成多类型学习资源
→ QuizAgent 生成练习题
→ PlannerAgent 生成学习计划
→ 返回完整学习包与 RAG 引用
```

## 技术栈

- Python 3.13
- FastAPI
- MySQL / PyMySQL
- JWT 鉴权
- LangChain / langchain-openai
- 大模型 API 调用
- sentence-transformers
- FAISS
- Pydantic
- HTML / CSS / JavaScript
- uv

## 已实现功能

### 基础能力

- 用户注册、登录
- JWT Bearer Token 鉴权
- 多用户数据隔离
- 任务 CRUD
- 操作日志记录

### 学生画像

- `POST /profiles/generate`：根据自然语言生成学生画像
- `GET /profiles/me`：查询当前用户画像
- 学生画像用于调整资源难度、讲解方式和学习计划节奏

### 课程资料与 RAG

- `POST /materials`：上传课程资料
- `GET /materials`：查询课程资料列表
- `POST /materials/{material_id}/build-index`：将课程资料切分为 chunks
- `POST /materials/rag-search`：基于 FAISS 检索相关课程片段

RAG 流程：

```text
课程资料原文
→ split_text_to_chunks 切分文本
→ sentence-transformers 生成向量
→ FAISS 相似度检索
→ 返回相关 chunk
```

生成结果会返回 `rag_references`，用于追踪内容依据，降低大模型幻觉风险。

### 学习资源生成

- `POST /resources/generate`
- `GET /resources`
- `GET /resources/{resource_id}`

当前资源生成已升级为结构化 `resource_package`，支持多类型资源：

- 课程讲解文档 `explanation_doc`
- 知识点思维导图 `mind_map`
- 拓展阅读材料 `extended_reading`
- 实操案例 `practice_case`
- 常见误区 `common_mistakes`
- 视频讲解脚本 `video_script`

### 练习题生成

- `POST /quizzes/generate`
- `GET /quizzes`
- `GET /quizzes/{quiz_set_id}`

QuizAgent 会结合学生画像和 RAG 检索结果生成题目，并保存题集与题目详情。

### 学习计划生成

- `POST /plans/preview`：生成学习计划预览
- `POST /plans/confirm`：将学习计划导入任务表

PlannerAgent 会根据课程名、知识点和计划天数生成可执行的学习任务。

### AI 学习助手

- `POST /agent/chat`

总控智能体会解析用户自然语言学习需求，判断需要调用的工具，并协调资源生成、题目生成和学习计划生成。

支持工具：

- `generate_resource`
- `generate_quiz`
- `generate_plan`

示例请求：

```json
{
  "message": "我想学习软件测试-A3内部课里的单因子扰动原则，给我讲解和练习题，安排三天学习计划"
}
```

返回结果包含：

- `plan`：总控智能体解析出的执行计划
- `tool_results.resource`：多类型学习资源包
- `tool_results.quiz_set`：练习题集
- `tool_results.learning_plan`：学习计划
- `rag_references`：课程资料引用片段

## 项目结构

```text
fastapi-task-system/
├── agents/
│   ├── orchestrator_agent.py
│   ├── resource_agent.py
│   ├── quiz_agent.py
│   └── planner_agent.py
├── routers/
│   ├── users.py
│   ├── tasks.py
│   ├── profiles.py
│   ├── materials.py
│   ├── resources.py
│   ├── quizzes.py
│   ├── plans.py
│   └── agent.py
├── services/
│   └── rag_service.py
├── static/
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js
├── sql/init.sql
├── db.py
├── llm_client.py
├── main.py
├── models.py
├── utils.py
├── pyproject.toml
└── README.md
```

## 环境准备

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

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

### 3. 初始化数据库

确保 MySQL 服务已启动，然后执行：

```bash
mysql -u root -p < sql/init.sql
```

### 4. 启动项目

```bash
uv run uvicorn main:app --reload
```

启动后访问：

- 前端页面：`http://127.0.0.1:8000`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- ReDoc 文档：`http://127.0.0.1:8000/redoc`

## RAG 验证说明

项目中可构造一份私有课程资料，例如：

- 课程名：`软件测试-A3内部课`
- 资料标题：`青瓷等价类法完整内部讲义`
- 自定义术语：`青层`、`瓷层`、`裂层`、`单因子扰动原则`

如果系统能基于该资料准确解释“单因子扰动原则”，并返回相关 `rag_references`，说明生成内容确实参考了课程知识库，而不是单纯依赖模型已有知识。

## 当前规划

- 引入外部学习资源检索能力，为学习包推荐真实课程、视频、文档和练习链接
- 优化前端展示，将资源包、题目、计划和 RAG 引用卡片化展示
- 增加学习效果评估，根据答题结果分析薄弱点并推荐后续学习内容
- 完善课程知识库，构造更完整的高校专业课程文档集
- 优化 PlannerAgent，使学习计划能够结合 RAG 资料和外部资源进行编排

## 项目定位

本项目当前重点不是构建通用在线教育平台，而是实现一个可演示、可追踪、可扩展的 A3 赛道原型系统。系统通过学生画像、课程知识库 RAG 和多智能体协作，生成个性化学习资源、练习题和学习计划，为后续扩展真实学习资源检索和学习效果评估打基础。
