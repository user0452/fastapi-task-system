<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCourseStore } from '../../stores/course'
import CourseInspector from './components/CourseInspector.vue'
import WorkspaceChat from './components/WorkspaceChat.vue'


const route = useRoute()
const router = useRouter()
const courses = useCourseStore()
const chat = ref(null)
const refreshKey = ref(0)
const validPanels = new Set([
  'overview', 'today', 'diagnostic', 'knowledge', 'plan', 'practice', 'wrong', 'materials', 'memory'
])

const courseId = computed(() => Number(route.params.courseId))
const course = computed(() => courses.courses.find(item => Number(item.id) === courseId.value) || courses.current)
const activePanel = computed(() => validPanels.has(String(route.query.panel)) ? String(route.query.panel) : '')
const inspectorOpen = computed(() => Boolean(activePanel.value))

async function openPanel(panel) {
  const selected = validPanels.has(panel) ? panel : 'overview'
  await router.replace({ path: route.path, query: { ...route.query, panel: selected } })
}

async function closePanel() {
  const query = { ...route.query }
  delete query.panel
  await router.replace({ path: route.path, query })
}

async function promptChat(prompt) {
  if (window.innerWidth <= 820) await closePanel()
  await chat.value?.send(prompt)
}

function dataChanged() {
  refreshKey.value += 1
}

onMounted(async () => {
  await courses.ensureLoaded()
  const exists = courses.courses.some(item => Number(item.id) === courseId.value)
  if (!exists) {
    await router.replace('/today')
    return
  }
  await courses.select(courseId.value)
})

// AppShell remounts this view for a course route, but keep this explicit as
// well: it also covers an in-place route update and ensures the course store
// has selected the same course as the chat's `courseId` prop.
watch(courseId, async id => {
  if (!id || !courses.courses.some(item => Number(item.id) === id)) return
  await courses.select(id)
})
</script>

<template>
  <div v-if="course" class="course-ai-workspace" :class="{ 'inspector-open': inspectorOpen }">
    <WorkspaceChat
      :key="`workspace-chat-${courseId}`"
      ref="chat"
      :course-id="courseId"
      :course="course"
      @open-panel="openPanel"
      @data-changed="dataChanged"
    />

    <transition name="inspector-slide">
      <div v-if="inspectorOpen" class="inspector-host">
        <CourseInspector
          :course-id="courseId"
          :active-panel="activePanel"
          :refresh-key="refreshKey"
          @close="closePanel"
          @change-panel="openPanel"
          @prompt="promptChat"
          @data-changed="dataChanged"
        />
      </div>
    </transition>
    <button v-if="inspectorOpen" class="inspector-scrim" type="button" aria-label="关闭课程面板" @click="closePanel"></button>
  </div>
</template>

<style scoped>
.course-ai-workspace { position: relative; height: 100dvh; display: grid; grid-template-columns: minmax(0, 1fr); overflow: hidden; }
.course-ai-workspace.inspector-open { grid-template-columns: minmax(420px, 1fr) 410px; }
.inspector-host { position: relative; z-index: 20; }
.inspector-scrim { display: none; }
.inspector-slide-enter-active,
.inspector-slide-leave-active { transition: opacity 170ms ease, transform 170ms ease; }
.inspector-slide-enter-from,
.inspector-slide-leave-to { opacity: 0; transform: translateX(18px); }
@media (max-width: 1180px) {
  .course-ai-workspace.inspector-open { grid-template-columns: minmax(0, 1fr); }
  .inspector-host { position: absolute; inset: 0 0 0 auto; z-index: 30; }
  .inspector-scrim { position: absolute; inset: 0; z-index: 25; display: block; width: 100%; background: rgba(25, 34, 29, .18); }
}
@media (max-width: 820px) {
  .course-ai-workspace { height: calc(100dvh - 52px); }
  .inspector-host { inset: 0; background: #f8faf8; }
  .inspector-scrim { display: none; }
  .inspector-slide-enter-active,
  .inspector-slide-leave-active { transition: transform 180ms ease; }
  .inspector-slide-enter-from,
  .inspector-slide-leave-to { opacity: 1; transform: translateX(100%); }
}
</style>
