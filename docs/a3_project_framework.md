# A3 Adaptive Tutor 项目框架

## 产品命题

A3 不再把“AI 学习工作台”作为产品。它维护有证据的 Student Model，并持续选择：

```text
课程资料 → Learning Objectives → Student Model → Learning Policy
         → Next Action → Tutor/Practice → Evidence → State Update
```

## 五个核心模块

1. **Curriculum Model**：从资料抽取可观察、可评估的 Learning Objective，保存 prerequisite 和 provenance。
2. **Question Bank**：接收真实题库，解析、去重、自动标注、校验和来源追踪；一题可覆盖多个 Objective。
3. **Student Model**：按课程隔离 mastery、confidence、attempt、错误模式和 confidence components。
4. **Learning Policy**：Objective Selector 先决定学什么，Action Selector 再决定怎么学；确定性 baseline 是最终决策权威。
5. **Tutor**：用课程 evidence 解释、举例、拆步骤和做 Tutor Check；LLM 不直接写 durable state。

## 工程边界

- `app/modules/adaptive` 是学习业务核心。
- `app/modules/materials` 和 `app/integrations/document_parser` 提供资料解析与 evidence retrieval layer。
- `app/integrations/llm` 只提供结构化抽取、评分、Tutor 内容和生成 fallback。
- `alembic/versions` 是新 schema 变更的唯一正式入口。
- `frontend/src/features/adaptive` 只保留 Learn、Progress、Sources 三个课程区域。
- `app/evaluation/adaptive.py` 和 `scripts/evaluate_adaptive.py` 提供冻结 benchmark、baselines 和 ablations。

## 不属于产品核心

聊天 UI、RAG、LangGraph、通用 Memory、知识图谱画布、长期 Roadmap、资源推荐和 Multi-Agent 拆分都不是产品目标；只有能改善 Next Best Learning Action 的实现才有资格进入后续范围。
