# Adaptive Tutor V2 实现状态

更新时间：2026-08-25

## 已完成

- Curriculum 以 Learning Objective 为核心，保存 importance、difficulty、extraction confidence、prerequisite relation 和 material/chunk provenance。
- Objective extraction 使用结构化 schema、证据 chunk 校验、去重和失败状态；不会静默回退为标题/正文摘要。
- Question Bank 支持 JSON、JSONL、Markdown、TXT 预览/确认导入、幂等批次、来源记录、六种题型、自动/手动 Objective tagging 和质量状态。
- Student Model 使用 `StudentObjectiveState`，显式分离 mastery/confidence，并保存五个 confidence components。
- Learning Evidence 是状态变化唯一事实来源；Grader 输出经过 schema/service 边界后才能更新 Student Model。
- Misconception 有 code、bounded text、confidence、occurrence、success/failure 和 resolved 生命周期。
- Learning Policy 拆分 Objective Selector 与 Action Selector，包含 prerequisite gating、spacing、goal relevance、uncertainty 和 unnecessary-practice penalty。
- Practice retrieval-first；高质量真实题存在时不会调用 generator，生成 fallback 经过 grounded validator。
- Diagnostic 使用 importance、uncertainty、coverage、prerequisite hub 和 diversity 选择题目。
- Tutor 已收敛为真实课程 endpoint：带 Student Model、当前 action、misconception、prerequisite 和 RAG/provenance citations；普通 Tutor 不写 Evidence，Tutor Check 才能写入。
- 前端正式导航为 Home、Learn、Progress、Materials、Settings；没有 Roadmap、知识图谱画布、资源推荐、generic Memory、日志或开发者控制台页面。
- 固定 Mini Course seed、Adaptive Benchmark、baseline/ablation、闭环 E2E、迁移测试和文档已加入仓库。

## 已退出正式主线

- Roadmap、固定阶段计划、Study Plan/Today schedule 作为课程核心。
- Resource/Bilibili/YouTube recommendation 及交互系统。
- Generic Memory CRUD、跨课程学习记忆聚合和 Memory worker。
- Knowledge Graph Canvas、图布局和筛选器。
- 旧 Agent/Router/Service 顶层兼容层、旧课程聊天工具注册和通用工具 marketplace。
- 旧 Quiz/Knowledge Point 学习闭环；V2 只消费 Learning Objective、Question、Evidence 和 Student State。

历史库中的旧表仍由基础迁移兼容边界识别，但正式 V2 service/router 不读写它们；新字段与业务表变化只通过 Alembic revision 发布。

## 仍需真实环境验证的内容

- 外部 LLM provider 的主观评分、Objective extraction 和生成题质量。
- 真实学生纵向学习效果和 calibration，不由当前 fixture benchmark 证明。
- 公共题源搜索的版权许可与保存策略；当前主流程以用户上传题库为优先。
