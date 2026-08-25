<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Menu, PanelLeftClose, PanelLeftOpen, Sparkles } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import { useCourseStore } from '../stores/course'
import CourseRail from '../features/workspace/components/CourseRail.vue'
import Modal from '../components/common/Modal.vue'
import { showToast } from '../components/common/toast'
import { safePostLoginRoute } from '../router/redirect'


const auth = useAuthStore()
const courses = useCourseStore()
const route = useRoute()
const router = useRouter()
const railOpen = ref(false)
const railCollapsed = ref(localStorage.getItem('a3:course-rail-collapsed') === 'true')
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

function toggleRail() {
  railCollapsed.value = !railCollapsed.value
  localStorage.setItem('a3:course-rail-collapsed', String(railCollapsed.value))
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
    await router.push(`/materials/${course.id}`)
    showToast({ type: 'success', message: '课程已创建，先添加一份资料吧' })
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
  <div class="ai-shell" :class="{ 'rail-collapsed': railCollapsed }">
    <div class="desktop-rail">
      <CourseRail
        :courses="courses.courses"
        :current-id="currentId"
        :username="auth.username"
        :loading="courses.loading"
        :error="courses.error"
        :collapsed="railCollapsed"
        @create="openCreator"
        @logout="logout"
      />
      <button
        class="rail-collapse-toggle"
        type="button"
        :title="railCollapsed ? '展开课程栏' : '折叠课程栏'"
        :aria-label="railCollapsed ? '展开课程栏' : '折叠课程栏'"
        :aria-expanded="!railCollapsed"
        @click="toggleRail"
      >
        <PanelLeftOpen v-if="railCollapsed" :size="16" />
        <PanelLeftClose v-else :size="16" />
      </button>
    </div>

    <header class="mobile-bar">
      <button class="mobile-icon" type="button" title="打开课程栏" aria-label="打开课程栏" @click="railOpen = true">
        <Menu :size="19" />
      </button>
      <span><Sparkles :size="15" /> A3 学习</span>
      <span class="mobile-course">{{ courses.current?.name || '首页' }}</span>
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

    <Modal :show="creatorOpen" title="创建一门长期学习的课程" size="md" @close="closeCreator">
      <form class="course-creator-form" @submit.prevent="createCourse">
        <p class="creator-kicker">新课程助手</p>
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
    </Modal>
  </div>
</template>

<style scoped>
.ai-shell {
  min-height: 100dvh;
  display: grid;
  grid-template-columns: var(--rail-width) minmax(0, 1fr);
  background: var(--gradient-soft-page);
  transition: grid-template-columns var(--duration-normal) var(--ease-out);
}
.ai-shell.rail-collapsed { grid-template-columns: var(--rail-collapsed) minmax(0, 1fr); }
.desktop-rail {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 40;
  width: var(--rail-width);
  transition: width var(--duration-normal) var(--ease-out);
}
.rail-collapsed .desktop-rail { width: var(--rail-collapsed); }
.ai-main { grid-column: 2; min-width: 0; min-height: 100dvh; overflow: hidden; }
.rail-collapse-toggle {
  position: absolute;
  z-index: 3;
  right: -14px;
  top: 84px;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  color: var(--text-secondary);
  background: var(--surface-elevated);
  box-shadow: var(--shadow-small);
  backdrop-filter: blur(16px);
}
.rail-collapse-toggle:hover {
  color: var(--accent);
  border-color: var(--border-accent);
  background: var(--surface-primary);
}
.mobile-bar,
.mobile-rail,
.rail-scrim { display: none; }
.workspace-fade-enter-active,
.workspace-fade-leave-active {
  transition:
    opacity var(--duration-normal) var(--ease-standard),
    transform var(--duration-normal) var(--ease-out);
}
.workspace-fade-enter-from { opacity: 0; transform: translateY(4px); }
.workspace-fade-leave-to { opacity: 0; transform: translateY(-2px); }
.course-creator-form { display: grid; gap: 18px; }
.creator-kicker { color: var(--accent); font-size: var(--font-caption); font-weight: 600; }
.course-creator-form label { display: grid; gap: 6px; }
.course-creator-form label > span {
  color: var(--text-secondary);
  font-size: var(--font-secondary);
  font-weight: 600;
}
.course-creator-form input,
.course-creator-form textarea {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border-strong);
  border-radius: 14px;
  background: var(--surface-card);
  font-size: 14px;
}
.course-creator-form textarea { resize: vertical; line-height: 1.55; }
.course-creator-form input:focus,
.course-creator-form textarea:focus {
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}
.creator-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(120px, .7fr);
  gap: 12px;
}
.course-creator-form footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 3px;
}
.creator-cancel,
.creator-submit {
  min-height: var(--control-lg);
  padding: 0 18px;
  border-radius: 13px;
  font-size: 14px;
  font-weight: 600;
}
.creator-cancel {
  color: var(--text-secondary);
  border: 1px solid var(--border-strong);
  background: var(--surface-card);
}
.creator-submit {
  color: var(--text-inverse);
  background: var(--gradient-brand);
  box-shadow: var(--shadow-brand);
}
.creator-submit:disabled { opacity: .45; }

@media (max-width: 820px) {
  .ai-shell { display: block; padding-top: 52px; }
  .desktop-rail,
  .rail-collapse-toggle { display: none; }
  .ai-main { min-height: calc(100dvh - 52px); }
  .mobile-bar {
    position: fixed;
    inset: 0 0 auto;
    z-index: 45;
    height: 52px;
    display: grid;
    grid-template-columns: 40px auto minmax(0, 1fr);
    align-items: center;
    gap: 9px;
    padding: 0 10px;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--surface-glass);
    backdrop-filter: blur(22px) saturate(1.25);
  }
  .mobile-bar > span {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--text-primary);
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
  }
  .mobile-bar > span svg { color: var(--accent); }
  .mobile-bar .mobile-course {
    overflow: hidden;
    justify-self: end;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 500;
    text-overflow: ellipsis;
  }
  .mobile-icon {
    width: 40px;
    height: 40px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    color: var(--text-secondary);
  }
  .mobile-rail {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 70;
    display: block;
  }
  .mobile-rail :deep(.course-rail) { width: min(290px, 84vw); }
  .rail-scrim {
    position: fixed;
    inset: 0;
    z-index: 65;
    display: block;
    width: 100%;
    background: rgba(20, 22, 28, .28);
    backdrop-filter: blur(4px);
  }
  .rail-slide-enter-active,
  .rail-slide-leave-active { transition: transform var(--duration-normal) var(--ease-out); }
  .rail-slide-enter-from,
  .rail-slide-leave-to { transform: translateX(-100%); }
}

@media (prefers-reduced-motion: reduce) {
  .ai-shell,
  .desktop-rail,
  .workspace-fade-enter-active,
  .workspace-fade-leave-active,
  .rail-slide-enter-active,
  .rail-slide-leave-active { transition: none; }
}

@media (max-width: 520px) {
  .creator-grid { grid-template-columns: 1fr; }
  .course-creator-form footer { flex-direction: column-reverse; }
  .creator-cancel,
  .creator-submit { width: 100%; }
}
</style>
