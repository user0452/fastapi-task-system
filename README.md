# 基于大模型与 RAG 的个性化学习资源生成与学习规划智能体系统

本项目面向“中国软件杯 A3 赛道”学习智能体场景，构建一个可演示、可交互、可闭环的个性化学习工作台。系统通过学生画像、课程知识库 RAG、多工具聊天 Agent、学习资源生成、练习评估和任务跟踪，完成从“学习需求输入”到“学习反馈改进”的完整链路。

当前分支：`feature/a3-competition`

## 项目背景

高校课程学习中，学生常见问题包括资料分散、复习路径不清晰、练习反馈滞后和个性化支持不足。本系统将大模型能力与课程资料 RAG 检索结合，让学生通过自然语言向 AI 学习助手提出需求，自动生成学习资源包、练习题、学习计划和外部学习资源推荐，并通过答题评估形成薄弱点和复习建议。

## A3 赛道对应关系

- 个性化学习：学生画像驱动资源难度、任务节奏和反馈建议。
- 课程知识库：支持 txt、md、docx、文本型 PDF 和手动文本资料，构建 RAG 检索片段。
- 学习资源生成：基于课程名、知识点、画像和 RAG 命中内容生成资源包。
- 智能体调度：聊天 Agent 统一识别意图并调用多个后端工具。
- 学习闭环：资源生成、练习作答、效果评估、学习计划导入任务中心。

## 核心功能

- 用户注册、登录、JWT Bearer Token 鉴权和多用户数据隔离
- 学生画像生成与读取
- 课程资料上传、文本解析、RAG 分块和检索
- 个性化学习资源包生成
- 练习题生成、在线作答和学习效果评估
- 学习计划生成与任务中心导入
- Tavily 外部视频、文章、文档、练习资源搜索
- AI 学习助手聊天页，支持流式输出和结构化资源卡片
- 首页数据看板，展示课程资料、学习资源、题集、评估和任务数量

## 技术架构

```text
Vue 3 工作台
  |
  |  登录、画像、资料、聊天、题集、评估、任务
  v
FastAPI 后端 API
  |
  |-- Orchestrator Agent：理解自然语言需求，规划工具调用
  |-- Resource Agent：生成学习资源包
  |-- Quiz Agent：生成练习题
  |-- Planner Agent：生成学习计划
  |-- Evaluation Agent：评估答题效果
  |
  |-- RAG Service：资料分块、embedding、FAISS 检索
  |-- External Resource Service：Tavily 联网搜索
  v
MySQL 数据库
```

## 后端技术栈

- Python 3.13
- FastAPI / Uvicorn
- MySQL / PyMySQL
- Pydantic
- python-jose / passlib
- LangChain / langchain-openai
- sentence-transformers
- FAISS
- python-docx / pypdf / python-multipart

## 前端技术栈

- Vue 3
- Vite
- Pinia
- Vue Router
- lucide-vue-next
- 原子化工作台样式与响应式布局

## AI / Agent / RAG 流程

1. 用户上传课程资料或手动录入资料。
2. 后端解析文本并构建 `course_material_chunks`。
3. 聊天 Agent 读取学生画像和最近对话历史。
4. Orchestrator Agent 输出结构化计划：`intent`、`tools`、`tool_args`。
5. 后端按计划调用资源、题集、计划、外部资源等工具。
6. 工具结果以聊天气泡下的结构化卡片展示。
7. 用户点击题集作答，Evaluation Agent 输出总分、等级、薄弱点、建议和每题反馈。
8. 用户将学习计划导入任务中心，形成可跟踪学习任务。

## 环境变量

复制 `.env.example` 为 `.env`，按本地环境填写：

```env
DATABASE_HOST=127.0.0.1
DATABASE_PORT=3306
DATABASE_USER=root
DATABASE_PASSWORD=your_password
DATABASE_NAME=task_db2

SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_HOURS=2

DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

TAVILY_API_KEY=your_tavily_api_key
```

## 启动方式

初始化数据库：

```bash
mysql -u root -p < sql/init.sql
```

启动后端：

```bash
uv sync
uv run uvicorn main:app --reload
```

或使用 `requirements.txt`：

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

访问地址：

- 系统入口：`http://127.0.0.1:8000/`
- Vue 静态构建页：`http://127.0.0.1:8000/static/vue/index.html`
- Swagger：`http://127.0.0.1:8000/docs`

前端开发模式：

```bash
cd frontend
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5173`

## 演示流程

1. 注册或登录。
2. 生成学生画像。
3. 上传或手动录入课程资料。
4. 为课程资料构建 RAG 索引。
5. 进入 AI 学习助手，输入自然语言学习需求。
6. 检查助手气泡下是否出现学习资源包、练习题、学习计划、外部资源卡片。
7. 点击练习题卡片进入作答。
8. 填写至少一道题答案并提交评估。
9. 查看总分、掌握等级、薄弱点、学习建议和每题反馈。
10. 将学习计划导入任务中心。
11. 回到首页检查数据看板是否更新。

## 推荐演示数据

推荐演示课程：

```text
软件测试-A3内部课
```

推荐知识点：

```text
等价类划分
```

推荐学生画像文本：

```text
我是软件工程专业学生，正在学习软件测试课程。我的基础一般，希望通过图文讲解、案例、练习题和阶段性学习计划掌握黑盒测试、等价类划分和边界值分析。
```

推荐课程资料文本：

```text
青瓷等价类法是本课程内部设计的一种黑盒测试用例设计方法，用来帮助初学者从输入约束中快速识别测试类别。它包含三个核心层次：青层、瓷层和裂层。青层表示完全符合需求说明的有效输入集合；瓷层表示形式上接近合法输入，但容易触发边界或格式问题的输入集合；裂层表示明显非法、异常或高风险输入。对于范围型、长度型、枚举型、格式型输入，都可以按照青层、瓷层、裂层进行划分，并设计对应测试用例。
```

推荐 AI 助手输入：

```text
我想学习软件测试-A3内部课里的等价类划分，给我讲解、练习题、三天学习计划，再推荐几个视频和资料。
```

## 支持的文件类型

- `.txt`
- `.md`
- `.docx`
- 文本型 `.pdf`
- 手动粘贴文本资料

## 当前限制

- 扫描版 PDF 暂不支持 OCR。
- 外部资源搜索依赖 `TAVILY_API_KEY`。
- RAG embedding 依赖本地 `sentence-transformers` 模型缓存或首次联网下载。
- 生成质量依赖配置的大模型服务稳定性。
- 当前演示版重点覆盖学习闭环，不包含班级管理、教师端审核和多模态 OCR。

## 后续可扩展方向

- 增加扫描版 PDF OCR 和图片资料解析。
- 增加教师端课程资料审核与班级知识库共享。
- 增加学习进度时间线和任务完成统计。
- 增加 Agent 工具调用可视化轨迹。
- 引入更细粒度的知识点掌握度建模。
- 支持更多搜索源和外部资源质量排序策略。

## 验证命令

```bash
python -m py_compile main.py models.py routers/agent.py agents/orchestrator_agent.py
cd frontend
npm run build
```
