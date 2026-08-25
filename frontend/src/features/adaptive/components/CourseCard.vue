<script setup>
import { ArrowRight } from 'lucide-vue-next'

defineProps({
  entry: { type: Object, required: true },
  actionLabel: { type: Function, required: true }
})

defineEmits(['open'])
</script>

<template>
  <article class="course-card">
    <div class="course-mark">{{ entry.course.name.slice(0, 1) }}</div>
    <div class="course-copy">
      <strong>{{ entry.course.name }}</strong>
      <span v-if="entry.next_action">{{ actionLabel(entry.next_action) }} · {{ entry.next_action.objective_title || '继续学习' }}</span>
      <span v-else-if="entry.error" class="error">{{ entry.error }}</span>
      <span v-else>添加资料后开始学习</span>
    </div>
    <button type="button" :aria-label="`进入${entry.course.name}`" @click="$emit('open')"><ArrowRight :size="18" /></button>
  </article>
</template>

<style scoped>
.course-card { display: grid; grid-template-columns: 38px minmax(0, 1fr) 38px; align-items: center; gap: 13px; min-height: 72px; padding: 10px 3px; border-bottom: 1px solid var(--border-subtle); }
.course-mark { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 11px; color: var(--tone-jade-fg); background: var(--tone-jade-bg); font-size: 13px; font-weight: 700; }.course-copy { min-width: 0; display: grid; gap: 4px; }.course-copy strong, .course-copy span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.course-copy strong { font-size: 14px; }.course-copy span { color: var(--text-tertiary); font-size: 12px; }.course-copy .error { color: var(--danger); }
button { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 9px; color: var(--text-secondary); } button:hover { color: var(--accent-deep); background: var(--accent-softer); }
</style>
