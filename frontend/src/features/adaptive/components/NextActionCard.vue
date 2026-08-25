<script setup>
import { ArrowRight, Lightbulb } from 'lucide-vue-next'

defineProps({
  entry: { type: Object, required: true },
  actionLabel: { type: Function, required: true }
})

defineEmits(['start'])
</script>

<template>
  <section class="next-action-card">
    <div class="next-copy">
      <span class="kicker"><Lightbulb :size="14" /> 今天建议</span>
      <p class="course-name">{{ entry.course.name }}</p>
      <h2>{{ entry.next_action?.objective_title || '先添加课程资料' }}</h2>
      <p class="reason">{{ entry.next_action?.reason || '上传一份教材或讲义后，我们会帮你找到合适的起点。' }}</p>
      <button type="button" @click="$emit('start')">
        {{ entry.next_action ? '开始学习' : '添加资料' }} <ArrowRight :size="17" />
      </button>
    </div>
    <div class="next-meta">
      <span>{{ actionLabel(entry.next_action) }}</span>
      <strong>{{ entry.next_action?.expected_minutes || entry.course.daily_minutes || 25 }}</strong>
      <small>预计分钟</small>
      <em>{{ entry.next_action ? '完成后会更新下一步' : '先准备课程内容' }}</em>
    </div>
  </section>
</template>

<style scoped>
.next-action-card { display: grid; grid-template-columns: minmax(0, 1fr) 190px; gap: 32px; margin-top: 42px; padding: clamp(26px, 5vw, 46px); border: 1px solid var(--border-strong); border-radius: 22px; background: var(--surface-primary); box-shadow: var(--shadow-medium); }
.kicker { display: inline-flex; align-items: center; gap: 6px; color: var(--accent-deep); font-size: 11px; font-weight: 700; letter-spacing: .08em; }
.course-name { margin-top: 22px; color: var(--text-tertiary); font-size: 12px; }
h2 { max-width: 680px; margin-top: 7px; font-size: clamp(25px, 4vw, 40px); letter-spacing: -.04em; }
.reason { max-width: 640px; margin-top: 13px; font-size: 14px; }
button { min-height: 44px; display: inline-flex; align-items: center; gap: 7px; margin-top: 26px; padding: 0 16px; border-radius: 10px; color: var(--text-inverse); background: var(--accent); font-size: 13px; font-weight: 700; box-shadow: var(--shadow-brand); }
button:hover { background: var(--accent-hover); }
.next-meta { align-self: end; display: grid; gap: 4px; padding-left: 22px; border-left: 1px solid var(--border-subtle); }
.next-meta span { color: var(--accent-deep); font-size: 11px; font-weight: 700; }.next-meta strong { margin-top: 8px; font-size: 42px; letter-spacing: -.05em; }.next-meta small, .next-meta em { color: var(--text-tertiary); font-size: 11px; font-style: normal; }.next-meta em { margin-top: 18px; padding-top: 12px; border-top: 1px solid var(--border-subtle); line-height: 1.5; }
@media (max-width: 650px) { .next-action-card { grid-template-columns: 1fr; gap: 24px; padding: 24px 19px; }.next-meta { padding: 16px 0 0; border-top: 1px solid var(--border-subtle); border-left: 0; }.next-meta strong { margin-top: 2px; } button { width: 100%; justify-content: center; } }
</style>
