<script setup>
import { computed, ref, watch } from 'vue'
import {
  CalendarDays,
  Check,
  ChevronDown,
  Clock3,
  Link2,
  MessageSquareText,
  RefreshCw,
  Route
} from 'lucide-vue-next'
import {
  getLearningRoadmap,
  getStudyPlan,
  rescheduleLearningSession,
  retryLearningRoadmap
} from '../../../api/learning'
import { showToast } from '../../../components/common/toast'
import { calculateRoadmapProgress } from '../roadmapProgress'


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
const emit = defineEmits(['change-panel', 'prompt', 'data-changed'])
const loading = ref(true)
const plan = ref(null)
const roadmap = ref(null)
const error = ref('')
const editingId = ref(null)
const scheduledDate = ref('')
const saving = ref(false)
const retrying = ref(false)

const overallProgress = computed(() => {
  return calculateRoadmapProgress(roadmap.value)
})

function statusLabel(status) {
  return {
    pending: '待开始', generating: '生成中', ready: '已就绪', failed: '生成失败',
    active: '当前阶段', planned: '待学习', in_progress: '进行中', completed: '已完成', evaluated: '已评估'
  }[status] || status
}

async function load() {
  loading.value = true
  error.value = ''
  const [roadmapResponse, planResponse] = await Promise.all([
    getLearningRoadmap(props.courseId),
    getStudyPlan(props.courseId)
  ])
  roadmap.value = roadmapResponse.code === 200 ? roadmapResponse.data : null
  plan.value = planResponse.code === 200 ? planResponse.data : null
  if (roadmapResponse.code !== 200) error.value = roadmapResponse.message || '长期路线读取失败'
  loading.value = false
}

async function retryRoadmap() {
  if (retrying.value) return
  retrying.value = true
  const response = await retryLearningRoadmap(props.courseId)
  retrying.value = false
  if (response.code === 200) {
    roadmap.value = response.data
    error.value = ''
    emit('data-changed')
    showToast({ type: 'success', message: '长期学习路线已重新生成' })
  } else showToast({ type: 'error', message: response.message })
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
    <div v-if="loading" class="panel-state">正在读取长期路线与每日计划</div>
    <div v-else-if="error && !roadmap" class="panel-empty">
      <Route :size="28" />
      <strong>长期路线读取失败</strong>
      <p>{{ error }}</p>
      <button type="button" @click="load">重新读取</button>
    </div>
    <template v-else>
      <section class="roadmap-section" aria-labelledby="roadmap-title">
        <header class="roadmap-header">
          <div>
            <span>长期阶段路线</span>
            <strong id="roadmap-title">从当前起点到课程目标</strong>
          </div>
          <span class="roadmap-status" :class="roadmap?.status">{{ statusLabel(roadmap?.status) }}</span>
        </header>

        <div v-if="['pending', 'generating'].includes(roadmap?.status)" class="roadmap-state" aria-live="polite">
          <RefreshCw :size="18" class="spinning" />
          <div><strong>正在生成初始路线</strong><p>课程目标、目标日期和每日时长已进入生成任务。</p></div>
        </div>
        <div v-else-if="roadmap?.status === 'failed'" class="roadmap-state failed" role="alert">
          <Route :size="18" />
          <div><strong>路线生成失败</strong><p>{{ roadmap.last_error || '生成任务未能完成，未创建占位路线。' }}</p></div>
          <button type="button" :disabled="retrying" @click="retryRoadmap">
            <RefreshCw :size="13" /> {{ retrying ? '正在重试' : '重试生成' }}
          </button>
        </div>
        <template v-else-if="roadmap?.status === 'ready'">
          <div class="roadmap-overview">
            <span>总进度 <strong>{{ overallProgress }}%</strong></span>
            <span>{{ roadmap.stages.length }} 个阶段</span>
            <span>生成方式：规则路线 v1</span>
          </div>
          <div class="stage-list">
            <article
              v-for="stage in roadmap.stages"
              :key="stage.id"
              class="roadmap-stage"
              :class="stage.status"
            >
              <span class="stage-marker">{{ stage.position }}</span>
              <div class="stage-body">
                <div class="stage-heading">
                  <div><span>{{ statusLabel(stage.status) }}</span><strong>{{ stage.name }}</strong></div>
                  <strong>{{ Math.round(stage.progress) }}%</strong>
                </div>
                <span
                  class="stage-progress"
                  role="progressbar"
                  :aria-label="`${stage.name}进度`"
                  :aria-valuenow="Math.round(stage.progress)"
                  aria-valuemin="0"
                  aria-valuemax="100"
                ><i :style="{ width: `${stage.progress}%` }"></i></span>
                <p class="stage-goal">{{ stage.goal }}</p>
                <details :open="stage.status === 'active'">
                  <summary>阶段依据与完成条件 <ChevronDown :size="13" /></summary>
                  <dl>
                    <div><dt>预计投入</dt><dd>{{ stage.estimated_days }} 天</dd></div>
                    <div><dt>完成条件</dt><dd>{{ stage.completion_condition }}</dd></div>
                    <div><dt>调整原因</dt><dd>{{ stage.adaptation_reason || '暂无动态调整' }}</dd></div>
                  </dl>
                  <div v-if="stage.knowledge_points?.length" class="stage-evidence">
                    <span><Link2 :size="12" /> 真实知识点</span>
                    <button
                      v-for="point in stage.knowledge_points"
                      :key="point.id"
                      type="button"
                      @click="$emit('prompt', `请结合课程资料讲解知识点：${point.name}`)"
                    >{{ point.name }} {{ Math.round(point.mastery) }}%</button>
                  </div>
                  <div class="recommended-content">
                    <span v-for="item in stage.recommended_content" :key="item">{{ item }}</span>
                  </div>
                  <small v-if="stage.daily_sessions?.length">
                    已关联 {{ stage.daily_sessions.length }} 个真实每日学习单元
                  </small>
                </details>
              </div>
            </article>
          </div>
        </template>
      </section>

      <section class="daily-section" aria-labelledby="daily-plan-title">
        <header class="daily-heading">
          <div><span>每日执行计划</span><strong id="daily-plan-title">今天具体学什么</strong></div>
          <p v-if="plan">{{ plan.start_date }} 至 {{ plan.end_date }}</p>
        </header>
        <div v-if="!plan" class="panel-empty compact">
          <CalendarDays :size="24" /><strong>还没有每日计划</strong><p>完成课程诊断后，会基于真实掌握度生成按天执行的学习单元。</p>
          <button type="button" @click="$emit('change-panel', 'diagnostic')">开始入门诊断</button>
        </div>
        <template v-else>
          <div class="daily-summary"><strong>{{ plan.title }}</strong><span>{{ plan.sessions.length }} 个学习单元</span></div>
          <div class="session-list">
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
          </div>
        </template>
      </section>
    </template>
  </div>
</template>

<style scoped>
.plan-panel { display: grid; gap: 36px; }
.panel-state,
.panel-empty { min-height: 260px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--text-secondary); text-align: center; }
.panel-state { font-size: 14px; }
.panel-empty.compact { min-height: 180px; }
.panel-empty svg { color: var(--accent); }
.panel-empty strong { color: var(--text-primary); font-size: 17px; font-weight: 620; }
.panel-empty p { max-width: 340px; color: var(--text-secondary); font-size: 14px; line-height: 1.7; }
.panel-empty button { min-height: 42px; padding: 0 15px; border-radius: 12px; color: #fff; background: var(--accent); font-size: 13px; font-weight: 600; }
.roadmap-section,
.daily-section { display: grid; gap: 18px; }
.roadmap-header,
.daily-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-bottom: 15px; border-bottom: 1px solid var(--border-subtle); }
.roadmap-header > div,
.daily-heading > div { display: grid; gap: 3px; }
.roadmap-header div > span,
.daily-heading div > span { color: var(--accent); font-size: 12px; font-weight: 600; }
.roadmap-header strong,
.daily-heading strong { color: var(--text-primary); font-size: 22px; font-weight: 630; letter-spacing: -.025em; }
.daily-heading > p { color: var(--text-tertiary); font-size: 12px; }
.roadmap-status { padding: 4px 8px; border-radius: 999px; color: var(--text-secondary); background: var(--surface-tertiary); font-size: 11px; font-weight: 600; }
.roadmap-status.ready { color: var(--success); background: rgba(36, 138, 61, .1); }
.roadmap-status.failed { color: var(--danger); background: rgba(215, 0, 21, .08); }
.roadmap-state { min-height: 104px; display: grid; grid-template-columns: 24px minmax(0, 1fr); align-items: center; gap: 12px; padding: 16px; border-radius: 16px; color: #2858a6; background: var(--accent-softer); }
.roadmap-state.failed { grid-template-columns: 24px minmax(0, 1fr) auto; color: var(--danger); background: rgba(215, 0, 21, .06); }
.roadmap-state div { display: grid; gap: 3px; }
.roadmap-state strong { font-size: 14px; }
.roadmap-state p { color: var(--text-secondary); font-size: 13px; line-height: 1.6; }
.roadmap-state button { min-height: 38px; display: inline-flex; align-items: center; gap: 4px; padding: 0 10px; border: 1px solid rgba(215, 0, 21, .2); border-radius: 11px; color: var(--danger); font-size: 12px; background: #fff; }
.spinning { animation: spin 900ms linear infinite; }
.roadmap-overview { display: flex; flex-wrap: wrap; gap: 6px 16px; color: var(--text-secondary); font-size: 12px; }
.roadmap-overview strong { color: var(--accent); }
.stage-list { display: grid; }
.roadmap-stage { position: relative; display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; padding: 0 0 20px; }
.roadmap-stage:not(:last-child)::before { content: ''; position: absolute; left: 16px; top: 32px; bottom: -1px; width: 1px; background: var(--border-strong); }
.stage-marker { position: relative; z-index: 1; width: 33px; height: 33px; display: grid; place-items: center; border: 1px solid var(--border-subtle); border-radius: 50%; color: var(--text-secondary); background: var(--surface-tertiary); font-size: 12px; font-weight: 650; }
.roadmap-stage.active .stage-marker { border: 0; color: #fff; background: var(--gradient-brand); box-shadow: 0 7px 18px rgba(79, 124, 255, .22); }
.roadmap-stage.completed .stage-marker { color: var(--success); border-color: rgba(36, 138, 61, .2); background: rgba(36, 138, 61, .09); }
.stage-body { min-width: 0; display: grid; gap: 10px; padding-top: 3px; }
.roadmap-stage.active .stage-body { margin-top: -5px; padding: 18px; border: 1px solid rgba(52, 120, 246, .1); border-radius: 20px; background: linear-gradient(135deg, rgba(52, 120, 246, .12), rgba(109, 93, 252, .07)); }
.roadmap-stage.planned { opacity: .64; }
.stage-heading { display: flex; justify-content: space-between; gap: 8px; }
.stage-heading > div { min-width: 0; display: grid; gap: 2px; }
.stage-heading span { color: var(--text-tertiary); font-size: 11px; }
.stage-heading strong { color: var(--text-primary); font-size: 15px; font-weight: 620; }
.stage-heading > strong { flex: 0 0 auto; color: var(--accent); font-size: 13px; }
.stage-progress { height: 5px; overflow: hidden; border-radius: 999px; background: rgba(52, 120, 246, .1); }
.stage-progress i { display: block; height: 100%; border-radius: inherit; background: var(--gradient-blue-cyan); transition: width 180ms ease; }
.stage-goal { color: var(--text-secondary); font-size: 13px; line-height: 1.68; }
.roadmap-stage details { padding-top: 1px; }
.roadmap-stage summary { display: inline-flex; align-items: center; gap: 5px; color: var(--accent); cursor: pointer; font-size: 12px; }
.roadmap-stage details[open] summary svg { transform: rotate(180deg); }
.roadmap-stage dl { display: grid; gap: 8px; margin-top: 11px; padding: 12px; border-radius: 12px; background: rgba(255, 255, 255, .68); }
.roadmap-stage dl > div { display: grid; grid-template-columns: 68px minmax(0, 1fr); gap: 7px; }
.roadmap-stage dt { color: var(--text-tertiary); font-size: 11px; }
.roadmap-stage dd { color: var(--text-secondary); font-size: 12px; line-height: 1.55; }
.stage-evidence { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 8px; }
.stage-evidence > span { display: inline-flex; align-items: center; gap: 4px; color: var(--text-tertiary); font-size: 11px; }
.stage-evidence button,
.recommended-content span { padding: 5px 8px; border-radius: 9px; color: var(--accent); background: var(--accent-soft); font-size: 11px; }
.stage-evidence button:hover { color: #fff; background: var(--accent); }
.recommended-content { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 7px; }
.recommended-content span { color: var(--text-secondary); background: var(--surface-tertiary); }
.roadmap-stage details > small { display: block; margin-top: 7px; color: var(--text-tertiary); font-size: 11px; }
.daily-section { padding-top: 30px; border-top: 1px solid var(--border-subtle); }
.daily-summary { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.daily-summary strong { color: var(--text-primary); font-size: 14px; }
.daily-summary span { color: var(--text-tertiary); font-size: 12px; }
.session-list { display: grid; }
.session-list article { display: grid; gap: 6px; padding: 16px 8px 16px 18px; border-bottom: 1px solid var(--border-subtle); border-left: 2px solid var(--border-strong); }
.session-list article.in_progress { border-left-color: var(--warning); }
.session-list article.completed,
.session-list article.evaluated { border-left-color: var(--success); opacity: .72; }
.session-date { color: var(--accent); font-size: 12px; font-weight: 600; }
.session-heading { display: flex; align-items: center; justify-content: space-between; gap: 9px; }
.session-heading strong { color: var(--text-primary); font-size: 14px; }
.session-heading span { flex: 0 0 auto; padding: 3px 7px; border-radius: 999px; color: var(--text-secondary); background: var(--surface-tertiary); font-size: 11px; }
.session-list article > p { display: flex; align-items: center; gap: 4px; color: var(--text-secondary); font-size: 12px; }
.session-list small { color: var(--warning); font-size: 12px; line-height: 1.55; }
.session-actions { display: flex; justify-content: flex-end; gap: 5px; }
.session-actions button { min-height: 36px; padding: 0 10px; border-radius: 10px; color: var(--accent); font-size: 12px; }
.session-actions button:hover { background: var(--accent-soft); }
.schedule-editor { display: grid; grid-template-columns: minmax(0, 1fr) 38px; gap: 6px; }
.schedule-editor input { min-width: 0; height: 38px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: 11px; font-size: 13px; }
.schedule-editor button { display: grid; place-items: center; border-radius: 11px; color: #fff; background: var(--accent); }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .spinning { animation: none; }
  .stage-progress i { transition: none; }
}
</style>
