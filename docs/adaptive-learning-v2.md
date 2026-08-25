# Adaptive Learning V2 Architecture

## Product goal

A3 V2 只优化一个问题：基于学生历史学习证据，选择 `Next Best Learning Action`。

产品闭环为：

```text
Materials
   ↓
Curriculum / Learning Objectives / Prerequisite Relations
   ↓
Student Model / Evidence / Misconceptions
   ↓
Learning Policy
   ├─ Objective Selector: 学什么
   └─ Action Selector: 怎么学
   ↓
Question Bank Retrieval / Tutor / Review / Repair
   ↓
Interaction → Evaluation → Learning Evidence → State Update
```

聊天、RAG、Memory、Knowledge Graph 和 Agent Runtime 都是实现边界内的手段，不是产品核心。

## Domain model

### Curriculum

`learning_objectives` 描述 observable、assessable 的能力，例如“给定 cwnd、ssthresh 和 ACK 状态，判断 TCP 所处阶段”，而不是单纯的“TCP”。每个 Objective 至少有：

- 课程归属、标题、描述和 required ability
- importance、difficulty、status
- extraction confidence
- `objective_evidence` provenance：material、chunk、confidence

`objective_relations` 使用 `source → target` 方向表达 `source` 是 `target` 的 prerequisite。它是 Policy 的内部约束，不是面向用户的知识图谱产品。

### Student Model

`student_objective_states` 按用户、课程、Objective 保存：

- `mastery`：当前能力水平的估计
- `confidence`：支持该估计的证据置信度
- attempts、correct/incorrect、success/failure streak
- last practiced/success/failure time
- unknown、learning、weak、progressing、mastered state

`mastery=0.85, confidence=0.25` 和 `mastery=0.85, confidence=0.85` 是不同状态：前者需要验证，后者可以停止无意义刷题。

### Learning Evidence

`learning_evidence` 是学习状态的事实来源。它记录 source type、question、attempt、response、score、difficulty、grader type/version、misconception code/text 和时间。

持久化状态变化必须经过：

```text
Interaction
  → Evaluation
  → LearningEvidence
  → deterministic StudentStateUpdater
```

LLM 的 grading 或 misconception 建议是输入，不是数据库权限。服务层做 schema validation、边界限制、去重、事务和 ownership 检查。

### Misconception

misconception 以 bounded code/text 保存，例如 `confuse_cwnd_rwnd`。同一 Objective 下通过 occurrence count、confidence、first/last seen 和 resolved_at 管理生命周期。强证据且没有新的错误模式时，服务层才会 resolve active misconception。

## Curriculum extraction

资料处理保留既有 PDF/DOCX/Markdown/TXT parser、heading path、page/offset、chunk、embedding、FAISS/BM25/hybrid retrieval 和 processing job。处理完成后额外执行 Objective extraction：

1. 输入课程上下文、文档结构和代表性 chunk。
2. LLM 输出 schema-validated assessable objectives、relation 和 evidence chunk indices。
3. 服务层检查 chunk ID、去重、confidence 和 provenance。
4. Extraction 失败时 curriculum 标记 `failed/degraded`，不会用标题或正文前缀伪造 Objective。

## Learning Policy

Policy 是纯确定性服务，不依赖聊天 UI，也不允许 LLM 最终决定 durable state。

### Objective Selector

对可用候选计算可解释分数：

```text
need =
  0.44 × weakness
+ 0.24 × uncertainty
+ 0.14 × importance
+ 0.10 × goal_relevance
+ 0.08 × spacing
- recent_overpractice_penalty
- attempt_penalty
```

prerequisite 未达到 `mastery >= 0.60` 且 `confidence >= 0.35` 时，dependent Objective 被阻塞。已达到 `mastery >= 0.80`、`confidence >= 0.70` 且最近验证过的 Objective 有 explicit unnecessary-practice penalty；如果所有候选都满足该条件，Policy 返回 no action，而不是继续刷题。间隔超过 7 天时，可以重新进入 review。

### Action Selector

选定 Objective 后再选择 action：

| 状态证据 | Action |
| --- | --- |
| active misconception | `misconception_repair` |
| mastery < 0.30 | `explain` |
| mastery 高但 confidence < 0.55 | `verify_mastery` |
| mastery >= 0.65 且超过 7 天 | `review` |
| 其他可学习状态 | `practice` |

返回值包含 reason、components、blocked_by、desired difficulty、expected minutes 和 policy version，便于 UI、审计和 benchmark。

## Question Bank and practice

`questions` 保存题目本体和 provenance；`question_objectives` 允许一题覆盖多个 Objective，并记录 relevance、coverage type 和 confidence。来源区分 `user_upload`、`textbook`、`public_source`、`search` 和 `generated`。V2 的正式输入是用户上传和 generated fallback；`search` 目前只是 provenance 枚举，不构成外部题源搜索产品。

Practice 的顺序是：

```text
Student State
  → Target Objective
  → Target Ability / Desired Difficulty
  → Question Bank retrieval + deterministic ranking
  → best real question
  → generator fallback only when no suitable question exists
```

排序考虑 Objective relevance、coverage、difficulty、历史尝试、重复惩罚、来源质量和 question quality。生成题必须记录 model、prompt version、Objective、evidence chunks 和生成时间，之后经过 validator；无明确答案、脱离资料、重复或目标不匹配的题直接 reject。

## Tutor boundary

Tutor 可以在一个 Objective 内：

- 解释、换例子和回答“为什么”
- 进行 Socratic questioning
- 根据 Student Model 控制 scaffold
- 使用课程 evidence 回答
- 说明当前 action 的原因

Tutor 不可以任意写 mastery、confidence、prerequisite、review schedule、Memory CRUD 或数据库记录。Tutor service 在内部组装 Learning Context、课程证据检索、当前 action、题库视图和 Objective evidence；这些是受控 service 调用，不是对外 Tool Marketplace。

## UI and migration boundary

默认产品 UI 为 Home、Learn、Progress、Materials、Settings。用户先看到下一步学习建议；Progress 的细节才展示学习记录、错误模式和前置内容。Course Goal/Exam Date 仍可作为 Policy constraint，但不再预生成 28 天假精确 Roadmap。Roadmap、Resource、generic Memory、Knowledge Graph Canvas 和旧 Agent 主线已退出正式运行时；历史表仅作为数据迁移兼容边界，不被 V2 学习服务读取。

## Reliability

V2 继续使用 ownership、事务、幂等 attempt、结构化错误、audit、trace、异步 material job、retry 和 Alembic。新 schema 在 [`20260825_12_adaptive_learning_v2.py`](../alembic/versions/20260825_12_adaptive_learning_v2.py) 和 [`20260825_13_adaptive_tutor_stage2.py`](../alembic/versions/20260825_13_adaptive_tutor_stage2.py) 中，Adaptive 领域 service/repository 不绕过这些边界直接访问其他用户数据。V2 新增迁移只使用 Alembic；历史内部迁移表仅用于旧库基线兼容。
