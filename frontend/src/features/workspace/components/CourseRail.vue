<script setup>
import { BookOpenCheck, CalendarCheck2, Gauge, LogOut, Plus, Settings, Sparkles, Upload, X } from 'lucide-vue-next'


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

function courseLine(course) {
  if (course.status === 'draft') return '等待课程资料'
  if (course.status === 'preparing') return '资料处理中'
  if (course.status === 'diagnostic_pending') return '等待初始诊断'
  return `${course.daily_minutes || 25} 分钟/天`
}
</script>

<template>
  <aside class="course-rail" :class="{ collapsed }" aria-label="学习导航">
    <header class="rail-brand">
      <span class="brand-mark"><Sparkles :size="17" /></span>
      <div>
        <strong>A3 学习</strong>
        <span>你的学习空间</span>
      </div>
      <button v-if="mobile" class="rail-icon" type="button" title="关闭课程栏" aria-label="关闭课程栏" @click="$emit('close')">
        <X :size="18" />
      </button>
    </header>

    <nav class="rail-navigation">
      <router-link to="/home" class="today-link" active-class="active" title="首页" @click="$emit('close')">
        <CalendarCheck2 :size="19" />
        <span>
          <strong>首页</strong>
          <small>今天该学什么</small>
        </span>
      </router-link>

      <div v-if="currentId" class="course-section-nav" aria-label="当前课程">
        <router-link :to="`/learn/${currentId}`" class="course-section-link" active-class="active" @click="$emit('close')">
          <BookOpenCheck :size="18" /><span>学习</span>
        </router-link>
        <router-link :to="`/progress/${currentId}`" class="course-section-link" active-class="active" @click="$emit('close')">
          <Gauge :size="18" /><span>进度</span>
        </router-link>
        <router-link :to="`/materials/${currentId}`" class="course-section-link" active-class="active" @click="$emit('close')">
          <Upload :size="18" /><span>资料</span>
        </router-link>
      </div>

      <div class="rail-section-heading">
        <span>我的课程</span>
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
            <small>{{ courseLine(course) }}</small>
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
  width: var(--rail-width);
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--text-primary);
  border-right: 1px solid var(--border-subtle);
  background: var(--surface-rail);
  backdrop-filter: blur(24px) saturate(1.15);
  transition: width var(--duration-normal) var(--ease-out);
}
.course-rail.collapsed { width: var(--rail-collapsed); }
.rail-brand { height: 76px; display: flex; align-items: center; gap: 11px; padding: 0 16px; }
.brand-mark {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: grid;
  place-items: center;
  border-radius: 13px;
  color: var(--text-inverse);
  background: var(--gradient-brand);
  box-shadow: var(--shadow-brand);
}
.rail-brand > div { min-width: 0; display: grid; gap: 2px; white-space: nowrap; }
.rail-brand strong {
  font-size: 15px;
  font-weight: var(--weight-bold);
  letter-spacing: var(--tracking-snug);
}
.rail-brand span:not(.brand-mark) { color: var(--text-tertiary); font-size: 12px; }
.rail-brand > .rail-icon { margin-left: auto; }
.rail-navigation { min-height: 0; flex: 1; overflow-y: auto; padding: 8px 10px 16px; }
.today-link,
.course-link,
.course-section-link,
.settings-link {
  display: flex;
  align-items: center;
  color: var(--text-secondary);
  border-radius: 14px;
  transition:
    color var(--duration-fast) var(--ease-standard),
    background var(--duration-fast) var(--ease-standard),
    box-shadow var(--duration-fast) var(--ease-standard);
}
.today-link { min-height: 52px; gap: 11px; padding: 7px 11px; }
.today-link > span { display: grid; min-width: 0; }
.today-link strong { color: var(--text-primary); font-size: 14px; font-weight: var(--weight-medium); }
.today-link small { color: var(--text-tertiary); font-size: 12px; }
.today-link:hover,
.today-link.active { color: var(--accent); background: var(--accent-soft); }
.today-link.active strong { color: var(--text-accent); }
.course-section-nav {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  margin: 8px 0 3px;
  padding: 4px;
  border-radius: 14px;
  background: var(--surface-secondary);
}
.course-section-link {
  min-height: 48px;
  display: grid;
  place-items: center;
  gap: 3px;
  padding: 6px 2px;
  border-radius: 10px;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
}
.course-section-link.active,
.course-section-link:hover { color: var(--text-accent); background: var(--surface-primary); }
.rail-section-heading {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 5px 5px 11px;
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 600;
}
.rail-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  flex: 0 0 38px;
  border-radius: 12px;
  color: var(--text-secondary);
}
.rail-icon:hover { color: var(--accent); background: var(--accent-soft); }
.course-links { display: grid; gap: 4px; }
.course-link { min-height: 64px; gap: 11px; padding: 8px 10px; }
.course-link:hover { background: var(--surface-hover); }
.course-link.selected {
  color: var(--text-accent);
  background: var(--gradient-selected);
  box-shadow: inset 0 0 0 1px rgba(52, 120, 246, .08);
}
.course-glyph {
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  font-size: 13px;
  font-weight: var(--weight-bold);
}
.course-glyph.jade { color: var(--tone-jade-fg); background: var(--tone-jade-bg); }
.course-glyph.blue { color: var(--tone-blue-fg); background: var(--tone-blue-bg); }
.course-glyph.amber { color: var(--tone-amber-fg); background: var(--tone-amber-bg); }
.course-glyph.coral { color: var(--tone-coral-fg); background: var(--tone-coral-bg); }
.course-glyph.violet { color: var(--tone-violet-fg); background: var(--tone-violet-bg); }
.course-glyph.teal { color: var(--tone-teal-fg); background: var(--tone-teal-bg); }
.course-copy { min-width: 0; flex: 1; display: grid; gap: 3px; }
.course-copy strong,
.course-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.course-copy strong { color: var(--text-primary); font-size: 14px; font-weight: var(--weight-medium); }
.course-copy small { color: var(--text-tertiary); font-size: 12px; }
.course-progress {
  width: 100%;
  height: 3px;
  overflow: hidden;
  border-radius: var(--radius-round);
  background: var(--accent-softer);
}
.course-progress i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--gradient-blue-cyan);
  transition: width var(--duration-normal) var(--ease-out);
}
.course-link.selected .course-copy strong { color: var(--text-accent); }
.rail-state { padding: 20px 10px; color: var(--text-tertiary); font-size: 12px; text-align: center; }
.rail-error { color: var(--danger); }
.rail-footer { padding: 10px 10px 14px; border-top: 1px solid var(--border-subtle); }
.settings-link { height: 44px; gap: 11px; padding: 0 11px; font-size: 13px; font-weight: 560; }
.settings-link:hover,
.settings-link.active { color: var(--accent); background: var(--accent-soft); }
.rail-user {
  min-width: 0;
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) 38px;
  align-items: center;
  gap: 9px;
  margin-top: 7px;
  padding: 10px 2px 0;
  border-top: 1px solid var(--border-subtle);
}
.user-avatar {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--tone-blue-fg);
  background: var(--tone-blue-bg);
  font-size: 13px;
  font-weight: var(--weight-bold);
}
.rail-user strong {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: var(--weight-medium);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.collapsed .rail-brand { justify-content: center; padding-inline: 0; }
.collapsed .rail-brand > div,
.collapsed .rail-brand > .rail-icon,
.collapsed .today-link > span,
.collapsed .course-section-nav,
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
