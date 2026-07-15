import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  createCourse as createCourseRequest,
  getCourses,
  getCurrentCourse,
  selectCourse as selectCourseRequest
} from '../api/courses'


export const useCourseStore = defineStore('course', () => {
  const courses = ref([])
  const current = ref(null)
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref('')
  // Route changes can cause both the shell and the course workspace to select
  // a course. Only the latest selection is allowed to update shared state.
  let selectionVersion = 0

  const hasCourses = computed(() => courses.value.length > 0)

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const [coursesResponse, currentResponse] = await Promise.all([
        getCourses(),
        getCurrentCourse()
      ])
      if (coursesResponse.code === 200) {
        courses.value = coursesResponse.data?.items || []
      } else {
        error.value = coursesResponse.message || '课程加载失败'
      }
      if (currentResponse.code === 200) {
        current.value = currentResponse.data || courses.value[0] || null
      }
      loaded.value = true
    } finally {
      loading.value = false
    }
    return current.value
  }

  async function ensureLoaded() {
    return loaded.value && !error.value ? current.value : load()
  }

  async function select(courseId) {
    const selectedId = Number(courseId)
    const requestVersion = ++selectionVersion
    if (!selectedId || selectedId === current.value?.id) return current.value

    const response = await selectCourseRequest(selectedId)
    if (response.code === 200) {
      if (requestVersion !== selectionVersion) return current.value
      current.value = response.data
      courses.value = courses.value.map(course => ({
        ...course,
        is_current: course.id === response.data.id
      }))
      return current.value
    }
    throw new Error(response.message || '课程切换失败')
  }

  async function create(payload) {
    const response = await createCourseRequest(payload)
    if (response.code < 200 || response.code >= 300) {
      throw new Error(response.message || '课程创建失败')
    }
    courses.value = [response.data, ...courses.value]
    if (!current.value) current.value = response.data
    return response.data
  }

  function reset() {
    courses.value = []
    current.value = null
    loaded.value = false
    error.value = ''
  }

  return {
    courses,
    current,
    loading,
    loaded,
    error,
    hasCourses,
    load,
    ensureLoaded,
    select,
    create,
    reset
  }
})
