<script setup>
import { computed, ref, watch } from 'vue'
import { ArrowRight, Clock3, Target } from 'lucide-vue-next'
import { getCourseProgress, getPracticeStats, getStudyPlan } from '../../../api/learning'


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
defineEmits(['change-panel', 'prompt'])
const loading = ref(true)
const progress = ref(null)
const practice = ref(null)
const plan = ref(null)

const averageMastery = computed(() => {
  const points = progress.value?.knowledge_points || []
  return points.length ? Math.round(points.reduce((sum, point) => sum + Number(point.mastery), 0) / points.length) : 0
})
const nextSession = computed(() => plan.value?.sessions?.find(item => !['completed', 'evaluated'].includes(item.status)) || null)

async function load() {
  loading.value = true
  const [progressResponse, practiceResponse, planResponse] = await Promise.all([
    getCourseProgress(props.courseId),
    getPracticeStats(props.courseId),
    getStudyPlan(props.courseId)
  ])
  progress.value = progressResponse.code === 200 ? progressResponse.data : null
  practice.value = practiceResponse.code === 200 ? practiceResponse.data : null
  plan.value = planResponse.code === 200 ? planResponse.data : null
  loading.value = false
}

watch(() => [props.courseId, props.refreshKey], load, { immediate: true })
</script>

<template>
  <div class="overview-panel">
    <div v-if="loading" class="panel-state">正在汇总课程状态</div>
    <template v-else>
      <section class="metric-band">
        <div><span>掌握度</span><strong>{{ averageMastery }}</strong><small>/100</small></div>
        <div><span>计划完成</span><strong>{{ progress?.completion_rate || 0 }}</strong><small>%</small></div>
        <div><span>累计学习</span><strong>{{ progress?.actual_minutes || 0 }}</strong><small>分钟</small></div>
        <div><span>练习正确</span><strong>{{ practice?.accuracy || 0 }}</strong><small>%</small></div>
      </section>

      <section class="next-block">
        <div class="panel-heading"><Target :size="16" /><h3>下一目标</h3></div>
        <template v-if="nextSession">
          <span>{{ nextSession.scheduled_date }}</span>
          <strong>{{ nextSession.items?.[0]?.title || '课程学习单元' }}</strong>
          <p>{{ nextSession.adaptation_reason || '按照当前计划继续学习。' }}</p>
          <button type="button" @click="$emit('prompt', '今天学什么？')">在对话中开始 <ArrowRight :size="14" /></button>
        </template>
        <template v-else>
          <p>当前没有待完成单元。</p>
          <button type="button" @click="$emit('prompt', '生成入门诊断题')">建立学习计划 <ArrowRight :size="14" /></button>
        </template>
      </section>

      <section class="status-list">
        <button type="button" @click="$emit('change-panel', 'knowledge')">
          <span>薄弱知识点</span><strong>{{ progress?.weak_points?.length || 0 }} 个</strong><ArrowRight :size="14" />
        </button>
        <button type="button" @click="$emit('change-panel', 'practice')">
          <span>练习次数</span><strong>{{ practice?.attempts || 0 }} 次</strong><ArrowRight :size="14" />
        </button>
        <button type="button" @click="$emit('change-panel', 'plan')">
          <span>后续单元</span><strong>{{ plan?.sessions?.filter(item => item.status === 'planned').length || 0 }} 个</strong><ArrowRight :size="14" />
        </button>
      </section>

      <section class="course-rhythm">
        <div class="panel-heading"><Clock3 :size="16" /><h3>学习节奏</h3></div>
        <p>{{ progress?.course?.daily_minutes || 30 }} 分钟/天</p>
        <span>{{ progress?.course?.goal || '尚未设置课程目标' }}</span>
      </section>
    </template>
  </div>
</template>

<style scoped>
.overview-panel { display: grid; gap: 20px; }
.panel-state { min-height: 260px; display: grid; place-items: center; color: #7a847f; font-size: 12px; }
.metric-band { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border-block: 1px solid #dce2de; }
.metric-band > div { min-width: 0; padding: 12px 10px; border-right: 1px solid #e1e5e2; border-bottom: 1px solid #e1e5e2; }
.metric-band > div:nth-child(2n) { border-right: 0; }
.metric-band > div:nth-last-child(-n+2) { border-bottom: 0; }
.metric-band span { display: block; color: #78827d; font-size: 10px; }
.metric-band strong { display: inline-block; margin-top: 3px; color: #27342e; font-size: 21px; font-weight: 760; }
.metric-band small { margin-left: 2px; color: #8a938e; font-size: 10px; }
.panel-heading { display: flex; align-items: center; gap: 6px; color: #276b59; }
.panel-heading h3 { font-size: 13px; font-weight: 760; }
.next-block { display: grid; gap: 5px; padding-bottom: 17px; border-bottom: 1px solid #dfe4e1; }
.next-block > span { margin-top: 8px; color: #19705a; font-size: 10px; font-weight: 740; }
.next-block > strong { color: #2d3933; font-size: 14px; }
.next-block p { color: #707b75; font-size: 11px; line-height: 1.55; }
.next-block button { min-height: 34px; display: inline-flex; align-items: center; gap: 5px; justify-self: start; margin-top: 4px; padding: 0 10px; border-radius: 5px; color: #fff; background: #176b58; font-size: 10px; font-weight: 740; }
.status-list { display: grid; }
.status-list button { min-height: 43px; display: grid; grid-template-columns: minmax(0, 1fr) auto 18px; align-items: center; gap: 8px; border-bottom: 1px solid #e2e6e3; color: #6c7771; text-align: left; }
.status-list button:hover { color: #176b58; }
.status-list span { font-size: 11px; }
.status-list strong { color: #33403a; font-size: 11px; }
.course-rhythm { display: grid; gap: 5px; }
.course-rhythm p { margin-top: 7px; color: #34413a; font-size: 13px; font-weight: 720; }
.course-rhythm > span { color: #77817c; font-size: 11px; line-height: 1.55; }
</style>
