<script setup>
import { CalendarCheck2, LogOut, Plus, Settings, Sparkles, X } from 'lucide-vue-next'


defineProps({
  courses: { type: Array, default: () => [] },
  currentId: { type: Number, default: null },
  username: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  mobile: { type: Boolean, default: false }
})

defineEmits(['create', 'logout', 'close'])

const tones = ['jade', 'blue', 'amber', 'coral', 'violet', 'teal']

function tone(index) {
  return tones[index % tones.length]
}

function initial(name) {
  return String(name || '课').trim().slice(0, 1).toUpperCase()
}
</script>

<template>
  <aside class="course-rail" aria-label="课程助手">
    <header class="rail-brand">
      <span class="brand-mark"><Sparkles :size="16" /></span>
      <div>
        <strong>A3 学习 AI</strong>
        <span>专属课程工作台</span>
      </div>
      <button v-if="mobile" class="rail-icon" type="button" title="关闭课程栏" aria-label="关闭课程栏" @click="$emit('close')">
        <X :size="18" />
      </button>
    </header>

    <nav class="rail-navigation">
      <router-link to="/today" class="today-link" active-class="active" @click="$emit('close')">
        <CalendarCheck2 :size="18" />
        <span>
          <strong>今日总览</strong>
          <small>所有课程</small>
        </span>
      </router-link>

      <div class="rail-section-heading">
        <span>课程助手</span>
        <button class="rail-icon" type="button" title="新建课程" aria-label="新建课程" @click="$emit('create')">
          <Plus :size="17" />
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
          @click="$emit('close')"
        >
          <span class="course-glyph" :class="tone(index)">{{ initial(course.name) }}</span>
          <span class="course-copy">
            <strong>{{ course.name }}</strong>
            <small>{{ course.daily_minutes }} 分钟/天 · {{ course.status === 'draft' ? '待添加资料' : '持续学习' }}</small>
          </span>
        </router-link>
      </div>
    </nav>

    <footer class="rail-footer">
      <router-link to="/settings" class="settings-link" active-class="active" @click="$emit('close')">
        <Settings :size="17" />
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
  width: 236px;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: #25302c;
  background: #f4f6f3;
  border-right: 1px solid #dce1dd;
}
.rail-brand { height: 68px; display: flex; align-items: center; gap: 10px; padding: 0 14px; border-bottom: 1px solid #e0e4e1; }
.brand-mark { width: 34px; height: 34px; flex: 0 0 34px; display: grid; place-items: center; color: #fff; background: #176b58; border-radius: 7px; }
.rail-brand > div { min-width: 0; display: grid; gap: 1px; }
.rail-brand strong { font-size: 14px; font-weight: 780; }
.rail-brand span:not(.brand-mark) { color: #7a827e; font-size: 10px; }
.rail-brand > .rail-icon { margin-left: auto; }
.rail-navigation { min-height: 0; flex: 1; overflow-y: auto; padding: 12px 9px; }
.today-link,
.course-link,
.settings-link { display: flex; align-items: center; color: #56615c; border-radius: 6px; }
.today-link { min-height: 46px; gap: 10px; padding: 6px 10px; }
.today-link > span { display: grid; }
.today-link strong { color: #34403a; font-size: 12px; }
.today-link small { color: #87908b; font-size: 10px; }
.today-link:hover,
.today-link.active { color: #12604d; background: #e5ece8; }
.rail-section-heading { height: 40px; display: flex; align-items: center; justify-content: space-between; padding: 8px 5px 3px 10px; color: #858d89; font-size: 10px; font-weight: 760; text-transform: uppercase; }
.rail-icon { width: 30px; height: 30px; display: grid; place-items: center; flex: 0 0 30px; border-radius: 6px; color: #69736e; }
.rail-icon:hover { color: #176b58; background: #e4eae6; }
.course-links { display: grid; gap: 3px; }
.course-link { min-height: 51px; gap: 9px; padding: 6px 8px; }
.course-link:hover { background: #e9edea; }
.course-link.selected { background: #dde8e2; }
.course-glyph { width: 30px; height: 30px; flex: 0 0 30px; display: grid; place-items: center; border-radius: 6px; font-size: 10px; font-weight: 820; }
.course-glyph.jade { color: #145e4b; background: #cfe8dd; }
.course-glyph.blue { color: #255c7c; background: #d7e7f0; }
.course-glyph.amber { color: #805915; background: #f1e3c3; }
.course-glyph.coral { color: #87453f; background: #f0d8d3; }
.course-glyph.violet { color: #654c7c; background: #e5dced; }
.course-glyph.teal { color: #236b68; background: #d4e9e7; }
.course-copy { min-width: 0; display: grid; gap: 2px; }
.course-copy strong,
.course-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.course-copy strong { color: #33403a; font-size: 12px; font-weight: 720; }
.course-copy small { color: #848c88; font-size: 10px; }
.course-link.selected .course-copy strong { color: #0f5947; }
.rail-state { padding: 18px 10px; color: #87908b; font-size: 10px; text-align: center; }
.rail-error { color: #b35b54; }
.rail-footer { padding: 8px 9px 11px; border-top: 1px solid #dce1dd; }
.settings-link { height: 37px; gap: 10px; padding: 0 10px; font-size: 11px; font-weight: 680; }
.settings-link:hover,
.settings-link.active { color: #155f4d; background: #e5ece8; }
.rail-user { min-width: 0; display: grid; grid-template-columns: 30px minmax(0, 1fr) 30px; align-items: center; gap: 8px; margin-top: 6px; padding: 8px 3px 0; border-top: 1px solid #e0e4e1; }
.user-avatar { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 50%; color: #2c6253; background: #dce8e2; font-size: 10px; font-weight: 800; }
.rail-user strong { overflow: hidden; color: #58635e; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
</style>
