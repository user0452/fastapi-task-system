import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getProfile } from '../api/profiles'
import { getMaterials } from '../api/materials'
import { getResources } from '../api/resources'
import { getQuizzes, getEvaluations } from '../api/quizzes'
import { getTasks } from '../api/tasks'

export const useWorkspaceStore = defineStore('workspace', () => {
  const profile = ref(null)
  const materialsTotal = ref(0)
  const resourcesTotal = ref(0)
  const quizzesTotal = ref(0)
  const evaluationsTotal = ref(0)
  const tasksTotal = ref(0)
  const recentMaterials = ref([])
  const recentResources = ref([])
  const recentQuizzes = ref([])
  const recentTasks = ref([])
  const loading = ref(false)

  async function loadOverview() {
    loading.value = true
    try {
      const [profileRes, materialsRes, resourcesRes, quizzesRes, evalsRes, tasksRes] =
        await Promise.all([
          getProfile(),
          getMaterials({ page: 1, size: 5 }),
          getResources({ page: 1, size: 5 }),
          getQuizzes({ page: 1, size: 5 }),
          getEvaluations({ page: 1, size: 5 }),
          getTasks({ page: 1, size: 5 })
        ])

      if (profileRes.code === 200) {
        profile.value = profileRes.data
      }
      if (materialsRes.code === 200) {
        materialsTotal.value = materialsRes.data?.total || 0
        recentMaterials.value = materialsRes.data?.list || materialsRes.data?.items || materialsRes.data || []
      }
      if (resourcesRes.code === 200) {
        resourcesTotal.value = resourcesRes.data?.total || 0
        recentResources.value = resourcesRes.data?.list || resourcesRes.data?.items || resourcesRes.data || []
      }
      if (quizzesRes.code === 200) {
        quizzesTotal.value = quizzesRes.data?.total || 0
        recentQuizzes.value = quizzesRes.data?.list || quizzesRes.data?.items || quizzesRes.data || []
      }
      if (evalsRes.code === 200) {
        evaluationsTotal.value = evalsRes.data?.total || 0
      }
      if (tasksRes.code === 200) {
        tasksTotal.value = tasksRes.data?.total || 0
        recentTasks.value = tasksRes.data?.list || tasksRes.data?.items || tasksRes.data || []
      }
    } finally {
      loading.value = false
    }
  }

  function getRecommendedAction() {
    if (!profile.value) {
      return { text: '生成学生画像', route: '/profile', desc: '先建立你的学习画像，系统将为你生成个性化内容' }
    }
    if (materialsTotal.value === 0) {
      return { text: '上传课程资料', route: '/materials', desc: '上传课程资料，构建知识库' }
    }
    if (resourcesTotal.value === 0) {
      return { text: '生成学习资源', route: '/resources', desc: '基于画像和资料生成学习资源' }
    }
    if (quizzesTotal.value === 0) {
      return { text: '生成练习题', route: '/quizzes', desc: '生成练习题检验学习成果' }
    }
    return { text: 'AI 学习助手', route: '/agent', desc: '让 AI 助手帮你规划学习' }
  }

  return {
    profile,
    materialsTotal,
    resourcesTotal,
    quizzesTotal,
    evaluationsTotal,
    tasksTotal,
    recentMaterials,
    recentResources,
    recentQuizzes,
    recentTasks,
    loading,
    loadOverview,
    getRecommendedAction
  }
})
