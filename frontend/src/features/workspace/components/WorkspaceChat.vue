<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpenText, PanelRightOpen, Paperclip, Send, Sparkles } from 'lucide-vue-next'
import {
  decideAgentAction,
  getCourseAgentWorkspace,
  sendAgentMessageStream
} from '../../../api/agent'
import { showToast } from '../../../components/common/toast'
import ChatMessage from '../../agent/components/ChatMessage.vue'


const props = defineProps({
  courseId: { type: Number, required: true },
  course: { type: Object, required: true }
})
const emit = defineEmits(['open-panel', 'data-changed'])
const route = useRoute()
const router = useRouter()
const messages = ref([])
const session = ref(null)
const agent = ref(null)
const input = ref(localStorage.getItem(`a3:course-draft:${props.courseId}`) || '')
const loading = ref(true)
const sending = ref(false)
const actionBusy = ref(false)
const statusText = ref('')
const viewport = ref(null)
const inputElement = ref(null)
let loadVersion = 0
let streamVersion = 0
let streamController = null

const quickPrompts = [
  '今天学什么？',
  '总结我的薄弱知识点',
  '给我出 3 道针对性练习题',
  '帮我找网上的视频讲解'
]

async function scrollBottom(behavior = 'auto') {
  await nextTick()
  if (viewport.value) viewport.value.scrollTo({ top: viewport.value.scrollHeight, behavior })
}

async function load() {
  const version = ++loadVersion
  loading.value = true
  try {
    const response = await getCourseAgentWorkspace(props.courseId, { message_limit: 100 })
    if (version !== loadVersion) return
    if (response.code === 200) {
      session.value = response.data.session
      agent.value = response.data.agent
      messages.value = response.data.messages || []
      await scrollBottom()
    } else {
      showToast({ type: 'error', message: response.message })
    }
  } catch (error) {
    if (version === loadVersion) showToast({ type: 'error', message: error.message || '课程会话加载失败' })
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

function cancelStream() {
  streamVersion += 1
  streamController?.abort()
  streamController = null
}

async function switchCourse() {
  // A session is scoped to one course. Clear it before loading the next one so
  // a new course message can never be sent with the previous course session id.
  cancelStream()
  sending.value = false
  messages.value = []
  session.value = null
  agent.value = null
  statusText.value = ''
  input.value = localStorage.getItem(`a3:course-draft:${props.courseId}`) || ''
  await load()
}

function updateResource(updated) {
  messages.value = messages.value.map(message => {
    const toolCalls = message.tool_calls
    if (!toolCalls?.resources?.length) return message
    return {
      ...message,
      tool_calls: {
        ...toolCalls,
        resources: toolCalls.resources.map(resource => resource.id === updated.id ? updated : resource)
      }
    }
  })
  emit('data-changed', 'resources')
}

async function send(textOverride = '') {
  const text = String(textOverride || input.value).trim()
  if (!text || sending.value) return
  const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
  const assistantId = `local-assistant-${requestId}`
  const requestCourseId = props.courseId
  messages.value.push({ id: `local-user-${requestId}`, role: 'user', content: text, sources: [] })
  input.value = ''
  localStorage.removeItem(`a3:course-draft:${props.courseId}`)
  messages.value.push({
    id: assistantId,
    role: 'assistant',
    content: '',
    sources: [],
    tool_calls: {},
    streaming: true
  })
  sending.value = true
  statusText.value = '正在读取课程上下文'
  await scrollBottom('smooth')

  let received = null
  const controller = new AbortController()
  streamController?.abort()
  streamController = controller
  const requestVersion = ++streamVersion
  const isCurrentRequest = () => (
    requestVersion === streamVersion
    && requestCourseId === props.courseId
    && !controller.signal.aborted
  )
  const currentAssistant = () => (
    isCurrentRequest()
      ? messages.value.find(message => message.id === assistantId)
      : null
  )
  try {
    await sendAgentMessageStream(
      {
        message: text,
        session_id: session.value?.id || null,
        course_id: requestCourseId,
        client_request_id: requestId
      },
      {
        onStatus(message) {
          if (!isCurrentRequest()) return
          statusText.value = message
        },
        onDelta(delta) {
          const assistant = currentAssistant()
          if (!assistant) return
          assistant.content += delta
          scrollBottom()
        },
        onResult(result) {
          const assistant = currentAssistant()
          if (!assistant) return
          received = result
          session.value = result.session
          agent.value = result.agent || agent.value
          const assistantIndex = messages.value.findIndex(message => message.id === assistantId)
          if (assistantIndex < 0) return
          messages.value[assistantIndex] = {
            ...result.message,
            content: result.reply || assistant.content,
            streaming: false
          }
        },
        onDone() {
          if (!isCurrentRequest()) return
          statusText.value = ''
        }
      },
      { signal: controller.signal }
    )
  } catch (error) {
    if (error.name === 'AbortError' || controller.signal.aborted) return
    const assistant = currentAssistant()
    if (!assistant) return
    const assistantIndex = messages.value.findIndex(message => message.id === assistantId)
    if (assistantIndex < 0) return
    messages.value[assistantIndex] = {
      ...assistant,
      content: `请求失败：${error.message}`,
      streaming: false
    }
  } finally {
    if (isCurrentRequest()) {
      if (streamController === controller) streamController = null
      const assistant = currentAssistant()
      if (!received && assistant) assistant.streaming = false
      sending.value = false
      statusText.value = ''
      emit('data-changed', received?.intent || 'chat')
      await scrollBottom()
    }
  }
}

function usePrompt(prompt) {
  input.value = prompt
  nextTick(() => inputElement.value?.focus())
}

async function practiceResource(resource) {
  const point = resource.knowledge_point_id ? `知识点 #${resource.knowledge_point_id}` : '相关知识点'
  if (sending.value) {
    await new Promise(resolve => {
      const stop = watch(sending, value => {
        if (value) return
        stop()
        resolve()
      })
    })
  }
  await send(`我已经看完推荐的学习资源，请围绕${point}给我出 3 道题。`)
}

async function decide(confirmation, confirmed) {
  if (actionBusy.value) return
  actionBusy.value = true
  const response = await decideAgentAction(confirmation.id, confirmed)
  actionBusy.value = false
  if (response.code === 200) {
    showToast({ type: confirmed ? 'success' : 'info', message: confirmed ? '操作已执行' : '操作已取消' })
    await load()
    emit('data-changed', 'action')
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

watch(input, value => {
  const key = `a3:course-draft:${props.courseId}`
  if (value) localStorage.setItem(key, value)
  else localStorage.removeItem(key)
})

watch(() => props.courseId, switchCourse)

onMounted(async () => {
  await load()
  if (route.query.prompt) {
    const prompt = String(route.query.prompt)
    const query = { ...route.query }
    delete query.prompt
    await router.replace({ path: route.path, query })
    await send(prompt)
  }
})

onBeforeUnmount(() => {
  loadVersion += 1
  cancelStream()
})

defineExpose({ send, focus: () => inputElement.value?.focus() })
</script>

<template>
  <section class="workspace-chat">
    <header class="chat-header">
      <div class="course-identity">
        <span class="course-icon"><BookOpenText :size="17" /></span>
        <div>
          <strong>{{ course.name }}</strong>
          <span><i></i>{{ agent?.name || `${course.name} 学习助手` }}</span>
        </div>
      </div>
      <span v-if="statusText" class="agent-status"><i></i>{{ statusText }}</span>
      <button type="button" title="打开课程面板" aria-label="打开课程面板" @click="$emit('open-panel', 'overview')">
        <PanelRightOpen :size="18" />
      </button>
    </header>

    <div ref="viewport" class="chat-viewport">
      <div v-if="loading" class="chat-state">正在恢复课程对话</div>
      <div v-else-if="!messages.length" class="course-welcome">
        <Sparkles :size="25" />
        <span>{{ course.name }}</span>
        <h1>从这门课继续</h1>
        <p>{{ course.goal || '先添加资料，或者直接从一个知识点开始提问。' }}</p>
        <div class="welcome-actions">
          <button v-for="prompt in quickPrompts" :key="prompt" type="button" @click="usePrompt(prompt)">{{ prompt }}</button>
        </div>
      </div>
      <div v-else class="message-list">
        <ChatMessage
          v-for="message in messages"
          :key="message.id"
          :message="message"
          :course-id="courseId"
          :action-busy="actionBusy"
          @navigate="to => router.push(to)"
          @open-panel="panel => $emit('open-panel', panel)"
          @decide="decide"
          @resource-updated="updateResource"
          @practice="practiceResource"
          @data-changed="result => $emit('data-changed', result)"
        />
      </div>
    </div>

    <footer class="chat-composer">
      <div class="composer-prompts">
        <button v-for="prompt in quickPrompts.slice(0, 3)" :key="prompt" type="button" @click="usePrompt(prompt)">{{ prompt }}</button>
      </div>
      <form @submit.prevent="send()">
        <button type="button" title="打开资料面板" aria-label="打开资料面板" @click="$emit('open-panel', 'materials')"><Paperclip :size="18" /></button>
        <textarea
          ref="inputElement"
          v-model="input"
          rows="1"
          maxlength="3000"
          :disabled="sending"
          :placeholder="`向 ${course.name} 学习助手提问`"
          @keydown.enter.exact.prevent="send()"
        ></textarea>
        <button class="send-action" type="submit" :disabled="sending || !input.trim()" title="发送" aria-label="发送消息"><Send :size="18" /></button>
      </form>
      <small>课程资料与外部来源会分别标注</small>
    </footer>
  </section>
</template>

<style scoped>
.workspace-chat { min-width: 0; height: 100dvh; display: grid; grid-template-rows: 58px minmax(0, 1fr) auto; background: #fff; }
.chat-header { display: flex; align-items: center; gap: 12px; padding: 0 16px; border-bottom: 1px solid #e0e4e1; }
.course-identity { min-width: 0; display: flex; align-items: center; gap: 9px; }
.course-icon { width: 32px; height: 32px; display: grid; place-items: center; flex: 0 0 32px; border-radius: 7px; color: #155f4d; background: #dcece4; }
.course-identity > div { min-width: 0; display: grid; gap: 1px; }
.course-identity strong { overflow: hidden; color: #2b3731; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.course-identity span:not(.course-icon) { display: flex; align-items: center; gap: 5px; color: #7a847f; font-size: 10px; }
.course-identity i { width: 5px; height: 5px; border-radius: 50%; background: #24946f; }
.chat-header > button { width: 34px; height: 34px; display: grid; place-items: center; margin-left: auto; border-radius: 6px; color: #66716b; }
.chat-header > button:hover { color: #176b58; background: #edf2ef; }
.agent-status { display: inline-flex; align-items: center; gap: 5px; margin-left: auto; color: #6d7872; font-size: 10px; white-space: nowrap; }
.agent-status + button { margin-left: 0; }
.agent-status i { width: 7px; height: 7px; border: 1px solid #268169; border-top-color: transparent; border-radius: 50%; animation: spin 700ms linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.chat-viewport { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 24px clamp(14px, 4vw, 52px); background: #fafbf9; }
.chat-state { height: 100%; display: grid; place-items: center; color: #7b8580; font-size: 12px; }
.course-welcome { min-height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }
.course-welcome > svg { color: #24715e; }
.course-welcome > span { margin-top: 11px; color: #19705a; font-size: 11px; font-weight: 760; }
.course-welcome h1 { margin-top: 4px; font-size: 23px; font-weight: 730; }
.course-welcome p { max-width: 520px; margin-top: 7px; color: #6e7973; font-size: 12px; line-height: 1.55; }
.welcome-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; margin-top: 17px; }
.welcome-actions button,
.composer-prompts button { min-height: 32px; padding: 0 10px; border: 1px solid #cbd4cf; border-radius: 5px; color: #52605a; background: #fff; font-size: 10px; }
.welcome-actions button:hover,
.composer-prompts button:hover { color: #176b58; border-color: #9eb9ae; }
.message-list { width: min(880px, 100%); display: grid; gap: 18px; margin: 0 auto; }
.chat-composer { padding: 9px clamp(12px, 3vw, 32px) 11px; border-top: 1px solid #e0e4e1; background: #fff; }
.composer-prompts { width: min(880px, 100%); display: flex; gap: 5px; margin: 0 auto 7px; overflow-x: auto; }
.composer-prompts button { flex: 0 0 auto; }
.chat-composer form { width: min(880px, 100%); min-height: 46px; display: grid; grid-template-columns: 34px minmax(0, 1fr) 38px; align-items: end; gap: 6px; margin: 0 auto; padding: 4px; border: 1px solid #cbd4cf; border-radius: 7px; background: #fbfcfb; }
.chat-composer form:focus-within { border-color: #2b7d68; box-shadow: 0 0 0 2px rgba(43, 125, 104, .1); }
.chat-composer form > button:not(.send-action) { width: 34px; height: 36px; display: grid; place-items: center; border-radius: 5px; color: #6f7974; }
.chat-composer textarea { width: 100%; min-height: 36px; max-height: 120px; resize: vertical; padding: 8px 3px 6px; border: 0; background: transparent; color: #29352f; font-size: 13px; line-height: 1.55; }
.send-action { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 6px; color: #fff; background: #176b58; }
.send-action:disabled { opacity: .38; }
.chat-composer > small { display: block; width: min(880px, 100%); margin: 5px auto 0; color: #909893; font-size: 9px; text-align: right; }
@media (max-width: 820px) {
  .workspace-chat { height: calc(100dvh - 52px); }
}
@media (max-width: 620px) {
  .chat-header { padding: 0 10px; }
  .chat-viewport { padding: 16px 10px; }
  .composer-prompts,
  .chat-composer > small { display: none; }
  .chat-composer { padding: 8px; }
}
</style>
