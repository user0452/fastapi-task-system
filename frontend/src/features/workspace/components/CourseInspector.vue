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

const groups = [
  {
    label: '学习',
    tabs: [
      { id: 'overview', label: '概览', icon: LayoutDashboard, component: OverviewPanel },
      { id: 'today', label: '今日', icon: CalendarCheck2, component: TodayPage },
      { id: 'plan', label: '路线', icon: CalendarRange, component: PlanPanel },
      { id: 'practice', label: '练习', icon: ChartNoAxesColumn, component: PracticePanel }
    ]
  },
  {
    label: '知识',
    tabs: [
      { id: 'diagnostic', label: '诊断', icon: ClipboardCheck, component: DiagnosticWorkspace },
      { id: 'knowledge', label: '知识点', icon: Network, component: KnowledgePanel },
      { id: 'wrong', label: '错题', icon: CircleX, component: WrongAnswersPanel }
    ]
  },
  { label: '资料', tabs: [{ id: 'materials', label: '资料库', icon: BookOpen, component: MaterialsResourcesPanel }] },
  { label: '系统', tabs: [{ id: 'memory', label: '长期记忆', icon: Brain, component: MemoryPanel }] }
]

const tabs = groups.flatMap(group => group.tabs)
const current = computed(() => tabs.find(tab => tab.id === props.activePanel) || tabs[0])
</script>

<template>
  <aside class="course-inspector">
    <header class="inspector-header">
      <div>
        <span>课程面板</span>
        <strong>{{ current.label }}</strong>
      </div>
      <button type="button" title="关闭课程面板" aria-label="关闭课程面板" @click="$emit('close')"><X :size="18" /></button>
    </header>
    <div class="inspector-tabs" aria-label="课程二级视图">
      <section v-for="group in groups" :key="group.label" class="inspector-tab-group">
        <span>{{ group.label }}</span>
        <div role="tablist" :aria-label="group.label">
          <button
            v-for="tab in group.tabs"
            :key="tab.id"
            type="button"
            role="tab"
            :aria-selected="activePanel === tab.id"
            :title="tab.label"
            :class="{ active: activePanel === tab.id }"
            @click="$emit('change-panel', tab.id)"
          >
            <component :is="tab.icon" :size="15" />
            <span>{{ tab.label }}</span>
          </button>
        </div>
      </section>
    </div>
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
.course-inspector { width: 460px; height: 100dvh; display: grid; grid-template-rows: 78px auto minmax(0, 1fr); overflow: hidden; border-left: 1px solid var(--border-subtle); background: rgba(250, 250, 252, .96); box-shadow: -14px 0 44px rgba(0, 0, 0, .08); backdrop-filter: blur(24px); }
.inspector-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 18px 0 22px; border-bottom: 1px solid var(--border-subtle); background: rgba(255, 255, 255, .84); }
.inspector-header > div { display: grid; gap: 3px; }
.inspector-header span { color: var(--text-tertiary); font-size: 12px; }
.inspector-header strong { color: var(--text-primary); font-size: 21px; font-weight: 640; letter-spacing: -.02em; }
.inspector-header button { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 12px; color: var(--text-secondary); }
.inspector-header button:hover { color: var(--accent); background: var(--accent-soft); }
.inspector-tabs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 14px; padding: 14px 16px; border-bottom: 1px solid var(--border-subtle); background: rgba(255, 255, 255, .72); }
.inspector-tab-group { min-width: 0; display: grid; gap: 6px; }
.inspector-tab-group > span { color: var(--text-tertiary); font-size: 11px; font-weight: 600; }
.inspector-tab-group > div { display: flex; flex-wrap: wrap; gap: 4px; }
.inspector-tabs button { min-width: 0; min-height: 34px; display: inline-flex; align-items: center; justify-content: center; gap: 5px; padding: 0 8px; border-radius: 10px; color: var(--text-secondary); font-size: 12px; font-weight: 550; }
.inspector-tabs button:hover { color: var(--text-primary); background: rgba(0, 0, 0, .04); }
.inspector-tabs button.active { color: var(--accent); background: var(--accent-soft); }
.inspector-content { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 22px 20px 36px; }
@media (max-width: 1180px) {
  .course-inspector { box-shadow: -12px 0 36px rgba(25, 35, 30, .12); }
}
@media (max-width: 820px) {
  .course-inspector { width: 100vw; height: calc(100dvh - 52px); border-left: 0; }
  .inspector-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .inspector-content { padding: 20px 16px 32px; }
}
</style>
