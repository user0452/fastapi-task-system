<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Braces, Bug, LogOut, Save, ShieldCheck, UserRound } from 'lucide-vue-next'
import { getAgentTools } from '../../api/agent'
import { getMemorySettings, getProfile, updateMemorySettings } from '../../api/profiles'
import { updateCourse } from '../../api/courses'
import { useAuthStore } from '../../stores/auth'
import { useCourseStore } from '../../stores/course'
import { showToast } from '../../components/common/toast'
import OpenAIConfigSection from './components/OpenAIConfigSection.vue'


const router = useRouter()
const auth = useAuthStore()
const courses = useCourseStore()
const profile = ref(null)
const toolCatalog = ref(null)
const saving = ref(false)
const developerMode = ref(localStorage.getItem('a3:developer-mode') === 'true')
const preferences = ref({ daily_minutes: 30, exam_at: '' })
const memorySettings = ref({ course_auto_memory_enabled: false, cross_course_profile_enabled: false })
const memorySaving = ref(false)

const profileData = computed(() => profile.value?.profile || profile.value || {})
const derivedProfile = computed(() => profile.value?.derived_profile || null)
const derivedProfileMeta = computed(() => profile.value?.derived_profile_meta || null)

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

async function saveMemorySettings() {
  if (memorySaving.value) return
  memorySaving.value = true
  const response = await updateMemorySettings(memorySettings.value)
  memorySaving.value = false
  if (response.code === 200) {
    memorySettings.value = response.data
    showToast({ type: 'success', message: '自动学习记忆设置已更新' })
  } else {
    showToast({ type: 'error', message: response.message || '设置保存失败' })
  }
}

function toggleCourseAutoMemory() {
  if (!memorySettings.value.course_auto_memory_enabled) memorySettings.value.cross_course_profile_enabled = false
  saveMemorySettings()
}

function toggleCrossCourseProfile() {
  if (memorySettings.value.cross_course_profile_enabled) memorySettings.value.course_auto_memory_enabled = true
  saveMemorySettings()
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
  const [profileResponse, toolResponse, memoryResponse] = await Promise.all([getProfile(), getAgentTools(), getMemorySettings()])
  if (profileResponse.code === 200) profile.value = profileResponse.data
  if (memoryResponse.code === 200) memorySettings.value = memoryResponse.data
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

      <OpenAIConfigSection />

      <section class="settings-section">
        <div class="section-heading">
          <ShieldCheck :size="19" />
          <div><h2>自动学习记忆</h2><p>只从你启用的课程对话中提炼明确、长期有用的信息。</p></div>
        </div>
        <div class="memory-settings">
          <label class="toggle-row">
            <div><strong>自动提炼课程记忆</strong><span>从明确的学习偏好和目标中生成可查看、可修正的课程记忆。</span></div>
            <input v-model="memorySettings.course_auto_memory_enabled" type="checkbox" :disabled="memorySaving" @change="toggleCourseAutoMemory" />
            <i></i>
          </label>
          <label class="toggle-row">
            <div><strong>生成跨课程学习画像</strong><span>在多门课程出现足够证据后，汇总共通的学习偏好和规律。</span></div>
            <input v-model="memorySettings.cross_course_profile_enabled" type="checkbox" :disabled="memorySaving" @change="toggleCrossCourseProfile" />
            <i></i>
          </label>
        </div>
        <div v-if="derivedProfileMeta" class="derived-profile">
          <div><span>自动画像</span><strong>{{ derivedProfileMeta.status === 'active' ? '已更新' : '等待更新' }}</strong></div>
          <div><span>覆盖范围</span><strong>{{ derivedProfileMeta.source_course_count || 0 }} 门课 · {{ derivedProfileMeta.source_memory_count || 0 }} 条记忆</strong></div>
          <p v-if="derivedProfile?.learning_preferences?.length">{{ derivedProfile.learning_preferences.map(item => item.text || item).join('；') }}</p>
          <p v-else>系统会在收集到足够的跨课程证据后生成学习画像。</p>
        </div>
        <p v-else class="memory-hint">关闭后会停止未来自动提炼和画像注入；已有课程记忆仍可在课程面板中修正、暂停或删除。</p>
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
.settings-page {
  max-width: 980px;
  margin: 0 auto;
  padding: 46px clamp(18px, 5vw, 58px) 72px;
}
.page-heading { margin-bottom: 34px; }
.eyebrow { color: var(--accent); font-size: 13px; font-weight: 600; }
.page-heading h1 {
  margin-top: 7px;
  font-size: 42px;
  font-weight: var(--weight-bold);
  letter-spacing: -.045em;
}
.page-heading p {
  margin-top: 10px;
  color: var(--text-secondary);
  font-size: 15px;
}
.settings-layout { display: grid; gap: 20px; }
.settings-section {
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-large);
  background: var(--surface-card);
  box-shadow: var(--shadow-small), var(--shadow-hairline);
}
.section-heading {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 20px 22px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--accent);
}
.section-heading h2 {
  color: var(--text-primary);
  font-size: 17px;
  font-weight: var(--weight-semibold);
}
.section-heading p {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.55;
}
.account-row { display: flex; align-items: center; gap: 13px; padding: 20px 22px; }
.account-avatar {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 15px;
  color: var(--tone-blue-fg);
  background: var(--tone-blue-bg);
  font-size: 15px;
  font-weight: var(--weight-bold);
}
.account-row > div { min-width: 0; display: grid; }
.account-row strong { font-size: 14px; }
.account-row span { color: var(--text-tertiary); font-size: 12px; }
.account-row button { margin-left: auto; }
.profile-summary {
  display: grid;
  grid-template-columns: 1fr 2fr;
  border-top: 1px solid var(--border-subtle);
}
.profile-summary > div {
  display: grid;
  gap: 5px;
  padding: 17px 22px;
  border-right: 1px solid var(--border-subtle);
}
.profile-summary > div:last-child { border-right: 0; }
.profile-summary span { color: var(--text-tertiary); font-size: 12px; }
.profile-summary strong { font-size: 13px; font-weight: var(--weight-medium); }
.memory-settings { display: grid; }
.memory-settings .toggle-row { border-bottom: 1px solid var(--border-subtle); }
.memory-settings .toggle-row:last-child { border-bottom: 0; }
.derived-profile,
.memory-hint { padding: 17px 22px; border-top: 1px solid var(--border-subtle); }
.derived-profile { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.derived-profile div { display: grid; gap: 4px; }
.derived-profile span { color: var(--text-tertiary); font-size: 12px; }
.derived-profile strong { color: var(--text-primary); font-size: 13px; font-weight: var(--weight-medium); }
.derived-profile p { grid-column: 1 / -1; color: var(--text-secondary); font-size: 13px; line-height: 1.6; }
.memory-hint { color: var(--text-secondary); font-size: 13px; line-height: 1.6; }
.preference-form {
  display: grid;
  grid-template-columns: 1fr 1.3fr auto;
  align-items: end;
  gap: 14px;
  padding: 20px 22px;
}
.preference-form label { display: grid; gap: 7px; }
.preference-form label > span {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
}
.preference-form input {
  width: 100%;
  height: var(--control-lg);
  padding: 0 13px;
  border: 1px solid var(--border-strong);
  border-radius: 13px;
  background: var(--surface-secondary);
  font-size: 14px;
}
.number-field { position: relative; }
.number-field input { padding-right: 42px; }
.number-field small {
  position: absolute;
  right: 13px;
  top: 13px;
  color: var(--text-tertiary);
  font-size: 11px;
}
.primary-button,
.secondary-button,
.text-button {
  min-height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 15px;
  border-radius: 13px;
  font-size: 13px;
  font-weight: 600;
}
.primary-button {
  color: var(--text-inverse);
  background: var(--gradient-brand);
  box-shadow: var(--shadow-brand);
}
.secondary-button {
  color: var(--accent);
  border: 1px solid var(--border-accent);
  background: var(--surface-primary);
}
.text-button { margin: 0 18px 16px; color: var(--accent); padding: 0; }
.developer-section > .secondary-button { margin: 0 18px 16px; }
.capability-list { display: grid; }
.capability-row {
  min-height: 72px;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 14px 22px;
  border-bottom: 1px solid var(--border-subtle);
}
.capability-row:last-child { border-bottom: 0; }
.capability-row > div { min-width: 0; flex: 1; display: grid; gap: 3px; }
.capability-row strong { font-size: 14px; }
.capability-row span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.status-pill {
  flex: none;
  padding: 5px 9px;
  border-radius: var(--radius-round);
  color: var(--success);
  background: var(--success-soft);
  font-size: 11px;
  font-weight: 600;
}
.status-pill.warning,
.status-pill.configured_not_implemented,
.status-pill.misconfigured {
  color: var(--warning);
  background: var(--warning-soft);
}
.status-pill.disabled,
.status-pill.unconfigured {
  color: var(--text-secondary);
  background: var(--surface-tertiary);
}
.toggle-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 19px 22px;
  cursor: pointer;
}
.toggle-row > div { flex: 1; display: grid; gap: 4px; }
.toggle-row strong { font-size: 14px; }
.toggle-row span { color: var(--text-secondary); font-size: 12px; }
.toggle-row input { position: absolute; opacity: 0; }
.toggle-row i {
  position: relative;
  width: 44px;
  height: 26px;
  border-radius: var(--radius-round);
  background: #c7c8cd;
  transition: background var(--duration-fast) var(--ease-standard);
}
.toggle-row i::after {
  content: '';
  position: absolute;
  left: 3px;
  top: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--surface-primary);
  transition: transform var(--duration-fast) var(--ease-standard);
}
.toggle-row input:checked + i { background: var(--accent); }
.toggle-row input:checked + i::after { transform: translateX(18px); }
@media (max-width: 680px) {
  .settings-page { padding: 26px 14px 48px; }
  .page-heading h1 { font-size: 36px; }
  .preference-form { grid-template-columns: 1fr; }
  .profile-summary { grid-template-columns: 1fr; }
  .profile-summary > div {
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }
  .account-row { align-items: flex-start; flex-wrap: wrap; }
  .account-row button { margin-left: 56px; }
  .capability-row { align-items: flex-start; }
}
</style>

