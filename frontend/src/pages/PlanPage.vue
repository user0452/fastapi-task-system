<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { previewPlan, confirmPlan } from '../api/plans'
import { showToast } from '../components/common/toast'
import EmptyState from '../components/common/EmptyState.vue'
import { CalendarDays } from 'lucide-vue-next'

const router = useRouter()

const form = ref({
  course_name: '',
  topic: '',
  days: 3
})
const previewing = ref(false)
const plan = ref(null)

const importing = ref(false)

async function handlePreview() {
  if (!form.value.course_name) {
    showToast({ type: 'warning', message: '请填写课程名' })
    return
  }
  if (!form.value.topic) {
    showToast({ type: 'warning', message: '请填写主题' })
    return
  }

  previewing.value = true
  const res = await previewPlan({
    course_name: form.value.course_name,
    topic: form.value.topic,
    days: form.value.days
  })
  previewing.value = false

  if (res.code === 200 && res.data) {
    plan.value = res.data
    showToast({ type: 'success', message: '计划预览生成成功' })
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

async function handleImport() {
  if (!plan.value) return

  importing.value = true
  const res = await confirmPlan({
    tasks_preview: plan.value.tasks_preview || []
  })
  importing.value = false

  if (res.code === 200) {
    const count = res.data?.created_count ?? res.data?.task_count ?? res.data?.tasks?.length ?? '?'
    showToast({ type: 'success', message: `成功导入 ${count} 个任务` })
    if (confirm('是否跳转到任务中心查看？')) {
      router.push('/tasks')
    }
  } else {
    showToast({ type: 'error', message: res.message })
  }
}
</script>

<template>
  <div class="plan-page">
    <div class="page-header">
      <h1>学习计划</h1>
    </div>

    <div class="plan-generator">
      <div class="card">
        <div class="card-header">
          <h3>生成计划</h3>
        </div>
        <div class="card-body">
          <div class="plan-form-grid">
            <div class="form-group">
              <label class="form-label">课程名 *</label>
              <input v-model="form.course_name" class="form-input" placeholder="如：高等数学" />
            </div>
            <div class="form-group">
              <label class="form-label">主题 *</label>
              <input v-model="form.topic" class="form-input" placeholder="如：导数与微分" />
            </div>
            <div class="form-group">
              <label class="form-label">计划天数</label>
              <input v-model.number="form.days" type="number" class="form-input" min="1" max="7" />
            </div>
          </div>
        </div>
        <div class="card-footer">
          <button class="btn btn-primary" :disabled="previewing" @click="handlePreview">
            {{ previewing ? '生成中...' : '预览计划' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="plan" class="plan-preview">
      <div class="card">
        <div class="card-header">
          <h3>{{ plan.plan_title || '学习计划' }}</h3>
          <button class="btn btn-primary btn-sm" :disabled="importing" @click="handleImport">
            {{ importing ? '导入中...' : '导入任务中心' }}
          </button>
        </div>
        <div class="card-body">
          <div v-if="plan.course_name" class="plan-summary">
            课程：{{ plan.course_name }} | 主题：{{ plan.topic }} | 天数：{{ plan.days }}
          </div>

          <div
            v-for="(task, i) in (plan.tasks_preview || [])"
            :key="i"
            class="plan-task-item"
          >
            <div class="plan-task-marker"></div>
            <div class="plan-task-content">
              <div class="plan-task-title">{{ task.title }}</div>
              <div v-if="task.description" class="plan-task-desc">{{ task.description }}</div>
              <div class="plan-task-meta">
                <span class="badge badge-info">{{ task.priority || 'medium' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <EmptyState v-if="!plan" :icon="CalendarDays" title="填写表单生成学习计划" desc="生成后可以预览并导入任务中心" />
  </div>
</template>

<style scoped>
.plan-task-item {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  margin-bottom: 0.5rem;
}

.plan-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 140px;
  gap: 1rem;
}

.plan-summary {
  margin-bottom: 1rem;
  color: var(--color-text-soft);
  font-size: var(--text-sm);
}

.plan-task-marker {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-primary);
  border-radius: 4px;
  flex-shrink: 0;
  margin-top: 2px;
}

.plan-task-content {
  flex: 1;
}

.plan-task-title {
  font-weight: 500;
  margin-bottom: 0.25rem;
}

.plan-task-desc {
  font-size: 0.875rem;
  color: var(--color-text-soft);
  margin-bottom: 0.25rem;
}

.plan-task-meta {
  display: flex;
  gap: 0.5rem;
}

@media (max-width: 760px) {
  .plan-form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
