<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  CalendarCheck2,
  CheckCircle2,
  MessageSquareText,
  Route,
  RotateCw
} from 'lucide-vue-next'
import { getTodayOverview } from '../../api/learning'
import { useCourseStore } from '../../stores/course'


const router = useRouter()
const courses = useCourseStore()
const loading = ref(true)
const rows = ref([])
const overviewError = ref('')
const summary = ref({ course_count: 0, total_minutes: 0, total_items: 0, completed: 0, with_session: 0 })

const now = new Date()
const todayLabel = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(now)
const greeting = now.getHours() < 6 ? '夜深了' : now.getHours() < 12 ? '早上好' : now.getHours() < 18 ? '下午好' : '晚上好'
const totalMinutes = computed(() => Number(summary.value.total_minutes || 0))
const totalItems = computed(() => Number(summary.value.total_items || 0))
const completed = computed(() => Number(summary.value.completed || 0))
const loadError = computed(() => overviewError.value || courses.error)
const primaryRow = computed(() => (
  rows.value.find(row => row.session && !['completed', 'evaluated'].includes(row.session.status))
  || rows.value.find(row => row.session)
  || rows.value[0]
  || null
))
const primaryTask = computed(() => primaryRow.value?.session?.items?.[0]?.title || '继续推进你的长期学习目标')
const primaryStage = computed(() => primaryRow.value?.course?.roadmap_summary?.current_stage_name || '持续学习')
const primaryProgress = computed(() => Math.round(
  primaryRow.value?.course?.roadmap_summary?.overall_progress
  ?? primaryRow.value?.course?.roadmap_summary?.current_stage_progress
  ?? 0
))

async function load() {
  loading.value = true
  rows.value = []
  overviewError.value = ''
  try {
    await courses.ensureLoaded()
    if (courses.error) return
    const response = await getTodayOverview()
    if (response.code === 200) {
      rows.value = response.data?.items || []
      summary.value = response.data?.summary || {
        course_count: rows.value.length,
        total_minutes: 0,
        total_items: 0,
        completed: 0,
        with_session: 0
      }
    } else {
      overviewError.value = response.message || '今日总览加载失败'
    }
  } finally {
    loading.value = false
  }
}

function openCourse(row, prompt = '', panel = '') {
  if (!row?.course?.id) return
  const query = prompt ? { prompt } : {}
  if (panel) query.panel = panel
  router.push({ path: `/learn/${row.course.id}`, query })
}

onMounted(load)
</script>

<template>
  <div class="global-today">
    <header class="today-topline">
      <div><CalendarCheck2 :size="17" /><span>{{ todayLabel }}</span></div>
      <button type="button" title="刷新今日总览" aria-label="刷新今日总览" @click="load"><RotateCw :size="17" /> 刷新</button>
    </header>

    <div v-if="loading" class="today-state">正在汇总所有课程</div>
    <div v-else-if="loadError" class="today-empty today-error">
      <CalendarCheck2 :size="34" />
      <h2>课程暂时未加载</h2>
      <p>{{ loadError }}</p>
      <button type="button" @click="load">重新加载</button>
    </div>
    <div v-else-if="!rows.length" class="today-empty">
      <span class="empty-orb"><CalendarCheck2 :size="30" /></span>
      <h2>先创建一门课程</h2>
      <p>课程助手会把目标、路线和每天的下一步组织在这里。</p>
    </div>
    <template v-else>
      <section class="today-hero">
        <div class="hero-copy">
          <span>{{ greeting }}，{{ primaryRow.course.name }}</span>
          <h1>{{ primaryTask }}</h1>
          <p>{{ primaryRow.course.goal || `当前处于“${primaryStage}”阶段，按今天的节奏继续即可。` }}</p>
          <div class="hero-actions">
            <button type="button" class="hero-primary" @click="openCourse(primaryRow, '', 'today')">
              开始今日学习 <ArrowRight :size="17" />
            </button>
            <button type="button" class="hero-secondary" @click="openCourse(primaryRow, '', 'plan')">
              <Route :size="17" /> 查看学习路线
            </button>
          </div>
        </div>
        <div class="hero-progress" :aria-label="`${primaryRow.course.name} 总进度 ${primaryProgress}%`">
          <span>当前阶段</span>
          <strong>{{ primaryStage }}</strong>
          <div><i :style="{ width: `${primaryProgress}%` }"></i></div>
          <small>总进度 {{ primaryProgress }}%</small>
        </div>
      </section>

      <section class="continue-section">
        <header class="section-heading">
          <div><span>下一步</span><h2>继续学习</h2></div>
          <span>{{ primaryRow.session?.estimated_minutes || primaryRow.course.daily_minutes }} 分钟</span>
        </header>
        <article class="continue-card">
          <span class="continue-glyph">{{ primaryRow.course.name.slice(0, 1) }}</span>
          <div class="continue-copy">
            <span>{{ primaryStage }}</span>
            <h3>{{ primaryRow.course.name }}</h3>
            <p>{{ primaryTask }}</p>
          </div>
          <div class="continue-meta">
            <strong>{{ primaryProgress }}%</strong>
            <span>长期路线总进度</span>
          </div>
          <button type="button" title="进入课程" aria-label="进入课程" @click="openCourse(primaryRow)"><ArrowRight :size="20" /></button>
        </article>
      </section>

      <section class="today-plan-section">
        <header class="section-heading">
          <div><span>按课程排列</span><h2>今日计划</h2></div>
          <span>{{ rows.filter(row => row.session).length }} 门有任务</span>
        </header>
        <div class="course-day-list">
          <article v-for="row in rows" :key="row.course.id" :class="row.session?.status || 'empty'">
            <span class="timeline-dot"></span>
            <div class="day-time">
              <strong>{{ row.session?.estimated_minutes || row.course.daily_minutes }}</strong>
              <span>分钟</span>
            </div>
            <div class="day-course-copy">
              <span>{{ row.course.name }}</span>
              <strong>{{ row.session?.items?.[0]?.title || '暂无今日单元' }}</strong>
              <p>{{ row.session ? `${row.session.items?.length || 0} 项学习内容` : (row.course.goal || '进入课程继续学习') }}</p>
            </div>
            <CheckCircle2 v-if="['completed', 'evaluated'].includes(row.session?.status)" class="done-icon" :size="21" />
            <div v-else class="day-actions">
              <button type="button" title="开始今日学习" aria-label="开始今日学习" @click="openCourse(row, '', 'today')"><ArrowRight :size="17" /></button>
              <button v-if="row.session" type="button" title="在对话中开始" aria-label="在对话中开始" @click="openCourse(row, '今天学什么？')"><MessageSquareText :size="17" /></button>
            </div>
          </article>
        </div>
      </section>

      <section class="learning-status">
        <header class="section-heading"><div><span>真实汇总</span><h2>学习状态</h2></div></header>
        <div class="status-metrics">
          <div><span>课程</span><strong>{{ rows.length }}</strong><small>门</small></div>
          <div><span>预计学习</span><strong>{{ totalMinutes }}</strong><small>分钟</small></div>
          <div><span>学习项目</span><strong>{{ totalItems }}</strong><small>项</small></div>
          <div><span>今日完成</span><strong>{{ completed }}</strong><small>/ {{ rows.length }}</small></div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.global-today { width: min(1180px, 100%); min-height: 100dvh; margin: 0 auto; padding: 26px clamp(20px, 5vw, 70px) 80px; }
.today-topline { min-height: 42px; display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 18px; }
.today-topline > div,
.today-topline button { display: inline-flex; align-items: center; gap: 7px; color: var(--text-secondary); font-size: 13px; }
.today-topline button { min-height: 38px; padding: 0 12px; border-radius: 12px; }
.today-topline button:hover { color: var(--accent); background: var(--accent-soft); }
.today-state,
.today-empty { min-height: 560px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 11px; color: var(--text-secondary); text-align: center; }
.today-state { font-size: 14px; }
.today-empty h2 { font-size: 28px; font-weight: 620; }
.today-empty p { max-width: 460px; font-size: 15px; }
.empty-orb { width: 72px; height: 72px; display: grid; place-items: center; margin-bottom: 8px; border-radius: 26px; color: #fff; background: var(--gradient-brand); box-shadow: 0 18px 46px rgba(79, 124, 255, .24); }
.today-error > svg { color: var(--danger); }
.today-error button { min-height: 42px; margin-top: 7px; padding: 0 16px; border-radius: 13px; color: #fff; background: var(--accent); font-size: 14px; font-weight: 600; }
.today-hero { position: relative; min-height: 390px; display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(240px, .7fr); align-items: end; gap: 44px; overflow: hidden; padding: clamp(34px, 5vw, 62px); border: 1px solid rgba(255, 255, 255, .62); border-radius: 32px; background: var(--gradient-soft-page); box-shadow: var(--shadow-medium); }
.today-hero::before { content: ''; position: absolute; width: 340px; height: 340px; right: -80px; top: -130px; border-radius: 50%; background: rgba(109, 93, 252, .11); filter: blur(1px); }
.hero-copy,
.hero-progress { position: relative; z-index: 1; }
.hero-copy > span { color: var(--accent); font-size: 14px; font-weight: 600; }
.hero-copy h1 { max-width: 760px; margin-top: 10px; font-size: clamp(42px, 5vw, 62px); font-weight: 670; line-height: 1.03; letter-spacing: -.055em; }
.hero-copy p { max-width: 650px; margin-top: 20px; color: var(--text-secondary); font-size: 16px; line-height: 1.72; }
.hero-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 30px; }
.hero-actions button { min-height: 48px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 0 18px; border-radius: 14px; font-size: 14px; font-weight: 600; }
.hero-primary { color: #fff; background: var(--gradient-brand); box-shadow: 0 10px 28px rgba(79, 124, 255, .25); }
.hero-secondary { color: var(--text-primary); border: 1px solid var(--border-subtle); background: rgba(255, 255, 255, .72); }
.hero-progress { align-self: end; display: grid; gap: 7px; padding: 22px; border: 1px solid rgba(255, 255, 255, .68); border-radius: 22px; background: rgba(255, 255, 255, .7); box-shadow: var(--shadow-small); backdrop-filter: blur(16px); }
.hero-progress > span,
.hero-progress small { color: var(--text-tertiary); font-size: 12px; }
.hero-progress strong { overflow: hidden; font-size: 17px; font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.hero-progress > div { height: 7px; overflow: hidden; margin-top: 8px; border-radius: 999px; background: rgba(52, 120, 246, .12); }
.hero-progress i { display: block; height: 100%; border-radius: inherit; background: var(--gradient-blue-cyan); }
.continue-section,
.today-plan-section,
.learning-status { margin-top: 64px; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
.section-heading > div { display: grid; gap: 4px; }
.section-heading div > span { color: var(--accent); font-size: 12px; font-weight: 600; }
.section-heading h2 { font-size: 25px; font-weight: 630; }
.section-heading > span { color: var(--text-tertiary); font-size: 13px; }
.continue-card { min-height: 156px; display: grid; grid-template-columns: 58px minmax(0, 1fr) auto 48px; align-items: center; gap: 20px; padding: 26px 28px; border: 1px solid var(--border-subtle); border-radius: 24px; background: var(--surface-elevated); box-shadow: var(--shadow-small); }
.continue-glyph { width: 58px; height: 58px; display: grid; place-items: center; border-radius: 20px; color: #46658d; background: #e4ebf5; font-size: 19px; font-weight: 650; }
.continue-copy { min-width: 0; display: grid; gap: 4px; }
.continue-copy > span { color: var(--accent); font-size: 12px; font-weight: 600; }
.continue-copy h3 { overflow: hidden; font-size: 19px; font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.continue-copy p { overflow: hidden; color: var(--text-secondary); font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.continue-meta { display: grid; justify-items: end; }
.continue-meta strong { font-size: 26px; font-weight: 620; }
.continue-meta span { color: var(--text-tertiary); font-size: 12px; }
.continue-card > button { width: 46px; height: 46px; display: grid; place-items: center; border-radius: 14px; color: #fff; background: var(--accent); }
.course-day-list { position: relative; display: grid; }
.course-day-list::before { content: ''; position: absolute; left: 8px; top: 28px; bottom: 28px; width: 1px; background: var(--border-strong); }
.course-day-list article { position: relative; min-height: 100px; display: grid; grid-template-columns: 18px 64px minmax(0, 1fr) auto; align-items: center; gap: 18px; padding: 14px 2px; border-bottom: 1px solid var(--border-subtle); }
.timeline-dot { position: relative; z-index: 1; width: 10px; height: 10px; border: 3px solid var(--page-bg); border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 1px rgba(52, 120, 246, .3); }
.day-time { display: grid; }
.day-time strong { font-size: 18px; font-weight: 620; }
.day-time span { color: var(--text-tertiary); font-size: 11px; }
.day-course-copy { min-width: 0; display: grid; gap: 3px; }
.day-course-copy > span { color: var(--accent); font-size: 12px; font-weight: 600; }
.day-course-copy strong,
.day-course-copy p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.day-course-copy strong { color: var(--text-primary); font-size: 15px; font-weight: 600; }
.day-course-copy p { color: var(--text-secondary); font-size: 13px; }
.day-actions { display: flex; gap: 6px; }
.day-actions button { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 13px; color: var(--text-secondary); }
.day-actions button:hover { color: var(--accent); background: var(--accent-soft); }
.done-icon { color: var(--success); }
.course-day-list article.evaluated,
.course-day-list article.completed { opacity: .66; }
.status-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-block: 1px solid var(--border-subtle); background: rgba(255, 255, 255, .5); }
.status-metrics > div { padding: 22px 20px; border-right: 1px solid var(--border-subtle); }
.status-metrics > div:last-child { border-right: 0; }
.status-metrics span { display: block; color: var(--text-tertiary); font-size: 13px; }
.status-metrics strong { display: inline-block; margin-top: 4px; font-size: 30px; font-weight: 620; }
.status-metrics small { margin-left: 4px; color: var(--text-tertiary); font-size: 12px; }

@media (max-width: 900px) {
  .today-hero { min-height: auto; grid-template-columns: 1fr; align-items: start; }
  .hero-progress { width: min(360px, 100%); }
}

@media (max-width: 700px) {
  .global-today { min-height: calc(100dvh - 52px); padding: 18px 14px 54px; }
  .today-hero { gap: 28px; padding: 30px 22px; border-radius: 26px; }
  .hero-copy h1 { font-size: 38px; }
  .hero-actions { display: grid; }
  .continue-section,
  .today-plan-section,
  .learning-status { margin-top: 46px; }
  .continue-card { grid-template-columns: 48px minmax(0, 1fr) 44px; gap: 13px; padding: 20px 18px; }
  .continue-glyph { width: 48px; height: 48px; border-radius: 16px; }
  .continue-meta { grid-column: 2; justify-items: start; }
  .continue-card > button { grid-column: 3; grid-row: 1 / span 2; }
  .course-day-list article { grid-template-columns: 16px 52px minmax(0, 1fr) auto; gap: 10px; }
  .day-actions { grid-column: 3 / -1; justify-self: start; }
  .status-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .status-metrics > div:nth-child(2) { border-right: 0; }
  .status-metrics > div:nth-child(-n+2) { border-bottom: 1px solid var(--border-subtle); }
}
</style>
