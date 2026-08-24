# Adaptive Learning Evaluation

## Scope

RAG evaluation 继续衡量 evidence retrieval 的 recall、MRR、latency 和 trace。它不是 Adaptive Tutor 的主指标。

Adaptive benchmark 衡量三层：

```text
Historical Evidence → Student Diagnosis → Teaching Decision
```

Benchmark 当前使用 deterministic fixtures，明确称为 simulation/fixture benchmark，不代表真实学生实验。

## Reproducible command

```powershell
uv run python scripts/evaluate_adaptive.py --check
uv run python scripts/evaluate_adaptive.py --output docs/benchmark-report.md
```

`--check` 不访问 LLM、数据库或网络，失败时退出码非零，适合 CI。报告会记录 benchmark version、运行时间、fixtures、baseline、V2、question-bank ranking、calibration 和 limitations。

## Frozen fixtures

当前 fixture 覆盖：

- prerequisite-first：dependent Objective 的 mastery 更低，但 prerequisite 未达阈值。
- misconception-repair：目标中有 active misconception。
- verify-low-confidence：mastery 高但 evidence confidence 低。
- spaced-review：高掌握 Objective 的最近有效证据超过一周。
- stop-unnecessary-practice：全部目标已近期验证，Policy 应返回 no action。

Question Bank fixture 覆盖真实上传题优先于 generated，以及 direct/transfer coverage 的 deterministic ranking。

## Baselines

### Baseline A：lowest mastery

对每个 active Objective 选择 mastery 最低者，不读取 prerequisite，也不区分 confidence、misconception、spacing 和 no-action 条件。它是故意简单的下限，用来说明“只看分数”会跳过 prerequisite 或重复练习。

### V2 deterministic policy

V2 使用：

- prerequisite-aware Objective Selector
- weakness、uncertainty、importance、goal relevance 和 spacing score
- explicit overpractice penalty
- Action Selector：explain/practice/verify/review/misconception repair
- objective-aligned Question Bank Selector

### 未来 baseline

可以加入旧 V1 行为或 LLM-only 策略，但必须冻结 prompt、模型、verifier、运行环境和失败分类后，才能与 deterministic baseline 比较。

## Metrics

| 指标 | 含义 | 方向 |
| --- | --- | --- |
| Next Objective Accuracy | 选中的目标是否匹配 fixture expected target | 越高越好 |
| Action Accuracy | explain/practice/verify/review/repair 是否匹配 | 越高越好 |
| Prerequisite Violation Rate | 是否跳过未达阈值的 prerequisite | 越低越好，目标接近 0 |
| Unnecessary Practice Rate | 高 mastery、高 confidence、近期已验证仍被选择 | 越低越好 |
| Question-Objective Match | 题目是否真正覆盖 target Objective | 越高越好 |
| Weakness Detection | 是否识别 ground-truth weak objective | 越高越好 |
| Misconception Detection | 是否选择正确 repair action/错误模式 | 越高越好 |
| Mastery Calibration | mastery 与后续成功概率的 Brier/calibration gap | 越低越好 |

Practice benchmark 还应在 provider-backed run 中记录：retrieval hit rate、generation fallback rate、invalid/duplicate question rate，以及“有合适真实题时 LLM generation calls == 0”。当前离线 fixture 的 fallback rate 为 0，不把它误报成真实线上调用统计。

## Longitudinal simulation

后续可加入 50–500 个 simulated learners：每个 Objective 有 latent mastery，回答概率由 latent mastery 与 question difficulty 决定，比较 random practice、lowest mastery 和 V2 policy 的 final mastery、time-to-mastery、actions required、unnecessary practice 和 prerequisite violations。结果必须明确标记为 simulation，不能替代真实学生实验。

## Limitations

- fixture 数量有限，不能证明真实学习效果。
- 当前 calibration observations 是冻结观察值，不是 longitudinal learner outcomes。
- 主观 short-answer grading 和 misconception extraction 仍需要单独的真实/模型 provider 评测。
- Question Bank 的版权、公开搜索和生成质量必须在启用外部 source 时另行记录。
