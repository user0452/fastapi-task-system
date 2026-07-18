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
        <Plus :size="15" /> 在对话中生成练习
      </button>

      <section class="trend-section">
        <header><BarChart3 :size="15" /><strong>得分趋势</strong><span>{{ stats?.trend?.length || 0 }} 次</span></header>
        <div v-if="stats?.trend?.length" class="trend-chart">
          <span
            v-for="item in stats.trend"
            :key="item.id"
            :style="{ height: `${Math.max(5, Number(item.score) / maxTrendScore * 100)}%` }"
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
.practice-panel-view { display: grid; gap: 18px; }
.panel-state { min-height: 260px; display: grid; place-items: center; color: #7a847f; font-size: 12px; }
.practice-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-block: 1px solid #dce2de; }
.practice-metrics > div { min-width: 0; padding: 11px 7px; border-right: 1px solid #e0e5e2; }
.practice-metrics > div:last-child { border-right: 0; }
.practice-metrics span { display: block; color: #7a847f; font-size: 9px; }
.practice-metrics strong { display: block; margin-top: 3px; color: #303d36; font-size: 18px; }
.generate-button { min-height: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 5px; border-radius: 5px; color: #fff; background: #176b58; font-size: 10px; font-weight: 750; }
.trend-section,
.distribution-section { display: grid; gap: 9px; }
.trend-section header,
.distribution-section header { display: flex; align-items: center; gap: 6px; padding-bottom: 8px; color: #2a6b59; border-bottom: 1px solid #dfe4e1; }
.trend-section header strong,
.distribution-section header strong { color: #35413b; font-size: 12px; }
.trend-section header span { margin-left: auto; color: #838c87; font-size: 10px; }
.trend-chart { height: 110px; display: flex; align-items: end; gap: 5px; padding: 9px 5px 0; border-bottom: 1px solid #cfd6d2; background: #f7f9f7; }
.trend-chart span { min-width: 5px; flex: 1; border-radius: 3px 3px 0 0; background: #4a8875; transition: height 180ms ease; }
.trend-chart span:hover { background: #176b58; }
.trend-section > p,
.distribution-section > p { padding: 20px 0; color: #838c87; font-size: 10px; text-align: center; }
.distribution-section article { display: grid; grid-template-columns: minmax(0, 1fr) 42px; gap: 4px 8px; padding: 8px 0; border-bottom: 1px solid #e3e7e4; }
.distribution-section article > div:first-child { display: flex; justify-content: space-between; gap: 8px; }
.distribution-section article span,
.distribution-section article strong { font-size: 10px; }
.distribution-section article strong { color: #176b58; }
.score-track { height: 5px; overflow: hidden; align-self: center; border-radius: 3px; background: #e5e9e6; }
.score-track i { display: block; height: 100%; background: #3d816d; }
.distribution-section article span { font-size: 10px; }
.distribution-section small { color: #818a85; font-size: 9px; text-align: right; }
.answer-breakdown { display: flex; justify-content: space-between; gap: 8px; padding: 10px 0; border-block: 1px solid #dfe4e1; font-size: 10px; }
.answer-breakdown span { color: #6d7872; }
.answer-breakdown strong { color: #247457; }
.answer-breakdown b { color: #a84c44; }
</style>
