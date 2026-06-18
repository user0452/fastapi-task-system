<script setup>
import { ref, onMounted } from 'vue'
import { getOperationLogs } from '../api/logs'
import EmptyState from '../components/common/EmptyState.vue'
import LoadingState from '../components/common/LoadingState.vue'
import { ChevronDown, ClipboardList } from 'lucide-vue-next'

const logs = ref([])
const loading = ref(false)
const expandedId = ref(null)

onMounted(() => {
  loadLogs()
})

async function loadLogs() {
  loading.value = true
  const res = await getOperationLogs({ page: 1, size: 100 })
  loading.value = false
  if (res.code === 200) {
    logs.value = res.data?.list || res.data?.items || res.data || []
  }
}

function toggleExpand(id) {
  expandedId.value = expandedId.value === id ? null : id
}

function formatDate(val) {
  if (!val) return ''
  const d = new Date(val)
  return d.toLocaleString('zh-CN')
}

// 解析日志详情，返回友好的键值对
function parseDetail(log) {
  const detail = log.detail || log.input_data || log.output_data
  if (!detail) return null

  // 如果是字符串，尝试解析 JSON
  if (typeof detail === 'string') {
    try {
      const parsed = JSON.parse(detail)
      return formatObject(parsed)
    } catch {
      return detail
    }
  }

  // 如果是对象
  if (typeof detail === 'object') {
    return formatObject(detail)
  }

  return String(detail)
}

// 格式化对象为友好的键值对列表
function formatObject(obj) {
  if (!obj || typeof obj !== 'object') return []

  const result = []
  const keyLabels = {
    course_name: '课程名',
    topic: '主题',
    title: '标题',
    content_length: '内容长度',
    chunk_count: '分块数量',
    filename: '文件名',
    content_type: '文件类型',
    text_length: '文本长度',
    intent: '意图',
    tools: '工具',
    resource_id: '资源ID',
    quiz_set_id: '题集ID',
    has_learning_plan: '有学习计划',
    rag_hit_count: 'RAG命中数',
    learner_level: '学习水平',
    max_results: '最大结果数',
    result_count: '结果数量',
    queries: '搜索词',
    task_count: '任务数量',
    days: '天数'
  }

  for (const [key, value] of Object.entries(obj)) {
    if (value === null || value === undefined) continue

    const label = keyLabels[key] || key

    if (Array.isArray(value)) {
      result.push({ label, value: value.join('、') || '无' })
    } else if (typeof value === 'boolean') {
      result.push({ label, value: value ? '是' : '否' })
    } else if (typeof value === 'object') {
      result.push({ label, value: JSON.stringify(value) })
    } else {
      result.push({ label, value: String(value) })
    }
  }

  return result
}

// 获取日志类型标签
function getActionLabel(action) {
  const labels = {
    A3_UPLOAD_COURSE_MATERIAL: '上传课程资料',
    A3_UPLOAD_COURSE_MATERIAL_FILE: '上传课程文件',
    A3_BUILD_MATERIAL_INDEX: '构建资料索引',
    A3_SEARCH_EXTERNAL_RESOURCES: '搜索外部资源',
    A3_AGENT_CHAT_DISPATCH: 'AI助手对话'
  }
  return labels[action] || action
}
</script>

<template>
  <div class="logs-page">
    <div class="page-header">
      <h1>操作日志</h1>
      <button class="btn btn-ghost btn-sm" @click="loadLogs">刷新</button>
    </div>

    <LoadingState v-if="loading" />

    <EmptyState v-else-if="logs.length === 0" :icon="ClipboardList" title="暂无日志" />

    <div v-else class="logs-list">
      <div
        v-for="log in logs"
        :key="log.id || log.log_id || log.timestamp"
        class="log-item"
      >
        <div class="log-header" @click="toggleExpand(log.id || log.log_id || log.timestamp)">
          <div class="log-info">
            <span class="log-action">{{ getActionLabel(log.action) }}</span>
            <span v-if="log.module || log.category" class="badge badge-info">{{ log.module || log.category }}</span>
          </div>
          <div class="log-meta">
            <span class="log-time">{{ formatDate(log.created_at || log.timestamp) }}</span>
            <ChevronDown
              :size="16"
              class="log-toggle"
              :class="{ expanded: expandedId === (log.id || log.log_id || log.timestamp) }"
            />
          </div>
        </div>
        <div
          v-if="expandedId === (log.id || log.log_id || log.timestamp)"
          class="log-detail"
        >
          <template v-if="parseDetail(log)">
            <div v-if="typeof parseDetail(log) === 'string'" class="detail-text">
              {{ parseDetail(log) }}
            </div>
            <div v-else class="detail-fields">
              <div v-for="(item, i) in parseDetail(log)" :key="i" class="detail-field">
                <span class="field-label">{{ item.label }}</span>
                <span class="field-value">{{ item.value }}</span>
              </div>
            </div>
          </template>
          <div v-else class="detail-empty">无详细信息</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.logs-page {
  max-width: 1000px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
}

.page-header h1 {
  font-size: var(--text-2xl);
  font-weight: 600;
}

.logs-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.log-item {
  background-color: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.875rem 1rem;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.log-header:hover {
  background-color: var(--color-surface-hover);
}

.log-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.log-action {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text);
}

.log-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.log-time {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.log-toggle {
  color: var(--color-muted);
  transition: transform 0.2s ease;
}

.log-toggle.expanded {
  transform: rotate(180deg);
}

.log-detail {
  padding: 0 1rem 1rem;
  border-top: 1px solid var(--color-line);
}

.detail-text {
  padding: 0.75rem;
  background-color: var(--color-surface-strong);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  color: var(--color-text-soft);
  line-height: 1.6;
  white-space: pre-wrap;
  margin-top: 0.75rem;
}

.detail-fields {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.detail-field {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background-color: var(--color-surface-strong);
  border-radius: var(--radius-sm);
}

.detail-field .field-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-muted);
  min-width: 100px;
  flex-shrink: 0;
}

.detail-field .field-value {
  font-size: var(--text-sm);
  color: var(--color-text-soft);
  word-break: break-all;
}

.detail-empty {
  padding: 0.75rem;
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-muted);
  margin-top: 0.75rem;
}

@media (max-width: 640px) {
  .log-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .log-meta {
    width: 100%;
    justify-content: space-between;
  }

  .detail-field {
    flex-direction: column;
    gap: 0.25rem;
  }

  .detail-field .field-label {
    min-width: auto;
  }
}
</style>
