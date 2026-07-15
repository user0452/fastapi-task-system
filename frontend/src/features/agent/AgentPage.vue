<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Menu, Plus, Send, Sparkles } from 'lucide-vue-next'
import {
  archiveAgentSession,
  createAgentSession,
  decideAgentAction,
  getAgentSession,
  getAgentSessions,
  sendAgentMessageStream
} from '../../api/agent'
import { useCourseStore } from '../../stores/course'
import { showToast } from '../../components/common/toast'
import ChatMessage from './components/ChatMessage.vue'
import SessionList from './components/SessionList.vue'


const route = useRoute()
const router = useRouter()
const courses = useCourseStore()
const sessions = ref([])
const activeId = ref(null)
const messages = ref([])
const input = ref('')
const loadingSessions = ref(false)
const loadingMessages = ref(false)
const sending = ref(false)
const statusText = ref('')
const actionBusy = ref(false)
const showSessions = ref(false)
const messageViewport = ref(null)
const inputElement = ref(null)

const quickPrompts = [
  '今天学什么？',
  '总结我的薄弱知识点',
  '根据课程资料讲解一个核心概念',
  '生成入门诊断题'
]

async function scrollBottom() {
  await nextTick()
  if (messageViewport.value) messageViewport.value.scrollTop = messageViewport.value.scrollHeight
}

async function loadSessions(selectFirst = true) {
  loadingSessions.value = true
  const response = await getAgentSessions({ page: 1, size: 50 })
  loadingSessions.value = false
  if (response.code >= 200 && response.code < 300) {
    sessions.value = response.data?.items || []
    if (selectFirst && !activeId.value && sessions.value.length) await selectSession(sessions.value[0])
  }
}

async function loadActiveSession() {
  if (!activeId.value) return
  loadingMessages.value = true
  const response = await getAgentSession(activeId.value, { size: 100 })
  loadingMessages.value = false
  if (response.code >= 200 && response.code < 300) {
    messages.value = response.data?.messages || []
    await scrollBottom()
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

async function selectSession(session) {
  activeId.value = session.id
  showSessions.value = false
  await loadActiveSession()
}

async function newSession() {
  const response = await createAgentSession({
    course_id: courses.current?.id || null,
    title: '新对话'
  })
  if (response.code >= 200 && response.code < 300) {
    activeId.value = response.data.id
    messages.value = []
    await loadSessions(false)
    inputElement.value?.focus()
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

async function archiveSession(session) {
  if (!window.confirm(`归档对话“${session.title}”？`)) return
  const response = await archiveAgentSession(session.id)
  if (response.code === 200) {
    if (activeId.value === session.id) {
      activeId.value = null
      messages.value = []
    }
    await loadSessions(true)
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  const userMessage = { id: `local-user-${Date.now()}`, role: 'user', content: text, sources: [] }
  messages.value.push(userMessage)
  input.value = ''
  const assistantIndex = messages.value.length
  messages.value.push({ id: `local-assistant-${Date.now()}`, role: 'assistant', content: '', sources: [], streaming: true })
  sending.value = true
  statusText.value = '正在连接课程助教'
  await scrollBottom()

  let receivedResult = null
  try {
    await sendAgentMessageStream(
      {
        message: text,
        session_id: activeId.value,
        course_id: courses.current?.id || null
      },
      {
        onStatus(message) {
          statusText.value = message
        },
        onDelta(delta) {
          messages.value[assistantIndex].content += delta
          scrollBottom()
        },
        onResult(result) {
          receivedResult = result
          activeId.value = result.session.id
          messages.value[assistantIndex] = {
            ...result.message,
            content: result.reply || messages.value[assistantIndex].content,
            streaming: false
          }
        },
        onDone() {
          statusText.value = ''
        }
      }
    )
    await loadSessions(false)
  } catch (error) {
    messages.value[assistantIndex] = {
      ...messages.value[assistantIndex],
      content: `请求失败：${error.message}`,
      streaming: false
    }
  } finally {
    if (!receivedResult) messages.value[assistantIndex].streaming = false
    sending.value = false
    statusText.value = ''
    await scrollBottom()
  }
}

function usePrompt(prompt) {
  input.value = prompt
  nextTick(() => inputElement.value?.focus())
}

async function decide(confirmation, confirmed) {
  if (actionBusy.value) return
  actionBusy.value = true
  const response = await decideAgentAction(confirmation.id, confirmed)
  actionBusy.value = false
  if (response.code === 200) {
    showToast({
      type: confirmed ? 'success' : 'info',
      message: confirmed ? '操作已确认并执行' : '操作已取消，数据未改变'
    })
    await loadActiveSession()
    await loadSessions(false)
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

onMounted(async () => {
  await courses.ensureLoaded()
  await loadSessions(true)
  if (route.query.prompt) {
    input.value = String(route.query.prompt)
    router.replace({ path: '/agent' })
    nextTick(() => inputElement.value?.focus())
  }
})
</script>

<template>
  <div class="agent-page">
    <header class="agent-heading">
      <div>
        <span>{{ courses.current?.name || '未绑定课程' }}</span>
        <h1>AI 助教</h1>
        <p>回答默认结合当前课程资料、掌握度和最近会话；资料命中时显示引用。</p>
      </div>
      <button class="new-chat-button" type="button" @click="newSession"><Plus :size="16" /> 新对话</button>
    </header>

    <section class="agent-workspace">
      <div class="mobile-session-panel" :class="{ open: showSessions }">
        <SessionList
          :sessions="sessions"
          :active-id="activeId"
          :loading="loadingSessions"
          @select="selectSession"
          @new="newSession"
          @archive="archiveSession"
        />
      </div>

      <div class="chat-panel">
        <div class="chat-toolbar">
          <button class="icon-button session-toggle" type="button" aria-label="查看历史会话" @click="showSessions = !showSessions"><Menu :size="17" /></button>
          <div>
            <strong>{{ courses.current?.name || '通用对话' }}</strong>
            <span>{{ activeId ? `会话 #${activeId}` : '发送第一条消息后自动保存会话' }}</span>
          </div>
          <span v-if="statusText" class="stream-status"><i></i>{{ statusText }}</span>
        </div>

        <div ref="messageViewport" class="message-viewport">
          <div v-if="loadingMessages" class="message-state">正在恢复会话</div>
          <div v-else-if="!messages.length" class="agent-welcome">
            <Sparkles :size="28" />
            <h2>从当前课程开始</h2>
            <p v-if="courses.current">可以问《{{ courses.current.name }}》中的概念，也可以查看今日任务、进度或生成诊断。</p>
            <p v-else>先选择课程，AI 助教才能使用课程资料和掌握度。</p>
            <div class="welcome-prompts">
              <button v-for="prompt in quickPrompts" :key="prompt" type="button" @click="usePrompt(prompt)">{{ prompt }}</button>
            </div>
          </div>
          <div v-else class="message-list">
            <ChatMessage
              v-for="message in messages"
              :key="message.id"
              :message="message"
              :course-id="courses.current?.id || null"
              :action-busy="actionBusy"
              @navigate="to => router.push(to)"
              @decide="decide"
            />
          </div>
        </div>

        <form class="chat-composer" @submit.prevent="send">
          <div class="quick-row">
            <button v-for="prompt in quickPrompts.slice(0, 3)" :key="prompt" type="button" @click="usePrompt(prompt)">{{ prompt }}</button>
          </div>
          <div class="composer-row">
            <textarea
              ref="inputElement"
              v-model="input"
              rows="1"
              maxlength="3000"
              :disabled="sending"
              :placeholder="courses.current ? `向《${courses.current.name}》提问` : '请先选择课程'"
              @keydown.enter.exact.prevent="send"
            ></textarea>
            <button class="send-button" type="submit" :disabled="sending || !input.trim()" title="发送" aria-label="发送消息">
              <Send :size="18" />
            </button>
          </div>
          <small>每次发送都会附带精确到分钟的本地时间；审计时间以服务端 UTC 为准。</small>
        </form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.agent-page { max-width: 1240px; margin: 0 auto; }
.agent-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.agent-heading > div > span { color: #17705b; font-size: 11px; font-weight: 750; }
.agent-heading h1 { margin-top: 3px; font-size: 25px; font-weight: 720; }
.agent-heading p { margin-top: 5px; color: #69736e; font-size: 11px; }
.new-chat-button { min-height: 36px; display: inline-flex; align-items: center; gap: 6px; padding: 0 12px; border: 1px solid #afc1b9; border-radius: 6px; color: #175b4a; background: #ffffff; font-size: 11px; font-weight: 750; }
.agent-workspace { height: calc(100dvh - 174px); min-height: 520px; display: grid; grid-template-columns: 224px minmax(0, 1fr); overflow: hidden; border: 1px solid #d8dfdb; border-radius: 8px; background: #ffffff; }
.mobile-session-panel { min-height: 0; }
.mobile-session-panel :deep(.session-panel) { height: 100%; }
.chat-panel { min-width: 0; min-height: 0; display: grid; grid-template-rows: 50px minmax(0, 1fr) auto; }
.chat-toolbar { display: flex; align-items: center; gap: 9px; padding: 7px 12px; border-bottom: 1px solid #dde3df; }
.chat-toolbar > div { min-width: 0; display: grid; gap: 1px; }
.chat-toolbar strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.chat-toolbar span { color: #7a847f; font-size: 8px; }
.stream-status { display: inline-flex !important; align-items: center; gap: 5px; margin-left: auto; white-space: nowrap; }
.stream-status i { width: 7px; height: 7px; border: 1px solid #268169; border-top-color: transparent; border-radius: 50%; animation: spin 700ms linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.icon-button { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 6px; color: #637069; }
.session-toggle { display: none; }
.message-viewport { min-height: 0; overflow-y: auto; padding: 18px clamp(12px, 3vw, 30px); background: #f8faf8; }
.message-state { min-height: 100%; display: grid; place-items: center; color: #7a847f; font-size: 10px; }
.agent-welcome { min-height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; text-align: center; }
.agent-welcome > svg { color: #24715e; }
.agent-welcome h2 { font-size: 17px; font-weight: 750; }
.agent-welcome p { max-width: 520px; color: #6f7a74; font-size: 11px; }
.welcome-prompts { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; margin-top: 6px; }
.welcome-prompts button,
.quick-row button { min-height: 29px; padding: 0 9px; border: 1px solid #c6d1cb; border-radius: 5px; color: #51605a; background: #ffffff; font-size: 9px; }
.welcome-prompts button:hover,
.quick-row button:hover { color: #176b58; border-color: #9cb9ad; }
.message-list { display: grid; gap: 13px; }
.chat-composer { padding: 9px 12px 10px; border-top: 1px solid #dde3df; background: #ffffff; }
.quick-row { display: flex; gap: 5px; margin-bottom: 7px; overflow-x: auto; }
.quick-row button { flex: 0 0 auto; }
.composer-row { display: grid; grid-template-columns: minmax(0, 1fr) 38px; align-items: end; gap: 7px; }
.composer-row textarea { width: 100%; min-height: 39px; max-height: 110px; resize: vertical; padding: 9px 11px; border: 1px solid #cbd4cf; border-radius: 6px; background: #fbfcfb; font-size: 12px; line-height: 1.55; }
.composer-row textarea:focus { border-color: #27806a; box-shadow: 0 0 0 2px rgba(39,128,106,.11); }
.send-button { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 6px; color: #ffffff; background: #176b58; }
.send-button:disabled { opacity: .4; }
.chat-composer > small { display: block; margin-top: 5px; color: #88918d; font-size: 8px; }
@media (max-width: 820px) {
  .agent-workspace { position: relative; grid-template-columns: 1fr; }
  .mobile-session-panel { position: absolute; inset: 0 auto 0 0; z-index: 5; width: 240px; transform: translateX(-101%); transition: transform 180ms ease; }
  .mobile-session-panel.open { transform: translateX(0); }
  .session-toggle { display: grid; }
}
@media (max-width: 680px) {
  .agent-heading p { display: none; }
  .agent-workspace { height: calc(100dvh - 218px); min-height: 360px; }
  .agent-heading h1 { font-size: 22px; }
  .quick-row { display: none; }
  .chat-composer > small { display: none; }
  .message-viewport { padding: 12px 9px; }
}
</style>
