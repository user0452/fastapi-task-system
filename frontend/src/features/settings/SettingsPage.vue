<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Braces, Bug, LogOut, Save, ShieldCheck, UserRound } from 'lucide-vue-next'
import { getAgentTools } from '../../api/agent'
import { getProfile } from '../../api/profiles'
import { updateCourse } from '../../api/courses'
import { useAuthStore } from '../../stores/auth'
import { useCourseStore } from '../../stores/course'
import { showToast } from '../../components/common/toast'


const router = useRouter()
const auth = useAuthStore()
const courses = useCourseStore()
const profile = ref(null)
const toolCatalog = ref(null)
const saving = ref(false)
const developerMode = ref(localStorage.getItem('a3:developer-mode') === 'true')
const preferences = ref({ daily_minutes: 30, exam_at: '' })

const profileData = computed(() => profile.value?.profile || profile.value || {})

function toLocalDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

function syncPreferences() {
  preferences.value = {
    daily_minutes: courses.current?.daily_minutes || 30,
    exam_at: toLocalDateTime(courses.current?.exam_at)
  }
}

async function savePreferences() {
  if (!courses.current?.id || saving.value) return
  saving.value = true
  const response = await updateCourse(courses.current.id, {
    daily_minutes: Number(preferences.value.daily_minutes),
    exam_at: preferences.value.exam_at || null
  })
  saving.value = false
  if (response.code === 200) {
    await courses.load()
    showToast({ type: 'success', message: '学习安排已更新' })
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

function toggleDeveloperMode() {
  localStorage.setItem('a3:developer-mode', String(developerMode.value))
}

async function logout() {
  courses.reset()
  await auth.logout()
  await router.push('/login')
}

onMounted(async () => {
  await courses.ensureLoaded()
  syncPreferences()
  const [profileResponse, toolResponse] = await Promise.all([getProfile(), getAgentTools()])
  if (profileResponse.code === 200) profile.value = profileResponse.data
  if (toolResponse.code === 200) toolCatalog.value = toolResponse.data
})
watch(() => courses.current?.id, syncPreferences)
</script>

<template>
  <div class="settings-page">
    <header class="page-heading">
      <div>
        <span class="eyebrow">个人与偏好</span>
        <h1>设置</h1>
        <p>账号、当前课程安排和开发模式集中在这里。</p>
      </div>
    </header>

    <div class="settings-layout">
      <section class="settings-section">
        <div class="section-heading">
          <UserRound :size="19" />
          <div><h2>账号与学习画像</h2><p>AI 助教会读取画像，但不会让画像内容覆盖系统规则。</p></div>
        </div>
        <div class="account-row">
          <span class="account-avatar">{{ (auth.username || 'U').slice(0, 1).toUpperCase() }}</span>
          <div><strong>{{ auth.username }}</strong><span>当前登录账号</span></div>
          <button class="secondary-button" type="button" @click="logout"><LogOut :size="15" /> 退出登录</button>
        </div>
        <div v-if="Object.keys(profileData).length" class="profile-summary">
          <div><span>学习阶段</span><strong>{{ profileData.learning_stage || profileData.level || '已建立画像' }}</strong></div>
          <div><span>学习目标</span><strong>{{ profileData.learning_goal || profileData.goal || '持续完成课程计划' }}</strong></div>
        </div>
        <button v-else class="text-button" type="button" @click="router.push('/agent?prompt=请根据我的学习情况建立学习画像')">
          让 AI 助教建立学习画像
        </button>
      </section>

      <section class="settings-section">
        <div class="section-heading">
          <ShieldCheck :size="19" />
          <div><h2>当前课程安排</h2><p>{{ courses.current?.name || '尚未选择课程' }}</p></div>
        </div>
        <form v-if="courses.current" class="preference-form" @submit.prevent="savePreferences">
          <label>
            <span>每日学习时长</span>
            <div class="number-field"><input v-model.number="preferences.daily_minutes" type="number" min="10" max="480" /><small>分钟</small></div>
          </label>
          <label>
            <span>考试日期</span>
            <input v-model="preferences.exam_at" type="datetime-local" />
          </label>
          <button class="primary-button" type="submit" :disabled="saving"><Save :size="15" /> {{ saving ? '正在保存' : '保存安排' }}</button>
        </form>
        <button v-else class="text-button" type="button" @click="router.push('/courses')">先创建一门课程</button>
      </section>

      <section v-if="toolCatalog" class="settings-section capability-section">
        <div class="section-heading">
          <Braces :size="19" />
          <div><h2>工具与安全边界</h2><p>这里显示服务端报告的真实能力状态。</p></div>
        </div>
        <div class="capability-list">
          <div v-if="toolCatalog.items?.find(item => item.name === 'python_sandbox')" class="capability-row">
            <div>
              <strong>受限 Python 执行器</strong>
              <span>应用级隔离，不是容器或虚拟机，不可面向不可信公网用户开放。</span>
            </div>
            <small class="status-pill warning">实验性</small>
          </div>
          <div v-for="(integration, name) in toolCatalog.integrations" :key="name" class="capability-row">
            <div>
              <strong>{{ name === 'mcp' ? 'MCP 工具' : '图片生成' }}</strong>
              <span>{{ integration.status === 'configured_not_implemented' ? '已配置，但真实执行适配器尚未实现。' : '按服务端配置与适配器状态显示。' }}</span>
            </div>
            <small class="status-pill" :class="integration.status">{{ ({ unconfigured: '未配置', misconfigured: '配置错误', configured_not_implemented: '适配器未实现', available: '可用', disabled: '已停用' })[integration.status] || integration.status }}</small>
          </div>
        </div>
      </section>

      <section class="settings-section developer-section">
        <div class="section-heading">
          <Bug :size="19" />
          <div><h2>开发模式</h2><p>仅在调试时显示技术页面和操作日志。</p></div>
        </div>
        <label class="toggle-row">
          <div><strong>显示开发工具</strong><span>普通学习流程不展示 RAG 测试和调度摘要。</span></div>
          <input v-model="developerMode" type="checkbox" @change="toggleDeveloperMode" />
          <i></i>
        </label>
        <button v-if="developerMode" class="secondary-button" type="button" @click="router.push('/logs')">查看操作日志</button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-page { max-width: 900px; margin: 0 auto; }
.page-heading { margin-bottom: 22px; }
.eyebrow { color: #17705b; font-size: 12px; font-weight: 750; }
.page-heading h1 { margin-top: 4px; font-size: 28px; font-weight: 720; }
.page-heading p { margin-top: 7px; color: #69736e; font-size: 13px; }
.settings-layout { display: grid; gap: 18px; }
.settings-section { border: 1px solid #d8dfdb; border-radius: 8px; background: #ffffff; }
.section-heading { display: flex; align-items: flex-start; gap: 10px; padding: 15px 18px; border-bottom: 1px solid #e0e5e2; color: #256c59; }
.section-heading h2 { color: #27332d; font-size: 14px; font-weight: 750; }
.section-heading p { margin-top: 3px; color: #727d77; font-size: 10px; }
.account-row { display: flex; align-items: center; gap: 10px; padding: 17px 18px; }
.account-avatar { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 50%; color: #176b58; background: #dcece5; font-size: 13px; font-weight: 800; }
.account-row > div { min-width: 0; display: grid; }
.account-row strong { font-size: 12px; }
.account-row span { color: #77817c; font-size: 9px; }
.account-row button { margin-left: auto; }
.profile-summary { display: grid; grid-template-columns: 1fr 2fr; border-top: 1px solid #e3e7e4; }
.profile-summary > div { display: grid; gap: 4px; padding: 14px 18px; border-right: 1px solid #e3e7e4; }
.profile-summary > div:last-child { border-right: 0; }
.profile-summary span { color: #77817c; font-size: 9px; }
.profile-summary strong { font-size: 11px; font-weight: 650; }
.preference-form { display: grid; grid-template-columns: 1fr 1.3fr auto; align-items: end; gap: 13px; padding: 17px 18px; }
.preference-form label { display: grid; gap: 5px; }
.preference-form label > span { color: #59655f; font-size: 10px; font-weight: 700; }
.preference-form input { width: 100%; height: 37px; padding: 0 10px; border: 1px solid #cbd4cf; border-radius: 6px; background: #fbfcfb; font-size: 12px; }
.number-field { position: relative; }
.number-field input { padding-right: 42px; }
.number-field small { position: absolute; right: 10px; top: 10px; color: #77817c; font-size: 9px; }
.primary-button,
.secondary-button,
.text-button { min-height: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 0 13px; border-radius: 6px; font-size: 11px; font-weight: 750; }
.primary-button { color: #ffffff; background: #176b58; }
.secondary-button { color: #175b4a; border: 1px solid #aec0b8; background: #ffffff; }
.text-button { margin: 0 18px 16px; color: #176b58; padding: 0; }
.developer-section > .secondary-button { margin: 0 18px 16px; }
.capability-list { display: grid; }
.capability-row { min-height: 58px; display: flex; align-items: center; gap: 16px; padding: 11px 18px; border-bottom: 1px solid #e3e7e4; }
.capability-row:last-child { border-bottom: 0; }
.capability-row > div { min-width: 0; flex: 1; display: grid; gap: 3px; }
.capability-row strong { font-size: 11px; }
.capability-row span { color: #77817c; font-size: 9px; line-height: 1.5; }
.status-pill { flex: none; padding: 3px 8px; border-radius: 999px; color: #315f52; background: #e5f1ec; font-size: 9px; font-weight: 750; }
.status-pill.warning,
.status-pill.configured_not_implemented,
.status-pill.misconfigured { color: #7b5426; background: #f8edd7; }
.status-pill.disabled,
.status-pill.unconfigured { color: #69736e; background: #edf0ee; }
.toggle-row { position: relative; display: flex; align-items: center; gap: 12px; padding: 16px 18px; cursor: pointer; }
.toggle-row > div { flex: 1; display: grid; gap: 2px; }
.toggle-row strong { font-size: 11px; }
.toggle-row span { color: #77817c; font-size: 9px; }
.toggle-row input { position: absolute; opacity: 0; }
.toggle-row i { position: relative; width: 38px; height: 22px; border-radius: 12px; background: #c8cfcb; transition: background 150ms ease; }
.toggle-row i::after { content: ''; position: absolute; left: 3px; top: 3px; width: 16px; height: 16px; border-radius: 50%; background: #ffffff; transition: transform 150ms ease; }
.toggle-row input:checked + i { background: #176b58; }
.toggle-row input:checked + i::after { transform: translateX(16px); }
@media (max-width: 680px) {
  .preference-form { grid-template-columns: 1fr; }
  .profile-summary { grid-template-columns: 1fr; }
  .profile-summary > div { border-right: 0; border-bottom: 1px solid #e3e7e4; }
  .account-row { align-items: flex-start; flex-wrap: wrap; }
  .account-row button { margin-left: 46px; }
}
</style>
