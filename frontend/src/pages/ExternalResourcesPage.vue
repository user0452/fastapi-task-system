<script setup>
import { ref } from 'vue'
import { searchExternalResources } from '../api/externalResources'
import { showToast } from '../components/common/toast'
import EmptyState from '../components/common/EmptyState.vue'
import LoadingState from '../components/common/LoadingState.vue'
import { Search, ExternalLink, FileText, Video, BookOpen, Code } from 'lucide-vue-next'

const form = ref({
  course_name: '',
  topic: '',
  learner_level: 'beginner',
  max_results: 8
})

const loading = ref(false)
const results = ref(null)

const levelOptions = [
  { value: 'beginner', label: '初学者' },
  { value: 'intermediate', label: '中级' },
  { value: 'advanced', label: '高级' }
]

const resourceTypeIcons = {
  video: Video,
  article: FileText,
  document: BookOpen,
  practice: Code
}

const resourceTypeLabels = {
  video: '视频',
  article: '文章',
  document: '文档',
  practice: '练习'
}

async function handleSearch() {
  const topic = form.value.topic.trim()
  const courseName = form.value.course_name.trim()

  if (!topic) {
    showToast({ type: 'warning', message: '请填写搜索主题' })
    return
  }

  loading.value = true
  const res = await searchExternalResources({
    ...form.value,
    course_name: courseName || '通用学习',
    topic
  })
  loading.value = false

  if (res.code === 200 && res.data) {
    results.value = res.data
    if (res.data.total === 0) {
      showToast({ type: 'info', message: '未找到相关资源' })
    }
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

function openUrl(url) {
  if (url) {
    window.open(url, '_blank')
  }
}
</script>

<template>
  <div class="external-page">
    <div class="page-header">
      <h1>联网搜索资源</h1>
      <span class="page-hint">从互联网搜索优质学习资源</span>
    </div>

    <div class="search-section">
      <div class="search-form">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">课程名称</label>
            <input
              v-model="form.course_name"
              class="form-input"
              placeholder="如：高等数学（可选）"
              @keyup.enter="handleSearch"
            />
          </div>
          <div class="form-group">
            <label class="form-label">搜索主题 *</label>
            <input
              v-model="form.topic"
              class="form-input"
              placeholder="如：导数的应用"
              @keyup.enter="handleSearch"
            />
          </div>
          <div class="form-group">
            <label class="form-label">学习水平</label>
            <select v-model="form.learner_level" class="form-select">
              <option v-for="opt in levelOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div class="form-group form-actions">
            <button class="btn btn-primary" :disabled="loading" @click="handleSearch">
              <Search :size="16" />
              {{ loading ? '搜索中...' : '搜索' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <LoadingState v-if="loading" text="正在联网搜索学习资源..." />

    <template v-else-if="results">
      <div class="results-header">
        <span>找到 {{ results.total }} 个相关资源</span>
        <span v-if="results.queries?.length" class="search-queries">
          搜索词：{{ results.queries.join(' | ') }}
        </span>
      </div>

      <div v-if="results.resources?.length" class="results-grid">
        <div
          v-for="(resource, i) in results.resources"
          :key="i"
          class="resource-card"
          @click="openUrl(resource.url)"
        >
          <div class="resource-header">
            <div class="resource-type">
              <component :is="resourceTypeIcons[resource.resource_type] || FileText" :size="16" />
              <span>{{ resourceTypeLabels[resource.resource_type] || '其他' }}</span>
            </div>
            <span class="resource-time">{{ resource.estimated_time }}</span>
          </div>

          <h3 class="resource-title">{{ resource.title }}</h3>

          <p class="resource-snippet">{{ resource.snippet }}</p>

          <div class="resource-footer">
            <span class="resource-source">{{ resource.source }}</span>
            <ExternalLink :size="14" class="external-icon" />
          </div>

          <div v-if="resource.reason" class="resource-reason">
            {{ resource.reason }}
          </div>
        </div>
      </div>
    </template>

    <EmptyState
      v-else
      :icon="Search"
      title="搜索学习资源"
      desc="输入课程名称和主题，从互联网搜索优质学习资源"
    />
  </div>
</template>

<style scoped>
.external-page {
  max-width: 1200px;
}

.page-header {
  display: flex;
  align-items: baseline;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.page-header h1 {
  font-size: var(--text-2xl);
  font-weight: 600;
}

.page-hint {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.search-section {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}

.form-row {
  display: flex;
  gap: 1rem;
  align-items: flex-end;
}

.form-row .form-group {
  flex: 1;
  margin-bottom: 0;
}

.form-actions {
  flex: 0 0 auto;
}

.results-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
  font-size: var(--text-sm);
  color: var(--color-text-soft);
}

.search-queries {
  color: var(--color-muted);
  font-size: var(--text-xs);
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1rem;
}

.resource-card {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  padding: 1rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.resource-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.resource-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.625rem;
}

.resource-type {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary);
  background-color: var(--color-primary-light);
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-sm);
}

.resource-time {
  font-size: var(--text-xs);
  color: var(--color-muted);
}

.resource-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 0.5rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.resource-snippet {
  font-size: var(--text-sm);
  color: var(--color-text-soft);
  line-height: 1.6;
  margin-bottom: 0.75rem;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.resource-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 0.625rem;
  border-top: 1px solid var(--color-line);
}

.resource-source {
  font-size: var(--text-xs);
  color: var(--color-muted);
}

.external-icon {
  color: var(--color-muted);
}

.resource-reason {
  margin-top: 0.625rem;
  padding: 0.5rem 0.625rem;
  background-color: var(--color-surface-strong);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--color-text-soft);
  line-height: 1.5;
}

@media (max-width: 768px) {
  .form-row {
    flex-direction: column;
    align-items: stretch;
  }

  .form-actions {
    width: 100%;
  }

  .form-actions .btn {
    width: 100%;
  }

  .results-grid {
    grid-template-columns: 1fr;
  }
}
</style>
