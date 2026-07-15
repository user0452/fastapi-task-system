# API 与业务状态说明

## 1. 通用约定

- V1 前缀：`/api/v1`
- 鉴权：`Authorization: Bearer <token>`
- 时间：客户端发送的当前时间只作为时区提示；审计统一使用服务端 UTC。
- 分页：所有分页接口限制 `size <= 100`。
- 权限：课程、资料、诊断、计划、会话和动作都用当前 `user_id` 过滤。

成功响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

业务错误使用真实 HTTP 状态码：

```json
{
  "code": 409,
  "message": "诊断已经提交，请直接进入今日学习",
  "data": null,
  "details": null,
  "error_code": "DIAGNOSTIC_ALREADY_SUBMITTED"
}
```

## 2. 核心 V1 API

### 课程

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/courses` | 当前用户课程列表 |
| `POST` | `/api/v1/courses` | 创建课程、目标、考试时间和每日时长 |
| `GET` | `/api/v1/courses/current` | 当前选中课程 |
| `GET` | `/api/v1/courses/{id}` | 课程详情 |
| `PATCH` | `/api/v1/courses/{id}` | 更新课程配置 |
| `POST` | `/api/v1/courses/{id}/select` | 切换当前课程 |
| `DELETE` | `/api/v1/courses/{id}?confirmed=true` | 归档课程，必须确认 |

### 资料与知识点

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/courses/{id}/materials` | 资料列表和处理状态 |
| `POST` | `/api/v1/courses/{id}/materials/text` | 手动文本资料，返回 `202` |
| `POST` | `/api/v1/courses/{id}/materials/upload` | 文件上传，返回 `202` |
| `GET` | `/api/v1/materials/{id}` | 轮询处理状态和错误原因 |
| `POST` | `/api/v1/materials/{id}/retry` | 重试失败资料 |
| `GET` | `/api/v1/courses/{id}/knowledge-points` | 知识点及来源 |
| `GET` | `/api/v1/courses/{id}/knowledge-graph` | 知识点、掌握度和依赖关系 |
| `POST` | `/api/v1/courses/{id}/materials/search` | 关键词、片段向量、知识点向量融合检索与引用 |

### 诊断、计划和今日学习

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/courses/{id}/diagnostic` | 生成 5-8 道诊断题 |
| `GET` | `/api/v1/courses/{id}/diagnostic` | 最近一次课程诊断 |
| `GET` | `/api/v1/diagnostics/{id}` | 诊断详情，不返回标准答案 |
| `POST` | `/api/v1/diagnostics/{id}/submit` | 评分、掌握度和计划初始化 |
| `GET` | `/api/v1/study/today?course_id={id}` | 今日学习单元 |
| `POST` | `/api/v1/study/sessions/{id}/start` | 开始或继续学习 |
| `POST` | `/api/v1/study/sessions/{id}/submit` | 提交练习并自适应后续计划 |
| `GET` | `/api/v1/courses/{id}/progress` | 掌握度、计划、变化原因和完成率 |
| `GET` | `/api/v1/courses/{id}/study-plan` | 完整计划与后续单元 |
| `PATCH` | `/api/v1/study/sessions/{id}/schedule` | 调整计划单元时间 |
| `POST` | `/api/v1/courses/{id}/practices` | 按课程/知识点生成聊天内练习 |
| `POST` | `/api/v1/practices/{id}/submit` | 批改练习、更新掌握度并调整计划 |
| `GET` | `/api/v1/courses/{id}/practice-stats` | 正确率、趋势和知识点分布 |
| `GET` | `/api/v1/courses/{id}/wrong-answers` | 错题、用户答案、解析和薄弱知识点 |

### Agent

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/agent/sessions` | 后端会话列表 |
| `POST` | `/api/v1/agent/sessions` | 创建课程会话 |
| `GET` | `/api/v1/agent/sessions/{id}` | 恢复历史消息、引用和动作 |
| `GET` | `/api/v1/agent/courses/{id}/workspace` | 恢复课程助手、唯一主会话、消息和课程记忆 |
| `PUT` | `/api/v1/agent/courses/{id}/memories` | 更新当前课程助手记忆 |
| `POST` | `/api/v1/agent/chat` | 非流式请求 |
| `POST` | `/api/v1/agent/chat/stream` | NDJSON 流式请求 |
| `POST` | `/api/v1/agent/actions/{id}/decision` | 确认或拒绝破坏性动作 |

课程聊天请求应显式携带 `course_id`。`current_time` 使用本地时间和 UTC 偏移，精确到分钟，仅用于回答语境；服务端审计时间仍以 UTC 为准。若 `session_id` 属于另一门课程，接口返回 `409 SESSION_COURSE_MISMATCH`。

### 外部资源

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/courses/{id}/external-resources/search` | 搜索并规范化 3-6 个课程相关视频 |
| `GET` | `/api/v1/courses/{id}/external-resources` | 课程资源及当前用户交互状态 |
| `POST` | `/api/v1/courses/{id}/external-resources/{resourceId}/interactions` | 记录打开、收藏、看完或有用性 |
| `POST` | `/api/v1/courses/{id}/external-resources/{resourceId}/check` | 检测链接有效性并更新时间 |

资源返回统一字段：`provider`、`canonical_url`、`title`、`author`、`duration_seconds`、`thumbnail_url`、`reason`、`validity_status` 和 `interaction`。URL 哈希在课程内去重，搜索结果按查询缓存。

## 3. 资料状态机

```text
uploaded -> parsing -> indexing -> ready
     |          |          |
     +----------+----------+-> failed -> retry -> parsing
```

| 状态 | 含义 | 前端动作 |
| --- | --- | --- |
| `uploaded` | 元数据已保存，等待后台任务 | 显示等待，不提供手动构建索引按钮 |
| `parsing` | 文本解析和文件校验中 | 保持轮询 |
| `indexing` | 分块、Embedding、知识点提取中 | 保持轮询 |
| `ready` | 可用于诊断和 RAG | 开放诊断与提问 |
| `failed` | 保存 `processing_error` | 展示原因和重试按钮 |

文件上限为 100MB；上传流按块落盘，后续直接按路径解析，不把大文件整体载入内存。处理由数据库 job、原子 claim、lease、heartbeat 和重试驱动，服务重启或多 worker 部署都能安全恢复未完成任务。

索引保存内容哈希和模型版本。重新处理资料时只向量化变化片段与变化知识点，未变化记录保留原 ID 和 embedding。引用结构包含 `material_id`、`material_title`、`page_number`、`chunk_id`、`chunk_index`、`knowledge_points`、融合分数和摘要。

## 4. 学习状态与确定性规则

学习单元主要状态：

```text
planned -> in_progress -> evaluated
```

诊断和每日练习都保存逐题答案与知识点评分。掌握度更新规则：

```text
after = before * 0.7 + assessment_score * 0.3
```

每次变化保存 `before_value`、`after_value`、`reason` 和 `evaluation_id`。业务 service 根据阈值调整后续计划，LLM 不直接修改掌握度或计划状态。

## 5. Agent 动作分级

| 风险 | 行为 |
| --- | --- |
| 只读 | 直接执行并保存审计摘要 |
| 生成 | 允许执行，使用稳定上下文避免重复生成 |
| 写入 | 执行时保存幂等键和审计记录 |
| 破坏性 | 创建 10 分钟有效的确认请求，确认后一次性执行 |

破坏性请求确认前不改业务表；重复确认返回同一结果。直接删除和旧批量接口也要求 `confirmed=true`，旧 Agent 不再绕过新确认链路。

## 6. 降级状态

- Tavily 失败：外部搜索返回 `degraded: true`、`warning` 和可用的部分或空资源列表。
- 视频封面失败：优先使用搜索结果自带图片，再由前端显示稳定占位，不阻止卡片打开。
- LLM 失败：有 RAG 引用时根据课程片段回答；无引用时返回可执行的引导文案。
- 日志写入失败：不回滚已经成功的核心业务动作。

## 7. 持久化与审计

- `course_agents.course_id` 唯一，保证一门课程只有一个助手和一个主会话。
- 每次课程聊天写入 `agent_runs`；每个工具写入 `agent_tool_calls`，包含课程、风险、参数、结果和状态。
- 资料、课程、学习、Agent 与资源操作都写入 `operation_logs`，并在读取和写入前校验 `user_id + course_id` 所有权。
- 数据库上下文使用显式事务，断线不会透明丢弃未提交消息；并发死锁只重试已完整回滚的幂等事务段。
