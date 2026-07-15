<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CalendarDays, Check, ChevronRight, Plus, Target } from 'lucide-vue-next'
import { getKnowledgePoints } from '../../api/materials'
import { useCourseStore } from '../../stores/course'
import { showToast } from '../../components/common/toast'
import DiagnosticWorkspace from './components/DiagnosticWorkspace.vue'
import MaterialWorkspace from './components/MaterialWorkspace.vue'


const route = useRoute()
const router = useRouter()
const courses = useCourseStore()
const selectedId = ref(null)
const creating = ref(false)
const saving = ref(false)
const knowledgePoints = ref([])
const loadingPoints = ref(false)
const form = ref({ name: '', goal: '', exam_at: '', daily_minutes: 30 })
const validTabs = ['materials', 'knowledge', 'diagnostic']
const activeTab = ref(validTabs.includes(route.query.tab) ? route.query.tab : 'materials')

const selectedCourse = computed(() => courses.courses.find(course => course.id === selectedId.value) || courses.current)

const statusText = {
  draft: '待添加资料',
  preparing: '资料处理中',
  diagnostic_pending: '等待诊断',
  active: '学习中',
  completed: '已完成'
}

function formatDate(value) {
  if (!value) return '未设置考试日期'
  return new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date(value))
}

async function chooseCourse(course) {
  selectedId.value = course.id
  if (courses.current?.id !== course.id) {
    try {
      await courses.select(course.id)
    } catch (error) {
      showToast({ type: 'error', message: error.message })
    }
  }
  await loadKnowledgePoints()
}

function setTab(tab) {
  activeTab.value = tab
  router.replace({ path: '/courses', query: { ...route.query, tab } })
}

function openCourseCreator() {
  creating.value = true
}

function toggleCourseCreator() {
  creating.value = !creating.value
}

function closeCourseCreator() {
  creating.value = false
}

async function loadKnowledgePoints() {
  if (!selectedCourse.value?.id) return
  loadingPoints.value = true
  const response = await getKnowledgePoints(selectedCourse.value.id)
  loadingPoints.value = false
  if (response.code === 200) knowledgePoints.value = response.data?.items || []
}

async function createCourse() {
  if (!form.value.name.trim() || saving.value) return
  saving.value = true
  try {
    const course = await courses.create({
      name: form.value.name.trim(),
      goal: form.value.goal.trim(),
      exam_at: form.value.exam_at || null,
      daily_minutes: Number(form.value.daily_minutes)
    })
    await courses.select(course.id)
    selectedId.value = course.id
    creating.value = false
    form.value = { name: '', goal: '', exam_at: '', daily_minutes: 30 }
    knowledgePoints.value = []
    showToast({ type: 'success', message: '课程已创建，下一步添加资料' })
  } catch (error) {
    showToast({ type: 'error', message: error.message })
  } finally {
    saving.value = false
  }
}

async function refreshCourseState() {
  await courses.load()
  selectedId.value = courses.current?.id || selectedId.value
  await loadKnowledgePoints()
}

onMounted(async () => {
  await courses.ensureLoaded()
  selectedId.value = courses.current?.id || courses.courses[0]?.id || null
  await loadKnowledgePoints()
  if (!courses.courses.length) creating.value = true
})

watch(() => route.query.tab, tab => {
  if (validTabs.includes(tab)) activeTab.value = tab
})
</script>

<template>
  <div class="courses-page">
    <header class="page-heading">
      <div>
        <span class="eyebrow">课程空间</span>
        <h1>我的课程</h1>
        <p>课程是资料、诊断、计划和 AI 对话的统一上下文。</p>
      </div>
      <button class="primary-button" type="button" @click="toggleCourseCreator">
        <Plus :size="17" /> 新建课程
      </button>
    </header>

    <section v-if="creating" class="create-course-panel">
      <div class="create-heading">
        <div>
          <h2>建立冲刺目标</h2>
          <p>课程创建后可继续上传资料，不需要一次填写完所有信息。</p>
        </div>
        <button type="button" @click="closeCourseCreator">取消</button>
      </div>
      <form @submit.prevent="createCourse">
        <label>
          <span>课程名称</span>
          <input v-model="form.name" required maxlength="100" placeholder="例如：软件测试期末冲刺" />
        </label>
        <label class="goal-field">
          <span>本次目标</span>
          <input v-model="form.goal" maxlength="500" placeholder="例如：七天掌握测试设计方法" />
        </label>
        <label>
          <span>考试日期</span>
          <input v-model="form.exam_at" type="datetime-local" />
        </label>
        <label>
          <span>每天投入</span>
          <div class="minutes-input">
            <input v-model.number="form.daily_minutes" type="number" min="10" max="480" />
            <span>分钟</span>
          </div>
        </label>
        <button class="primary-button" type="submit" :disabled="saving || !form.name.trim()">
          {{ saving ? '正在创建' : '创建并设为当前课程' }}
        </button>
      </form>
    </section>

    <div v-if="courses.courses.length" class="course-layout">
      <aside class="course-list" aria-label="课程列表">
        <button
          v-for="course in courses.courses"
          :key="course.id"
          type="button"
          :class="{ active: selectedCourse?.id === course.id }"
          @click="chooseCourse(course)"
        >
          <span class="course-status-dot" :class="course.status"></span>
          <span class="course-list-copy">
            <strong>{{ course.name }}</strong>
            <small>{{ statusText[course.status] || course.status }}</small>
          </span>
          <Check v-if="courses.current?.id === course.id" :size="15" />
          <ChevronRight v-else :size="15" />
        </button>
      </aside>

      <main v-if="selectedCourse" class="course-detail">
        <section class="course-overview">
          <div class="course-title-block">
            <div>
              <span class="course-state" :class="selectedCourse.status">{{ statusText[selectedCourse.status] || selectedCourse.status }}</span>
              <h2>{{ selectedCourse.name }}</h2>
              <p>{{ selectedCourse.goal || '尚未填写课程目标' }}</p>
            </div>
          </div>
          <div class="course-facts">
            <span><CalendarDays :size="15" /> {{ formatDate(selectedCourse.exam_at) }}</span>
            <span><Target :size="15" /> 每天 {{ selectedCourse.daily_minutes }} 分钟</span>
          </div>
        </section>

        <div class="course-tabs" role="tablist" aria-label="课程内容">
          <button type="button" :class="{ active: activeTab === 'materials' }" @click="setTab('materials')">课程资料</button>
          <button type="button" :class="{ active: activeTab === 'knowledge' }" @click="setTab('knowledge')">知识点</button>
          <button type="button" :class="{ active: activeTab === 'diagnostic' }" @click="setTab('diagnostic')">入门诊断</button>
        </div>

        <div class="tab-content">
          <MaterialWorkspace
            v-if="activeTab === 'materials'"
            :course-id="selectedCourse.id"
            @processed="refreshCourseState"
          />

          <section v-else-if="activeTab === 'knowledge'" class="knowledge-workspace">
            <div class="section-heading">
              <div>
                <h3>从资料提取的知识点</h3>
                <p>每个知识点都保留来源片段，掌握度会在诊断与练习后建立。</p>
              </div>
              <span>{{ knowledgePoints.length }} 个</span>
            </div>
            <div v-if="loadingPoints" class="knowledge-state">正在读取知识点</div>
            <div v-else-if="!knowledgePoints.length" class="knowledge-state">资料处理完成后，知识点会自动出现在这里。</div>
            <div v-else class="knowledge-list">
              <article v-for="(point, index) in knowledgePoints" :key="point.id">
                <span>{{ String(index + 1).padStart(2, '0') }}</span>
                <div>
                  <strong>{{ point.name }}</strong>
                  <p>{{ point.description }}</p>
                </div>
                <small>{{ point.source_chunk_ids?.length || 0 }} 个来源片段</small>
              </article>
            </div>
          </section>

          <DiagnosticWorkspace
            v-else
            :course-id="selectedCourse.id"
            @completed="refreshCourseState"
          />
        </div>
      </main>
    </div>

    <section v-else-if="!creating" class="no-courses">
      <h2>还没有课程</h2>
      <p>创建第一门课程后即可上传资料并开始诊断。</p>
      <button class="primary-button" type="button" @click="openCourseCreator"><Plus :size="17" /> 新建课程</button>
    </section>
  </div>
</template>

<style scoped>
.courses-page { max-width: 1240px; margin: 0 auto; }
.page-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 22px; }
.eyebrow { color: #17705b; font-size: 12px; font-weight: 750; }
.page-heading h1 { margin-top: 4px; font-size: 28px; font-weight: 720; }
.page-heading p { margin-top: 7px; color: #69736e; font-size: 13px; }
.primary-button { min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 15px; border-radius: 6px; color: #ffffff; background: #176b58; font-size: 12px; font-weight: 750; }
.primary-button:hover:not(:disabled) { background: #105845; }
.primary-button:disabled { opacity: .48; }
.create-course-panel { margin-bottom: 20px; border: 1px solid #ccd9d2; border-radius: 8px; background: #ffffff; }
.create-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding: 15px 18px; border-bottom: 1px solid #e0e5e2; }
.create-heading h2 { font-size: 16px; font-weight: 750; }
.create-heading p { margin-top: 3px; color: #6e7973; font-size: 11px; }
.create-heading > button { color: #65716b; font-size: 11px; }
.create-course-panel form { display: grid; grid-template-columns: 1.2fr 1.8fr 1fr .7fr auto; align-items: end; gap: 12px; padding: 16px 18px; }
.create-course-panel label { display: grid; gap: 5px; min-width: 0; }
.create-course-panel label > span { color: #59655f; font-size: 10px; font-weight: 700; }
.create-course-panel input { width: 100%; height: 37px; padding: 0 10px; border: 1px solid #cbd4cf; border-radius: 6px; background: #fbfcfb; font-size: 12px; }
.create-course-panel input:focus { border-color: #27806a; box-shadow: 0 0 0 2px rgba(39,128,106,.11); }
.minutes-input { position: relative; }
.minutes-input input { padding-right: 37px; }
.minutes-input span { position: absolute; right: 9px; top: 10px; color: #75807a; font-size: 10px; }
.course-layout { display: grid; grid-template-columns: 224px minmax(0, 1fr); gap: 22px; align-items: start; }
.course-list { display: grid; gap: 5px; position: sticky; top: 84px; }
.course-list > button { width: 100%; min-height: 56px; display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; align-items: center; gap: 9px; padding: 8px 10px; border-radius: 7px; color: #52605a; text-align: left; }
.course-list > button:hover { background: #e9eeeb; }
.course-list > button.active { color: #174f42; background: #dceae4; }
.course-status-dot { width: 7px; height: 7px; border-radius: 50%; background: #a7b0ac; }
.course-status-dot.active { background: #168057; }
.course-status-dot.diagnostic_pending { background: #d38a19; }
.course-status-dot.preparing { background: #397e9d; }
.course-list-copy { min-width: 0; display: grid; gap: 2px; }
.course-list-copy strong,
.course-list-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.course-list-copy strong { font-size: 12px; }
.course-list-copy small { color: #7a847f; font-size: 9px; }
.course-detail { min-width: 0; }
.course-overview { display: flex; align-items: flex-end; justify-content: space-between; gap: 22px; padding-bottom: 17px; border-bottom: 1px solid #dce2de; }
.course-state { display: inline-flex; padding: 3px 6px; border-radius: 5px; color: #626e68; background: #e9edeb; font-size: 9px; font-weight: 750; }
.course-state.active { color: #146347; background: #dff1e7; }
.course-state.diagnostic_pending { color: #8b5b12; background: #fff0cf; }
.course-title-block h2 { margin-top: 7px; font-size: 21px; font-weight: 750; }
.course-title-block p { margin-top: 5px; color: #69736e; font-size: 12px; }
.course-facts { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 9px 14px; }
.course-facts span { display: inline-flex; align-items: center; gap: 5px; color: #66726c; font-size: 11px; white-space: nowrap; }
.course-tabs { display: flex; gap: 2px; margin-top: 16px; border-bottom: 1px solid #dce2de; }
.course-tabs button { min-height: 39px; padding: 0 15px; color: #69746e; border-bottom: 2px solid transparent; font-size: 11px; font-weight: 750; }
.course-tabs button.active { color: #176b58; border-bottom-color: #176b58; }
.tab-content { padding-top: 18px; }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding-bottom: 14px; border-bottom: 1px solid #dce2de; }
.section-heading h3 { font-size: 15px; font-weight: 750; }
.section-heading p { margin-top: 3px; color: #6d7872; font-size: 11px; }
.section-heading > span { color: #176b58; font-size: 11px; font-weight: 750; }
.knowledge-state { padding: 44px 0; color: #77817c; text-align: center; font-size: 12px; }
.knowledge-list article { display: grid; grid-template-columns: 34px minmax(0, 1fr) auto; gap: 10px; padding: 15px 0; border-bottom: 1px solid #e0e5e2; }
.knowledge-list article > span { color: #8a948f; font-family: var(--font-mono); font-size: 10px; }
.knowledge-list strong { font-size: 12px; }
.knowledge-list p { margin-top: 4px; color: #68736d; font-size: 11px; line-height: 1.5; }
.knowledge-list small { color: #7a8580; font-size: 9px; }
.no-courses { min-height: 340px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; border-block: 1px solid #dce2de; text-align: center; }
.no-courses h2 { font-size: 18px; font-weight: 750; }
.no-courses p { color: #6d7872; font-size: 12px; }
@media (max-width: 1050px) {
  .create-course-panel form { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .create-course-panel form .primary-button { align-self: end; }
}
@media (max-width: 760px) {
  .page-heading { align-items: stretch; flex-direction: column; }
  .page-heading > .primary-button { align-self: flex-start; }
  .create-course-panel form { grid-template-columns: 1fr; }
  .course-layout { grid-template-columns: 1fr; }
  .course-list { position: static; display: flex; overflow-x: auto; padding-bottom: 4px; }
  .course-list > button { min-width: 190px; }
  .course-overview { align-items: flex-start; flex-direction: column; }
  .course-facts { justify-content: flex-start; }
  .course-tabs { overflow-x: auto; }
  .course-tabs button { flex: 1; min-width: 88px; }
}
</style>
