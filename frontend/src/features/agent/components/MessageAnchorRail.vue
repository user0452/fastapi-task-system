<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { createMessageAnchors } from '../messageAnchors'


const props = defineProps({
  messages: { type: Array, default: () => [] },
  activeMessageId: { type: [Number, String], default: null },
  mobileOpen: { type: Boolean, default: false }
})
const emit = defineEmits(['jump', 'close-mobile'])
const itemElements = ref(new Map())
const railExpanded = ref(false)
const hoveredId = ref(null)
const anchors = computed(() => createMessageAnchors(props.messages))

function setItemElement(id, element) {
  if (element) itemElements.value.set(String(id), element)
  else itemElements.value.delete(String(id))
}

function jump(id) {
  emit('jump', id)
  if (props.mobileOpen) emit('close-mobile')
}

function expandRail() {
  railExpanded.value = true
}

function collapseRail() {
  railExpanded.value = false
  hoveredId.value = null
}

function showPreview(id) {
  railExpanded.value = true
  hoveredId.value = id
}

function hidePreview(id) {
  if (String(hoveredId.value) === String(id)) hoveredId.value = null
}

watch(() => props.activeMessageId, async id => {
  if (id == null) return
  await nextTick()
  const element = itemElements.value.get(String(id))
  if (typeof element?.scrollIntoView === 'function') {
    element.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }
})
</script>

<template>
  <div
    class="message-anchor-slot"
    :class="{
      'mobile-open': mobileOpen,
      expanded: railExpanded
    }"
  >
    <button
      v-if="mobileOpen"
      class="outline-scrim"
      type="button"
      aria-label="关闭本次对话目录"
      @click="$emit('close-mobile')"
    ></button>
    <aside
      class="message-anchor-rail"
      aria-label="本次对话目录"
      @mouseenter="expandRail"
      @mouseleave="collapseRail"
      @focusin="expandRail"
      @focusout="event => {
        if (!event.currentTarget.contains(event.relatedTarget)) collapseRail()
      }"
    >
      <nav aria-label="用户消息目录">
        <div
          v-for="(anchor, index) in anchors"
          :key="anchor.id"
          class="anchor-row"
          :class="{
            active: String(activeMessageId) === String(anchor.id),
            previewing: String(hoveredId) === String(anchor.id)
          }"
          @mouseenter="showPreview(anchor.id)"
          @mouseleave="hidePreview(anchor.id)"
          @focusin="showPreview(anchor.id)"
          @focusout="hidePreview(anchor.id)"
        >
          <button
            :ref="element => setItemElement(anchor.id, element)"
            type="button"
            class="anchor-item"
            :aria-label="`跳转到消息 ${index + 1}：${anchor.title}`"
            :title="anchor.title"
            :aria-current="String(activeMessageId) === String(anchor.id) ? 'location' : undefined"
            @click="jump(anchor.id)"
          >
            <i class="anchor-bar"></i>
            <span class="anchor-summary">{{ anchor.title }}</span>
          </button>
        </div>
      </nav>
    </aside>
  </div>
</template>

<style scoped>
.message-anchor-slot {
  position: absolute;
  z-index: 45;
  top: 50%;
  left: 10px;
  width: 36px;
  min-width: 36px;
  height: min(68vh, 560px);
  display: flex;
  align-items: center;
  justify-content: flex-start;
  overflow: visible;
  padding: 0;
  background: transparent;
  pointer-events: none;
  transform: translateY(-50%);
}
.message-anchor-slot.expanded {
  z-index: 70;
  width: min(260px, 32vw);
  height: min(78vh, 680px);
}
.message-anchor-rail {
  pointer-events: auto;
  position: relative;
  z-index: 1;
  width: 28px;
  height: 100%;
  max-height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: visible;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
  transition: width var(--duration-fast) var(--ease-out);
}
.message-anchor-slot.expanded .message-anchor-rail {
  width: min(248px, 30vw);
}
.message-anchor-rail nav {
  min-height: 0;
  flex: 1;
  display: grid;
  align-content: center;
  gap: 8px;
  overflow-x: visible;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px 0;
  scrollbar-width: none;
}
.message-anchor-rail nav::-webkit-scrollbar {
  width: 0;
  height: 0;
}
.message-anchor-slot.expanded .message-anchor-rail nav {
  align-content: safe center;
  gap: 7px;
  padding: 10px 0;
  scrollbar-width: none;
}
.message-anchor-slot.expanded .message-anchor-rail nav::-webkit-scrollbar {
  width: 0;
  height: 0;
}
.message-anchor-slot.expanded .message-anchor-rail nav::-webkit-scrollbar-thumb {
  background: transparent;
}
.anchor-row {
  position: relative;
  display: grid;
  justify-items: start;
  padding-left: 4px;
}
.anchor-item {
  min-width: 0;
  width: 24px;
  height: 16px;
  display: grid;
  grid-template-columns: 18px;
  align-items: center;
  gap: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  overflow: visible;
  background: transparent;
  box-shadow: none;
  transition:
    width var(--duration-fast) var(--ease-out),
    height var(--duration-fast) ease,
    padding var(--duration-fast) ease,
    grid-template-columns var(--duration-fast) ease;
}
.message-anchor-slot.expanded .anchor-item {
  width: min(236px, calc(30vw - 12px));
  height: 28px;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 10px;
  padding: 0 4px 0 2px;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}
.anchor-bar {
  width: 12px;
  height: 2px;
  justify-self: center;
  border-radius: 999px;
  background: rgba(0, 0, 0, .16);
  transition:
    width var(--duration-fast) var(--ease-out),
    height var(--duration-fast) ease,
    background var(--duration-fast) ease,
    box-shadow var(--duration-fast) ease;
}
.message-anchor-slot.expanded .anchor-bar {
  width: 16px;
  height: 3px;
  background: rgba(0, 0, 0, .26);
}
.anchor-summary {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 560;
  line-height: 1.35;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0;
  transform: translateX(-4px);
  text-shadow:
    0 0 8px rgba(255, 255, 255, .95),
    0 1px 0 rgba(255, 255, 255, .9);
  transition: opacity var(--duration-fast) ease, transform var(--duration-fast) var(--ease-out), color var(--duration-fast) ease;
}
.message-anchor-slot.expanded .anchor-summary {
  opacity: 1;
  transform: translateX(0);
}
.anchor-row.previewing .anchor-item,
.anchor-item:focus-visible {
  background: transparent;
}
.anchor-row.previewing .anchor-bar,
.anchor-item:focus-visible .anchor-bar {
  width: 24px;
  height: 5px;
  background: var(--accent);
  box-shadow: none;
}
.anchor-row.previewing .anchor-summary,
.anchor-item:focus-visible .anchor-summary {
  color: var(--accent);
  font-weight: 650;
}
.anchor-row.active .anchor-bar {
  width: 16px;
  height: 3px;
  background: var(--accent);
  box-shadow: none;
}
.message-anchor-slot.expanded .anchor-row.active .anchor-item {
  background: transparent;
}
.message-anchor-slot.expanded .anchor-row.active .anchor-bar {
  width: 18px;
  height: 4px;
}
.message-anchor-slot.expanded .anchor-row.active .anchor-summary {
  color: var(--accent);
}
.anchor-row.active.previewing .anchor-bar {
  width: 26px;
  height: 5px;
}
.outline-scrim { display: none; }

@media (max-width: 820px) {
  .message-anchor-slot {
    position: fixed;
    inset: 52px 0 0;
    top: 52px;
    left: 0;
    z-index: 80;
    display: none;
    width: auto;
    min-width: 0;
    height: auto;
    padding: 0;
    align-items: stretch;
    justify-content: stretch;
    background: transparent;
    pointer-events: auto;
    transform: none;
  }
  .message-anchor-slot.mobile-open,
  .message-anchor-slot.expanded {
    display: block;
    width: auto;
    height: auto;
  }
  .outline-scrim {
    position: absolute;
    inset: 0;
    display: block;
    width: 100%;
    background: rgba(20, 22, 28, .28);
    backdrop-filter: blur(4px);
  }
  .message-anchor-rail,
  .message-anchor-slot.expanded .message-anchor-rail {
    position: absolute;
    inset: 0 0 0 auto;
    width: min(340px, 92vw);
    max-height: none;
    border: 0;
    border-radius: 24px 0 0 24px;
    background: rgba(250, 250, 252, .96);
    box-shadow: var(--shadow-floating);
    overflow: hidden;
  }
  .message-anchor-rail nav,
  .message-anchor-slot.expanded .message-anchor-rail nav {
    align-content: start;
    gap: 4px;
    padding: 16px 12px 24px;
    overflow-x: hidden;
  }
  .anchor-row {
    display: block;
    padding-left: 0;
  }
  .anchor-item,
  .message-anchor-slot.expanded .anchor-item {
    width: 100%;
    min-height: 48px;
    height: auto;
    display: grid;
    grid-template-columns: 18px minmax(0, 1fr);
    justify-items: start;
    gap: 12px;
    padding: 10px 4px;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
    text-align: left;
  }
  .anchor-bar,
  .message-anchor-slot.expanded .anchor-bar,
  .anchor-row.previewing .anchor-bar,
  .anchor-row.active .anchor-bar,
  .anchor-row.active.previewing .anchor-bar {
    width: 16px;
    height: 3px;
    margin-top: 8px;
    box-shadow: none;
  }
  .anchor-summary,
  .message-anchor-slot.expanded .anchor-summary {
    opacity: 1;
    transform: none;
    white-space: normal;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    font-size: 14px;
    text-shadow: none;
  }
  .anchor-row.active .anchor-item,
  .anchor-row.previewing .anchor-item {
    background: transparent;
  }
  .anchor-row.active .anchor-bar,
  .anchor-row.previewing .anchor-bar {
    background: var(--accent);
  }
  .anchor-row.active .anchor-summary,
  .anchor-row.previewing .anchor-summary {
    color: var(--accent);
  }
}

@media (prefers-reduced-motion: reduce) {
  .message-anchor-rail,
  .anchor-item,
  .anchor-bar,
  .anchor-summary {
    transition: none;
  }
}
</style>
