<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { CheckCircle2, ClipboardCheck, RefreshCw } from 'lucide-vue-next'
import {
  generateDiagnostic,
  getLatestDiagnostic,
  submitDiagnostic
} from '../../../api/learning'
import { showToast } from '../../../components/common/toast'


const props = defineProps({ courseId: { type: Number, required: true } })
const emit = defineEmits(['completed'])
const router = useRouter()
const diagnostic = ref(null)
const answers = ref({})
const loading = ref(false)
const generating = ref(false)
const submitting = ref(false)
const submission = ref(null)

function openTodayLearning() {
  router.push({ path: `/learn/${props.courseId}`, query: { panel: 'today' } })
}

const answered = computed(() => (diagnostic.value?.questions || []).filter(question =>
  String(answers.value[question.id] || '').trim()
).length)
const complete = computed(() => diagnostic.value?.questions?.length > 0 && answered.value === diagnostic.value.questions.length)

async function load() {
  loading.value = true
  submission.value = null
  const response = await getLatestDiagnostic(props.courseId)
  loading.value = false
  if (response.code >= 200 && response.code < 300) {
    diagnostic.value = response.data
    answers.value = {}
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

async function generate() {
  generating.value = true
  const response = await generateDiagnostic(props.courseId, 6)
  generating.value = false
  if (response.code >= 200 && response.code < 300) {
    diagnostic.value = response.data
    answers.value = {}
    showToast({ type: 'success', message: '已生成 6 道诊断题' })
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

async function submit() {
  if (!complete.value || submitting.value) return
  submitting.value = true
  const payload = diagnostic.value.questions.map(question => ({
    question_id: question.id,
    user_answer: answers.value[question.id].trim()
  }))
  const response = await submitDiagnostic(diagnostic.value.id, payload)
  submitting.value = false
  if (response.code === 200) {
    submission.value = response.data
    diagnostic.value = { ...diagnostic.value, submitted: true }
    emit('completed')
    showToast({ type: 'success', message: '诊断完成，每日计划已生成' })
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

watch(() => props.courseId, load, { immediate: true })
</script>

<template>
  <div class="diagnostic-workspace">
    <div v-if="loading" class="diagnostic-state">正在读取诊断状态</div>

    <section v-else-if="submission" class="diagnostic-complete">
      <CheckCircle2 :size="30" />
      <div>
        <h3>诊断完成，计划已建立</h3>
        <p>已评估 {{ submission.mastery_changes?.length || 0 }} 个知识点，并生成 {{ submission.plan?.days || 0 }} 天学习计划。</p>
      </div>
      <button type="button" @click="openTodayLearning">进入今日学习</button>
    </section>

    <section v-else-if="diagnostic?.submitted" class="diagnostic-complete">
      <CheckCircle2 :size="30" />
      <div>
        <h3>本课程已完成诊断</h3>
        <p>掌握度和每日计划已经建立，无需重复作答。</p>
      </div>
      <button type="button" @click="openTodayLearning">进入今日学习</button>
    </section>

    <section v-else-if="!diagnostic" class="diagnostic-empty">
      <ClipboardCheck :size="32" />
      <h3>用 6 道题建立起始掌握度</h3>
      <p>题目会覆盖至少 3 个已提取知识点，提交后自动生成每日计划。</p>
      <button type="button" :disabled="generating" @click="generate">
        {{ generating ? '正在生成' : '生成诊断题' }}
      </button>
    </section>

    <template v-else>
      <header class="diagnostic-heading">
        <div>
          <span>入门诊断 · {{ diagnostic.questions.length }} 题</span>
          <h3>{{ diagnostic.title }}</h3>
        </div>
        <button class="icon-button" type="button" title="重新加载" aria-label="重新加载诊断" @click="load">
          <RefreshCw :size="16" />
        </button>
      </header>

      <ol class="question-list">
        <li v-for="(question, index) in diagnostic.questions" :key="question.id">
          <div class="question-number">{{ index + 1 }}</div>
          <div class="question-content">
            <span>知识点 #{{ question.knowledge_point_id }} · {{ question.difficulty }}</span>
            <p>{{ question.question }}</p>
            <textarea
              v-model="answers[question.id]"
              rows="3"
              maxlength="3000"
              placeholder="用自己的话回答即可"
            ></textarea>
          </div>
        </li>
      </ol>

      <footer class="diagnostic-actions">
        <span>已回答 {{ answered }} / {{ diagnostic.questions.length }}</span>
        <button type="button" :disabled="!complete || submitting" @click="submit">
          {{ submitting ? '正在评估' : '提交诊断并生成计划' }}
        </button>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.diagnostic-workspace { min-height: 320px; }
.diagnostic-state,
.diagnostic-empty {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #74807a;
  text-align: center;
}
.diagnostic-empty svg { color: #22705c; }
.diagnostic-empty h3 { color: #26322c; font-size: 17px; font-weight: 750; }
.diagnostic-empty p { max-width: 460px; font-size: 12px; }
.diagnostic-empty button,
.diagnostic-complete button,
.diagnostic-actions button {
  min-height: 37px;
  padding: 0 14px;
  border-radius: 6px;
  color: #ffffff;
  background: #176b58;
  font-size: 12px;
  font-weight: 750;
}
button:disabled { opacity: .48; cursor: not-allowed; }
.diagnostic-complete {
  min-height: 180px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 14px;
  padding: 22px;
  border: 1px solid #cfe0d7;
  border-radius: 8px;
  background: #f1f8f4;
}
.diagnostic-complete svg { color: #176b58; }
.diagnostic-complete h3 { font-size: 16px; font-weight: 750; }
.diagnostic-complete p { margin-top: 4px; color: #66726c; font-size: 12px; }
.diagnostic-heading,
.diagnostic-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.diagnostic-heading { padding: 4px 0 15px; border-bottom: 1px solid #dde3df; }
.diagnostic-heading span { color: #17705b; font-size: 10px; font-weight: 750; }
.diagnostic-heading h3 { margin-top: 3px; font-size: 16px; font-weight: 750; }
.icon-button { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 6px; color: #65716b; }
.icon-button:hover { background: #e9eeeb; color: #176b58; }
.question-list { padding: 0; list-style: none; }
.question-list li { display: grid; grid-template-columns: 34px 1fr; gap: 10px; margin: 0; padding: 18px 0; border-bottom: 1px solid #e1e6e3; }
.question-number { width: 27px; height: 27px; display: grid; place-items: center; border-radius: 6px; color: #176b58; background: #e2eee8; font-size: 11px; font-weight: 800; }
.question-content > span { color: #7b8580; font-size: 10px; }
.question-content p { margin: 5px 0 9px; color: #29352f; font-size: 13px; line-height: 1.55; }
.question-content textarea { width: 100%; resize: vertical; padding: 10px 11px; border: 1px solid #cdd5d0; border-radius: 6px; background: #fbfcfb; font-size: 12px; line-height: 1.5; }
.question-content textarea:focus { border-color: #27806a; box-shadow: 0 0 0 2px rgba(39,128,106,.11); }
.diagnostic-actions { min-height: 62px; padding-top: 12px; }
.diagnostic-actions span { color: #6f7a74; font-size: 11px; }
@media (max-width: 620px) {
  .diagnostic-complete { grid-template-columns: auto 1fr; }
  .diagnostic-complete button { grid-column: 1 / -1; width: 100%; }
  .question-list li { grid-template-columns: 27px 1fr; }
  .diagnostic-actions { align-items: stretch; flex-direction: column; }
}
</style>
