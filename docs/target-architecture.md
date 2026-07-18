# 专科学习 AI 目标架构

## 1. 产品主线

```text
创建一门课程 AI
  -> 上传或手动录入资料
  -> 自动解析、增量分块、向量化并提取知识点/依赖
  -> 在课程窗口提问，回答附内部资料引用
  -> 按需搜索并展示 3-6 个外部视频卡片
  -> 标记学习，直接在聊天中生成和提交练习
  -> 保存错题并更新知识点掌握度
  -> 自适应重排本课程后续学习计划
```

每门课程是一个长期存在的专科学习 AI，而不是课程管理页中的一条记录。AI 负责理解和生成，确定性业务服务负责所有权、课程隔离、状态、掌握度、计划调整和审计。

## 2. 模块化单体边界

```text
app/
  main.py
  core/                 配置、数据库、安全、错误、日志
  api/v1/               API 聚合与版本入口
  modules/
    auth/               身份和当前用户
    courses/            课程、目标、考试时间、每日时长
    materials/          上传、解析、索引、知识点来源
    learning/           诊断、掌握度、计划、今日学习、评估
    roadmaps/           长期阶段路线、生成任务、真实关联和调整依据
    agent/              课程助手、会话、记忆、运行、工具策略和确认
    resources/          外部资源 Provider、缓存、去重、有效性和交互
    audit/              操作日志和 AI 调用审计
  integrations/         LLM、Embedding、混合检索、外部搜索、文档解析
  jobs/                 可替换的后台任务入口
```

每个业务模块采用 `router.py`、`schemas.py`、`service.py`、`repository.py`。数据库访问以 SQLAlchemy 2.x Session、ORM 表达式和反射模型为主；仍需复杂 MySQL 语句的仓储通过同一事务游标适配层执行，service 负责事务边界、锁顺序和业务规则。

## 3. 关键状态机

### 资料

```text
uploaded -> parsing -> indexing -> ready
                    \-> failed
```

### 课程

```text
draft -> preparing -> diagnostic_pending -> active -> completed
```

### 学习单元

```text
planned -> in_progress -> completed -> evaluated -> adapted
```

### 长期学习路线

```text
pending -> generating -> ready
                     \-> failed -> retry -> generating

stage: pending -> active -> completed
```

路线创建、生成任务和调整记录均使用幂等键。缺失路线由课程行锁串行初始化，避免课程列表与当前课程并发读取时重复创建。

状态只允许通过 service 中的显式规则迁移，并保存失败原因和更新时间。

## 4. 核心实体

- `courses`：课程目标、考试时间、每日可用时长和课程状态。
- `course_materials`：原始资料元数据、处理状态和失败原因。
- `course_material_chunks`：页码、片段、embedding 和模型版本。
- `knowledge_points`：课程知识点以及对应资料来源。
- `knowledge_point_relations`：知识点前置和依赖关系。
- `mastery_records`：用户对知识点的掌握度和最近评估依据。
- `study_plans`：课程计划的生命周期和时间范围。
- `study_sessions`：每天可执行的学习单元。
- `study_session_items`：讲解、例题、练习和复习项目。
- `learning_roadmaps` / `learning_roadmap_stages`：课程目标快照、四阶段路线、进度和调整原因。
- `roadmap_generation_jobs` / `roadmap_adjustments`：可重试生成任务及诊断、练习触发的幂等调整依据。
- `roadmap_stage_points` / `roadmap_stage_sessions`：阶段与真实知识点、每日学习单元的关联。
- `chat_sessions`：按课程组织的后端会话。
- `agent_chat_messages`：会话消息、工具结果和引用。
- `course_agents`：每门课程唯一的助手及主会话。
- `course_agent_memories`：按课程隔离的偏好、目标和学习记忆。
- `agent_runs` / `agent_tool_calls`：每次 Agent 运行及工具调用审计。
- `external_resources`：规范化外部视频、缓存信息和有效性状态。
- `resource_interactions`：打开、收藏、看完和有用性反馈。

## 5. 课程检索边界

每次检索同时执行关键词召回、片段向量召回和知识点向量召回，再进行重排。所有 SQL 和相似度候选在召回前强制应用 `user_id + course_id`，不能在召回后再过滤。

```text
问题 -> 课程过滤 -> BM25 风格关键词分数
                 -> 片段 embedding 相似度
                 -> 知识点 embedding 相似度
                 -> 融合与重排 -> 材料/页码/片段/知识点引用
```

资料更新使用内容哈希复用未变化片段和知识点向量。embedding 的规范数据保存在 MySQL，课程级 FAISS 文件负责向量候选召回，MySQL 倒排 term 负责关键词候选召回；应用只对候选做融合和重排，不再全量扫描整门课程。更大规模部署仍可通过 integration 边界替换为 Qdrant 或 pgvector。

## 6. 外部资源边界

`BilibiliProvider`、`YouTubeProvider` 和 `TavilyProvider` 实现同一搜索接口。服务层负责 URL 规范化、哈希去重、课程相关度筛选、缓存、封面降级和交互合并。Provider 失败只产生 `degraded` 状态，不阻断课程回答。

## 7. 掌握度规则

第一版使用可解释的确定性算法：

```text
new_mastery = old_mastery * 0.7 + assessment_score * 0.3
```

- `< 60`：次日加入基础讲解和复习题。
- `60-80`：保持难度并继续当前知识点。
- `> 80`：进入下一知识点或提高难度。
- 连续两次 `< 60`：增加例题并降低新知识比例。

每次调整保存 `reason`、`before`、`after`、`evaluation_id`，以支持前端解释计划变化。

## 8. Agent 安全边界

- 只读工具：直接执行。
- 生成工具：使用幂等键防止重复产物。
- 写入工具：记录审计和请求来源。
- 破坏性工具：只生成确认请求，确认后使用一次性 token 执行。
- 资料、网页和长期记忆均按不可信内容处理，不允许覆盖系统指令。
- 客户端时间仅提供时区语境，审计时间由服务端以 UTC 生成。
- 课程会话与请求课程不一致时返回 `409 SESSION_COURSE_MISMATCH`。
- 每个数据库事务显式 `begin/commit/rollback`；课程聊天统一锁顺序，并对已完整回滚的死锁事务段有限重试。

工具平台使用注册表声明名称、类别、风险、课程要求、确认要求、可用状态和超时。执行前由策略守卫校验，执行后把状态、耗时、来源、学习上下文和业务更新保存为结构化摘要。摘要只展示可验证的调用与数据依据，不暴露模型内部推理过程。

- 计算器只接受基础算术 AST。
- 受限 Python 执行器在独立进程中执行，禁止导入、文件、网络和子进程，并限制时长、内存和输出。它只有应用级隔离，未使用容器、cgroup、seccomp 或独立虚拟机，属于实验性能力，不得面向不可信公网用户开放。
- MCP 与图片工具当前是预留适配器：策略与配置状态已完成，真实外部执行尚未实现；即使已配置也返回 `configured_not_implemented`，不会成为可调用工具。

## 9. 前端结构

一级入口只有跨课程 Today、左侧课程 AI 列表和设置。进入课程后，聊天左侧显示当前会话内的用户消息目录；多会话历史位于聊天头部的独立抽屉。课程检查器提供九个视图：概览、今日、诊断、知识点、路线、练习、错题、长期记忆、资料库。

- Today 是登录后的跨课程总览。
- 资料上传后自动显示处理状态，不暴露 RAG 和 Embedding 操作。
- AI 回答显示可跳转的内部引用和可操作的外部视频卡片。
- 每条回答可展开“本次回答依据”，区分工具执行、课程资料、外部来源、学习上下文和本次更新。
- 知识图谱支持图形与列表双视图、缩放、拖拽、筛选、证据详情和节点快捷提问。
- 长期记忆展示来源与更新时间，允许用户逐条或按类型控制是否进入后续回答。
- URL 同时保存课程、面板和会话标识，刷新与重新登录后恢复到同一学习现场。
- 出题、答题、批改和掌握度变化在聊天内完成，面板显示完整统计。
- 面板开关、课程切换、刷新和重新登录都不丢聊天草稿与持久状态。
- 桌面使用 264px 课程栏与 460px 检查器；移动端使用抽屉课程栏和全宽二级面板。
- 技术调试信息仅在开发模式显示。
