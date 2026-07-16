<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, CalendarCheck2, CheckCircle2, Clock3, MessageSquareText } from 'lucide-vue-next'
import { getTodayLearning } from '../../api/learning'
import { useCourseStore } from '../../stores/course'


const router = useRouter()
const courses = useCourseStore()
const loading = ref(true)
const rows = ref([])

const todayLabel = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
const totalMinutes = computed(() => rows.value.reduce((sum, row) => sum + Number(row.session?.estimated_minutes || 0), 0))
const totalItems = computed(() => rows.value.reduce((sum, row) => sum + Number(row.session?.items?.length || 0), 0))
const completed = computed(() => rows.value.filter(row => ['completed', 'evaluated'].includes(row.session?.status)).length)

async function load() {
  loading.value = true
  rows.value = []
  try {
    await courses.ensureLoaded()
    if (courses.error) return
    const results = await Promise.all(courses.courses.map(async course => {
      const response = await getTodayLearning(course.id)
      return { course, session: response.code === 200 ? response.data : null }
    }))
    rows.value = results
  } finally {
    loading.value = false
  }
}

function openCourse(row, prompt = '', panel = '') {
  const query = prompt ? { prompt } : {}
  if (panel) query.panel = panel
  router.push({ path: `/learn/${row.course.id}`, query })
}

onMounted(load)
</script>

<template>
  <div class="global-today">
    <header class="today-heading">
      <div>
        <span>{{ todayLabel }}</span>
        <h1>今日总览</h1>
        <p>跨课程安排</p>
      </div>
      <button type="button" title="刷新今日总览" aria-label="刷新今日总览" @click="load"><CalendarCheck2 :size="19" /></button>
    </header>

    <div v-if="loading" class="today-state">正在汇总所有课程</div>
    <div v-else-if="courses.error" class="today-empty today-error">
      <CalendarCheck2 :size="31" />
      <h2>课程暂时未加载</h2>
      <p>{{ courses.error }}</p>
      <button type="button" @click="load">重新加载</button>
    </div>
    <div v-else-if="!rows.length" class="today-empty">
      <CalendarCheck2 :size="31" />
      <h2>先创建一门课程</h2>
      <p>课程助手会出现在左侧课程栏。</p>
    </div>
    <template v-else>
      <section class="today-metrics">
        <div><span>课程</span><strong>{{ rows.length }}</strong><small>门</small></div>
        <div><span>预计学习</span><strong>{{ totalMinutes }}</strong><small>分钟</small></div>
        <div><span>学习项目</span><strong>{{ totalItems }}</strong><small>项</small></div>
        <div><span>今日完成</span><strong>{{ completed }}</strong><small>/ {{ rows.length }}</small></div>
      </section>

      <section class="course-day-list">
        <header><h2>课程安排</h2><span>{{ rows.filter(row => row.session).length }} 门有任务</span></header>
        <article v-for="row in rows" :key="row.course.id" :class="row.session?.status || 'empty'">
          <span class="day-course-icon">{{ row.course.name.slice(0, 1) }}</span>
          <div class="day-course-copy">
            <span>{{ row.session ? row.session.scheduled_date : '暂无今日单元' }}</span>
            <strong>{{ row.course.name }}</strong>
            <p v-if="row.session">{{ row.session.items?.[0]?.title || '课程学习' }}</p>
            <p v-else>{{ row.course.goal || '进入课程助手继续学习' }}</p>
          </div>
          <div v-if="row.session" class="day-meta">
            <span><Clock3 :size="13" />{{ row.session.estimated_minutes }} 分钟</span>
            <span>{{ row.session.items?.length || 0 }} 项</span>
          </div>
          <CheckCircle2 v-if="['completed', 'evaluated'].includes(row.session?.status)" class="done-icon" :size="19" />
          <div v-else class="day-actions">
            <button type="button" title="开始今日学习" aria-label="开始今日学习" @click="openCourse(row, '', 'today')"><ArrowRight :size="16" /></button>
            <button v-if="row.session" type="button" title="在对话中开始" aria-label="在对话中开始" @click="openCourse(row, '今天学什么？')"><MessageSquareText :size="16" /></button>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.global-today { width: min(1040px, 100%); min-height: 100dvh; margin: 0 auto; padding: 38px clamp(20px, 5vw, 64px) 56px; }
.today-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding-bottom: 22px; border-bottom: 1px solid #dce2de; }
.today-heading span { color: #19705a; font-size: 11px; font-weight: 750; }
.today-heading h1 { margin-top: 4px; font-size: 26px; font-weight: 730; }
.today-heading p { margin-top: 5px; color: #7b8580; font-size: 12px; line-height: 1.55; }
.today-heading button { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 6px; color: #5f6b65; border: 1px solid #d3dad6; background: #fff; }
.today-heading button:hover { color: #176b58; border-color: #a7bcb2; }
.today-state,
.today-empty { min-height: 420px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: #7a847f; text-align: center; }
.today-state { font-size: 12px; }
.today-empty svg { color: #24715e; }
.today-empty h2 { color: #34413a; font-size: 15px; font-weight: 720; }
.today-empty p { font-size: 11px; }
.today-error button { min-height: 34px; margin-top: 7px; padding: 0 12px; border-radius: 999px; color: #ffffff; background: #176b58; font-size: 11px; font-weight: 740; }
.today-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 24px 0 32px; border-block: 1px solid #dce2de; background: #fff; }
.today-metrics > div { padding: 14px 16px; border-right: 1px solid #e0e5e2; }
.today-metrics > div:last-child { border-right: 0; }
.today-metrics span { display: block; color: #7a847f; font-size: 10px; }
.today-metrics strong { display: inline-block; margin-top: 3px; color: #2d3933; font-size: 22px; }
.today-metrics small { margin-left: 3px; color: #89928d; font-size: 10px; }
.course-day-list > header { display: flex; align-items: baseline; justify-content: space-between; gap: 15px; padding-bottom: 10px; border-bottom: 1px solid #dce2de; }
.course-day-list h2 { font-size: 13px; font-weight: 730; }
.course-day-list > header span { color: #808984; font-size: 10px; }
.course-day-list article { min-height: 86px; display: grid; grid-template-columns: 38px minmax(0, 1fr) auto auto; align-items: center; gap: 12px; padding: 12px 2px; border-bottom: 1px solid #e0e5e2; }
.day-course-icon { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 7px; color: #155e4c; background: #dcece4; font-size: 11px; font-weight: 800; }
.day-course-copy { min-width: 0; display: grid; gap: 2px; }
.day-course-copy > span { color: #19705a; font-size: 9px; font-weight: 740; }
.day-course-copy strong,
.day-course-copy p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.day-course-copy strong { color: #33403a; font-size: 13px; }
.day-course-copy p { color: #7a847f; font-size: 10px; }
.day-meta { display: flex; align-items: center; gap: 12px; color: #77817c; font-size: 10px; }
.day-meta span { display: inline-flex; align-items: center; gap: 4px; }
.day-actions { display: flex; gap: 4px; }
.day-actions button { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 6px; color: #5f6b65; }
.day-actions button:hover { color: #176b58; background: #e8efeb; }
.done-icon { color: #26805e; }
.course-day-list article.evaluated,
.course-day-list article.completed { opacity: .72; }
@media (max-width: 700px) {
  .global-today { min-height: calc(100dvh - 52px); padding: 24px 14px 40px; }
  .today-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .today-metrics > div:nth-child(2) { border-right: 0; }
  .today-metrics > div:nth-child(-n+2) { border-bottom: 1px solid #e0e5e2; }
  .course-day-list article { grid-template-columns: 36px minmax(0, 1fr) auto; }
  .day-meta { grid-column: 2; justify-self: start; }
  .day-actions,
  .done-icon { grid-column: 3; grid-row: 1 / span 2; }
}
</style>
