<script setup>
import { computed, ref, watch } from 'vue'
import { BarChart3, Plus } from 'lucide-vue-next'
import { getPracticeStats } from '../../../api/learning'


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
defineEmits(['prompt'])
const loading = ref(true)
const stats = ref(null)

const maxTrendScore = computed(() => Math.max(100, ...(stats.value?.trend || []).map(item => Number(item.score))))

async function load() {
  loading.value = true
  const response = await getPracticeStats(props.courseId)
  stats.value = response.code === 200 ? response.data : null
  loading.value = false
}

watch(() => [props.courseId, props.refreshKey], load, { immediate: true })
</script>

<template>
  <div class="practice-panel-view">
    <div v-if="loading" class="panel-state">正在汇总做题记录</div>
    <template v-else>
      <section class="practice-metrics">
        <div><span>练习次数</span><strong>{{ stats?.attempts || 0 }}</strong></div>
        <div><span>平均得分</span><strong>{{ stats?.average_score || 0 }}</strong></div>
        <div><span>正确率</span><strong>{{ stats?.accuracy || 0 }}%</strong></div>
      </section>

      <button class="generate-button" type="button" @click="$emit('prompt', '根据当前薄弱知识点给我出 3 道题')">
        <Plus :size="16" /> 在对话中生成练习
      </button>

      <section class="trend-section">
        <header><BarChart3 :size="16" /><strong>得分趋势</strong><span>{{ stats?.trend?.length || 0 }} 次</span></header>
        <div v-if="stats?.trend?.length" class="trend-chart">
          <span
            v-for="item in stats.trend"
            :key="item.id"
            :style="{ height: `${Math.max(8, Number(item.score) / maxTrendScore * 100)}%` }"
            :title="`${item.title}：${item.score} 分`"
          ></span>
        </div>
        <p v-else>完成诊断或练习后显示趋势。</p>
      </section>

      <section class="distribution-section">
        <header><strong>题型表现</strong></header>
        <article v-for="item in stats?.type_distribution || []" :key="item.question_type">
          <div><span>{{ item.question_type === 'short_answer' ? '简答题' : item.question_type }}</span><strong>{{ item.average_score }} 分</strong></div>
          <div class="score-track"><i :style="{ width: `${Math.max(2, Number(item.average_score))}%` }"></i></div>
          <small>{{ item.total }} 道</small>
        </article>
        <p v-if="!stats?.type_distribution?.length">还没有题型数据。</p>
      </section>

      <section class="answer-breakdown">
        <span>已答 {{ stats?.answered || 0 }}</span>
        <strong>通过 {{ stats?.passed || 0 }}</strong>
        <b>错题 {{ stats?.wrong || 0 }}</b>
      </section>
    </template>
  </div>
</template>

<style scoped>
.practice-panel-view { display: grid; gap: 14px; }
.panel-state { min-height: 220px; display: grid; place-items: center; color: var(--text-secondary); font-size: 14px; }
.practice-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-medium);
  background: var(--surface-primary);
  box-shadow: var(--shadow-small);
}
.practice-metrics > div { min-width: 0; padding: 14px 12px; border-right: 1px solid var(--border-subtle); }
.practice-metrics > div:last-child { border-right: 0; }
.practice-metrics span { display: block; color: var(--text-tertiary); font-size: 12px; }
.practice-metrics strong {
  display: block;
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 22px;
  font-weight: var(--weight-semibold);
}
.generate-button {
  min-height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-radius: var(--radius-small);
  color: var(--text-inverse);
  background: var(--gradient-brand);
  font-size: 13px;
  font-weight: 600;
  box-shadow: var(--shadow-brand);
}
.trend-section,
.distribution-section { display: grid; gap: 10px; }
.trend-section header,
.distribution-section header { display: flex; align-items: center; gap: 8px; padding-bottom: 10px; color: var(--accent); border-bottom: 1px solid var(--border-subtle); }
.trend-section header strong,
.distribution-section header strong { color: var(--text-primary); font-size: 15px; font-weight: 620; }
.trend-section header span { margin-left: auto; color: var(--text-tertiary); font-size: 12px; }
.trend-chart { height: 140px; display: flex; align-items: end; gap: 6px; padding: 14px 10px 0; border: 1px solid var(--border-subtle); border-radius: 16px; background: linear-gradient(180deg, rgba(52, 120, 246, .05), rgba(255, 255, 255, .9)); }
.trend-chart span { min-width: 8px; flex: 1; border-radius: 8px 8px 0 0; background: var(--gradient-blue-cyan); transition: height var(--duration-normal) ease, filter var(--duration-fast) ease; }
.trend-chart span:hover { filter: brightness(1.05); }
.trend-section > p,
.distribution-section > p { padding: 22px 0; color: var(--text-tertiary); font-size: 13px; text-align: center; }
.distribution-section article { display: grid; grid-template-columns: minmax(0, 1fr) 48px; gap: 6px 10px; padding: 12px 0; border-bottom: 1px solid var(--border-subtle); }
.distribution-section article > div:first-child { display: flex; justify-content: space-between; gap: 8px; }
.distribution-section article span,
.distribution-section article strong { font-size: 13px; }
.distribution-section article strong { color: var(--accent); }
.score-track { height: 6px; overflow: hidden; align-self: center; border-radius: 999px; background: rgba(52, 120, 246, .1); }
.score-track i { display: block; height: 100%; border-radius: inherit; background: var(--gradient-blue-cyan); }
.distribution-section small { color: var(--text-tertiary); font-size: 12px; text-align: right; }
.answer-breakdown { display: flex; justify-content: space-between; gap: 10px; padding: 14px 16px; border: 1px solid var(--border-subtle); border-radius: 14px; background: rgba(255, 255, 255, .72); font-size: 13px; }
.answer-breakdown span { color: var(--text-secondary); }
.answer-breakdown strong { color: var(--success); }
.answer-breakdown b { color: var(--danger); }
@media (prefers-reduced-motion: reduce) {
  .trend-chart span { transition: none; }
}
</style>
