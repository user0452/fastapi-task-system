<script setup>
import { computed, ref, watch } from 'vue'
import { ArrowRight, Clock3, Route, Target, TrendingDown, TrendingUp } from 'lucide-vue-next'
import { getCourseWorkspaceOverview } from '../../../api/learning'
import { calculateRoadmapProgress } from '../roadmapProgress'


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
const roadmapProgress = computed(() => calculateRoadmapProgress(roadmap.value))
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
  const response = await getCourseWorkspaceOverview(props.courseId)
  if (response.code === 200) {
    progress.value = response.data?.progress || null
    practice.value = response.data?.practice || null
    plan.value = response.data?.plan || null
    roadmap.value = response.data?.roadmap || null
    today.value = response.data?.today || null
  } else {
    progress.value = null
    practice.value = null
    plan.value = null
    roadmap.value = null
    today.value = null
  }
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
            <div>
              <strong>{{ change.knowledge_point_name }}</strong>
              <span>{{ change.reason }}</span>
              <small v-if="change.formula || change.weight">{{ change.formula || `weight ${change.weight}` }}</small>
            </div>
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
.overview-panel { display: grid; gap: 28px; }
.panel-state { min-height: 260px; display: grid; place-items: center; color: var(--text-secondary); font-size: 14px; }
.metric-band { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border: 1px solid var(--border-subtle); border-radius: 20px; overflow: hidden; background: rgba(255, 255, 255, .72); box-shadow: var(--shadow-small); }
.metric-band > div { min-width: 0; padding: 18px 16px; border-right: 1px solid var(--border-subtle); border-bottom: 1px solid var(--border-subtle); }
.metric-band > div:nth-child(2n) { border-right: 0; }
.metric-band > div:nth-last-child(-n+2) { border-bottom: 0; }
.metric-band span { display: block; color: var(--text-tertiary); font-size: 12px; }
.metric-band strong { display: inline-block; margin-top: 4px; color: var(--text-primary); font-size: 26px; font-weight: 620; }
.metric-band small { margin-left: 2px; color: var(--text-tertiary); font-size: 11px; }
.panel-heading { display: flex; align-items: center; gap: 8px; color: var(--accent); }
.panel-heading h3 { font-size: 17px; font-weight: 620; }
.route-snapshot,
.mastery-snapshot,
.change-snapshot { display: grid; gap: 11px; padding-bottom: 22px; border-bottom: 1px solid var(--border-subtle); }
.route-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 3px; }
.route-title strong { color: var(--text-primary); font-size: 15px; }
.route-title span { color: var(--accent); font-size: 13px; font-weight: 620; }
.route-progress { height: 7px; overflow: hidden; border-radius: 999px; background: rgba(52, 120, 246, .1); }
.route-progress i { display: block; height: 100%; border-radius: inherit; background: var(--gradient-blue-cyan); transition: width .2s ease; }
.route-snapshot > p,
.mastery-snapshot > p,
.change-snapshot > p { color: var(--text-secondary); font-size: 13px; line-height: 1.68; }
.adjustment-note { margin-top: 2px; padding: 12px 14px; border-radius: 14px; background: rgba(169, 101, 0, .08); }
.adjustment-note span { color: var(--warning); font-size: 11px; font-weight: 600; }
.adjustment-note p { margin-top: 3px; color: var(--text-secondary); font-size: 12px; line-height: 1.55; }
.distribution-bar { height: 10px; display: flex; overflow: hidden; border-radius: 999px; background: var(--surface-tertiary); }
.distribution-bar i { min-width: 0; height: 100%; }
.distribution-bar .weak,
.distribution-legend .weak i { background: #d96b66; }
.distribution-bar .steady,
.distribution-legend .steady i { background: #d0a33e; }
.distribution-bar .strong,
.distribution-legend .strong i { background: #3d9a5a; }
.distribution-legend { display: flex; flex-wrap: wrap; gap: 8px 14px; }
.distribution-legend span { display: inline-flex; align-items: center; gap: 6px; color: var(--text-secondary); font-size: 12px; }
.distribution-legend span i { width: 8px; height: 8px; border-radius: 50%; }
.change-list { display: grid; }
.change-list article { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; align-items: start; gap: 8px; padding: 12px 0; border-bottom: 1px solid var(--border-subtle); }
.change-list article:last-child { border-bottom: 0; }
.change-list svg { color: var(--accent); margin-top: 2px; }
.change-list div { min-width: 0; display: grid; gap: 2px; }
.change-list strong { overflow: hidden; color: var(--text-primary); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.change-list span,
.change-list b { color: var(--text-secondary); font-size: 11px; }
.change-list small { color: var(--text-tertiary); font-size: 10px; }
.next-block { display: grid; gap: 8px; padding: 18px; border: 1px solid rgba(52, 120, 246, .12); border-radius: 18px; background: linear-gradient(135deg, rgba(52, 120, 246, .08), rgba(109, 93, 252, .05)); }
.next-block > span { color: var(--accent); font-size: 12px; font-weight: 600; }
.next-block > strong { color: var(--text-primary); font-size: 17px; }
.next-block p { color: var(--text-secondary); font-size: 13px; line-height: 1.68; }
.next-block button { min-height: 40px; display: inline-flex; align-items: center; gap: 5px; justify-self: start; margin-top: 2px; padding: 0 14px; border-radius: 12px; color: #fff; background: var(--gradient-brand); font-size: 13px; font-weight: 600; box-shadow: 0 8px 18px rgba(79, 124, 255, .2); }
.status-list { display: grid; gap: 4px; }
.status-list button { min-height: 52px; display: grid; grid-template-columns: minmax(0, 1fr) auto 18px; align-items: center; gap: 8px; padding: 0 10px; border-radius: 14px; color: var(--text-secondary); text-align: left; }
.status-list button:hover { color: var(--accent); background: var(--accent-soft); }
.status-list span,
.status-list strong { font-size: 13px; }
.status-list strong { color: var(--text-primary); }
.course-rhythm { display: grid; gap: 6px; }
.course-rhythm p { color: var(--text-primary); font-size: 15px; font-weight: 600; }
.course-rhythm > span { color: var(--text-secondary); font-size: 13px; line-height: 1.68; }
@media (prefers-reduced-motion: reduce) { .route-progress i { transition: none; } }
</style>
