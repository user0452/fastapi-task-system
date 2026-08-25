# A3 Goal 基线报告（历史审计）

> 本文记录 V2 重构前的仓库状态，仅作为迁移证据，不是当前产品架构或可用 API 文档。当前实现以 `README.md`、`docs/adaptive-learning-v2.md` 和 `docs/api-and-states.md` 为准。

记录日期：2026-07-11

## 1. 基线目的

本文件记录“课程冲刺学习教练 V1”重构开始前的权威状态。后续迁移必须保留当前可用能力，不得通过重置工作区或删除用户改动来制造干净基线。

## 2. 仓库状态

- 当前分支：`feature/a3-competition`
- 工作区已有大量未提交修改和新增文件，均视为需要保留的现有工作。
- `.env` 已被 `.gitignore` 排除，没有被 Git 跟踪。
- 前端生产构建产物当前写入 `static/vue`，构建会更新带哈希的资源文件。

## 3. 可重复运行环境

项目使用现有 `uv.lock` 建立了仓库内 `.venv`：

```powershell
& 'C:\Users\刘\AppData\Roaming\uv\venv\Scripts\uv.exe' sync --frozen
```

验证到的关键版本：

- Python：3.13.12
- FastAPI：0.135.3
- Pydantic：2.12.5
- Node.js：24.14.0
- npm：11.12.1
- Vite：8.0.16

## 4. 基线验证结果

### 后端

```powershell
.\.venv\Scripts\python.exe -c "from main import app; print(len(app.routes))"
```

结果：FastAPI 应用可导入，共 46 条路由；根路径返回 `307 /static/vue/index.html`。

当前冷导入耗时约 40 秒，原因是 `main.py` 导入路由时同步加载 AI、Embedding 相关模块。后续必须把重依赖延迟到实际使用阶段。

### 前端

```powershell
cd frontend
npm run build
```

结果：1784 个模块转换成功，生产构建通过。

## 5. 当前页面

- `/login`
- `/overview`
- `/profile`
- `/materials`
- `/agent`
- `/resources`
- `/quizzes`
- `/plans`
- `/tasks`
- `/logs`

目标信息架构会收敛为“今日学习、我的课程、AI 助教、学习进度、设置”，旧页面在迁移期间保留兼容入口。

## 6. 当前后端能力

- 用户注册、登录和 JWT 鉴权
- 学生画像生成与查询
- 课程资料录入、文件上传、文本解析、分块和临时 FAISS 检索
- 学习资源、题集、学习计划和学习效果评估
- 任务 CRUD 和操作日志
- 外部资源搜索
- Agent 流式对话和多工具调度
- AI 长期记忆 API

## 7. 已确认的基线缺口

- `sql/init.sql` 使用 `DROP TABLE`，不能作为生产升级路径。
- 没有课程实体，业务依赖自由文本 `course_name` 关联。
- 资料上传后需要用户手动构建索引。
- Chunk 未持久化 embedding、页码和 embedding 模型版本。
- RAG 查询会重新计算全部 chunk embedding。
- 诊断、知识点掌握度、今日学习和自适应计划尚不存在。
- 聊天主要依赖浏览器 localStorage 恢复，缺少会话 API。
- 多数业务错误只在 JSON 中写 `code`，真实 HTTP 状态仍可能为 200。
- Agent 在 LLM 和外部调用期间占用数据库连接。
- 危险 Agent 工具没有统一二次确认协议。
- 当前测试主要是打印式脚本，缺少 pytest、前端组件测试和 E2E。

## 8. 基线保护规则

- 不执行 `git reset --hard`、`git checkout --` 或其他清理用户改动的命令。
- 不直接在已有数据库执行带 `DROP TABLE` 的初始化脚本。
- 新结构通过兼容入口逐步接管功能，不一次性删除旧路由。
- 每个阶段结束必须重新验证后端导入、前端构建和该阶段新增测试。
