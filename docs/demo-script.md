# Adaptive Tutor 产品演示脚本

## 演示前准备

1. 启动 MySQL、后端和前端，并执行 `uv run alembic upgrade head`。
2. 使用 `A3_MOCK_LLM=true`、`A3_MOCK_EMBEDDING=true` 保证本地演示可重复。
3. 执行 `uv run python scripts/seed_demo.py --username-prefix a3_demo --reset`。
4. 登录脚本输出的账号，密码为 `A3Demo123!`。

## 0:00–0:30 先看 Next Action

打开 `计算机网络 Mini Course` 的 Learn 页面。

话术：

> 这个系统的中心不是聊天，而是下一步学习决策。它先看课程 Objective、前置关系和学生证据，再决定当前最值得学什么，以及是讲解、练习、验证、复习还是错误模式修复。

验收点：页面第一屏展示 Next Action、原因、预计时间和当前目标，不展示固定 28 天路线。

## 0:30–1:00 看 Student Model

切到 Progress，打开“拥塞控制”或“慢启动”目标。

话术：

> mastery 表示当前表现估计，confidence 表示证据够不够。两者分离后，0.85 mastery/0.25 confidence 会触发验证，而不是直接标记掌握。

验收点：Objective 列表显示 mastery、confidence、状态、最近 Evidence、Misconception 和 Prerequisites。

## 1:00–1:35 演示真实题库优先

切到 Sources，展示课程资料和题库来源，确认题目带有 `textbook`/`user_upload` provenance 与 Objective 关联。

话术：

> Practice 先在真实题库中按目标、题型覆盖、难度、历史尝试和来源质量检索。只有没有合适题时，才调用 evidence-grounded generator，并经过 validator；有合适真实题时生成调用为 0。

验收点：Sources 显示题目数量、已关联/未关联、来源和导入批次；重新导入相同 idempotency key 不重复创建。

## 1:35–2:05 演示 Tutor 不直接写状态

回到 Learn，点击 Tutor 的“换一个例子”或“拆开判断步骤”。

话术：

> Tutor 只负责基于课程证据解释和提问。本次响应会显示课程引用，但不会直接写入 Evidence，也不会修改 mastery。

随后点击“开始 Tutor Check”，回答检查问题并提交。

验收点：普通 Tutor 响应标记“本次对话未写入 Evidence”；只有 Tutor Check 提交后才出现 Evidence、grader 和新的 Next Action。

## 2:05–2:35 演示错误模式修复

在固定演示数据中展示 `confuse_cwnd_rwnd`，观察 Next Action 变为错误模式修复；开始练习并提交回答。

话术：

> 系统不只记录答错，还保存 bounded misconception code、描述、置信度、出现次数和 resolved_at。这个错误模式会影响下一个 Objective 内的 action 选择。

验收点：提交后 Evidence 数量、mastery/confidence、错误模式生命周期和 Next Action 都可在 Progress 解释。

## 2:35–3:00 结论与评测

展示 `docs/benchmark-report.md`。

话术：

> V2 使用确定性 Learning Policy，因此可以和 lowest-mastery、random/simple、mastery+prerequisite 三个 baseline 做可重复比较。当前 50 个 policy fixture 中，V2 的 objective/action accuracy 都是 100%，prerequisite violation 和 unnecessary practice 都是 0%；这是真实运行的 simulation benchmark，不是伪造的学生实验结果。

## 故障切换

- LLM 不稳定：使用 `A3_MOCK_LLM=true`，Tutor 和结构化 fixture 仍可重复。
- RAG 索引暂不可用：Tutor 回退到 Objective provenance chunk，不会无引用编造课程事实。
- 题库导入失败：保留 `failed/needs_review` 状态，修正文件后使用新的幂等 key 重试。
- 演示数据被修改：重新执行 seed 的 `--reset`，不要手动改业务表。
