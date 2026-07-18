<script setup>
import { nextTick, onMounted, ref, toRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BookOpenText,
  MessageSquareText,
  PanelRightOpen,
  Paperclip,
  Send,
  Sparkles
} from 'lucide-vue-next'
import ChatMessage from '../../agent/components/ChatMessage.vue'
import HoverSessionRail from '../../agent/components/HoverSessionRail.vue'
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
const mobileSessionsOpen = ref(false)

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
  onSessionSelected: () => { mobileSessionsOpen.value = false }
})

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

watch(() => props.courseId, switchCourse)

onMounted(async () => {
  await initialize()
  if (route.query.prompt) {
    const prompt = String(route.query.prompt)
    const query = { ...route.query }
    delete query.prompt
    await router.replace({ path: route.path, query })
    await send(prompt)
  }
})

defineExpose({ send, focus: () => inputElement.value?.focus() })
</script>

<template>
  <section class="workspace-chat-shell">
    <HoverSessionRail
      :sessions="sessions"
      :active-id="activeId"
      :loading="loadingSessions"
      :mobile-open="mobileSessionsOpen"
      @select="selectSession"
      @new="newSession"
      @archive="archiveSession"
      @close-mobile="mobileSessionsOpen = false"
    />

    <div class="workspace-chat">
      <header class="chat-header">
        <button
          type="button"
          class="header-action session-drawer-toggle"
          title="查看历史会话"
          aria-label="查看历史会话"
          :aria-expanded="mobileSessionsOpen"
          @click="mobileSessionsOpen = true"
        ><MessageSquareText :size="18" /></button>
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
          class="header-action inspector-action"
          title="打开课程面板"
          aria-label="打开课程面板"
          @click="$emit('open-panel', 'overview')"
        ><PanelRightOpen :size="18" /></button>
      </header>

      <div ref="viewport" class="chat-viewport">
        <div v-if="loadingMessages" class="chat-state">正在恢复课程对话</div>
        <div v-else-if="loadError" class="chat-state error-state">
          <strong>会话暂时无法加载</strong>
          <span>{{ loadError }}</span>
          <button type="button" @click="initialize()">重新加载</button>
        </div>
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
    </div>
  </section>
</template>

<style scoped>
.workspace-chat-shell { position: relative; min-width: 0; height: 100dvh; display: grid; grid-template-columns: 38px minmax(0, 1fr); overflow: hidden; background: #fff; }
.workspace-chat { min-width: 0; min-height: 0; display: grid; grid-template-rows: 58px minmax(0, 1fr) auto; background: #fff; }
.chat-header { display: flex; align-items: center; gap: 12px; padding: 0 16px; border-bottom: 1px solid #e0e4e1; }
.course-identity { min-width: 0; display: flex; align-items: center; gap: 9px; }
.course-icon { width: 32px; height: 32px; display: grid; place-items: center; flex: 0 0 32px; border-radius: 7px; color: #155f4d; background: #dcece4; }
.course-identity > div { min-width: 0; display: grid; gap: 1px; }
.course-identity strong { overflow: hidden; color: #2b3731; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.course-identity span:not(.course-icon) { display: flex; align-items: center; gap: 5px; overflow: hidden; color: #7a847f; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.course-identity i { width: 5px; height: 5px; border-radius: 50%; background: #24946f; }
.header-action { width: 34px; height: 34px; display: grid; place-items: center; flex: 0 0 34px; border-radius: 6px; color: #66716b; }
.header-action:hover,
.header-action:focus-visible { color: #176b58; background: #edf2ef; }
.header-action:focus-visible { outline: 2px solid #287a66; outline-offset: 1px; }
.inspector-action { margin-left: auto; }
.session-drawer-toggle { display: none; }
.agent-status { display: inline-flex; align-items: center; gap: 5px; margin-left: auto; color: #6d7872; font-size: 10px; white-space: nowrap; }
.agent-status + .inspector-action { margin-left: 0; }
.agent-status i { width: 7px; height: 7px; border: 1px solid #268169; border-top-color: transparent; border-radius: 50%; animation: spin 700ms linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.chat-viewport { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 24px clamp(14px, 4vw, 52px); background: #fafbf9; }
.chat-state { height: 100%; display: grid; place-items: center; align-content: center; gap: 8px; color: #7b8580; font-size: 12px; text-align: center; }
.chat-state strong { color: #35423b; font-size: 14px; }
.chat-state button { min-height: 32px; padding: 0 11px; border: 1px solid #aec1b8; border-radius: 6px; color: #175f4d; background: #fff; font-weight: 700; }
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
  .workspace-chat-shell { height: calc(100dvh - 52px); grid-template-columns: minmax(0, 1fr); }
  .session-drawer-toggle { display: grid; }
  .chat-header { gap: 8px; }
}

@media (max-width: 620px) {
  .chat-header { padding: 0 10px; }
  .course-icon { display: none; }
  .chat-viewport { padding: 16px 10px; }
  .composer-prompts,
  .chat-composer > small { display: none; }
  .chat-composer { padding: 8px; }
}

@media (prefers-reduced-motion: reduce) {
  .agent-status i { animation: none; }
}
</style>
