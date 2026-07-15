<script setup>
import { ShieldAlert } from 'lucide-vue-next'


defineProps({ confirmation: { type: Object, required: true }, busy: { type: Boolean, default: false } })
defineEmits(['decide'])
</script>

<template>
  <div class="confirmation-bar">
    <ShieldAlert :size="19" />
    <div>
      <strong>需要二次确认</strong>
      <p>{{ confirmation.summary }}</p>
    </div>
    <div class="confirmation-actions">
      <button type="button" :disabled="busy" @click="$emit('decide', false)">取消</button>
      <button class="danger" type="button" :disabled="busy" @click="$emit('decide', true)">确认执行</button>
    </div>
  </div>
</template>

<style scoped>
.confirmation-bar { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 9px; margin-top: 10px; padding: 10px 11px; border: 1px solid #e6c97f; border-radius: 6px; color: #71511d; background: #fff8e6; }
.confirmation-bar > svg { color: #a66d13; }
.confirmation-bar strong { font-size: 10px; }
.confirmation-bar p { margin-top: 2px; color: #80642e; font-size: 9px; }
.confirmation-actions { display: flex; gap: 5px; }
.confirmation-actions button { min-height: 30px; padding: 0 9px; border: 1px solid #d5bd83; border-radius: 5px; color: #6e5525; background: #ffffff; font-size: 9px; font-weight: 750; }
.confirmation-actions button.danger { color: #ffffff; border-color: #aa453d; background: #aa453d; }
.confirmation-actions button:disabled { opacity: .5; }
@media (max-width: 600px) {
  .confirmation-bar { grid-template-columns: auto 1fr; }
  .confirmation-actions { grid-column: 1 / -1; }
  .confirmation-actions button { flex: 1; }
}
</style>
