<script setup>
import { ref, watch } from 'vue'
import { FileSearch, Search, Video } from 'lucide-vue-next'
import { getCourseResources, searchCourseResources } from '../../../api/courseResources'
import { searchCourseMaterials } from '../../../api/materials'
import { showToast } from '../../../components/common/toast'
import ResourceVideoCard from '../../agent/components/ResourceVideoCard.vue'
import MaterialWorkspace from '../../courses/components/MaterialWorkspace.vue'


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
const emit = defineEmits(['prompt', 'data-changed'])
const mode = ref('materials')
const materialQuery = ref('')
const resourceQuery = ref('')
const citations = ref([])
const resources = ref([])
const searchingMaterials = ref(false)
const searchingResources = ref(false)
const resourceWarning = ref('')

async function loadResources() {
  const response = await getCourseResources(props.courseId)
  resources.value = response.code === 200 ? response.data?.items || [] : []
}

async function searchMaterials() {
  if (!materialQuery.value.trim() || searchingMaterials.value) return
  searchingMaterials.value = true
  const response = await searchCourseMaterials(props.courseId, materialQuery.value.trim(), 5)
  searchingMaterials.value = false
  if (response.code === 200) citations.value = response.data?.citations || []
  else showToast({ type: 'error', message: response.message })
}

async function searchResources() {
  if (!resourceQuery.value.trim() || searchingResources.value) return
  searchingResources.value = true
  const response = await searchCourseResources(props.courseId, { topic: resourceQuery.value.trim(), max_results: 4 })
  searchingResources.value = false
  if (response.code === 200) {
    resources.value = response.data?.resources || []
    resourceWarning.value = response.data?.warning || ''
    emit('data-changed')
  } else showToast({ type: 'error', message: response.message })
}

function updateResource(updated) {
  resources.value = resources.value.map(item => item.id === updated.id ? updated : item)
  emit('data-changed')
}

function practiceResource(resource) {
  const point = resource.knowledge_point_id ? `知识点 #${resource.knowledge_point_id}` : '相关知识点'
  emit('prompt', `我已经学习了“${resource.title}”，请围绕${point}给我出 3 道题。`)
}

function materialChanged() {
  citations.value = []
  emit('data-changed')
}

watch(() => [props.courseId, props.refreshKey], loadResources, { immediate: true })
</script>

<template>
  <div class="materials-resources-panel">
    <div class="panel-segment" role="tablist" aria-label="资料与资源">
      <button type="button" :class="{ active: mode === 'materials' }" @click="mode = 'materials'">课程资料</button>
      <button type="button" :class="{ active: mode === 'resources' }" @click="mode = 'resources'">外部视频</button>
    </div>

    <template v-if="mode === 'materials'">
      <form class="panel-search" @submit.prevent="searchMaterials">
        <FileSearch :size="15" />
        <input v-model="materialQuery" placeholder="检索本课程资料片段" />
        <button type="submit" :disabled="!materialQuery.trim() || searchingMaterials" title="检索资料" aria-label="检索资料"><Search :size="15" /></button>
      </form>
      <section v-if="citations.length" class="citation-results">
        <article v-for="citation in citations" :key="citation.chunk_id">
          <header><strong>{{ citation.material_title }}</strong><span>{{ Math.round(Number(citation.score) * 100) }}%</span></header>
          <small>{{ citation.page_number ? `第 ${citation.page_number} 页 · ` : '' }}片段 {{ citation.chunk_index + 1 }}</small>
          <p>{{ citation.snippet }}</p>
          <div v-if="citation.knowledge_points?.length">
            <span v-for="point in citation.knowledge_points" :key="point.id">{{ point.name }}</span>
          </div>
        </article>
      </section>
      <MaterialWorkspace :course-id="courseId" @processed="materialChanged" />
    </template>

    <template v-else>
      <form class="panel-search" @submit.prevent="searchResources">
        <Video :size="15" />
        <input v-model="resourceQuery" placeholder="搜索本课程的外部视频" />
        <button type="submit" :disabled="!resourceQuery.trim() || searchingResources" title="搜索视频" aria-label="搜索视频"><Search :size="15" /></button>
      </form>
      <p v-if="resourceWarning" class="resource-warning">{{ resourceWarning }}</p>
      <div v-if="resources.length" class="resource-list">
        <ResourceVideoCard
          v-for="resource in resources"
          :key="resource.id"
          :resource="resource"
          :course-id="courseId"
          compact
          @updated="updateResource"
          @practice="practiceResource"
        />
      </div>
      <div v-else class="resource-empty">
        <Video :size="27" /><strong>还没有外部视频</strong><p>搜索结果会保留收藏、观看和有用性状态。</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.materials-resources-panel { display: grid; gap: 16px; }
.panel-segment { display: grid; grid-template-columns: 1fr 1fr; padding: 4px; border-radius: 14px; background: var(--surface-tertiary); }
.panel-segment button { height: 38px; border-radius: 11px; color: var(--text-secondary); font-size: 13px; font-weight: 600; }
.panel-segment button.active { color: var(--accent); background: #fff; box-shadow: var(--shadow-small); }
.panel-search { height: 44px; display: grid; grid-template-columns: 28px minmax(0, 1fr) 38px; align-items: center; gap: 4px; padding: 0 6px 0 12px; border: 1px solid var(--border-strong); border-radius: 13px; color: var(--text-tertiary); background: #fff; }
.panel-search:focus-within { border-color: var(--accent); box-shadow: var(--shadow-focus); }
.panel-search input { min-width: 0; border: 0; color: var(--text-primary); font-size: 13px; background: transparent; }
.panel-search button { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 10px; color: var(--accent); }
.panel-search button:hover { background: var(--accent-soft); }
.panel-search button:disabled { opacity: .4; }
.citation-results { display: grid; max-height: 340px; overflow-y: auto; border-block: 1px solid var(--border-subtle); }
.citation-results article { display: grid; gap: 5px; padding: 12px 2px; border-bottom: 1px solid var(--border-subtle); }
.citation-results header { display: flex; justify-content: space-between; gap: 8px; }
.citation-results strong { color: var(--text-primary); font-size: 13px; }
.citation-results header span { color: var(--accent); font-size: 12px; font-weight: 600; }
.citation-results small { color: var(--text-tertiary); font-size: 11px; }
.citation-results p { display: -webkit-box; overflow: hidden; color: var(--text-secondary); font-size: 12px; line-height: 1.6; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.citation-results article > div { display: flex; flex-wrap: wrap; gap: 5px; }
.citation-results article > div span { padding: 3px 7px; border-radius: 999px; color: var(--accent); background: var(--accent-soft); font-size: 11px; }
.resource-list { display: grid; gap: 10px; }
.resource-warning { padding: 11px 12px; border-radius: 12px; border-left: 3px solid var(--warning); color: var(--text-secondary); background: rgba(169, 101, 0, .08); font-size: 12px; }
.resource-empty { min-height: 240px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: var(--text-secondary); text-align: center; }
.resource-empty svg { color: var(--accent); }
.resource-empty strong { color: var(--text-primary); font-size: 16px; font-weight: 620; }
.resource-empty p { max-width: 280px; font-size: 13px; line-height: 1.65; }
.materials-resources-panel :deep(.materials-workspace) { gap: 16px; }
.materials-resources-panel :deep(.material-editor) { border: 0; border-radius: 0; background: transparent; }
.materials-resources-panel :deep(.editor-heading) { padding: 10px 0; }
.materials-resources-panel :deep(.editor-heading p) { display: none; }
.materials-resources-panel :deep(.editor-fields) { padding: 12px 0; }
.materials-resources-panel :deep(.editor-actions) { padding: 10px 0; background: transparent; }
.materials-resources-panel :deep(.mode-switch button) { min-width: 72px; font-size: 12px; }
.materials-resources-panel :deep(.file-picker) { min-height: 110px; border-radius: 14px; }
.materials-resources-panel :deep(.material-row) { grid-template-columns: 34px minmax(0, 1fr) auto auto; }
.materials-resources-panel :deep(.material-row .status) { grid-column: 3; }
.materials-resources-panel :deep(.material-row .material-actions) { grid-column: 4; }
.materials-resources-panel :deep(.material-copy span) { max-width: 210px; }
</style>
