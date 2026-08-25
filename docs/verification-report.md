# Adaptive Tutor V2 验收报告

日期：2026-08-25

## 产品闭环

Playwright 主流程已实际跑通：

```text
注册/登录
 → 创建课程
 → 上传课程资料并等待 ready
 → 生成 Curriculum / Learning Objectives
 → 导入 JSON 题库并自动关联 Objective
 → Diagnostic
 → 写入 diagnostic Evidence
 → Learning Policy 生成 retrieval-first Next Action
 → 提交真实题 Practice
 → Grader / Evidence / Student State Update
 → Tutor 课程引用交互
 → Tutor Check 写入 Evidence
 → Progress / Sources 展示更新
```

同一套 E2E 还覆盖旧书签入口只重定向到核心区域、移动端无横向溢出和四视口截图。

## 实际结果

- 后端：`uv run pytest -q`，205 passed；coverage gate 77.97%，门槛 70%。
- 前端：Vitest 20 tests passed，ESLint 通过，production build 通过。
- E2E：3/3 Chromium scenarios passed。
- Adaptive Benchmark：50 policy cases；V2 objective/action accuracy 100%；prerequisite violation 0%；unnecessary practice 0%。
- Question benchmark：20 cases；retrieval match 100%；高质量真实题 generation calls 0；invalid 0%。
- Grader/state/curriculum fixtures：20/5/10 cases，全部通过。
- Alembic revision 13 和 fresh/current migration tests 已纳入后端测试。
- 静态交付检查：Ruff、Mypy（82 source files）、compileall 和 `competition_launcher.py --check` 均通过。

## Final hardening review

- 删除未被正式主线引用的通用课程 Chat responder、MySQL checkpointer、旧 Knowledge Point extractor 与 audit-log 页面/API。
- 开放题确定性兜底从关键词重合改为显式 rubric criterion 评分；会保存缺失能力点，供 Evidence、Student Model 和 Tutor 反馈使用。
- 增加 mastery confidence 抗偶然性测试：连续正确会提升置信度；重复同题的单一证据不会获得与多类型题相同的置信度。
- 验证 generated question 只在题库无合格匹配时作为兜底，并通过验证后带 provenance 保存；高质量真实题命中时不会调用生成器。

## 主线清理

正式 API 和前端不再注册 Roadmap、Resource、Memory、Knowledge Graph、旧 Agent 工具或旧顶层 Router/Service。历史数据表只在迁移兼容层识别；新功能只写 V2 Curriculum、Question、Evidence、Student State 和 Learning Action。

## 限制

- 以上 Adaptive 数字来自可重复 fixture/simulation，不是现实学生实验。
- 外部 LLM 的 subject grading、misconception interpretation、Objective extraction 和 question generation 仍需 live-provider 评测。
- 外部公开题源尚未作为主流程依赖；题库上传是当前优先路径。
