<script setup>
import { ref, computed, onMounted } from 'vue'
import { getTasks, createTask, updateTask, deleteTask } from '../api/tasks'
import { showToast } from '../components/common/toast'
import EmptyState from '../components/common/EmptyState.vue'
import LoadingState from '../components/common/LoadingState.vue'
import Modal from '../components/common/Modal.vue'
import { CheckSquare, Edit3, Plus, Trash2 } from 'lucide-vue-next'

const tasks = ref([])
const total = ref(0)
const loading = ref(false)

const statusFilter = ref('')
const priorityFilter = ref('')
const query = ref('')

const showModal = ref(false)
const editingTask = ref(null)
const form = ref({ title: '', description: '', status: 'todo', priority: 'medium' })
const saving = ref(false)

const deleteTarget = ref(null)

const statusMap = { todo: '待办', doing: '进行中', done: '已完成' }
const priorityMap = { low: '低', medium: '中', high: '高' }

const filteredTasks = computed(() => {
  let result = tasks.value
  if (statusFilter.value) {
    result = result.filter(t => t.status === statusFilter.value)
  }
  if (priorityFilter.value) {
    result = result.filter(t => t.priority === priorityFilter.value)
  }
  if (query.value) {
    const q = query.value.toLowerCase()
    result = result.filter(t =>
      (t.title || '').toLowerCase().includes(q) ||
      (t.description || '').toLowerCase().includes(q)
    )
  }
  return result
})

const stats = computed(() => {
  const all = tasks.value
  return {
    total: all.length,
    todo: all.filter(t => t.status === 'todo').length,
    doing: all.filter(t => t.status === 'doing').length,
    done: all.filter(t => t.status === 'done').length
  }
})

onMounted(() => {
  loadTasks()
})

async function loadTasks() {
  loading.value = true
  const res = await getTasks({ page: 1, size: 100 })
  loading.value = false
  if (res.code === 200) {
    tasks.value = res.data?.list || res.data?.items || res.data || []
    total.value = res.data?.total || tasks.value.length
  }
}

function openCreate() {
  editingTask.value = null
  form.value = { title: '', description: '', status: 'todo', priority: 'medium' }
  showModal.value = true
}

function openEdit(task) {
  editingTask.value = task
  form.value = {
    title: task.title || '',
    description: task.description || '',
    status: task.status || 'todo',
    priority: task.priority || 'medium'
  }
  showModal.value = true
}

async function handleSave() {
  if (!form.value.title) {
    showToast({ type: 'warning', message: '请填写任务标题' })
    return
  }

  saving.value = true
  let res

  if (editingTask.value) {
    res = await updateTask(editingTask.value.task_id || editingTask.value.id, form.value)
  } else {
    res = await createTask(form.value)
  }

  saving.value = false

  if (res.code === 200 || res.code === 201) {
    showToast({ type: 'success', message: editingTask.value ? '更新成功' : '创建成功' })
    showModal.value = false
    loadTasks()
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

async function toggleStatus(task) {
  const nextStatus = task.status === 'done' ? 'todo' : task.status === 'todo' ? 'doing' : 'done'
  const res = await updateTask(task.task_id || task.id, { status: nextStatus })
  if (res.code === 200) {
    task.status = nextStatus
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

function confirmDelete(task) {
  deleteTarget.value = task
}

async function handleDelete() {
  if (!deleteTarget.value) return
  const res = await deleteTask(deleteTarget.value.task_id || deleteTarget.value.id)
  if (res.code === 200) {
    showToast({ type: 'success', message: '删除成功' })
    deleteTarget.value = null
    loadTasks()
  } else {
    showToast({ type: 'error', message: res.message })
  }
}
</script>

<template>
  <div class="tasks-page">
    <div class="tasks-header">
      <div>
        <h1>任务中心</h1>
      </div>
      <div class="tasks-stats">
        <div class="task-stat">
          <div class="task-stat-value">{{ stats.total }}</div>
          <div class="task-stat-label">总计</div>
        </div>
        <div class="task-stat">
          <div class="task-stat-value">{{ stats.todo }}</div>
          <div class="task-stat-label">待办</div>
        </div>
        <div class="task-stat">
          <div class="task-stat-value">{{ stats.doing }}</div>
          <div class="task-stat-label">进行中</div>
        </div>
        <div class="task-stat">
          <div class="task-stat-value">{{ stats.done }}</div>
          <div class="task-stat-label">已完成</div>
        </div>
      </div>
      <button class="btn btn-primary" @click="openCreate">
        <Plus :size="16" />
        新建任务
      </button>
    </div>

    <div class="tasks-filters">
      <div class="filter-group">
        <label class="filter-label">状态</label>
        <select v-model="statusFilter" class="filter-select">
          <option value="">全部</option>
          <option value="todo">待办</option>
          <option value="doing">进行中</option>
          <option value="done">已完成</option>
        </select>
      </div>
      <div class="filter-group">
        <label class="filter-label">优先级</label>
        <select v-model="priorityFilter" class="filter-select">
          <option value="">全部</option>
          <option value="low">低</option>
          <option value="medium">中</option>
          <option value="high">高</option>
        </select>
      </div>
      <div class="filter-group task-search">
        <input
          v-model="query"
          class="form-input"
          placeholder="搜索任务..."
        />
      </div>
    </div>

    <LoadingState v-if="loading" />

    <EmptyState
      v-else-if="filteredTasks.length === 0"
      :icon="CheckSquare"
      title="暂无任务"
      desc="点击上方按钮新建任务"
    >
      <template #action>
        <button class="btn btn-primary" @click="openCreate">新建任务</button>
      </template>
    </EmptyState>

    <div v-else>
      <div
        v-for="task in filteredTasks"
        :key="task.task_id || task.id"
        class="task-row"
      >
        <div
          class="task-checkbox"
          :class="{ checked: task.status === 'done' }"
          @click="toggleStatus(task)"
        >
          <span v-if="task.status === 'done'">✓</span>
        </div>
        <div class="task-content">
          <div class="task-title" :class="{ 'task-title-done': task.status === 'done' }">
            {{ task.title }}
          </div>
          <div v-if="task.description" class="task-desc">{{ task.description }}</div>
        </div>
        <div class="task-meta">
          <span class="task-status" :class="`task-status-${task.status}`">
            {{ statusMap[task.status] || task.status }}
          </span>
          <span class="task-priority" :class="`task-priority-${task.priority}`">
            {{ priorityMap[task.priority] || task.priority }}
          </span>
        </div>
        <div class="task-actions">
          <button class="btn btn-ghost btn-sm" title="编辑任务" @click="openEdit(task)">
            <Edit3 :size="15" />
            编辑
          </button>
          <button class="btn btn-ghost btn-sm btn-danger-text" title="删除任务" @click="confirmDelete(task)">
            <Trash2 :size="15" />
            删除
          </button>
        </div>
      </div>
    </div>

    <Modal :show="showModal" :title="editingTask ? '编辑任务' : '新建任务'" @close="showModal = false">
      <div class="form-group">
        <label class="form-label">标题 *</label>
        <input v-model="form.title" class="form-input" placeholder="任务标题" />
      </div>
      <div class="form-group">
        <label class="form-label">描述</label>
        <textarea v-model="form.description" class="form-textarea" rows="3" placeholder="任务描述"></textarea>
      </div>
      <div class="task-form-grid">
        <div class="form-group">
          <label class="form-label">状态</label>
          <select v-model="form.status" class="form-select">
            <option value="todo">待办</option>
            <option value="doing">进行中</option>
            <option value="done">已完成</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">优先级</label>
          <select v-model="form.priority" class="form-select">
            <option value="low">低</option>
            <option value="medium">中</option>
            <option value="high">高</option>
          </select>
        </div>
      </div>
      <template #footer>
        <button class="btn btn-secondary" @click="showModal = false">取消</button>
        <button class="btn btn-primary" :disabled="saving" @click="handleSave">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </template>
    </Modal>

    <Modal :show="!!deleteTarget" title="确认删除" size="sm" @close="deleteTarget = null">
      <p>确定要删除任务「{{ deleteTarget?.title }}」吗？此操作不可撤销。</p>
      <template #footer>
        <button class="btn btn-secondary" @click="deleteTarget = null">取消</button>
        <button class="btn btn-accent" @click="handleDelete">删除</button>
      </template>
    </Modal>
  </div>
</template>
