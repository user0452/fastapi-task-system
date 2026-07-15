<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  Clock3,
  MessageSquareText,
  Play,
  RefreshCw
} from 'lucide-vue-next'
import {
  getTodayLearning,
  startLearningSession,
  submitLearningSession
} from '../../api/learning'
import { useCourseStore } from '../../stores/course'
import { showToast } from '../../components/common/toast'


const router = useRouter()
const courses = useCourseStore()
const session = ref(null)
const loading = ref(true)
const starting = ref(false)
const submitting = ref(false)
const error = ref('')
const answers = ref({})
const result = ref(null)
const startedAt = ref(null)

const isStarted = computed(() => session.value?.status === 'in_progress')
const isCompleted = computed(() => ['completed', 'evaluated'].includes(session.value?.status))
const practiceItems = computed(() => (session.value?.items || []).filter(item =>
  ['practice', 'advanced'].includes(item.item_type) && item.question
))
const answeredCount = computed(() => practiceItems.value.filter(item =>
  String(answers.value[item.question.id] || '').trim()
).length)
const canSubmit = computed(() => practiceItems.value.length > 0 && answeredCount.value === practiceItems.value.length)

function itemLabel(type) {
  return {
    explanation: '讲解',
    review: '复习',
    worked_example: '例题',
    practice: '练习',
    advanced: '进阶'
  }[type] || '学习'
}

async function loadToday() {
  if (!courses.current?.id) {
    session.value = null
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  const response = await getTodayLearning(courses.current.id)
  loading.value = false
  if (response.code === 200) {
    session.value = response.data
    answers.value = {}
    if (session.value?.status === 'in_progress') startedAt.value = Date.now()
  } else {
    error.value = response.message || '今日学习加载失败'
  }
}

async function startSession() {
  if (!session.value || starting.value) return
  starting.value = true
  const response = await startLearningSession(session.value.id)
  starting.value = false
  if (response.code === 200) {
    session.value = response.data
    startedAt.value = Date.now()
    showToast({ type: 'success', message: '今日学习已开始' })
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

async function submitSession() {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  const payload = practiceItems.value.map(item => ({
    question_id: item.question.id,
    user_answer: answers.value[item.question.id].trim()
  }))
  const elapsedMinutes = startedAt.value
    ? Math.max(1, Math.round((Date.now() - startedAt.value) / 60000))
    : session.value.estimated_minutes
  const response = await submitLearningSession(session.value.id, payload, elapsedMinutes)
  submitting.value = false
  if (response.code === 200) {
    result.value = response.data
    session.value = null
    showToast({ type: 'success', message: '练习已评估，后续计划已更新' })
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

function askCoach(item) {
  const point = item.knowledge_point_name || item.title
  router.push({ path: '/agent', query: { prompt: `请讲解${point}，并给我一个容易理解的例子。` } })
}

onMounted(async () => {
  await courses.ensureLoaded()
  await loadToday()
})

watch(() => courses.current?.id, (next, previous) => {
  if (previous && next !== previous) loadToday()
})
</script>

<template>
  <div class="today-page">
    <header class="page-heading">
      <div>
        <span class="eyebrow">{{ courses.current?.name || '课程冲刺' }}</span>
        <h1>今日学习</h1>
        <p>只处理今天需要完成的内容，提交后自动调整后续计划。</p>
      </div>
      <button v-if="courses.current" class="icon-button" type="button" title="刷新" aria-label="刷新今日学习" @click="loadToday">
        <RefreshCw :size="18" />
      </button>
    </header>

    <div v-if="loading" class="state-block" aria-live="polite">
      <span class="spinner"></span>
      <p>正在加载今日计划</p>
    </div>

    <div v-else-if="error" class="state-block error-state">
      <p>{{ error }}</p>
      <button class="text-button" type="button" @click="loadToday">重新加载</button>
    </div>

    <section v-else-if="!courses.current" class="empty-workspace">
      <BookOpenCheck :size="34" />
      <h2>先创建一门冲刺课程</h2>
      <p>设置考试日期和每日可用时间后，资料、诊断和每日计划都会绑定到这门课程。</p>
      <button class="primary-button" type="button" @click="router.push('/courses')">
        创建课程 <ArrowRight :size="17" />
      </button>
    </section>

    <section v-else-if="result" class="completion-view">
      <div class="completion-title">
        <CheckCircle2 :size="32" />
        <div>
          <h2>今天的学习已完成</h2>
          <p>掌握度已经更新，明日任务已根据本次表现调整。</p>
        </div>
      </div>

      <div class="mastery-change-list">
        <article v-for="change in result.mastery_changes" :key="change.id" class="mastery-change-row">
          <span>知识点 #{{ change.knowledge_point_id }}</span>
          <strong>{{ Number(change.before).toFixed(0) }} → {{ Number(change.after).toFixed(0) }}</strong>
          <p>{{ change.reason }}</p>
        </article>
      </div>

      <div v-if="result.adaptations?.length" class="adaptation-note">
        <strong>计划调整</strong>
        <p>{{ result.adaptations[0].reason }}</p>
      </div>

      <div class="completion-actions">
        <button class="secondary-button" type="button" @click="router.push('/progress')">查看掌握度</button>
        <button class="primary-button" type="button" @click="router.push('/agent')">继续问 AI 助教</button>
      </div>
    </section>

    <section v-else-if="isCompleted" class="completion-view persisted-completion">
      <div class="completion-title">
        <CheckCircle2 :size="32" />
        <div>
          <h2>今天的学习已完成</h2>
          <p>提交记录、掌握度和后续计划都已保存在服务端。</p>
        </div>
      </div>
      <div class="completion-actions">
        <button class="secondary-button" type="button" @click="router.push('/progress')">查看掌握度与计划变化</button>
        <button class="primary-button" type="button" @click="router.push('/agent')">继续问 AI 助教</button>
      </div>
    </section>

    <section v-else-if="!session" class="empty-workspace">
      <CheckCircle2 :size="34" />
      <h2>今天没有待完成单元</h2>
      <p v-if="courses.current.status === 'diagnostic_pending'">资料已经准备好，完成一次诊断即可生成每日计划。</p>
      <p v-else-if="['draft', 'preparing'].includes(courses.current.status)">先上传课程资料并等待自动处理完成。</p>
      <p v-else>今天的内容可能已经完成，也可以查看后续计划和学习进度。</p>
      <button
        class="primary-button"
        type="button"
        @click="router.push(courses.current.status === 'diagnostic_pending' ? '/courses?tab=diagnostic' : '/courses')"
      >
        {{ courses.current.status === 'diagnostic_pending' ? '开始诊断' : '查看课程' }}
        <ArrowRight :size="17" />
      </button>
    </section>

    <template v-else>
      <section class="today-summary" aria-label="今日学习概览">
        <div>
          <span>计划单元</span>
          <strong>{{ session.items?.length || 0 }}</strong>
        </div>
        <div>
          <span>预计时长</span>
          <strong>{{ session.estimated_minutes }} 分钟</strong>
        </div>
        <div>
          <span>练习题</span>
          <strong>{{ practiceItems.length }}</strong>
        </div>
        <div>
          <span>状态</span>
          <strong>{{ isStarted ? '进行中' : '待开始' }}</strong>
        </div>
      </section>

      <section class="study-workspace">
        <div class="study-heading">
          <div>
            <span>{{ session.scheduled_date }}</span>
            <h2>{{ courses.current.name }} · 今日单元</h2>
          </div>
          <div class="time-label"><Clock3 :size="16" /> {{ session.estimated_minutes }} 分钟</div>
        </div>

        <ol class="study-items">
          <li v-for="(item, index) in session.items" :key="item.id" class="study-item">
            <span class="step-index">{{ String(index + 1).padStart(2, '0') }}</span>
            <div class="item-content">
              <div class="item-title-row">
                <span class="item-type">{{ itemLabel(item.item_type) }}</span>
                <h3>{{ item.title }}</h3>
                <button
                  v-if="['explanation', 'review', 'worked_example'].includes(item.item_type)"
                  class="icon-button small"
                  type="button"
                  title="让 AI 讲解"
                  aria-label="让 AI 讲解"
                  @click="askCoach(item)"
                >
                  <MessageSquareText :size="16" />
                </button>
              </div>
              <p v-if="!item.question" class="item-description">
                围绕“{{ item.knowledge_point_name || item.title }}”梳理定义、关键步骤和典型应用。
              </p>
              <div v-else class="practice-block">
                <p class="question-text">{{ item.question.question }}</p>
                <textarea
                  v-model="answers[item.question.id]"
                  :disabled="!isStarted"
                  rows="4"
                  maxlength="3000"
                  placeholder="写下你的理解，不需要与参考答案逐字一致"
                ></textarea>
              </div>
            </div>
          </li>
        </ol>

        <footer class="study-actions">
          <span v-if="isStarted && practiceItems.length">已完成 {{ answeredCount }} / {{ practiceItems.length }} 道练习</span>
          <span v-else>开始后即可填写练习并提交评估</span>
          <button v-if="!isStarted" class="primary-button" type="button" :disabled="starting" @click="startSession">
            <Play :size="17" fill="currentColor" /> {{ starting ? '正在开始' : '开始今日学习' }}
          </button>
          <button v-else class="primary-button" type="button" :disabled="!canSubmit || submitting" @click="submitSession">
            {{ submitting ? '正在评估' : '提交今日练习' }}
          </button>
        </footer>
      </section>
    </template>
  </div>
</template>

<style scoped>
.today-page { max-width: 1080px; margin: 0 auto; }
.page-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
}
.eyebrow { color: #17705b; font-size: 12px; font-weight: 700; }
.page-heading h1 { margin-top: 4px; font-size: 28px; font-weight: 720; }
.page-heading p { margin-top: 7px; color: #69736e; font-size: 13px; }
.icon-button {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border: 1px solid #d5dcd7;
  border-radius: 6px;
  color: #5d6963;
  background: #ffffff;
}
.icon-button:hover { color: #14634f; border-color: #9ebcaf; }
.icon-button.small { width: 30px; height: 30px; margin-left: auto; }
.state-block,
.empty-workspace {
  min-height: 360px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  border-top: 1px solid #dce2de;
  border-bottom: 1px solid #dce2de;
}
.state-block p,
.empty-workspace p { max-width: 500px; color: #69736e; font-size: 13px; }
.empty-workspace svg { color: #23735f; }
.empty-workspace h2 { font-size: 19px; font-weight: 700; }
.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #ccd7d1;
  border-top-color: #176b58;
  border-radius: 50%;
  animation: spin 700ms linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.primary-button,
.secondary-button,
.text-button {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 15px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
}
.primary-button { color: #ffffff; background: #176b58; }
.primary-button:hover:not(:disabled) { background: #105845; }
.primary-button:disabled { opacity: .45; cursor: not-allowed; }
.secondary-button { color: #1a5d4d; border: 1px solid #a8beb4; background: #ffffff; }
.text-button { color: #176b58; }
.today-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 18px;
  background: #eef3f0;
  border: 1px solid #d8dfdb;
  border-radius: 8px;
}
.today-summary > div { display: grid; gap: 4px; padding: 15px 18px; border-right: 1px solid #d8dfdb; }
.today-summary > div:last-child { border-right: 0; }
.today-summary span { color: #6b756f; font-size: 11px; }
.today-summary strong { color: #26312c; font-size: 15px; }
.study-workspace { background: #ffffff; border: 1px solid #d8dfdb; border-radius: 8px; overflow: hidden; }
.study-heading {
  min-height: 74px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid #e0e5e2;
}
.study-heading span { color: #75807a; font-size: 11px; }
.study-heading h2 { margin-top: 2px; font-size: 17px; font-weight: 700; }
.time-label { display: flex; align-items: center; gap: 6px; color: #66716b; font-size: 12px; }
.study-items { padding: 0; list-style: none; }
.study-item { display: grid; grid-template-columns: 42px 1fr; gap: 14px; margin: 0; padding: 20px; border-bottom: 1px solid #e3e7e4; }
.step-index { color: #8b9590; font-family: var(--font-mono); font-size: 11px; padding-top: 3px; }
.item-title-row { display: flex; align-items: center; gap: 9px; }
.item-type { color: #176b58; font-size: 11px; font-weight: 800; }
.item-title-row h3 { font-size: 15px; font-weight: 700; }
.item-description { margin-top: 8px; color: #68736d; font-size: 13px; }
.question-text { margin: 10px 0; color: #2a3530; font-size: 14px; line-height: 1.65; }
.practice-block textarea {
  width: 100%;
  resize: vertical;
  padding: 11px 12px;
  border: 1px solid #cdd5d0;
  border-radius: 6px;
  background: #fbfcfb;
  font-size: 13px;
  line-height: 1.55;
}
.practice-block textarea:focus { border-color: #27806a; box-shadow: 0 0 0 2px rgba(39, 128, 106, .11); }
.practice-block textarea:disabled { background: #f0f2f0; cursor: not-allowed; }
.study-actions {
  min-height: 66px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  padding: 13px 20px;
  background: #f5f7f5;
}
.study-actions > span { color: #68736d; font-size: 12px; }
.completion-view { padding: 24px; background: #ffffff; border: 1px solid #d8dfdb; border-radius: 8px; }
.completion-title { display: flex; align-items: center; gap: 13px; padding-bottom: 20px; border-bottom: 1px solid #e0e5e2; }
.completion-title svg { color: #197055; }
.completion-title h2 { font-size: 19px; font-weight: 750; }
.completion-title p { margin-top: 4px; color: #68736d; font-size: 13px; }
.mastery-change-list { display: grid; margin-top: 8px; }
.mastery-change-row { display: grid; grid-template-columns: 1fr auto; gap: 3px 16px; padding: 14px 0; border-bottom: 1px solid #e4e8e5; }
.mastery-change-row span { font-size: 13px; }
.mastery-change-row strong { color: #176b58; font-size: 14px; }
.mastery-change-row p { grid-column: 1 / -1; color: #6a756f; font-size: 12px; }
.adaptation-note { margin-top: 18px; padding: 14px 16px; border-left: 3px solid #d79528; background: #fff8e9; }
.adaptation-note strong { font-size: 13px; }
.adaptation-note p { margin-top: 4px; color: #6b5a36; font-size: 12px; }
.completion-actions { display: flex; justify-content: flex-end; gap: 9px; margin-top: 20px; }

@media (max-width: 700px) {
  .today-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .today-summary > div:nth-child(2) { border-right: 0; }
  .today-summary > div:nth-child(-n+2) { border-bottom: 1px solid #d8dfdb; }
  .study-item { grid-template-columns: 28px 1fr; gap: 8px; padding: 16px 12px; }
  .study-heading,
  .study-actions { align-items: flex-start; flex-direction: column; padding: 13px 14px; }
  .study-actions .primary-button { width: 100%; }
  .completion-view { padding: 18px 14px; }
  .completion-actions { flex-direction: column-reverse; }
  .completion-actions button { width: 100%; }
}
</style>
