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
  Bot,
  BarChart3,
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
    label: '课程知识库',
    icon: BookOpen,
    route: '/materials',
    done: ws.materialsTotal > 0,
    count: ws.materialsTotal,
    desc: '上传资料并构建 RAG'
  },
  {
    label: 'AI 学习助手',
    icon: Bot,
    route: '/agent',
    done: ws.resourcesTotal > 0 || ws.quizzesTotal > 0,
    count: ws.resourcesTotal + ws.quizzesTotal,
    desc: '多工具 Agent 调度'
  },
  {
    label: '练习与评估',
    icon: PencilLine,
    route: '/quizzes',
    done: ws.evaluationsTotal > 0,
    count: ws.evaluationsTotal,
    desc: '作答并生成反馈'
  },
  {
    label: '计划与任务',
    icon: CalendarDays,
    route: '/tasks',
    done: ws.tasksTotal > 0,
    count: ws.tasksTotal,
    desc: '导入计划并跟踪'
  }
])

const metricCards = computed(() => [
  { label: '课程资料', value: ws.materialsTotal, route: '/materials' },
  { label: '学习资源', value: ws.resourcesTotal, route: '/resources' },
  { label: '题集数量', value: ws.quizzesTotal, route: '/quizzes' },
  { label: '评估次数', value: ws.evaluationsTotal, route: '/quizzes' },
  { label: '任务数量', value: ws.tasksTotal, route: '/tasks' }
])

const demoFlow = [
  '学生画像',
  '课程资料上传',
  'RAG 检索',
  '多工具 Agent',
  '资源/题集/计划/外部资料',
  '学习评估'
]

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

function startDemo() {
  router.push('/agent')
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
    <div class="overview-hero">
      <div>
        <p class="overview-eyebrow">中国软件杯 A3 赛道演示项目</p>
        <h1>个性化学习资源生成与学习规划智能体系统</h1>
        <p class="overview-subtitle">基于大模型与 RAG 的个性化学习资源生成与学习规划智能体系统</p>
      </div>
      <button class="btn btn-primary btn-lg" @click="startDemo">
        开始演示
        <ArrowRight :size="18" />
      </button>
    </div>

    <LoadingState v-if="ws.loading" />

    <template v-else>
      <div class="metrics-grid">
        <button
          v-for="metric in metricCards"
          :key="metric.label"
          class="metric-card"
          @click="go(metric.route)"
        >
          <span class="metric-value">{{ metric.value }}</span>
          <span class="metric-label">{{ metric.label }}</span>
        </button>
      </div>

      <div class="workflow-section">
        <div class="workflow-header">
          <h2>学习闭环 5 阶段</h2>
          <span class="workflow-hint">从画像、知识库到 Agent 生成、评估反馈和任务跟踪</span>
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

      <div class="agent-flow-section">
        <div class="workflow-header">
          <h2>演示链路</h2>
          <span class="workflow-hint">学生画像 → 资料检索 → 多工具生成 → 评估改进</span>
        </div>
        <div class="agent-flow">
          <template v-for="(item, index) in demoFlow" :key="item">
            <div class="flow-node">
              <BarChart3 v-if="index === demoFlow.length - 1" :size="16" />
              <FileText v-else-if="index === 4" :size="16" />
              <Bot v-else-if="index === 3" :size="16" />
              <BookOpen v-else-if="index === 1 || index === 2" :size="16" />
              <UserRound v-else :size="16" />
              <span>{{ item }}</span>
            </div>
            <ArrowRight v-if="index < demoFlow.length - 1" :size="16" class="flow-arrow" />
          </template>
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
  max-width: 1180px;
}

.overview-hero {
  display: flex;
  justify-content: space-between;
  gap: 2rem;
  align-items: flex-end;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-soft);
}

.overview-eyebrow {
  margin: 0 0 0.375rem;
  color: var(--color-primary);
  font-size: var(--text-sm);
  font-weight: 700;
}

.overview-hero h1 {
  max-width: 760px;
  margin: 0;
  font-size: 1.75rem;
  line-height: 1.3;
  font-weight: 700;
}

.overview-subtitle {
  max-width: 760px;
  margin: 0.625rem 0 0;
  color: var(--color-text-soft);
  font-size: var(--text-base);
  line-height: 1.6;
}

.page-header {
  margin-bottom: 1.5rem;
}

.page-header h1 {
  font-size: 1.375rem;
  font-weight: 600;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.metric-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
  padding: 1rem;
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  text-align: left;
  box-shadow: var(--shadow-soft);
}

.metric-card:hover {
  border-color: var(--color-primary);
}

.metric-value {
  color: var(--color-primary);
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1;
}

.metric-label {
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.workflow-section {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.agent-flow-section {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.agent-flow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.flow-node {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0.75rem;
  background-color: var(--color-surface-strong);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  color: var(--color-text-soft);
  font-size: var(--text-sm);
  font-weight: 600;
}

.flow-node svg {
  color: var(--color-primary);
}

.flow-arrow {
  color: var(--color-muted);
  flex-shrink: 0;
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

  .overview-hero {
    align-items: flex-start;
    flex-direction: column;
  }

  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
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
  .metrics-grid {
    grid-template-columns: 1fr;
  }

  .workflow-step {
    flex: 0 0 calc(50% - 0.5rem);
  }
}
</style>
