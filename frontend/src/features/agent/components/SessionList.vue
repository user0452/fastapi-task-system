<script setup>
import { ref } from 'vue'
import { Archive, MessageSquare, MoreHorizontal, Plus } from 'lucide-vue-next'


defineProps({
  sessions: { type: Array, default: () => [] },
  activeId: { type: Number, default: null },
  loading: { type: Boolean, default: false }
})
const emit = defineEmits(['select', 'new', 'archive'])
const openMenuId = ref(null)

function shortDate(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(new Date(value))
}

function toggleMenu(sessionId) {
  openMenuId.value = Number(openMenuId.value) === Number(sessionId) ? null : sessionId
}

function archive(session) {
  openMenuId.value = null
  emit('archive', session)
}

function closeMenu() {
  openMenuId.value = null
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
        <div class="session-menu" @keydown.esc.stop="closeMenu">
          <button
            type="button"
            class="session-menu-trigger"
            title="会话操作"
            :aria-label="`打开会话操作：${session.title}`"
            :aria-expanded="Number(openMenuId) === Number(session.id)"
            aria-haspopup="menu"
            @click.stop="toggleMenu(session.id)"
          ><MoreHorizontal :size="16" /></button>
          <div
            v-if="Number(openMenuId) === Number(session.id)"
            class="session-menu-popover"
            role="menu"
          >
            <button
              type="button"
              role="menuitem"
              :aria-label="`归档会话：${session.title}`"
              @click.stop="archive(session)"
            ><Archive :size="14" /> 归档会话</button>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.session-panel { min-height: 0; display: flex; flex-direction: column; background: transparent; }
.session-heading { min-height: 64px; display: flex; align-items: center; justify-content: space-between; padding: 10px 12px 10px 18px; border-bottom: 1px solid var(--border-subtle); }
.session-heading strong { font-size: 14px; font-weight: 620; }
.session-heading button { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 12px; color: var(--text-secondary); }
.session-heading button:hover { color: var(--accent); background: var(--accent-soft); }
.session-state { min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; color: var(--text-tertiary); font-size: 12px; }
.session-list { min-height: 0; display: grid; align-content: start; gap: 3px; padding: 10px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: rgba(120, 126, 138, .3) transparent; }
.session-item { position: relative; min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr) 38px; align-items: center; border-radius: 13px; color: var(--text-secondary); transition: color var(--duration-fast) ease, background var(--duration-fast) ease; }
.session-item:hover { background: var(--color-surface-hover); }
.session-item.active { color: var(--accent); background: var(--accent-soft); }
.session-select { min-width: 0; min-height: 68px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 10px; padding: 10px 5px 10px 11px; color: inherit; text-align: left; }
.session-select:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; border-radius: 12px; }
.session-copy { min-width: 0; display: grid; gap: 2px; }
.session-copy strong,
.session-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-copy strong { color: inherit; font-size: 13px; font-weight: 600; }
.session-copy small { color: var(--text-tertiary); font-size: 11px; font-weight: 500; }
.session-meta { display: grid; justify-items: end; gap: 3px; color: var(--text-tertiary); font-size: 10px; white-space: nowrap; }
.session-meta > span:first-child { color: var(--text-secondary); }
.session-menu { position: relative; display: grid; place-items: center; }
.session-menu-trigger { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 11px; color: var(--text-tertiary); opacity: 0; }
.session-item:hover .session-menu-trigger,
.session-menu-trigger:focus-visible,
.session-menu-trigger[aria-expanded='true'] { opacity: 1; }
.session-menu-trigger:hover { color: var(--text-primary); background: rgba(255, 255, 255, .7); }
.session-menu-popover { position: absolute; z-index: 4; top: calc(100% + 4px); right: 0; width: 150px; padding: 5px; border: 1px solid var(--border-subtle); border-radius: 12px; background: #fff; box-shadow: var(--shadow-medium); }
.session-menu-popover button { width: 100%; min-height: 40px; display: flex; align-items: center; gap: 8px; padding: 0 10px; border-radius: 9px; color: var(--danger); font-size: 12px; text-align: left; }
.session-menu-popover button:hover,
.session-menu-popover button:focus-visible { background: rgba(215, 0, 21, .07); }

@media (max-width: 820px), (hover: none) {
  .session-menu-trigger { width: 44px; height: 44px; opacity: 1; }
  .session-menu-popover { width: 164px; }
  .session-menu-popover button { min-height: 44px; font-size: 13px; }
}
</style>
