<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { PanelLeftOpen, Plus } from 'lucide-vue-next'
import SessionList from './SessionList.vue'


const props = defineProps({
  sessions: { type: Array, default: () => [] },
  activeId: { type: Number, default: null },
  loading: { type: Boolean, default: false },
  mobileOpen: { type: Boolean, default: false }
})
const emit = defineEmits(['select', 'new', 'archive', 'close-mobile'])
const pointerInside = ref(false)
const focusInside = ref(false)
const manualExpanded = ref(false)
let closeTimer = null

const expanded = computed(() => (
  props.mobileOpen || pointerInside.value || focusInside.value || manualExpanded.value
))

function clearCloseTimer() {
  if (closeTimer) window.clearTimeout(closeTimer)
  closeTimer = null
}

function openForPointer() {
  clearCloseTimer()
  pointerInside.value = true
}

function schedulePointerClose() {
  clearCloseTimer()
  closeTimer = window.setTimeout(() => {
    pointerInside.value = false
    if (!focusInside.value) manualExpanded.value = false
  }, 200)
}

function onFocusIn() {
  clearCloseTimer()
  focusInside.value = true
}

function onFocusOut(event) {
  if (event.currentTarget.contains(event.relatedTarget)) return
  focusInside.value = false
  schedulePointerClose()
}

function toggleExpanded() {
  clearCloseTimer()
  manualExpanded.value = !manualExpanded.value
}

function close() {
  clearCloseTimer()
  pointerInside.value = false
  focusInside.value = false
  manualExpanded.value = false
  emit('close-mobile')
}

function handleKeydown(event) {
  if (event.key !== 'Escape') return
  event.preventDefault()
  close()
}

function selectSession(session) {
  emit('select', session)
  if (props.mobileOpen) emit('close-mobile')
}

onBeforeUnmount(clearCloseTimer)
</script>

<template>
  <div class="session-rail-slot" :class="{ 'mobile-open': mobileOpen }">
    <button
      v-if="mobileOpen"
      type="button"
      class="session-drawer-scrim"
      aria-label="关闭历史会话"
      @click="close"
    ></button>
    <aside
      class="hover-session-rail"
      :class="{ expanded }"
      aria-label="当前课程历史会话"
      @mouseenter="openForPointer"
      @mouseleave="schedulePointerClose"
      @focusin="onFocusIn"
      @focusout="onFocusOut"
      @keydown="handleKeydown"
    >
      <div class="collapsed-rail">
        <button
          type="button"
          class="rail-control"
          aria-label="新建会话"
          title="新建会话"
          @click="$emit('new')"
        ><Plus :size="16" /></button>
        <div class="session-markers" aria-label="会话快捷切换">
          <button
            v-for="item in sessions"
            :key="item.id"
            type="button"
            class="session-marker"
            :class="{ active: Number(activeId) === Number(item.id) }"
            :aria-label="`切换到会话：${item.title}`"
            :title="item.title"
            @click="selectSession(item)"
          ><span></span></button>
        </div>
        <button
          type="button"
          class="rail-control expand-control"
          aria-label="展开历史会话"
          :aria-expanded="expanded"
          @click="toggleExpanded"
        ><PanelLeftOpen :size="15" /></button>
      </div>

      <transition name="session-popover">
        <div v-if="expanded" class="expanded-session-panel">
          <SessionList
            :sessions="sessions"
            :active-id="activeId"
            :loading="loading"
            @select="selectSession"
            @new="$emit('new')"
            @archive="$emit('archive', $event)"
          />
        </div>
      </transition>
    </aside>
  </div>
</template>

<style scoped>
.session-rail-slot { position: relative; z-index: 12; width: 38px; min-width: 38px; min-height: 0; }
.hover-session-rail { position: absolute; inset: 0 auto 0 0; width: 38px; min-height: 0; border-right: 1px solid #e0e5e2; background: #f4f6f4; }
.collapsed-rail { height: 100%; display: grid; grid-template-rows: 48px minmax(0, 1fr) 40px; justify-items: center; padding: 5px 0; }
.rail-control { width: 30px; height: 30px; display: grid; place-items: center; align-self: center; border-radius: 6px; color: #5f6b65; }
.rail-control:hover,
.rail-control:focus-visible { color: #155f4d; background: #e3ebe7; }
.rail-control:focus-visible,
.session-marker:focus-visible { outline: 2px solid #287a66; outline-offset: 1px; }
.session-markers { width: 100%; min-height: 0; display: grid; align-content: start; justify-items: center; gap: 2px; overflow-y: auto; padding: 6px 0; scrollbar-width: none; }
.session-markers::-webkit-scrollbar { display: none; }
.session-marker { width: 32px; height: 25px; display: grid; place-items: center; }
.session-marker span { width: 12px; height: 2px; border-radius: 1px; background: #a9b5af; transition: width 170ms ease, background-color 170ms ease; }
.session-marker:hover span { width: 18px; background: #71827a; }
.session-marker.active span { width: 23px; height: 3px; background: #176b58; }
.expanded-session-panel { position: absolute; inset: 0 auto 0 0; z-index: 2; width: 280px; overflow: hidden; border-right: 1px solid #cfd8d3; background: #f2f4f2; box-shadow: 10px 0 28px rgba(31, 58, 47, .12); }
.expanded-session-panel :deep(.session-panel) { height: 100%; }
.session-popover-enter-active,
.session-popover-leave-active { transition: opacity 180ms ease, transform 180ms ease; }
.session-popover-enter-from,
.session-popover-leave-to { opacity: 0; transform: translateX(-10px); }
.session-drawer-scrim { display: none; }

@media (max-width: 820px) {
  .session-rail-slot { position: absolute; inset: 0; z-index: 45; width: 0; min-width: 0; pointer-events: none; }
  .session-rail-slot.mobile-open { width: 100%; pointer-events: auto; }
  .hover-session-rail { width: min(300px, 88vw); transform: translateX(-101%); border-right-color: #cfd8d3; transition: transform 190ms ease; }
  .mobile-open .hover-session-rail { transform: translateX(0); }
  .collapsed-rail { display: none; }
  .expanded-session-panel { width: 100%; box-shadow: none; }
  .session-drawer-scrim { position: absolute; inset: 0; display: block; width: 100%; background: rgba(31, 45, 38, .28); }
}

@media (prefers-reduced-motion: reduce) {
  .session-marker span,
  .session-popover-enter-active,
  .session-popover-leave-active,
  .hover-session-rail { transition: none; }
}
</style>
