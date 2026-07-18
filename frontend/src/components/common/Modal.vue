<script setup>
import { X } from 'lucide-vue-next'


defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '' },
  size: { type: String, default: 'md' }
})

const emit = defineEmits(['close'])
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="modal-overlay" @click.self="emit('close')">
      <div class="modal" :class="`modal-${size}`">
        <div class="modal-header">
          <h2>{{ title }}</h2>
          <button class="modal-close" type="button" title="关闭" aria-label="关闭" @click="emit('close')"><X :size="19" /></button>
        </div>
        <div class="modal-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="modal-footer">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 20px; background: rgba(20, 22, 28, .3); backdrop-filter: blur(9px); }
.modal { width: min(560px, 100%); max-height: calc(100dvh - 40px); overflow: hidden; border: 1px solid rgba(255, 255, 255, .62); border-radius: 26px; background: var(--surface-elevated); box-shadow: var(--shadow-floating); backdrop-filter: blur(28px) saturate(1.15); }
.modal-sm { max-width: 420px; }
.modal-lg { max-width: 760px; }
.modal-header { min-height: 78px; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 18px 22px; border-bottom: 1px solid var(--border-subtle); }
.modal-header h2 { font-size: 21px; font-weight: 630; }
.modal-close { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 12px; color: var(--text-secondary); }
.modal-close:hover { color: var(--accent); background: var(--accent-soft); }
.modal-body { max-height: calc(100dvh - 200px); overflow-y: auto; padding: 22px; }
.modal-footer { display: flex; justify-content: flex-end; gap: 9px; padding: 16px 22px 20px; border-top: 1px solid var(--border-subtle); }
</style>
