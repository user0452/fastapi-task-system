<script setup>
import { ref, watch } from 'vue'
import { RotateCcw, XCircle } from 'lucide-vue-next'
import { getWrongAnswers } from '../../../api/learning'


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
defineEmits(['prompt'])
const loading = ref(true)
const items = ref([])

async function load() {
  loading.value = true
  const response = await getWrongAnswers(props.courseId)
  items.value = response.code === 200 ? response.data?.items || [] : []
  loading.value = false
}

watch(() => [props.courseId, props.refreshKey], load, { immediate: true })
</script>

<template>
  <div class="wrong-panel">
    <div v-if="loading" class="panel-state">正在读取错题记录</div>
    <div v-else-if="!items.length" class="panel-empty">
      <XCircle :size="28" /><strong>还没有错题</strong><p>完成练习后，低于 60 分的题目会保留在这里。</p>
    </div>
    <section v-else class="wrong-list">
      <article v-for="item in items" :key="item.id">
        <header>
          <span>{{ item.knowledge_point_name || '课程知识点' }}</span>
          <strong>{{ Number(item.score).toFixed(0) }} 分</strong>
        </header>
        <h3>{{ item.question }}</h3>
        <div><span>你的答案</span><p>{{ item.user_answer }}</p></div>
        <div><span>批改反馈</span><p>{{ item.feedback }}</p></div>
        <button type="button" @click="$emit('prompt', `针对“${item.knowledge_point_name || item.question}”再给我出 3 道题`)" title="针对性重做">
          <RotateCcw :size="14" /> 针对性重做
        </button>
      </article>
    </section>
  </div>
</template>

<style scoped>
.wrong-panel { display: grid; gap: 12px; }
.panel-state,
.panel-empty { min-height: 280px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--text-secondary); text-align: center; }
.panel-state { font-size: 14px; }
.panel-empty svg { color: var(--danger); }
.panel-empty strong { color: var(--text-primary); font-size: 18px; font-weight: 620; }
.panel-empty p { max-width: 280px; color: var(--text-secondary); font-size: 13px; line-height: 1.65; }
.wrong-list { display: grid; gap: 10px; }
.wrong-list article { display: grid; gap: 10px; padding: 16px; border: 1px solid var(--border-subtle); border-radius: 18px; background: rgba(255, 255, 255, .82); box-shadow: var(--shadow-small); }
.wrong-list header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.wrong-list header span { color: var(--accent); font-size: 12px; font-weight: 600; }
.wrong-list header strong { color: var(--danger); font-size: 13px; font-weight: 620; }
.wrong-list h3 { color: var(--text-primary); font-size: 14px; font-weight: 600; line-height: 1.6; }
.wrong-list article > div { display: grid; gap: 4px; padding: 10px 12px; border-radius: 12px; background: var(--surface-secondary); }
.wrong-list article > div > span { color: var(--text-tertiary); font-size: 11px; }
.wrong-list article > div > p { color: var(--text-secondary); font-size: 13px; line-height: 1.6; }
.wrong-list button { min-height: 38px; display: inline-flex; align-items: center; gap: 6px; justify-self: end; padding: 0 12px; border: 1px solid rgba(52, 120, 246, .22); border-radius: 11px; color: var(--accent); background: #fff; font-size: 12px; font-weight: 600; }
.wrong-list button:hover { background: var(--accent-soft); }
</style>
