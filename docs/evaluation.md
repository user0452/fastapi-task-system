# Adaptive Learning Evaluation

## 目标与边界

RAG 评测继续衡量 evidence retrieval 的 recall、MRR、latency 和 trace，但它是底层能力评测，不是 Adaptive Tutor 的产品主指标。

Adaptive Benchmark 评估三层闭环：

```text
Historical Evidence → Student Diagnosis → Teaching Decision
```

当前报告是 deterministic fixture/simulation benchmark，不代表真实学生实验，也不把模型调用结果伪装成学习效果。

## 可重复运行

```powershell
uv run python scripts/evaluate_adaptive.py --check
uv run python scripts/evaluate_adaptive.py --check --output docs/benchmark-report.md
```

`--check` 不访问 LLM、数据库或网络；失败时退出码非零，适合 CI。报告冻结 benchmark version、运行时间、fixture 数量、策略、baselines、question bank、grader、state sequence、ablation 和 limitations。

## Frozen fixtures

当前 policy fixture 共 50 个 case，分为十类，每类 5 个：

- prerequisite：dependent Objective 的 mastery 更低，但未达 prerequisite 阈值。
- confidence：mastery 高但证据数量不足，应先 verify。
- misconception：存在 active misconception，应进入 repair。
- spacing：高掌握内容超过间隔周期，应 review。
- importance：重要目标在同等状态下优先。
- uncertainty：置信度低的目标优先补证据。
- goal relevance：与课程目标/考试约束相关的目标优先。
- weakness：能识别当前真正薄弱目标。
- unnecessary practice：高 mastery、高 confidence、近期已验证内容不再刷题。
- contradictory evidence：混合对错证据不应导致极端跳变。

另有固定的 20 个 question-selection case、20 个 grader case、5 个 state-sequence case 和 10 个 curriculum case。

## Baselines

### Baseline A：lowest mastery

只选择 mastery 最低的 Objective，不读取 prerequisite、confidence、misconception、spacing 或 no-action 条件。它是最简单的下限，用来验证“只看分数”会跳过前置或重复练习。

### Baseline B：random/simple

使用固定随机种子在 active Objective 中选择目标，并用简单的 mastery 阈值映射 action。它代表没有稳定 Student Model/Policy 的简单策略，保证结果可复现。

### Baseline C：mastery + prerequisite

选择未被 prerequisite 阻塞且 mastery 最低的目标，再用基础阈值选 action。它隔离“仅增加 prerequisite 约束”相对于完整 V2 的收益。

### V2 deterministic policy

V2 使用：

- prerequisite-aware Objective Selector；
- weakness、uncertainty、importance、goal relevance、spacing 和 recent-overpractice penalty；
- 独立的 Action Selector：explain/practice/verify/review/misconception repair；
- objective-aligned Question Bank Selector；
- 真实题 retrieval-first，生成 fallback 只在没有合格题时触发。

## 指标

| 指标 | 含义 | 方向 |
| --- | --- | --- |
| Next Objective Accuracy | 选中的目标是否匹配 fixture expected target | 越高越好 |
| Action Accuracy | explain/practice/verify/review/repair 是否匹配 | 越高越好 |
| Prerequisite Violation Rate | 是否跳过未达阈值的 prerequisite | 越低越好，目标接近 0 |
| Unnecessary Practice Rate | 已掌握、高置信度、近期验证内容是否仍被练习 | 越低越好 |
| Question-Objective Match | 题目是否覆盖 target Objective | 越高越好 |
| Weakness Detection | 是否识别 ground-truth weak objective | 越高越好 |
| Misconception Detection | 是否选择正确 repair/action 与错误模式 | 越高越好 |
| Mastery Calibration | mastery 与后续成功概率的 calibration gap/Brier | 越低越好 |

Practice benchmark 还统计 retrieval hit rate、generation fallback rate、invalid/duplicate question rate，以及“有合适真实题时 LLM generation calls == 0”。

## 纵向模拟

可以进一步运行 50–500 个 simulated learners：每个 Objective 保存 latent mastery，回答概率由 latent mastery 与 question difficulty 决定，比较 random practice、lowest mastery 和 V2 的 final mastery、actions required、time-to-mastery、unnecessary practice 和 prerequisite violations。此类结果必须明确标为 simulation，不能替代真实学生实验。

## 限制

- fixture 数量和状态分布有限，不能证明真实学习效果。
- 当前 state sequence 是可重复的规则/模拟检查，不是纵向学生结果。
- 主观 short-answer grading、misconception extraction 和 question generation 仍需要单独的 live-provider 评测。
- 公开题目搜索必须额外记录版权和保存策略；当前主流程优先支持用户上传题库。

真实运行结果见 [benchmark-report.md](benchmark-report.md)，简历可用的事实只记录在 [resume-evidence.md](resume-evidence.md)。
