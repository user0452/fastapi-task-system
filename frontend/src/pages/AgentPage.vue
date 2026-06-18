<script setup>
import { ref, nextTick, computed, onMounted, watch } from 'vue'
import { sendAgentMessageStream } from '../api/agent'
import { confirmPlan } from '../api/plans'
import { useAuthStore } from '../stores/auth'
import { useWorkspaceStore } from '../stores/workspace'
import { showToast } from '../components/common/toast'
import EmptyState from '../components/common/EmptyState.vue'
import { Bot, ClipboardList, Trash2 } from 'lucide-vue-next'

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
  '帮我生成高等数学的学习资源',
  '出一组线性代数练习题',
  '帮我制定本周学习计划',
  '总结一下我目前的学习画像'
]

// 解析后端返回的数据
const plan = computed(() => result.value?.plan || {})
const toolResults = computed(() => result.value?.tool_results || {})
const intent = computed(() => plan.value?.intent || '')
const courseName = computed(() => plan.value?.course_name || '')
const topic = computed(() => plan.value?.topic || '')
const tools = computed(() => plan.value?.tools || [])
const resource = computed(() => toolResults.value?.resource || null)
const quizSet = computed(() => toolResults.value?.quiz_set || null)
const learningPlan = computed(() => toolResults.value?.learning_plan || null)
const externalResources = computed(() => toolResults.value?.external_resources || null)
const externalResourceItems = computed(() => externalResources.value?.resources || [])

const intentLabels = {
  generate_study_package: '学习包',
  generate_resource: '学习资源',
  generate_quiz: '练习题',
  generate_plan: '学习计划',
  search_external_learning_resources: '联网搜索资源',
  update_profile: '更新画像',
  qa: '问答',
  unknown: '未知'
}

const toolLabels = {
  generate_resource: '生成资源',
  generate_quiz: '生成题集',
  generate_plan: '生成计划',
  search_external_learning_resources: '联网搜索资源'
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
          saveResult()
          if (data?.tool_results?.resource || data?.tool_results?.quiz_set || data?.tool_results?.learning_plan) {
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

async function handleImportTasks() {
  if (!learningPlan.value) {
    showToast({ type: 'warning', message: '没有可导入的计划' })
    return
  }

  const res = await confirmPlan({
    tasks_preview: learningPlan.value.tasks_preview || []
  })
  if (res.code === 200) {
    const count = res.data?.created_count ?? res.data?.task_count ?? res.data?.tasks?.length ?? '?'
    showToast({ type: 'success', message: `成功导入 ${count} 个任务` })
    workspace.loadOverview()
  } else {
    showToast({ type: 'error', message: res.message })
  }
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
            <template v-if="msg.content">
              {{ msg.content }}
              <span v-if="msg.streaming" class="stream-cursor"></span>
            </template>
            <div v-else-if="msg.streaming" class="stream-status">
              <div class="loading-spinner loading-spinner-sm"></div>
              <span>{{ streamingStatus || '正在思考...' }}</span>
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
        <h3>本次结果</h3>
      </div>

      <EmptyState
        v-if="!result"
        :icon="ClipboardList"
        title="暂无结果"
        desc="发送消息后，AI 的处理结果将展示在这里"
      />

      <template v-else>
        <div class="result-scroll">
          <!-- 意图 -->
          <div v-if="intent" class="result-section">
            <h4>识别意图</h4>
            <span class="badge badge-primary">{{ intentLabels[intent] || intent }}</span>
          </div>

          <!-- 课程信息 -->
          <div v-if="courseName" class="result-section">
            <h4>课程名</h4>
            <p>{{ courseName }}</p>
          </div>

          <div v-if="topic" class="result-section">
            <h4>主题</h4>
            <p>{{ topic }}</p>
          </div>

          <!-- 调用工具 -->
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

          <!-- 生成的资源 -->
          <div v-if="resource" class="result-section">
            <h4>生成资源</h4>
            <div class="result-card">
              <div class="result-card-title">{{ resource.title }}</div>
              <div class="result-card-meta">类型：{{ resource.resource_type }}</div>
              <div class="result-card-content">{{ (resource.content || '').substring(0, 300) }}...</div>
              <div v-if="resource.key_points?.length" class="result-card-points">
                <strong>关键知识点：</strong>
                <ul>
                  <li v-for="(p, i) in resource.key_points.slice(0, 3)" :key="i">{{ p }}</li>
                </ul>
              </div>
            </div>
          </div>

          <!-- 生成的题集 -->
          <div v-if="quizSet" class="result-section">
            <h4>生成题集</h4>
            <div class="result-card">
              <div class="result-card-title">{{ quizSet.title }}</div>
              <div class="result-card-meta">
                {{ quizSet.course_name }} · {{ quizSet.questions?.length || 0 }} 题
              </div>
              <div v-if="quizSet.questions?.length" class="result-card-questions">
                <div v-for="(q, i) in quizSet.questions.slice(0, 3)" :key="i" class="question-preview">
                  <span class="question-num">{{ i + 1 }}.</span>
                  <span>{{ q.question }}</span>
                </div>
                <div v-if="quizSet.questions.length > 3" class="question-more">
                  还有 {{ quizSet.questions.length - 3 }} 题...
                </div>
              </div>
            </div>
          </div>

          <!-- 生成的计划 -->
          <div v-if="learningPlan" class="result-section">
            <h4>生成计划</h4>
            <div class="result-card">
              <div class="result-card-title">{{ learningPlan.plan_title }}</div>
              <div class="result-card-meta">
                {{ learningPlan.course_name }} · {{ learningPlan.days }} 天
              </div>
              <div v-if="learningPlan.tasks_preview?.length" class="result-card-tasks">
                <div v-for="(t, i) in learningPlan.tasks_preview.slice(0, 5)" :key="i" class="task-preview">
                  <span class="task-marker">□</span>
                  <span>{{ t.title }}</span>
                </div>
                <div v-if="learningPlan.tasks_preview.length > 5" class="task-more">
                  还有 {{ learningPlan.tasks_preview.length - 5 }} 个任务...
                </div>
              </div>
              <button class="btn btn-primary btn-sm import-tasks-button" @click="handleImportTasks">
                导入任务中心
              </button>
            </div>
          </div>

          <!-- 联网搜索结果 -->
          <div v-if="externalResources" class="result-section">
            <h4>联网搜索结果</h4>
            <div v-if="externalResources.error" class="result-card result-card-warning">
              <div class="result-card-title">搜索失败</div>
              <div class="result-card-content">{{ externalResources.error }}</div>
            </div>
            <div v-else-if="externalResourceItems.length" class="external-resource-list">
              <component
                :is="item.url ? 'a' : 'div'"
                v-for="(item, i) in externalResourceItems"
                :key="item.url || i"
                class="external-resource-card"
                :href="item.url || undefined"
                :target="item.url ? '_blank' : undefined"
                :rel="item.url ? 'noopener noreferrer' : undefined"
              >
                <div class="external-resource-main">
                  <div class="result-card-title">{{ item.title || '未命名资源' }}</div>
                  <div class="result-card-meta">
                    {{ item.source || '未知来源' }} · {{ item.resource_type || 'resource' }}
                    <span v-if="item.estimated_time"> · {{ item.estimated_time }}</span>
                  </div>
                  <div v-if="item.snippet" class="result-card-content">{{ item.snippet }}</div>
                  <div v-if="item.reason" class="external-resource-reason">{{ item.reason }}</div>
                </div>
              </component>
            </div>
            <div v-else class="result-card">
              <div class="result-card-content">没有搜索到可展示的外部资源。</div>
            </div>
          </div>

          <!-- 无工具调用 -->
          <div v-if="!tools.length && !resource && !quizSet && !learningPlan && !externalResources" class="result-section">
            <div class="result-empty">
              <p>{{ plan.reply || 'AI 已回复' }}</p>
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
  white-space: pre-wrap;
  word-break: break-word;
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

.external-resource-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.external-resource-card {
  display: block;
  padding: 0.875rem;
  background-color: var(--color-surface-strong);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.external-resource-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  text-decoration: none;
}

.external-resource-main {
  min-width: 0;
}

.external-resource-reason {
  font-size: var(--text-sm);
  color: var(--color-primary);
  line-height: 1.5;
}

.result-card-points {
  font-size: var(--text-sm);
  color: var(--color-text-soft);
}

.result-card-points ul {
  margin-top: 0.375rem;
  padding-left: 1.25rem;
}

.result-card-points li {
  margin-bottom: 0.25rem;
}

.question-preview {
  display: flex;
  gap: 0.5rem;
  font-size: var(--text-sm);
  color: var(--color-text-soft);
  margin-bottom: 0.375rem;
}

.question-num {
  color: var(--color-primary);
  font-weight: 600;
  flex-shrink: 0;
}

.question-more,
.task-more {
  font-size: var(--text-sm);
  color: var(--color-muted);
  margin-top: 0.375rem;
}

.task-preview {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: var(--text-sm);
  color: var(--color-text-soft);
  margin-bottom: 0.375rem;
}

.task-marker {
  color: var(--color-primary);
  font-weight: 600;
}

.import-tasks-button {
  margin-top: 0.75rem;
}

.result-empty {
  text-align: center;
  padding: 1.5rem;
  color: var(--color-text-soft);
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
