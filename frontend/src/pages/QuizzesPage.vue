<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  getQuizzes,
  generateQuiz,
  getQuiz,
  getEvaluations,
  submitEvaluation,
  getEvaluation
} from '../api/quizzes'
import { showToast } from '../components/common/toast'
import EmptyState from '../components/common/EmptyState.vue'
import LoadingState from '../components/common/LoadingState.vue'
import { BarChart3, ClipboardList, PencilLine } from 'lucide-vue-next'

const route = useRoute()

const quizzes = ref([])
const total = ref(0)
const loading = ref(false)

const form = ref({ course_name: '', topic: '' })
const generating = ref(false)

const selectedId = ref(null)
const quizDetail = ref(null)
const detailLoading = ref(false)

const activeTab = ref('questions')

const evalAnswers = ref({})
const submittingEval = ref(false)

const evaluations = ref([])
const evalsLoading = ref(false)
const currentEval = ref(null)

onMounted(async () => {
  await loadQuizzes()
  selectQuizFromRoute()
})

watch(
  () => [route.query.quiz_set_id, route.query.tab],
  () => {
    selectQuizFromRoute()
  }
)

function selectQuizFromRoute() {
  const id = Number(route.query.quiz_set_id)
  if (id) {
    selectQuiz(id, route.query.tab === 'submit' ? 'submit' : 'questions')
  }
}

async function loadQuizzes() {
  loading.value = true
  const res = await getQuizzes({ page: 1, size: 50 })
  loading.value = false
  if (res.code === 200) {
    quizzes.value = res.data?.list || res.data?.items || res.data || []
    total.value = res.data?.total || quizzes.value.length
  }
}

async function handleGenerate() {
  if (!form.value.course_name || !form.value.topic) {
    showToast({ type: 'warning', message: '请填写课程名和主题' })
    return
  }

  generating.value = true
  const res = await generateQuiz({
    course_name: form.value.course_name,
    topic: form.value.topic
  })
  generating.value = false

  if (res.code === 200 || res.code === 201) {
    showToast({ type: 'success', message: '题集生成成功' })
    form.value = { course_name: '', topic: '' }
    await loadQuizzes()
    if (res.data?.quiz_set_id || res.data?.id) {
      selectQuiz(res.data.quiz_set_id || res.data.id)
    }
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

async function selectQuiz(id, nextTab = 'questions') {
  selectedId.value = id
  activeTab.value = nextTab
  detailLoading.value = true
  const res = await getQuiz(id)
  detailLoading.value = false
  if (res.code === 200) {
    quizDetail.value = res.data
    evalAnswers.value = {}
  }
}

async function loadEvaluations() {
  if (!selectedId.value) return
  evalsLoading.value = true
  const res = await getEvaluations({ quiz_set_id: selectedId.value })
  evalsLoading.value = false
  if (res.code === 200) {
    const all = res.data?.list || res.data?.items || res.data || []
    evaluations.value = all.filter(e => Number(e.quiz_set_id) === Number(selectedId.value))
  }
}

async function handleSubmitEvaluation() {
  if (!quizDetail.value) return

  const questions = quizDetail.value.questions || []
  const answers = []

  questions.forEach((q, i) => {
    const userAnswer = evalAnswers.value[i] || ''
    if (userAnswer.trim()) {
      answers.push({
        question_id: q.question_id || q.id || i,
        user_answer: userAnswer.trim()
      })
    }
  })

  if (!answers.length) {
    showToast({ type: 'warning', message: '至少填写一道题答案' })
    return
  }

  submittingEval.value = true
  const res = await submitEvaluation({
    quiz_set_id: selectedId.value,
    answers
  })
  submittingEval.value = false

  if (res.code === 200 || res.code === 201) {
    showToast({ type: 'success', message: '评估提交成功' })
    currentEval.value = res.data
    loadEvaluations()
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

async function viewEvaluation(id) {
  const res = await getEvaluation(id)
  if (res.code === 200) {
    currentEval.value = res.data
    activeTab.value = 'submit'
  }
}

function formatDate(val) {
  if (!val) return ''
  return new Date(val).toLocaleDateString('zh-CN')
}
</script>

<template>
  <div class="quizzes-page">
    <div class="page-header">
      <h1>练习题与评估</h1>
      <span class="badge badge-primary">共 {{ total }} 套题集</span>
    </div>

    <div class="quizzes-generator">
      <div class="card">
        <div class="card-header">
          <h3>生成题集</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label class="form-label">课程名 *</label>
            <input v-model="form.course_name" class="form-input" placeholder="如：高等数学" />
          </div>
          <div class="form-group">
            <label class="form-label">主题 *</label>
            <input v-model="form.topic" class="form-input" placeholder="如：导数" />
          </div>
        </div>
        <div class="card-footer">
          <button class="btn btn-primary" :disabled="generating" @click="handleGenerate">
            {{ generating ? '生成中...' : '生成' }}
          </button>
        </div>
      </div>
    </div>

    <div class="quizzes-list">
      <div class="card">
        <div class="card-header">
          <h3>题集列表</h3>
          <button class="btn btn-ghost btn-sm" @click="loadQuizzes">刷新</button>
        </div>
        <div class="card-body quiz-list-body">
          <LoadingState v-if="loading" />
          <EmptyState v-else-if="quizzes.length === 0" :icon="PencilLine" title="暂无题集" desc="生成后会显示在这里" />
          <div v-else>
            <div
              v-for="q in quizzes"
              :key="q.quiz_set_id || q.id"
              class="quiz-item"
              :class="{ active: selectedId === (q.quiz_set_id || q.id) }"
              @click="selectQuiz(q.quiz_set_id || q.id)"
            >
              <div class="quiz-item-title">{{ q.title || q.course_name }}</div>
              <div class="quiz-item-meta">
                {{ q.course_name }} · {{ q.topic || '未标注主题' }} · {{ formatDate(q.created_at) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="quizzes-detail">
      <div class="card">
        <div class="card-header">
          <h3>题集详情</h3>
        </div>

        <LoadingState v-if="detailLoading" />
        <EmptyState v-else-if="!quizDetail" :icon="ClipboardList" title="选择题集查看详情" />

        <template v-else>
          <div class="tabs quiz-tabs">
            <button
              class="tab"
              :class="{ active: activeTab === 'questions' }"
              @click="activeTab = 'questions'"
            >题目</button>
            <button
              class="tab"
              :class="{ active: activeTab === 'submit' }"
              @click="activeTab = 'submit'"
            >提交评估</button>
            <button
              class="tab"
              :class="{ active: activeTab === 'history' }"
              @click="activeTab = 'history'; loadEvaluations()"
            >历史评估</button>
          </div>

          <div class="card-body quiz-detail-body">
            <div v-if="activeTab === 'questions'">
              <div
                v-for="(q, i) in quizDetail.questions"
                :key="i"
                class="question-item"
              >
                <div class="question-number">第 {{ i + 1 }} 题</div>
                <div class="question-text">{{ q.question || q.content || q.text }}</div>
                <ul v-if="q.options" class="question-options">
                  <li
                    v-for="(opt, j) in q.options"
                    :key="j"
                    class="question-option"
                  >
                    <span class="question-option-marker">{{ String.fromCharCode(65 + j) }}</span>
                    <span>{{ typeof opt === 'string' ? opt : opt.text || opt.content }}</span>
                  </li>
                </ul>
              </div>
            </div>

            <div v-if="activeTab === 'submit'">
              <div
                v-for="(q, i) in quizDetail.questions"
                :key="i"
                class="form-group"
              >
                <label class="form-label">第 {{ i + 1 }} 题：{{ (q.question || q.content || '').substring(0, 60) }}...</label>
                <input
                  v-model="evalAnswers[i]"
                  class="form-input"
                  placeholder="输入你的答案"
                />
              </div>
              <button
                class="btn btn-primary"
                :disabled="submittingEval"
                @click="handleSubmitEvaluation"
              >
                {{ submittingEval ? '提交中...' : '提交评估' }}
              </button>

              <div v-if="currentEval" class="eval-result-wrap">
                <h4 class="eval-result-title">评估结果</h4>
                <div class="eval-result">
                  <div class="eval-score-row">
                    <div class="eval-score">
                      <span class="eval-score-value">{{ currentEval.score || 0 }}</span>
                      <span class="eval-score-label">得分</span>
                    </div>
                    <div class="eval-level">
                      <span class="badge" :class="currentEval.score >= 80 ? 'badge-success' : currentEval.score >= 60 ? 'badge-warning' : 'badge-accent'">
                        {{ currentEval.level || '未知' }}
                      </span>
                    </div>
                  </div>

                  <div v-if="currentEval.summary" class="eval-section">
                    <h4>总结</h4>
                    <p>{{ currentEval.summary }}</p>
                  </div>

                  <div v-if="currentEval.weak_points?.length" class="eval-section">
                    <h4>薄弱环节</h4>
                    <ul>
                      <li v-for="(point, i) in currentEval.weak_points" :key="i">{{ point }}</li>
                    </ul>
                  </div>

                  <div v-if="currentEval.suggestions?.length" class="eval-section">
                    <h4>改进建议</h4>
                    <ul>
                      <li v-for="(sug, i) in currentEval.suggestions" :key="i">{{ sug }}</li>
                    </ul>
                  </div>

                  <div v-if="currentEval.question_reviews?.length" class="eval-section">
                    <h4>题目详情</h4>
                    <div v-for="(review, i) in currentEval.question_reviews" :key="i" class="eval-review-item">
                      <div class="eval-review-header">
                        <span>第 {{ i + 1 }} 题</span>
                        <span class="badge" :class="review.score >= 80 ? 'badge-success' : review.score >= 60 ? 'badge-warning' : 'badge-accent'">
                          {{ review.score }} 分
                        </span>
                      </div>
                      <div class="eval-review-content">
                        <p><strong>题目：</strong>{{ review.question }}</p>
                        <p><strong>参考答案：</strong>{{ review.reference_answer }}</p>
                        <p><strong>你的答案：</strong>{{ review.user_answer }}</p>
                        <p><strong>反馈：</strong>{{ review.feedback }}</p>
                        <p v-if="review.weak_point"><strong>薄弱点：</strong>{{ review.weak_point }}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="activeTab === 'history'">
              <LoadingState v-if="evalsLoading" />
              <EmptyState v-else-if="evaluations.length === 0" :icon="BarChart3" title="暂无评估记录" />
              <div v-else>
                <div
                  v-for="e in evaluations"
                  :key="e.evaluation_id || e.id"
                  class="resource-item"
                  @click="viewEvaluation(e.evaluation_id || e.id)"
                >
                  <div class="resource-item-title">
                    评估 {{ formatDate(e.created_at) }}
                    <span v-if="e.score !== undefined" class="badge badge-primary eval-history-score">{{ e.score }} 分</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quiz-list-body,
.quiz-detail-body {
  max-height: 600px;
  overflow-y: auto;
}

.quiz-detail-body {
  max-height: 520px;
}

.quiz-tabs {
  padding: 0 1.25rem;
}

.eval-result-wrap {
  margin-top: 1.5rem;
}

.eval-result-title {
  margin-bottom: 0.75rem;
}

.eval-history-score {
  margin-left: 0.5rem;
}

.eval-result {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: 1.5rem;
}

.eval-score-row {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-line);
}

.eval-score {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.eval-score-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--color-primary);
}

.eval-score-label {
  font-size: 0.875rem;
  color: var(--color-muted);
}

.eval-section {
  margin-bottom: 1.25rem;
}

.eval-section h4 {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-soft);
  margin-bottom: 0.5rem;
}

.eval-section p {
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--color-text-soft);
}

.eval-section ul {
  padding-left: 1.25rem;
  font-size: 0.875rem;
  color: var(--color-text-soft);
}

.eval-section li {
  margin-bottom: 0.375rem;
}

.eval-review-item {
  background-color: var(--color-surface-strong);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  margin-bottom: 0.75rem;
  overflow: hidden;
}

.eval-review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background-color: var(--color-surface);
  border-bottom: 1px solid var(--color-line);
  font-weight: 600;
  font-size: 0.875rem;
}

.eval-review-content {
  padding: 1rem;
  font-size: 0.875rem;
  line-height: 1.6;
}

.eval-review-content p {
  margin-bottom: 0.5rem;
}

.eval-review-content p:last-child {
  margin-bottom: 0;
}
</style>
