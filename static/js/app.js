// API 封装
async function api(url, options = {}) {
    const token = localStorage.getItem('token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(url, {
        ...options,
        headers: { ...headers, ...options.headers }
    });
    return res.json();
}

// 状态
let currentPage = 1;
let pageSize = 10;
let currentStatus = '';

// DOM 元素
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// 页面切换
function showPage(page) {
    $$('.page').forEach(p => p.classList.add('hidden'));
    $(`#${page}-page`).classList.remove('hidden');
}

// 提示消息
function showToast(msg, type = 'success') {
    const toast = $('#toast');
    toast.textContent = msg;
    toast.className = `toast ${type}`;
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 3000);
}

// 认证消息
function showAuthMsg(msg, type = 'error') {
    const el = $('#auth-msg');
    el.textContent = msg;
    el.className = `message ${type}`;
}

// 检查登录状态
function checkAuth() {
    const token = localStorage.getItem('token');
    const username = localStorage.getItem('username');
    if (token && username) {
        $('#username-display').textContent = username;
        showPage('main');
        loadTasks();
    } else {
        showPage('auth');
    }
}

// Tab 切换
$$('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        $$('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        $$('.form').forEach(f => f.classList.remove('active'));
        $(`#${tab.dataset.tab}-form`).classList.add('active');
        $('#auth-msg').textContent = '';
    });
});

// 登录
$('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = $('#login-username').value;
    const password = $('#login-password').value;

    const res = await api('/users/login', {
        method: 'POST',
        body: JSON.stringify({ username, password })
    });

    if (res.code === 200) {
        localStorage.setItem('token', res.data.token);
        localStorage.setItem('username', username);
        $('#username-display').textContent = username;
        showPage('main');
        loadTasks();
    } else {
        showAuthMsg(res.message);
    }
});

// 注册
$('#register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = $('#reg-username').value;
    const password = $('#reg-password').value;
    const confirm = $('#reg-confirm').value;

    if (password !== confirm) {
        showAuthMsg('两次密码不一致');
        return;
    }

    const res = await api('/users/register', {
        method: 'POST',
        body: JSON.stringify({ username, password })
    });

    if (res.code === 200) {
        showAuthMsg('注册成功，请登录', 'success');
        // 切换到登录 tab
        $$('.tab').forEach(t => t.classList.remove('active'));
        $('.tab[data-tab="login"]').classList.add('active');
        $$('.form').forEach(f => f.classList.remove('active'));
        $('#login-form').classList.add('active');
        $('#login-username').value = username;
    } else {
        showAuthMsg(res.message);
    }
});

// 退出
$('#logout-btn').addEventListener('click', () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    showPage('auth');
    // 清空表单
    $('#login-form').reset();
    $('#register-form').reset();
    $('#auth-msg').textContent = '';
});

// 加载任务
async function loadTasks() {
    const params = new URLSearchParams({
        page: currentPage,
        size: pageSize
    });
    if (currentStatus) params.append('status', currentStatus);

    const res = await api(`/tasks?${params}`);

    if (res.code === 200) {
        renderTasks(res.data);
    } else if (res.code === 401) {
        localStorage.removeItem('token');
        localStorage.removeItem('username');
        showPage('auth');
        showAuthMsg('登录已过期，请重新登录');
    }
}

// 渲染任务列表
function renderTasks(data) {
    const tbody = $('#task-tbody');
    const emptyMsg = $('#empty-msg');

    if (data.list.length === 0) {
        tbody.innerHTML = '';
        emptyMsg.classList.remove('hidden');
        return;
    }

    emptyMsg.classList.add('hidden');

    const statusMap = {
        'todo': '待办',
        'doing': '进行中',
        'done': '已完成'
    };

    const priorityMap = {
        'low': '低',
        'medium': '中',
        'high': '高'
    };

    tbody.innerHTML = data.list.map(task => `
        <tr>
            <td>${task.id}</td>
            <td>${escapeHtml(task.title)}</td>
            <td>${escapeHtml(task.description || '-')}</td>
            <td><span class="status-badge status-${task.status}">${statusMap[task.status] || task.status}</span></td>
            <td><span class="priority-badge priority-${task.priority}">${priorityMap[task.priority] || task.priority}</span></td>
            <td class="actions">
                <button class="btn-secondary btn-small edit-btn" data-id="${task.id}">编辑</button>
                <button class="btn-danger btn-small delete-btn" data-id="${task.id}">删除</button>
            </td>
        </tr>
    `).join('');

    // 更新分页
    const totalPages = Math.ceil(data.total / pageSize);
    $('#page-info').textContent = `第 ${currentPage} / ${totalPages || 1} 页`;
    $('#prev-page').disabled = currentPage <= 1;
    $('#next-page').disabled = currentPage >= totalPages;

    // 绑定编辑和删除事件
    $$('.edit-btn').forEach(btn => {
        btn.addEventListener('click', () => openEditModal(btn.dataset.id));
    });
    $$('.delete-btn').forEach(btn => {
        btn.addEventListener('click', () => deleteTask(btn.dataset.id));
    });
}

// HTML 转义
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// 状态筛选
$('#status-filter').addEventListener('change', (e) => {
    currentStatus = e.target.value;
    currentPage = 1;
    loadTasks();
});

// 分页
$('#prev-page').addEventListener('click', () => {
    if (currentPage > 1) {
        currentPage--;
        loadTasks();
    }
});

$('#next-page').addEventListener('click', () => {
    currentPage++;
    loadTasks();
});

// 打开新建弹窗
$('#add-task-btn').addEventListener('click', () => {
    $('#modal-title').textContent = '新建任务';
    $('#task-form').reset();
    $('#task-id').value = '';
    $('#task-priority').value = 'medium';
    $('#task-modal').classList.remove('hidden');
});

// 打开编辑弹窗
async function openEditModal(id) {
    const res = await api(`/tasks/${id}`);
    if (res.code === 200) {
        const task = res.data;
        $('#modal-title').textContent = '编辑任务';
        $('#task-id').value = task.id;
        $('#task-title').value = task.title;
        $('#task-desc').value = task.description || '';
        $('#task-status').value = task.status;
        $('#task-priority').value = task.priority;
        $('#task-modal').classList.remove('hidden');
    } else {
        showToast(res.message, 'error');
    }
}

// 关闭弹窗
$$('.modal-close').forEach(btn => {
    btn.addEventListener('click', () => {
        $('#task-modal').classList.add('hidden');
    });
});

// 点击遮罩关闭
$('#task-modal').addEventListener('click', (e) => {
    if (e.target === $('#task-modal')) {
        $('#task-modal').classList.add('hidden');
    }
});

// 保存任务
$('#task-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = $('#task-id').value;
    const data = {
        title: $('#task-title').value,
        description: $('#task-desc').value,
        status: $('#task-status').value,
        priority: $('#task-priority').value
    };

    let res;
    if (id) {
        res = await api(`/tasks/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    } else {
        res = await api('/tasks', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    if (res.code === 200) {
        showToast(id ? '更新成功' : '创建成功');
        $('#task-modal').classList.add('hidden');
        loadTasks();
    } else {
        showToast(res.message, 'error');
    }
});

// 删除任务
let deleteTargetId = null;

function deleteTask(id) {
    deleteTargetId = id;
    $('#delete-modal').classList.remove('hidden');
}

$('#delete-cancel').addEventListener('click', () => {
    $('#delete-modal').classList.add('hidden');
    deleteTargetId = null;
});
$('#delete-cancel-x').addEventListener('click', () => {
    $('#delete-modal').classList.add('hidden');
    deleteTargetId = null;
});
$('#delete-modal').addEventListener('click', (e) => {
    if (e.target === $('#delete-modal')) {
        $('#delete-modal').classList.add('hidden');
        deleteTargetId = null;
    }
});
$('#delete-confirm').addEventListener('click', async () => {
    if (!deleteTargetId) return;
    const id = deleteTargetId;
    $('#delete-modal').classList.add('hidden');
    deleteTargetId = null;

    const res = await api(`/tasks/${id}`, { method: 'DELETE' });
    if (res.code === 200) {
        showToast('删除成功');
        loadTasks();
    } else {
        showToast(res.message, 'error');
    }
});

// AI 指令
$('#ai-btn').addEventListener('click', executeAiCommand);
$('#ai-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') executeAiCommand();
});

async function executeAiCommand() {
    const input = $('#ai-input');
    const text = input.value.trim();
    if (!text) return;

    const resultDiv = $('#ai-result');
    resultDiv.classList.add('hidden');

    const res = await api('/ai/command', {
        method: 'POST',
        body: JSON.stringify({ text })
    });

    resultDiv.classList.remove('hidden');
    if (res.code === 200) {
        resultDiv.className = 'ai-result success';
        resultDiv.textContent = res.message;
        input.value = '';
        loadTasks();
    } else {
        resultDiv.className = 'ai-result error';
        resultDiv.textContent = res.message;
    }
}

// 初始化
checkAuth();
