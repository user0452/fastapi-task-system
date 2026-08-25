# 后续改进边界

当前 V2 主闭环已经可运行和评测；以下事项不属于本次产品主线完成条件，必须有新的证据后再扩展：

1. 用 50–500 个 simulated learners 比较随机、lowest-mastery、V2 的 time-to-mastery 和 action cost。
2. 用冻结 prompt、模型、verifier 和运行环境做 live-provider grader 与 generated-question quality 评测。
3. 扩充题库版权合规的公开题源 metadata/link 检索，但不把视频推荐做成一级产品。
4. 基于真实学习数据校准 BKT 参数和 confidence calibration；在此之前不引入 DKT 等复杂模型。
5. 对 Objective extraction 和 question tagging 建立人工抽样集，报告 precision、recall 和 unmatched rate。

每一项都必须先回答：它是否显著提高系统选择 Next Best Learning Action 的能力？不能以增加 Agent、图谱、Memory 或 UI 数量作为目标。
