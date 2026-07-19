<script setup>
import { computed } from 'vue'
import {
  BookOpen,
  Brain,
  CalendarCheck2,
  CalendarRange,
  ChartNoAxesColumn,
  ClipboardCheck,
  CircleX,
  LayoutDashboard,
  Network,
  X
} from 'lucide-vue-next'
import OverviewPanel from '../panels/OverviewPanel.vue'
import KnowledgePanel from '../panels/KnowledgePanel.vue'
import PlanPanel from '../panels/PlanPanel.vue'
import PracticePanel from '../panels/PracticePanel.vue'
import WrongAnswersPanel from '../panels/WrongAnswersPanel.vue'
import MaterialsResourcesPanel from '../panels/MaterialsResourcesPanel.vue'
import MemoryPanel from '../panels/MemoryPanel.vue'
import DiagnosticWorkspace from '../../courses/components/DiagnosticWorkspace.vue'
import TodayPage from '../../today/TodayPage.vue'


const props = defineProps({
  courseId: { type: Number, required: true },
  activePanel: { type: String, default: 'overview' },
  refreshKey: { type: Number, default: 0 }
})
const emit = defineEmits(['close', 'change-panel', 'prompt', 'data-changed'])

// Flat, ordered nav — group labels made the rail noisy without adding path clarity.
const tabs = [
  { id: 'overview', label: '概览', icon: LayoutDashboard, component: OverviewPanel },
  { id: 'today', label: '今日', icon: CalendarCheck2, component: TodayPage },
  { id: 'plan', label: '路线', icon: CalendarRange, component: PlanPanel },
  { id: 'practice', label: '练习', icon: ChartNoAxesColumn, component: PracticePanel },
  { id: 'diagnostic', label: '诊断', icon: ClipboardCheck, component: DiagnosticWorkspace },
  { id: 'knowledge', label: '知识点', icon: Network, component: KnowledgePanel },
  { id: 'wrong', label: '错题', icon: CircleX, component: WrongAnswersPanel },
  { id: 'materials', label: '资料', icon: BookOpen, component: MaterialsResourcesPanel },
  { id: 'memory', label: '记忆', icon: Brain, component: MemoryPanel }
]

const current = computed(() => tabs.find(tab => tab.id === props.activePanel) || tabs[0])
</script>

<template>
  <aside class="course-inspector">
    <header class="inspector-header">
      <div class="header-copy">
        <span class="eyebrow">课程面板</span>
        <strong>{{ current.label }}</strong>
      </div>
      <button
        type="button"
        class="close-button"
        title="关闭课程面板"
        aria-label="关闭课程面板"
        @click="$emit('close')"
      ><X :size="18" /></button>
    </header>

    <nav class="inspector-nav" aria-label="课程面板导航">
      <div class="nav-track" role="tablist" aria-label="课程视图">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          role="tab"
          class="nav-item"
          :aria-selected="activePanel === tab.id"
          :title="tab.label"
          :class="{ active: activePanel === tab.id }"
          @click="$emit('change-panel', tab.id)"
        >
          <component :is="tab.icon" :size="15" />
          <span>{{ tab.label }}</span>
        </button>
      </div>
    </nav>

    <div class="inspector-content">
      <KeepAlive>
        <component
          :is="current.component"
          :key="`${courseId}:${current.id}`"
          :course-id="courseId"
          :refresh-key="refreshKey"
          @change-panel="panel => emit('change-panel', panel)"
          @completed="emit('data-changed')"
          @prompt="prompt => emit('prompt', prompt)"
          @data-changed="emit('data-changed')"
        />
      </KeepAlive>
    </div>
  </aside>
</template>

<style scoped>
.course-inspector {
  width: var(--inspector-width);
  height: 100dvh;
  display: grid;
  grid-template-rows: 64px 56px minmax(0, 1fr);
  overflow: hidden;
  border-left: 1px solid var(--border-subtle);
  background: var(--surface-primary);
  box-shadow: var(--shadow-panel);
}

.inspector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 16px 0 18px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-primary);
}

.header-copy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.eyebrow {
  color: var(--text-tertiary);
  font-size: var(--font-caption);
  font-weight: 600;
}

.header-copy strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 18px;
  font-weight: var(--weight-semibold);
  letter-spacing: var(--tracking-snug);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.close-button {
  width: var(--control-md);
  height: var(--control-md);
  display: grid;
  place-items: center;
  flex: 0 0 var(--control-md);
  border-radius: var(--radius-small);
  color: var(--text-secondary);
}

.close-button:hover {
  color: var(--accent);
  background: var(--accent-soft);
}

.inspector-nav {
  min-width: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-secondary);
}

.nav-track {
  height: 100%;
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  padding: 0 12px;
  scrollbar-width: none;
}

.nav-track::-webkit-scrollbar {
  display: none;
}

.nav-item {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 0 12px;
  border-radius: var(--radius-round);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: var(--weight-medium);
  white-space: nowrap;
}

.nav-item:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}

.nav-item.active {
  color: var(--accent);
  background: var(--surface-primary);
  box-shadow: var(--shadow-small), inset 0 0 0 1px var(--border-accent);
}

.inspector-content {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 18px 16px 28px;
  background: var(--surface-secondary);
}

/* Give every nested panel a calmer default rhythm without editing each one. */
.inspector-content :deep(.overview-panel),
.inspector-content :deep(.practice-panel-view),
.inspector-content :deep(.memory-panel),
.inspector-content :deep(.plan-panel),
.inspector-content :deep(.knowledge-panel),
.inspector-content :deep(.materials-panel),
.inspector-content :deep(.wrong-panel),
.inspector-content :deep(.today-page),
.inspector-content :deep(.diagnostic-workspace) {
  display: grid;
  gap: 16px;
}

.inspector-content :deep(.panel-heading h3),
.inspector-content :deep(.memory-heading h2),
.inspector-content :deep(h2),
.inspector-content :deep(h3) {
  letter-spacing: var(--tracking-snug);
}

.inspector-content :deep(.metric-band),
.inspector-content :deep(.practice-metrics),
.inspector-content :deep(.materials-metrics),
.inspector-content :deep(.memory-metrics),
.inspector-content :deep(.next-block) {
  border-radius: var(--radius-medium);
  background: var(--surface-primary);
  box-shadow: var(--shadow-small);
}

.inspector-content :deep(.route-snapshot),
.inspector-content :deep(.mastery-snapshot),
.inspector-content :deep(.change-snapshot),
.inspector-content :deep(.course-rhythm),
.inspector-content :deep(.trend-section),
.inspector-content :deep(.distribution-section) {
  gap: 10px;
  padding: 14px 14px 16px;
  border: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
  border-radius: var(--radius-medium);
  background: var(--surface-primary);
  box-shadow: var(--shadow-small);
}

.inspector-content :deep(.status-list) {
  gap: 6px;
}

.inspector-content :deep(.status-list button) {
  min-height: 48px;
  padding: 0 12px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-medium);
  background: var(--surface-primary);
}

.inspector-content :deep(.status-list button:hover) {
  border-color: var(--border-accent);
  background: var(--accent-softer);
}

@media (max-width: 1180px) {
  .course-inspector {
    box-shadow: -12px 0 36px rgba(18, 22, 34, .12);
  }
}

@media (max-width: 820px) {
  .course-inspector {
    width: 100vw;
    height: calc(100dvh - 52px);
    border-left: 0;
  }

  .inspector-content {
    padding: 16px 14px 24px;
  }
}
</style>
