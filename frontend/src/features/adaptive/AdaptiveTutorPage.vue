<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight,
  BookOpenCheck,
  Check,
  CircleAlert,
  CircleHelp,
  FileText,
  Lightbulb,
  RefreshCw,
  Send,
  Sparkles,
  Upload
} from 'lucide-vue-next'
import {
  addAdaptiveQuestions,
  commitAdaptiveQuestionBank,
  getAdaptiveOverview,
  getAdaptiveProgress,
  getAdaptiveSources,
  previewAdaptiveQuestionBank,
  sendAdaptiveTutor,
  startAdaptiveAction,
  startAdaptiveDiagnostic,
  submitAdaptiveAction,
  submitAdaptiveDiagnostic,
  submitAdaptiveTutorCheck,
  tagAdaptiveQuestion
} from '../../api/adaptive'
import { showToast } from '../../components/common/toast'
import MaterialWorkspace from '../courses/components/MaterialWorkspace.vue'
import { useCourseStore } from '../../stores/course'

const props = defineProps({
  pageMode: { type: String, default: 'learn' }
})

const route = useRoute()
const router = useRouter()
const courses = useCourseStore()
const courseId = computed(() => Number(route.params.courseId))
const course = computed(() => courses.courses.find(item => Number(item.id) === courseId.value) || courses.current)

const overview = ref(null)
const progress = ref(null)
const sources = ref(null)
const loading = ref(true)
const viewLoading = ref(false)
const error = ref('')
const selectedObjectiveId = ref(null)
const actionAnswer = ref('')
const actionStarted = ref(false)
const actionSubmitting = ref(false)
const actionResult = ref(null)
const tutorResponse = ref(null)
const tutorLoading = ref(false)
const tutorCheckResponse = ref('')
const tutorCheckSubmitting = ref(false)
const diagnostic = ref(null)
const diagnosticAnswers = ref({})
const diagnosticSubmitting = ref(false)
const questionSubmitting = ref(false)
const questionFile = ref(null)
const importPreview = ref(null)
const importLoading = ref(false)
const importCommitting = ref(false)
const manualObjectiveByQuestion = ref({})
let overviewRequestSequence = 0
const questionForm = ref({
  content: '',
  answer: '',
  question_type: 'short_answer',
  options: '',
  difficulty: 'medium',
  objective_id: '',
  source_type: 'user_upload'
})

const view = computed(() => props.pageMode)
const action = computed(() => overview.value?.next_action || null)
const objectives = computed(() => overview.value?.objectives || progress.value?.objectives || [])
const selectedObjective = computed(() => (
  progress.value?.objectives?.find(item => Number(item.id) === Number(selectedObjectiveId.value))
  || objectives.value.find(item => Number(item.id) === Number(selectedObjectiveId.value))
  || null
))
const actionTypeLabel = {
  explain: '基础讲解',
  practice: '场景练习',
  verify_mastery: '掌握度验证',
  review: '间隔复习',
  misconception_repair: '错误模式修复',
  repair_prerequisite: '前置目标修复',
  transfer: '迁移练习'
}
const stateLabel = {
  mastered: '已掌握',
  progressing: '进展中',
  learning: '学习中',
  weak: '薄弱',
  unknown: '未验证'
}
const questionTypeLabel = {
  multiple_choice: '选择题',
  true_false: '判断题',
  short_answer: '简答题',
  calculation: '计算题',
  scenario: '场景题',
  essay: '论述题'
}

function masteryPercent(value) {
  return `${Math.round(Math.max(0, Math.min(1, Number(value || 0))) * 100)}%`
}

function formatDate(value) {
  if (!value) return '尚无记录'
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(value))
}

function objectiveForAction(value) {
  return objectives.value.find(item => Number(item.id) === Number(value))
}

function actionObjectiveTitle(value) {
  return action.value?.objective_title
    || objectiveForAction(value)?.title
    || '等待可验证学习目标'
}

function setView(nextView) {
  const paths = {
    learn: `/learn/${courseId.value}`,
    progress: `/progress/${courseId.value}`,
    sources: `/materials/${courseId.value}`
  }
  router.push(paths[nextView] || paths.learn)
  if (nextView === 'progress') loadProgress()
  if (nextView === 'sources') loadSources()
}

async function loadOverview() {
  if (!courseId.value) return
  const sequence = ++overviewRequestSequence
  loading.value = true
  error.value = ''
  try {
    const response = await getAdaptiveOverview(courseId.value)
    // AppShell, route changes, and material completion can request the same
    // overview concurrently. An older response must not roll back a newer
    // in-progress action or next-action decision.
    if (sequence !== overviewRequestSequence) return
    if (response.code !== 200) throw new Error(response.message || 'Adaptive Tutor 读取失败')
    overview.value = response.data
    if (!selectedObjectiveId.value) selectedObjectiveId.value = response.data?.objectives?.[0]?.id || null
    actionStarted.value = response.data?.next_action?.status === 'in_progress'
    if (!actionStarted.value) actionAnswer.value = ''
  } catch (requestError) {
    error.value = requestError.message || 'Adaptive Tutor 读取失败'
  } finally {
    loading.value = false
  }
}

async function loadProgress() {
  if (!courseId.value) return
  viewLoading.value = true
  try {
    const response = await getAdaptiveProgress(courseId.value)
    if (response.code !== 200) throw new Error(response.message || '学习进度读取失败')
    progress.value = response.data
    if (!selectedObjectiveId.value) selectedObjectiveId.value = response.data?.objectives?.[0]?.id || null
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '学习进度读取失败' })
  } finally {
    viewLoading.value = false
  }
}

async function loadSources() {
  if (!courseId.value) return
  viewLoading.value = true
  try {
    const response = await getAdaptiveSources(courseId.value)
    if (response.code !== 200) throw new Error(response.message || 'Sources 读取失败')
    sources.value = response.data
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || 'Sources 读取失败' })
  } finally {
    viewLoading.value = false
  }
}

async function beginAction() {
  if (!action.value?.id) return
  try {
    const response = await startAdaptiveAction(action.value.id)
    if (response.code !== 200) throw new Error(response.message || '学习动作无法开始')
    overview.value.next_action = response.data
    actionStarted.value = true
    actionResult.value = null
    tutorResponse.value = null
    if (!response.data?.question) {
      await askTutor('explain', `请围绕“${actionObjectiveTitle(response.data?.objective_id)}”开始一段简短、基于课程资料的讲解。`)
    }
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '学习动作无法开始' })
  }
}

async function submitAction() {
  if (!action.value?.id || !actionAnswer.value.trim() || actionSubmitting.value) return
  if (!action.value.question) {
    showToast({ type: 'info', message: '讲解完成后，可以用“检查理解”提交你的回答' })
    return
  }
  actionSubmitting.value = true
  try {
    const response = await submitAdaptiveAction(action.value.id, {
      response: actionAnswer.value.trim(),
      idempotency_key: `web-action-${action.value.id}-${btoa(unescape(encodeURIComponent(actionAnswer.value.trim()))).slice(0, 80)}`
    })
    if (response.code !== 200) throw new Error(response.message || '答案提交失败')
    actionResult.value = response.data
    overview.value.next_action = response.data.next_action
    actionStarted.value = false
    actionAnswer.value = ''
    await Promise.all([loadProgress(), view.value === 'sources' ? loadSources() : Promise.resolve()])
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '答案提交失败' })
  } finally {
    actionSubmitting.value = false
  }
}

async function askTutor(intent, prompt) {
  if (tutorLoading.value) return
  tutorLoading.value = true
  try {
    const response = await sendAdaptiveTutor(courseId.value, {
      message: prompt,
      intent,
      action_id: action.value?.id || null,
      objective_id: action.value?.objective_id || selectedObjectiveId.value || null
    })
    if (response.code !== 200) throw new Error(response.message || 'Tutor 暂时无法回答')
    tutorResponse.value = response.data
    if (response.data?.tutor_check) tutorCheckResponse.value = ''
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || 'Tutor 暂时无法回答' })
  } finally {
    tutorLoading.value = false
  }
}

async function requestTutorCheck() {
  await askTutor('check_understanding', '请检查我是否真正理解当前目标，并给我一个需要自己回答的问题。')
}

async function submitTutorCheck() {
  const checkId = tutorResponse.value?.tutor_check?.id
  if (!checkId || !tutorCheckResponse.value.trim() || tutorCheckSubmitting.value) return
  tutorCheckSubmitting.value = true
  try {
    const response = await submitAdaptiveTutorCheck(courseId.value, checkId, {
      response: tutorCheckResponse.value.trim(),
      idempotency_key: `web-tutor-check-${checkId}-${Date.now()}`
    })
    if (response.code !== 200) throw new Error(response.message || 'Tutor Check 提交失败')
    actionResult.value = response.data
    overview.value.next_action = response.data.next_action
    actionStarted.value = false
    tutorResponse.value = null
    tutorCheckResponse.value = ''
    await loadProgress()
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || 'Tutor Check 提交失败' })
  } finally {
    tutorCheckSubmitting.value = false
  }
}

async function beginDiagnostic() {
  try {
    const response = await startAdaptiveDiagnostic(courseId.value, 6)
    if (response.code !== 200) throw new Error(response.message || '诊断无法开始')
    diagnostic.value = response.data
    diagnosticAnswers.value = {}
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '诊断无法开始' })
  }
}

async function submitDiagnostic() {
  if (!diagnostic.value?.questions?.length || diagnosticSubmitting.value) return
  const answers = diagnostic.value.questions
    .map(question => ({ question_id: question.id, response: diagnosticAnswers.value[question.id] || '' }))
    .filter(item => item.response.trim())
  if (answers.length !== diagnostic.value.questions.length) {
    showToast({ type: 'error', message: '请先完成每一道诊断题' })
    return
  }
  diagnosticSubmitting.value = true
  try {
    const response = await submitAdaptiveDiagnostic(courseId.value, answers)
    if (response.code !== 200) throw new Error(response.message || '诊断提交失败')
    diagnostic.value = { ...diagnostic.value, complete: true, result: response.data }
    overview.value.next_action = response.data.next_action
    await loadProgress()
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '诊断提交失败' })
  } finally {
    diagnosticSubmitting.value = false
  }
}

async function addQuestion() {
  const form = questionForm.value
  if (!form.content.trim() || !form.answer.trim() || !form.objective_id || questionSubmitting.value) return
  questionSubmitting.value = true
  try {
    const response = await addAdaptiveQuestions(courseId.value, [{
      content: form.content.trim(),
      answer: form.answer.trim(),
      question_type: form.question_type,
      options: form.options.split(/\n|,/).map(item => item.trim()).filter(Boolean),
      difficulty: form.difficulty,
      source_type: form.source_type,
      objective_ids: [Number(form.objective_id)],
      coverage_type: 'scenario'
    }])
    if (response.code !== 201) throw new Error(response.message || '题目添加失败')
    questionForm.value = { content: '', answer: '', question_type: 'short_answer', options: '', difficulty: 'medium', objective_id: '', source_type: 'user_upload' }
    await Promise.all([loadSources(), loadOverview()])
    showToast({ type: 'success', message: '题目已加入题库，后续练习会优先检索它' })
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '题目添加失败' })
  } finally {
    questionSubmitting.value = false
  }
}

function selectQuestionFile(event) {
  questionFile.value = event.target.files?.[0] || null
  importPreview.value = null
}

async function previewQuestionFile() {
  if (!questionFile.value || importLoading.value) return
  importLoading.value = true
  try {
    const response = await previewAdaptiveQuestionBank(courseId.value, questionFile.value)
    if (response.code !== 202) throw new Error(response.message || '题库解析失败')
    importPreview.value = response.data
    showToast({ type: 'success', message: '题库已解析，请确认匹配和待复核项目后导入' })
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '题库解析失败' })
  } finally {
    importLoading.value = false
  }
}

async function commitQuestionFile() {
  const batchId = importPreview.value?.batch?.id
  if (!batchId || importCommitting.value) return
  importCommitting.value = true
  try {
    const response = await commitAdaptiveQuestionBank(courseId.value, batchId)
    if (response.code !== 200) throw new Error(response.message || '题库导入失败')
    importPreview.value = null
    questionFile.value = null
    await Promise.all([loadSources(), loadOverview()])
    showToast({ type: 'success', message: `题库导入完成：${response.data?.created_count || 0} 道新题` })
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '题库导入失败' })
  } finally {
    importCommitting.value = false
  }
}

async function tagQuestionManually(question) {
  const objectiveId = manualObjectiveByQuestion.value[question.id]
  if (!objectiveId) return
  try {
    const response = await tagAdaptiveQuestion(courseId.value, question.id, [Number(objectiveId)])
    if (response.code !== 200) throw new Error(response.message || '手动关联失败')
    await Promise.all([loadSources(), loadOverview()])
    showToast({ type: 'success', message: '题目已准备好用于练习' })
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '手动关联失败' })
  }
}

async function onMaterialProcessed() {
  await Promise.all([loadOverview(), loadSources()])
}

onMounted(async () => {
  await courses.ensureLoaded()
  await loadOverview()
  if (view.value === 'progress') await loadProgress()
  if (view.value === 'sources') await loadSources()
})

watch(() => route.params.courseId, async () => {
  await loadOverview()
  progress.value = null
  sources.value = null
})

watch(view, nextView => {
  if (nextView === 'progress' && !progress.value) loadProgress()
  if (nextView === 'sources' && !sources.value) loadSources()
})
</script>

<template>
  <div class="adaptive-tutor">
    <header class="adaptive-header">
      <div class="adaptive-identity">
        <span class="adaptive-kicker"><Sparkles :size="14" /> {{ view === 'learn' ? '今天的学习' : (view === 'progress' ? '学习进度' : '课程资料') }}</span>
        <h1>{{ course?.name || '课程学习' }}</h1>
        <p>{{ view === 'learn' ? '专注完成眼前这一小步。完成后，我们会为你准备下一步。' : (view === 'progress' ? '看看已经掌握的内容，以及下一次该复习什么。' : '上传教材和题目，让课程准备好为你出题。') }}</p>
      </div>
      <div v-if="course?.exam_at" class="adaptive-header-meta">
        <span class="exam-date">目标日期：{{ formatDate(course.exam_at) }}</span>
      </div>
    </header>

    <div v-if="loading" class="adaptive-state" role="status">正在读取课程证据与下一动作</div>
    <div v-else-if="error" class="adaptive-state error-state" role="alert">
      <CircleAlert :size="24" /><strong>{{ error }}</strong><button type="button" @click="loadOverview">重新读取</button>
    </div>
    <main v-else class="adaptive-main">
      <template v-if="view === 'learn'">
        <section class="learn-layout">
          <div class="learn-primary">
          <div class="section-intro">
              <span class="section-eyebrow">现在就开始</span>
              <h2>今天建议学这个</h2>
              <p>不用规划整天，完成这一项就好。</p>
            </div>

            <article v-if="action" class="action-surface" :class="action.action_type">
              <div class="action-topline">
                <span class="action-type"><Lightbulb :size="15" /> {{ actionTypeLabel[action.action_type] || action.action_type }}</span>
                <span class="action-time">约 {{ action.expected_minutes }} 分钟</span>
              </div>
              <h3>{{ actionObjectiveTitle(action.objective_id) }}</h3>
              <p class="action-ability">{{ objectiveForAction(action.objective_id)?.required_ability || action.required_ability || '完成一次可验证的学习动作' }}</p>
              <div class="action-reason">
                <strong>为什么推荐给你</strong>
                <p>{{ action.reason }}</p>
              </div>

              <div v-if="!actionStarted" class="action-start-row">
                <span v-if="action.question">我们已经为你准备好一道练习题。</span>
                <span v-else>先听一个简短讲解，再用自己的话检查理解。</span>
                <button type="button" class="action-button" @click="beginAction">开始 <ArrowRight :size="16" /></button>
              </div>

              <form v-else-if="action.question" class="action-answer" @submit.prevent="submitAction">
                <div class="question-block">
                  <span>练习 · {{ questionTypeLabel[action.question.question_type] || action.question.question_type }}</span>
                  <p>{{ action.question.content }}</p>
                </div>
                <div v-if="action.question.question_type === 'multiple_choice'" class="choice-list">
                  <label v-for="(option, index) in action.question.options || []" :key="option" class="choice-option">
                    <input v-model="actionAnswer" type="radio" name="adaptive-choice" :value="String.fromCharCode(65 + index)" />
                    <span>{{ String.fromCharCode(65 + index) }}. {{ option }}</span>
                  </label>
                </div>
                <div v-else-if="action.question.question_type === 'true_false'" class="choice-list boolean-choice">
                  <label class="choice-option"><input v-model="actionAnswer" type="radio" name="adaptive-true-false" value="true" /><span>正确</span></label>
                  <label class="choice-option"><input v-model="actionAnswer" type="radio" name="adaptive-true-false" value="false" /><span>错误</span></label>
                </div>
                <label v-else class="answer-field">
                  <span>你的回答</span>
                  <textarea v-model="actionAnswer" rows="5" placeholder="先写判断依据，再写结论……" autofocus></textarea>
                </label>
                <div class="answer-actions">
                  <span>提交后会立刻为你准备下一步。</span>
                  <button type="submit" class="action-button" :disabled="actionSubmitting || !actionAnswer.trim()">
                    <Send :size="15" /> {{ actionSubmitting ? '正在查看' : '提交答案' }}
                  </button>
                </div>
              </form>
              <section v-else class="tutor-learning-surface">
                <div class="explain-block">
                  <span>学习助手</span>
                  <p>不着急。先用更容易理解的方式讲清楚，再检查自己是否真的会用。</p>
                </div>
                <div v-if="tutorResponse" class="tutor-live-response" aria-live="polite">
                  <strong>{{ tutorResponse.provider === 'llm' ? 'Tutor' : 'Tutor（确定性兜底）' }}</strong>
                  <p>{{ tutorResponse.reply }}</p>
                  <small v-if="tutorResponse.citations?.length">课程引用：{{ tutorResponse.citations.map(item => item.title || item.heading_path || `chunk ${item.chunk_id}`).join(' · ') }}</small>
                </div>
                <div v-else class="tutor-live-response"><p>{{ tutorLoading ? 'Tutor 正在读取课程证据……' : '点击一个教学动作开始。' }}</p></div>
                <div class="tutor-check-actions">
                  <button type="button" class="quiet-button" :disabled="tutorLoading" @click="askTutor('reframe', '换一种更直观的方式解释当前目标')">换一种解释</button>
                  <button type="button" class="quiet-button" :disabled="tutorLoading" @click="askTutor('example', '给我一个新的课程场景例子')">给个例子</button>
                  <button type="button" class="quiet-button" :disabled="tutorLoading" @click="askTutor('break_down', '把这个判断过程拆成几个步骤')">拆开步骤</button>
                  <button type="button" class="action-button" :disabled="tutorLoading" @click="requestTutorCheck">检查理解</button>
                </div>
                <form v-if="tutorResponse?.tutor_check" class="tutor-check-form" @submit.prevent="submitTutorCheck">
                  <span>理解检查</span>
                  <strong>{{ tutorResponse.tutor_check.question }}</strong>
                  <textarea v-model="tutorCheckResponse" rows="4" placeholder="用自己的话回答，说明判断依据和一个场景……"></textarea>
                  <button type="submit" class="action-button" :disabled="tutorCheckSubmitting || !tutorCheckResponse.trim()">{{ tutorCheckSubmitting ? '正在查看' : '提交回答' }}</button>
                </form>
              </section>
            </article>

            <article v-else class="empty-action">
              <Check :size="26" /><h3>先让课程准备好</h3><p>上传一份教材和几道题，我们就能从第一步开始陪你学。</p><button type="button" @click="setView('sources')">添加资料</button>
            </article>

            <article v-if="actionResult" class="evidence-result" aria-live="polite">
              <div class="result-mark"><Check :size="18" /></div>
              <div><span>刚刚完成</span><strong>{{ masteryPercent(actionResult.state.mastery) }} 掌握度 · {{ masteryPercent(actionResult.state.confidence) }} 把握度</strong><p>{{ actionResult.feedback }}</p></div>
              <small>{{ actionResult.update_reason }}</small>
            </article>

            <article v-if="diagnostic?.complete" class="evidence-result diagnostic-evidence-result" aria-live="polite">
              <div class="result-mark"><Check :size="18" /></div>
              <div><span>诊断完成</span><strong>已完成 {{ diagnostic.result?.count || 0 }} 次初步判断</strong><p>我们已经根据你的回答准备好下一步。</p></div>
              <small>{{ diagnostic.result?.question_count || 0 }} 道快速诊断题</small>
            </article>

            <section class="diagnostic-strip">
              <div><span class="section-eyebrow">先认识你</span><h3>想从适合你的难度开始？</h3><p>用几道小题快速了解你现在已经会什么。</p></div>
              <button type="button" class="quiet-button" @click="beginDiagnostic"><RefreshCw :size="15" /> 开始快速定位</button>
            </section>

            <section v-if="diagnostic" class="diagnostic-surface">
              <header><div><span class="section-eyebrow">快速定位</span><h3>{{ diagnostic.complete ? '定位完成' : '用几道题找到合适的起点' }}</h3></div><button type="button" @click="diagnostic = null">关闭</button></header>
              <div v-if="diagnostic.complete" class="diagnostic-complete"><Check :size="19" /><p>下一步已经为你准备好了。</p></div>
              <form v-else @submit.prevent="submitDiagnostic">
                <article v-for="(question, index) in diagnostic.questions" :key="question.id" class="diagnostic-question">
                  <span>0{{ index + 1 }} · {{ question.difficulty }}</span><p>{{ question.content }}</p><textarea v-model="diagnosticAnswers[question.id]" rows="3" placeholder="写出你的判断依据……"></textarea>
                </article>
                <button type="submit" class="action-button" :disabled="diagnosticSubmitting">{{ diagnosticSubmitting ? '正在查看' : '完成定位' }}</button>
              </form>
              <p v-if="!diagnostic.questions?.length" class="inline-empty">题库里还没有适合的题目，请先去资料页添加。</p>
            </section>
          </div>

          <aside class="tutor-context">
            <div class="context-heading"><CircleHelp :size="17" /><span>需要一点帮助？</span></div>
            <p>可以随时让学习助手换一种讲法、给出例子，或解释为什么现在学这一项。</p>
            <div class="context-objective" v-if="action">
              <span>当前目标</span><strong>{{ actionObjectiveTitle(action.objective_id) }}</strong><p>{{ objectiveForAction(action.objective_id)?.description || '等待课程目标详情' }}</p>
            </div>
            <div class="tutor-prompts">
              <button type="button" :disabled="tutorLoading" @click="askTutor('example', '换一个更具体的课程例子')">换一个例子 <ArrowRight :size="14" /></button>
              <button type="button" :disabled="tutorLoading" @click="askTutor('break_down', '把判断步骤拆开')">拆开判断步骤 <ArrowRight :size="14" /></button>
              <button type="button" :disabled="tutorLoading" @click="askTutor('why_this_action', '告诉我这道题在检查什么')">为什么学这个 <ArrowRight :size="14" /></button>
              <button type="button" :disabled="tutorLoading" @click="requestTutorCheck">检查理解 <ArrowRight :size="14" /></button>
            </div>
            <div v-if="tutorResponse" class="tutor-response"><span>学习助手</span><p>{{ tutorResponse.reply }}</p><small v-if="tutorResponse.citations?.length">来自课程资料：{{ tutorResponse.citations.map(item => item.material_title || item.heading_path || `资料片段 ${item.chunk_id}`).join(' · ') }}</small></div>
            <form v-if="tutorResponse?.tutor_check" class="tutor-check-form tutor-check-form-sidebar" @submit.prevent="submitTutorCheck">
              <span>理解检查</span>
              <strong>{{ tutorResponse.tutor_check.question }}</strong>
              <textarea v-model="tutorCheckResponse" rows="4" placeholder="用自己的话回答，说明判断依据和一个场景……"></textarea>
              <button type="submit" class="action-button" :disabled="tutorCheckSubmitting || !tutorCheckResponse.trim()">{{ tutorCheckSubmitting ? '正在查看' : '提交回答' }}</button>
            </form>
            <div class="context-foot"><FileText :size="14" /><span>围绕当前学习内容提供帮助</span></div>
          </aside>
        </section>
      </template>

      <template v-else-if="view === 'progress'">
        <section class="progress-view">
          <div class="section-intro"><span class="section-eyebrow">你的学习状态</span><h2>进度</h2><p>这里显示你已经会什么、正在练什么，以及哪些内容值得再看一次。</p></div>
          <div class="status-line" aria-label="学习状态统计">
            <span><i class="status-dot mastered"></i>已掌握 {{ progress?.status_counts?.mastered || 0 }}</span>
            <span><i class="status-dot progressing"></i>进展中 {{ progress?.status_counts?.progressing || 0 }}</span>
            <span><i class="status-dot learning"></i>学习中 {{ progress?.status_counts?.learning || 0 }}</span>
            <span><i class="status-dot weak"></i>薄弱 {{ progress?.status_counts?.weak || 0 }}</span>
            <span><i class="status-dot unknown"></i>未验证 {{ progress?.status_counts?.unknown || 0 }}</span>
          </div>
          <div v-if="viewLoading" class="inline-loading">正在读取学习进度</div>
          <div v-else class="progress-layout">
            <div class="objective-table" aria-label="学习目标列表">
              <button v-for="objective in progress?.objectives || []" :key="objective.id" type="button" class="objective-row" :class="{ selected: Number(selectedObjectiveId) === Number(objective.id) }" @click="selectedObjectiveId = objective.id">
                <span class="status-chip" :class="objective.state">{{ stateLabel[objective.state] || objective.state }}</span>
                <span class="objective-row-copy"><strong>{{ objective.title }}</strong><small>{{ objective.attempt_count }} 次练习 · 最近 {{ formatDate(objective.last_practiced_at) }}</small></span>
                <span class="objective-values"><b>{{ masteryPercent(objective.mastery) }}</b><small>置信 {{ masteryPercent(objective.confidence) }}</small></span>
              </button>
              <div v-if="!progress?.objectives?.length" class="inline-empty">课程还没有可学习内容。请先在资料页添加教材。</div>
            </div>
            <aside v-if="selectedObjective" class="objective-detail">
              <span class="section-eyebrow">为什么是这个状态</span><h3>{{ selectedObjective.title }}</h3><p>{{ selectedObjective.description }}</p>
              <div class="detail-metrics"><div><span>掌握度</span><strong>{{ masteryPercent(selectedObjective.mastery) }}</strong></div><div><span>把握度</span><strong>{{ masteryPercent(selectedObjective.confidence) }}</strong></div></div>
              <p class="confidence-explanation">{{ selectedObjective.confidence_explanation || '把握度会随着练习次数、回答是否稳定，以及最近是否练习而变化。' }}</p>
              <section><strong>最近学习记录</strong><article v-for="item in selectedObjective.evidence || []" :key="item.id"><span>{{ item.source_type }} · {{ masteryPercent(item.score) }}</span><p>{{ item.update_reason || '已记录一次学习' }}</p></article><small v-if="!selectedObjective.evidence?.length">完成一次练习后，这里会出现学习记录。</small></section>
              <section><strong>需要注意</strong><article v-for="item in selectedObjective.misconceptions || []" :key="item.id"><span>{{ item.code }} · {{ masteryPercent(item.confidence) }}</span><p>{{ item.description }}</p></article><small v-if="!selectedObjective.misconceptions?.length">暂时没有发现重复出现的问题。</small></section>
              <section v-if="selectedObjective.prerequisites?.length"><strong>先学这些</strong><p v-for="relation in selectedObjective.prerequisites" :key="relation.id">{{ relation.source_title }} · {{ masteryPercent(relation.confidence) }}</p></section>
            </aside>
          </div>
        </section>
      </template>

      <template v-else>
        <section class="sources-view">
          <div class="section-intro"><span class="section-eyebrow">课程准备</span><h2>资料</h2><p>上传教材和练习题。准备好后，我们会基于这些内容陪你练习。</p></div>
          <div class="source-count-line"><span><FileText :size="15" /> {{ sources?.materials?.length || 0 }} 份资料</span><span><BookOpenCheck :size="15" /> {{ sources?.counts?.question_count || 0 }} 道题</span></div>
          <div v-if="viewLoading" class="inline-loading">正在读取 Sources</div>
          <div v-else class="sources-layout">
            <section class="materials-source"><header><div><span class="section-eyebrow">教材与讲义</span><h3>学习资料</h3></div><span>PDF · DOCX · Markdown · TXT</span></header><MaterialWorkspace :course-id="courseId" @processed="onMaterialProcessed" /></section>
            <section class="question-source"><header><div><span class="section-eyebrow">练习题</span><h3>题库</h3></div><span>优先使用你上传的题目</span></header>
              <form class="question-import-form" @submit.prevent="previewQuestionFile">
                <label><span>批量导入题库</span><input type="file" accept=".json,.jsonl,.md,.markdown,.txt" @change="selectQuestionFile" /></label>
                <small>支持 JSON / JSONL / Markdown / TXT；导入前会先检查每道题是否适合当前课程。</small>
                <button type="submit" class="secondary-button" :disabled="importLoading || !questionFile">{{ importLoading ? '正在解析' : '预览题库' }}</button>
              </form>
              <section v-if="importPreview" class="import-preview">
                <div class="import-summary"><strong>导入预览</strong><span>{{ importPreview.batch.parsed_count }} 条解析</span><span>{{ importPreview.batch.matched_count }} 条已匹配</span><span>{{ importPreview.batch.unmatched_count }} 条未匹配</span><span>{{ importPreview.batch.invalid_count }} 条待复核/无效</span></div>
                <article v-for="item in importPreview.items" :key="item.raw_provenance?.line_or_index || item.content" class="import-item"><strong>{{ item.content }}</strong><small>{{ item.tagging?.status === 'matched' ? '已准备好用于练习' : (item.parse_error || '导入后可再确认') }}</small></article>
                <button type="button" class="action-button" :disabled="importCommitting" @click="commitQuestionFile">{{ importCommitting ? '正在导入' : '确认导入这批题' }}</button>
              </section>
              <form class="question-form" @submit.prevent="addQuestion">
                <label><span>题目</span><textarea v-model="questionForm.content" rows="3" placeholder="给定一个场景，要求学生完成什么可验证判断？"></textarea></label>
                <label><span>参考答案</span><textarea v-model="questionForm.answer" rows="3" placeholder="明确答案或评分依据"></textarea></label>
                <div class="question-form-grid"><label><span>题型</span><select v-model="questionForm.question_type"><option v-for="(label, type) in questionTypeLabel" :key="type" :value="type">{{ label }}</option></select></label><label><span>难度</span><select v-model="questionForm.difficulty"><option value="easy">简单</option><option value="medium">中等</option><option value="hard">困难</option></select></label></div>
                <label v-if="questionForm.question_type === 'multiple_choice'"><span>选项（每行一个）</span><textarea v-model="questionForm.options" rows="3" placeholder="选项 A\n选项 B\n选项 C"></textarea></label>
                <label><span>这道题练什么</span><select v-model="questionForm.objective_id" required><option value="" disabled>选择学习内容</option><option v-for="objective in objectives" :key="objective.id" :value="objective.id">{{ objective.title }}</option></select></label>
                <button type="submit" class="action-button" :disabled="questionSubmitting || !questionForm.objective_id"><Upload :size="15" /> {{ questionSubmitting ? '正在保存' : '添加到题库' }}</button>
              </form>
              <div class="question-list"><article v-for="question in sources?.questions || []" :key="question.id"><div><span class="question-type">{{ questionTypeLabel[question.question_type] || question.source_type }}</span><span>{{ question.difficulty }}</span><span>{{ question.status }}</span></div><strong>{{ question.content }}</strong><p>{{ question.objective_titles || '尚未确定练习内容' }}</p><div v-if="question.status === 'unmatched'" class="manual-tag"><select v-model="manualObjectiveByQuestion[question.id]"><option value="">选择这道题练什么</option><option v-for="objective in objectives" :key="objective.id" :value="objective.id">{{ objective.title }}</option></select><button type="button" class="secondary-button" :disabled="!manualObjectiveByQuestion[question.id]" @click="tagQuestionManually(question)">准备题目</button></div></article><div v-if="!sources?.questions?.length" class="inline-empty">还没有题目。添加一题后，就可以开始练习。</div></div>
            </section>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.adaptive-tutor { min-height: 100dvh; max-width: 1320px; margin: 0 auto; padding: 36px clamp(18px, 4vw, 56px) 70px; color: var(--text-primary); }
.adaptive-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 26px; padding-bottom: 28px; border-bottom: 1px solid var(--border-subtle); }
.adaptive-identity { min-width: 0; }
.adaptive-kicker, .section-eyebrow { display: inline-flex; align-items: center; gap: 6px; color: var(--accent-deep); font-size: 10px; font-weight: 750; letter-spacing: .12em; }
.adaptive-identity h1 { margin-top: 7px; font-size: clamp(26px, 4vw, 42px); font-weight: 680; letter-spacing: -.04em; }
.adaptive-identity p { max-width: 560px; margin-top: 8px; color: var(--text-secondary); font-size: 13px; }
.adaptive-header-meta { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 10px; color: var(--text-tertiary); font-size: 11px; }
.curriculum-status { display: inline-flex; align-items: center; gap: 6px; padding: 7px 9px; color: var(--success); border: 1px solid rgba(36, 138, 61, .18); border-radius: 8px; background: var(--success-soft); }
.curriculum-status.pending, .curriculum-status.degraded { color: var(--warning); border-color: rgba(169, 101, 0, .18); background: var(--warning-soft); }
.curriculum-status.failed { color: var(--danger); border-color: rgba(215, 0, 21, .18); background: var(--danger-soft); }
.exam-date { padding: 7px 0; }
.adaptive-nav { display: flex; gap: 22px; margin-top: 18px; border-bottom: 1px solid var(--border-subtle); }
.adaptive-nav button { display: inline-flex; align-items: center; gap: 7px; min-height: 46px; padding: 0 2px; color: var(--text-tertiary); border-bottom: 2px solid transparent; font-size: 13px; font-weight: 650; }
.adaptive-nav button small { color: inherit; font-size: 10px; font-weight: 450; }
.adaptive-nav button:hover, .adaptive-nav button.active { color: var(--accent-deep); border-bottom-color: var(--accent); }
.adaptive-main { padding-top: 34px; }
.adaptive-state { min-height: 380px; display: grid; place-content: center; justify-items: center; gap: 12px; color: var(--text-secondary); font-size: 13px; text-align: center; }
.error-state button, .empty-action button, .inline-empty button { min-height: 34px; padding: 0 12px; color: var(--accent-deep); border: 1px solid var(--border-accent); border-radius: 8px; background: var(--accent-softer); font-size: 12px; }
.section-intro h2 { margin-top: 5px; font-size: 25px; font-weight: 680; letter-spacing: -.03em; }
.section-intro p { margin-top: 7px; color: var(--text-secondary); font-size: 13px; }
.learn-layout { width: min(780px, 100%); display: grid; grid-template-columns: minmax(0, 1fr); gap: 34px; align-items: start; }
.learn-primary { min-width: 0; }
.action-surface { position: relative; margin-top: 25px; padding: clamp(22px, 4vw, 42px); border: 1px solid var(--border-strong); border-radius: 20px; background: var(--surface-primary); box-shadow: var(--shadow-medium); overflow: hidden; }
.action-surface::before { position: absolute; inset: 0 auto 0 0; width: 4px; content: ''; background: var(--accent); }
.action-surface.misconception_repair::before { background: var(--warning); }
.action-surface.verify_mastery::before { background: var(--success); }
.action-topline, .action-start-row, .answer-actions { display: flex; align-items: center; justify-content: space-between; gap: 15px; }
.action-type { display: inline-flex; align-items: center; gap: 6px; color: var(--accent-deep); font-size: 11px; font-weight: 750; }
.action-time { color: var(--text-tertiary); font-size: 11px; }
.action-surface h3 { max-width: 720px; margin-top: 25px; font-size: clamp(23px, 3.5vw, 35px); font-weight: 680; line-height: 1.24; }
.action-ability { max-width: 700px; margin-top: 12px; color: var(--text-secondary); font-size: 14px; line-height: 1.72; }
.action-reason { max-width: 680px; display: grid; gap: 4px; margin-top: 27px; padding-top: 18px; border-top: 1px solid var(--border-subtle); }
.action-reason strong { color: var(--text-primary); font-size: 12px; }
.action-reason p { color: var(--text-secondary); font-size: 13px; line-height: 1.6; }
.action-start-row { align-items: flex-end; margin-top: 28px; }
.action-start-row > span { max-width: 430px; color: var(--text-tertiary); font-size: 11px; line-height: 1.55; }
.action-button { min-height: 42px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 16px; color: var(--text-inverse); border-radius: 9px; background: var(--accent); font-size: 12px; font-weight: 700; box-shadow: 0 8px 18px rgba(52, 120, 246, .18); transition: transform var(--duration-fast) var(--ease-out), background var(--duration-fast) var(--ease-standard); }
.action-button:hover:not(:disabled) { background: var(--accent-hover); transform: translateY(-1px); }
.action-button:disabled { opacity: .45; }
.action-answer { margin-top: 25px; }
.question-block, .explain-block { padding: 15px 16px; border-left: 2px solid var(--accent); background: var(--accent-softer); }
.question-block > span, .explain-block > span { color: var(--accent-deep); font-size: 10px; font-weight: 750; letter-spacing: .05em; }
.question-block p, .explain-block p { margin-top: 8px; color: var(--text-primary); font-size: 15px; line-height: 1.7; }
.answer-field { display: grid; gap: 7px; margin-top: 18px; }
.answer-field > span { color: var(--text-secondary); font-size: 11px; font-weight: 650; }
.answer-field textarea, .diagnostic-question textarea, .question-form textarea { width: 100%; padding: 12px; border: 1px solid var(--border-strong); border-radius: 9px; background: var(--surface-secondary); font-size: 13px; line-height: 1.6; resize: vertical; }
.answer-field textarea:focus, .diagnostic-question textarea:focus, .question-form textarea:focus { border-color: var(--accent); box-shadow: var(--shadow-focus); }
.answer-actions { align-items: flex-end; margin-top: 12px; }
.answer-actions > span { color: var(--text-tertiary); font-size: 10px; }
.empty-action { min-height: 280px; display: grid; place-content: center; justify-items: center; gap: 11px; margin-top: 25px; padding: 28px; border: 1px solid var(--border-subtle); border-radius: 20px; background: var(--surface-primary); color: var(--text-tertiary); text-align: center; box-shadow: var(--shadow-small); }
.empty-action h3 { color: var(--text-primary); font-size: 18px; }
.empty-action p { max-width: 350px; font-size: 12px; }
.evidence-result { display: grid; grid-template-columns: 34px minmax(0, 1fr) minmax(180px, .7fr); gap: 13px; align-items: start; margin-top: 18px; padding: 16px; border-top: 1px solid rgba(36, 138, 61, .25); border-bottom: 1px solid rgba(36, 138, 61, .25); background: linear-gradient(90deg, rgba(36, 138, 61, .06), transparent); }
.result-mark { width: 30px; height: 30px; display: grid; place-items: center; color: var(--success); border-radius: 50%; background: var(--success-soft); }
.evidence-result div:nth-child(2) { display: grid; gap: 4px; }
.evidence-result div:nth-child(2) > span { color: var(--success); font-size: 10px; font-weight: 750; letter-spacing: .06em; }
.evidence-result strong { font-size: 15px; }
.evidence-result p { color: var(--text-secondary); font-size: 12px; }
.evidence-result > small { color: var(--text-tertiary); font-family: var(--font-mono); font-size: 10px; line-height: 1.55; }
.diagnostic-strip { display: flex; justify-content: space-between; gap: 20px; align-items: center; margin-top: 38px; padding-top: 22px; border-top: 1px solid var(--border-subtle); }
.diagnostic-strip h3 { margin-top: 4px; font-size: 15px; }
.diagnostic-strip p { max-width: 580px; margin-top: 4px; color: var(--text-secondary); font-size: 12px; }
.quiet-button { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 0 11px; color: var(--accent-deep); border: 1px solid var(--border-accent); border-radius: 8px; background: var(--accent-softer); font-size: 11px; font-weight: 650; white-space: nowrap; }
.diagnostic-surface { margin-top: 20px; padding: 18px; border: 1px solid var(--border-subtle); border-radius: 14px; background: var(--surface-secondary); }
.diagnostic-surface > header, .sources-layout section > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 15px; }
.diagnostic-surface > header h3, .sources-layout section > header h3 { margin-top: 4px; font-size: 16px; }
.diagnostic-surface > header button { color: var(--text-tertiary); font-size: 11px; }
.diagnostic-question { display: grid; gap: 7px; padding: 16px 0; border-bottom: 1px solid var(--border-subtle); }
.diagnostic-question > span { color: var(--accent-deep); font-size: 10px; font-weight: 750; }
.diagnostic-question > p { color: var(--text-primary); font-size: 13px; }
.diagnostic-question textarea { background: var(--surface-primary); }
.diagnostic-surface form > .action-button { margin-top: 16px; }
.diagnostic-complete { display: flex; align-items: center; gap: 9px; margin-top: 15px; color: var(--success); font-size: 12px; }
.tutor-context { padding: 24px; border: 1px solid var(--border-subtle); border-radius: 18px; background: var(--surface-secondary); }
.context-heading { display: flex; align-items: center; gap: 8px; color: var(--accent-deep); font-size: 12px; font-weight: 750; }
.tutor-context > p { margin-top: 12px; color: var(--text-secondary); font-size: 12px; line-height: 1.7; }
.context-objective { display: grid; gap: 5px; margin-top: 25px; padding-top: 18px; border-top: 1px solid var(--border-subtle); }
.context-objective > span { color: var(--text-tertiary); font-size: 10px; font-weight: 750; letter-spacing: .08em; }
.context-objective strong { font-size: 14px; line-height: 1.45; }
.context-objective p { color: var(--text-secondary); font-size: 11px; line-height: 1.6; }
.tutor-prompts { display: grid; gap: 1px; margin-top: 20px; border-top: 1px solid var(--border-subtle); }
.tutor-prompts button { display: flex; align-items: center; justify-content: space-between; min-height: 40px; color: var(--text-secondary); border-bottom: 1px solid var(--border-subtle); font-size: 11px; text-align: left; }
.tutor-prompts button:hover { color: var(--accent-deep); padding-left: 4px; }
.tutor-response { margin-top: 18px; padding: 12px; border-radius: 8px; background: var(--accent-softer); }
.tutor-response span { color: var(--accent-deep); font-size: 10px; font-weight: 750; }
.tutor-response p { margin-top: 5px; color: var(--text-secondary); font-size: 11px; line-height: 1.6; }
.context-foot { display: flex; align-items: center; gap: 6px; margin-top: 36px; padding-top: 14px; border-top: 1px solid var(--border-subtle); color: var(--text-tertiary); font-size: 10px; }
.progress-view, .sources-view { max-width: 1100px; }
.status-line, .source-count-line { display: flex; flex-wrap: wrap; gap: 15px; margin-top: 23px; padding: 13px 0; border-block: 1px solid var(--border-subtle); color: var(--text-secondary); font-size: 11px; }
.status-line span, .source-count-line span { display: inline-flex; align-items: center; gap: 6px; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--text-tertiary); }
.status-dot.mastered { background: var(--success); }.status-dot.progressing { background: #4e9fca; }.status-dot.learning { background: var(--warning); }.status-dot.weak { background: var(--danger); }.status-dot.unknown { background: #9ca2ad; }
.progress-layout { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(280px, .8fr); gap: 36px; margin-top: 24px; align-items: start; }
.objective-table { display: grid; border-top: 1px solid var(--border-subtle); }
.objective-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 13px; min-height: 76px; padding: 10px 4px; border-bottom: 1px solid var(--border-subtle); text-align: left; transition: background var(--duration-fast) var(--ease-standard), padding var(--duration-fast) var(--ease-standard); }
.objective-row:hover, .objective-row.selected { padding-inline: 10px; background: var(--accent-softer); }
.status-chip { min-width: 51px; padding: 4px 6px; border-radius: 5px; color: var(--text-secondary); background: var(--surface-tertiary); font-size: 10px; text-align: center; }
.status-chip.mastered { color: var(--success); background: var(--success-soft); }.status-chip.weak { color: var(--danger); background: var(--danger-soft); }.status-chip.learning { color: var(--warning); background: var(--warning-soft); }.status-chip.progressing { color: #28739c; background: rgba(40, 115, 156, .1); }
.objective-row-copy { min-width: 0; display: grid; gap: 5px; }.objective-row-copy strong { overflow: hidden; color: var(--text-primary); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.objective-row-copy small { color: var(--text-tertiary); font-size: 10px; }
.objective-values { display: grid; justify-items: end; gap: 3px; }.objective-values b { color: var(--accent-deep); font-size: 16px; }.objective-values small { color: var(--text-tertiary); font-size: 10px; }
.objective-detail { display: grid; gap: 13px; padding-left: 25px; border-left: 1px solid var(--border-subtle); }.objective-detail h3 { font-size: 19px; line-height: 1.4; }.objective-detail > p { color: var(--text-secondary); font-size: 12px; line-height: 1.65; }.detail-metrics { display: flex; gap: 28px; padding-block: 13px; border-block: 1px solid var(--border-subtle); }.detail-metrics div { display: grid; gap: 3px; }.detail-metrics span { color: var(--text-tertiary); font-size: 10px; }.detail-metrics strong { color: var(--accent-deep); font-size: 22px; }.objective-detail section { display: grid; gap: 7px; }.objective-detail section > strong { font-size: 12px; }.objective-detail article { padding: 9px 10px; background: var(--surface-secondary); }.objective-detail article span { color: var(--accent-deep); font-size: 10px; }.objective-detail article p, .objective-detail section > p { margin-top: 3px; color: var(--text-secondary); font-size: 11px; line-height: 1.55; }.objective-detail section > small { color: var(--text-tertiary); font-size: 11px; }
.inline-loading, .inline-empty { padding: 30px 0; color: var(--text-tertiary); font-size: 12px; text-align: center; }
.source-count-line { gap: 22px; }.source-count-line span { color: var(--text-secondary); }.sources-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(330px, .85fr); gap: 36px; margin-top: 26px; align-items: start; }.sources-layout section { min-width: 0; }.sources-layout section > header { padding-bottom: 14px; border-bottom: 1px solid var(--border-subtle); }.sources-layout section > header > span { color: var(--text-tertiary); font-size: 10px; }
.materials-source :deep(.materials-workspace) { margin-top: 15px; }.question-form { display: grid; gap: 11px; margin-top: 15px; padding-bottom: 20px; border-bottom: 1px solid var(--border-subtle); }.question-form label { display: grid; gap: 5px; }.question-form label > span { color: var(--text-secondary); font-size: 10px; font-weight: 650; }.question-form textarea, .question-form select { background: var(--surface-secondary); }.question-form select { width: 100%; height: 38px; padding: 0 9px; border: 1px solid var(--border-strong); border-radius: 8px; font-size: 12px; }.question-form-grid { display: grid; grid-template-columns: minmax(0, 1fr) 120px; gap: 9px; }.question-form .action-button { justify-self: start; min-height: 37px; }.question-list { display: grid; }.question-list article { display: grid; gap: 6px; padding: 13px 0; border-bottom: 1px solid var(--border-subtle); }.question-list article > div { display: flex; gap: 8px; color: var(--text-tertiary); font-size: 10px; }.question-type { color: var(--accent-deep); }.question-list article strong { color: var(--text-primary); font-size: 12px; line-height: 1.55; }.question-list article p { color: var(--text-tertiary); font-size: 10px; }
@media (max-width: 900px) { .progress-layout, .sources-layout { grid-template-columns: 1fr; gap: 30px; }.objective-detail { padding: 22px 0 0; border-top: 1px solid var(--border-subtle); border-left: 0; }.sources-layout { gap: 42px; } }
@media (max-width: 620px) { .adaptive-tutor { padding: 22px 14px 46px; }.adaptive-header { flex-direction: column; gap: 15px; }.adaptive-header-meta { justify-content: flex-start; }.adaptive-nav { gap: 15px; overflow-x: auto; }.adaptive-nav button { white-space: nowrap; }.action-surface { padding: 22px 18px; }.action-start-row, .answer-actions, .diagnostic-strip { align-items: stretch; flex-direction: column; }.action-button, .quiet-button { align-self: flex-start; }.evidence-result { grid-template-columns: 30px minmax(0, 1fr); }.evidence-result > small { grid-column: 1 / -1; }.objective-row { grid-template-columns: auto minmax(0, 1fr); }.objective-values { grid-column: 2; justify-items: start; display: flex; align-items: baseline; gap: 7px; }.question-form-grid { grid-template-columns: 1fr; } }
.choice-list { display: grid; gap: 8px; margin-top: 16px; }
.choice-option { display: flex; align-items: center; gap: 9px; padding: 11px 12px; border: 1px solid var(--border-subtle); border-radius: 9px; color: var(--text-secondary); background: var(--surface-secondary); font-size: 13px; }
.choice-option:has(input:checked) { border-color: var(--border-accent); color: var(--accent-deep); background: var(--accent-softer); }
.choice-option input { accent-color: var(--accent); }
.tutor-learning-surface { display: grid; gap: 14px; margin-top: 25px; }
.tutor-live-response { display: grid; gap: 7px; padding: 15px; border: 1px solid var(--border-accent); border-radius: 12px; background: var(--accent-softer); }
.tutor-live-response strong { color: var(--accent-deep); font-size: 12px; }
.tutor-live-response p { color: var(--text-primary); font-size: 14px; line-height: 1.75; white-space: pre-wrap; }
.tutor-live-response small { color: var(--text-tertiary); font-size: 10px; line-height: 1.5; }
.tutor-check-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.tutor-check-form { display: grid; gap: 9px; padding: 15px; border: 1px solid rgba(169, 101, 0, .22); border-radius: 12px; background: var(--warning-soft); }
.tutor-check-form > span { color: var(--warning); font-size: 10px; font-weight: 700; }
.tutor-check-form strong { color: var(--text-primary); font-size: 13px; line-height: 1.6; }
.tutor-check-form textarea { width: 100%; padding: 11px; border: 1px solid var(--border-strong); border-radius: 8px; background: var(--surface-primary); font-size: 13px; line-height: 1.6; resize: vertical; }
.question-import-form { display: grid; gap: 8px; margin-top: 15px; padding: 14px; border: 1px dashed var(--border-strong); border-radius: 12px; background: var(--surface-secondary); }
.question-import-form label { display: grid; gap: 6px; color: var(--text-secondary); font-size: 11px; font-weight: 650; }
.question-import-form input[type='file'] { width: 100%; font-size: 11px; }
.question-import-form small { color: var(--text-tertiary); font-size: 10px; line-height: 1.5; }
.question-import-form .secondary-button { justify-self: start; min-height: 35px; }
.import-preview { display: grid; gap: 9px; margin-top: 12px; padding: 13px; border: 1px solid var(--border-accent); border-radius: 12px; background: var(--accent-softer); }
.import-summary { display: flex; flex-wrap: wrap; gap: 7px 11px; align-items: center; color: var(--text-tertiary); font-size: 10px; }
.import-summary strong { width: 100%; color: var(--accent-deep); font-size: 12px; }
.import-item { display: grid; gap: 4px; padding: 8px 9px; border-radius: 8px; background: var(--surface-primary); }
.import-item strong { color: var(--text-primary); font-size: 11px; line-height: 1.5; }
.import-item small { color: var(--text-tertiary); font-size: 10px; }
.manual-tag { display: flex; gap: 7px; align-items: center; }
.manual-tag select { min-height: 32px; flex: 1; padding: 0 8px; border: 1px solid var(--border-strong); border-radius: 7px; background: var(--surface-primary); font-size: 11px; }
.manual-tag .secondary-button { min-height: 32px; padding-inline: 10px; font-size: 11px; }
.confidence-explanation { padding: 10px 11px; border-radius: 8px; color: var(--text-secondary); background: var(--surface-secondary); font-size: 11px; line-height: 1.6; }
</style>
