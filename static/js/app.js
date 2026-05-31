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

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

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

function switchView(target) {
    $$(".nav-item").forEach((item) => {
        item.classList.toggle("active", item.dataset.view === target);
    });
    $$(".view").forEach((view) => {
        view.classList.toggle("active", view.id === `${target}-view`);
    });
    $("#workspace-title").textContent = target === "ai" ? "AI 复习计划" : "任务中心";
}

function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    state.tasks = [];
    state.exams = [];
    state.previewTasks = [];
    $("#login-form").reset();
    $("#register-form").reset();
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
    loadDashboard();
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
        await loadDashboard();
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

    $("#logout-btn").addEventListener("click", logout);
    $("#refresh-btn").addEventListener("click", () => loadDashboard());
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
}

bindEvents();
renderPreviewTasks();
renderOperationLogs();
checkAuth();
