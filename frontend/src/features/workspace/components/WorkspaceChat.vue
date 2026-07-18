<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BookOpenText,
  History,
  ListTree,
  PanelRightOpen,
  Paperclip,
  Send,
  Sparkles
} from 'lucide-vue-next'
import ChatMessage from '../../agent/components/ChatMessage.vue'
import MessageAnchorRail from '../../agent/components/MessageAnchorRail.vue'
import SessionList from '../../agent/components/SessionList.vue'
import { useCourseAgentChat } from '../../agent/composables/useCourseAgentChat'


const props = defineProps({
  courseId: { type: Number, required: true },
  course: { type: Object, required: true }
})
const emit = defineEmits(['open-panel', 'data-changed'])
const route = useRoute()
const router = useRouter()
const viewport = ref(null)
const inputElement = ref(null)
const outlineOpen = ref(false)
const historyOpen = ref(false)
const activeMessageId = ref(null)
const highlightedMessageId = ref(null)
let scrollFrame = null
let highlightTimer = null
let suppressActiveUntil = 0

const quickPrompts = [
  '今天学什么？',
  '总结我的薄弱知识点',
  '给我出 3 道针对性练习题',
  '帮我找网上的视频讲解'
]

async function scrollBottom(behavior = 'auto') {
  await nextTick()
  if (viewport.value) {
    viewport.value.scrollTo({ top: viewport.value.scrollHeight, behavior })
  }
  scheduleActiveMessageUpdate()
}

const {
  sessions,
  activeId,
  agent,
  messages,
  input,
  loadingSessions,
  loadingMessages,
  sending,
  actionBusy,
  statusText,
  loadError,
  initialize,
  switchCourse,
  selectSession,
  newSession,
  archiveSession,
  send,
  decide
} = useCourseAgentChat({
  courseId: toRef(props, 'courseId'),
  route,
  router,
  scrollBottom,
  focusInput: () => inputElement.value?.focus(),
  onDataChanged: result => emit('data-changed', result),
  onSessionSelected: () => { historyOpen.value = false }
})

const userMessageCount = computed(() => messages.value.filter(message => message.role === 'user').length)

function updateResource(updated) {
  messages.value = messages.value.map(message => {
    const toolCalls = message.tool_calls
    if (!toolCalls?.resources?.length) return message
    return {
      ...message,
      tool_calls: {
        ...toolCalls,
        resources: toolCalls.resources.map(resource => (
          resource.id === updated.id ? updated : resource
        ))
      }
    }
  })
  emit('data-changed', 'resources')
}

function resizeComposer() {
  const element = inputElement.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 156)}px`
}

function usePrompt(prompt) {
  input.value = prompt
  nextTick(() => {
    resizeComposer()
    inputElement.value?.focus()
  })
}

async function submitMessage() {
  await send()
  await nextTick()
  resizeComposer()
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

function updateActiveMessage() {
  scrollFrame = null
  if (!viewport.value || performance.now() < suppressActiveUntil) return
  const targets = [...viewport.value.querySelectorAll('[data-message-role="user"]')]
  if (!targets.length) {
    activeMessageId.value = null
    return
  }
  const reachedBottom = viewport.value.scrollHeight - viewport.value.scrollTop - viewport.value.clientHeight <= 4
  if (reachedBottom) {
    const lastId = targets.at(-1)?.dataset.messageId
    if (String(activeMessageId.value) !== String(lastId)) activeMessageId.value = lastId
    return
  }
  const viewportTop = viewport.value.getBoundingClientRect().top + 28
  let closest = targets[0]
  let closestDistance = Number.POSITIVE_INFINITY
  for (const target of targets) {
    const distance = Math.abs(target.getBoundingClientRect().top - viewportTop)
    if (distance < closestDistance) {
      closest = target
      closestDistance = distance
    }
  }
  const nextId = closest.dataset.messageId
  if (String(activeMessageId.value) !== String(nextId)) activeMessageId.value = nextId
}

function scheduleActiveMessageUpdate() {
  if (scrollFrame != null) return
  scrollFrame = window.requestAnimationFrame(updateActiveMessage)
}

function jumpToMessage(messageId) {
  const target = [...(viewport.value?.querySelectorAll('[data-message-id]') || [])]
    .find(element => String(element.dataset.messageId) === String(messageId))
  if (!target || !viewport.value) return
  const viewportRect = viewport.value.getBoundingClientRect()
  const targetRect = target.getBoundingClientRect()
  const top = viewport.value.scrollTop + targetRect.top - viewportRect.top - 24
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  suppressActiveUntil = performance.now() + (reducedMotion ? 80 : 520)
  activeMessageId.value = messageId
  highlightedMessageId.value = messageId
  viewport.value.scrollTo({ top, behavior: reducedMotion ? 'auto' : 'smooth' })
  if (highlightTimer) window.clearTimeout(highlightTimer)
  highlightTimer = window.setTimeout(() => {
    highlightedMessageId.value = null
    scheduleActiveMessageUpdate()
  }, reducedMotion ? 120 : 1100)
}

async function chooseSession(session) {
  await selectSession(session)
  historyOpen.value = false
}

async function createConversation() {
  await newSession()
  historyOpen.value = false
}

watch(() => props.courseId, courseId => {
  outlineOpen.value = false
  historyOpen.value = false
  activeMessageId.value = null
  switchCourse(courseId)
})

watch(() => messages.value.filter(message => message.role === 'user').map(message => message.id).join(','), async () => {
  await nextTick()
  scheduleActiveMessageUpdate()
})

onMounted(async () => {
  await initialize()
  if (route.query.prompt) {
    const prompt = String(route.query.prompt)
    const query = { ...route.query }
    delete query.prompt
    await router.replace({ path: route.path, query })
    await send(prompt)
  }
  scheduleActiveMessageUpdate()
})

onBeforeUnmount(() => {
  if (scrollFrame != null) window.cancelAnimationFrame(scrollFrame)
  if (highlightTimer) window.clearTimeout(highlightTimer)
})

defineExpose({ send, focus: () => inputElement.value?.focus(), jumpToMessage })
</script>

<template>
  <section class="workspace-chat-shell" :class="{ 'has-outline': userMessageCount }">
    <MessageAnchorRail
      v-if="userMessageCount"
      :messages="messages"
      :active-message-id="activeMessageId"
      :mobile-open="outlineOpen"
      @jump="jumpToMessage"
      @close-mobile="outlineOpen = false"
    />

    <div class="workspace-chat">
      <header class="chat-header">
        <button
          v-if="userMessageCount"
          type="button"
          class="header-action outline-drawer-toggle"
          title="打开本次对话目录"
          aria-label="打开本次对话目录"
          :aria-expanded="outlineOpen"
          @click="outlineOpen = true"
        ><ListTree :size="18" /></button>
        <div class="course-identity">
          <span class="course-icon"><BookOpenText :size="17" /></span>
          <div>
            <strong>{{ course.name }}</strong>
            <span><i></i>{{ agent?.name || `${course.name} 学习助手` }} · 会话 {{ activeId || '加载中' }}</span>
          </div>
        </div>
        <span v-if="statusText" class="agent-status"><i></i>{{ statusText }}</span>
        <button
          type="button"
          class="header-action history-action"
          title="打开历史对话"
          aria-label="打开历史对话"
          :aria-expanded="historyOpen"
          @click="historyOpen = true"
        ><History :size="18" /></button>
        <button
          type="button"
          class="header-action inspector-action"
          title="打开课程面板"
          aria-label="打开课程面板"
          @click="$emit('open-panel', 'overview')"
        ><PanelRightOpen :size="18" /></button>
      </header>

      <div ref="viewport" class="chat-viewport" @scroll.passive="scheduleActiveMessageUpdate">
        <div v-if="loadingMessages" class="chat-state">正在恢复课程对话</div>
        <div v-else-if="loadError" class="chat-state error-state">
          <strong>会话暂时无法加载</strong>
          <span>{{ loadError }}</span>
          <button type="button" @click="initialize()">重新加载</button>
        </div>
        <div v-else-if="!messages.length" class="course-welcome">
          <span class="welcome-orb"><Sparkles :size="27" /></span>
          <span>{{ course.name }}</span>
          <h1>今天想从哪里开始？</h1>
          <p>{{ course.goal || '先添加资料，或者直接从一个知识点开始提问。' }}</p>
          <div class="welcome-actions">
            <button v-for="prompt in quickPrompts" :key="prompt" type="button" @click="usePrompt(prompt)">{{ prompt }}</button>
          </div>
        </div>
        <div v-else class="message-list">
          <div
            v-for="message in messages"
            :id="`chat-message-${message.id}`"
            :key="message.id"
            class="chat-message-anchor"
            :class="{ highlighted: String(highlightedMessageId) === String(message.id) }"
            :data-message-id="message.id"
            :data-message-role="message.role"
          >
            <ChatMessage
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
      </div>

      <footer class="chat-composer">
        <form @submit.prevent="submitMessage">
          <button type="button" title="打开资料面板" aria-label="打开资料面板" @click="$emit('open-panel', 'materials')"><Paperclip :size="18" /></button>
          <textarea
            ref="inputElement"
            v-model="input"
            rows="1"
            maxlength="3000"
            :disabled="sending"
            :placeholder="`向 ${course.name} 学习助手提问`"
            @input="resizeComposer"
            @keydown.enter.exact.prevent="submitMessage"
          ></textarea>
          <button class="send-action" type="submit" :disabled="sending || !input.trim()" title="发送" aria-label="发送消息"><Send :size="18" /></button>
        </form>
        <small>AI 可能出错，请核对重要信息。课程资料与外部来源会分别标注。</small>
      </footer>
    </div>

    <button v-if="historyOpen" class="history-scrim" type="button" aria-label="关闭历史对话" @click="historyOpen = false"></button>
    <aside v-if="historyOpen" class="history-drawer" aria-label="历史对话" @keydown.esc="historyOpen = false">
      <SessionList
        :sessions="sessions"
        :active-id="activeId"
        :loading="loadingSessions"
        @select="chooseSession"
        @new="createConversation"
        @archive="archiveSession"
      />
    </aside>
  </section>
</template>

<style scoped>
.workspace-chat-shell { position: relative; min-width: 0; height: 100dvh; display: grid; grid-template-columns: minmax(0, 1fr); overflow: hidden; background: var(--surface-primary); }
.workspace-chat-shell.has-outline { grid-template-columns: 254px minmax(0, 1fr); }
.workspace-chat { min-width: 0; min-height: 0; display: grid; grid-template-rows: 68px minmax(0, 1fr) auto; background: rgba(255, 255, 255, .94); }
.chat-header { display: flex; align-items: center; gap: 10px; padding: 0 18px; border-bottom: 1px solid var(--border-subtle); background: rgba(255, 255, 255, .84); backdrop-filter: blur(18px); }
.course-identity { min-width: 0; display: flex; align-items: center; gap: 11px; }
.course-icon { width: 38px; height: 38px; display: grid; place-items: center; flex: 0 0 38px; border-radius: 13px; color: var(--accent); background: var(--accent-soft); }
.course-identity > div { min-width: 0; display: grid; gap: 2px; }
.course-identity strong { overflow: hidden; color: var(--text-primary); font-size: 15px; font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.course-identity span:not(.course-icon) { display: flex; align-items: center; gap: 6px; overflow: hidden; color: var(--text-tertiary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.course-identity i { width: 6px; height: 6px; border-radius: 50%; background: var(--success); }
.header-action { width: 40px; height: 40px; display: grid; place-items: center; flex: 0 0 40px; border-radius: 12px; color: var(--text-secondary); transition: color var(--duration-fast) ease, background var(--duration-fast) ease; }
.header-action:hover,
.header-action:focus-visible { color: var(--accent); background: var(--accent-soft); }
.outline-drawer-toggle { display: none; }
.history-action { margin-left: auto; }
.agent-status { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; color: var(--text-tertiary); font-size: 12px; white-space: nowrap; }
.agent-status + .history-action { margin-left: 0; }
.agent-status i { width: 8px; height: 8px; border: 1px solid var(--accent); border-top-color: transparent; border-radius: 50%; animation: spin 700ms linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.chat-viewport { min-height: 0; overflow-y: auto; overscroll-behavior: contain; scroll-behavior: smooth; padding: 38px clamp(20px, 4vw, 58px) 32px; background: var(--surface-secondary); }
.chat-state { height: 100%; display: grid; place-items: center; align-content: center; gap: 10px; color: var(--text-secondary); font-size: 14px; text-align: center; }
.chat-state strong { color: var(--text-primary); font-size: 17px; }
.chat-state button { min-height: 40px; padding: 0 14px; border: 1px solid var(--border-strong); border-radius: 12px; color: var(--accent); background: #fff; font-weight: 600; }
.course-welcome { min-height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 30px 0; text-align: center; }
.welcome-orb { width: 66px; height: 66px; display: grid; place-items: center; border-radius: 24px; color: #fff; background: var(--gradient-brand); box-shadow: 0 18px 44px rgba(79, 124, 255, .25); }
.course-welcome > span:not(.welcome-orb) { margin-top: 22px; color: var(--accent); font-size: 13px; font-weight: 600; }
.course-welcome h1 { max-width: 720px; margin-top: 7px; font-size: clamp(34px, 4vw, 52px); font-weight: 650; letter-spacing: -.045em; }
.course-welcome p { max-width: 560px; margin-top: 13px; color: var(--text-secondary); font-size: 15px; line-height: 1.72; }
.welcome-actions { width: min(680px, 100%); display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 28px; }
.welcome-actions button { min-height: 52px; padding: 10px 16px; border: 1px solid var(--border-subtle); border-radius: 16px; color: var(--text-secondary); background: rgba(255, 255, 255, .78); box-shadow: 0 4px 16px rgba(0, 0, 0, .035); font-size: 13px; font-weight: 540; text-align: left; }
.welcome-actions button:hover { color: var(--accent); border-color: rgba(52, 120, 246, .22); background: #fff; }
.message-list { width: min(850px, 100%); display: grid; gap: 28px; margin: 0 auto; }
.chat-message-anchor { scroll-margin-top: 24px; border-radius: 24px; transition: background var(--duration-normal) ease, box-shadow var(--duration-normal) ease; }
.chat-message-anchor.highlighted { animation: anchorHighlight 1.05s var(--ease-out); }
@keyframes anchorHighlight {
  0%, 100% { background: transparent; box-shadow: none; }
  18%, 72% { background: rgba(52, 120, 246, .09); box-shadow: 0 0 0 10px rgba(52, 120, 246, .09); }
}
.chat-composer { padding: 12px clamp(16px, 3vw, 38px) 14px; background: linear-gradient(to top, #fff 72%, rgba(255, 255, 255, .84)); }
.chat-composer form { width: min(850px, 100%); min-height: 60px; display: grid; grid-template-columns: 42px minmax(0, 1fr) 44px; align-items: end; gap: 7px; margin: 0 auto; padding: 8px; border: 1px solid var(--border-subtle); border-radius: 23px; background: rgba(255, 255, 255, .94); box-shadow: 0 10px 34px rgba(0, 0, 0, .08); transition: border-color var(--duration-fast) ease, box-shadow var(--duration-fast) ease; }
.chat-composer form:focus-within { border-color: rgba(52, 120, 246, .5); box-shadow: var(--shadow-focus), 0 14px 38px rgba(0, 0, 0, .09); }
.chat-composer form > button:not(.send-action) { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 13px; color: var(--text-tertiary); }
.chat-composer form > button:not(.send-action):hover { color: var(--accent); background: var(--accent-soft); }
.chat-composer textarea { width: 100%; min-height: 42px; max-height: 156px; resize: none; overflow-y: auto; padding: 9px 4px 7px; border: 0; background: transparent; color: var(--text-primary); font-size: 15px; line-height: 1.6; }
.chat-composer textarea::placeholder { color: var(--text-tertiary); }
.send-action { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 14px; color: #fff; background: var(--gradient-brand); box-shadow: 0 8px 18px rgba(79, 124, 255, .24); }
.send-action:disabled { opacity: .38; box-shadow: none; }
.chat-composer > small { display: block; width: min(850px, 100%); margin: 7px auto 0; color: var(--text-tertiary); font-size: 11px; text-align: center; }
.history-scrim { position: absolute; inset: 0; z-index: 49; width: 100%; background: rgba(20, 22, 28, .2); backdrop-filter: blur(3px); }
.history-drawer { position: absolute; z-index: 50; inset: 12px 12px 12px auto; width: min(340px, calc(100% - 24px)); overflow: hidden; border: 1px solid rgba(255, 255, 255, .6); border-radius: 24px; background: rgba(248, 248, 250, .96); box-shadow: var(--shadow-floating); backdrop-filter: blur(24px); }
.history-drawer :deep(.session-panel) { height: 100%; border: 0; background: transparent; }

@media (max-width: 1180px) and (min-width: 821px) {
  .workspace-chat-shell.has-outline { grid-template-columns: 70px minmax(0, 1fr); }
}

@media (max-width: 820px) {
  .workspace-chat-shell,
  .workspace-chat-shell.has-outline { height: calc(100dvh - 52px); grid-template-columns: minmax(0, 1fr); }
  .workspace-chat { grid-template-rows: 62px minmax(0, 1fr) auto; }
  .outline-drawer-toggle { display: grid; }
  .chat-header { gap: 5px; padding: 0 10px; }
  .history-action { margin-left: auto; }
  .course-identity { flex: 1; }
  .agent-status { display: none; }
  .history-drawer { inset: 8px 8px 8px auto; width: min(360px, calc(100% - 16px)); }
}

@media (max-width: 620px) {
  .course-icon { display: none; }
  .course-identity span:not(.course-icon) { max-width: 150px; }
  .chat-viewport { padding: 24px 14px; }
  .course-welcome h1 { font-size: 34px; }
  .welcome-actions { grid-template-columns: 1fr; }
  .chat-composer { padding: 8px 10px 10px; }
  .chat-composer > small { display: none; }
  .chat-composer form { min-height: 56px; grid-template-columns: 40px minmax(0, 1fr) 42px; border-radius: 20px; }
  .chat-composer form > button:not(.send-action),
  .send-action { width: 40px; height: 40px; }
}

@media (prefers-reduced-motion: reduce) {
  .agent-status i { animation: none; }
  .chat-viewport { scroll-behavior: auto; }
  .chat-message-anchor.highlighted { animation: none; background: var(--accent-soft); }
}
</style>
