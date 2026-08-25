# Adaptive Tutor API 与状态契约

## 正式产品 API

所有接口都通过当前用户的 ownership 校验，统一返回 `{code, message, data}`。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/adaptive/courses/{course_id}/overview` | Curriculum 摘要、Student Model 计数和 Next Action |
| `GET` | `/api/v1/adaptive/courses/{course_id}/next-action` | 读取或重新生成下一动作 |
| `GET` | `/api/v1/adaptive/courses/{course_id}/progress` | Objective 状态、Evidence、Misconception、Prerequisite |
| `GET` | `/api/v1/adaptive/courses/{course_id}/sources` | 资料、题库、导入批次和 provenance 计数 |
| `GET` | `/api/v1/adaptive/courses/{course_id}/objectives/{objective_id}` | 单个 Objective 的状态详情 |
| `POST` | `/api/v1/adaptive/courses/{course_id}/curriculum/rebuild` | 从已就绪资料重新提取 Curriculum |
| `POST` | `/api/v1/adaptive/courses/{course_id}/questions` | 添加一批题目并自动/显式关联 Objective |
| `POST` | `/api/v1/adaptive/courses/{course_id}/question-bank/import` | 预览 JSON/JSONL/Markdown/TXT 题库 |
| `POST` | `/api/v1/adaptive/courses/{course_id}/question-bank/import/commit` | 幂等确认导入题库 |
| `PATCH` | `/api/v1/adaptive/courses/{course_id}/questions/{question_id}/objectives` | 手动修正题目 Objective 关联 |
| `POST` | `/api/v1/adaptive/courses/{course_id}/diagnostic` | 选择最少诊断题 |
| `POST` | `/api/v1/adaptive/courses/{course_id}/diagnostic/submit` | 评分并写入 diagnostic Evidence |
| `POST` | `/api/v1/adaptive/actions/{action_id}/start` | 开始当前 Learning Action |
| `POST` | `/api/v1/adaptive/actions/{action_id}/submit` | 评分练习、写入 practice Evidence、重新决策 |
| `POST` | `/api/v1/adaptive/courses/{course_id}/tutor` | 基于 Student Model 和课程 evidence 的 Tutor 交互 |
| `POST` | `/api/v1/adaptive/courses/{course_id}/tutor/checks/{check_id}/submit` | 唯一的 Tutor Check Evidence 写入入口 |

## 学习状态生命周期

```text
Question/Interaction
  → Grader / Evaluation
  → LearningEvidence
  → BKT-inspired StudentStateUpdater
  → StudentObjectiveState
  → Learning Policy
  → Next Learning Action
```

### Curriculum

`learning_objectives` 描述 observable、assessable 的能力；`objective_relations` 的 `source → target` 表示 source 是 target 的 prerequisite；`objective_evidence` 保存 material/chunk provenance。抽取失败时状态为 `failed/degraded`，不会从标题或正文开头静默制造目标。

### Student Model

`student_objective_states` 以 `(user_id, course_id, objective_id)` 隔离，保存 `mastery`、`confidence`、attempt/correct/incorrect、success/failure streak、最近练习时间和状态。`mastery` 与 `confidence` 独立更新；置信度由数量、一致性、题型多样性、评分质量和近期性组成。

### Evidence

`learning_evidence` 必须带 `source_type`（`diagnostic`、`practice`、`review`、`assessment`、`tutor_check`）、题目/attempt、response、score、difficulty、grader version、misconception 和 idempotency key。相同事实重放不会创建第二条 Evidence。

### Misconception

错误模式保存 bounded `code`/`description`、confidence、occurrence count、first/last seen、success/failure count 和 `resolved_at`。LLM 只能提出结构化候选，服务层负责合法性、去重和生命周期更新。

### Learning Action

Action 是一次即时决策，不是预生成长期计划。状态为 `queued → in_progress → completed`；当题库、诊断或题目关联改变 policy 输入时，未开始的旧 action 进入 `superseded`，随后重新计算。解释动作不接受普通文本写入 Evidence，必须通过 Tutor Check。

## Question Bank

支持 `multiple_choice`、`true_false`、`short_answer`、`calculation`、`scenario`、`essay` 六种题型。一题可以通过 `question_objectives` 覆盖多个 Objective。题目来源和生成上下文分别保存；生成题必须带 model、prompt version、Objective 和 evidence chunks，并通过 validator。

## Tutor 边界

Tutor 可以解释、换例子、提示、拆步骤、进行 Socratic questioning 和解释推荐原因；它不能直接 CRUD Student Model、修改 prerequisite、维护 schedule 或写通用 Memory。普通 Tutor 响应明确返回 `evidence_written=false`；只有 Tutor Check 提交经过 grader 后才写入 Evidence。

## 迁移边界

新 schema 只走 Alembic。当前 V2 新增 revision 是 `20260825_13_adaptive_tutor_stage2`，支持 question import、题目扩展字段、grader provenance、Tutor Check、confidence components 和 Evidence 幂等约束。历史数据库表只作为旧库兼容边界，不属于正式 V2 API。
