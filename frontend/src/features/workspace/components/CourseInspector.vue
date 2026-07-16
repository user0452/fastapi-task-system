<script setup>
import { computed } from 'vue'
import {
  BookOpen,
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
import DiagnosticWorkspace from '../../courses/components/DiagnosticWorkspace.vue'
import TodayPage from '../../today/TodayPage.vue'


const props = defineProps({
  courseId: { type: Number, required: true },
  activePanel: { type: String, default: 'overview' },
  refreshKey: { type: Number, default: 0 }
})
const emit = defineEmits(['close', 'change-panel', 'prompt', 'data-changed'])

const tabs = [
  { id: 'overview', label: '概览', icon: LayoutDashboard, component: OverviewPanel },
  { id: 'today', label: '今日', icon: CalendarCheck2, component: TodayPage },
  { id: 'diagnostic', label: '诊断', icon: ClipboardCheck, component: DiagnosticWorkspace },
  { id: 'knowledge', label: '知识点', icon: Network, component: KnowledgePanel },
  { id: 'plan', label: '计划', icon: CalendarRange, component: PlanPanel },
  { id: 'practice', label: '练习', icon: ChartNoAxesColumn, component: PracticePanel },
  { id: 'wrong', label: '错题', icon: CircleX, component: WrongAnswersPanel },
  { id: 'materials', label: '资料', icon: BookOpen, component: MaterialsResourcesPanel }
]

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
    <div class="inspector-tabs" role="tablist" aria-label="课程二级视图">
      <button
        v-for="tab in tabs"
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
.course-inspector { width: 410px; height: 100dvh; display: grid; grid-template-rows: 58px 48px minmax(0, 1fr); overflow: hidden; background: #f8faf8; border-left: 1px solid #dce2de; box-shadow: -8px 0 24px rgba(31, 43, 37, .035); }
.inspector-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 12px 0 15px; border-bottom: 1px solid #e0e4e1; background: #fff; }
.inspector-header > div { display: grid; gap: 1px; }
.inspector-header span { color: #858e89; font-size: 9px; }
.inspector-header strong { color: #34413a; font-size: 13px; }
.inspector-header button { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 6px; color: #68736d; }
.inspector-header button:hover { color: #176b58; background: #edf1ee; }
.inspector-tabs { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); padding: 4px 6px 0; border-bottom: 1px solid #dfe4e1; background: #fff; }
.inspector-tabs button { min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; color: #7a847f; border-bottom: 2px solid transparent; font-size: 9px; }
.inspector-tabs button:hover { color: #3f6f60; }
.inspector-tabs button.active { color: #176b58; border-bottom-color: #176b58; }
.inspector-content { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 16px 15px 28px; }
@media (max-width: 1180px) {
  .course-inspector { box-shadow: -12px 0 36px rgba(25, 35, 30, .12); }
}
@media (max-width: 820px) {
  .course-inspector { width: 100vw; height: calc(100dvh - 52px); }
}
</style>
