<script setup>
import { onMounted, ref, watch } from 'vue'
import { LogOut, Save, Settings2 } from 'lucide-vue-next'
import { updateCourse } from '../../api/courses'
import { showToast } from '../../components/common/toast'
import { useAuthStore } from '../../stores/auth'
import { useCourseStore } from '../../stores/course'
import { useRouter } from 'vue-router'

const router = useRouter()
const auth = useAuthStore()
const courses = useCourseStore()
const saving = ref(false)
const preferences = ref({ daily_minutes: 30, exam_at: '' })

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
    showToast({ type: 'success', message: '学习偏好已保存，下次学习时会自动生效' })
  } else {
    showToast({ type: 'error', message: response.message || '设置保存失败' })
  }
}

async function logout() {
  courses.reset()
  await auth.logout()
  await router.push('/login')
}

onMounted(async () => {
  await courses.ensureLoaded()
  syncPreferences()
})
watch(() => courses.current?.id, syncPreferences)
</script>

<template>
  <div class="settings-page">
    <header class="page-heading">
      <span class="eyebrow">课程与偏好</span>
      <h1>设置</h1>
      <p>管理账号和学习习惯。学习进度会在课程内单独展示。</p>
    </header>

    <div class="settings-layout">
      <section class="settings-section account-section">
        <div class="section-heading"><Settings2 :size="19" /><div><h2>账号</h2><p>{{ auth.username }} 的学习空间。</p></div></div>
        <div class="account-row"><span class="account-avatar">{{ (auth.username || 'U').slice(0, 1).toUpperCase() }}</span><div><strong>{{ auth.username }}</strong><span>当前登录账号</span></div><button class="secondary-button" type="button" @click="logout"><LogOut :size="15" /> 退出登录</button></div>
      </section>

      <section class="settings-section">
        <div class="section-heading"><Settings2 :size="19" /><div><h2>当前课程</h2><p>{{ courses.current?.name || '尚未选择课程' }} · 设置每天可安排的学习时间与目标日期。</p></div></div>
        <form v-if="courses.current" class="preference-form" @submit.prevent="savePreferences">
          <label><span>每日学习时长</span><div class="number-field"><input v-model.number="preferences.daily_minutes" type="number" min="10" max="480" /><small>分钟</small></div></label>
          <label><span>考试日期</span><input v-model="preferences.exam_at" type="datetime-local" /></label>
          <button class="primary-button" type="submit" :disabled="saving"><Save :size="15" /> {{ saving ? '正在保存' : '保存设置' }}</button>
        </form>
        <button v-else class="text-button" type="button" @click="router.push('/home')">先创建一门课程</button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-page { max-width: 980px; margin: 0 auto; padding: 46px clamp(18px, 5vw, 58px) 72px; }
.page-heading { margin-bottom: 34px; }.eyebrow { color: var(--accent); font-size: 13px; font-weight: 600; }.page-heading h1 { margin-top: 7px; font-size: 42px; font-weight: var(--weight-bold); letter-spacing: -.045em; }.page-heading p { margin-top: 10px; color: var(--text-secondary); font-size: 15px; line-height: 1.6; }
.settings-layout { display: grid; gap: 20px; }.settings-section { overflow: hidden; border: 1px solid var(--border-subtle); border-radius: var(--radius-large); background: var(--surface-card); box-shadow: var(--shadow-small), var(--shadow-hairline); }.section-heading { display: flex; align-items: flex-start; gap: 12px; padding: 20px 22px; border-bottom: 1px solid var(--border-subtle); color: var(--accent); }.section-heading h2 { color: var(--text-primary); font-size: 17px; font-weight: var(--weight-semibold); }.section-heading p { margin-top: 4px; color: var(--text-secondary); font-size: 13px; line-height: 1.55; }
.account-row { display: flex; align-items: center; gap: 13px; padding: 20px 22px; }.account-avatar { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 15px; color: var(--tone-blue-fg); background: var(--tone-blue-bg); font-size: 15px; font-weight: var(--weight-bold); }.account-row > div { min-width: 0; display: grid; gap: 4px; }.account-row strong { font-size: 14px; }.account-row span { color: var(--text-tertiary); font-size: 12px; }.account-row button { margin-left: auto; }
.preference-form { display: grid; grid-template-columns: 1fr 1.3fr auto; align-items: end; gap: 14px; padding: 20px 22px; }.preference-form label { display: grid; gap: 7px; }.preference-form label > span { color: var(--text-secondary); font-size: 13px; font-weight: 600; }.preference-form input { width: 100%; height: var(--control-lg); padding: 0 13px; border: 1px solid var(--border-strong); border-radius: 13px; background: var(--surface-secondary); font-size: 14px; }.number-field { position: relative; }.number-field input { padding-right: 42px; }.number-field small { position: absolute; right: 13px; top: 13px; color: var(--text-tertiary); font-size: 11px; }
.primary-button, .secondary-button, .text-button { min-height: 42px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 0 15px; border-radius: 13px; font-size: 13px; font-weight: 600; }.primary-button { color: var(--text-inverse); background: var(--gradient-brand); box-shadow: var(--shadow-brand); }.secondary-button { color: var(--accent); border: 1px solid var(--border-accent); background: var(--surface-primary); }.text-button { margin: 0 18px 16px; color: var(--accent); padding: 0; }
@media (max-width: 680px) { .settings-page { padding: 26px 14px 48px; }.page-heading h1 { font-size: 36px; }.preference-form { grid-template-columns: 1fr; }.account-row { align-items: flex-start; flex-wrap: wrap; }.account-row button { margin-left: 56px; } }
</style>
