import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { safePostLoginRoute } from './redirect'


const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../pages/LoginPage.vue'),
    meta: { guest: true }
  },
  {
    path: '/',
    component: () => import('../layouts/AppShell.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/today' },
      {
        path: 'today',
        name: 'today',
        component: () => import('../features/adaptive/AdaptiveHomePage.vue')
      },
      {
        path: 'learn/:courseId(\\d+)',
        name: 'course-ai-workspace',
        component: () => import('../features/adaptive/AdaptiveTutorPage.vue')
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('../features/settings/SettingsPage.vue')
      },
      // Keep bookmarks working without loading any retired roadmap/resource/agent UI.
      { path: 'courses', name: 'legacy-courses', redirect: '/today' },
      { path: 'agent', name: 'legacy-agent', redirect: '/today' },
      { path: 'progress', name: 'legacy-progress', redirect: '/today' },
      { path: 'materials', name: 'legacy-materials', redirect: '/today' },
      { path: 'resources', name: 'legacy-resources', redirect: '/today' },
      { path: 'quizzes', name: 'legacy-quizzes', redirect: '/today' },
      { path: 'plans', name: 'legacy-plans', redirect: '/today' },
      { path: 'tasks', name: 'legacy-tasks', redirect: '/today' },
      { path: 'overview', redirect: '/today' },
      { path: 'profile', redirect: '/settings' }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach(async to => {
  const auth = useAuthStore()
  await auth.restore()

  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { path: '/login', query: { redirect: safePostLoginRoute(to.fullPath) || '/today' } }
  }
  if (to.meta.guest && auth.isLoggedIn) {
    return safePostLoginRoute(to.query.redirect) || '/today'
  }

  return true
})

export default router
