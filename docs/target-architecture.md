# Adaptive Tutor V2 目标架构

## 1. 产品主线

```text
创建课程
  → 上传资料
  → 抽取 Learning Objectives 与 prerequisite
  → 导入/关联 Question Bank
  → Diagnostic 建立 Student Model
  → Learning Policy 选择 Next Action
  → Tutor / Practice / Review / Repair
  → Grader 产生 Learning Evidence
  → 更新 mastery、confidence、misconception
  → 重新选择 Next Action
```

产品指标是学习决策的正确性、可解释性、证据质量和学生时间利用率；聊天、RAG、Agent Runtime 都是实现手段。

## 2. 模块化单体边界

```text
app/
  core/                 配置、数据库、安全、错误、审计、可观测性
  api/v1/               认证、课程、资料和 Adaptive Tutor API 聚合
  modules/
    auth/               注册、登录、ownership
    courses/            课程与 Course Goal/Exam Date
    materials/          文件、解析、chunk、embedding、hybrid retrieval
    adaptive/           Curriculum、Question、Evidence、Student Model、Policy、Tutor
    account/            账户与时区等基础设置
  integrations/
    document_parser/    PDF/DOCX/Markdown/TXT 解析
    embedding/          embedding 与 FAISS/BM25 适配
    llm/                结构化抽取、评分、Tutor 内容、生成 fallback
  jobs/                 durable material ingestion/indexing worker
  evaluation/           deterministic Adaptive benchmark 与 RAG benchmark
```

`app/modules/adaptive` 是正式学习领域入口；新业务不依赖旧顶层 Router、Agent、Service，也不把历史兼容表当作 Student Model。

## 3. 核心实体

- `learning_objectives`：学生应该完成的 observable/assessable ability。
- `objective_relations`：`source → target` prerequisite 关系。
- `objective_evidence`：Objective 为什么来自课程资料的 chunk provenance。
- `questions` / `question_objectives`：题库本体、来源、质量、题型和 Objective alignment。
- `learning_evidence`：每次诊断、练习、复习、assessment 或 Tutor Check 的事实记录。
- `student_objective_states`：mastery、confidence、证据统计、状态和 confidence components。
- `misconceptions`：bounded 错误模式及其生命周期。
- `learning_actions`：一次即时 policy decision，不是长期 roadmap；旧 queued snapshot 可被 `superseded`。
- `tutor_checks`：Tutor 生成的显式理解检查，提交后才进入 Evidence。

## 4. 决策边界

```text
Objective Selector
  = weakness + uncertainty + importance + goal relevance + spacing
    - recent overpractice, subject to prerequisite eligibility

Action Selector
  = misconception repair / explain / practice / verify / review

Question Selector
  = objective alignment + coverage + difficulty + history + quality
```

这些选择由确定性 Policy 完成。LLM 可以抽取 Objective、标注题目、评分主观题、解释 misconception、生成 Tutor 内容或作为生成题 fallback，但不能直接修改 durable mastery/confidence/prerequisite/schedule。

## 5. 资料与 Tutor evidence

资料链路保留 parser、heading path、page/offset、chunk、embedding、FAISS、BM25、hybrid search、RRF、reranking、neighbor expansion、provenance、trace 和 retry。Tutor 先调用课程检索；若索引暂时无命中，使用已有 Objective provenance chunk 作为受控兜底，并明确引用来源。

## 6. 前端

课程内部只有：

- **Learn**：Next Action、题目、反馈、Tutor 解释、Tutor Check。
- **Progress**：Objective 状态、mastery/confidence、Evidence、Misconception、Prerequisite。
- **Sources**：课程资料和 Question Bank 导入、关联、来源和质量。

首页也只突出跨课程 Next Action；不再呈现固定阶段路线、知识图谱画布、视频推荐或 generic Memory 管理。

## 7. 可靠性

保留认证、ownership、事务、幂等、结构化错误、审计、日志、trace、durable material job、retry、test isolation 和 CI。新 schema 变化只由 Alembic 发布；当前阶段新增 revision 为 `20260825_13_adaptive_tutor_stage2`。
