# Resume Evidence

本文件只记录已经实际运行过、可由仓库命令复现的证据；deterministic fixture 和 simulation 不写成真实学生学习效果。

## Adaptive Benchmark

命令：

```powershell
uv run python scripts/evaluate_adaptive.py --check --output docs/benchmark-report.md
```

最近一次报告使用 `adaptive-benchmark-v2-stage2`，包含 50 个 policy cases（十类、每类 5 个）：

- V2 Next Objective Accuracy：100%。
- V2 Action Accuracy：100%。
- V2 Prerequisite Violation Rate：0%。
- V2 Unnecessary Practice Rate：0%。
- Weakness Detection：100%。
- Misconception Detection：100%。
- Baseline A lowest mastery：70% objective accuracy、10% prerequisite violation、10% unnecessary practice。
- Baseline B random/simple：36% objective accuracy、8% prerequisite violation、46% unnecessary practice。
- Baseline C mastery + prerequisite：80% objective accuracy、0% prerequisite violation、10% unnecessary practice。

Question Bank fixture：20 cases，retrieval match rate 100%；对已有高质量真实题的 generation calls 为 0；invalid question rate 为 0%。

Grader fixture：20 cases，accuracy 100%；state sequence：5 cases，pass rate 100%；curriculum fixture：10 cases，accuracy 100%。

这些数字是 deterministic benchmark/simulation，不是现实学生效果或线上 A/B 结果。

## Engineering verification

本次最终验证实际运行过：

- 后端：`uv run pytest -q`，205 passed；CI 同口径 coverage gate 通过，核心覆盖率 77.97%（门槛 70%）。
- Adaptive/RAG 相关 Ruff、Mypy（82 source files）、compileall 检查通过；发行包检查 `BUNDLE_CHECK_OK`。
- 前端：Vitest 6 个 test files、20 tests passed；ESLint 和 production build 通过。
- Playwright：3 个 Chromium 场景 passed，覆盖资料 → Curriculum → Question Bank → Diagnostic → Evidence → Student Model → Next Action，以及旧入口重定向、移动端和视觉布局。
- Alembic migration/fresh database tests 在完整后端测试中通过；V2 新增 revision 为 `20260825_13_adaptive_tutor_stage2`。

这些证据对应当前工作区的测试环境，不等于远端 CI、外部 LLM provider 或真实学生实验。若后续代码变化，必须重新运行命令后再更新数量。
