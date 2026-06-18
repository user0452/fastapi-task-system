# A3 Vue Frontend

这是 A3 Learning Agent System 的 Vue 3 前端源码。前端使用 Vite 构建，开发时通过代理访问 FastAPI 后端，生产构建产物输出到项目根目录的 `static/vue/`。

## 技术栈

- Vue 3
- Vite
- Pinia
- Vue Router
- lucide-vue-next

## 开发运行

先启动后端：

```bash
uv run uvicorn main:app --reload
```

再启动前端：

```bash
cd frontend
npm install
npm run dev
```

默认访问：

```text
http://127.0.0.1:5173
```

`vite.config.js` 已将 `/users`、`/agent`、`/materials`、`/resources`、`/external-resources` 等接口代理到 `http://127.0.0.1:8000`。

## 构建

```bash
cd frontend
npm run build
```

构建输出：

```text
../static/vue/
```

后端启动后可访问：

```text
http://127.0.0.1:8000/static/vue/index.html
```

## 页面模块

- 总览
- 学生画像
- 课程知识库
- 学习资源
- 联网搜索
- 练习与评估
- 学习计划
- 任务中心
- AI 助手
- 操作日志

AI 助手页面使用 `POST /agent/chat/stream` 做流式输出，并在右侧展示资源、题集、计划和联网搜索结果。
