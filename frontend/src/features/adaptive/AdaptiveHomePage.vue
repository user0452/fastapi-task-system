<script setup>
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, CircleAlert, RefreshCw, Sparkles, Target } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { getAdaptiveOverview } from '../../api/adaptive'
import { useCourseStore } from '../../stores/course'


const router = useRouter()
const courses = useCourseStore()
const loading = ref(true)
const error = ref('')
const courseRows = ref([])

const actionLabels = {
  explain: '基础讲解',
  practice: '场景练习',
  verify_mastery: '掌握度验证',
  review: '间隔复习',
  misconception_repair: '错误模式修复',
  repair_prerequisite: '前置目标修复',
  transfer: '迁移练习'
}

const primary = computed(() => (
  courseRows.value.find(item => item.course.id === courses.current?.id && item.next_action)
  || courseRows.value.find(item => item.next_action)
  || courseRows.value[0]
  || null
))

function actionLabel(action) {
  return actionLabels[action?.action_type] || action?.action_type || '等待学习证据'
}

function openCourse(courseId, view = 'learn') {
  router.push({ path: `/learn/${courseId}`, query: { view } })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    await courses.ensureLoaded()
    if (courses.error) throw new Error(courses.error)
    const results = await Promise.all(courses.courses.map(async course => {
      try {
        const response = await getAdaptiveOverview(course.id)
        if (response.code !== 200) throw new Error(response.message || '读取失败')
        return { course, ...response.data, next_action: response.data?.next_action || null }
      } catch (requestError) {
        return { course, next_action: null, error: requestError.message || 'Adaptive Tutor 读取失败' }
      }
    }))
    courseRows.value = results
  } catch (requestError) {
    error.value = requestError.message || '课程读取失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="adaptive-home">
    <header class="home-header">
      <div>
        <span class="home-kicker"><Sparkles :size="14" /> EVIDENCE-BACKED LEARNING</span>
        <h1>今天，下一步学什么？</h1>
        <p>每门课程都从真实学习证据出发，持续选择当前最值得完成的一个动作。</p>
      </div>
      <button type="button" class="home-refresh" :disabled="loading" aria-label="刷新下一动作" @click="load">
        <RefreshCw :size="16" /> 刷新
      </button>
    </header>

    <div v-if="loading" class="home-state" role="status">正在读取每门课程的 Student Model</div>
    <div v-else-if="error" class="home-state home-error" role="alert">
      <CircleAlert :size="24" /><strong>{{ error }}</strong><button type="button" @click="load">重新读取</button>
    </div>
    <div v-else-if="!courseRows.length" class="home-state">
      <Target :size="30" /><h2>先创建一门课程</h2><p>从左侧新建课程，然后上传资料与题库。</p>
    </div>
    <main v-else>
      <section v-if="primary" class="home-next-action">
        <div class="next-copy">
          <span class="home-kicker">NEXT BEST LEARNING ACTION</span>
          <p class="next-course">{{ primary.course.name }}</p>
          <h2>{{ primary.next_action ? (primary.next_action.objective_title || '当前学习目标') : '建立课程学习目标' }}</h2>
          <p class="next-reason">{{ primary.next_action?.reason || '上传课程资料并建立可评估的 Learning Objective。' }}</p>
          <button type="button" class="home-primary" @click="openCourse(primary.course.id)">
            {{ primary.next_action ? '开始下一动作' : '去建立 Curriculum' }} <ArrowRight :size="17" />
          </button>
        </div>
        <div class="next-meta">
          <span>{{ actionLabel(primary.next_action) }}</span>
          <strong>{{ primary.next_action?.expected_minutes || primary.course.daily_minutes || 25 }}</strong>
          <small>预计分钟</small>
          <em>{{ primary.curriculum?.objective_count || 0 }} 个 Learning Objective</em>
        </div>
      </section>

      <section class="home-courses" aria-labelledby="course-list-title">
        <header><div><span class="home-kicker">YOUR COURSES</span><h2 id="course-list-title">课程队列</h2></div><span>{{ courseRows.length }} 门课程</span></header>
        <div class="course-list">
          <article v-for="item in courseRows" :key="item.course.id" class="course-row">
            <div class="course-row-mark">{{ item.course.name.slice(0, 1) }}</div>
            <div class="course-row-copy">
              <strong>{{ item.course.name }}</strong>
              <span v-if="item.next_action">{{ actionLabel(item.next_action) }} · {{ item.next_action.objective_title || '待选目标' }}</span>
              <span v-else-if="item.error" class="row-error">{{ item.error }}</span>
              <span v-else>等待课程资料或初始诊断</span>
            </div>
            <button type="button" class="course-row-action" :aria-label="`进入${item.course.name}`" @click="openCourse(item.course.id)"><ArrowRight :size="18" /></button>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.adaptive-home { width: min(1120px, 100%); min-height: 100dvh; margin: 0 auto; padding: 48px clamp(20px, 5vw, 70px) 80px; color: var(--text-primary); }
.home-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 22px; padding-bottom: 29px; border-bottom: 1px solid var(--border-subtle); }
.home-kicker { display: inline-flex; align-items: center; gap: 6px; color: var(--accent-deep); font-size: 10px; font-weight: 750; letter-spacing: .12em; }
.home-header h1 { margin-top: 10px; font-size: clamp(31px, 5vw, 56px); font-weight: 680; letter-spacing: -.055em; line-height: 1.05; }
.home-header p { max-width: 600px; margin-top: 12px; color: var(--text-secondary); font-size: 14px; line-height: 1.7; }
.home-refresh { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 0 11px; color: var(--text-secondary); border-radius: 8px; font-size: 11px; }
.home-refresh:hover:not(:disabled) { color: var(--accent-deep); background: var(--accent-softer); }.home-refresh:disabled { opacity: .5; }
.home-state { min-height: 420px; display: grid; place-content: center; justify-items: center; gap: 10px; color: var(--text-secondary); text-align: center; }.home-state h2 { color: var(--text-primary); font-size: 23px; }.home-state p { font-size: 13px; }.home-error { color: var(--danger); }.home-state button { min-height: 35px; padding: 0 12px; color: var(--accent-deep); border: 1px solid var(--border-accent); border-radius: 8px; background: var(--accent-softer); font-size: 12px; }
.home-next-action { display: grid; grid-template-columns: minmax(0, 1fr) 210px; gap: 34px; margin-top: 42px; padding: clamp(26px, 5vw, 48px); border: 1px solid var(--border-strong); border-radius: 20px; background: var(--surface-primary); box-shadow: var(--shadow-medium); }
.next-course { margin-top: 22px; color: var(--accent-deep); font-size: 12px; font-weight: 650; }.next-copy h2 { max-width: 700px; margin-top: 7px; font-size: clamp(24px, 4vw, 39px); font-weight: 680; letter-spacing: -.04em; line-height: 1.2; }.next-reason { max-width: 680px; margin-top: 12px; color: var(--text-secondary); font-size: 13px; line-height: 1.7; }.home-primary { display: inline-flex; align-items: center; gap: 7px; min-height: 42px; margin-top: 26px; padding: 0 15px; color: var(--text-inverse); border-radius: 9px; background: var(--accent); font-size: 12px; font-weight: 700; box-shadow: 0 8px 18px rgba(52,120,246,.18); }.home-primary:hover { background: var(--accent-hover); }
.next-meta { align-self: end; display: grid; gap: 4px; padding-left: 23px; border-left: 1px solid var(--border-subtle); }.next-meta span { color: var(--accent-deep); font-size: 11px; font-weight: 700; }.next-meta strong { margin-top: 10px; font-size: 42px; font-weight: 680; letter-spacing: -.05em; }.next-meta small { color: var(--text-tertiary); font-size: 11px; }.next-meta em { margin-top: 21px; padding-top: 12px; color: var(--text-tertiary); border-top: 1px solid var(--border-subtle); font-size: 10px; font-style: normal; line-height: 1.5; }
.home-courses { margin-top: 50px; }.home-courses > header { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; padding-bottom: 13px; border-bottom: 1px solid var(--border-subtle); }.home-courses > header h2 { margin-top: 5px; font-size: 20px; font-weight: 680; }.home-courses > header > span { color: var(--text-tertiary); font-size: 11px; }.course-list { display: grid; }.course-row { display: grid; grid-template-columns: 38px minmax(0, 1fr) 38px; align-items: center; gap: 13px; min-height: 72px; padding: 10px 3px; border-bottom: 1px solid var(--border-subtle); }.course-row-mark { width: 34px; height: 34px; display: grid; place-items: center; color: var(--tone-blue-fg); border-radius: 11px; background: var(--tone-blue-bg); font-size: 13px; font-weight: 700; }.course-row-copy { min-width: 0; display: grid; gap: 4px; }.course-row-copy strong { overflow: hidden; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.course-row-copy span { overflow: hidden; color: var(--text-tertiary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.course-row-copy .row-error { color: var(--danger); }.course-row-action { width: 34px; height: 34px; display: grid; place-items: center; color: var(--text-secondary); border-radius: 9px; }.course-row-action:hover { color: var(--accent-deep); background: var(--accent-softer); }
@media (max-width: 700px) { .adaptive-home { padding: 26px 15px 50px; }.home-header { flex-direction: column; }.home-next-action { grid-template-columns: 1fr; gap: 25px; padding: 24px 19px; }.next-meta { padding: 17px 0 0; border-top: 1px solid var(--border-subtle); border-left: 0; }.next-meta strong { margin-top: 4px; }.next-meta em { margin-top: 10px; }.home-primary { width: 100%; justify-content: center; } }
</style>
