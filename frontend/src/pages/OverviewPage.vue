<script setup>
import { onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore } from '../stores/workspace'
import { useAuthStore } from '../stores/auth'
import LoadingState from '../components/common/LoadingState.vue'
import {
  UserRound,
  BookOpen,
  FileText,
  PencilLine,
  CalendarDays,
  CheckSquare,
  ArrowRight
} from 'lucide-vue-next'

const router = useRouter()
const ws = useWorkspaceStore()
const auth = useAuthStore()

onMounted(() => {
  if (auth.isLoggedIn) {
    ws.loadOverview()
  }
})

const steps = computed(() => [
  {
    label: '学生画像',
    icon: UserRound,
    route: '/profile',
    done: !!ws.profile,
    count: ws.profile ? 1 : 0,
    desc: '建立学习画像'
  },
  {
    label: '课程资料',
    icon: BookOpen,
    route: '/materials',
    done: ws.materialsTotal > 0,
    count: ws.materialsTotal,
    desc: '上传课程知识'
  },
  {
    label: '学习资源',
    icon: FileText,
    route: '/resources',
    done: ws.resourcesTotal > 0,
    count: ws.resourcesTotal,
    desc: '生成学习内容'
  },
  {
    label: '练习题',
    icon: PencilLine,
    route: '/quizzes',
    done: ws.quizzesTotal > 0,
    count: ws.quizzesTotal,
    desc: '检验学习成果'
  },
  {
    label: '学习计划',
    icon: CalendarDays,
    route: '/plans',
    done: false,
    count: 0,
    desc: '规划学习路径'
  },
  {
    label: '任务执行',
    icon: CheckSquare,
    route: '/tasks',
    done: ws.tasksTotal > 0,
    count: ws.tasksTotal,
    desc: '跟踪学习进度'
  }
])

const nextAction = computed(() => {
  if (!ws.profile) {
    return {
      title: '生成学生画像',
      desc: '先建立你的学习画像，系统将为你生成个性化内容',
      route: '/profile',
      btnText: '去生成画像'
    }
  }
  if (ws.materialsTotal === 0) {
    return {
      title: '上传课程资料',
      desc: '上传课程资料，构建知识库，为后续生成资源和题集做准备',
      route: '/materials',
      btnText: '去上传资料'
    }
  }
  if (ws.resourcesTotal === 0) {
    return {
      title: '生成学习资源',
      desc: '基于画像和资料，生成个性化的学习资源',
      route: '/resources',
      btnText: '去生成资源'
    }
  }
  if (ws.quizzesTotal === 0) {
    return {
      title: '生成练习题',
      desc: '生成练习题检验学习成果',
      route: '/quizzes',
      btnText: '去生成题集'
    }
  }
  return {
    title: 'AI 学习助手',
    desc: '让 AI 助手帮你规划学习、解答问题',
    route: '/agent',
    btnText: '去对话'
  }
})

function go(route) {
  router.push(route)
}

function formatDate(val) {
  if (!val) return ''
  const d = new Date(val)
  return d.toLocaleDateString('zh-CN')
}

function getRecentItems() {
  const items = []
  if (ws.recentMaterials.length) {
    items.push({ type: '资料', data: ws.recentMaterials[0], route: '/materials' })
  }
  if (ws.recentResources.length) {
    items.push({ type: '资源', data: ws.recentResources[0], route: '/resources' })
  }
  if (ws.recentQuizzes.length) {
    items.push({ type: '题集', data: ws.recentQuizzes[0], route: '/quizzes' })
  }
  if (ws.recentTasks.length) {
    items.push({ type: '任务', data: ws.recentTasks[0], route: '/tasks' })
  }
  return items
}
</script>

<template>
  <div class="overview-page">
    <div class="page-header">
      <h1>学习流程总览</h1>
    </div>

    <LoadingState v-if="ws.loading" />

    <template v-else>
      <div class="workflow-section">
        <div class="workflow-header">
          <h2>学习流程</h2>
          <span class="workflow-hint">完成每个步骤，逐步构建你的学习体系</span>
        </div>

        <div class="workflow-steps">
          <div
            v-for="(step, i) in steps"
            :key="step.route"
            class="workflow-step"
            :class="{ 'step-done': step.done }"
            @click="go(step.route)"
          >
            <div class="step-indicator">
              <div class="step-icon">
                <component :is="step.icon" :size="20" />
              </div>
              <div v-if="i < steps.length - 1" class="step-line"></div>
            </div>
            <div class="step-content">
              <div class="step-label">{{ step.label }}</div>
              <div class="step-desc">{{ step.desc }}</div>
              <div v-if="step.count > 0" class="step-count">{{ step.count }} 项</div>
            </div>
          </div>
        </div>
      </div>

      <div class="action-section">
        <div class="action-card">
          <div class="action-info">
            <h3>{{ nextAction.title }}</h3>
            <p>{{ nextAction.desc }}</p>
          </div>
          <button class="btn btn-primary" @click="go(nextAction.route)">
            {{ nextAction.btnText }}
            <ArrowRight :size="16" />
          </button>
        </div>
      </div>

      <div v-if="getRecentItems().length" class="recent-section">
        <h2>最近活动</h2>
        <div class="recent-list">
          <div
            v-for="item in getRecentItems()"
            :key="item.type"
            class="recent-item"
            @click="go(item.route)"
          >
            <div class="recent-type">{{ item.type }}</div>
            <div class="recent-info">
              <div class="recent-title">{{ item.data.title || item.data.course_name }}</div>
              <div class="recent-meta">{{ formatDate(item.data.created_at) }}</div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.overview-page {
  max-width: 1000px;
}

.page-header {
  margin-bottom: 1.5rem;
}

.page-header h1 {
  font-size: 1.375rem;
  font-weight: 600;
}

.workflow-section {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.workflow-header {
  display: flex;
  align-items: baseline;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.workflow-header h2 {
  font-size: 1.125rem;
  font-weight: 600;
}

.workflow-hint {
  font-size: 0.8125rem;
  color: var(--color-muted);
}

.workflow-steps {
  display: flex;
  gap: 0;
}

.workflow-step {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
  padding: 0.75rem;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease;
}

.workflow-step:hover {
  background-color: rgba(0, 0, 0, 0.03);
}

.step-indicator {
  display: flex;
  align-items: center;
  width: 100%;
  margin-bottom: 0.75rem;
}

.step-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-surface-strong);
  border: 2px solid var(--color-line);
  border-radius: 50%;
  color: var(--color-muted);
  flex-shrink: 0;
  transition: all 0.15s ease;
}

.step-done .step-icon {
  background-color: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

.step-line {
  flex: 1;
  height: 2px;
  background-color: var(--color-line);
  margin: 0 0.5rem;
}

.step-done .step-line {
  background-color: var(--color-primary);
}

.step-content {
  text-align: center;
}

.step-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-soft);
  margin-bottom: 0.25rem;
}

.step-done .step-label {
  color: var(--color-primary);
}

.step-desc {
  font-size: 0.75rem;
  color: var(--color-muted);
  margin-bottom: 0.25rem;
}

.step-count {
  font-size: 0.75rem;
  color: var(--color-primary);
  font-weight: 500;
}

.action-section {
  margin-bottom: 1.5rem;
}

.action-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(135deg, var(--color-primary) 0%, #1a4a3f 100%);
  color: white;
  border-radius: var(--radius-md);
  padding: 1.25rem 1.5rem;
}

.action-info h3 {
  font-size: 1.125rem;
  font-weight: 600;
  color: white;
  margin-bottom: 0.25rem;
}

.action-info p {
  font-size: 0.875rem;
  color: rgba(255, 255, 255, 0.86);
  opacity: 0.9;
  margin: 0;
}

.action-card .btn {
  background-color: white;
  color: var(--color-primary);
  flex-shrink: 0;
}

.action-card .btn:hover {
  background-color: rgba(255, 255, 255, 0.9);
}

.recent-section {
  margin-bottom: 1.5rem;
}

.recent-section h2 {
  font-size: 1.125rem;
  font-weight: 600;
  margin-bottom: 1rem;
}

.recent-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 0.75rem;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem;
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
}

.recent-item:hover {
  border-color: var(--color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.recent-type {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-primary);
  background-color: rgba(37, 92, 79, 0.1);
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.recent-info {
  flex: 1;
  min-width: 0;
}

.recent-title {
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recent-meta {
  font-size: 0.75rem;
  color: var(--color-muted);
}

@media (max-width: 768px) {
  .overview-page {
    max-width: none;
  }

  .workflow-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.375rem;
  }

  .workflow-header h2 {
    white-space: nowrap;
  }

  .workflow-steps {
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .workflow-step {
    flex: 0 0 calc(33.333% - 0.5rem);
  }

  .step-indicator {
    justify-content: center;
  }

  .step-line {
    display: none;
  }

  .action-card {
    flex-direction: column;
    gap: 1rem;
    text-align: center;
  }
}

@media (max-width: 480px) {
  .workflow-step {
    flex: 0 0 calc(50% - 0.5rem);
  }
}
</style>
