# 前端构建产物策略

## 决策

`frontend/src` 是前端源码的唯一事实来源，`static/vue` 是由 Vite 生成、供 FastAPI 直接托管的可部署快照。当前仓库继续保留并跟踪 `static/vue`，避免改变现有部署方式；本地开发缓存 `frontend/.vite` 不进入 Git，也不参与 ESLint。

## 日常开发

- 开发与单元验证使用 `npm run dev`、`npm run lint` 和 `npm run test:run`。
- 普通源码修改不要运行 `npm run build`，以免无关地重写带内容哈希的 `static/vue/assets`。
- 不手工编辑 `static/vue`。发现静态文件变化时，先确认它来自一次有意的生产构建。

## 发布更新

只有准备更新可部署快照时，才在 `frontend` 目录运行 `npm run build`。该命令会原子地刷新入口清单与带哈希资源，因此提交时必须把以下内容作为同一个变更集检查：

1. `static/vue/index.html` 中引用的入口文件。
2. 新增的 `static/vue/assets` 哈希文件。
3. 已不再被入口引用的旧哈希文件。

发布前至少运行 `npm run lint`、`npm run test:run` 和 `npm run build`，再由 FastAPI 静态路由或端到端测试验证页面可加载。CI 可以执行构建验证，但不应把 CI 生成物自动回写源码分支。

## 工作区保护

如果 `static/vue` 已有未提交变化，默认将其视为用户正在准备的发布快照并予以保留。除非本次任务明确包含发布构建，否则不要清理、覆盖或重新生成这些文件。
