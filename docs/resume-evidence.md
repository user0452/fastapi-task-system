# Resume Evidence

本文件只记录已经实际运行过、可由仓库命令复现的证据；没有运行过的数据不写成成果。

## Current deterministic benchmark

命令：

```powershell
uv run python scripts/evaluate_adaptive.py --check
```

最近一次报告见 [benchmark-report.md](benchmark-report.md)。当前冻结的 5 个 fixture case 结果：

- V2 Next Objective Accuracy：100%。
- V2 Action Accuracy：100%。
- V2 Prerequisite Violation Rate：0%。
- V2 Unnecessary Practice Rate：0%。
- V2 Weakness Detection Rate：100%。
- V2 Misconception Detection Rate：100%。
- Question Bank fixture Objective Match：100%（2 个 question-ranking cases）。
- Baseline A（lowest mastery）Next Objective Accuracy：40%。

这些数字是 deterministic simulation/fixture benchmark，不是现实学生效果或线上 A/B 结果。

## Engineering verification

本次最终验证实际得到：

- 后端：`384 passed`，总覆盖率 `80.45%`，coverage gate 为 `70%`。
- 前端：`24` 个 test files、`76 passed`，ESLint 和 production build 通过。
- Playwright：`4 passed`，包含资料 → Curriculum → Question Bank → Diagnostic → Evidence → Student State → Next Action 主流程、seed demo misconception repair、legacy redirect 和四视口视觉检查。
- Mypy：`115 source files` 无错误；Ruff 全部通过；Alembic fresh/current migration tests 通过。

这些是本次本地运行的证据，不等于远端 CI 已完成，也不等于真实学生实验。简历版本应在发布前把命令输出、commit 和运行环境一起保存；如果后续版本没有重新运行，不应沿用这些具体通过数量。
