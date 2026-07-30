# 运行、部署与排障

## 启动顺序

1. 启动 MySQL 8.x，并确认目标数据库存在。
2. 执行 `uv run alembic upgrade head`。该命令同时支持空库、未 stamp 的历史库和旧 Alembic 基线库。
3. 启动 FastAPI。每个实例都会安全竞争数据库 job；过期 lease 会被重新 claim。
4. 启动 Vite，或由 FastAPI 提供 `static/vue` 中的生产构建。

探针：

- `GET /health/live`：进程存活。
- `GET /health/ready`：数据库可连接，且 `alembic_version` 与当前 Alembic head 一致。
- `GET /metrics`：Prometheus 文本指标。

## 生产配置

- `APP_ENV=production`
- `ENABLE_LEGACY_ROUTES=false`
- 至少 32 字符的随机 `SECRET_KEY`
- `LLM_TIMEOUT_SECONDS=30`
- `LLM_MAX_RETRIES=2`
- `A3_MOCK_LLM=false`
- `A3_MOCK_EMBEDDING=false`
- 数据库账户仅授予目标库所需 DML/DDL 权限
- 通过 HTTPS 部署，认证 Cookie 在生产环境自动启用 `Secure`

旧 `routers/` API 只用于迁移期。生产环境不会导入或注册旧路由，除非显式设置 `ENABLE_LEGACY_ROUTES=true`。

依赖只在 `pyproject.toml` 中声明，并由 `uv.lock` 锁定。安装和执行统一使用 `uv sync --locked --dev` 与 `uv run ...`，不要再生成或维护独立的 `requirements.txt`。

## 模型提供方与密钥

- `.env` 中的 `DEEPSEEK_*` 是可选的服务端默认模型；未配置时，用户仍可在设置页保存自己的 OpenAI Chat Completions 兼容服务。
- 用户配置按账户隔离，启用后优先于服务端默认模型；停用或删除后自动回退。
- Base URL 应包含提供方要求的版本前缀，服务端会追加 `/chat/completions`。
- 用户 API Key 使用由 `SECRET_KEY` 派生的 Fernet 密钥加密入库，读取接口只返回尾号掩码，日志和前端状态不保存明文。
- `SECRET_KEY` 必须备份并在实例间保持一致。没有密钥迁移方案时直接轮换会使已保存的用户 API Key 无法解密，需让用户重新保存。

## 数据库迁移与测试隔离

- 所有环境统一执行 `uv run alembic upgrade head`，不要手工运行 `app.core.migrations` 或 `alembic stamp`。
- `/health/ready` 返回 503 且 `reason=database_schema_outdated` 时，先执行 Alembic 升级，再重启实例。
- pytest 默认使用随机 `a3_pytest_*` 数据库；可通过 `A3_TEST_DATABASE_NAME=a3_ci_test` 显式指定。
- Playwright 默认使用 `A3_E2E_DATABASE_NAME=a3_e2e_test`。
- 自动删除数据库或清理 E2E 数据前，数据库名必须包含独立的 `test`/`pytest` 标识；`task_db2` 等开发库名会被安全保护拒绝。
- Playwright 使用其下载的 Chromium，不依赖本机 Chrome。可用 `A3_PYTHON` 指向当前 Python；未设置时使用 `uv run python`。

### 生产升级、备份与恢复边界

- 升级前停止或排空写流量，并创建目标 MySQL 数据库的一致性备份。备份必须包含业务表、`alembic_version` 和 `schema_migrations`；同时保留对应版本的上传原文件和 `SECRET_KEY`。`var/rag_indexes` 可由数据库中的 chunk embedding 重建，不是数据库回滚点。
- 当前 revision 只支持向前升级，`alembic downgrade` 会有意失败。Alembic 不会自动备份业务数据，也不会把失败前已由 MySQL 提交的 DDL/DML 恢复到旧版本。
- 需要回退时，停止应用写入，将升级前备份恢复到隔离数据库并完成校验，再切换数据库；同时部署与备份 schema 匹配的应用版本、上传文件和 `SECRET_KEY`。不要用 `alembic stamp` 冒充恢复或跳过实际 schema 变更。
- 恢复后先核对两张迁移状态表和关键业务数据，再运行 `uv run alembic upgrade head`、检查 `/health/ready`，最后恢复流量。

### 新迁移约束

- `app.core.migrations.MIGRATIONS` 中新增内部版本时，必须新增对应的 Alembic revision，并在 revision 中以字符串字面量调用 `run_migrations(target_version="xxxx")`。
- 已发布 revision 的 `target_version` 不得修改。每个 revision 的固定边界保证旧 revision 在未来代码中重放时不会越级执行新迁移。
- 迁移专项测试会校验 revision 与内部版本的映射，并在空库中逐 revision 升级；新增 revision 时必须同步更新该映射测试。

## 资料任务

- 单文件最大 100MB。
- 状态为 `uploaded → parsing → indexing → ready`，失败进入 `failed`。
- `material_processing_jobs` 保存 job 状态、attempt、owner、lease、heartbeat、重试时间和错误。
- worker 原子 claim；多进程不会同时处理同一个有效 lease 的 job。
- 进程退出后，其他 worker 会在 lease 过期后接管；启动恢复也会为历史处理中资料补齐 job。
- PDF 最多 2000 页；DOCX 最大 20000 个成员、解压后最大 256MB；抽取文本最大 1200 万字符。

常用查询：

```sql
SELECT status, COUNT(*) FROM material_processing_jobs GROUP BY status;
SELECT id, material_id, status, attempts, worker_id, lease_expires_at, last_error
FROM material_processing_jobs ORDER BY id DESC LIMIT 20;
```

## 学习记忆任务

- 用户需先在设置页主动启用自动学习记忆；默认不会替用户开启。
- `LEARNING_MEMORY_WORKER_ENABLED` 控制持久化 worker，轮询、lease、最大尝试次数和提取阈值由对应 `LEARNING_MEMORY_*`、`AUTO_MEMORY_*` 与 `PROFILE_*` 环境变量配置。
- 对话后的候选记忆先写入数据库 job，再由 worker 提取和聚合；重启后可继续处理，重复消费由幂等约束保护。

## RAG 索引

- MySQL 保存规范化 chunk、倒排 term 和引用元数据。
- `var/rag_indexes/` 保存用户/课程隔离的 FAISS 文件，并使用原子替换写入。
- 第一阶段并行使用向量索引和关键词倒排召回候选；只对候选读取正文和执行融合重排。
- Agent 首先搜索 anchor，再按需读取邻接证据、资料目录或完整章节。
- 删除或重建资料后会重建对应课程索引；旧资料在首次查询时自动补齐倒排索引。

不要把 `var/rag_indexes` 当成唯一数据源。它可以由 MySQL 中的 chunk embedding 重建；备份优先保证数据库和上传文件。

## Human-in-the-loop

破坏性工具由 `HumanInTheLoopMiddleware` 在工具执行前中断。检查点持久化在 MySQL LangGraph 表中，`agent_action_requests` 只承担审计、幂等、过期和前端确认状态。批准或拒绝后使用 `Command(resume=...)` 恢复原 graph；不要直接从确认接口绕过 graph 修改业务数据。

## 可观测性

应用日志为一行一个 JSON，包含 UTC 时间、级别、logger、`request_id` 和消息；HTTP 完成日志还包含 method、path、status 和耗时。客户端可传 `X-Request-ID`，服务端会在响应中回传。

主要指标：

- `a3_http_requests_total`、`a3_http_request_duration_seconds`
- `a3_db_pool_in_use`、`a3_db_pool_capacity`、`a3_db_transaction_duration_seconds`
- `a3_llm_requests_total`、`a3_llm_request_duration_seconds`、`a3_llm_tokens_total`
- `a3_agent_tool_calls_total`、`a3_agent_tool_duration_seconds`
- `a3_material_jobs`、`a3_material_job_attempts_total`、`a3_material_job_duration_seconds`

指标为进程内聚合。多 worker 部署应逐实例抓取，或接入统一遥测后端。

## 常见排障

1. 查看 `/health/ready` 和数据库连接参数。
2. 检查 `alembic_version` 是否为当前 head；历史 `schema_migrations` 由 Alembic 基线桥接自动维护。
3. 上传失败时查看资料 `processing_status/processing_error` 和 job 的 `last_error`。
4. 聊天中断时按响应的 `X-Request-ID` 检索 JSON 日志，再检查 `agent_runs`、`agent_tool_calls` 和 LangGraph checkpoint 表。
5. RAG 结果异常时检查 `course_material_search_terms`、`var/rag_indexes`，然后运行 `scripts/reindex_user_materials.py`。
6. 外部资源不足时检查 Provider warning；YouTube/Tavily 未配置不会阻断课程主流程。

## 验收

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

完整验收包括 Alembic 迁移、编译、Ruff、Mypy、关键路径覆盖率、ESLint、Vitest、生产构建和 Playwright。CI 使用相同的静态检查和测试门槛，并在 E2E 失败时保存 trace、截图和服务日志。
