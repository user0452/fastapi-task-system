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
.session-menu { position: relative; display: grid; place-items: center; }
.session-menu-trigger { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 5px; color: #7a847f; opacity: 0; }
.session-item:hover .session-menu-trigger,
.session-menu-trigger:focus-visible,
.session-menu-trigger[aria-expanded='true'] { opacity: 1; }
.session-menu-trigger:hover { color: #34413a; background: #dce3df; }
.session-menu-popover { position: absolute; z-index: 4; top: calc(100% + 3px); right: 0; width: 126px; padding: 4px; border: 1px solid #d4dcd7; border-radius: 7px; background: #fff; box-shadow: 0 10px 28px rgba(30, 42, 36, .14); }
.session-menu-popover button { width: 100%; min-height: 36px; display: flex; align-items: center; gap: 7px; padding: 0 8px; border-radius: 5px; color: #9f3e36; font-size: 10px; text-align: left; }
.session-menu-popover button:hover,
.session-menu-popover button:focus-visible { background: #f7e6e4; }

@media (max-width: 820px), (hover: none) {
  .session-menu-trigger { width: 44px; height: 44px; opacity: 1; }
  .session-menu-popover { width: 152px; }
  .session-menu-popover button { min-height: 44px; font-size: 12px; }
}
</style>
