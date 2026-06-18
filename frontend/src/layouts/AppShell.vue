<script setup>
import { useAuthStore } from '../stores/auth'
import { useWorkspaceStore } from '../stores/workspace'
import { useRouter } from 'vue-router'
import { computed, onMounted } from 'vue'
import {
  LayoutDashboard,
  UserRound,
  BookOpen,
  FileText,
  PencilLine,
  CalendarDays,
  CheckSquare,
  Bot,
  History,
  LogOut,
  Globe
} from 'lucide-vue-next'

const auth = useAuthStore()
const workspace = useWorkspaceStore()
const router = useRouter()

const navItems = computed(() => [
  { path: '/overview', label: '总览', icon: LayoutDashboard },
  { path: '/profile', label: '学生画像', icon: UserRound, status: workspace.profile ? 'done' : 'empty' },
  { path: '/materials', label: '课程知识库', icon: BookOpen, status: workspace.materialsTotal > 0 ? 'done' : 'empty' },
  { path: '/resources', label: '学习资源', icon: FileText, status: workspace.resourcesTotal > 0 ? 'done' : 'empty' },
  { path: '/external-resources', label: '联网搜索', icon: Globe },
  { path: '/quizzes', label: '练习与评估', icon: PencilLine, status: workspace.quizzesTotal > 0 ? 'done' : 'empty' },
  { path: '/plans', label: '学习计划', icon: CalendarDays },
  { path: '/tasks', label: '任务中心', icon: CheckSquare, status: workspace.tasksTotal > 0 ? 'done' : 'empty' },
  { path: '/agent', label: 'AI 助手', icon: Bot },
  { path: '/logs', label: '操作日志', icon: History }
])

const currentPath = computed(() => router.currentRoute.value.path)

function handleLogout() {
  auth.logout()
  router.push('/login')
}

onMounted(() => {
  if (auth.isLoggedIn) {
    workspace.loadOverview()
  }
})
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-brand">
        <span class="brand-mark">A3</span>
        <div class="brand-text">
          <strong>学习工作台</strong>
        </div>
      </div>

      <div class="header-tools">
        <span class="username">{{ auth.username }}</span>
        <button type="button" class="btn btn-ghost btn-sm" @click="handleLogout">
          <LogOut :size="16" />
          <span>退出</span>
        </button>
      </div>
    </header>

    <div class="app-body">
      <nav class="app-sidebar">
        <div class="nav-list">
          <router-link
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: currentPath === item.path }"
          >
            <component :is="item.icon" :size="18" class="nav-icon" />
            <span class="nav-label">{{ item.label }}</span>
            <span
              v-if="item.status"
              class="nav-status"
              :class="`nav-status-${item.status}`"
            ></span>
          </router-link>
        </div>
      </nav>

      <main class="app-main">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background-color: var(--color-bg);
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  height: 56px;
  padding: 0 1.25rem;
  background-color: var(--color-surface);
  border-bottom: 1px solid var(--color-line);
}

.app-brand {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  min-width: 0;
}

.brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background-color: var(--color-primary);
  color: white;
  font-weight: 700;
  font-size: 0.75rem;
  border-radius: var(--radius-sm);
}

.brand-text strong {
  font-size: 0.9375rem;
  font-weight: 600;
}

.header-tools {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
  flex-shrink: 1;
}

.username {
  font-size: 0.8125rem;
  color: var(--color-text-soft);
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-body {
  display: flex;
  flex: 1;
}

.app-sidebar {
  width: 220px;
  background-color: var(--color-surface);
  border-right: 1px solid var(--color-line);
  padding: 0.75rem 0;
  overflow-y: auto;
  flex-shrink: 0;
}

.app-main {
  flex: 1;
  padding: 1.5rem;
  overflow-y: auto;
  min-width: 0;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: 0 0.5rem;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  color: var(--color-text-soft);
  text-decoration: none;
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.15s ease;
  position: relative;
}

.nav-item:hover {
  background-color: rgba(0, 0, 0, 0.04);
  color: var(--color-text);
  text-decoration: none;
}

.nav-item.active {
  background-color: rgba(37, 92, 79, 0.08);
  color: var(--color-primary);
}

.nav-icon {
  flex-shrink: 0;
  opacity: 0.7;
}

.nav-item.active .nav-icon {
  opacity: 1;
}

.nav-label {
  flex: 1;
  white-space: nowrap;
}

.nav-status {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.nav-status-done {
  background-color: var(--color-primary);
}

.nav-status-empty {
  background-color: var(--color-line);
}

@media (max-width: 1024px) {
  .app-sidebar {
    width: 180px;
  }
}

@media (max-width: 768px) {
  .app-header {
    padding: 0 1rem;
  }

  .brand-text strong {
    display: block;
    max-width: 6.5rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .username {
    max-width: 7.25rem;
  }

  .app-body {
    flex-direction: column;
  }

  .app-sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--color-line);
    padding: 0.5rem 0;
  }

  .nav-list {
    flex-direction: row;
    overflow-x: auto;
    padding: 0 0.5rem;
    gap: 0.25rem;
  }

  .nav-item {
    padding: 0.5rem 0.625rem;
    font-size: 0.8125rem;
    white-space: nowrap;
  }

  .nav-status {
    display: none;
  }

  .app-main {
    padding: 1rem;
  }
}
</style>
