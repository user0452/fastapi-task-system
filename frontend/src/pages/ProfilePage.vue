<script setup>
import { ref, onMounted, computed } from 'vue'
import { getProfile, generateProfile } from '../api/profiles'
import { showToast } from '../components/common/toast'
import EmptyState from '../components/common/EmptyState.vue'
import LoadingState from '../components/common/LoadingState.vue'
import {
  GraduationCap, BookOpen, Target, AlertCircle, Brain,
  Clock, RefreshCw, Sparkles, ChevronDown, ChevronUp, FileText, UserRound
} from 'lucide-vue-next'

const profile = ref(null)
const loading = ref(false)
const showForm = ref(true)

const form = ref({
  learning_goal: '',
  current_level: '',
  weak_points: '',
  learning_style: ''
})
const generating = ref(false)

onMounted(() => { loadProfile() })

async function loadProfile() {
  loading.value = true
  const res = await getProfile()
  loading.value = false
  if (res.code === 200 && res.data) {
    profile.value = res.data.profile || res.data
    if (profile.value) showForm.value = false
  }
}

async function handleGenerate() {
  if (!form.value.learning_goal) {
    showToast({ type: 'warning', message: '请填写学习目标' })
    return
  }
  generating.value = true
  const profileText = [
    `学习目标：${form.value.learning_goal}`,
    form.value.current_level ? `当前水平：${form.value.current_level}` : '',
    form.value.weak_points ? `薄弱环节：${form.value.weak_points}` : '',
    form.value.learning_style ? `学习风格：${form.value.learning_style}` : ''
  ].filter(Boolean).join('\n')
  const res = await generateProfile({ text: profileText })
  generating.value = false
  if (res.code === 200 || res.code === 201) {
    showToast({ type: 'success', message: '画像生成成功' })
    profile.value = res.data
    showForm.value = false
    form.value = { learning_goal: '', current_level: '', weak_points: '', learning_style: '' }
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

const profileData = computed(() => {
  if (!profile.value) return null
  if (typeof profile.value === 'string') return { content: profile.value }
  if (profile.value.content) return profile.value
  const d = profile.value
  return {
    grade: d.grade || d.current_level || '',
    major: d.major || '',
    goals: Array.isArray(d.goals) ? d.goals : (d.learning_goal ? [d.learning_goal] : []),
    weaknesses: Array.isArray(d.weaknesses) ? d.weaknesses : (d.weak_points ? [d.weak_points] : []),
    available_time: d.available_time || '',
    learning_preference: d.learning_preference || d.learning_style || '',
    summary: d.summary || ''
  }
})

const hasProfile = computed(() => !!profileData.value)
</script>

<template>
  <div class="profile-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-left">
        <h1>学生画像</h1>
        <span class="header-desc">AI 根据你的信息生成个性化学习画像</span>
      </div>
      <div class="header-actions">
        <button class="btn btn-ghost btn-sm" @click="loadProfile" :disabled="loading">
          <RefreshCw :size="14" :class="{ spinning: loading }" />
          刷新
        </button>
        <button class="btn btn-ghost btn-sm" @click="showForm = !showForm">
          <Sparkles :size="14" />
          {{ hasProfile ? '重新生成' : '生成画像' }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <LoadingState v-if="loading && !profileData" />

    <!-- Empty -->
    <EmptyState
      v-else-if="!hasProfile && !showForm"
      :icon="UserRound"
      title="暂无画像"
      desc="点击上方「生成画像」创建你的学习画像"
    />

    <!-- Profile Display -->
    <div v-if="hasProfile && !showForm" class="profile-display">
      <!-- 纯文本内容 -->
      <div v-if="profileData.content" class="profile-text-card">
        <div class="text-header">
          <FileText :size="18" />
          <span>画像概述</span>
        </div>
        <div class="text-body">{{ profileData.content }}</div>
      </div>

      <!-- 结构化内容 -->
      <template v-else>
        <!-- 基本信息卡片组 -->
        <div class="info-cards">
          <div class="info-card" v-if="profileData.grade">
            <div class="info-icon"><GraduationCap :size="20" /></div>
            <div class="info-detail">
              <span class="info-label">年级/水平</span>
              <span class="info-value">{{ profileData.grade }}</span>
            </div>
          </div>
          <div class="info-card" v-if="profileData.major">
            <div class="info-icon"><BookOpen :size="20" /></div>
            <div class="info-detail">
              <span class="info-label">专业</span>
              <span class="info-value">{{ profileData.major }}</span>
            </div>
          </div>
          <div class="info-card" v-if="profileData.available_time">
            <div class="info-icon"><Clock :size="20" /></div>
            <div class="info-detail">
              <span class="info-label">可用时间</span>
              <span class="info-value">{{ profileData.available_time }}</span>
            </div>
          </div>
          <div class="info-card" v-if="profileData.learning_preference">
            <div class="info-icon"><Brain :size="20" /></div>
            <div class="info-detail">
              <span class="info-label">学习偏好</span>
              <span class="info-value">{{ profileData.learning_preference }}</span>
            </div>
          </div>
        </div>

        <!-- 学习目标 -->
        <div class="section-block" v-if="profileData.goals?.length">
          <div class="section-title">
            <Target :size="16" />
            <span>学习目标</span>
          </div>
          <div class="tag-group">
            <span class="tag tag-primary" v-for="(g, i) in profileData.goals" :key="i">{{ g }}</span>
          </div>
        </div>

        <!-- 薄弱环节 -->
        <div class="section-block" v-if="profileData.weaknesses?.length">
          <div class="section-title">
            <AlertCircle :size="16" />
            <span>薄弱环节</span>
          </div>
          <div class="tag-group tag-warning">
            <span class="tag" v-for="(w, i) in profileData.weaknesses" :key="i">{{ w }}</span>
          </div>
        </div>

        <!-- 总结 -->
        <div class="section-block" v-if="profileData.summary">
          <div class="section-title">
            <FileText :size="16" />
            <span>画像总结</span>
          </div>
          <p class="summary-text">{{ profileData.summary }}</p>
        </div>
      </template>
    </div>

    <!-- Generate Form -->
    <div v-if="showForm" class="generate-section">
      <div class="form-card">
        <div class="form-header">
          <Sparkles :size="18" />
          <span>{{ hasProfile ? '重新生成画像' : '生成学习画像' }}</span>
        </div>
        <div class="form-body">
          <div class="form-group">
            <label class="form-label">学习目标 *</label>
            <textarea
              v-model="form.learning_goal"
              class="form-textarea"
              rows="3"
              placeholder="如：掌握 Python 基础，能独立完成 Web 项目"
            ></textarea>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">当前水平</label>
              <input
                v-model="form.current_level"
                class="form-input"
                placeholder="如：零基础 / 有一些编程经验"
              />
            </div>
            <div class="form-group">
              <label class="form-label">学习风格</label>
              <input
                v-model="form.learning_style"
                class="form-input"
                placeholder="如：偏好视频教程、动手实践"
              />
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">薄弱环节</label>
            <input
              v-model="form.weak_points"
              class="form-input"
              placeholder="如：数学基础较弱，英语阅读慢"
            />
          </div>
        </div>
        <div class="form-footer">
          <button class="btn btn-ghost" v-if="hasProfile" @click="showForm = false">取消</button>
          <button class="btn btn-primary" :disabled="generating" @click="handleGenerate">
            <Sparkles :size="14" />
            {{ generating ? '生成中...' : '生成画像' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-page {
  max-width: 900px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
}

.header-left h1 {
  font-size: var(--text-2xl);
  font-weight: 600;
  margin: 0;
}

.header-desc {
  font-size: var(--text-sm);
  color: var(--color-muted);
  margin-top: 0.25rem;
  display: block;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Info Cards */
.info-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.info-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  background: var(--color-card);
  border: 1px solid var(--color-line);
  border-radius: 10px;
}

.info-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary-light);
  color: var(--color-primary);
  border-radius: 8px;
  flex-shrink: 0;
}

.info-detail {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.info-label {
  font-size: var(--text-xs);
  color: var(--color-muted);
  margin-bottom: 0.125rem;
}

.info-value {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Section Block */
.section-block {
  background: var(--color-card);
  border: 1px solid var(--color-line);
  border-radius: 10px;
  padding: 1rem 1.25rem;
  margin-bottom: 0.75rem;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 0.75rem;
}

.section-title svg {
  color: var(--color-primary);
}

.tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.tag {
  display: inline-flex;
  align-items: center;
  padding: 0.375rem 0.75rem;
  font-size: var(--text-sm);
  border-radius: 6px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 500;
}

.tag-primary {
  background: var(--color-primary-light);
  color: var(--color-primary);
}

.tag-warning .tag {
  background: #fff3e0;
  color: #e65100;
}

.summary-text {
  font-size: var(--text-sm);
  color: var(--color-text-soft);
  line-height: 1.7;
  margin: 0;
}

/* Profile Text Card */
.profile-text-card {
  background: var(--color-card);
  border: 1px solid var(--color-line);
  border-radius: 10px;
  overflow: hidden;
}

.text-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.875rem 1.25rem;
  border-bottom: 1px solid var(--color-line);
  font-weight: 600;
  font-size: var(--text-sm);
}

.text-header svg {
  color: var(--color-primary);
}

.text-body {
  padding: 1.25rem;
  font-size: var(--text-sm);
  color: var(--color-text-soft);
  line-height: 1.8;
  white-space: pre-wrap;
}

/* Generate Form */
.generate-section {
  margin-top: 0.5rem;
}

.form-card {
  background: var(--color-card);
  border: 1px solid var(--color-line);
  border-radius: 10px;
  overflow: hidden;
}

.form-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.875rem 1.25rem;
  border-bottom: 1px solid var(--color-line);
  font-weight: 600;
  font-size: var(--text-sm);
}

.form-header svg {
  color: var(--color-primary);
}

.form-body {
  padding: 1.25rem;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.form-group {
  margin-bottom: 1rem;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-label {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  margin-bottom: 0.375rem;
}

.form-input,
.form-textarea {
  width: 100%;
  border: 1px solid var(--color-line);
  border-radius: 8px;
  font-size: var(--text-sm);
  transition: border-color 0.2s;
}

.form-input {
  height: 38px;
  padding: 0 0.75rem;
}

.form-textarea {
  padding: 0.625rem 0.75rem;
  resize: vertical;
  min-height: 80px;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}

.form-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  padding: 0.875rem 1.25rem;
  border-top: 1px solid var(--color-line);
}

@media (max-width: 640px) {
  .page-header {
    flex-direction: column;
    gap: 0.75rem;
  }

  .info-cards {
    grid-template-columns: 1fr;
  }

  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
