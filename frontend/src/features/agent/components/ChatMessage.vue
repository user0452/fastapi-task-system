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
</script>

<template>
  <article class="chat-message" :class="message.role">
    <span class="message-avatar"><UserRound v-if="message.role === 'user'" :size="15" /><Bot v-else :size="15" /></span>
    <div class="message-body">
      <div v-if="message.role === 'assistant'" class="message-text markdown-body" v-html="renderedContent"></div>
      <p v-else class="message-text">{{ message.content }}</p>
      <span v-if="message.streaming" class="typing-indicator"><i></i><i></i><i></i></span>

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
.chat-message { display: grid; grid-template-columns: 28px minmax(0, 1fr); align-items: start; gap: 8px; max-width: 820px; }
.chat-message.user { margin-left: auto; grid-template-columns: minmax(0, 1fr) 28px; }
.chat-message.user .message-avatar { grid-column: 2; }
.chat-message.user .message-body { grid-column: 1; grid-row: 1; justify-self: end; max-width: min(620px, 86%); color: #ffffff; background: #176b58; border-color: #176b58; }
.message-avatar { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; color: #176b58; background: #dcece5; }
.user .message-avatar { color: #5d6862; background: #e7ebe8; }
.message-body { min-width: 0; padding: 9px 11px; border: 1px solid #d9e0dc; border-radius: 7px; background: #ffffff; }
.chat-message.assistant .message-body { padding: 2px 0; border: 0; background: transparent; }
.message-text { color: inherit; font-size: 13px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.markdown-body { max-width: 100%; overflow-x: auto; color: #2f3b35; font-size: 14px; line-height: 1.72; white-space: normal; }
.markdown-body :deep(> :first-child) { margin-top: 0; }
.markdown-body :deep(> :last-child) { margin-bottom: 0; }
.markdown-body :deep(p) { margin: 0 0 10px; }
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) { margin: 20px 0 8px; color: #1f2b25; line-height: 1.35; letter-spacing: -.01em; }
.markdown-body :deep(h1) { font-size: 18px; font-weight: 730; }
.markdown-body :deep(h2) { font-size: 16px; font-weight: 730; }
.markdown-body :deep(h3),
.markdown-body :deep(h4) { font-size: 14px; font-weight: 720; }
.markdown-body :deep(strong) { color: #1f2b25; font-weight: 720; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 7px 0 12px; padding-left: 22px; }
.markdown-body :deep(li) { padding-left: 2px; }
.markdown-body :deep(li + li) { margin-top: 4px; }
.markdown-body :deep(li > ul),
.markdown-body :deep(li > ol) { margin: 4px 0 2px; }
.markdown-body :deep(blockquote) { margin: 12px 0; padding: 2px 0 2px 12px; border-left: 2px solid #82aa9d; color: #5d6a64; }
.markdown-body :deep(blockquote p) { margin: 0; }
.markdown-body :deep(hr) { height: 1px; margin: 18px 0; border: 0; background: #dfe5e1; }
.markdown-body :deep(code) { padding: 1px 4px; border-radius: 4px; color: #245f50; background: #edf3f0; font-family: Consolas, "SFMono-Regular", monospace; font-size: .9em; }
.markdown-body :deep(pre) { max-width: 100%; margin: 12px 0; overflow-x: auto; padding: 12px 13px; border: 1px solid #dce4df; border-radius: 7px; background: #f5f7f6; }
.markdown-body :deep(pre code) { padding: 0; color: #26332d; background: transparent; font-size: 12px; line-height: 1.65; }
.markdown-body :deep(table) { width: 100%; min-width: 440px; margin: 13px 0 15px; border-spacing: 0; border-collapse: separate; border: 1px solid #dce3df; border-radius: 7px; font-size: 12px; line-height: 1.55; }
.markdown-body :deep(th),
.markdown-body :deep(td) { padding: 8px 10px; border-right: 1px solid #e4e9e6; border-bottom: 1px solid #e4e9e6; text-align: left; vertical-align: top; }
.markdown-body :deep(th) { color: #34423b; background: #f2f5f3; font-weight: 720; }
.markdown-body :deep(tr > :last-child) { border-right: 0; }
.markdown-body :deep(tbody tr:last-child td) { border-bottom: 0; }
.markdown-body :deep(a) { color: #176b58; text-decoration: underline; text-decoration-color: #a8c8bd; text-underline-offset: 3px; }
.typing-indicator { display: inline-flex; gap: 3px; padding-top: 3px; }
.typing-indicator i { width: 4px; height: 4px; border-radius: 50%; background: #698078; animation: blink 900ms infinite; }
.typing-indicator i:nth-child(2) { animation-delay: 120ms; }
.typing-indicator i:nth-child(3) { animation-delay: 240ms; }
@keyframes blink { 50% { opacity: .25; } }
.message-card { display: grid; gap: 2px; margin-top: 9px; padding: 8px 9px; border-left: 3px solid #4b8271; background: #f1f5f3; }
.message-card strong { font-size: 12px; }
.message-card span { color: #6f7a74; font-size: 10px; }
.message-actions { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 9px; }
.message-actions button { min-height: 31px; padding: 0 10px; border: 1px solid #b8c9c1; border-radius: 5px; color: #175e4c; background: #ffffff; font-size: 10px; font-weight: 750; }
.resolved-action { display: inline-block; margin-top: 8px; color: #7a847f; font-size: 10px; }
@media (max-width: 620px) {
}
</style>
