import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useCourseStore } from '../stores/course'
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
      {
        path: 'logs',
        name: 'logs',
        component: () => import('../pages/LogsPage.vue')
      },
      { path: 'courses', name: 'legacy-courses', component: () => import('../features/today/GlobalTodayPage.vue'), meta: { legacyPanel: 'materials' } },
      { path: 'agent', name: 'legacy-agent', component: () => import('../features/today/GlobalTodayPage.vue'), meta: { legacyPanel: '' } },
      { path: 'progress', name: 'legacy-progress', component: () => import('../features/today/GlobalTodayPage.vue'), meta: { legacyPanel: 'overview' } },
      { path: 'materials', name: 'legacy-materials', component: () => import('../features/today/GlobalTodayPage.vue'), meta: { legacyPanel: 'materials' } },
      { path: 'resources', name: 'legacy-resources', component: () => import('../features/today/GlobalTodayPage.vue'), meta: { legacyPanel: 'materials' } },
      { path: 'quizzes', name: 'legacy-quizzes', component: () => import('../features/today/GlobalTodayPage.vue'), meta: { legacyPanel: 'practice' } },
      { path: 'plans', name: 'legacy-plans', component: () => import('../features/today/GlobalTodayPage.vue'), meta: { legacyPanel: 'plan' } },
      { path: 'tasks', name: 'legacy-tasks', component: () => import('../features/today/GlobalTodayPage.vue'), meta: { legacyPanel: 'plan' } },
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

  if (Object.prototype.hasOwnProperty.call(to.meta, 'legacyPanel')) {
    const courses = useCourseStore()
    await courses.ensureLoaded()
    if (!courses.current?.id) return '/today'
    const query = { ...to.query }
    if (to.meta.legacyPanel) query.panel = to.meta.legacyPanel
    return { path: `/learn/${courses.current.id}`, query, replace: true }
  }
  return true
})

export default router
