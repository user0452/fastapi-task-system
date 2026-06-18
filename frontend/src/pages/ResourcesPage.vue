<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getResources, generateResource, getResource } from '../api/resources'
import { showToast } from '../components/common/toast'
import EmptyState from '../components/common/EmptyState.vue'
import LoadingState from '../components/common/LoadingState.vue'
import { BookOpen, FileText } from 'lucide-vue-next'

const route = useRoute()

const resources = ref([])
const total = ref(0)
const loading = ref(false)

const form = ref({ course_name: '', topic: '' })
const generating = ref(false)

const selectedId = ref(null)
const detail = ref(null)
const detailLoading = ref(false)

onMounted(async () => {
  await loadResources()
  selectResourceFromRoute()
})

watch(
  () => route.query.resource_id,
  () => {
    selectResourceFromRoute()
  }
)

function selectResourceFromRoute() {
  const id = Number(route.query.resource_id)
  if (id) {
    selectResource(id)
  }
}

async function loadResources() {
  loading.value = true
  const res = await getResources({ page: 1, size: 50 })
  loading.value = false
  if (res.code === 200) {
    resources.value = res.data?.list || res.data?.items || res.data || []
    total.value = res.data?.total || resources.value.length
  }
}

async function handleGenerate() {
  if (!form.value.course_name || !form.value.topic) {
    showToast({ type: 'warning', message: '请填写课程名和主题' })
    return
  }

  generating.value = true
  const res = await generateResource({
    course_name: form.value.course_name,
    topic: form.value.topic
  })
  generating.value = false

  if (res.code === 200 || res.code === 201) {
    showToast({ type: 'success', message: '资源生成成功' })
    form.value = { course_name: '', topic: '' }
    await loadResources()
    if (res.data?.resource_id || res.data?.id) {
      selectResource(res.data.resource_id || res.data.id)
    }
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

async function selectResource(id) {
  selectedId.value = id
  detailLoading.value = true
  const res = await getResource(id)
  detailLoading.value = false
  if (res.code === 200) {
    detail.value = res.data
  }
}

function formatDate(val) {
  if (!val) return ''
  return new Date(val).toLocaleDateString('zh-CN')
}

// 获取资源详情的各个部分
const resourceContent = computed(() => {
  if (!detail.value) return null
  return detail.value.resource || detail.value
})

// 解析数组或字符串
function formatList(val) {
  if (!val) return []
  if (Array.isArray(val)) return val
  if (typeof val === 'string') return [val]
  return []
}

// 获取子资源内容
function getSubResourceContent(val) {
  if (!val) return ''
  if (typeof val === 'string') return val
  if (typeof val === 'object' && val.content) return val.content
  if (typeof val === 'object' && val.title) return val.title
  return ''
}

const ragReferences = computed(() => {
  return detail.value?.rag_references || resourceContent.value?.rag_references || []
})
</script>

<template>
  <div class="resources-page">
    <div class="page-header">
      <h1>学习资源</h1>
      <span class="badge badge-primary">共 {{ total }} 份</span>
    </div>

    <div class="resources-layout">
      <div class="resources-generator">
        <div class="card">
          <div class="card-header">
            <h3>生成资源</h3>
          </div>
          <div class="card-body">
            <div class="form-group">
              <label class="form-label">课程名 *</label>
              <input v-model="form.course_name" class="form-input" placeholder="如：高等数学" />
            </div>
            <div class="form-group">
              <label class="form-label">主题 *</label>
              <input v-model="form.topic" class="form-input" placeholder="如：导数的应用" />
            </div>
          </div>
          <div class="card-footer">
            <button class="btn btn-primary" :disabled="generating" @click="handleGenerate">
              {{ generating ? '生成中...' : '生成' }}
            </button>
          </div>
        </div>
      </div>

      <div class="resources-list">
        <div class="card">
          <div class="card-header">
            <h3>资源列表</h3>
            <button class="btn btn-ghost btn-sm" @click="loadResources">刷新</button>
          </div>
          <div class="card-body">
            <LoadingState v-if="loading" />
            <EmptyState v-else-if="resources.length === 0" :icon="FileText" title="暂无资源" desc="生成后会显示在这里" />
            <div v-else class="list-scroll">
              <div
                v-for="r in resources"
                :key="r.resource_id || r.id"
                class="resource-item"
                :class="{ active: selectedId === (r.resource_id || r.id) }"
                @click="selectResource(r.resource_id || r.id)"
              >
                <div class="resource-item-title">{{ r.title }}</div>
                <div class="resource-item-meta">{{ r.course_name }} · {{ formatDate(r.created_at) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="resources-detail">
        <div class="card">
          <div class="card-header">
            <h3>资源详情</h3>
          </div>
          <div class="card-body">
            <LoadingState v-if="detailLoading" />
            <EmptyState v-else-if="!detail" :icon="BookOpen" title="选择资源查看详情" />
            <div v-else class="detail-scroll">
              <h3 class="detail-title">{{ detail.title }}</h3>

              <!-- 主要内容 -->
              <div v-if="detail.content" class="detail-section">
                <h4>内容概述</h4>
                <p>{{ detail.content }}</p>
              </div>

              <!-- 关键知识点 -->
              <div v-if="formatList(resourceContent?.key_points).length" class="detail-section">
                <h4>关键知识点</h4>
                <ul>
                  <li v-for="(point, i) in formatList(resourceContent.key_points)" :key="i">{{ point }}</li>
                </ul>
              </div>

              <!-- 示例 -->
              <div v-if="formatList(resourceContent?.examples).length" class="detail-section">
                <h4>示例</h4>
                <ul>
                  <li v-for="(ex, i) in formatList(resourceContent.examples)" :key="i">{{ ex }}</li>
                </ul>
              </div>

              <!-- 子资源 -->
              <template v-if="resourceContent?.resources">
                <!-- 讲解文档 -->
                <div v-if="getSubResourceContent(resourceContent.resources.explanation_doc)" class="detail-section">
                  <h4>讲解文档</h4>
                  <p>{{ getSubResourceContent(resourceContent.resources.explanation_doc) }}</p>
                </div>

                <!-- 思维导图 -->
                <div v-if="getSubResourceContent(resourceContent.resources.mind_map)" class="detail-section">
                  <h4>思维导图</h4>
                  <pre class="mind-map">{{ getSubResourceContent(resourceContent.resources.mind_map) }}</pre>
                </div>

                <!-- 拓展阅读 -->
                <div v-if="getSubResourceContent(resourceContent.resources.extended_reading)" class="detail-section">
                  <h4>拓展阅读</h4>
                  <p>{{ getSubResourceContent(resourceContent.resources.extended_reading) }}</p>
                </div>

                <!-- 实践案例 -->
                <div v-if="getSubResourceContent(resourceContent.resources.practice_case)" class="detail-section">
                  <h4>实践案例</h4>
                  <p>{{ getSubResourceContent(resourceContent.resources.practice_case) }}</p>
                </div>

                <!-- 常见错误 -->
                <div v-if="getSubResourceContent(resourceContent.resources.common_mistakes)" class="detail-section">
                  <h4>常见错误</h4>
                  <p>{{ getSubResourceContent(resourceContent.resources.common_mistakes) }}</p>
                </div>

                <!-- 视频脚本 -->
                <div v-if="getSubResourceContent(resourceContent.resources.video_script)" class="detail-section">
                  <h4>视频脚本</h4>
                  <p>{{ getSubResourceContent(resourceContent.resources.video_script) }}</p>
                </div>
              </template>

              <!-- RAG 参考 -->
              <div v-if="ragReferences.length" class="detail-section">
                <h4>RAG 参考</h4>
                <div class="rag-references">
                  <div v-for="(ref, i) in ragReferences" :key="i" class="rag-ref-item">
                    <div class="rag-ref-header">
                      <span class="rag-ref-score">相似度: {{ ref.score?.toFixed(4) || '—' }}</span>
                      <span class="rag-ref-meta">分块 #{{ ref.chunk_index ?? '—' }}</span>
                    </div>
                    <div class="rag-ref-snippet">{{ ref.snippet || ref.chunk_text || '' }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.resources-page {
  max-width: 1400px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.page-header h1 {
  font-size: var(--text-2xl);
  font-weight: 600;
}

.resources-layout {
  display: grid;
  grid-template-columns: 280px 300px 1fr;
  gap: 1rem;
}

.card-body {
  padding: 0;
}

.list-scroll,
.detail-scroll {
  max-height: 600px;
  overflow-y: auto;
  padding: 1rem;
}

.resource-item {
  padding: 0.75rem;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.resource-item:hover {
  border-color: var(--color-primary);
}

.resource-item.active {
  border-color: var(--color-primary);
  background-color: var(--color-primary-light);
}

.resource-item-title {
  font-size: var(--text-sm);
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.resource-item-meta {
  font-size: var(--text-xs);
  color: var(--color-muted);
}

.detail-title {
  font-size: var(--text-xl);
  font-weight: 600;
  margin-bottom: 1.25rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-line);
}

.detail-section {
  margin-bottom: 1.25rem;
}

.detail-section h4 {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-muted);
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.detail-section p {
  font-size: var(--text-base);
  color: var(--color-text-soft);
  line-height: 1.6;
  margin: 0;
}

.detail-section ul {
  padding-left: 1.25rem;
  font-size: var(--text-base);
  color: var(--color-text-soft);
}

.detail-section li {
  margin-bottom: 0.375rem;
  line-height: 1.5;
}

.mind-map {
  white-space: pre-wrap;
  font-size: var(--text-sm);
  background-color: var(--color-surface-strong);
  padding: 0.75rem;
  border-radius: var(--radius-sm);
  overflow-x: auto;
}

.rag-references {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.rag-ref-item {
  background-color: var(--color-surface-strong);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-sm);
  padding: 0.625rem;
}

.rag-ref-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.375rem;
}

.rag-ref-score {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary);
}

.rag-ref-meta {
  font-size: var(--text-xs);
  color: var(--color-muted);
}

.rag-ref-snippet {
  font-size: var(--text-sm);
  color: var(--color-text-soft);
  line-height: 1.5;
}

@media (max-width: 1200px) {
  .resources-layout {
    grid-template-columns: 1fr 1fr;
  }

  .resources-generator {
    grid-column: 1 / -1;
  }
}

@media (max-width: 768px) {
  .resources-layout {
    grid-template-columns: 1fr;
  }
}
</style>
