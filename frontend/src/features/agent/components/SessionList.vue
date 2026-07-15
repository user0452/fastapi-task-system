<script setup>
import { Archive, MessageSquare, Plus } from 'lucide-vue-next'


defineProps({
  sessions: { type: Array, default: () => [] },
  activeId: { type: Number, default: null },
  loading: { type: Boolean, default: false }
})
defineEmits(['select', 'new', 'archive'])

function shortDate(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(new Date(value))
}
</script>

<template>
  <aside class="session-panel">
    <div class="session-heading">
      <strong>对话</strong>
      <button type="button" title="新建对话" aria-label="新建对话" @click="$emit('new')"><Plus :size="17" /></button>
    </div>
    <div v-if="loading" class="session-state">正在加载</div>
    <div v-else-if="!sessions.length" class="session-state">
      <MessageSquare :size="20" />
      <span>还没有历史对话</span>
    </div>
    <div v-else class="session-list">
      <button
        v-for="session in sessions"
        :key="session.id"
        type="button"
        class="session-item"
        :class="{ active: activeId === session.id }"
        @click="$emit('select', session)"
      >
        <span class="session-copy">
          <strong>{{ session.title }}</strong>
          <small>{{ session.last_message || session.course_name || '新对话' }}</small>
        </span>
        <time>{{ shortDate(session.updated_at) }}</time>
        <span
          class="archive-action"
          role="button"
          tabindex="0"
          title="归档会话"
          aria-label="归档会话"
          @click.stop="$emit('archive', session)"
          @keydown.enter.stop="$emit('archive', session)"
        ><Archive :size="14" /></span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.session-panel { min-height: 0; display: flex; flex-direction: column; background: #f2f4f2; border-right: 1px solid #dce2de; }
.session-heading { min-height: 50px; display: flex; align-items: center; justify-content: space-between; padding: 8px 11px 8px 14px; border-bottom: 1px solid #dce2de; }
.session-heading strong { font-size: 12px; }
.session-heading button { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 6px; color: #52605a; }
.session-heading button:hover { color: #176b58; background: #e1e8e4; }
.session-state { min-height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #7a847f; font-size: 10px; }
.session-list { min-height: 0; display: grid; align-content: start; gap: 2px; padding: 7px; overflow-y: auto; }
.session-item { min-width: 0; min-height: 54px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 7px; padding: 8px 7px 8px 9px; border-radius: 6px; color: #53605a; text-align: left; }
.session-item:hover { background: #e6ebe8; }
.session-item.active { color: #174f42; background: #dbe9e3; }
.session-copy { min-width: 0; display: grid; gap: 2px; }
.session-copy strong,
.session-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-copy strong { font-size: 10px; }
.session-copy small { color: #7a847f; font-size: 8px; font-weight: 500; }
.session-item time { color: #89928d; font-size: 8px; }
.archive-action { display: none; width: 22px; height: 22px; place-items: center; border-radius: 5px; color: #7a847f; }
.session-item:hover .archive-action { display: grid; }
.archive-action:hover { color: #9f3e36; background: #f7e6e4; }
</style>
