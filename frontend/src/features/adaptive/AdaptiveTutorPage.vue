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
  Gauge,
  Lightbulb,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  Upload
} from 'lucide-vue-next'
import {
  addAdaptiveQuestions,
  getAdaptiveOverview,
  getAdaptiveProgress,
  getAdaptiveSources,
  startAdaptiveAction,
  startAdaptiveDiagnostic,
  submitAdaptiveAction,
  submitAdaptiveDiagnostic
} from '../../api/adaptive'
import { showToast } from '../../components/common/toast'
import MaterialWorkspace from '../courses/components/MaterialWorkspace.vue'
import { useCourseStore } from '../../stores/course'


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
const tutorPrompt = ref('')
const diagnostic = ref(null)
const diagnosticAnswers = ref({})
const diagnosticSubmitting = ref(false)
const questionSubmitting = ref(false)
let overviewRequestSequence = 0
const questionForm = ref({
  content: '',
  answer: '',
  difficulty: 'medium',
  objective_id: '',
  source_type: 'user_upload'
})

const legacyViewMap = {
  today: 'learn',
  overview: 'progress',
  knowledge: 'progress',
  practice: 'learn',
  materials: 'sources',
  plan: 'learn',
  memory: 'learn'
}

const view = computed(() => {
  const requested = String(route.query.view || route.query.panel || 'learn')
  return ['learn', 'progress', 'sources'].includes(requested) ? requested : (legacyViewMap[requested] || 'learn')
})
const action = computed(() => overview.value?.next_action || null)
const objectives = computed(() => overview.value?.objectives || progress.value?.objectives || [])
const selectedObjective = computed(() => (
  progress.value?.objectives?.find(item => Number(item.id) === Number(selectedObjectiveId.value))
  || objectives.value.find(item => Number(item.id) === Number(selectedObjectiveId.value))
  || null
))
const curriculum = computed(() => overview.value?.curriculum || { status: 'pending', objective_count: 0 })
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
const curriculumLabel = {
  pending: '等待 Curriculum',
  ready: 'Curriculum 已就绪',
  degraded: 'Curriculum 需要复核',
  failed: 'Curriculum 构建失败'
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
  router.replace({ path: route.path, query: { ...route.query, view: nextView } })
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
    if (response.code !== 200) throw new Error(response.message || 'Student Model 读取失败')
    progress.value = response.data
    if (!selectedObjectiveId.value) selectedObjectiveId.value = response.data?.objectives?.[0]?.id || null
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || 'Student Model 读取失败' })
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
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '学习动作无法开始' })
  }
}

async function submitAction() {
  if (!action.value?.id || !actionAnswer.value.trim() || actionSubmitting.value) return
  actionSubmitting.value = true
  try {
    const response = await submitAdaptiveAction(action.value.id, { response: actionAnswer.value.trim() })
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

function askTutor(prompt) {
  tutorPrompt.value = prompt
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
      difficulty: form.difficulty,
      source_type: form.source_type,
      objective_ids: [Number(form.objective_id)],
      coverage_type: 'scenario'
    }])
    if (response.code !== 201) throw new Error(response.message || '题目添加失败')
    questionForm.value = { content: '', answer: '', difficulty: 'medium', objective_id: '', source_type: 'user_upload' }
    await Promise.all([loadSources(), loadOverview()])
    showToast({ type: 'success', message: '题目已加入题库，后续练习会优先检索它' })
  } catch (requestError) {
    showToast({ type: 'error', message: requestError.message || '题目添加失败' })
  } finally {
    questionSubmitting.value = false
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
        <span class="adaptive-kicker"><Sparkles :size="14" /> ADAPTIVE TUTOR</span>
        <h1>{{ course?.name || '课程学习' }}</h1>
        <p>每次学习都留下证据，系统据此决定下一步最值得完成的动作。</p>
      </div>
      <div class="adaptive-header-meta">
        <span class="curriculum-status" :class="curriculum.status">
          <ShieldCheck :size="14" /> {{ curriculumLabel[curriculum.status] || curriculum.status }}
        </span>
        <span v-if="course?.exam_at" class="exam-date">目标 {{ formatDate(course.exam_at) }}</span>
      </div>
    </header>

    <nav class="adaptive-nav" role="tablist" aria-label="课程学习区域">
      <button type="button" role="tab" :aria-selected="view === 'learn'" :class="{ active: view === 'learn' }" @click="setView('learn')">
        <Target :size="16" /> Learn <small>下一动作</small>
      </button>
      <button type="button" role="tab" :aria-selected="view === 'progress'" :class="{ active: view === 'progress' }" @click="setView('progress')">
        <Gauge :size="16" /> Progress <small>学生状态</small>
      </button>
      <button type="button" role="tab" :aria-selected="view === 'sources'" :class="{ active: view === 'sources' }" @click="setView('sources')">
        <BookOpenCheck :size="16" /> Sources <small>资料与题库</small>
      </button>
    </nav>

    <div v-if="loading" class="adaptive-state" role="status">正在读取课程证据与下一动作</div>
    <div v-else-if="error" class="adaptive-state error-state" role="alert">
      <CircleAlert :size="24" /><strong>{{ error }}</strong><button type="button" @click="loadOverview">重新读取</button>
    </div>
    <main v-else class="adaptive-main">
      <template v-if="view === 'learn'">
        <section class="learn-layout">
          <div class="learn-primary">
            <div class="section-intro">
              <span class="section-eyebrow">NEXT BEST LEARNING ACTION</span>
              <h2>下一步建议</h2>
              <p>策略先判断学什么，再根据你的状态决定怎么学。</p>
            </div>

            <article v-if="action" class="action-surface" :class="action.action_type">
              <div class="action-topline">
                <span class="action-type"><Lightbulb :size="15" /> {{ actionTypeLabel[action.action_type] || action.action_type }}</span>
                <span class="action-time">约 {{ action.expected_minutes }} 分钟</span>
              </div>
              <h3>{{ actionObjectiveTitle(action.objective_id) }}</h3>
              <p class="action-ability">{{ objectiveForAction(action.objective_id)?.required_ability || action.required_ability || '完成一次可验证的学习动作' }}</p>
              <div class="action-reason">
                <strong>为什么现在做</strong>
                <p>{{ action.reason }}</p>
              </div>

              <div v-if="!actionStarted" class="action-start-row">
                <span v-if="action.question">题库已找到匹配题，优先使用真实题目。</span>
                <span v-else>当前动作需要先完成讲解或自检；题库没有合适题时不会假装生成。</span>
                <button type="button" class="action-button" @click="beginAction">开始 <ArrowRight :size="16" /></button>
              </div>

              <form v-else class="action-answer" @submit.prevent="submitAction">
                <div v-if="action.question" class="question-block">
                  <span>题库练习 · {{ action.question.source_type }}</span>
                  <p>{{ action.question.content }}</p>
                </div>
                <div v-else class="explain-block">
                  <span>讲解后的自检</span>
                  <p>{{ objectiveForAction(action.objective_id)?.description || '用自己的话写下你现在的理解。' }}</p>
                </div>
                <label class="answer-field">
                  <span>{{ action.question ? '你的回答' : '用一句话写下你的理解' }}</span>
                  <textarea v-model="actionAnswer" rows="5" :placeholder="action.question ? '先写判断依据，再写结论……' : '我现在能够……'" autofocus></textarea>
                </label>
                <div class="answer-actions">
                  <span>提交后会形成 Learning Evidence，并重新计算下一步。</span>
                  <button type="submit" class="action-button" :disabled="actionSubmitting || !actionAnswer.trim()">
                    <Send :size="15" /> {{ actionSubmitting ? '正在评估' : '提交并更新状态' }}
                  </button>
                </div>
              </form>
            </article>

            <article v-else class="empty-action">
              <Check :size="26" /><h3>当前没有需要重复刷新的目标</h3><p>先上传课程资料并建立 Learning Objective，或者添加题库。</p><button type="button" @click="setView('sources')">去 Sources</button>
            </article>

            <article v-if="actionResult" class="evidence-result" aria-live="polite">
              <div class="result-mark"><Check :size="18" /></div>
              <div><span>刚刚写入 Evidence</span><strong>{{ masteryPercent(actionResult.state.mastery) }} 掌握度 · {{ masteryPercent(actionResult.state.confidence) }} 置信度</strong><p>{{ actionResult.feedback }}</p></div>
              <small>{{ actionResult.update_reason }}</small>
            </article>

            <section class="diagnostic-strip">
              <div><span class="section-eyebrow">INITIAL DIAGNOSIS</span><h3>还没有足够的学习证据？</h3><p>用少量题目覆盖高重要度目标和关键前置关系，先建立初始 Student Model。</p></div>
              <button type="button" class="quiet-button" @click="beginDiagnostic"><RefreshCw :size="15" /> 开始快速诊断</button>
            </section>

            <section v-if="diagnostic" class="diagnostic-surface">
              <header><div><span class="section-eyebrow">DIAGNOSTIC</span><h3>{{ diagnostic.complete ? '诊断已完成' : '用最少题目建立初始状态' }}</h3></div><button type="button" @click="diagnostic = null">关闭</button></header>
              <div v-if="diagnostic.complete" class="diagnostic-complete"><Check :size="19" /><p>诊断证据已写入 Student Model，下一动作已经重新计算。</p></div>
              <form v-else @submit.prevent="submitDiagnostic">
                <article v-for="(question, index) in diagnostic.questions" :key="question.id" class="diagnostic-question">
                  <span>0{{ index + 1 }} · {{ question.difficulty }}</span><p>{{ question.content }}</p><textarea v-model="diagnosticAnswers[question.id]" rows="3" placeholder="写出你的判断依据……"></textarea>
                </article>
                <button type="submit" class="action-button" :disabled="diagnosticSubmitting">{{ diagnosticSubmitting ? '正在建立状态' : '提交诊断' }}</button>
              </form>
              <p v-if="!diagnostic.questions?.length" class="inline-empty">题库中还没有关联 Objective 的题目，请先去 Sources 添加。</p>
            </section>
          </div>

          <aside class="tutor-context">
            <div class="context-heading"><CircleHelp :size="17" /><span>Tutor 辅助</span></div>
            <p>Tutor 负责解释和提问，不直接修改掌握度。状态只由下面的学习证据更新。</p>
            <div class="context-objective" v-if="action">
              <span>当前目标</span><strong>{{ actionObjectiveTitle(action.objective_id) }}</strong><p>{{ objectiveForAction(action.objective_id)?.description || '等待课程目标详情' }}</p>
            </div>
            <div class="tutor-prompts">
              <button type="button" @click="askTutor('换一个更具体的例子')">换一个例子 <ArrowRight :size="14" /></button>
              <button type="button" @click="askTutor('把判断步骤拆开')">拆开判断步骤 <ArrowRight :size="14" /></button>
              <button type="button" @click="askTutor('告诉我这道题在检查什么')">解释这题在检查什么 <ArrowRight :size="14" /></button>
            </div>
            <div v-if="tutorPrompt" class="tutor-response"><span>教学提示</span><p>{{ tutorPrompt }}：先看目标要求的动作，再从资料证据里找判断条件，最后用一个新场景自检。</p></div>
            <div class="context-foot"><FileText :size="14" /><span>{{ curriculum.objective_count || 0 }} 个目标 · {{ overview?.counts?.evidence_count || 0 }} 条 Evidence</span></div>
          </aside>
        </section>
      </template>

      <template v-else-if="view === 'progress'">
        <section class="progress-view">
          <div class="section-intro"><span class="section-eyebrow">STUDENT MODEL</span><h2>Progress</h2><p>掌握度回答“现在表现如何”，置信度回答“证据够不够”。两者故意分开。</p></div>
          <div class="status-line" aria-label="Student Model 状态统计">
            <span><i class="status-dot mastered"></i>已掌握 {{ progress?.status_counts?.mastered || 0 }}</span>
            <span><i class="status-dot progressing"></i>进展中 {{ progress?.status_counts?.progressing || 0 }}</span>
            <span><i class="status-dot learning"></i>学习中 {{ progress?.status_counts?.learning || 0 }}</span>
            <span><i class="status-dot weak"></i>薄弱 {{ progress?.status_counts?.weak || 0 }}</span>
            <span><i class="status-dot unknown"></i>未验证 {{ progress?.status_counts?.unknown || 0 }}</span>
          </div>
          <div v-if="viewLoading" class="inline-loading">正在读取 Student Model</div>
          <div v-else class="progress-layout">
            <div class="objective-table" aria-label="学习目标列表">
              <button v-for="objective in progress?.objectives || []" :key="objective.id" type="button" class="objective-row" :class="{ selected: Number(selectedObjectiveId) === Number(objective.id) }" @click="selectedObjectiveId = objective.id">
                <span class="status-chip" :class="objective.state">{{ stateLabel[objective.state] || objective.state }}</span>
                <span class="objective-row-copy"><strong>{{ objective.title }}</strong><small>{{ objective.attempt_count }} 次 Evidence · 最近 {{ formatDate(objective.last_practiced_at) }}</small></span>
                <span class="objective-values"><b>{{ masteryPercent(objective.mastery) }}</b><small>置信 {{ masteryPercent(objective.confidence) }}</small></span>
              </button>
              <div v-if="!progress?.objectives?.length" class="inline-empty">课程还没有 Learning Objective。请先在 Sources 处理资料。</div>
            </div>
            <aside v-if="selectedObjective" class="objective-detail">
              <span class="section-eyebrow">WHY THIS STATE</span><h3>{{ selectedObjective.title }}</h3><p>{{ selectedObjective.description }}</p>
              <div class="detail-metrics"><div><span>掌握度</span><strong>{{ masteryPercent(selectedObjective.mastery) }}</strong></div><div><span>置信度</span><strong>{{ masteryPercent(selectedObjective.confidence) }}</strong></div></div>
              <section><strong>最近 Evidence</strong><article v-for="item in selectedObjective.evidence || []" :key="item.id"><span>{{ item.source_type }} · {{ masteryPercent(item.score) }}</span><p>{{ item.update_reason || '已记录一次学习证据' }}</p></article><small v-if="!selectedObjective.evidence?.length">还没有可解释证据。</small></section>
              <section><strong>Misconceptions</strong><article v-for="item in selectedObjective.misconceptions || []" :key="item.id"><span>{{ item.code }} · {{ masteryPercent(item.confidence) }}</span><p>{{ item.description }}</p></article><small v-if="!selectedObjective.misconceptions?.length">当前没有 active misconception。</small></section>
              <section v-if="selectedObjective.prerequisites?.length"><strong>Prerequisites</strong><p v-for="relation in selectedObjective.prerequisites" :key="relation.id">{{ relation.source_title }} · prerequisite · {{ masteryPercent(relation.confidence) }}</p></section>
            </aside>
          </div>
        </section>
      </template>

      <template v-else>
        <section class="sources-view">
          <div class="section-intro"><span class="section-eyebrow">EVIDENCE SOURCES</span><h2>Sources</h2><p>课程资料负责提供证据，题库负责提供可评估的学习行为。生成题只在找不到合适真实题时兜底。</p></div>
          <div class="source-count-line"><span><FileText :size="15" /> {{ sources?.materials?.length || 0 }} 份资料</span><span><BookOpenCheck :size="15" /> {{ sources?.counts?.question_count || 0 }} 道题</span><span><CircleAlert :size="15" /> {{ sources?.counts?.unmatched_question_count || 0 }} 道未关联</span></div>
          <div v-if="viewLoading" class="inline-loading">正在读取 Sources</div>
          <div v-else class="sources-layout">
            <section class="materials-source"><header><div><span class="section-eyebrow">COURSE MATERIALS</span><h3>资料</h3></div><span>PDF · DOCX · Markdown · TXT</span></header><MaterialWorkspace :course-id="courseId" @processed="onMaterialProcessed" /></section>
            <section class="question-source"><header><div><span class="section-eyebrow">QUESTION BANK</span><h3>题库</h3></div><span>真实题目优先</span></header>
              <form class="question-form" @submit.prevent="addQuestion">
                <label><span>题目</span><textarea v-model="questionForm.content" rows="3" placeholder="给定一个场景，要求学生完成什么可验证判断？"></textarea></label>
                <label><span>参考答案</span><textarea v-model="questionForm.answer" rows="3" placeholder="明确答案或评分依据"></textarea></label>
                <div class="question-form-grid"><label><span>关联 Objective</span><select v-model="questionForm.objective_id" required><option value="" disabled>选择学习目标</option><option v-for="objective in objectives" :key="objective.id" :value="objective.id">{{ objective.title }}</option></select></label><label><span>难度</span><select v-model="questionForm.difficulty"><option value="easy">简单</option><option value="medium">中等</option><option value="hard">困难</option></select></label></div>
                <button type="submit" class="action-button" :disabled="questionSubmitting || !questionForm.objective_id"><Upload :size="15" /> {{ questionSubmitting ? '正在保存' : '添加到题库' }}</button>
              </form>
              <div class="question-list"><article v-for="question in sources?.questions || []" :key="question.id"><div><span class="question-type">{{ question.source_type }}</span><span>{{ question.difficulty }}</span></div><strong>{{ question.content }}</strong><p>{{ question.objective_titles || '尚未关联 Objective' }}</p></article><div v-if="!sources?.questions?.length" class="inline-empty">还没有题目。添加一题后，Learning Policy 会优先检索它。</div></div>
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
.learn-layout { display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 52px; align-items: start; }
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
.empty-action { min-height: 280px; display: grid; place-content: center; justify-items: center; gap: 11px; margin-top: 25px; border-block: 1px solid var(--border-subtle); color: var(--text-tertiary); text-align: center; }
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
.tutor-context { position: sticky; top: 28px; padding-top: 4px; }
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
@media (max-width: 900px) { .learn-layout, .progress-layout, .sources-layout { grid-template-columns: 1fr; gap: 30px; }.tutor-context { position: static; padding-top: 20px; border-top: 1px solid var(--border-subtle); }.objective-detail { padding: 22px 0 0; border-top: 1px solid var(--border-subtle); border-left: 0; }.sources-layout { gap: 42px; } }
@media (max-width: 620px) { .adaptive-tutor { padding: 22px 14px 46px; }.adaptive-header { flex-direction: column; gap: 15px; }.adaptive-header-meta { justify-content: flex-start; }.adaptive-nav { gap: 15px; overflow-x: auto; }.adaptive-nav button { white-space: nowrap; }.action-surface { padding: 22px 18px; }.action-start-row, .answer-actions, .diagnostic-strip { align-items: stretch; flex-direction: column; }.action-button, .quiet-button { align-self: flex-start; }.evidence-result { grid-template-columns: 30px minmax(0, 1fr); }.evidence-result > small { grid-column: 1 / -1; }.objective-row { grid-template-columns: auto minmax(0, 1fr); }.objective-values { grid-column: 2; justify-items: start; display: flex; align-items: baseline; gap: 7px; }.question-form-grid { grid-template-columns: 1fr; } }
</style>
