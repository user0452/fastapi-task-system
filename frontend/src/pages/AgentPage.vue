<script setup>
import { ref, nextTick, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { sendAgentMessageStream } from '../api/agent'
import { confirmPlan } from '../api/plans'
import { useAuthStore } from '../stores/auth'
import { useWorkspaceStore } from '../stores/workspace'
import { showToast } from '../components/common/toast'
import EmptyState from '../components/common/EmptyState.vue'
import { Bot, ClipboardList, ExternalLink, Trash2 } from 'lucide-vue-next'

const router = useRouter()
const auth = useAuthStore()
const workspace = useWorkspaceStore()
const storageKey = computed(() => `agent_chat_messages:${auth.username || 'guest'}`)
const resultStorageKey = computed(() => `agent_chat_result:${auth.username || 'guest'}`)
const messages = ref([])
const input = ref('')
const sending = ref(false)
const streamingStatus = ref('')
const result = ref(null)
const messagesEl = ref(null)
const inputEl = ref(null)

const quickPrompts = [
  '我想学习软件测试-A3内部课里的等价类划分，给我讲解、练习题、三天学习计划，再推荐几个视频和资料。',
  '保存一份软件测试-A3内部课资料，标题是青瓷等价类法，内容是青瓷等价类法包含青层、瓷层和裂层。',
  '查看我目前的学生画像',
  '列出最近的练习题和评估记录'
]

// 解析后端返回的数据
const plan = computed(() => result.value?.plan || {})
const toolResults = computed(() => result.value?.tool_results || {})
const intent = computed(() => plan.value?.intent || '')
const courseName = computed(() => plan.value?.course_name || '')
const topic = computed(() => plan.value?.topic || '')
const tools = computed(() => plan.value?.tools || [])
const externalResources = computed(() => toolResults.value?.external_resources || null)

const intentLabels = {
  generate_study_package: '学习包',
  generate_resource: '学习资源',
  generate_resource_only: '学习资源',
  list_resources: '学习资源列表',
  get_resource: '学习资源详情',
  generate_quiz: '练习题',
  generate_quiz_only: '练习题',
  list_quizzes: '题集列表',
  get_quiz: '题集详情',
  generate_plan: '学习计划',
  generate_plan_only: '学习计划',
  import_plan_tasks: '导入学习计划',
  search_external_learning_resources: '外部资源检索',
  chat: '普通对话',
  generate_profile: '生成画像',
  get_profile: '查看画像',
  update_profile: '更新画像',
  update_profile_request: '画像更新请求',
  create_material: '保存资料',
  list_materials: '资料列表',
  build_material_index: '资料索引',
  rag_search_materials: '资料检索',
  create_task: '创建任务',
  list_tasks: '任务列表',
  get_task: '任务详情',
  update_task: '更新任务',
  delete_task: '删除任务',
  bulk_update_tasks_status: '批量更新任务',
  bulk_delete_tasks_status: '批量删除任务',
  submit_evaluation: '学习评估',
  list_evaluations: '评估记录',
  get_evaluation: '评估详情',
  parse_exam_schedule: '考试解析',
  preview_review_plan: '复习计划',
  import_review_plan_tasks: '导入复习任务',
  list_operation_logs: '操作日志',
  qa: '问答',
  unknown: '未知'
}

const toolLabels = {
  generate_profile: '生成画像',
  get_profile: '查看画像',
  create_material: '保存资料',
  list_materials: '查询资料',
  build_material_index: '构建索引',
  rag_search_materials: '资料检索',
  generate_resource: '生成资源',
  list_resources: '查询资源',
  get_resource: '资源详情',
  generate_quiz: '生成题集',
  list_quizzes: '查询题集',
  get_quiz: '题集详情',
  generate_plan: '生成计划',
  import_plan_tasks: '导入计划任务',
  create_task: '创建任务',
  list_tasks: '查询任务',
  get_task: '任务详情',
  update_task: '更新任务',
  delete_task: '删除任务',
  bulk_update_tasks_status: '批量更新任务',
  bulk_delete_tasks_status: '批量删除任务',
  submit_evaluation: '提交评估',
  list_evaluations: '查询评估',
  get_evaluation: '评估详情',
  parse_exam_schedule: '解析考试',
  preview_review_plan: '生成复习计划',
  import_review_plan_tasks: '导入复习任务',
  list_operation_logs: '查询日志',
  search_external_learning_resources: '外部资源',
  chat: '普通对话',
  update_profile_request: '画像更新请求'
}

const overviewRefreshResultKeys = new Set([
  'profile',
  'material',
  'material_index',
  'resource',
  'quiz_set',
  'learning_plan',
  'plan_import',
  'task',
  'task_update',
  'task_delete',
  'bulk_task_update',
  'bulk_task_delete',
  'evaluation',
  'review_import'
])

function messageToolResults(msg) {
  return msg?.result?.tool_results || {}
}

function messagePlan(msg) {
  return msg?.result?.plan || {}
}

function hasMessageCards(msg) {
  const results = messageToolResults(msg)
  return Boolean(
    results.resource ||
    results.quiz_set ||
    results.learning_plan ||
    results.external_resources
  )
}

function truncateText(text, length = 180) {
  const value = text || ''
  return value.length > length ? value.slice(0, length) + '...' : value
}

function quizDifficultySummary(quiz) {
  const questions = quiz?.questions || []
  if (!questions.length) return '暂无难度标注'

  const labelMap = {
    easy: '简单',
    medium: '中等',
    hard: '困难'
  }
  const counts = questions.reduce((acc, question) => {
    const key = question.difficulty || 'medium'
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})

  return Object.entries(counts)
    .map(([key, count]) => `${labelMap[key] || key} ${count}`)
    .join(' · ')
}

function sortedExternalResources(externalResources) {
  const items = externalResources?.resources || []
  const priority = {
    video: 0,
    practice: 1,
    document: 2,
    article: 3
  }

  return [...items].sort((a, b) => {
    const left = priority[a.resource_type] ?? 9
    const right = priority[b.resource_type] ?? 9
    if (left !== right) return left - right
    return (b.score || 0) - (a.score || 0)
  })
}

function viewResource(resource) {
  router.push({
    path: '/resources',
    query: resource?.id ? { resource_id: resource.id } : {}
  })
}

function viewQuiz(quiz) {
  router.push({
    path: '/quizzes',
    query: quiz?.id ? { quiz_set_id: quiz.id, tab: 'submit' } : {}
  })
}

async function importLearningPlan(planData) {
  if (!planData) {
    showToast({ type: 'warning', message: '没有可导入的计划' })
    return
  }

  const res = await confirmPlan({
    tasks_preview: planData.tasks_preview || []
  })
  if (res.code === 200) {
    const count = res.data?.created_count ?? res.data?.task_count ?? res.data?.tasks?.length ?? '?'
    showToast({ type: 'success', message: `成功导入 ${count} 个任务` })
    workspace.loadOverview()
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

function resultTypeSummary(results) {
  const labels = []
  if (results.resource) labels.push('学习资源包')
  if (results.quiz_set) labels.push('练习题')
  if (results.learning_plan) labels.push('学习计划')
  if (results.external_resources) labels.push('外部资源')
  if (results.profile || results.profile_detail) labels.push('学生画像')
  if (results.material || results.materials || results.material_index || results.rag_search) labels.push('课程知识库')
  if (results.evaluation || results.evaluations || results.evaluation_detail) labels.push('学习评估')
  if (results.task || results.tasks || results.plan_import || results.review_import) labels.push('任务中心')
  return labels
}

// 保存聊天记录到 localStorage
function saveMessages() {
  try {
    localStorage.setItem(storageKey.value, JSON.stringify(messages.value))
  } catch (e) {
    console.warn('保存聊天记录失败:', e)
  }
}

function saveResult() {
  try {
    if (result.value) {
      localStorage.setItem(resultStorageKey.value, JSON.stringify(result.value))
    } else {
      localStorage.removeItem(resultStorageKey.value)
    }
  } catch (e) {
    console.warn('保存本次结果失败:', e)
  }
}

// 从 localStorage 恢复聊天记录
function loadMessages() {
  try {
    const saved = localStorage.getItem(storageKey.value)
    if (saved) {
      messages.value = JSON.parse(saved).map(msg => ({ ...msg, streaming: false }))
    }
  } catch (e) {
    console.warn('加载聊天记录失败:', e)
  }
}

function loadResult() {
  try {
    const saved = localStorage.getItem(resultStorageKey.value)
    result.value = saved ? JSON.parse(saved) : null
  } catch (e) {
    console.warn('加载本次结果失败:', e)
    result.value = null
  }
}

// 清空聊天记录
function clearMessages() {
  messages.value = []
  result.value = null
  localStorage.removeItem(storageKey.value)
  localStorage.removeItem(resultStorageKey.value)
  showToast({ type: 'info', message: '聊天记录已清空' })
}

// 监听 messages 变化，自动保存
watch(messages, saveMessages, { deep: true })

onMounted(() => {
  loadMessages()
  loadResult()
  nextTick(() => {
    scrollToBottom()
    adjustTextareaHeight()
  })
})

async function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  adjustTextareaHeight()
  result.value = null
  saveResult()

  const assistantIndex = messages.value.length
  messages.value.push({ role: 'assistant', content: '', streaming: true })
  await scrollToBottom()

  sending.value = true
  streamingStatus.value = '正在连接 AI 助手'

  try {
    await sendAgentMessageStream(
      { message: text },
      {
        onStatus(message) {
          streamingStatus.value = message
          scrollToBottom()
        },
        onDelta(delta) {
          messages.value[assistantIndex].content += delta
          scrollToBottom()
        },
        onResult(data) {
          result.value = data
          messages.value[assistantIndex].result = data
          saveResult()
          const resultKeys = Object.keys(data?.tool_results || {})
          if (resultKeys.some(key => overviewRefreshResultKeys.has(key))) {
            workspace.loadOverview()
          }
          if (!messages.value[assistantIndex].content) {
            messages.value[assistantIndex].content = data?.plan?.reply || '处理完成'
          }
        },
        onDone() {
          messages.value[assistantIndex].streaming = false
          streamingStatus.value = ''
        }
      }
    )
  } catch (err) {
    messages.value[assistantIndex].content = '请求失败：' + (err.message || '未知错误')
  } finally {
    messages.value[assistantIndex].streaming = false
    streamingStatus.value = ''
    sending.value = false
  }

  await scrollToBottom()
}

function useQuickPrompt(text) {
  input.value = text
  nextTick(() => {
    adjustTextareaHeight()
    if (inputEl.value) {
      inputEl.value.focus()
    }
  })
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

// 自动调整输入框高度
function adjustTextareaHeight() {
  nextTick(() => {
    if (inputEl.value) {
      inputEl.value.style.height = 'auto'
      const scrollHeight = inputEl.value.scrollHeight
      const maxHeight = 150 // 最大高度约6行
      inputEl.value.style.height = Math.min(scrollHeight, maxHeight) + 'px'
    }
  })
}

</script>

<template>
  <div class="agent-page">
    <div class="agent-chat">
      <div class="chat-header">
        <h3>AI 学习助手</h3>
        <button
          v-if="messages.length > 0"
          class="btn btn-ghost btn-sm"
          title="清空聊天记录"
          @click="clearMessages"
        >
          <Trash2 :size="16" />
        </button>
      </div>

      <div ref="messagesEl" class="agent-messages">
        <EmptyState
          v-if="messages.length === 0"
          :icon="Bot"
          title="AI 学习助手"
          desc="输入你的需求，AI 帮你生成资源、题集或学习计划"
        />

        <div
          v-for="(msg, i) in messages"
          :key="i"
          class="agent-message"
          :class="msg.role === 'user' ? 'agent-message-user' : 'agent-message-assistant'"
        >
          <div class="agent-message-avatar">
            {{ msg.role === 'user' ? '我' : 'AI' }}
          </div>
          <div class="agent-message-content">
            <div v-if="msg.content" class="agent-message-text">
              {{ msg.content }}
              <span v-if="msg.streaming" class="stream-cursor"></span>
            </div>
            <div v-else-if="msg.streaming" class="stream-status">
              <div class="loading-spinner loading-spinner-sm"></div>
              <span>{{ streamingStatus || '正在思考...' }}</span>
            </div>

            <div
              v-if="msg.role === 'assistant' && hasMessageCards(msg)"
              class="agent-card-stack"
            >
              <div v-if="messageToolResults(msg).resource" class="agent-tool-card resource-package-card">
                <div class="agent-card-kicker">学习资源包</div>
                <div class="agent-card-title">{{ messageToolResults(msg).resource.title }}</div>
                <div class="agent-card-meta">
                  {{ messageToolResults(msg).resource.course_name || messagePlan(msg).course_name || '未标注课程' }}
                  <span>·</span>
                  {{ messageToolResults(msg).resource.topic || messagePlan(msg).topic || '未标注知识点' }}
                </div>
                <p class="agent-card-summary">
                  {{ truncateText(messageToolResults(msg).resource.content, 220) }}
                </p>
                <div v-if="messageToolResults(msg).resource.key_points?.length" class="agent-card-points">
                  <span
                    v-for="(point, index) in messageToolResults(msg).resource.key_points.slice(0, 3)"
                    :key="index"
                    class="agent-card-point"
                  >
                    {{ point }}
                  </span>
                </div>
                <div class="agent-card-actions">
                  <button class="btn btn-sm btn-primary" @click="viewResource(messageToolResults(msg).resource)">
                    查看资源详情
                  </button>
                </div>
              </div>

              <div v-if="messageToolResults(msg).quiz_set" class="agent-tool-card quiz-card">
                <div class="agent-card-kicker">练习题</div>
                <div class="agent-card-title">{{ messageToolResults(msg).quiz_set.title }}</div>
                <div class="agent-card-meta">
                  {{ messageToolResults(msg).quiz_set.course_name }}
                  <span>·</span>
                  {{ messageToolResults(msg).quiz_set.topic }}
                </div>
                <div class="agent-card-stats">
                  <span>{{ messageToolResults(msg).quiz_set.questions?.length || 0 }} 题</span>
                  <span>{{ quizDifficultySummary(messageToolResults(msg).quiz_set) }}</span>
                </div>
                <div class="agent-card-actions">
                  <button class="btn btn-sm btn-primary" @click="viewQuiz(messageToolResults(msg).quiz_set)">
                    开始作答
                  </button>
                  <button class="btn btn-sm btn-secondary" @click="viewQuiz(messageToolResults(msg).quiz_set)">
                    查看题集
                  </button>
                </div>
              </div>

              <div v-if="messageToolResults(msg).learning_plan" class="agent-tool-card plan-card">
                <div class="agent-card-kicker">学习计划</div>
                <div class="agent-card-title">{{ messageToolResults(msg).learning_plan.plan_title }}</div>
                <div class="agent-card-meta">
                  {{ messageToolResults(msg).learning_plan.course_name }}
                  <span>·</span>
                  {{ messageToolResults(msg).learning_plan.days }} 天
                </div>
                <div v-if="messageToolResults(msg).learning_plan.tasks_preview?.length" class="agent-plan-preview">
                  <div
                    v-for="(task, index) in messageToolResults(msg).learning_plan.tasks_preview.slice(0, 3)"
                    :key="index"
                    class="agent-plan-task"
                  >
                    <span>{{ index + 1 }}</span>
                    <p>{{ task.title }}</p>
                  </div>
                </div>
                <div class="agent-card-actions">
                  <button class="btn btn-sm btn-primary" @click="importLearningPlan(messageToolResults(msg).learning_plan)">
                    导入任务中心
                  </button>
                </div>
              </div>

              <div v-if="messageToolResults(msg).external_resources" class="agent-tool-card external-card">
                <div class="agent-card-kicker">外部学习资源</div>
                <div v-if="messageToolResults(msg).external_resources.error" class="external-error">
                  外部搜索暂时不可用：{{ messageToolResults(msg).external_resources.error }}
                </div>
                <template v-else-if="sortedExternalResources(messageToolResults(msg).external_resources).length">
                  <a
                    v-for="(item, index) in sortedExternalResources(messageToolResults(msg).external_resources).slice(0, 5)"
                    :key="item.url || index"
                    class="external-agent-item"
                    :href="item.url || undefined"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <img
                      v-if="item.favicon"
                      class="external-favicon"
                      :src="item.favicon"
                      alt=""
                    />
                    <div class="external-agent-main">
                      <div class="external-agent-title">{{ item.title || '未命名资源' }}</div>
                      <div class="agent-card-meta">
                        {{ item.resource_type || 'resource' }}
                        <span>·</span>
                        {{ item.source || '未知来源' }}
                        <span v-if="item.estimated_time">· {{ item.estimated_time }}</span>
                      </div>
                      <p v-if="item.reason" class="external-reason">{{ item.reason }}</p>
                      <p v-if="item.snippet" class="external-snippet">{{ truncateText(item.snippet, 150) }}</p>
                    </div>
                    <span class="external-open-button">
                      打开资源
                      <ExternalLink :size="14" />
                    </span>
                  </a>
                </template>
                <div v-else class="external-empty">没有搜索到可展示的外部资源。</div>
              </div>
            </div>
          </div>
        </div>

      </div>

      <div class="agent-input-area">
        <div v-if="quickPrompts.length && messages.length === 0" class="quick-prompts">
          <button
            v-for="p in quickPrompts"
            :key="p"
            class="btn btn-sm btn-secondary"
            @click="useQuickPrompt(p)"
          >
            {{ p }}
          </button>
        </div>
        <div class="agent-input-wrapper">
          <textarea
            ref="inputEl"
            v-model="input"
            class="agent-input"
            placeholder="输入你的需求..."
            rows="1"
            @keydown.enter.exact.prevent="sendMessage"
            @input="adjustTextareaHeight"
          ></textarea>
          <button class="btn btn-primary" :disabled="sending || !input.trim()" @click="sendMessage">
            发送
          </button>
        </div>
      </div>
    </div>

    <div class="agent-result">
      <div class="card-header">
        <h3>本轮调度摘要</h3>
      </div>

      <EmptyState
        v-if="!result"
        :icon="ClipboardList"
        title="等待对话"
        desc="发送消息后，这里会显示本轮意图、工具和结果类型"
      />

      <template v-else>
        <div class="result-scroll">
          <div v-if="intent" class="result-section">
            <h4>识别意图</h4>
            <span class="badge badge-primary">{{ intentLabels[intent] || intent }}</span>
          </div>

          <div v-if="courseName" class="result-section">
            <h4>课程名</h4>
            <p>{{ courseName }}</p>
          </div>

          <div v-if="topic" class="result-section">
            <h4>主题</h4>
            <p>{{ topic }}</p>
          </div>

          <div v-if="tools.length" class="result-section">
            <h4>调用工具</h4>
            <div class="tool-tags">
              <span
                v-for="t in tools"
                :key="t"
                class="badge badge-info"
              >{{ toolLabels[t] || t }}</span>
            </div>
          </div>

          <div class="result-section">
            <h4>结果类型</h4>
            <div v-if="resultTypeSummary(toolResults).length" class="tool-tags">
              <span
                v-for="label in resultTypeSummary(toolResults)"
                :key="label"
                class="badge badge-info"
              >
                {{ label }}
              </span>
            </div>
            <div v-else class="result-empty result-empty-compact">
              <p>{{ plan.reply || 'AI 已回复' }}</p>
            </div>
          </div>

          <div v-if="externalResources?.error" class="result-section">
            <h4>外部资源状态</h4>
            <div class="result-card result-card-warning">
              <div class="result-card-content">搜索暂时不可用，聊天气泡中已显示友好提示。</div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.agent-page {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  height: calc(100vh - 120px);
}

.agent-chat {
  display: flex;
  flex-direction: column;
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.875rem 1rem;
  border-bottom: 1px solid var(--color-line);
}

.chat-header h3 {
  font-size: var(--text-lg);
  font-weight: 600;
}

.agent-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.agent-message {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.agent-message-user {
  flex-direction: row-reverse;
}

.agent-message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 600;
  flex-shrink: 0;
}

.agent-message-user .agent-message-avatar {
  background-color: var(--color-primary);
  color: white;
}

.agent-message-assistant .agent-message-avatar {
  background-color: var(--color-info);
  color: white;
}

.agent-message-content {
  max-width: 80%;
  padding: 0.625rem 0.875rem;
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  line-height: 1.6;
  word-break: break-word;
}

.agent-message-text {
  white-space: pre-wrap;
}

.loading-spinner-sm {
  width: 1rem;
  height: 1rem;
}

.stream-status {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-text-soft);
}

.stream-cursor {
  display: inline-block;
  width: 0.45rem;
  height: 1em;
  margin-left: 0.125rem;
  background-color: currentColor;
  vertical-align: -0.125rem;
  animation: stream-cursor-blink 0.9s steps(2, start) infinite;
}

@keyframes stream-cursor-blink {
  50% {
    opacity: 0;
  }
}

.agent-message-user .agent-message-content {
  background-color: var(--color-primary);
  color: white;
  border-bottom-right-radius: 4px;
}

.agent-message-assistant .agent-message-content {
  background-color: var(--color-surface-strong);
  border: 1px solid var(--color-line);
  border-bottom-left-radius: 4px;
}

.agent-card-stack {
  display: grid;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.agent-tool-card {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: 0.875rem;
}

.agent-card-kicker {
  margin-bottom: 0.375rem;
  color: var(--color-primary);
  font-size: var(--text-xs);
  font-weight: 700;
}

.agent-card-title {
  color: var(--color-text);
  font-size: var(--text-lg);
  font-weight: 700;
  line-height: 1.35;
}

.agent-card-meta,
.agent-card-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 0.375rem;
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.agent-card-summary,
.external-reason,
.external-snippet {
  margin: 0.625rem 0 0;
  color: var(--color-text-soft);
  font-size: var(--text-sm);
  line-height: 1.55;
}

.agent-card-points {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 0.75rem;
}

.agent-card-point {
  padding: 0.25rem 0.5rem;
  background-color: var(--color-primary-light);
  border-radius: var(--radius-sm);
  color: var(--color-primary);
  font-size: var(--text-xs);
  font-weight: 600;
}

.agent-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.agent-plan-preview {
  display: grid;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.agent-plan-task {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  padding: 0.5rem;
  background-color: var(--color-surface-strong);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
}

.agent-plan-task span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  background-color: var(--color-primary);
  border-radius: 50%;
  color: white;
  font-size: var(--text-xs);
  font-weight: 700;
  flex-shrink: 0;
}

.agent-plan-task p {
  margin: 0;
  color: var(--color-text-soft);
  font-size: var(--text-sm);
  line-height: 1.45;
}

.external-card {
  display: grid;
  gap: 0.625rem;
}

.external-agent-item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 0.625rem;
  align-items: flex-start;
  padding: 0.75rem;
  color: inherit;
  text-decoration: none;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  background-color: var(--color-surface-strong);
}

.external-agent-item:hover {
  border-color: var(--color-primary);
}

.external-favicon {
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 4px;
  margin-top: 0.125rem;
}

.external-agent-title {
  color: var(--color-text);
  font-weight: 700;
  line-height: 1.4;
}

.external-open-button {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--color-line-strong);
  border-radius: var(--radius-sm);
  color: var(--color-primary);
  font-size: var(--text-xs);
  font-weight: 700;
  white-space: nowrap;
}

.external-open-button svg {
  color: var(--color-muted);
}

.external-error,
.external-empty {
  padding: 0.75rem;
  border-radius: var(--radius-sm);
  color: var(--color-text-soft);
  font-size: var(--text-sm);
  line-height: 1.5;
}

.external-error {
  background-color: rgba(217, 119, 6, 0.08);
  border: 1px solid rgba(217, 119, 6, 0.3);
}

.agent-input-area {
  padding: 0.875rem;
  border-top: 1px solid var(--color-line);
}

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.agent-input-wrapper {
  display: flex;
  gap: 0.625rem;
  align-items: flex-end;
}

.agent-input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-line-strong);
  border-radius: var(--radius-md);
  resize: none;
  min-height: 40px;
  max-height: 150px;
  font-size: var(--text-base);
  font-family: inherit;
  line-height: 1.5;
  overflow-y: auto;
  transition: border-color 0.15s ease;
}

.agent-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.agent-input::placeholder {
  color: var(--color-muted);
}

.agent-result {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.agent-result .card-header {
  padding: 0.875rem 1rem;
  border-bottom: 1px solid var(--color-line);
  margin-bottom: 0;
}

.result-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.result-section {
  margin-bottom: 1.25rem;
}

.result-section h4 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-muted);
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.result-section p {
  font-size: var(--text-base);
  color: var(--color-text-soft);
  margin: 0;
}

.tool-tags {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.result-card {
  background-color: var(--color-surface-strong);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: 0.875rem;
}

.result-card-warning {
  border-color: rgba(217, 119, 6, 0.35);
  background-color: rgba(217, 119, 6, 0.06);
}

.result-card-title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 0.375rem;
}

.result-card-meta {
  font-size: var(--text-sm);
  color: var(--color-muted);
  margin-bottom: 0.625rem;
}

.result-card-content {
  font-size: var(--text-sm);
  color: var(--color-text-soft);
  line-height: 1.6;
  margin-bottom: 0.625rem;
}

.result-empty {
  text-align: center;
  padding: 1.5rem;
  color: var(--color-text-soft);
}

.result-empty-compact {
  padding: 0.75rem;
  text-align: left;
}

@media (max-width: 1024px) {
  .agent-page {
    grid-template-columns: 1fr;
    height: auto;
  }

  .agent-chat {
    min-height: min(400px, calc(100vh - 180px));
  }

  .agent-result {
    min-height: min(300px, calc(100vh - 220px));
  }
}
</style>
