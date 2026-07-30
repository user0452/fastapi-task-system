# 真实 AI 集成冒烟

常规 CI 固定使用 mock，保证可重复且不产生外部费用。真实集成由独立的 `Live AI canary` 工作流验证，每个组件只执行一次最小调用：

- LLM 发送一条固定短提示，只验证返回非空；报告不保存响应正文、API Key 或上游错误正文。
- Embedding 对两条固定短文本编码，验证维度、有限值、归一化和区分度。
- 工作流报告上传为 `live-canary-report` artifact，只包含模型名、维度、延迟、错误类型和通过状态。

仓库配置：

- Secret `DEEPSEEK_API_KEY`：真实服务端密钥。
- Variable `DEEPSEEK_MODEL`：要验证的模型名。
- Variable `DEEPSEEK_BASE_URL`：可选，默认 `https://api.deepseek.com`。
- Variable `LIVE_CANARY_ENABLED=true`：启用工作日定时执行。未启用时仍可手动触发。

本地执行：

```powershell
$env:A3_MOCK_LLM = "false"
$env:A3_MOCK_EMBEDDING = "false"
.venv\Scripts\python.exe -m scripts.verify_live_integrations `
  --output var\live-canary.json
```

失败时先查看 artifact 中的 `component` 和 `error_type`，再在受控环境复现。脚本有意不输出上游异常正文，避免密钥或供应商请求信息进入日志。

成本边界：定时任务每个工作日只发起一次短 LLM 请求；常规 push/PR CI 不调用付费模型。若要提高频率，应先设置供应商预算告警和账户级限额。
