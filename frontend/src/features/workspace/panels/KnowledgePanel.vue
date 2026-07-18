<script setup>
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import {
  ArrowRight,
  Focus,
  GitBranch,
  List,
  Network,
  RefreshCw,
  Search,
  Tags
} from 'lucide-vue-next'
import { getCourseProgress } from '../../../api/learning'
import { getKnowledgeGraph } from '../../../api/materials'


const KnowledgeGraphCanvas = defineAsyncComponent(() => import('../components/KnowledgeGraphCanvas.vue'))


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
const emit = defineEmits(['prompt'])
const loading = ref(true)
const error = ref('')
const graph = ref({ points: [], relations: [] })
const progress = ref(null)
const canvas = ref(null)
const search = ref('')
const masteryFilter = ref('all')
const categoryFilter = ref('all')
const relationFilter = ref('all')
const showLabels = ref(true)
const viewMode = ref('graph')
const selectedId = ref(null)

const points = computed(() => {
  const mastery = new Map((progress.value?.knowledge_points || []).map(item => [Number(item.id), item]))
  return (graph.value.points || []).map(point => ({
    ...point,
    mastery: Number(mastery.get(Number(point.id))?.mastery || 0)
  }))
})

const categories = computed(() => Array.from(new Set(points.value.map(point => point.category).filter(Boolean))).sort())
const relationTypes = computed(() => Array.from(new Set((graph.value.relations || []).map(item => item.relation_type).filter(Boolean))).sort())

function masteryGroup(value) {
  if (value >= 80) return 'high'
  if (value >= 60) return 'medium'
  if (value > 0) return 'low'
  return 'empty'
}

function level(value) {
  return {
    high: { label: '已掌握', class: 'high' },
    medium: { label: '巩固中', class: 'medium' },
    low: { label: '薄弱', class: 'low' },
    empty: { label: '未学习', class: 'empty' }
  }[masteryGroup(value)]
}

const filteredPoints = computed(() => {
  const keyword = search.value.trim().toLocaleLowerCase()
  return points.value.filter(point => {
    if (masteryFilter.value !== 'all' && masteryGroup(point.mastery) !== masteryFilter.value) return false
    if (categoryFilter.value !== 'all' && point.category !== categoryFilter.value) return false
    if (!keyword) return true
    return `${point.name} ${point.summary || ''} ${point.description || ''}`.toLocaleLowerCase().includes(keyword)
  })
})

const filteredRelations = computed(() => {
  const ids = new Set(filteredPoints.value.map(point => Number(point.id)))
  return (graph.value.relations || []).filter(relation => (
    ids.has(Number(relation.source_point_id))
    && ids.has(Number(relation.target_point_id))
    && (relationFilter.value === 'all' || relation.relation_type === relationFilter.value)
  ))
})

const selected = computed(() => points.value.find(point => Number(point.id) === Number(selectedId.value)) || null)
const selectedRelations = computed(() => selected.value ? (graph.value.relations || []).filter(relation => (
  Number(relation.source_point_id) === Number(selected.value.id)
  || Number(relation.target_point_id) === Number(selected.value.id)
)) : [])

function selectPoint(id) {
  selectedId.value = Number(id)
}

function resetFilters() {
  search.value = ''
  masteryFilter.value = 'all'
  categoryFilter.value = 'all'
  relationFilter.value = 'all'
}

async function load() {
  loading.value = true
  error.value = ''
  const [graphResponse, progressResponse] = await Promise.all([
    getKnowledgeGraph(props.courseId),
    getCourseProgress(props.courseId)
  ])
  graph.value = graphResponse.code === 200 ? graphResponse.data : { points: [], relations: [] }
  progress.value = progressResponse.code === 200 ? progressResponse.data : null
  if (graphResponse.code !== 200) error.value = graphResponse.message || '知识图谱读取失败'
  selectedId.value = graph.value.points?.[0]?.id || null
  loading.value = false
}

watch(() => [props.courseId, props.refreshKey], load, { immediate: true })
</script>

<template>
  <div class="knowledge-panel">
    <div v-if="loading" class="panel-state">正在读取知识图谱</div>
    <div v-else-if="error" class="panel-empty">
      <GitBranch :size="27" /><strong>知识图谱读取失败</strong><p>{{ error }}</p>
      <button type="button" @click="load">重新读取</button>
    </div>
    <div v-else-if="!points.length" class="panel-empty">
      <GitBranch :size="27" /><strong>还没有知识点</strong><p>添加课程资料后会提取真实知识点与有证据的关系；这里不会显示演示节点。</p>
    </div>
    <template v-else>
      <header class="graph-summary">
        <div><span>课程知识结构</span><strong>{{ points.length }} 个节点 · {{ graph.relations.length }} 条关系</strong></div>
        <button type="button" :title="viewMode === 'graph' ? '切换为可访问列表' : '切换为图谱'" @click="viewMode = viewMode === 'graph' ? 'list' : 'graph'">
          <List v-if="viewMode === 'graph'" :size="15" /><Network v-else :size="15" />
        </button>
      </header>

      <section class="graph-filters" aria-label="图谱筛选">
        <label class="search-field"><Search :size="13" /><input v-model="search" placeholder="搜索知识点" /></label>
        <select v-model="masteryFilter" aria-label="按掌握度筛选">
          <option value="all">全部掌握度</option><option value="high">已掌握</option><option value="medium">巩固中</option><option value="low">薄弱</option><option value="empty">未学习</option>
        </select>
        <select v-model="categoryFilter" aria-label="按知识类别筛选">
          <option value="all">全部类别</option><option v-for="category in categories" :key="category" :value="category">{{ category }}</option>
        </select>
        <select v-model="relationFilter" aria-label="按关系类型筛选">
          <option value="all">全部关系</option><option v-for="type in relationTypes" :key="type" :value="type">{{ type }}</option>
        </select>
      </section>

      <section class="knowledge-legend">
        <span><i class="high"></i>已掌握 {{ points.filter(item => item.mastery >= 80).length }}</span>
        <span><i class="medium"></i>巩固中 {{ points.filter(item => item.mastery >= 60 && item.mastery < 80).length }}</span>
        <span><i class="low"></i>薄弱 {{ points.filter(item => item.mastery > 0 && item.mastery < 60).length }}</span>
        <span><i class="empty"></i>未学习 {{ points.filter(item => item.mastery === 0).length }}</span>
      </section>

      <template v-if="viewMode === 'graph'">
        <div class="graph-toolbar">
          <span>{{ filteredPoints.length }} 个可见节点 · {{ filteredRelations.length }} 条可见关系</span>
          <label><input v-model="showLabels" type="checkbox" /> 显示标签</label>
          <button type="button" title="重新自动布局" @click="canvas?.relayout()"><RefreshCw :size="13" /> 自动布局</button>
          <button type="button" title="重置缩放与位置" @click="canvas?.resetView()"><Focus :size="13" /> 重置视图</button>
        </div>
        <p v-if="points.length > 120" class="performance-note">大型图谱已启用精简模式：隐藏部分标签与布局动画，筛选后可查看细节。</p>
        <KnowledgeGraphCanvas
          v-if="filteredPoints.length"
          ref="canvas"
          :points="filteredPoints"
          :relations="filteredRelations"
          :selected-id="selectedId"
          :show-labels="showLabels"
          @select="selectPoint"
        />
        <div v-else class="filter-empty"><strong>没有匹配的节点</strong><button type="button" @click="resetFilters">清除筛选</button></div>
      </template>

      <section v-else class="knowledge-list" aria-label="知识点列表视图">
        <article v-for="point in filteredPoints" :key="point.id" :class="{ selected: point.id === selectedId }">
          <button type="button" @click="selectPoint(point.id)">
            <span :class="level(point.mastery).class">{{ level(point.mastery).label }}</span>
            <strong>{{ point.name }}</strong><b>{{ point.mastery.toFixed(0) }}%</b>
          </button>
          <p>{{ point.summary || point.description || '暂无知识点描述' }}</p>
        </article>
        <div v-if="!filteredPoints.length" class="filter-empty"><strong>没有匹配的节点</strong><button type="button" @click="resetFilters">清除筛选</button></div>
      </section>

      <aside v-if="selected" class="point-detail" aria-live="polite">
        <header>
          <div><span :class="level(selected.mastery).class">{{ level(selected.mastery).label }}</span><strong>{{ selected.name }}</strong></div>
          <b>{{ selected.mastery.toFixed(0) }}%</b>
        </header>
        <p>{{ selected.summary || selected.description || '暂无知识点描述' }}</p>
        <dl>
          <div><dt><Tags :size="11" /> 类别</dt><dd>{{ selected.category || '未分类' }}</dd></div>
          <div><dt><Network :size="11" /> 层级</dt><dd>{{ selected.knowledge_level || 'concept' }}</dd></div>
        </dl>
        <section class="evidence-list">
          <strong>资料证据</strong>
          <article v-for="item in selected.evidence || []" :key="item.chunk_id">
            <span>{{ item.material_title }} · 片段 {{ item.chunk_index + 1 }}</span>
            <p>{{ item.snippet }}</p>
          </article>
          <p v-if="!selected.evidence?.length" class="muted">当前节点没有可展示的资料摘录。</p>
        </section>
        <section class="detail-relations">
          <strong>直接关系 {{ selectedRelations.length }}</strong>
          <p v-for="relation in selectedRelations" :key="relation.id">
            {{ relation.source_name }} <ArrowRight :size="11" /> {{ relation.target_name }}
            <small>{{ relation.relation_type }} · {{ Math.round(relation.confidence * 100) }}%</small>
          </p>
        </section>
        <div class="detail-actions">
          <button type="button" @click="emit('prompt', `结合课程资料讲解“${selected.name}”，并说明它和相邻知识点的关系`)">讲解与关系</button>
          <button type="button" @click="emit('prompt', `围绕“${selected.name}”给我一道练习题并在我回答后评分`)">开始练习</button>
        </div>
      </aside>
    </template>
  </div>
</template>

<style scoped>
.knowledge-panel { display: grid; gap: 13px; }
.panel-state,
.panel-empty { min-height: 260px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #78827d; text-align: center; }
.panel-state { font-size: 12px; }
.panel-empty svg { color: #27715d; }
.panel-empty strong { color: #35413b; font-size: 13px; }
.panel-empty p { max-width: 270px; font-size: 11px; line-height: 1.5; }
.panel-empty button,
.filter-empty button { min-height: 32px; padding: 0 9px; color: #fff; background: #176b58; font-size: 9px; }
.graph-summary { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-bottom: 10px; border-bottom: 1px solid #dfe4e1; }
.graph-summary > div { display: grid; gap: 2px; }
.graph-summary span { color: #19705a; font-size: 9px; font-weight: 760; }
.graph-summary strong { color: #34413a; font-size: 12px; }
.graph-summary button { width: 31px; height: 31px; display: grid; place-items: center; color: #176b58; background: #e7efeb; }
.graph-filters { display: grid; grid-template-columns: minmax(120px, 1.4fr) repeat(3, minmax(82px, 1fr)); gap: 5px; }
.search-field { min-width: 0; display: flex; align-items: center; gap: 4px; padding: 0 7px; border: 1px solid #ccd5d0; background: #fff; }
.search-field input { min-width: 0; width: 100%; height: 32px; font-size: 9px; }
.graph-filters select { min-width: 0; height: 34px; padding: 0 5px; border: 1px solid #ccd5d0; background: #fff; color: #59655f; font-size: 9px; }
.knowledge-legend { display: flex; flex-wrap: wrap; gap: 6px 10px; }
.knowledge-legend span { display: inline-flex; align-items: center; gap: 4px; color: #747e79; font-size: 9px; }
.knowledge-legend i { width: 6px; height: 6px; border-radius: 50%; }
.high { background: #23735a; }.medium { background: #77906f; }.low { background: #b46b5f; }.empty { background: #a7b0ab; }
.graph-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 5px 8px; color: #737e78; font-size: 8px; }
.graph-toolbar > span { margin-right: auto; }
.graph-toolbar label,
.graph-toolbar button { display: inline-flex; align-items: center; gap: 3px; }
.graph-toolbar button { min-height: 28px; padding: 0 6px; color: #176b58; background: #e7efeb; }
.performance-note { padding: 7px 8px; color: #6e776f; background: #edf1ee; font-size: 8px; }
.filter-empty { min-height: 180px; display: grid; place-content: center; justify-items: center; gap: 8px; color: #75807a; font-size: 10px; }
.knowledge-list { display: grid; max-height: 420px; overflow-y: auto; border-top: 1px solid #e1e5e2; }
.knowledge-list article { display: grid; gap: 5px; padding: 9px 0; border-bottom: 1px solid #e1e5e2; }
.knowledge-list article.selected { background: #edf3f0; }
.knowledge-list article > button { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 6px; width: 100%; text-align: left; }
.knowledge-list article span,
.point-detail header span { padding: 2px 5px; color: #fff; font-size: 8px; }
.knowledge-list article strong { color: #34413a; font-size: 10px; }
.knowledge-list article b { color: #5d6862; font-size: 9px; }
.knowledge-list article p { color: #748079; font-size: 9px; }
.point-detail { display: grid; gap: 10px; padding: 12px; background: #f0f4f1; border-left: 2px solid #27715d; }
.point-detail > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.point-detail header > div { display: flex; align-items: center; gap: 6px; }
.point-detail header strong { color: #2f3d36; font-size: 12px; }
.point-detail header b { color: #176b58; font-size: 11px; }
.point-detail > p { color: #65716a; font-size: 10px; line-height: 1.55; }
.point-detail dl { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.point-detail dl > div { display: grid; gap: 2px; padding: 6px; background: #fff; }
.point-detail dt { display: flex; align-items: center; gap: 3px; color: #78827d; font-size: 8px; }
.point-detail dd { color: #46534c; font-size: 9px; }
.evidence-list,
.detail-relations { display: grid; gap: 5px; }
.evidence-list > strong,
.detail-relations > strong { color: #4f5d55; font-size: 9px; }
.evidence-list article { display: grid; gap: 3px; padding: 7px; background: #fff; }
.evidence-list article span { color: #26705b; font-size: 8px; }
.evidence-list article p { display: -webkit-box; overflow: hidden; color: #626e67; font-size: 9px; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.muted { color: #808984; font-size: 9px; }
.detail-relations > p { display: flex; flex-wrap: wrap; align-items: center; gap: 3px; color: #5d6962; font-size: 9px; }
.detail-relations small { margin-left: auto; color: #7d8681; font-size: 8px; }
.detail-actions { display: flex; justify-content: flex-end; gap: 5px; }
.detail-actions button { min-height: 30px; padding: 0 8px; color: #176b58; border: 1px solid #adc5ba; background: #fff; font-size: 9px; }
@media (max-width: 520px) { .graph-filters { grid-template-columns: 1fr 1fr; }.search-field { grid-column: 1 / -1; } }
</style>
