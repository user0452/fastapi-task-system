<script setup>
import { computed, ref, watch } from 'vue'
import { ArrowRight, Clock3, Route, Target, TrendingDown, TrendingUp } from 'lucide-vue-next'
import {
  getCourseProgress,
  getLearningRoadmap,
  getPracticeStats,
  getStudyPlan,
  getTodayLearning
} from '../../../api/learning'


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
defineEmits(['change-panel', 'prompt'])
const loading = ref(true)
const progress = ref(null)
const practice = ref(null)
const plan = ref(null)
const roadmap = ref(null)
const today = ref(null)

const averageMastery = computed(() => {
  const points = progress.value?.knowledge_points || []
  return points.length ? Math.round(points.reduce((sum, point) => sum + Number(point.mastery), 0) / points.length) : 0
})
const nextSession = computed(() => plan.value?.sessions?.find(item => !['completed', 'evaluated'].includes(item.status)) || null)
const roadmapProgress = computed(() => {
  const stages = roadmap.value?.stages || []
  return stages.length
    ? Math.round(stages.reduce((sum, stage) => sum + Number(stage.progress || 0), 0) / stages.length)
    : 0
})
const currentStage = computed(() => (
  roadmap.value?.stages?.find(stage => stage.status === 'active')
  || roadmap.value?.stages?.find(stage => stage.status !== 'completed')
  || null
))
const latestAdjustment = computed(() => roadmap.value?.adjustments?.[0] || null)
const masteryDistribution = computed(() => {
  const points = progress.value?.knowledge_points || []
  const total = points.length
  const bands = [
    { key: 'weak', label: '待加强', count: points.filter(point => Number(point.mastery) < 60).length },
    { key: 'steady', label: '巩固中', count: points.filter(point => Number(point.mastery) >= 60 && Number(point.mastery) <= 80).length },
    { key: 'strong', label: '已掌握', count: points.filter(point => Number(point.mastery) > 80).length }
  ]
  return bands.map(band => ({
    ...band,
    percentage: total ? Math.round(band.count / total * 100) : 0
  }))
})
const todayCompleted = computed(() => ['completed', 'evaluated'].includes(today.value?.status))

async function load() {
  loading.value = true
  const [progressResponse, practiceResponse, planResponse, roadmapResponse, todayResponse] = await Promise.all([
    getCourseProgress(props.courseId),
    getPracticeStats(props.courseId),
    getStudyPlan(props.courseId),
    getLearningRoadmap(props.courseId),
    getTodayLearning(props.courseId)
  ])
  progress.value = progressResponse.code === 200 ? progressResponse.data : null
  practice.value = practiceResponse.code === 200 ? practiceResponse.data : null
  plan.value = planResponse.code === 200 ? planResponse.data : null
  roadmap.value = roadmapResponse.code === 200 ? roadmapResponse.data : null
  today.value = todayResponse.code === 200 ? todayResponse.data : null
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
        <div><span>路线进度</span><strong>{{ roadmapProgress }}</strong><small>%</small></div>
        <div><span>今日学习</span><strong>{{ today ? (todayCompleted ? '已完成' : '待完成') : '无任务' }}</strong></div>
        <div><span>完成单元</span><strong>{{ progress?.session_completed || 0 }}</strong><small>/{{ progress?.session_total || 0 }}</small></div>
      </section>

      <section class="route-snapshot">
        <div class="panel-heading"><Route :size="16" /><h3>当前学习阶段</h3></div>
        <template v-if="currentStage">
          <div class="route-title"><strong>{{ currentStage.name }}</strong><span>{{ Math.round(currentStage.progress || 0) }}%</span></div>
          <span class="route-progress" role="progressbar" :aria-valuenow="Math.round(currentStage.progress || 0)" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${currentStage.progress || 0}%` }"></i></span>
          <p>{{ currentStage.goal }}</p>
        </template>
        <p v-else>{{ roadmap?.status === 'failed' ? '学习路线生成失败，可在计划面板重试。' : roadmap?.status === 'generating' ? '正在根据课程目标生成路线。' : '完成课程设置或诊断后会显示当前阶段。' }}</p>
        <div v-if="latestAdjustment" class="adjustment-note">
          <span>最近调整</span><p>{{ latestAdjustment.reason }}</p>
        </div>
      </section>

      <section class="mastery-snapshot">
        <div class="panel-heading"><Target :size="16" /><h3>掌握度分布</h3></div>
        <div v-if="progress?.knowledge_points?.length" class="distribution-bar" aria-label="知识点掌握度分布">
          <i v-for="band in masteryDistribution" :key="band.key" :class="band.key" :style="{ width: `${band.percentage}%` }"></i>
        </div>
        <div v-if="progress?.knowledge_points?.length" class="distribution-legend">
          <span v-for="band in masteryDistribution" :key="band.key" :class="band.key"><i></i>{{ band.label }} {{ band.count }}</span>
        </div>
        <p v-else>完成诊断后会显示真实知识点分布。</p>
      </section>

      <section class="change-snapshot">
        <div class="panel-heading"><TrendingUp :size="16" /><h3>最近评估变化</h3></div>
        <div v-if="progress?.recent_changes?.length" class="change-list">
          <article v-for="change in progress.recent_changes.slice(0, 3)" :key="change.id">
            <component :is="Number(change.after_value) >= Number(change.before_value) ? TrendingUp : TrendingDown" :size="14" />
            <div><strong>{{ change.knowledge_point_name }}</strong><span>{{ change.reason }}</span></div>
            <b>{{ Number(change.before_value).toFixed(0) }} → {{ Number(change.after_value).toFixed(0) }}</b>
          </article>
        </div>
        <p v-else>完成练习评估后会显示真实掌握度变化。</p>
      </section>

      <section class="next-block">
        <div class="panel-heading"><Target :size="16" /><h3>下一目标</h3></div>
        <template v-if="nextSession">
          <span>{{ nextSession.scheduled_date }}</span>
          <strong>{{ nextSession.items?.[0]?.title || '课程学习单元' }}</strong>
          <p>{{ nextSession.adaptation_reason || '按照当前计划继续学习。' }}</p>
          <button type="button" @click="$emit('change-panel', 'today')">进入今日学习 <ArrowRight :size="14" /></button>
        </template>
        <template v-else>
          <p>当前没有待完成单元。</p>
          <button type="button" @click="$emit('change-panel', 'diagnostic')">开始入门诊断 <ArrowRight :size="14" /></button>
        </template>
      </section>

      <section class="status-list">
        <button type="button" @click="$emit('change-panel', 'knowledge')">
          <span>薄弱知识点</span><strong>{{ progress?.weak_points?.length || 0 }} 个</strong><ArrowRight :size="14" />
        </button>
        <button type="button" @click="$emit('change-panel', 'practice')">
          <span>练习与错题</span><strong>{{ practice?.attempts || 0 }} 次 · {{ practice?.wrong || 0 }} 错题</strong><ArrowRight :size="14" />
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
.route-snapshot,
.mastery-snapshot,
.change-snapshot { display: grid; gap: 8px; padding-bottom: 16px; border-bottom: 1px solid #dfe4e1; }
.route-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 3px; }
.route-title strong { color: #2f3d36; font-size: 12px; }
.route-title span { color: #176b58; font-size: 10px; font-weight: 780; }
.route-progress { height: 6px; overflow: hidden; border-radius: 999px; background: #e1e8e4; }
.route-progress i { display: block; height: 100%; border-radius: inherit; background: #2c7d65; transition: width .2s ease; }
.route-snapshot > p,
.mastery-snapshot > p,
.change-snapshot > p { color: #77817c; font-size: 10px; line-height: 1.55; }
.adjustment-note { margin-top: 2px; padding: 7px 8px; border-left: 2px solid #c4a257; background: #faf6ea; }
.adjustment-note span { color: #8a6a30; font-size: 8px; font-weight: 800; }
.adjustment-note p { margin-top: 2px; color: #675b43; font-size: 9px; line-height: 1.45; }
.distribution-bar { height: 9px; display: flex; overflow: hidden; border-radius: 999px; background: #e5e9e6; }
.distribution-bar i { min-width: 0; height: 100%; }
.distribution-bar .weak,
.distribution-legend .weak i { background: #c85a50; }
.distribution-bar .steady,
.distribution-legend .steady i { background: #c99534; }
.distribution-bar .strong,
.distribution-legend .strong i { background: #2d8163; }
.distribution-legend { display: flex; flex-wrap: wrap; gap: 7px 12px; }
.distribution-legend span { display: inline-flex; align-items: center; gap: 4px; color: #707b75; font-size: 9px; }
.distribution-legend span i { width: 6px; height: 6px; border-radius: 50%; }
.change-list { display: grid; }
.change-list article { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; align-items: start; gap: 5px; padding: 7px 0; border-bottom: 1px solid #e5e9e6; }
.change-list article:last-child { border-bottom: 0; }
.change-list svg { color: #39705e; margin-top: 1px; }
.change-list div { min-width: 0; display: grid; gap: 1px; }
.change-list strong { overflow: hidden; color: #3a4741; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.change-list span { color: #818c86; font-size: 8px; }
.change-list b { color: #4e5c55; font-size: 8px; white-space: nowrap; }
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
@media (prefers-reduced-motion: reduce) { .route-progress i { transition: none; } }
</style>
