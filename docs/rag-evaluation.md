# RAG 检索评测

离线评测包应包含且只读取一份 Markdown 语料和一份 JSONL 评测集。JSONL 中的标准答案不会进入索引。

完整语料烟测：

```powershell
.venv\Scripts\python.exe -m scripts.evaluate_rag `
  "C:\path\to\rag-test-pack.zip" `
  --mode full --top-k 8 `
  --output var\rag-evaluation\full.json
```

去泄漏推理测：

```powershell
.venv\Scripts\python.exe -m scripts.evaluate_rag `
  "C:\path\to\rag-test-pack.zip" `
  --mode reasoning --top-k 8 `
  --output var\rag-evaluation\reasoning.json
```

`reasoning` 模式会排除案例答案、FAQ、评测说明和附录索引，移除 CASE/FAQ 直接答案引用，并按问题文本去重。它更适合衡量底层证据召回；`full` 模式用于验证真实上传整份资料后的表现。

主要指标：

- `mean_support_recall`：每题所需 KB-ID 的平均召回比例。
- `any_hit_rate`：至少召回一个支持 KB-ID 的题目比例。
- `all_support_rate`：全部支持 KB-ID 都被召回的题目比例。
- `mrr`：第一个相关证据的平均倒数排名。
- `latency_ms.p50/p95`：单次检索延迟分位数。

生产搜索响应包含 `trace`，记录 retriever/embedding 版本、候选数量、各阶段耗时以及每个命中的分项分数。相同 trace 也会写入审计日志。
