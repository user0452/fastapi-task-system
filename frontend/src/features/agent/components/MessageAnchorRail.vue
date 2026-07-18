<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { ListTree, X } from 'lucide-vue-next'
import { createMessageAnchors } from '../messageAnchors'


const props = defineProps({
  messages: { type: Array, default: () => [] },
  activeMessageId: { type: [Number, String], default: null },
  mobileOpen: { type: Boolean, default: false }
})
const emit = defineEmits(['jump', 'close-mobile'])
const itemElements = ref(new Map())
const anchors = computed(() => createMessageAnchors(props.messages))

function setItemElement(id, element) {
  if (element) itemElements.value.set(String(id), element)
  else itemElements.value.delete(String(id))
}

function jump(id) {
  emit('jump', id)
  if (props.mobileOpen) emit('close-mobile')
}

watch(() => props.activeMessageId, async id => {
  if (id == null) return
  await nextTick()
  const element = itemElements.value.get(String(id))
  if (typeof element?.scrollIntoView === 'function') element.scrollIntoView({ block: 'nearest' })
})
</script>

<template>
  <div class="message-anchor-slot" :class="{ 'mobile-open': mobileOpen }">
    <button
      v-if="mobileOpen"
      class="outline-scrim"
      type="button"
      aria-label="关闭本次对话目录"
      @click="$emit('close-mobile')"
    ></button>
    <aside class="message-anchor-rail" aria-label="本次对话目录">
      <header>
        <span><ListTree :size="16" /> 本次对话</span>
        <button type="button" title="关闭目录" aria-label="关闭本次对话目录" @click="$emit('close-mobile')"><X :size="18" /></button>
      </header>
      <nav aria-label="用户消息目录">
        <button
          v-for="anchor in anchors"
          :key="anchor.id"
          :ref="element => setItemElement(anchor.id, element)"
          type="button"
          class="anchor-item"
          :class="{ active: String(activeMessageId) === String(anchor.id) }"
          :aria-label="anchor.title"
          :title="anchor.title"
          :aria-current="String(activeMessageId) === String(anchor.id) ? 'location' : undefined"
          @click="jump(anchor.id)"
        >
          <span>{{ anchor.title }}</span>
          <i></i>
        </button>
      </nav>
    </aside>
  </div>
</template>

<style scoped>
.message-anchor-slot { position: relative; z-index: 10; min-width: 0; padding: 18px 0 18px 18px; background: var(--surface-primary); }
.message-anchor-rail { width: 236px; height: 100%; min-height: 0; display: flex; flex-direction: column; overflow: hidden; border: 1px solid rgba(0, 0, 0, .055); border-radius: 24px; background: rgba(246, 247, 250, .82); box-shadow: var(--shadow-small); backdrop-filter: blur(18px); }
.message-anchor-rail header { min-height: 58px; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; color: var(--text-tertiary); }
.message-anchor-rail header span { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; }
.message-anchor-rail header button { display: none; width: 40px; height: 40px; place-items: center; border-radius: 12px; }
.message-anchor-rail nav { min-height: 0; display: grid; align-content: start; gap: 1px; overflow-y: auto; padding: 2px 10px 14px; }
.anchor-item { min-height: 43px; display: grid; grid-template-columns: minmax(0, 1fr) 28px; align-items: center; gap: 10px; padding: 0 8px 0 10px; border-radius: 11px; color: var(--text-tertiary); text-align: left; transition: color var(--duration-fast) ease, background var(--duration-fast) ease; }
.anchor-item span { overflow: hidden; font-size: 13px; font-weight: 520; text-overflow: ellipsis; white-space: nowrap; }
.anchor-item i { width: 16px; height: 2px; justify-self: end; border-radius: 999px; background: rgba(0, 0, 0, .18); transition: width var(--duration-fast) var(--ease-out), background var(--duration-fast) ease; }
.anchor-item:hover { color: var(--text-primary); background: rgba(0, 0, 0, .035); }
.anchor-item:hover i { width: 22px; background: var(--text-secondary); }
.anchor-item.active { color: var(--accent); background: var(--accent-softer); }
.anchor-item.active i { width: 28px; height: 3px; background: var(--accent); }
.outline-scrim { display: none; }

@media (max-width: 1180px) and (min-width: 821px) {
  .message-anchor-slot { width: 70px; padding-left: 12px; }
  .message-anchor-rail { width: 52px; border-radius: 20px; }
  .message-anchor-rail header { display: none; }
  .message-anchor-rail nav { gap: 3px; padding: 14px 6px; }
  .anchor-item { min-height: 36px; display: grid; grid-template-columns: 1fr; padding: 0 6px; }
  .anchor-item span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
  .anchor-item i { justify-self: center; }
}

@media (max-width: 820px) {
  .message-anchor-slot { position: fixed; inset: 52px 0 0; z-index: 80; display: none; padding: 0; background: transparent; }
  .message-anchor-slot.mobile-open { display: block; }
  .outline-scrim { position: absolute; inset: 0; display: block; width: 100%; background: rgba(20, 22, 28, .28); backdrop-filter: blur(4px); }
  .message-anchor-rail { position: absolute; inset: 0 0 0 auto; width: min(340px, 92vw); border: 0; border-radius: 24px 0 0 24px; background: rgba(250, 250, 252, .96); box-shadow: var(--shadow-floating); }
  .message-anchor-rail header { min-height: 68px; padding-inline: 18px 12px; color: var(--text-secondary); }
  .message-anchor-rail header span { font-size: 14px; }
  .message-anchor-rail header button { display: grid; }
  .message-anchor-rail nav { padding: 4px 12px 24px; }
  .anchor-item { min-height: 48px; font-size: 14px; }
  .anchor-item span { font-size: 14px; }
}

@media (prefers-reduced-motion: reduce) {
  .anchor-item,
  .anchor-item i { transition: none; }
}
</style>
