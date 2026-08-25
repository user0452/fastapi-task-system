# 运行、部署与排障

## 启动顺序

1. 启动 MySQL 8.x，并确认目标数据库存在。
2. 执行 `uv run alembic upgrade head`。
3. 启动 FastAPI：`uv run python -m uvicorn main:app --reload --host 127.0.0.1 --port 8010`。
4. 启动前端：设置 `VITE_API_TARGET=http://127.0.0.1:8010` 后运行 `npm run dev`，或使用 `npm run build` 后由 FastAPI 提供 `static/vue`。

探针：`GET /health/live`、`GET /health/ready`、`GET /metrics`。

## 生产配置

- `APP_ENV=production`
- 至少 32 字符的随机 `SECRET_KEY`
- `A3_MOCK_LLM=false`、`A3_MOCK_EMBEDDING=false`
- 配置数据库和可选 LLM provider；密钥不进入代码、日志或 benchmark fixture。
- 通过 HTTPS 部署，认证 Cookie 在生产环境启用 `Secure`。

正式运行时不注册已退役的 Roadmap、Resource、Memory、旧 Agent 或 legacy route；不要再配置已经移除的开关。

## 数据库迁移

- 所有环境统一使用 `uv run alembic upgrade head`，不要手工调用历史内部迁移函数或用 `alembic stamp` 跳过实际变更。
- 当前 V2 新增 revision 为 `20260825_13_adaptive_tutor_stage2`，包含 question import、题目字段、grader、Tutor Check、confidence components 和 Evidence 幂等约束。
- 迁移只支持向前升级；回退应恢复升级前的一致性备份，再部署匹配版本，不把 downgrade 当作业务数据恢复。
- `/health/ready` 返回 `database_schema_outdated` 时先升级 schema，再重启应用。
- pytest 使用随机 `a3_pytest_*` 库，Playwright 使用 `a3_e2e_test`；清理数据库前必须验证名称包含测试标识。

## 资料处理与 RAG

- 支持 PDF、DOCX、Markdown 和 TXT；状态为 `uploaded → parsing → indexing → ready`，失败进入 `failed`。
- 资料 job 使用事务、lease、heartbeat、retry 和 ownership；FAISS/BM25/hybrid 索引可由 MySQL chunk/evidence provenance 重建。
- RAG 只作为 Evidence Retrieval Layer：为 Objective provenance、Tutor 课程引用和生成题 fallback 提供证据，不直接决定 mastery 或 Next Action。
- 索引问题先检查 `course_material_search_terms`、`var/rag_indexes` 和 material job 日志，再运行 `scripts/reindex_user_materials.py`。

## 学习闭环排障

1. 检查 `GET /api/v1/adaptive/courses/{id}/overview` 是否有 Curriculum 和 Next Action。
2. 检查 Sources 中题库 `matched/unmatched/needs_review` 和 import batch 状态。
3. 检查 Progress 的 Evidence、grader version、misconception 和 confidence components。
4. 若 action 似乎过期，确认题库/诊断/手动 tagging 后旧 queued action 已变为 `superseded`，然后重新读取 overview。
5. Tutor 无 RAG 命中时应回退到 Objective provenance；如果仍无引用，检查资料是否 ready、Objective 是否有 evidence chunk。

## 质量门禁

```powershell
uv run pytest -q
uv run ruff check app tests scripts alembic packaging/competition_launcher.py
uv run mypy app
uv run python -m compileall -q app tests scripts alembic main.py
uv run python scripts/evaluate_adaptive.py --check --output docs/benchmark-report.md
Set-Location frontend
npm run lint
npm run test:run
npm run build
npm run test:e2e
```

CI 和交付前验收以这些命令为准；报告中的数量必须来自最近一次实际运行。
