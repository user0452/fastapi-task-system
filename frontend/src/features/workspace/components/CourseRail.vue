<script setup>
import { CalendarCheck2, LogOut, Plus, Settings, Sparkles, X } from 'lucide-vue-next'


defineProps({
  courses: { type: Array, default: () => [] },
  currentId: { type: Number, default: null },
  username: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  mobile: { type: Boolean, default: false },
  collapsed: { type: Boolean, default: false }
})

defineEmits(['create', 'logout', 'close'])

const tones = ['jade', 'blue', 'amber', 'coral', 'violet', 'teal']

function tone(index) {
  return tones[index % tones.length]
}

function initial(name) {
  return String(name || '课').trim().slice(0, 1).toUpperCase()
}

function roadmapLine(course) {
  const summary = course.roadmap_summary
  if (!summary) return `${course.daily_minutes} 分钟/天 · 持续学习`
  if (summary.status === 'failed') return '路线生成失败 · 可在计划页重试'
  if (['pending', 'generating'].includes(summary.status)) return '正在生成长期学习路线'
  if (!summary.current_stage_name) return '长期路线已完成'
  const overall = Math.round(summary.overall_progress ?? summary.current_stage_progress ?? 0)
  return `${summary.current_stage_name} · 总进度 ${overall}%`
}
</script>

<template>
  <aside class="course-rail" :class="{ collapsed }" aria-label="课程助手">
    <header class="rail-brand">
      <span class="brand-mark"><Sparkles :size="17" /></span>
      <div>
        <strong>A3 学习 AI</strong>
        <span>专属课程工作台</span>
      </div>
      <button v-if="mobile" class="rail-icon" type="button" title="关闭课程栏" aria-label="关闭课程栏" @click="$emit('close')">
        <X :size="18" />
      </button>
    </header>

    <nav class="rail-navigation">
      <router-link to="/today" class="today-link" active-class="active" title="今日总览" @click="$emit('close')">
        <CalendarCheck2 :size="19" />
        <span>
          <strong>今日总览</strong>
          <small>所有课程</small>
        </span>
      </router-link>

      <div class="rail-section-heading">
        <span>课程助手</span>
        <button class="rail-icon" type="button" title="新建课程" aria-label="新建课程" @click="$emit('create')">
          <Plus :size="18" />
        </button>
      </div>

      <div class="course-links">
        <span v-if="loading" class="rail-state">正在加载课程</span>
        <span v-else-if="error" class="rail-state rail-error">课程读取失败，请刷新页面</span>
        <span v-else-if="!courses.length" class="rail-state">还没有课程</span>
        <router-link
          v-for="(course, index) in courses"
          :key="course.id"
          :to="`/learn/${course.id}`"
          class="course-link"
          :class="{ selected: Number(currentId) === Number(course.id) }"
          :title="course.name"
          @click="$emit('close')"
        >
          <span class="course-glyph" :class="tone(index)">{{ initial(course.name) }}</span>
          <span class="course-copy">
            <strong>{{ course.name }}</strong>
            <small>{{ roadmapLine(course) }}</small>
            <span
              v-if="Number(currentId) === Number(course.id) && course.roadmap_summary?.status === 'ready'"
              class="course-progress"
              role="progressbar"
              :aria-label="`${course.name} 当前路线总进度`"
              :aria-valuenow="Math.round(course.roadmap_summary.overall_progress ?? course.roadmap_summary.current_stage_progress ?? 0)"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <i :style="{ width: `${course.roadmap_summary.overall_progress ?? course.roadmap_summary.current_stage_progress ?? 0}%` }"></i>
            </span>
          </span>
        </router-link>
      </div>
    </nav>

    <footer class="rail-footer">
      <router-link to="/settings" class="settings-link" active-class="active" title="设置" @click="$emit('close')">
        <Settings :size="18" />
        <span>设置</span>
      </router-link>
      <div class="rail-user">
        <span class="user-avatar">{{ initial(username || 'U') }}</span>
        <strong>{{ username || '学习者' }}</strong>
        <button class="rail-icon" type="button" title="退出登录" aria-label="退出登录" @click="$emit('logout')">
          <LogOut :size="17" />
        </button>
      </div>
    </footer>
  </aside>
</template>

<style scoped>
.course-rail {
  width: 264px;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--text-primary);
  border-right: 1px solid var(--border-subtle);
  background: rgba(247, 247, 249, .84);
  backdrop-filter: blur(24px) saturate(1.15);
  transition: width var(--duration-normal) var(--ease-out);
}
.course-rail.collapsed { width: 76px; }
.rail-brand { height: 76px; display: flex; align-items: center; gap: 11px; padding: 0 16px; }
.brand-mark { width: 38px; height: 38px; flex: 0 0 38px; display: grid; place-items: center; border-radius: 13px; color: #fff; background: var(--gradient-brand); box-shadow: 0 8px 22px rgba(79, 124, 255, .22); }
.rail-brand > div { min-width: 0; display: grid; gap: 2px; white-space: nowrap; }
.rail-brand strong { font-size: 15px; font-weight: 650; letter-spacing: -.01em; }
.rail-brand span:not(.brand-mark) { color: var(--text-tertiary); font-size: 12px; }
.rail-brand > .rail-icon { margin-left: auto; }
.rail-navigation { min-height: 0; flex: 1; overflow-y: auto; padding: 8px 10px 16px; }
.today-link,
.course-link,
.settings-link { display: flex; align-items: center; color: var(--text-secondary); border-radius: 13px; transition: color var(--duration-fast) ease, background var(--duration-fast) ease; }
.today-link { min-height: 52px; gap: 11px; padding: 7px 11px; }
.today-link > span { display: grid; min-width: 0; }
.today-link strong { color: var(--text-primary); font-size: 14px; font-weight: 580; }
.today-link small { color: var(--text-tertiary); font-size: 12px; }
.today-link:hover,
.today-link.active { color: var(--accent); background: var(--accent-soft); }
.today-link.active strong { color: #1f5ec8; }
.rail-section-heading { height: 48px; display: flex; align-items: center; justify-content: space-between; padding: 13px 5px 5px 11px; color: var(--text-tertiary); font-size: 12px; font-weight: 600; }
.rail-icon { width: 38px; height: 38px; display: grid; place-items: center; flex: 0 0 38px; border-radius: 12px; color: var(--text-secondary); }
.rail-icon:hover { color: var(--accent); background: var(--accent-soft); }
.course-links { display: grid; gap: 3px; }
.course-link { min-height: 64px; gap: 11px; padding: 8px 10px; }
.course-link:hover { background: rgba(0, 0, 0, .04); }
.course-link.selected { color: #1f5ec8; background: linear-gradient(135deg, rgba(52, 120, 246, .14), rgba(109, 93, 252, .08)); }
.course-glyph { width: 36px; height: 36px; flex: 0 0 36px; display: grid; place-items: center; border-radius: 12px; font-size: 13px; font-weight: 650; }
.course-glyph.jade { color: #397064; background: #dfebe8; }
.course-glyph.blue { color: #466b86; background: #e1ebf2; }
.course-glyph.amber { color: #846c3e; background: #f2ead8; }
.course-glyph.coral { color: #855c58; background: #f0e2df; }
.course-glyph.violet { color: #6b5e82; background: #e9e4f0; }
.course-glyph.teal { color: #4d7473; background: #dfecec; }
.course-copy { min-width: 0; flex: 1; display: grid; gap: 3px; }
.course-copy strong,
.course-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.course-copy strong { color: var(--text-primary); font-size: 14px; font-weight: 580; }
.course-copy small { color: var(--text-tertiary); font-size: 12px; }
.course-progress { width: 100%; height: 3px; overflow: hidden; border-radius: 999px; background: rgba(52, 120, 246, .13); }
.course-progress i { display: block; height: 100%; border-radius: inherit; background: var(--gradient-blue-cyan); transition: width var(--duration-normal) var(--ease-out); }
.course-link.selected .course-copy strong { color: #1f5ec8; }
.rail-state { padding: 20px 10px; color: var(--text-tertiary); font-size: 12px; text-align: center; }
.rail-error { color: var(--danger); }
.rail-footer { padding: 10px 10px 14px; border-top: 1px solid var(--border-subtle); }
.settings-link { height: 44px; gap: 11px; padding: 0 11px; font-size: 13px; font-weight: 560; }
.settings-link:hover,
.settings-link.active { color: var(--accent); background: var(--accent-soft); }
.rail-user { min-width: 0; display: grid; grid-template-columns: 36px minmax(0, 1fr) 38px; align-items: center; gap: 9px; margin-top: 7px; padding: 10px 2px 0; border-top: 1px solid var(--border-subtle); }
.user-avatar { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 50%; color: #53647d; background: #e4e8ef; font-size: 13px; font-weight: 650; }
.rail-user strong { overflow: hidden; color: var(--text-secondary); font-size: 13px; font-weight: 550; text-overflow: ellipsis; white-space: nowrap; }
.collapsed .rail-brand { justify-content: center; padding-inline: 0; }
.collapsed .rail-brand > div,
.collapsed .rail-brand > .rail-icon,
.collapsed .today-link > span,
.collapsed .rail-section-heading > span,
.collapsed .course-copy,
.collapsed .settings-link > span,
.collapsed .rail-user strong,
.collapsed .rail-user > .rail-icon { display: none; }
.collapsed .rail-navigation { padding-inline: 10px; }
.collapsed .today-link,
.collapsed .course-link,
.collapsed .settings-link { justify-content: center; padding-inline: 0; }
.collapsed .rail-section-heading { justify-content: center; padding-inline: 0; }
.collapsed .rail-footer { padding-inline: 10px; }
.collapsed .rail-user { display: flex; justify-content: center; padding-inline: 0; }

@media (prefers-reduced-motion: reduce) {
  .course-rail,
  .course-progress i { transition: none; }
}
</style>
