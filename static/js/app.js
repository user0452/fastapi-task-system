const state = {
    page: 1,
    pageSize: 10,
    status: "",
    priority: "",
    query: "",
    total: 0,
    tasks: [],
    exams: [],
    previewTasks: [],
    operationLogs: [],
    resources: [],
    resourcesTotal: 0,
    selectedResourceId: null,
    quizzes: [],
    quizzesTotal: 0,
    selectedQuizId: null,
    studyPlanPreview: null,
    agentMessages: [],
    agentPlanPreview: null,
    a3Page: "overview",
    deleteTargetId: null,
};

const statusMap = {
    todo: "待办",
    doing: "进行中",
    done: "已完成",
};

const priorityMap = {
    low: "低",
    medium: "中",
    high: "高",
};

const agentStatusMap = {
    need_more_info: "需要补充",
    ready_to_execute: "已执行",
    chat_only: "仅对话",
};

const agentIntentMap = {
    generate_study_package: "学习包",
    generate_resource: "学习资源",
    generate_quiz: "练习题",
    generate_plan: "学习计划",
    update_profile: "更新画像",
    qa: "问答",
    unknown: "未知",
};

const agentToolMap = {
    generate_resource: "资源",
    generate_quiz: "题集",
    generate_plan: "计划",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function setText(selector, text) {
    const element = $(selector);
    if (element) {
        element.textContent = text;
    }
}

async function api(path, options = {}) {
    const token = localStorage.getItem("token");
    const headers = { ...(options.headers || {}) };

    if (options.body && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }
    if (token) {
        headers.Authorization = `Bearer ${token}`;
    }

    try {
        const response = await fetch(path, { ...options, headers });
        const text = await response.text();
        let payload = null;

        if (text) {
            try {
                payload = JSON.parse(text);
            } catch {
                payload = { message: text };
            }
        }

        if (!response.ok) {
            return {
                code: response.status,
                message: normalizeMessage(payload?.detail || payload?.message, "请求失败"),
                data: payload,
            };
        }

        return payload || { code: response.status, message: "success", data: null };
    } catch {
        return { code: 0, message: "无法连接服务，请确认后端已启动", data: null };
    }
}

function normalizeMessage(message, fallback) {
    if (!message) return fallback;
    if (Array.isArray(message)) {
        return message.map((item) => item.msg || item.message || JSON.stringify(item)).join("；");
    }
    if (typeof message === "object") {
        return message.msg || message.message || JSON.stringify(message);
    }
    return String(message);
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML;
}

function formatDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    });
}

function prettyJson(value) {
    return JSON.stringify(value ?? null, null, 2);
}

function valueToText(value) {
    if (value === null || value === undefined || value === "") return "";
    if (typeof value === "string") return value;
    return JSON.stringify(value, null, 2);
}

function renderMultiline(value) {
    const text = valueToText(value);
    return text ? escapeHtml(text).replace(/\n/g, "<br>") : "暂无";
}

function normalizeListValue(value) {
    if (!value) return [];
    return Array.isArray(value) ? value : [value];
}

function renderPlainList(value) {
    const list = normalizeListValue(value);
    if (!list.length) {
        return `<span class="muted-text">暂无</span>`;
    }
    return `
        <ul class="plain-list">
            ${list.map((item) => `<li>${renderMultiline(item)}</li>`).join("")}
        </ul>
    `;
}

function showToast(message, type = "success") {
    const toast = $("#toast");
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.remove("hidden");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 2800);
}

function showInlineMessage(element, message, type = "success") {
    element.textContent = message;
    element.className = `inline-message ${type}`;
    element.classList.remove("hidden");
}

function hideInlineMessage(element) {
    element.textContent = "";
    element.className = "inline-message hidden";
}

function handleAuthExpired(result) {
    if (result.code !== 401) return false;
    logout();
    showInlineMessage($("#auth-msg"), "登录已失效，请重新登录", "error");
    return true;
}

function setBusy(button, busy, busyText = "处理中") {
    if (!button) return;
    if (busy) {
        button.dataset.originalText = button.textContent;
        button.textContent = busyText;
        button.disabled = true;
        return;
    }
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
}

function showPage(page) {
    $$(".page").forEach((item) => item.classList.add("hidden"));
    $(`#${page}-page`).classList.remove("hidden");
}

function switchAuthTab(target) {
    $$(".auth-tab").forEach((tab) => {
        tab.classList.toggle("active", tab.dataset.authTab === target);
    });
    $$(".auth-form").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.authPanel === target);
    });
    hideInlineMessage($("#auth-msg"));
}

function updateTopNavState() {
    const activeView = $(".view.active")?.id?.replace("-view", "") || "a3";
    $$(".top-nav-link").forEach((button) => {
        const isA3Link = Boolean(button.dataset.a3Goto);
        const active = activeView === "a3"
            ? isA3Link && button.dataset.a3Goto === state.a3Page
            : !isA3Link && button.dataset.view === activeView;
        button.classList.toggle("active", active);
    });
}

function switchView(target) {
    $("#main-page").dataset.activeView = target;
    $$(".nav-item").forEach((item) => {
        item.classList.toggle("active", item.dataset.view === target);
    });
    $$(".view").forEach((view) => {
        view.classList.toggle("active", view.id === `${target}-view`);
    });

    const titleMap = {
        tasks: "任务工作台",
        ai: "智能工具",
        a3: "A3 学习书案",
    };
    const eyebrowMap = {
        tasks: "Personal Workspace",
        ai: "Smart Tools",
        a3: "A3 Learning Agent",
    };
    const subtitleMap = {
        tasks: "查看任务状态、维护优先级并保持日常执行节奏。",
        ai: "保留现有规则命令、考试解析和 AI 操作日志能力。",
        a3: "以画像为底稿，分章管理计划、资源和练习题集。",
    };

    $(".eyebrow").textContent = eyebrowMap[target] || "FastAPI 工作台";
    $("#workspace-title").textContent = titleMap[target] || "任务工作台";
    $("#workspace-subtitle").textContent = subtitleMap[target] || "查看任务状态、维护优先级并保持日常执行节奏。";
    $("#add-task-btn").classList.toggle("hidden", target !== "tasks");
    updateTopNavState();

    if (target === "a3") {
        loadA3Dashboard();
    }
}

function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    state.tasks = [];
    state.exams = [];
    state.previewTasks = [];
    state.resources = [];
    state.resourcesTotal = 0;
    state.selectedResourceId = null;
    state.quizzes = [];
    state.quizzesTotal = 0;
    state.selectedQuizId = null;
    state.studyPlanPreview = null;
    state.agentMessages = [];
    state.agentPlanPreview = null;
    state.a3Page = "overview";
    $("#login-form").reset();
    $("#register-form").reset();
    renderStudyPlanPreview();
    renderAgentMessages();
    renderAgentSummary();
    switchA3Page("overview");
    showPage("auth");
}

function checkAuth() {
    const token = localStorage.getItem("token");
    const username = localStorage.getItem("username");
    if (!token || !username) {
        showPage("auth");
        return;
    }

    $("#username-display").textContent = username;
    showPage("main");
    switchView("a3");
    loadDashboard();
    loadA3Dashboard();
}

async function fetchTasks(page, size, status = "") {
    const params = new URLSearchParams({ page: String(page), size: String(size) });
    if (status) params.set("status", status);
    const result = await api(`/tasks?${params.toString()}`);
    if (result.code === 401) {
        logout();
        showInlineMessage($("#auth-msg"), "登录已失效，请重新登录", "error");
        result.authExpired = true;
    }
    return result;
}

async function loadMetrics() {
    const [all, todo, doing, done] = await Promise.all([
        fetchTasks(1, 1),
        fetchTasks(1, 1, "todo"),
        fetchTasks(1, 1, "doing"),
        fetchTasks(1, 1, "done"),
    ]);

    if ([all, todo, doing, done].some((result) => result.authExpired)) return;

    $("#metric-total").textContent = all.code === 200 ? all.data.total : 0;
    $("#metric-todo").textContent = todo.code === 200 ? todo.data.total : 0;
    $("#metric-doing").textContent = doing.code === 200 ? doing.data.total : 0;
    $("#metric-done").textContent = done.code === 200 ? done.data.total : 0;
}

async function loadDashboard() {
    await Promise.all([loadMetrics(), loadTasks(), loadOperationLogs()]);
}

async function loadAllFilteredTasks() {
    const first = await fetchTasks(1, 100, state.status);
    if (first.code !== 200) return first;

    const total = first.data.total || 0;
    const pages = Math.ceil(total / 100);
    let list = [...(first.data.list || [])];

    if (pages > 1) {
        const rest = await Promise.all(
            Array.from({ length: pages - 1 }, (_, index) => fetchTasks(index + 2, 100, state.status)),
        );
        rest.forEach((result) => {
            if (result.code === 200 && result.data?.list) {
                list = list.concat(result.data.list);
            }
        });
    }

    return { code: 200, data: { list, total: list.length } };
}

function applyClientFilters(tasks) {
    const query = state.query.trim().toLowerCase();
    return tasks.filter((task) => {
        const matchesPriority = !state.priority || task.priority === state.priority;
        const searchable = `${task.title || ""} ${task.description || ""}`.toLowerCase();
        const matchesQuery = !query || searchable.includes(query);
        return matchesPriority && matchesQuery;
    });
}

async function loadTasks() {
    const useClientFilter = Boolean(state.priority || state.query.trim());
    const result = useClientFilter
        ? await loadAllFilteredTasks()
        : await fetchTasks(state.page, state.pageSize, state.status);

    if (result.code !== 200) {
        if (result.authExpired) return;
        showToast(normalizeMessage(result.message, "加载任务失败"), "error");
        return;
    }

    if (useClientFilter) {
        const filtered = applyClientFilters(result.data.list || []);
        state.total = filtered.length;
        const start = (state.page - 1) * state.pageSize;
        state.tasks = filtered.slice(start, start + state.pageSize);
    } else {
        state.total = result.data.total || 0;
        state.tasks = result.data.list || [];
    }

    renderTasks();
}

function renderTasks() {
    const tbody = $("#task-tbody");
    const empty = $("#empty-msg");
    const tableWrap = $(".table-wrap");
    const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));

    if (state.page > totalPages) {
        state.page = totalPages;
        loadTasks();
        return;
    }

    $("#task-count-label").textContent = `共 ${state.total} 条`;
    $("#page-info").textContent = `第 ${state.page} / ${totalPages} 页`;
    $("#prev-page").disabled = state.page <= 1;
    $("#next-page").disabled = state.page >= totalPages;

    if (!state.tasks.length) {
        tbody.innerHTML = "";
        tableWrap.classList.add("hidden");
        empty.classList.remove("hidden");
        return;
    }

    tableWrap.classList.remove("hidden");
    empty.classList.add("hidden");

    tbody.innerHTML = state.tasks.map((task) => {
        const description = task.description ? escapeHtml(task.description) : "无描述";
        const updated = task.updated_at || task.created_at;
        return `
            <tr>
                <td>
                    <div class="task-title">
                        <strong>${escapeHtml(task.title)}</strong>
                        <span>${description}</span>
                    </div>
                </td>
                <td><span class="badge status-${escapeHtml(task.status)}">${statusMap[task.status] || task.status}</span></td>
                <td><span class="badge priority-${escapeHtml(task.priority)}">${priorityMap[task.priority] || task.priority}</span></td>
                <td>${formatDate(updated)}</td>
                <td>
                    <div class="row-actions">
                        <button type="button" class="btn btn-ghost" data-action="edit" data-id="${task.id}">编辑</button>
                        <button type="button" class="btn btn-danger" data-action="delete" data-id="${task.id}">删除</button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

function openTaskModal(task = null) {
    $("#modal-title").textContent = task ? "编辑任务" : "新建任务";
    $("#task-form").reset();
    $("#task-id").value = task?.id || "";
    $("#task-title").value = task?.title || "";
    $("#task-desc").value = task?.description || "";
    $("#task-status").value = task?.status || "todo";
    $("#task-priority").value = task?.priority || "medium";
    $("#task-modal").classList.remove("hidden");
    $("#task-modal").setAttribute("aria-hidden", "false");
}

function closeTaskModal() {
    $("#task-modal").classList.add("hidden");
    $("#task-modal").setAttribute("aria-hidden", "true");
}

async function openEditModal(id) {
    const result = await api(`/tasks/${id}`);
    if (result.code !== 200) {
        showToast(normalizeMessage(result.message, "获取任务失败"), "error");
        return;
    }
    openTaskModal(result.data);
}

function openDeleteModal(id) {
    state.deleteTargetId = id;
    $("#delete-modal").classList.remove("hidden");
    $("#delete-modal").setAttribute("aria-hidden", "false");
}

function closeDeleteModal() {
    state.deleteTargetId = null;
    $("#delete-modal").classList.add("hidden");
    $("#delete-modal").setAttribute("aria-hidden", "true");
}

function renderExamList() {
    const container = $("#exam-list");
    if (!state.exams.length) {
        container.innerHTML = "";
        return;
    }

    container.innerHTML = state.exams.map((exam) => `
        <div class="result-item">
            <strong>${escapeHtml(exam.course)}</strong>
            <span>${escapeHtml(exam.exam_date)} ${escapeHtml(exam.exam_time || "")}</span>
        </div>
    `).join("");
}

function renderPreviewTasks() {
    const container = $("#review-preview");
    const importButton = $("#import-plan-btn");

    if (!state.previewTasks.length) {
        container.innerHTML = `<div class="result-item"><span>暂无预览任务</span></div>`;
        importButton.disabled = true;
        return;
    }

    importButton.disabled = false;
    container.innerHTML = state.previewTasks.map((task) => `
        <div class="preview-item">
            <strong>${escapeHtml(task.title)}</strong>
            <span>${escapeHtml(task.description || "无描述")}</span>
            <div class="quick-actions">
                <span class="badge status-${escapeHtml(task.status || "todo")}">${statusMap[task.status || "todo"]}</span>
                <span class="badge priority-${escapeHtml(task.priority || "medium")}">${priorityMap[task.priority || "medium"]}</span>
            </div>
        </div>
    `).join("");
}

function renderOperationLogs() {
    const container = $("#log-list");
    if (!container) return;

    if (!state.operationLogs.length) {
        container.innerHTML = `<div class="result-item"><span>暂无 AI 操作日志</span></div>`;
        return;
    }

    container.innerHTML = state.operationLogs.map((log) => {
        let detail = "";
        if (typeof log.detail === "string" && log.detail.trim()) {
            try {
                const parsed = JSON.parse(log.detail);
                detail = Object.entries(parsed)
                    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : value}`)
                    .join(" | ");
            } catch {
                detail = log.detail;
            }
        }

        return `
            <div class="result-item">
                <strong>${escapeHtml(log.action || "未知操作")}</strong>
                <span>${formatDate(log.created_at)}${log.target_type ? ` · ${escapeHtml(log.target_type)}` : ""}</span>
                ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
            </div>
        `;
    }).join("");
}

async function loadOperationLogs() {
    const result = await api("/ai/operation_logs?page=1&size=10");
    if (result.code === 401) {
        logout();
        showInlineMessage($("#auth-msg"), "登录已失效，请重新登录", "error");
        result.authExpired = true;
        return result;
    }

    if (result.code !== 200) {
        state.operationLogs = [];
        renderOperationLogs();
        return result;
    }

    state.operationLogs = result.data?.list || [];
    renderOperationLogs();
    return result;
}

async function executeAiCommand() {
    const input = $("#ai-input");
    const text = input.value.trim();
    const resultBox = $("#ai-result");
    if (!text) {
        showInlineMessage(resultBox, "请输入命令", "error");
        return;
    }

    const button = $("#ai-btn");
    setBusy(button, true, "执行中");
    hideInlineMessage(resultBox);

    const result = await api("/ai/command", {
        method: "POST",
        body: JSON.stringify({ text }),
    });

    setBusy(button, false);

    if (result.code === 200) {
        input.value = "";
        showInlineMessage(resultBox, normalizeMessage(result.message, "执行成功"), "success");
        await loadDashboard();
        return;
    }

    showInlineMessage(resultBox, normalizeMessage(result.message, "执行失败"), "error");
}

async function parseExamSchedule() {
    const text = $("#exam-text").value.trim();
    if (!text) {
        showToast("请先输入考试安排", "error");
        return;
    }

    const button = $("#parse-exam-btn");
    setBusy(button, true, "解析中");

    const result = await api("/ai/parse-exam-schedule", {
        method: "POST",
        body: JSON.stringify({ text }),
    });

    setBusy(button, false);

    if (result.code !== 200) {
        showToast(normalizeMessage(result.message, "解析失败，请检查大模型配置"), "error");
        return;
    }

    state.exams = result.data?.exams || [];
    state.previewTasks = [];
    renderExamList();
    renderPreviewTasks();
    showToast(`已解析 ${state.exams.length} 门考试`);
}

async function previewReviewPlan() {
    if (!state.exams.length) {
        showToast("请先解析考试安排", "error");
        return;
    }

    const button = $("#preview-plan-btn");
    setBusy(button, true, "生成中");

    const result = await api("/ai/preview-review-plan", {
        method: "POST",
        body: JSON.stringify({ exams: state.exams }),
    });

    setBusy(button, false);

    if (result.code !== 200) {
        showToast(normalizeMessage(result.message, "生成预览失败，请检查大模型配置"), "error");
        return;
    }

    state.previewTasks = result.data?.tasks_preview || [];
    renderPreviewTasks();
    showToast(`已生成 ${state.previewTasks.length} 条预览任务`);
}

async function importPreviewTasks() {
    if (!state.previewTasks.length) return;

    const button = $("#import-plan-btn");
    setBusy(button, true, "导入中");
    const result = await api("/ai/confirm-review-plan", {
        method: "POST",
        body: JSON.stringify({ tasks_preview: state.previewTasks }),
    });
    setBusy(button, false);

    if (result.code !== 200) {
        showToast(normalizeMessage(result.message, "导入失败"), "error");
        return;
    }

    const createdCount = result.data?.created_count ?? state.previewTasks.length;
    state.previewTasks = [];
    renderPreviewTasks();
    await loadDashboard();
    showToast(`已通过确认接口导入 ${createdCount} 条任务`);
}

async function loadA3Dashboard() {
    if (!localStorage.getItem("token")) return;
    await Promise.all([loadCurrentProfile(), loadResources(), loadQuizzes()]);
    updateA3Overview();
}

function switchA3Page(target = "overview") {
    state.a3Page = target;
    $$(".chapter-link").forEach((button) => {
        button.classList.toggle("active", button.dataset.a3Page === target);
    });
    $$(".a3-subpage").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.a3Panel === target);
    });
    updateA3Overview();
    updateTopNavState();
}

function updateA3Overview() {
    const profileMeta = $("#profile-current-meta")?.textContent || "加载中";
    const profileStatus = profileMeta.includes("暂无")
        ? "未建立"
        : profileMeta.includes("加载")
            ? "加载中"
            : "已建立";
    const planCount = Array.isArray(state.studyPlanPreview?.tasks_preview)
        ? state.studyPlanPreview.tasks_preview.length
        : 0;

    setText("#overview-profile-status", profileStatus);
    setText("#overview-profile-note", profileMeta);
    setText("#overview-plan-status", planCount ? `${planCount} 项` : "待生成");
    setText("#overview-resource-total", `${state.resourcesTotal || 0} 条`);
    setText("#overview-resource-note", `共 ${state.resourcesTotal || 0} 条`);
    setText("#overview-quiz-total", `${state.quizzesTotal || 0} 套`);
    setText("#overview-quiz-note", `共 ${state.quizzesTotal || 0} 套`);
}

function renderStudyPlanPreview(plan = state.studyPlanPreview) {
    const container = $("#study-plan-result");
    const meta = $("#study-plan-meta");
    const confirmButton = $("#confirm-study-plan-btn");

    if (!container || !meta || !confirmButton) return;

    if (!plan || !Array.isArray(plan.tasks_preview) || !plan.tasks_preview.length) {
        meta.textContent = "根据课程、知识点和画像生成";
        container.className = "plan-preview empty-detail";
        container.innerHTML = `<span>尚未生成学习计划</span>`;
        confirmButton.disabled = true;
        updateA3Overview();
        return;
    }

    const tasks = plan.tasks_preview;
    const metaParts = [
        plan.course_name || "",
        plan.topic || "",
        plan.days ? `${plan.days} 天` : "",
    ].filter(Boolean);

    meta.textContent = metaParts.join(" · ") || "学习计划预览";
    container.className = "plan-preview";
    container.innerHTML = `
        <div class="plan-summary">
            <strong>${escapeHtml(plan.plan_title || "学习计划")}</strong>
            <span class="plan-summary-meta">共 ${tasks.length} 条任务</span>
        </div>
        <div class="plan-task-list">
            ${tasks.map((task, index) => `
                <article>
                    <div class="plan-task-head">
                        <strong>第 ${index + 1} 项 · ${escapeHtml(task.title || "未命名任务")}</strong>
                        <div class="plan-task-meta">
                            <span class="badge status-${escapeHtml(task.status || "todo")}">${statusMap[task.status || "todo"]}</span>
                            <span class="badge priority-${escapeHtml(task.priority || "medium")}">${priorityMap[task.priority || "medium"]}</span>
                        </div>
                    </div>
                    <p>${renderMultiline(task.description || "无描述")}</p>
                </article>
            `).join("")}
        </div>
    `;
    confirmButton.disabled = false;
    updateA3Overview();
}

async function previewStudyPlan() {
    const courseName = $("#plan-course").value.trim();
    const topic = $("#plan-topic").value.trim();
    const days = Number($("#plan-days").value);
    const messageBox = $("#study-plan-msg");

    if (!courseName || !topic) {
        showInlineMessage(messageBox, "请输入课程名和知识点", "error");
        return;
    }

    if (!Number.isInteger(days) || days < 1 || days > 7) {
        showInlineMessage(messageBox, "计划天数需在 1 到 7 之间", "error");
        return;
    }

    const button = $("#preview-study-plan-btn");
    setBusy(button, true, "生成中");
    hideInlineMessage(messageBox);

    const result = await api("/plans/preview", {
        method: "POST",
        body: JSON.stringify({
            course_name: courseName,
            topic,
            days,
        }),
    });

    setBusy(button, false);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        showInlineMessage(messageBox, normalizeMessage(result.message, "生成学习计划失败"), "error");
        return;
    }

    state.studyPlanPreview = result.data || null;
    renderStudyPlanPreview();
    showInlineMessage(messageBox, normalizeMessage(result.message, "生成学习计划成功"), "success");
}

async function confirmStudyPlan() {
    const preview = state.studyPlanPreview;
    const tasksPreview = Array.isArray(preview?.tasks_preview) ? preview.tasks_preview : [];
    const messageBox = $("#study-plan-msg");

    if (!tasksPreview.length) {
        showInlineMessage(messageBox, "请先生成学习计划预览", "error");
        return;
    }

    const button = $("#confirm-study-plan-btn");
    setBusy(button, true, "导入中");
    hideInlineMessage(messageBox);

    const result = await api("/plans/confirm", {
        method: "POST",
        body: JSON.stringify({ tasks_preview: tasksPreview }),
    });

    setBusy(button, false);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        showInlineMessage(messageBox, normalizeMessage(result.message, "导入学习计划失败"), "error");
        return;
    }

    const createdCount = Number(result.data?.created_count ?? tasksPreview.length);
    const expectedCount = tasksPreview.length;
    await loadDashboard();

    if (createdCount >= expectedCount) {
        state.studyPlanPreview = null;
        renderStudyPlanPreview();
        showInlineMessage(messageBox, normalizeMessage(result.message, `已导入 ${createdCount} 条任务`), "success");
        return;
    }

    renderStudyPlanPreview();
    showInlineMessage(
        messageBox,
        `后端已返回创建 ${createdCount}/${expectedCount} 条任务，预览已保留，请按当前后端结果继续处理。`,
        "error",
    );
}

function renderCurrentProfile(payload) {
    const meta = $("#profile-current-meta");
    const box = $("#profile-current-json");

    if (!payload) {
        meta.textContent = "暂无画像";
        box.textContent = "暂无画像";
        updateA3Overview();
        return;
    }

    const profile = payload.profile || payload;
    const updatedAt = payload.updated_at || payload.created_at;
    meta.textContent = updatedAt ? `更新于 ${formatDate(updatedAt)}` : "已保存";
    box.textContent = prettyJson(profile);
    updateA3Overview();
}

async function loadCurrentProfile() {
    const result = await api("/profiles/me");
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        $("#profile-current-meta").textContent = "获取失败";
        $("#profile-current-json").textContent = normalizeMessage(result.message, "获取学生画像失败");
        updateA3Overview();
        return;
    }

    renderCurrentProfile(result.data);
}

async function generateProfile() {
    const input = $("#profile-text");
    const text = input.value.trim();
    const messageBox = $("#profile-msg");
    const resultBox = $("#profile-generate-result");

    if (!text) {
        showInlineMessage(messageBox, "请输入学生描述", "error");
        return;
    }

    const button = $("#generate-profile-btn");
    setBusy(button, true, "生成中");
    hideInlineMessage(messageBox);

    const result = await api("/profiles/generate", {
        method: "POST",
        body: JSON.stringify({ text }),
    });

    setBusy(button, false);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        showInlineMessage(messageBox, normalizeMessage(result.message, "生成学生画像失败"), "error");
        return;
    }

    resultBox.textContent = prettyJson(result.data);
    resultBox.classList.remove("hidden");
    showInlineMessage(messageBox, normalizeMessage(result.message, "生成学生画像成功"), "success");
    await loadCurrentProfile();
}

function getResourceViewModel(resource) {
    const nested = resource?.resource || {};
    return {
        id: resource?.id || nested.id,
        title: resource?.title || nested.title || "未命名资源",
        course_name: resource?.course_name || nested.course_name || "",
        topic: resource?.topic || nested.topic || "",
        created_at: resource?.created_at || nested.created_at,
        content: resource?.content || nested.content || "",
        key_points: resource?.key_points || nested.key_points || [],
        examples: resource?.examples || nested.examples || [],
        raw: resource,
    };
}

function renderResourceSnapshot(resource) {
    const item = getResourceViewModel(resource);
    return `
        <div class="resource-snapshot">
            <strong>${escapeHtml(item.title)}</strong>
            <span class="resource-meta">${escapeHtml(item.course_name || "-")} · ${escapeHtml(item.topic || "-")}</span>
            <section>
                <h4>内容</h4>
                <p>${renderMultiline(item.content)}</p>
            </section>
            <section>
                <h4>关键点</h4>
                ${renderPlainList(item.key_points)}
            </section>
            <section>
                <h4>示例</h4>
                ${renderPlainList(item.examples)}
            </section>
        </div>
    `;
}

async function fetchResources(page = 1, size = 10) {
    const params = new URLSearchParams({ page: String(page), size: String(size) });
    return api(`/resources?${params.toString()}`);
}

async function loadResources() {
    const result = await fetchResources(1, 10);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        state.resources = [];
        state.resourcesTotal = 0;
        renderResourceList(0);
        $("#resource-list-meta").textContent = normalizeMessage(result.message, "获取学习资源失败");
        updateA3Overview();
        return;
    }

    const data = result.data || {};
    const list = data.list || data.items || (Array.isArray(data) ? data : []);
    state.resources = list;
    state.resourcesTotal = data.total ?? list.length;
    renderResourceList();
    updateA3Overview();
}

function renderResourceList(total = state.resourcesTotal) {
    const tbody = $("#resource-tbody");
    const tableWrap = $(".resource-table-wrap");
    const empty = $("#resource-empty");

    $("#resource-list-meta").textContent = `共 ${total} 条`;
    updateA3Overview();

    if (!state.resources.length) {
        tbody.innerHTML = "";
        tableWrap.classList.add("hidden");
        empty.classList.remove("hidden");
        return;
    }

    tableWrap.classList.remove("hidden");
    empty.classList.add("hidden");
    tbody.innerHTML = state.resources.map((resource) => {
        const active = String(resource.id) === String(state.selectedResourceId) ? "active" : "";
        return `
            <tr class="clickable-row ${active}" tabindex="0" data-resource-id="${escapeHtml(resource.id)}">
                <td><strong>${escapeHtml(resource.title || "未命名资源")}</strong></td>
                <td>${escapeHtml(resource.course_name || "-")}</td>
                <td>${escapeHtml(resource.topic || "-")}</td>
                <td>${formatDate(resource.created_at)}</td>
            </tr>
        `;
    }).join("");
}

function renderResourceDetail(resource = null) {
    const container = $("#resource-detail");
    const meta = $("#resource-detail-meta");

    if (!resource) {
        meta.textContent = "点击列表项查看";
        container.className = "resource-detail empty-detail";
        container.innerHTML = `<span>尚未选择学习资源</span>`;
        return;
    }

    const item = getResourceViewModel(resource);
    const metaParts = [item.course_name, item.topic, item.created_at ? formatDate(item.created_at) : ""].filter(Boolean);
    meta.textContent = metaParts.length ? metaParts.join(" · ") : "资源详情";
    container.className = "resource-detail";
    container.innerHTML = renderResourceSnapshot(item.raw);
}

async function openResourceDetail(id) {
    state.selectedResourceId = id;
    renderResourceList();
    $("#resource-detail-meta").textContent = "加载中";
    $("#resource-detail").className = "resource-detail empty-detail";
    $("#resource-detail").innerHTML = `<span>正在加载...</span>`;

    const result = await api(`/resources/${id}`);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        renderResourceDetail();
        showToast(normalizeMessage(result.message, "获取学习资源详情失败"), "error");
        return;
    }

    renderResourceDetail(result.data);
    renderResourceList();
}

async function generateResource() {
    const courseName = $("#resource-course").value.trim();
    const topic = $("#resource-topic").value.trim();
    const messageBox = $("#resource-generate-msg");
    const resultBox = $("#resource-generate-result");

    if (!courseName || !topic) {
        showInlineMessage(messageBox, "请输入课程名和知识点", "error");
        return;
    }

    const button = $("#generate-resource-btn");
    setBusy(button, true, "生成中");
    hideInlineMessage(messageBox);

    const result = await api("/resources/generate", {
        method: "POST",
        body: JSON.stringify({ course_name: courseName, topic }),
    });

    setBusy(button, false);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        showInlineMessage(messageBox, normalizeMessage(result.message, "生成学习资源失败"), "error");
        return;
    }

    const generatedResource = {
        ...result.data,
        course_name: result.data?.course_name || courseName,
        topic: result.data?.topic || topic,
    };
    resultBox.innerHTML = renderResourceSnapshot(generatedResource);
    showInlineMessage(messageBox, normalizeMessage(result.message, "生成学习资源成功"), "success");
    await loadResources();
    if (result.data?.id) {
        await openResourceDetail(result.data.id);
    }
}

function renderQuiz(quiz = null) {
    const container = $("#quiz-result");
    if (!quiz) {
        container.innerHTML = "";
        return;
    }
    container.innerHTML = renderQuizSnapshot(quiz);
}

function getQuizViewModel(quiz) {
    const nested = quiz?.quiz_set || quiz?.quiz_json || {};
    const nestedQuestions = Array.isArray(nested.questions) ? nested.questions : [];
    const directQuestions = Array.isArray(quiz?.questions) ? quiz.questions : [];
    return {
        id: quiz?.id || nested.id,
        title: quiz?.title || nested.title || "未命名题集",
        course_name: quiz?.course_name || nested.course_name || "",
        topic: quiz?.topic || nested.topic || "",
        created_at: quiz?.created_at || nested.created_at,
        questions: nestedQuestions.length ? nestedQuestions : directQuestions,
        raw: quiz,
    };
}

function renderQuizSnapshot(quiz) {
    const item = getQuizViewModel(quiz);
    const questions = normalizeListValue(item.questions);

    return `
        <div class="quiz-title">
            <strong>${escapeHtml(item.title)}</strong>
            <span>${escapeHtml(item.course_name || "-")} · ${escapeHtml(item.topic || "-")}</span>
        </div>
        <div class="quiz-question-list">
            ${questions.length ? questions.map((question, index) => {
                const meta = [question.question_type, question.difficulty].filter(Boolean).join(" · ");
                return `
                    <article class="quiz-question">
                        <div class="quiz-question-head">
                            <strong>第 ${index + 1} 题</strong>
                            ${meta ? `<span>${escapeHtml(meta)}</span>` : ""}
                        </div>
                        <p>${renderMultiline(question.question || question)}</p>
                        ${question.options ? `<div class="quiz-options">${renderPlainList(question.options)}</div>` : ""}
                        ${question.answer ? `<div class="quiz-answer"><span>答案</span><p>${renderMultiline(question.answer)}</p></div>` : ""}
                    </article>
                `;
            }).join("") : `<pre class="json-box">${escapeHtml(prettyJson(item.raw || quiz))}</pre>`}
        </div>
    `;
}

async function fetchQuizzes(page = 1, size = 10) {
    const params = new URLSearchParams({ page: String(page), size: String(size) });
    return api(`/quizzes?${params.toString()}`);
}

async function loadQuizzes() {
    const result = await fetchQuizzes(1, 10);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        state.quizzes = [];
        state.quizzesTotal = 0;
        renderQuizList();
        $("#quiz-list-meta").textContent = normalizeMessage(result.message, "获取题集列表失败");
        updateA3Overview();
        return;
    }

    const data = result.data || {};
    const list = data.list || data.items || (Array.isArray(data) ? data : []);
    state.quizzes = list;
    state.quizzesTotal = data.total ?? list.length;
    renderQuizList();
    updateA3Overview();
}

function renderQuizList(total = state.quizzesTotal) {
    const tbody = $("#quiz-tbody");
    const tableWrap = $(".quiz-table-wrap");
    const empty = $("#quiz-empty");

    $("#quiz-list-meta").textContent = `共 ${total} 条`;
    updateA3Overview();

    if (!state.quizzes.length) {
        tbody.innerHTML = "";
        tableWrap.classList.add("hidden");
        empty.classList.remove("hidden");
        return;
    }

    tableWrap.classList.remove("hidden");
    empty.classList.add("hidden");
    tbody.innerHTML = state.quizzes.map((quiz) => {
        const active = String(quiz.id) === String(state.selectedQuizId) ? "active" : "";
        return `
            <tr class="clickable-row ${active}" tabindex="0" data-quiz-id="${escapeHtml(quiz.id)}">
                <td><strong>${escapeHtml(quiz.title || "未命名题集")}</strong></td>
                <td>${escapeHtml(quiz.course_name || "-")}</td>
                <td>${escapeHtml(quiz.topic || "-")}</td>
                <td>${formatDate(quiz.created_at)}</td>
            </tr>
        `;
    }).join("");
}

function renderQuizDetail(quiz = null) {
    const container = $("#quiz-detail");
    const meta = $("#quiz-detail-meta");

    if (!quiz) {
        meta.textContent = "点击列表项查看";
        container.className = "quiz-box empty-detail";
        container.innerHTML = `<span>尚未选择题集</span>`;
        return;
    }

    const item = getQuizViewModel(quiz);
    const metaParts = [item.course_name, item.topic, item.created_at ? formatDate(item.created_at) : ""].filter(Boolean);
    meta.textContent = metaParts.length ? metaParts.join(" · ") : "题集详情";
    container.className = "quiz-box";
    container.innerHTML = renderQuizSnapshot(item.raw);
}

async function openQuizDetail(id) {
    state.selectedQuizId = id;
    renderQuizList();
    $("#quiz-detail-meta").textContent = "加载中";
    $("#quiz-detail").className = "quiz-box empty-detail";
    $("#quiz-detail").innerHTML = `<span>正在加载...</span>`;

    const result = await api(`/quizzes/${id}`);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        renderQuizDetail();
        showToast(normalizeMessage(result.message, "获取题集详情失败"), "error");
        return;
    }

    renderQuizDetail(result.data);
    renderQuizList();
}

async function generateQuiz() {
    const courseName = $("#quiz-course").value.trim();
    const topic = $("#quiz-topic").value.trim();
    const messageBox = $("#quiz-generate-msg");

    if (!courseName || !topic) {
        showInlineMessage(messageBox, "请输入课程名和知识点", "error");
        return;
    }

    const button = $("#generate-quiz-btn");
    setBusy(button, true, "生成中");
    hideInlineMessage(messageBox);

    const result = await api("/quizzes/generate", {
        method: "POST",
        body: JSON.stringify({ course_name: courseName, topic }),
    });

    setBusy(button, false);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        showInlineMessage(messageBox, normalizeMessage(result.message, "生成练习题失败"), "error");
        return;
    }

    renderQuiz(result.data?.quiz_set || result.data);
    showInlineMessage(messageBox, normalizeMessage(result.message, "生成练习题成功"), "success");
    await loadQuizzes();
    if (result.data?.id) {
        await openQuizDetail(result.data.id);
    }
}

function renderLearningPlanSnapshot(plan) {
    const tasks = Array.isArray(plan?.tasks_preview) ? plan.tasks_preview : [];
    return `
        <div class="plan-summary">
            <strong>${escapeHtml(plan?.plan_title || "学习计划")}</strong>
            <span class="plan-summary-meta">
                ${escapeHtml(plan?.course_name || "-")} · ${escapeHtml(plan?.topic || "-")} · ${escapeHtml(plan?.days || "-")} 天 · 共 ${tasks.length} 项
            </span>
        </div>
        <div class="plan-task-list">
            ${tasks.length ? tasks.map((task, index) => `
                <article>
                    <div class="plan-task-head">
                        <strong>第 ${index + 1} 项 · ${escapeHtml(task.title || "未命名任务")}</strong>
                        <div class="plan-task-meta">
                            <span class="badge status-${escapeHtml(task.status || "todo")}">${statusMap[task.status || "todo"] || "待办"}</span>
                            <span class="badge priority-${escapeHtml(task.priority || "medium")}">${priorityMap[task.priority || "medium"] || "中"}</span>
                        </div>
                    </div>
                    <p>${renderMultiline(task.description || "无描述")}</p>
                </article>
            `).join("") : `<span class="muted-text">暂无任务预览</span>`}
        </div>
    `;
}

function renderAgentToolCards(toolResults = {}) {
    const learningPlan = toolResults.learning_plan;
    const tasksPreview = Array.isArray(learningPlan?.tasks_preview) ? learningPlan.tasks_preview : [];

    return `
        ${toolResults.resource ? `
            <section class="agent-output-block">
                <h4>生成资源</h4>
                ${renderResourceSnapshot(toolResults.resource)}
            </section>
        ` : ""}
        ${toolResults.quiz_set ? `
            <section class="agent-output-block">
                <h4>生成题集</h4>
                ${renderQuizSnapshot(toolResults.quiz_set)}
            </section>
        ` : ""}
        ${learningPlan ? `
            <section class="agent-output-block">
                <h4>学习计划预览</h4>
                ${renderLearningPlanSnapshot(learningPlan)}
                ${tasksPreview.length ? `
                    <button type="button" class="btn btn-ink agent-import-plan-btn" data-agent-action="confirm-plan">
                        导入任务中心
                    </button>
                ` : ""}
            </section>
        ` : ""}
    `;
}

function renderAgentResult(result = null) {
    if (!result) return "";

    const plan = result.plan || {};
    const toolResults = result.tool_results || {};
    const tools = Array.isArray(plan.tools) ? plan.tools : [];
    const missingFields = Array.isArray(plan.missing_fields) ? plan.missing_fields : [];
    const shouldRenderTools = plan.status === "ready_to_execute";

    return `
        <div class="agent-result-card">
            <div class="agent-result-head">
                <span class="agent-pill">${escapeHtml(agentStatusMap[plan.status] || plan.status || "未识别")}</span>
                <span>${escapeHtml(agentIntentMap[plan.intent] || plan.intent || "未知意图")}</span>
            </div>
            <div class="agent-meta-grid">
                <span>课程：${escapeHtml(plan.course_name || "待补充")}</span>
                <span>知识点：${escapeHtml(plan.topic || "待补充")}</span>
                <span>天数：${escapeHtml(plan.days || "-")}</span>
                <span>工具：${tools.length ? tools.map((tool) => escapeHtml(agentToolMap[tool] || tool)).join(" / ") : "无"}</span>
            </div>
            ${missingFields.length ? `
                <div class="agent-missing">
                    <strong>还缺少</strong>
                    <span>${missingFields.map((item) => escapeHtml(item)).join("、")}</span>
                </div>
            ` : ""}
            ${shouldRenderTools ? renderAgentToolCards(toolResults) : ""}
        </div>
    `;
}

function renderAgentMessages() {
    const container = $("#agent-thread");
    if (!container) return;

    if (!state.agentMessages.length) {
        container.innerHTML = `
            <article class="agent-message assistant">
                <div class="agent-bubble">
                    <strong>学习助手</strong>
                    <p>可以直接说出课程、知识点和目标，我会根据后端总控智能体返回的计划生成资源、题集或学习计划。</p>
                </div>
            </article>
        `;
        return;
    }

    container.innerHTML = state.agentMessages.map((message) => `
        <article class="agent-message ${escapeHtml(message.role)}">
            <div class="agent-bubble">
                <strong>${message.role === "user" ? "我" : "学习助手"}</strong>
                <p>${renderMultiline(message.content)}</p>
                ${message.result?.plan?.status === "ready_to_execute" ? renderAgentResult(message.result) : ""}
            </div>
        </article>
    `).join("");
    container.scrollTop = container.scrollHeight;
}

function renderAgentSummary(result = state.agentPlanPreview) {
    const meta = $("#agent-summary-meta");
    const container = $("#agent-summary");
    if (!meta || !container) return;

    if (!result) {
        meta.textContent = "等待对话";
        container.className = "agent-summary empty-detail";
        container.innerHTML = `<span>发送学习需求后，这里会展示意图、缺失信息和生成结果。</span>`;
        return;
    }

    const plan = result.plan || {};
    meta.textContent = `${agentStatusMap[plan.status] || plan.status || "已返回"} · ${agentIntentMap[plan.intent] || plan.intent || "未知意图"}`;
    if (plan.status === "need_more_info") {
        container.className = "agent-summary empty-detail";
        container.innerHTML = `<span>${renderMultiline(plan.reply || "请继续补充学习需求。")}</span>`;
        return;
    }
    container.className = "agent-summary";
    container.innerHTML = renderAgentResult(result);
}

async function syncAgentToolResults(result) {
    if (result?.plan?.status !== "ready_to_execute") {
        updateA3Overview();
        return;
    }

    const toolResults = result?.tool_results || {};
    const refreshes = [];

    if (toolResults.learning_plan) {
        state.studyPlanPreview = toolResults.learning_plan;
        renderStudyPlanPreview();
    }
    if (toolResults.resource) {
        refreshes.push(loadResources());
    }
    if (toolResults.quiz_set) {
        refreshes.push(loadQuizzes());
    }
    if (refreshes.length) {
        await Promise.all(refreshes);
    }
    updateA3Overview();
}

async function sendAgentMessage(event) {
    event?.preventDefault();
    const input = $("#agent-message");
    const messageBox = $("#agent-chat-msg");
    const message = input.value.trim();

    if (!message) {
        showInlineMessage(messageBox, "请输入学习需求", "error");
        return;
    }

    state.agentMessages.push({ role: "user", content: message });
    renderAgentMessages();
    input.value = "";
    hideInlineMessage(messageBox);

    const button = $("#agent-send-btn");
    setBusy(button, true, "处理中");

    const result = await api("/agent/chat", {
        method: "POST",
        body: JSON.stringify({ message }),
    });

    setBusy(button, false);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        const errorText = normalizeMessage(result.message, "对话处理失败");
        state.agentMessages.push({ role: "assistant", content: errorText });
        renderAgentMessages();
        showInlineMessage(messageBox, errorText, "error");
        return;
    }

    const payload = result.data || {};
    const reply = payload.plan?.reply || normalizeMessage(result.message, "已处理学习需求");
    state.agentPlanPreview = payload;
    state.agentMessages.push({ role: "assistant", content: reply, result: payload });
    renderAgentMessages();
    renderAgentSummary();
    await syncAgentToolResults(payload);
    showInlineMessage(messageBox, normalizeMessage(result.message, "对话处理完成"), "success");
}

async function confirmAgentPlanFromChat(event) {
    const button = event?.target?.closest?.("[data-agent-action='confirm-plan']");
    if (!button) return;

    const learningPlan = state.agentPlanPreview?.tool_results?.learning_plan;
    const tasksPreview = Array.isArray(learningPlan?.tasks_preview) ? learningPlan.tasks_preview : [];
    if (!tasksPreview.length) {
        showToast("当前对话没有可导入的学习计划", "error");
        return;
    }

    setBusy(button, true, "导入中");
    const result = await api("/plans/confirm", {
        method: "POST",
        body: JSON.stringify({ tasks_preview: tasksPreview }),
    });
    setBusy(button, false);
    if (handleAuthExpired(result)) return;

    if (result.code !== 200) {
        showToast(normalizeMessage(result.message, "导入任务中心失败"), "error");
        return;
    }

    await loadDashboard();
    const createdCount = Number(result.data?.created_count ?? tasksPreview.length);
    showToast(normalizeMessage(result.message, `已导入 ${createdCount} 条任务`));
}

function clearAgentChat() {
    state.agentMessages = [];
    state.agentPlanPreview = null;
    renderAgentMessages();
    renderAgentSummary();
    hideInlineMessage($("#agent-chat-msg"));
}

function bindEvents() {
    $$(".auth-tab").forEach((tab) => {
        tab.addEventListener("click", () => switchAuthTab(tab.dataset.authTab));
    });

    $("#login-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = event.submitter;
        const username = $("#login-username").value.trim();
        const password = $("#login-password").value;
        setBusy(button, true, "登录中");

        const result = await api("/users/login", {
            method: "POST",
            body: JSON.stringify({ username, password }),
        });

        setBusy(button, false);

        if (result.code !== 200) {
            showInlineMessage($("#auth-msg"), normalizeMessage(result.message, "登录失败"), "error");
            return;
        }

        localStorage.setItem("token", result.data.token);
        localStorage.setItem("username", username);
        $("#username-display").textContent = username;
        showPage("main");
        switchView("a3");
        await Promise.all([loadDashboard(), loadA3Dashboard()]);
    });

    $("#register-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = event.submitter;
        const username = $("#reg-username").value.trim();
        const password = $("#reg-password").value;
        const confirm = $("#reg-confirm").value;

        if (password !== confirm) {
            showInlineMessage($("#auth-msg"), "两次输入的密码不一致", "error");
            return;
        }

        setBusy(button, true, "注册中");
        const result = await api("/users/register", {
            method: "POST",
            body: JSON.stringify({ username, password }),
        });
        setBusy(button, false);

        if (result.code !== 200) {
            showInlineMessage($("#auth-msg"), normalizeMessage(result.message, "注册失败"), "error");
            return;
        }

        $("#login-username").value = username;
        $("#register-form").reset();
        switchAuthTab("login");
        showInlineMessage($("#auth-msg"), "注册成功，请登录", "success");
    });

    $$(".nav-item").forEach((item) => {
        item.addEventListener("click", () => switchView(item.dataset.view));
    });

    $$(".top-nav-link").forEach((button) => {
        button.addEventListener("click", () => {
            if (button.dataset.a3Goto) {
                switchView("a3");
                switchA3Page(button.dataset.a3Goto);
                return;
            }
            if (button.dataset.view) {
                switchView(button.dataset.view);
            }
        });
    });

    $$("[data-view]:not(.nav-item):not(.top-nav-link)").forEach((button) => {
        button.addEventListener("click", () => switchView(button.dataset.view));
    });

    $$(".chapter-link").forEach((button) => {
        button.addEventListener("click", () => {
            switchView("a3");
            switchA3Page(button.dataset.a3Page);
        });
    });

    $$("[data-a3-goto]:not(.top-nav-link)").forEach((button) => {
        button.addEventListener("click", () => {
            switchView("a3");
            switchA3Page(button.dataset.a3Goto);
        });
    });

    $("#logout-btn").addEventListener("click", logout);
    $("#refresh-btn").addEventListener("click", () => {
        const activeView = $(".nav-item.active")?.dataset.view;
        if (activeView === "a3") {
            loadA3Dashboard();
            return;
        }
        loadDashboard();
    });
    $("#add-task-btn").addEventListener("click", () => openTaskModal());

    $("#status-filter").addEventListener("change", (event) => {
        state.status = event.target.value;
        state.page = 1;
        loadTasks();
    });

    $("#priority-filter").addEventListener("change", (event) => {
        state.priority = event.target.value;
        state.page = 1;
        loadTasks();
    });

    $("#page-size").addEventListener("change", (event) => {
        state.pageSize = Number(event.target.value);
        state.page = 1;
        loadTasks();
    });

    let searchTimer = null;
    $("#task-search").addEventListener("input", (event) => {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => {
            state.query = event.target.value;
            state.page = 1;
            loadTasks();
        }, 220);
    });

    $("#prev-page").addEventListener("click", () => {
        if (state.page <= 1) return;
        state.page -= 1;
        loadTasks();
    });

    $("#next-page").addEventListener("click", () => {
        const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
        if (state.page >= totalPages) return;
        state.page += 1;
        loadTasks();
    });

    $("#task-tbody").addEventListener("click", (event) => {
        const button = event.target.closest("button[data-action]");
        if (!button) return;
        if (button.dataset.action === "edit") openEditModal(button.dataset.id);
        if (button.dataset.action === "delete") openDeleteModal(button.dataset.id);
    });

    $$(".modal-close").forEach((button) => button.addEventListener("click", closeTaskModal));
    $("#task-modal").addEventListener("click", (event) => {
        if (event.target === $("#task-modal")) closeTaskModal();
    });

    $("#task-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const id = $("#task-id").value;
        const payload = {
            title: $("#task-title").value.trim(),
            description: $("#task-desc").value.trim(),
            status: $("#task-status").value,
            priority: $("#task-priority").value,
        };

        if (!payload.title) {
            showToast("标题不能为空", "error");
            return;
        }

        const button = event.submitter;
        setBusy(button, true, "保存中");
        const result = await api(id ? `/tasks/${id}` : "/tasks", {
            method: id ? "PUT" : "POST",
            body: JSON.stringify(payload),
        });
        setBusy(button, false);

        if (result.code !== 200) {
            showToast(normalizeMessage(result.message, "保存失败"), "error");
            return;
        }

        closeTaskModal();
        showToast(id ? "任务已更新" : "任务已创建");
        await loadDashboard();
    });

    $("#delete-cancel").addEventListener("click", closeDeleteModal);
    $("#delete-cancel-x").addEventListener("click", closeDeleteModal);
    $("#delete-modal").addEventListener("click", (event) => {
        if (event.target === $("#delete-modal")) closeDeleteModal();
    });

    $("#delete-confirm").addEventListener("click", async () => {
        if (!state.deleteTargetId) return;
        const result = await api(`/tasks/${state.deleteTargetId}`, { method: "DELETE" });
        if (result.code !== 200) {
            showToast(normalizeMessage(result.message, "删除失败"), "error");
            return;
        }
        closeDeleteModal();
        showToast("任务已删除");
        await loadDashboard();
    });

    $("#ai-btn").addEventListener("click", executeAiCommand);
    $("#ai-input").addEventListener("keydown", (event) => {
        if (event.key === "Enter") executeAiCommand();
    });

    $$(".chip[data-command]").forEach((chip) => {
        chip.addEventListener("click", () => {
            $("#ai-input").value = chip.dataset.command;
            $("#ai-input").focus();
        });
    });

    $("#parse-exam-btn").addEventListener("click", parseExamSchedule);
    $("#preview-plan-btn").addEventListener("click", previewReviewPlan);
    $("#import-plan-btn").addEventListener("click", importPreviewTasks);
    $("#refresh-logs-btn").addEventListener("click", () => loadOperationLogs());

    $("#refresh-profile-btn").addEventListener("click", loadCurrentProfile);
    $("#generate-profile-btn").addEventListener("click", generateProfile);
    $("#refresh-resources-btn").addEventListener("click", loadResources);
    $("#refresh-quizzes-btn").addEventListener("click", loadQuizzes);
    $("#preview-study-plan-btn").addEventListener("click", previewStudyPlan);
    $("#confirm-study-plan-btn").addEventListener("click", confirmStudyPlan);
    $("#generate-resource-btn").addEventListener("click", generateResource);
    $("#generate-quiz-btn").addEventListener("click", generateQuiz);
    $("#agent-chat-form").addEventListener("submit", sendAgentMessage);
    $("#clear-agent-chat-btn").addEventListener("click", clearAgentChat);
    $("#agent-thread").addEventListener("click", confirmAgentPlanFromChat);
    $("#agent-summary").addEventListener("click", confirmAgentPlanFromChat);
    $("#agent-message").addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            sendAgentMessage(event);
        }
    });
    $$("[data-agent-prompt]").forEach((button) => {
        button.addEventListener("click", () => {
            $("#agent-message").value = button.dataset.agentPrompt;
            $("#agent-message").focus();
        });
    });

    $("#resource-tbody").addEventListener("click", (event) => {
        const row = event.target.closest("tr[data-resource-id]");
        if (!row) return;
        openResourceDetail(row.dataset.resourceId);
    });

    $("#resource-tbody").addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const row = event.target.closest("tr[data-resource-id]");
        if (!row) return;
        event.preventDefault();
        openResourceDetail(row.dataset.resourceId);
    });

    $("#quiz-tbody").addEventListener("click", (event) => {
        const row = event.target.closest("tr[data-quiz-id]");
        if (!row) return;
        openQuizDetail(row.dataset.quizId);
    });

    $("#quiz-tbody").addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const row = event.target.closest("tr[data-quiz-id]");
        if (!row) return;
        event.preventDefault();
        openQuizDetail(row.dataset.quizId);
    });
}

bindEvents();
renderPreviewTasks();
renderOperationLogs();
renderResourceList();
renderResourceDetail();
renderQuizList();
renderQuizDetail();
renderQuiz();
renderStudyPlanPreview();
renderAgentMessages();
renderAgentSummary();
switchA3Page("overview");
checkAuth();
