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
      { path: '', redirect: '/home' },
      {
        path: 'home',
        name: 'home',
        component: () => import('../features/adaptive/AdaptiveHomePage.vue')
      },
      {
        path: 'learn/:courseId(\\d+)',
        name: 'course-ai-workspace',
        component: () => import('../features/adaptive/AdaptiveTutorPage.vue')
      },
      {
        path: 'progress/:courseId(\\d+)',
        name: 'course-progress',
        component: () => import('../features/adaptive/AdaptiveTutorPage.vue'),
        props: { pageMode: 'progress' }
      },
      {
        path: 'materials/:courseId(\\d+)',
        name: 'course-materials',
        component: () => import('../features/adaptive/AdaptiveTutorPage.vue'),
        props: { pageMode: 'sources' }
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('../features/settings/SettingsPage.vue')
      },
      // Keep old bookmarks working without loading retired product UIs.
      { path: 'today', redirect: '/home' },
      { path: 'courses', name: 'legacy-courses', redirect: '/home' },
      { path: 'agent', name: 'legacy-agent', redirect: '/home' },
      { path: 'progress', name: 'legacy-progress', redirect: '/home' },
      { path: 'materials', name: 'legacy-materials', redirect: '/home' },
      { path: 'resources', name: 'legacy-resources', redirect: '/home' },
      { path: 'quizzes', name: 'legacy-quizzes', redirect: '/home' },
      { path: 'plans', name: 'legacy-plans', redirect: '/home' },
      { path: 'tasks', name: 'legacy-tasks', redirect: '/home' },
      { path: 'overview', redirect: '/home' },
      { path: 'profile', redirect: '/settings' }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach(async to => {
  if (to.name === 'course-ai-workspace') {
    const courseId = to.params.courseId
    if (to.query.view === 'progress' || to.query.panel === 'progress') return `/progress/${courseId}`
    if (to.query.view === 'sources' || to.query.panel === 'materials') return `/materials/${courseId}`
  }

  const auth = useAuthStore()
  await auth.restore()

  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { path: '/login', query: { redirect: safePostLoginRoute(to.fullPath) || '/home' } }
  }
  if (to.meta.guest && auth.isLoggedIn) {
    return safePostLoginRoute(to.query.redirect) || '/home'
  }

  return true
})

export default router
