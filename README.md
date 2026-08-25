# A3 Adaptive Tutor

> A learning system that maintains an evidence-backed student model and continuously selects the next best learning action.

A3 是一个轻量、垂直、可评测的自适应课程 Tutor：用户上传课程资料和题库后，系统建立可评估的 Learning Objectives 及其前置关系；每次诊断、练习、复习或 Tutor check 都先生成 Learning Evidence，再更新 Student Model，最后重新决定“下一步学什么、应该怎么学”。

系统的价值不是聊天本身，而是持续回答一个可验证的问题：

> 基于目前的学习证据，这个学生下一步最值得完成什么动作？

## 核心闭环

```text
课程资料 ──> Curriculum / Learning Objectives
题库     ──> 可评估 Questions + Objective Alignment
                         │
                         ▼
              Student Model
       mastery + confidence + misconceptions
                         │
                         ▼
              Learning Policy
        Objective Selector + Action Selector
                         │
                         ▼
       Next Learning Action / Tutor / Practice
                         │
                         ▼
       Evaluation ──> Learning Evidence ──> State Update
```

核心领域只有五块：

- `Curriculum`：描述学生应该能够完成什么，而不是教材出现了什么词。
- `Student Model`：分离 `mastery` 与 `confidence`，记录掌握状态和错误模式。
- `Learning Evidence`：所有持久状态变化的事实来源，拒绝 LLM 直接写 mastery。
- `Question Bank`：真实题库优先，生成题只在没有合适题时兜底。
- `Learning Policy`：先选 Objective，再选 Action；策略为确定性、可解释、可测试的 baseline。

Tutor 是教学交互层，负责解释、举例、提问、反馈和 scaffold。它不负责路线、schedule、mastery 或数据库 CRUD。RAG 保留为 evidence retrieval layer，为 Curriculum provenance、Tutor 解释和题目生成 fallback 提供课程资料证据。

## 产品界面

每门课程主界面只有三个区域：

- `Learn`：展示 Next Action，完成讲解、题目、反馈和重试。
- `Home`：一眼看到当前最值得完成的学习步骤与课程入口。
- `Learn`：完成一项学习任务、练习并获得简短 Tutor 帮助。
- `Progress`：用已掌握、学习中、薄弱和未验证解释学习状态；细节中可查看学习记录与前置内容。
- `Materials`：上传课程资料和题库，查看处理进度。

主页以跨课程 `Next Best Learning Action` 为入口，不再把长期 Roadmap、知识图谱或聊天窗口作为产品主叙事。

## 目录

```text
app/modules/adaptive/          Curriculum、Question、Evidence、Student Model、Policy
app/integrations/llm/          Objective extraction 和 LLM 结构化输出
app/modules/materials/         资料解析、分块、索引和课程 provenance
app/evaluation/adaptive.py     冻结 fixture 的 Adaptive Learning Benchmark
frontend/src/features/adaptive Home / Learn / Progress / Materials
alembic/versions/               V2 schema migration；早期 revision 保留历史库 bridge
docs/adaptive-learning-v2.md    领域模型和运行边界
docs/evaluation.md               benchmark、baseline、指标和限制
docs/benchmark-report.md         最近一次真实运行结果
```

旧 Roadmap、Resource、generic Memory、Knowledge Graph UI、旧 Agent/Router/Service 主线已从正式运行时和前端移除。历史数据库表不再作为 V2 Student Model、Curriculum 或 Policy 状态；资料 RAG 仅为兼容已有 chunk provenance 读取必要的旧索引元数据。当前正式 API 只有 Adaptive Tutor 学习闭环。

## 启动

要求 Python 3.13、Node.js 20+、MySQL 8.x 和 `uv`。

```powershell
Copy-Item .env.example .env
# 在 .env 中设置数据库连接、SECRET_KEY 和可选的 LLM 配置
uv sync --locked --dev
Set-Location frontend
npm ci
Set-Location ..
uv run alembic upgrade head
```

启动后端和前端：

```powershell
uv run python -m uvicorn main:app --reload --host 127.0.0.1 --port 8010

Set-Location frontend
$env:VITE_API_TARGET='http://127.0.0.1:8010'
npm run dev -- --host 127.0.0.1 --port 5175
```

打开 `http://127.0.0.1:5175/#/home`。健康检查为 `/health/live` 和 `/health/ready`。

离线演示可使用：

```powershell
$env:A3_MOCK_LLM='true'
$env:A3_MOCK_EMBEDDING='true'
uv run python scripts/seed_demo.py
```

## 评测和验证

运行 Adaptive Benchmark：

```powershell
uv run python scripts/evaluate_adaptive.py --check
uv run python scripts/evaluate_adaptive.py --output docs/benchmark-report.md
```

该 benchmark 冻结 Curriculum、学生状态、prerequisite、misconception 和题库 fixture，并比较：

- `Baseline A`：只选择 mastery 最低的 Objective。
- `Baseline B`：固定随机种子下的 random/simple 策略。
- `Baseline C`：mastery + prerequisite 的简化策略。
- `V2`：prerequisite-aware Objective Selector + Action Selector + retrieval-first Question Selector。

报告同时输出固定 case 数、失败类别、Question/Grader/State Sequence 检查与 ablation；它是可复现的 simulation benchmark，不是对真实学生学习效果的声明。

完整本地检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_all.ps1
```

前端单独检查：

```powershell
Set-Location frontend
npm run lint
npm run test:run
npm run build
npx playwright install chromium
npm run test:e2e
```

底层 RAG 仍有独立评测，见 [docs/rag-evaluation.md](docs/rag-evaluation.md)；Adaptive 评测定义见 [docs/evaluation.md](docs/evaluation.md)。

## 工程边界

- 所有部署通过 Alembic CLI 升级 schema；早期 Alembic revision 为兼容历史数据库会调用内部 migration bridge，V2 新增 revision 不再依赖它。资料处理保留事务、异步 job、重试、审计、trace 和 ownership 检查。
- LLM 只负责抽取、标注、主观评分、错误解释、Tutor 交互和生成 fallback；结构化输出必须经过 schema、validator 和 service。
- 课程学习状态只通过 `Interaction → Evaluation → Evidence → Student Model Update` 变化。
- Objective extraction 失败时 curriculum 标记为 degraded/failed，不使用标题或正文前缀静默伪造学习目标。
- 生成题必须记录 model、prompt version、Objective 和 evidence chunks，并经过题目 validator；真实题库永远优先。

更多实现细节见：[Adaptive architecture](docs/adaptive-learning-v2.md)、[Evaluation](docs/evaluation.md)、[Operations](docs/operations.md) 和 [API/state notes](docs/api-and-states.md)。
