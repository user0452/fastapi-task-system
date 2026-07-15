<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, BarChart3, CalendarClock, RefreshCw, TrendingDown, TrendingUp } from 'lucide-vue-next'
import { getCourseProgress } from '../../api/learning'
import { useCourseStore } from '../../stores/course'


const router = useRouter()
const courses = useCourseStore()
const progress = ref(null)
const loading = ref(true)
const error = ref('')

const averageMastery = computed(() => {
  const points = progress.value?.knowledge_points || []
  if (!points.length) return 0
  return Math.round(points.reduce((sum, point) => sum + Number(point.mastery), 0) / points.length)
})

function masteryClass(value) {
  const score = Number(value)
  if (score < 60) return 'low'
  if (score <= 80) return 'medium'
  return 'high'
}

function formatDate(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', weekday: 'short' }).format(new Date(value))
}

async function load() {
  if (!courses.current?.id) {
    progress.value = null
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  const response = await getCourseProgress(courses.current.id)
  loading.value = false
  if (response.code === 200) progress.value = response.data
  else error.value = response.message || '学习进度加载失败'
}

onMounted(async () => {
  await courses.ensureLoaded()
  await load()
})
watch(() => courses.current?.id, (next, previous) => {
  if (previous && next !== previous) load()
})
</script>

<template>
  <div class="progress-page">
    <header class="page-heading">
      <div>
        <span class="eyebrow">{{ courses.current?.name || '课程进度' }}</span>
        <h1>学习进度</h1>
        <p>掌握度由每次练习评估更新，并保留变化依据与计划调整原因。</p>
      </div>
      <button v-if="courses.current" class="icon-button" type="button" title="刷新" aria-label="刷新学习进度" @click="load">
        <RefreshCw :size="18" />
      </button>
    </header>

    <div v-if="loading" class="page-state">正在汇总学习进度</div>
    <div v-else-if="error" class="page-state error">{{ error }}</div>
    <section v-else-if="!courses.current" class="page-state empty">
      <BarChart3 :size="32" />
      <h2>先创建一门课程</h2>
      <button type="button" @click="router.push('/courses')">打开我的课程 <ArrowRight :size="16" /></button>
    </section>
    <section v-else-if="!progress?.knowledge_points?.length" class="page-state empty">
      <BarChart3 :size="32" />
      <h2>还没有掌握度数据</h2>
      <p>上传资料并完成入门诊断后，这里会显示每个知识点的掌握情况。</p>
      <button type="button" @click="router.push('/courses?tab=diagnostic')">前往入门诊断 <ArrowRight :size="16" /></button>
    </section>

    <template v-else>
      <section class="progress-summary" aria-label="学习进度概览">
        <div>
          <span>平均掌握度</span>
          <strong>{{ averageMastery }}</strong>
          <small>/ 100</small>
        </div>
        <div>
          <span>计划完成</span>
          <strong>{{ progress.completion_rate }}</strong>
          <small>%</small>
        </div>
        <div>
          <span>已完成单元</span>
          <strong>{{ progress.session_completed }}</strong>
          <small>/ {{ progress.session_total }}</small>
        </div>
        <div>
          <span>待加强知识点</span>
          <strong>{{ progress.weak_points?.length || 0 }}</strong>
          <small>个</small>
        </div>
      </section>

      <div class="progress-layout">
        <section class="mastery-section">
          <div class="section-heading">
            <div>
              <h2>知识点掌握度</h2>
              <p>低于 60 优先复习，60–80 继续巩固，高于 80 进入进阶。</p>
            </div>
          </div>
          <div class="mastery-list">
            <article v-for="point in progress.knowledge_points" :key="point.id" class="mastery-row">
              <div class="mastery-copy">
                <strong>{{ point.name }}</strong>
                <span>{{ point.description || '暂无知识点描述' }}</span>
              </div>
              <div class="mastery-meter">
                <div class="meter-track">
                  <i :class="masteryClass(point.mastery)" :style="{ width: `${Math.max(2, Number(point.mastery))}%` }"></i>
                </div>
                <strong :class="masteryClass(point.mastery)">{{ Number(point.mastery).toFixed(0) }}</strong>
              </div>
            </article>
          </div>
        </section>

        <aside class="progress-side">
          <section>
            <div class="side-heading"><CalendarClock :size="17" /><h2>接下来</h2></div>
            <div v-if="progress.upcoming_sessions?.length" class="upcoming-list">
              <article v-for="item in progress.upcoming_sessions" :key="item.id">
                <span>{{ formatDate(item.scheduled_date) }}</span>
                <strong>{{ item.items?.[0]?.title || '学习单元' }}</strong>
                <small>{{ item.estimated_minutes }} 分钟 · {{ item.items?.length || 0 }} 项</small>
                <p v-if="item.adaptation_reason">{{ item.adaptation_reason }}</p>
              </article>
            </div>
            <p v-else class="side-empty">没有待执行的后续单元。</p>
          </section>

          <section>
            <div class="side-heading"><TrendingUp :size="17" /><h2>最近变化</h2></div>
            <div v-if="progress.recent_changes?.length" class="change-list">
              <article v-for="change in progress.recent_changes.slice(0, 5)" :key="change.id">
                <component :is="Number(change.after_value) >= Number(change.before_value) ? TrendingUp : TrendingDown" :size="15" />
                <div>
                  <strong>{{ change.knowledge_point_name }}</strong>
                  <p>{{ change.reason }}</p>
                </div>
                <span>{{ Number(change.before_value).toFixed(0) }} → {{ Number(change.after_value).toFixed(0) }}</span>
              </article>
            </div>
            <p v-else class="side-empty">完成练习后会记录变化依据。</p>
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.progress-page { max-width: 1180px; margin: 0 auto; }
.page-heading { display: flex; justify-content: space-between; gap: 18px; margin-bottom: 22px; }
.eyebrow { color: #17705b; font-size: 12px; font-weight: 750; }
.page-heading h1 { margin-top: 4px; font-size: 28px; font-weight: 720; }
.page-heading p { margin-top: 7px; color: #69736e; font-size: 13px; }
.icon-button { width: 36px; height: 36px; display: grid; place-items: center; border: 1px solid #d5dcd7; border-radius: 6px; color: #5d6963; background: #ffffff; }
.icon-button:hover { color: #14634f; border-color: #9ebcaf; }
.page-state { min-height: 360px; display: flex; align-items: center; justify-content: center; color: #74807a; border-block: 1px solid #dce2de; font-size: 12px; }
.page-state.empty { flex-direction: column; gap: 10px; text-align: center; }
.page-state.empty svg { color: #23735f; }
.page-state.empty h2 { color: #26322c; font-size: 18px; font-weight: 750; }
.page-state.empty p { max-width: 460px; font-size: 12px; }
.page-state.empty button { min-height: 37px; display: inline-flex; align-items: center; gap: 7px; padding: 0 14px; border-radius: 6px; color: #ffffff; background: #176b58; font-size: 12px; font-weight: 750; }
.progress-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 22px; border-block: 1px solid #d9e0dc; background: #ffffff; }
.progress-summary > div { padding: 15px 18px; border-right: 1px solid #e0e5e2; }
.progress-summary > div:last-child { border-right: 0; }
.progress-summary span { display: block; color: #6c7771; font-size: 10px; }
.progress-summary strong { display: inline-block; margin-top: 3px; color: #26322c; font-size: 24px; font-weight: 760; }
.progress-summary small { margin-left: 3px; color: #79837e; font-size: 10px; }
.progress-layout { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(280px, .8fr); gap: 26px; }
.section-heading { padding-bottom: 13px; border-bottom: 1px solid #dce2de; }
.section-heading h2,
.side-heading h2 { font-size: 15px; font-weight: 750; }
.section-heading p { margin-top: 3px; color: #6f7a74; font-size: 10px; }
.mastery-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(180px, 38%); align-items: center; gap: 18px; padding: 15px 0; border-bottom: 1px solid #e1e6e3; }
.mastery-copy { min-width: 0; display: grid; gap: 3px; }
.mastery-copy strong { font-size: 12px; }
.mastery-copy span { overflow: hidden; color: #747f79; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.mastery-meter { display: grid; grid-template-columns: 1fr 32px; align-items: center; gap: 10px; }
.meter-track { height: 7px; overflow: hidden; border-radius: 4px; background: #e5e9e6; }
.meter-track i { display: block; height: 100%; border-radius: inherit; }
.meter-track i.low { background: #c8584f; }
.meter-track i.medium { background: #d29327; }
.meter-track i.high { background: #27805f; }
.mastery-meter strong { font-size: 12px; text-align: right; }
.mastery-meter strong.low { color: #a64038; }
.mastery-meter strong.medium { color: #976517; }
.mastery-meter strong.high { color: #176746; }
.progress-side { display: grid; align-content: start; gap: 28px; }
.side-heading { display: flex; align-items: center; gap: 7px; padding-bottom: 10px; border-bottom: 1px solid #dce2de; color: #2d5f50; }
.upcoming-list article { padding: 12px 0; border-bottom: 1px solid #e1e6e3; }
.upcoming-list span { color: #17705b; font-size: 9px; font-weight: 750; }
.upcoming-list strong { display: block; margin-top: 3px; font-size: 11px; }
.upcoming-list small { display: block; margin-top: 2px; color: #78827d; font-size: 9px; }
.upcoming-list p { margin-top: 6px; padding: 7px 8px; color: #725c30; background: #fff5dd; font-size: 9px; line-height: 1.45; }
.change-list article { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; gap: 7px; padding: 11px 0; border-bottom: 1px solid #e1e6e3; }
.change-list svg { color: #417260; margin-top: 2px; }
.change-list strong { display: block; font-size: 10px; }
.change-list p { margin-top: 2px; color: #78827d; font-size: 9px; line-height: 1.4; }
.change-list > article > span { color: #4f5c56; font-size: 9px; font-weight: 750; white-space: nowrap; }
.side-empty { padding: 18px 0; color: #7a847f; font-size: 10px; }
@media (max-width: 900px) {
  .progress-layout { grid-template-columns: 1fr; }
  .progress-side { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 650px) {
  .progress-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .progress-summary > div:nth-child(2) { border-right: 0; }
  .progress-summary > div:nth-child(-n+2) { border-bottom: 1px solid #e0e5e2; }
  .mastery-row { grid-template-columns: 1fr; gap: 8px; }
  .progress-side { grid-template-columns: 1fr; }
}
</style>
