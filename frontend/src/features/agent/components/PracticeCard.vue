<script setup>
import { computed, reactive, ref } from 'vue'
import { CheckCircle2 } from 'lucide-vue-next'
import { submitPractice } from '../../../api/learning'
import { showToast } from '../../../components/common/toast'


const props = defineProps({ practice: { type: Object, required: true } })
const emit = defineEmits(['completed'])
const answers = reactive({})
const submitting = ref(false)
const result = ref(props.practice?.result || null)

const questions = computed(() => props.practice?.questions || [])
const answered = computed(() => questions.value.filter(question => String(answers[question.id] || '').trim()).length)
const ready = computed(() => questions.value.length > 0 && answered.value === questions.value.length)

async function submit() {
  if (!ready.value || submitting.value) return
  submitting.value = true
  const response = await submitPractice(
    props.practice.id,
    questions.value.map(question => ({ question_id: question.id, user_answer: answers[question.id].trim() }))
  )
  submitting.value = false
  if (response.code === 200) {
    result.value = response.data
    emit('completed', response.data)
  } else {
    showToast({ type: 'error', message: response.message })
  }
}
</script>

<template>
  <section class="practice-card">
    <header>
      <span>{{ practice.title }}</span>
      <strong v-if="!result">{{ answered }} / {{ questions.length }}</strong>
      <strong v-else>{{ result.evaluation.score }} 分</strong>
    </header>
    <div v-if="!result" class="practice-questions">
      <label v-for="(question, index) in questions" :key="question.id">
        <span>{{ index + 1 }}. {{ question.question }}</span>
        <textarea v-model="answers[question.id]" rows="2" maxlength="3000" placeholder="写下你的答案"></textarea>
      </label>
      <button class="submit-practice" type="button" :disabled="!ready || submitting" @click="submit">
        {{ submitting ? '正在批改' : '提交并更新掌握度' }}
      </button>
    </div>
    <div v-else class="practice-result">
      <CheckCircle2 :size="20" />
      <div>
        <strong>{{ result.evaluation.summary || '练习已完成' }}</strong>
        <p>{{ result.mastery_changes.length }} 个知识点已更新，{{ result.adaptations.length }} 项后续计划已重新安排。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.practice-card { margin-top: 10px; overflow: hidden; border: 1px solid #cfd9d4; border-radius: 7px; background: #fff; }
.practice-card > header { min-height: 38px; display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 7px 10px; border-bottom: 1px solid #e0e5e2; background: #f2f6f3; }
.practice-card > header span { color: #3c4943; font-size: 11px; font-weight: 760; }
.practice-card > header strong { color: #176b58; font-size: 11px; }
.practice-questions { display: grid; gap: 10px; padding: 10px; }
.practice-questions label { display: grid; gap: 5px; }
.practice-questions label > span { color: #36413c; font-size: 11px; line-height: 1.55; }
.practice-questions textarea { width: 100%; resize: vertical; padding: 7px 8px; border: 1px solid #cdd5d0; border-radius: 5px; background: #fbfcfb; font-size: 11px; line-height: 1.5; }
.practice-questions textarea:focus { border-color: #27806a; box-shadow: 0 0 0 2px rgba(39, 128, 106, .1); }
.submit-practice { min-height: 34px; justify-self: end; padding: 0 11px; border-radius: 5px; color: #fff; background: #176b58; font-size: 11px; font-weight: 750; }
.submit-practice:disabled { opacity: .45; }
.practice-result { display: grid; grid-template-columns: 24px minmax(0, 1fr); gap: 8px; padding: 12px; color: #19705a; }
.practice-result strong { color: #30403a; font-size: 12px; }
.practice-result p { margin-top: 2px; color: #6b7771; font-size: 10px; }
</style>
