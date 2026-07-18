# 改进方案落地记录

日期：2026-07-19  
分支：`feature/a3-competition`

## 已完成

### P0 前端设计系统收敛
- 删除 `PlanPanel` / `KnowledgePanel` / `SettingsPage` / `OverviewPanel` 的双层 “Learning OS visual layer” 覆盖写法，合并为单层 token 样式。
- 在 `frontend/src/styles/components.css` 增加共享 panel 原语（`.panel-state` / `.panel-empty` / `.panel-heading`）。

### P0 仓库与文档
- 新增本文件作为改进方案执行记录。
- 清理根目录过程文件（若存在）：临时报告、一次性 memory 脚本、无效 `=3.0` 等。
- 架构文档尺寸描述改为与当前工作台一致（课程栏 264px / 检查器 460px）。

### P1 今日总览聚合 API
- 新增 `GET /api/v1/study/today-overview`。
- 一次返回全部课程今日单元、路线摘要与汇总指标。
- `GlobalTodayPage` 改为单请求，去掉按课程 N+1。

### P1 前端交互
- `SessionList`：点击外部与 Esc 关闭操作菜单。
- `MessageAnchorRail`：中间态/线形目录补 `aria-label`。
- `AppShell` 创建课程对话框复用公共 `Modal`。

### P1 后端可维护与闭环
- 抽出 `app/modules/agent/memory_service.py`，`service.py` 仅再导出兼容导入。
- 掌握度更新增加短时重复练习权重衰减（6 小时内），并返回 `formula` / `weight`。
- 薄弱点（&lt;60）次日复习 item 标注 `spaced_review`。

## 验证建议

```powershell
uv run python -m pytest tests/test_learning_loop.py tests/test_agent_memories.py tests/test_course_ai_workspace.py -q
Set-Location frontend
npm run lint
npm run test:run
npm run build
```

## 后续可继续
- 继续拆分 `agent/service.py` 的会话/工具/流式编排。
- 逐步隔离并退役 `routers/` / `agents/` / `services/` legacy 层。
- 压测课程级 FAISS 与聚合 Today 接口在多课程下的延迟。
