<script setup>
import { ref, watch } from 'vue'
import { CalendarDays, Check, Clock3, MessageSquareText } from 'lucide-vue-next'
import { getStudyPlan, rescheduleLearningSession } from '../../../api/learning'
import { showToast } from '../../../components/common/toast'


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
const emit = defineEmits(['change-panel', 'prompt', 'data-changed'])
const loading = ref(true)
const plan = ref(null)
const editingId = ref(null)
const scheduledDate = ref('')
const saving = ref(false)

function statusLabel(status) {
  return { planned: '待学习', in_progress: '进行中', completed: '已完成', evaluated: '已评估' }[status] || status
}

async function load() {
  loading.value = true
  const response = await getStudyPlan(props.courseId)
  plan.value = response.code === 200 ? response.data : null
  loading.value = false
}

function edit(session) {
  editingId.value = session.id
  scheduledDate.value = session.scheduled_date
}

async function save(session) {
  if (!scheduledDate.value || saving.value) return
  saving.value = true
  const response = await rescheduleLearningSession(session.id, { scheduled_date: scheduledDate.value })
  saving.value = false
  if (response.code === 200) {
    editingId.value = null
    await load()
    emit('data-changed')
    showToast({ type: 'success', message: '计划时间已调整' })
  } else showToast({ type: 'error', message: response.message })
}

watch(() => [props.courseId, props.refreshKey], load, { immediate: true })
</script>

<template>
  <div class="plan-panel">
    <div v-if="loading" class="panel-state">正在读取学习计划</div>
    <div v-else-if="!plan" class="panel-empty">
      <CalendarDays :size="28" /><strong>还没有学习计划</strong><p>完成课程诊断后会生成按天执行的计划。</p>
      <button type="button" @click="$emit('change-panel', 'diagnostic')">开始入门诊断</button>
    </div>
    <template v-else>
      <header class="plan-summary">
        <span>{{ plan.start_date }} 至 {{ plan.end_date }}</span>
        <strong>{{ plan.title }}</strong>
        <p>{{ plan.sessions.length }} 个学习单元</p>
      </header>
      <section class="session-list">
        <article v-for="session in plan.sessions" :key="session.id" :class="session.status">
          <span class="session-date">{{ session.scheduled_date }}</span>
          <div class="session-heading">
            <strong>{{ session.items?.[0]?.title || '学习单元' }}</strong>
            <span>{{ statusLabel(session.status) }}</span>
          </div>
          <p><Clock3 :size="12" /> {{ session.estimated_minutes }} 分钟 · {{ session.items?.length || 0 }} 项</p>
          <small v-if="session.adaptation_reason">{{ session.adaptation_reason }}</small>
          <div v-if="editingId === session.id" class="schedule-editor">
            <input v-model="scheduledDate" type="date" />
            <button type="button" title="保存时间" aria-label="保存时间" @click="save(session)"><Check :size="15" /></button>
          </div>
          <div v-else-if="!['completed', 'evaluated'].includes(session.status)" class="session-actions">
            <button type="button" @click="edit(session)">调整日期</button>
            <button type="button" title="开始今日学习" aria-label="开始今日学习" @click="$emit('change-panel', 'today')"><MessageSquareText :size="14" /></button>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.plan-panel { display: grid; gap: 16px; }
.panel-state,
.panel-empty { min-height: 260px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #78827d; text-align: center; }
.panel-state { font-size: 12px; }
.panel-empty svg { color: #27715d; }
.panel-empty strong { color: #35413b; font-size: 13px; }
.panel-empty p { font-size: 11px; }
.panel-empty button { min-height: 34px; margin-top: 5px; padding: 0 10px; border-radius: 5px; color: #fff; background: #176b58; font-size: 10px; }
.plan-summary { display: grid; gap: 3px; padding-bottom: 13px; border-bottom: 1px solid #dfe4e1; }
.plan-summary span { color: #19705a; font-size: 10px; font-weight: 740; }
.plan-summary strong { color: #303c36; font-size: 14px; }
.plan-summary p { color: #7a847f; font-size: 10px; }
.session-list { display: grid; }
.session-list article { display: grid; gap: 5px; padding: 12px 0 12px 13px; border-bottom: 1px solid #e1e5e2; border-left: 2px solid #c5cec9; }
.session-list article.in_progress { border-left-color: #d0922d; }
.session-list article.completed,
.session-list article.evaluated { border-left-color: #27805f; opacity: .72; }
.session-date { color: #7a847f; font-size: 10px; }
.session-heading { display: flex; align-items: center; justify-content: space-between; gap: 9px; }
.session-heading strong { color: #34413a; font-size: 12px; }
.session-heading span { flex: 0 0 auto; padding: 2px 5px; border-radius: 4px; color: #5e6963; background: #edf1ee; font-size: 9px; }
.session-list article > p { display: flex; align-items: center; gap: 4px; color: #75807a; font-size: 10px; }
.session-list small { color: #8a6a2e; font-size: 9px; line-height: 1.45; }
.session-actions { display: flex; justify-content: flex-end; gap: 5px; }
.session-actions button { min-height: 29px; padding: 0 8px; border-radius: 5px; color: #176b58; font-size: 10px; }
.session-actions button:hover { background: #e7efeb; }
.schedule-editor { display: grid; grid-template-columns: minmax(0, 1fr) 32px; gap: 5px; }
.schedule-editor input { min-width: 0; height: 34px; padding: 0 7px; border: 1px solid #cbd4cf; border-radius: 5px; font-size: 11px; }
.schedule-editor button { display: grid; place-items: center; border-radius: 5px; color: #fff; background: #176b58; }
</style>
