# A3 `feature/a3-competition` 安全合并验证报告

验收日期：2026-07-16

分支：`feature/a3-competition`

目标基线：`main`

## 1. 实现提交

| SHA | 提交 | 主要范围 |
| --- | --- | --- |
| `0c2ff72d7699edbe51a8f5c535cb55b72339c74d` | `fix: harden learning material and agent invariants` | 题目/评估安全、诊断状态机、资料与索引一致性、Agent 生命周期、认证/课程/用户隔离、时区、RAG 和低风险清理 |
| `3947e9afa582067e9f6d4247e2c22bb94685c6bb` | `fix: isolate user state and streaming requests` | Pinia 账户隔离、课程加载竞态、流式取消、消息存在性检查、生产前端构建 |
| `593e43d555fc83e56f941c4502b263ec54f44ccf` | `ci: isolate test databases and run cross-platform e2e` | Alembic 统一入口、测试库保护、readiness revision、跨平台 Playwright、CI E2E 与失败产物 |
| `5e9a9f73524274bdc5a06b5a5b575b5ef9fd6c47` | `chore: remove stale dependency manifest and refresh docs` | 删除并行依赖清单，更新运行、迁移和验收文档 |

## 2. 九阶段验收结论

| 阶段 | 结果 | 关键证据 |
| --- | --- | --- |
| 1. 题目与评估安全 | 通过 | 公共题目 DTO 不含 `answer`、`reference_answer` 或完整 `quiz_json`；完整提交、重复 ID、越权 ID、LLM 明细完整性和服务端重算均有测试 |
| 2. 诊断状态机与幂等 | 通过 | `evaluating → evaluated → planning → completed`；评估/计划故障可重试；重复与并发提交不重复更新掌握度或计划 |
| 3. 资料与索引一致性 | 通过 | 上传前所有权校验、数据库失败回滚磁盘、可恢复删除、后台任务失效、MySQL advisory lock、FAISS generation 防旧任务覆盖 |
| 4. Agent 生命周期 | 通过 | `client_request_id` 幂等、稳定工具幂等键、断连取消、`resuming` lease 恢复、危险动作幂等、checkpoint 完成清理和延迟 GC |
| 5. 认证与用户隔离 | 通过 | Argon2id、legacy bcrypt 自动迁移、失败登录限流、可信代理 IP、课程状态命令、单 current 课程唯一约束、跨用户资源/会话/action/checkpoint 拒绝 |
| 6. 时区、RAG、数据质量 | 通过 | 用户 IANA 时区、DB 会话 UTC、用户本地“今天”、向量/关键词/知识点独立配额、知识点主动召回、查询 embedding 单次计算、orphan 过滤 |
| 7. 前端状态与流式竞态 | 通过 | 认证失效/退出/换号清空用户状态；请求版本与 AbortController 隔离旧流；reader 取消与释放；刷新并发课程加载合并 |
| 8. 迁移、CI、E2E | 通过 | 空库与历史库均只执行 `alembic upgrade head`；测试库随机/显式 test 名；E2E 清理拒绝非测试库；bundled Chromium 7/7；GitHub Actions 绿色 |
| 9. 低风险清理 | 通过 | 源码乱码扫描 0；公共字符串先 strip、必填空白拒绝；`pyproject.toml`/`uv.lock` 单一依赖真源；精确外链域名；外部时间 UTC；JSON 可控错误；静态绝对路径；embedding 首载锁 |

## 3. 数据库迁移

- 当前 Alembic head：`20260716_02`。
- 开发库从旧 `20260716_01` 自动升级到 `20260716_02`。
- 全新临时库：仅运行 `python -m alembic upgrade head`，创建完整历史结构、`schema_migrations` 和 `alembic_version`。
- 历史临时库：先构造到 legacy `0017` 并 stamp 旧基线，再运行 `alembic upgrade head`，自动补齐 `0018`、`0019` 和新 head。
- `/health/ready` 在数据库 revision 缺失或过期时返回 503；当前 head 返回 200。
- pytest 使用随机 `a3_pytest_*` 数据库；CI 和 E2E 分别使用 `a3_ci_test`、`a3_e2e_test`。删除保护明确拒绝 `task_db2`。

## 4. 最终自动化结果

统一命令：

```powershell
$env:A3_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
powershell -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

真实结果：

- Alembic：成功升级并保持 `20260716_02 (head)`。
- Python 编译：通过。
- Ruff：通过。
- Mypy：`Success: no issues found in 85 source files`。
- 后端 pytest：`145 passed in 29.82s`。
- 关键模块覆盖率：`78.33%`，高于 `70%` 门槛。
- 前端 ESLint：通过。
- Vitest：`9` 个测试文件、`27 passed`。
- Vite：`1812 modules transformed`，生产构建成功。
- Playwright：bundled Chromium，`7 passed (49.1s)`。
- `git diff --check`：通过。
- 源码乱码模式扫描：`0`。

远端 GitHub Actions：

- Workflow：`CI`
- Run ID：[`29500887944`](https://github.com/user0452/fastapi-task-system/actions/runs/29500887944)
- 验证 SHA：`5e9a9f73524274bdc5a06b5a5b575b5ef9fd6c47`
- Event：`push`
- Job：`verify`
- 结论：`success`
- 成功步骤：MySQL 8.4、锁定依赖、Alembic、Ruff/Mypy、后端测试与覆盖率、前端 ESLint/Vitest/构建、Playwright Chromium 和浏览器 E2E。

阶段 8 迁移专项命令：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_fresh_database_migrations.py `
  tests/test_migrations.py `
  tests/test_schema_readiness.py `
  tests/test_ci_configuration.py -q
```

结果：`12 passed`。其中分别实际创建并删除了全新测试库和历史升级测试库。

阶段 9 清理专项命令：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_low_risk_cleanup.py `
  tests/test_external_resource_engine_v1.py `
  tests/test_account_settings.py -q
```

结果：`18 passed`。

## 5. 浏览器 E2E 场景

1. 注册、创建课程、上传资料、后台处理、知识点与依赖图生成，并在刷新后恢复。
2. 三门课程的资料、助手和聊天历史隔离。
3. RAG 内部来源与外部网页来源气泡、展开内容和刷新恢复。
4. 聊天内练习、提交、掌握度、错题和计划重排。
5. 面板草稿保留、旧地址重定向和危险操作确认。
6. 390×844 移动端课程导航、聊天和面板可用。
7. 诊断提交、计划生成、今日学习开始与提交闭环。

Playwright 配置不使用本机 Chrome channel，也不硬编码 Windows `.venv\Scripts\python.exe`。失败时 CI 上传 `test-results`（trace/截图）、HTML 报告和前后端服务日志。

## 6. 启动验证

Playwright 验收实际启动了：

- FastAPI/Uvicorn：`127.0.0.1:8011`；
- Vite：`127.0.0.1:5176`；
- `/health/ready`：HTTP 200；
- 完整 API、后台资料 worker、FAISS、流式聊天与浏览器交互均成功运行。

静态目录由项目根目录绝对路径解析，不再依赖启动进程的当前工作目录。

## 7. 限制与人工事项

1. E2E 使用 Mock LLM/Mock Embedding，外部 Bilibili、YouTube、Tavily 的实时可用性会受网络、配额和密钥影响；这些 Provider 失败时已验证为可控降级，不阻断核心学习流程。
2. 历史数据库中旧时间列曾混用本地时间和 UTC，无法在没有业务语义映射的情况下安全批量改写。本次保证新连接、新写入和新时区计算使用 UTC；上线前建议对真实历史数据抽样审计。
3. `routers/`、`agents/`、`services/` 的 legacy 入口仍被兼容模式和 E2E 危险操作测试引用，因此未误删；生产继续保持 `ENABLE_LEGACY_ROUTES=false`。
4. 统一验收启动外层 PowerShell 时，Conda 自动激活在中文用户路径上输出一次 GBK 编码警告；脚本未中止且最终退出码为 0。项目命令均通过显式 `A3_PYTHON` 使用仓库 Python 3.13 环境。

## 8. 合并前检查

- [x] 分支不是 `main`，未修改 `main`。
- [x] 所有本地代码、迁移、测试、构建和 E2E 门槛通过。
- [x] 用户原有未跟踪文件未删除、未覆盖、未纳入提交。
- [x] 实现提交已按后端、前端、CI 三个逻辑范围拆分。
- [x] push 当前分支并确认 GitHub Actions `verify` 成功。
- [ ] PR 审核时重点检查真实生产数据库备份、历史时间数据和生产 secrets。

## 9. 2026-07-18 课程级个人学习操作系统升级

本轮在既有安全基线上完成五个阶段实现提交：

| SHA | 提交 | 主要范围 |
| --- | --- | --- |
| `46fddac` | `feat: add course-scoped session navigation` | 多会话创建、切换、归档、URL 恢复与悬浮会话轨道 |
| `1c0357a` | `feat: add adaptive course roadmaps` | 四阶段长期路线、真实任务关联、失败重试与幂等自适应调整 |
| `1777a66` | `feat: add evidence-backed knowledge graph` | 可交互知识图谱、关系证据、资料摘录与可访问列表回退 |
| `dbfdb89` | `feat: unify agent tool execution` | 统一工具注册、策略守卫、受限执行与回答依据摘要 |
| `d6a3bb7` | `feat: make learning memory transparent` | 课程记忆来源、编辑、暂停、恢复、软删除与类型开关 |

最终统一命令：

```powershell
$env:A3_PYTHON = (Resolve-Path .\.venv\Scripts\python.exe).Path
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

本机实测结果：

- Alembic：升级并保持 `20260718_06 (head)`；
- Python 编译、Ruff、前端 ESLint：通过；
- Mypy：`Success: no issues found in 92 source files`；
- 后端 pytest：`197 passed in 44.83s`，总覆盖率 `83.13%`；
- Vitest：16 个测试文件、`46 passed`；
- Vite：`2410 modules transformed`，生产构建成功；
- Playwright：bundled Chromium，`9 passed (1.0m)`；
- 统一脚本最终输出：`All verification checks passed.`。

端到端流程覆盖注册与资料处理、三课程隔离、内部/外部来源、知识图谱、路线调整、回答依据、多会话恢复与归档、记忆完整生命周期、练习闭环和 390×844 移动端九面板。

本轮验证边界：

1. 浏览器验收使用 Mock LLM/Mock Embedding，真实 LLM、Embedding、Tavily 和 YouTube 调用仍需要外部配置与网络可用性。
2. MCP 与图片工具目前完成策略和配置状态接口；MCP Server 与外部图片生成服务的真实执行适配器尚未实现，已配置时返回 `configured_not_implemented`，未用模拟成功掩盖该边界。
3. 受限 Python 执行器继续保留超时、内存和输出限制，并明确标记为实验性的应用级隔离；它不是容器、cgroup、seccomp 或独立虚拟机隔离，不允许面向不可信公网用户开放。
4. 上述结果是本地分支验证；本轮推送后的远端 GitHub Actions 结果应单独记录，不在本节预先宣称成功。
