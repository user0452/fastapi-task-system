<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCourseStore } from '../../stores/course'


const route = useRoute()
const router = useRouter()
const courses = useCourseStore()
const message = ref('正在打开课程工作台')

onMounted(async () => {
  await courses.ensureLoaded()
  if (!courses.current?.id) {
    message.value = '请先创建或选择一门课程'
    await router.replace('/today')
    return
  }
  await router.replace({
    path: `/learn/${courses.current.id}`,
    query: { ...route.query }
  })
})
</script>

<template>
  <main class="agent-redirect" aria-live="polite">{{ message }}</main>
</template>

<style scoped>
.agent-redirect { min-height: 240px; display: grid; place-items: center; color: #65716b; font-size: 13px; }
</style>
