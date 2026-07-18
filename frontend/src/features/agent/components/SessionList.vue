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
      <div
        v-for="session in sessions"
        :key="session.id"
        class="session-item"
        :class="{ active: activeId === session.id }"
      >
        <button
          type="button"
          class="session-select"
          :aria-current="activeId === session.id ? 'true' : undefined"
          @click="$emit('select', session)"
        >
          <span class="session-copy">
            <strong>{{ session.title }}</strong>
            <small>{{ session.last_message || session.course_name || '新对话' }}</small>
          </span>
          <span class="session-meta">
            <span>{{ activeId === session.id ? '当前' : session.status === 'active' ? '可继续' : session.status }}</span>
            <time>{{ shortDate(session.updated_at) }}</time>
          </span>
        </button>
        <button
          type="button"
          class="archive-action"
          title="归档会话"
          :aria-label="`归档会话：${session.title}`"
          @click="$emit('archive', session)"
        ><Archive :size="14" /></button>
      </div>
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
.session-list { min-height: 0; display: grid; align-content: start; gap: 2px; padding: 7px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #b8c5be transparent; }
.session-item { position: relative; min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr) 28px; align-items: center; border-radius: 6px; color: #53605a; }
.session-item:hover { background: #e6ebe8; }
.session-item.active { color: #174f42; background: #dbe9e3; }
.session-select { min-width: 0; min-height: 58px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 8px; padding: 8px 6px 8px 9px; color: inherit; text-align: left; }
.session-select:focus-visible { outline: 2px solid #287a66; outline-offset: -2px; border-radius: 5px; }
.session-copy { min-width: 0; display: grid; gap: 2px; }
.session-copy strong,
.session-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-copy strong { font-size: 10px; }
.session-copy small { color: #7a847f; font-size: 8px; font-weight: 500; }
.session-meta { display: grid; justify-items: end; gap: 3px; color: #89928d; font-size: 8px; white-space: nowrap; }
.session-meta > span:first-child { color: #63716a; }
.archive-action { width: 26px; height: 26px; display: grid; place-items: center; border-radius: 5px; color: #7a847f; opacity: 0; }
.session-item:hover .archive-action,
.archive-action:focus-visible { opacity: 1; }
.archive-action:hover { color: #9f3e36; background: #f7e6e4; }
</style>
