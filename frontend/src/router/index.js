import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

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
      {
        path: '',
        redirect: '/overview'
      },
      {
        path: 'overview',
        name: 'overview',
        component: () => import('../pages/OverviewPage.vue')
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('../pages/ProfilePage.vue')
      },
      {
        path: 'materials',
        name: 'materials',
        component: () => import('../pages/MaterialsPage.vue')
      },
      {
        path: 'agent',
        name: 'agent',
        component: () => import('../pages/AgentPage.vue')
      },
      {
        path: 'resources',
        name: 'resources',
        component: () => import('../pages/ResourcesPage.vue')
      },
      {
        path: 'external-resources',
        name: 'external-resources',
        component: () => import('../pages/ExternalResourcesPage.vue')
      },
      {
        path: 'quizzes',
        name: 'quizzes',
        component: () => import('../pages/QuizzesPage.vue')
      },
      {
        path: 'plans',
        name: 'plans',
        component: () => import('../pages/PlanPage.vue')
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('../pages/TasksPage.vue')
      },
      {
        path: 'logs',
        name: 'logs',
        component: () => import('../pages/LogsPage.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()

  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    next('/login')
  } else if (to.meta.guest && auth.isLoggedIn) {
    next('/overview')
  } else {
    next()
  }
})

export default router
