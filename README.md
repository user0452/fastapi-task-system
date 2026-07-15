# A3 学习 AI

面向多课程学习的 AI 工作台。每门课程拥有独立的会话、长期记忆、资料索引、知识结构、练习与掌握度；聊天 Agent 可以自主选择只读工具，破坏性操作由 LangGraph Human-in-the-loop 中断并在用户确认后从持久化检查点恢复。

## 主要能力

- V1 Cookie 认证：HttpOnly Cookie、登录限流、统一失败提示、用户状态校验和令牌撤销。
- 真流式聊天：模型 token 增量传输、有界并发和队列、超时、断连取消及前端 `AbortController`。
- Agentic RAG：持久化课程级 FAISS 候选索引、关键词倒排召回、融合重排、邻接证据、章节目录和完整章节读取。
- 分层知识提取：章节 map、全文 reduce、topic/concept/skill/example 层级及带原始片段证据的关系。
- 上下文管理：明确 token 预算、增量滚动摘要、语义长期记忆和最近消息分层装配。
- 可靠异步任务：资料处理 job、原子 claim、lease、heartbeat、重试、worker owner 和启动恢复。
- 学习闭环：诊断、练习、LLM 事务外评估、幂等 attempt、掌握度和后续计划调整。
- 可观测性：JSON 日志、请求 ID，以及 HTTP、数据库、LLM、工具和资料任务指标。

## 目录

```text
app/
  api/v1/                 V1 API 聚合
  core/                   配置、数据库、迁移、认证响应、日志、指标
  integrations/           LLM、Embedding、FAISS、文件与文档解析
  jobs/                   持久化资料任务 worker
  modules/                account/auth/courses/materials/learning/agent/resources
frontend/src/
  features/               当前产品页面与组件
  api/                    仅调用 /api/v1
  stores/                 Cookie 认证状态和课程状态
sql/migrations/           增量迁移 SQL
tests/                    后端回归测试
scripts/verify_all.ps1    完整本地验收
```

根目录的 `routers/`、`agents/` 和 `services/` 仅用于旧客户端迁移。生产环境默认不注册这些路由；设置 `ENABLE_LEGACY_ROUTES=true` 才会临时启用。

## 本地启动

要求 Python 3.13、Node.js 20+、MySQL 8.x 和 `uv`。

```powershell
Copy-Item .env.example .env
uv sync --dev
Set-Location frontend
npm install
Set-Location ..
.venv\Scripts\python.exe -m app.core.migrations
```

后端：

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8010
```

前端：

```powershell
Set-Location frontend
$env:VITE_API_TARGET='http://127.0.0.1:8010'
npm run dev -- --host 127.0.0.1 --port 5175
```

访问 `http://127.0.0.1:5175/#/today`。健康检查为 `/health/live`、`/health/ready`，Prometheus 指标为 `/metrics`。

## 关键配置

```env
APP_ENV=development
ENABLE_LEGACY_ROUTES=true
DATABASE_HOST=127.0.0.1
DATABASE_PORT=3306
DATABASE_USER=root
DATABASE_PASSWORD=your_password
DATABASE_NAME=task_db2
SECRET_KEY=replace-with-a-long-random-secret

DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=your-model
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=2
```

自动化或离线演示可使用 `A3_MOCK_LLM=true` 和 `A3_MOCK_EMBEDDING=true`。生产环境必须使用足够长的随机 `SECRET_KEY`，保持 `ENABLE_LEGACY_ROUTES=false`，并通过 HTTPS 提供服务。

## 资料限制

- 单文件最大 100MB，支持 TXT、Markdown、文本型 PDF 和 DOCX。
- 上传按块落盘；解析直接读取路径，不把 100MB 文件整体复制到内存。
- PDF 限制 2000 页；DOCX 校验文件签名、成员数量和解压后体积，防止压缩炸弹。
- 扫描版 PDF 暂不支持 OCR。

## 验证

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

该脚本执行迁移、编译、Ruff、Mypy、关键路径覆盖率、前端 ESLint/Vitest、生产构建和 Playwright。快速验证可加 `-SkipE2E -SkipCoverage`。

CI 定义在 `.github/workflows/ci.yml`，使用 MySQL 8.4 和锁定依赖运行同一组静态检查、测试和构建。

更多运行细节见 [docs/operations.md](docs/operations.md)，API 状态见 [docs/api-and-states.md](docs/api-and-states.md)，RAG 评测见 [docs/rag-evaluation.md](docs/rag-evaluation.md)。
