<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Menu, Sparkles, X } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import { useCourseStore } from '../stores/course'
import CourseRail from '../features/workspace/components/CourseRail.vue'
import { showToast } from '../components/common/toast'
import { safePostLoginRoute } from '../router/redirect'


const auth = useAuthStore()
const courses = useCourseStore()
const route = useRoute()
const router = useRouter()
const railOpen = ref(false)
const creatorOpen = ref(false)
const creating = ref(false)
const form = reactive({ name: '', goal: '', exam_at: '', daily_minutes: 30 })

const currentId = computed(() => Number(route.params.courseId || courses.current?.id || 0) || null)
const routeViewKey = computed(() => `${String(route.name || route.path)}:${route.params.courseId || ''}`)

async function selectCourse(courseId) {
  if (!courseId) return
  try {
    await courses.select(courseId)
  } catch (error) {
    showToast({ type: 'error', message: error.message })
  }
}

function openCreator() {
  creatorOpen.value = true
  railOpen.value = false
}

function closeCreator() {
  if (creating.value) return
  creatorOpen.value = false
}

async function createCourse() {
  if (!form.name.trim() || creating.value) return
  creating.value = true
  try {
    const course = await courses.create({
      name: form.name.trim(),
      goal: form.goal.trim(),
      exam_at: form.exam_at || null,
      daily_minutes: Number(form.daily_minutes) || 30
    })
    await courses.select(course.id)
    Object.assign(form, { name: '', goal: '', exam_at: '', daily_minutes: 30 })
    creatorOpen.value = false
    await router.push(`/learn/${course.id}?panel=materials`)
    showToast({ type: 'success', message: '课程助手已创建' })
  } catch (error) {
    showToast({ type: 'error', message: error.message })
  } finally {
    creating.value = false
  }
}

async function logout() {
  const redirect = safePostLoginRoute(route.fullPath)
  courses.reset()
  await auth.logout()
  await router.push({ path: '/login', query: redirect ? { redirect } : {} })
}

watch(() => route.params.courseId, courseId => {
  if (courseId) selectCourse(Number(courseId))
  railOpen.value = false
})

onMounted(async () => {
  await courses.ensureLoaded()
  if (route.params.courseId) await selectCourse(Number(route.params.courseId))
})
</script>

<template>
  <div class="ai-shell">
    <div class="desktop-rail">
      <CourseRail
        :courses="courses.courses"
        :current-id="currentId"
        :username="auth.username"
        :loading="courses.loading"
        :error="courses.error"
        @create="openCreator"
        @logout="logout"
      />
    </div>

    <header class="mobile-bar">
      <button class="mobile-icon" type="button" title="打开课程栏" aria-label="打开课程栏" @click="railOpen = true">
        <Menu :size="19" />
      </button>
      <span><Sparkles :size="15" /> A3 学习 AI</span>
      <span class="mobile-course">{{ courses.current?.name || '今日总览' }}</span>
    </header>

    <transition name="rail-slide">
      <div v-if="railOpen" class="mobile-rail">
        <CourseRail
          :courses="courses.courses"
          :current-id="currentId"
          :username="auth.username"
          :loading="courses.loading"
          :error="courses.error"
          mobile
          @create="openCreator"
          @logout="logout"
          @close="railOpen = false"
        />
      </div>
    </transition>
    <button v-if="railOpen" class="rail-scrim" type="button" aria-label="关闭课程栏" @click="railOpen = false"></button>

    <main class="ai-main">
      <router-view v-slot="{ Component }">
        <transition name="workspace-fade" mode="out-in">
          <component :is="Component" :key="routeViewKey" />
        </transition>
      </router-view>
    </main>

    <Teleport to="body">
      <div v-if="creatorOpen" class="creator-overlay" @click.self="closeCreator">
        <section class="course-creator" role="dialog" aria-modal="true" aria-labelledby="course-creator-title">
          <header>
            <div>
              <span>新课程助手</span>
              <h2 id="course-creator-title">创建一门长期学习的课程</h2>
            </div>
            <button type="button" title="关闭" aria-label="关闭" @click="closeCreator"><X :size="19" /></button>
          </header>
          <form @submit.prevent="createCourse">
            <label>
              <span>课程名称</span>
              <input v-model="form.name" autofocus maxlength="100" placeholder="例如：软件测试" />
            </label>
            <label>
              <span>学习目标</span>
              <textarea v-model="form.goal" rows="3" maxlength="500" placeholder="例如：掌握核心测试设计方法并完成考试冲刺"></textarea>
            </label>
            <div class="creator-grid">
              <label>
                <span>目标日期</span>
                <input v-model="form.exam_at" type="datetime-local" />
              </label>
              <label>
                <span>每日分钟</span>
                <input v-model.number="form.daily_minutes" type="number" min="10" max="480" step="5" />
              </label>
            </div>
            <footer>
              <button class="creator-cancel" type="button" @click="closeCreator">取消</button>
              <button class="creator-submit" type="submit" :disabled="!form.name.trim() || creating">
                {{ creating ? '正在创建' : '创建课程助手' }}
              </button>
            </footer>
          </form>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.ai-shell { min-height: 100dvh; display: grid; grid-template-columns: 236px minmax(0, 1fr); background: #f8f9f7; }
.desktop-rail { position: fixed; inset: 0 auto 0 0; z-index: 40; width: 236px; }
.ai-main { grid-column: 2; min-width: 0; min-height: 100dvh; overflow: hidden; }
.mobile-bar,
.mobile-rail,
.rail-scrim { display: none; }
.workspace-fade-enter-active,
.workspace-fade-leave-active { transition: opacity 150ms ease, transform 150ms ease; }
.workspace-fade-enter-from { opacity: 0; transform: translateY(4px); }
.workspace-fade-leave-to { opacity: 0; transform: translateY(-2px); }
.creator-overlay { position: fixed; inset: 0; z-index: 100; display: grid; place-items: center; padding: 20px; background: rgba(28, 35, 31, .38); }
.course-creator { width: min(520px, 100%); overflow: hidden; border: 1px solid #d8dfdb; border-radius: 8px; background: #fff; box-shadow: 0 20px 60px rgba(27, 39, 33, .18); }
.course-creator > header { min-height: 72px; display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 15px 18px; border-bottom: 1px solid #e0e5e2; }
.course-creator header span { color: #19705a; font-size: 9px; font-weight: 760; }
.course-creator h2 { margin-top: 3px; font-size: 16px; font-weight: 740; }
.course-creator header button { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 6px; color: #66716b; }
.course-creator header button:hover { background: #edf1ee; }
.course-creator form { display: grid; gap: 15px; padding: 18px; }
.course-creator label { display: grid; gap: 6px; }
.course-creator label > span { color: #58635e; font-size: 10px; font-weight: 720; }
.course-creator input,
.course-creator textarea { width: 100%; padding: 10px 11px; border: 1px solid #cbd4cf; border-radius: 6px; background: #fbfcfb; font-size: 12px; }
.course-creator textarea { resize: vertical; line-height: 1.55; }
.course-creator input:focus,
.course-creator textarea:focus { border-color: #287b66; box-shadow: 0 0 0 2px rgba(40, 123, 102, .11); }
.creator-grid { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(120px, .7fr); gap: 12px; }
.course-creator footer { display: flex; justify-content: flex-end; gap: 8px; padding-top: 3px; }
.creator-cancel,
.creator-submit { min-height: 36px; padding: 0 14px; border-radius: 6px; font-size: 11px; font-weight: 730; }
.creator-cancel { color: #59655f; border: 1px solid #cbd3ce; }
.creator-submit { color: #fff; background: #176b58; }
.creator-submit:disabled { opacity: .45; }

@media (max-width: 820px) {
  .ai-shell { display: block; padding-top: 52px; }
  .desktop-rail { display: none; }
  .ai-main { min-height: calc(100dvh - 52px); }
  .mobile-bar { position: fixed; inset: 0 0 auto; z-index: 45; height: 52px; display: grid; grid-template-columns: 38px auto minmax(0, 1fr); align-items: center; gap: 9px; padding: 0 10px; background: #fff; border-bottom: 1px solid #dce1dd; }
  .mobile-bar > span { display: inline-flex; align-items: center; gap: 5px; color: #1d5f4e; font-size: 11px; font-weight: 760; white-space: nowrap; }
  .mobile-bar .mobile-course { overflow: hidden; justify-self: end; color: #727c77; font-size: 9px; text-overflow: ellipsis; }
  .mobile-icon { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 6px; color: #5e6963; }
  .mobile-rail { position: fixed; inset: 0 auto 0 0; z-index: 70; display: block; }
  .mobile-rail :deep(.course-rail) { width: min(290px, 84vw); }
  .rail-scrim { position: fixed; inset: 0; z-index: 65; display: block; width: 100%; background: rgba(24, 31, 27, .32); }
  .rail-slide-enter-active,
  .rail-slide-leave-active { transition: transform 190ms ease; }
  .rail-slide-enter-from,
  .rail-slide-leave-to { transform: translateX(-100%); }
}

@media (max-width: 520px) {
  .creator-grid { grid-template-columns: 1fr; }
  .course-creator footer { flex-direction: column-reverse; }
  .creator-cancel,
  .creator-submit { width: 100%; }
}
</style>
