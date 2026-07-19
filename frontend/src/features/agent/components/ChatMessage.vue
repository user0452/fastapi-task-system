<script setup>
import { computed } from 'vue'
import { Bot, UserRound } from 'lucide-vue-next'
import SourceBubbles from './SourceBubbles.vue'
import ExecutionSummary from './ExecutionSummary.vue'
import ConfirmationBar from './ConfirmationBar.vue'
import PracticeCard from './PracticeCard.vue'
import { renderAssistantMarkdown } from '../markdown'


const props = defineProps({
  message: { type: Object, required: true },
  courseId: { type: Number, default: null },
  actionBusy: { type: Boolean, default: false }
})
const emit = defineEmits(['navigate', 'open-panel', 'decide', 'resource-updated', 'practice', 'data-changed'])
const renderedContent = computed(() => (
  props.message.role === 'assistant' ? renderAssistantMarkdown(props.message.content) : ''
))
const activity = computed(() => {
  if (!props.message.streaming) return null
  const current = props.message.activity
  if (current?.message) return current
  return {
    phase: props.message.content ? 'answering' : 'thinking',
    message: props.message.content ? '正在生成回答' : '正在思考',
    tool: null
  }
})
const activityTone = computed(() => {
  const phase = activity.value?.phase
  if (phase === 'web_search') return 'search'
  if (phase === 'tool') return 'tool'
  if (phase === 'answering') return 'answer'
  return 'think'
})

function cards() {
  return props.message.tool_calls?.cards || []
}

function actions() {
  return props.message.tool_calls?.actions || []
}

function confirmation() {
  return props.message.tool_calls?.confirmation || null
}

function resources() {
  return props.message.tool_calls?.resources || []
}

function executionSummary() {
  return props.message.tool_calls?.execution_summary || null
}

function triggerAction(action) {
  if (action.type === 'open_panel' && action.panel) emit('open-panel', action.panel)
  else if (action.to) emit('navigate', action.to)
}

async function handleMarkdownClick(event) {
  const button = event.target.closest('.code-copy-button')
  if (!button) return
  const content = button.parentElement?.querySelector('code')?.textContent || ''
  if (!content || !navigator.clipboard?.writeText) return
  await navigator.clipboard.writeText(content)
  button.textContent = '已复制'
  window.setTimeout(() => { button.textContent = '复制' }, 1200)
}
</script>

<template>
  <article class="chat-message" :class="message.role">
    <span class="message-avatar"><UserRound v-if="message.role === 'user'" :size="15" /><Bot v-else :size="15" /></span>
    <div class="message-body">
      <div v-if="activity" class="activity-chip" :class="`tone-${activityTone}`" aria-live="polite">
        <i></i>
        <span>{{ activity.message }}</span>
      </div>
      <div v-if="message.role === 'assistant' && renderedContent" class="message-text markdown-body" v-html="renderedContent" @click="handleMarkdownClick"></div>
      <p v-else-if="message.role !== 'assistant'" class="message-text">{{ message.content }}</p>
      <span v-if="message.streaming && !activity" class="typing-indicator"><i></i><i></i><i></i></span>

      <div v-for="(card, index) in cards().filter(item => item.type !== 'practice')" :key="`${card.type}-${index}`" class="message-card">
        <template v-if="card.type === 'today'">
          <strong>{{ card.data ? '今日学习已就绪' : '今天没有待完成单元' }}</strong>
          <span v-if="card.data">{{ card.data.items?.length || 0 }} 项 · {{ card.data.estimated_minutes }} 分钟</span>
        </template>
        <template v-else-if="card.type === 'progress'">
          <strong>计划完成 {{ card.data.completion_rate }}%</strong>
          <span>{{ card.data.weak_points?.length || 0 }} 个知识点需要优先加强</span>
        </template>
        <template v-else-if="card.type === 'diagnostic'">
          <strong>{{ card.data.submitted ? '课程诊断已完成' : `${card.data.questions?.length || 0} 道诊断题` }}</strong>
          <span>{{ card.reused ? '已恢复现有诊断' : '新诊断已生成' }}</span>
        </template>
        <template v-else-if="card.type === 'plan'">
          <strong>{{ card.data ? `${card.data.sessions?.length || 0} 个学习单元` : '尚未生成计划' }}</strong>
          <span v-if="card.data">{{ card.data.start_date }} 至 {{ card.data.end_date }}</span>
        </template>
        <template v-else-if="card.type === 'wrong_answers'">
          <strong>{{ card.data.total }} 道错题</strong>
          <span>{{ card.data.items?.[0]?.knowledge_point_name || '完成练习后会记录错因' }}</span>
        </template>
      </div>

      <PracticeCard
        v-for="card in cards().filter(item => item.type === 'practice')"
        :key="`practice-${card.data.id}`"
        :practice="card.data"
        @completed="result => $emit('data-changed', result)"
      />

      <SourceBubbles :citations="message.sources || []" :resources="resources()" :course-id="courseId" />
      <ExecutionSummary :summary="executionSummary()" />

      <div v-if="actions().length" class="message-actions">
        <button v-for="action in actions()" :key="`${action.panel || ''}-${action.to || action.label}`" type="button" @click="triggerAction(action)">{{ action.label }}</button>
      </div>

      <ConfirmationBar
        v-if="confirmation()?.status === 'pending'"
        :confirmation="confirmation()"
        :busy="actionBusy"
        @decide="confirmed => $emit('decide', confirmation(), confirmed)"
      />
      <span v-else-if="confirmation()" class="resolved-action">
        该操作已{{ confirmation().status === 'executed' ? '执行' : confirmation().status === 'cancelled' ? '取消' : '失效' }}
      </span>
    </div>
  </article>
</template>

<style scoped>
.chat-message {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  align-items: start;
  gap: 11px;
  max-width: var(--content-chat);
}
.chat-message.user { margin-left: auto; grid-template-columns: minmax(0, 1fr) 32px; }
.chat-message.user .message-avatar { grid-column: 2; }
.chat-message.user .message-body {
  grid-column: 1;
  grid-row: 1;
  justify-self: end;
  max-width: min(640px, 88%);
  padding: 12px 16px;
  border: 1px solid rgba(52, 120, 246, .1);
  border-radius: 21px 21px 7px 21px;
  color: #21324d;
  background: var(--accent-soft);
  box-shadow: var(--shadow-hairline);
}
.message-avatar {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 11px;
  color: var(--accent);
  background: var(--accent-soft);
}
.user .message-avatar { color: var(--text-secondary); background: var(--surface-tertiary); }
.message-body {
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-medium);
  background: var(--surface-primary);
}
.chat-message.assistant .message-body { padding: 2px 0; border: 0; background: transparent; }
.activity-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 30px;
  margin: 0 0 10px;
  padding: 0 11px;
  border-radius: var(--radius-round);
  color: var(--text-secondary);
  background: var(--surface-muted);
  font-size: 12px;
  font-weight: 600;
}
.activity-chip i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 0 rgba(52, 120, 246, .35);
  animation: pulse 1.2s ease-out infinite;
}
.activity-chip.tone-think { color: var(--text-secondary); background: var(--surface-muted); }
.activity-chip.tone-tool { color: var(--text-accent); background: var(--accent-soft); }
.activity-chip.tone-search { color: var(--text-accent); background: var(--accent-soft); }
.activity-chip.tone-answer { color: var(--success); background: var(--success-soft); }
.activity-chip.tone-answer i { background: var(--success); }
.message-text {
  color: inherit;
  font-size: 15px;
  line-height: 1.72;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.markdown-body {
  max-width: 100%;
  overflow-x: auto;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.76;
  white-space: normal;
}
.markdown-body :deep(> :first-child) { margin-top: 0; }
.markdown-body :deep(> :last-child) { margin-bottom: 0; }
.markdown-body :deep(p) { margin: 0 0 10px; }
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) { margin: 22px 0 9px; color: var(--text-primary); line-height: 1.35; letter-spacing: -.02em; }
.markdown-body :deep(h1) { font-size: 22px; font-weight: 650; }
.markdown-body :deep(h2) { font-size: 19px; font-weight: 640; }
.markdown-body :deep(h3),
.markdown-body :deep(h4) { font-size: 17px; font-weight: 630; }
.markdown-body :deep(strong) { color: var(--text-primary); font-weight: 650; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 7px 0 12px; padding-left: 22px; }
.markdown-body :deep(li) { padding-left: 2px; }
.markdown-body :deep(li + li) { margin-top: 4px; }
.markdown-body :deep(li > ul),
.markdown-body :deep(li > ol) { margin: 4px 0 2px; }
.markdown-body :deep(blockquote) {
  margin: 14px 0;
  padding: 4px 0 4px 14px;
  border-left: 3px solid rgba(52, 120, 246, .38);
  color: var(--text-secondary);
}
.markdown-body :deep(blockquote p) { margin: 0; }
.markdown-body :deep(hr) {
  height: 1px;
  margin: 20px 0;
  border: 0;
  background: var(--border-subtle);
}
.markdown-body :deep(code) {
  padding: 2px 5px;
  border-radius: 6px;
  color: var(--text-accent);
  background: var(--accent-softer);
  font-family: var(--font-mono);
  font-size: .9em;
}
.markdown-body :deep(.code-block) { position: relative; margin: 14px 0; }
.markdown-body :deep(pre) {
  max-width: 100%;
  margin: 0;
  overflow-x: auto;
  padding: 18px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-medium);
  background: var(--surface-secondary);
}
.markdown-body :deep(pre code) {
  padding: 0;
  color: var(--text-primary);
  background: transparent;
  font-size: 13px;
  line-height: 1.68;
}
.markdown-body :deep(.code-copy-button) {
  position: absolute;
  z-index: 2;
  top: 9px;
  right: 9px;
  min-width: 52px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 9px;
  color: var(--text-secondary);
  background: var(--surface-elevated);
  font-size: 12px;
  font-weight: var(--weight-medium);
  box-shadow: var(--shadow-small);
}
.markdown-body :deep(.code-copy-button:hover) { color: var(--accent); }
.markdown-body :deep(table) {
  width: 100%;
  min-width: 440px;
  margin: 13px 0 15px;
  border-spacing: 0;
  border-collapse: separate;
  border: 1px solid var(--border-strong);
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.55;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 8px 10px;
  border-right: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
  text-align: left;
  vertical-align: top;
}
.markdown-body :deep(th) {
  color: var(--text-primary);
  background: var(--surface-tertiary);
  font-weight: 680;
}
.markdown-body :deep(tr > :last-child) { border-right: 0; }
.markdown-body :deep(tbody tr:last-child td) { border-bottom: 0; }
.markdown-body :deep(a) {
  color: var(--accent);
  text-decoration: underline;
  text-decoration-color: rgba(52, 120, 246, .32);
  text-underline-offset: 3px;
}
.typing-indicator { display: inline-flex; gap: 3px; padding-top: 3px; }
.typing-indicator i {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--text-tertiary);
  animation: blink 900ms infinite;
}
.typing-indicator i:nth-child(2) { animation-delay: 120ms; }
.typing-indicator i:nth-child(3) { animation-delay: 240ms; }
@keyframes blink { 50% { opacity: .25; } }
@keyframes pulse {
  0% { transform: scale(.85); box-shadow: 0 0 0 0 rgba(52, 120, 246, .35); }
  70% { transform: scale(1); box-shadow: 0 0 0 7px rgba(52, 120, 246, 0); }
  100% { transform: scale(.85); box-shadow: 0 0 0 0 rgba(52, 120, 246, 0); }
}
.message-card {
  display: grid;
  gap: 4px;
  margin-top: 12px;
  padding: 12px 14px;
  border-left: 3px solid var(--accent);
  border-radius: 0 12px 12px 0;
  background: var(--accent-softer);
}
.message-card strong { font-size: 14px; }
.message-card span { color: var(--text-secondary); font-size: 13px; }
.message-actions { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 9px; }
.message-actions button {
  min-height: 38px;
  padding: 0 13px;
  border: 1px solid var(--border-accent);
  border-radius: var(--radius-small);
  color: var(--accent);
  background: var(--surface-primary);
  font-size: 13px;
  font-weight: 600;
}
.resolved-action {
  display: inline-block;
  margin-top: 9px;
  color: var(--text-tertiary);
  font-size: 12px;
}
@media (max-width: 620px) {
  .chat-message { grid-template-columns: 28px minmax(0, 1fr); gap: 8px; }
  .chat-message.user { grid-template-columns: minmax(0, 1fr) 28px; }
  .message-avatar { width: 28px; height: 28px; border-radius: 9px; }
  .chat-message.user .message-body { max-width: 92%; }
}
@media (prefers-reduced-motion: reduce) {
  .activity-chip i,
  .typing-indicator i { animation: none; }
}
</style>
