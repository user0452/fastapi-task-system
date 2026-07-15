<script setup>
import { computed, ref, watch } from 'vue'
import { ArrowRight, GitBranch } from 'lucide-vue-next'
import { getCourseProgress } from '../../../api/learning'
import { getKnowledgeGraph } from '../../../api/materials'


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
defineEmits(['prompt'])
const loading = ref(true)
const graph = ref({ points: [], relations: [] })
const progress = ref(null)

const points = computed(() => {
  const mastery = new Map((progress.value?.knowledge_points || []).map(item => [item.id, item]))
  return (graph.value.points || []).map(point => ({ ...point, mastery: Number(mastery.get(point.id)?.mastery || 0) }))
})

function level(value) {
  if (value >= 80) return { label: '已掌握', class: 'high' }
  if (value >= 60) return { label: '巩固中', class: 'medium' }
  if (value > 0) return { label: '薄弱', class: 'low' }
  return { label: '未学习', class: 'empty' }
}

async function load() {
  loading.value = true
  const [graphResponse, progressResponse] = await Promise.all([
    getKnowledgeGraph(props.courseId),
    getCourseProgress(props.courseId)
  ])
  graph.value = graphResponse.code === 200 ? graphResponse.data : { points: [], relations: [] }
  progress.value = progressResponse.code === 200 ? progressResponse.data : null
  loading.value = false
}

watch(() => [props.courseId, props.refreshKey], load, { immediate: true })
</script>

<template>
  <div class="knowledge-panel">
    <div v-if="loading" class="panel-state">正在读取知识图谱</div>
    <div v-else-if="!points.length" class="panel-empty">
      <GitBranch :size="27" /><strong>还没有知识点</strong><p>添加课程资料后会自动提取并建立向量索引。</p>
    </div>
    <template v-else>
      <section class="knowledge-legend">
        <span><i class="high"></i>已掌握 {{ points.filter(item => item.mastery >= 80).length }}</span>
        <span><i class="medium"></i>巩固中 {{ points.filter(item => item.mastery >= 60 && item.mastery < 80).length }}</span>
        <span><i class="low"></i>薄弱 {{ points.filter(item => item.mastery < 60).length }}</span>
      </section>
      <section class="knowledge-list">
        <article v-for="point in points" :key="point.id">
          <div class="point-heading">
            <span :class="level(point.mastery).class">{{ level(point.mastery).label }}</span>
            <strong>{{ point.name }}</strong>
            <b>{{ point.mastery.toFixed(0) }}</b>
          </div>
          <p>{{ point.summary || point.description || '暂无知识点描述' }}</p>
          <small v-if="point.examples?.length" class="point-example">例：{{ point.examples[0] }}</small>
          <div class="mastery-track"><i :class="level(point.mastery).class" :style="{ width: `${Math.max(2, point.mastery)}%` }"></i></div>
          <button type="button" @click="$emit('prompt', `讲解“${point.name}”，然后给我一道题`)" title="在对话中学习">
            学习这个知识点 <ArrowRight :size="13" />
          </button>
        </article>
      </section>
      <section class="relations">
        <header><GitBranch :size="15" /><strong>知识依赖</strong><span>{{ graph.relations.length }}</span></header>
        <div v-if="graph.relations.length">
          <p v-for="relation in graph.relations" :key="relation.id">
            <span>{{ relation.source_name }}</span><ArrowRight :size="12" /><strong>{{ relation.target_name }}</strong>
          </p>
        </div>
        <p v-else class="relation-empty">当前资料尚未形成明确依赖链。</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.knowledge-panel { display: grid; gap: 17px; }
.panel-state,
.panel-empty { min-height: 260px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #78827d; text-align: center; }
.panel-state { font-size: 12px; }
.panel-empty svg { color: #27715d; }
.panel-empty strong { color: #35413b; font-size: 13px; }
.panel-empty p { max-width: 240px; font-size: 11px; }
.knowledge-legend { display: flex; flex-wrap: wrap; gap: 8px 12px; padding-bottom: 11px; border-bottom: 1px solid #dfe4e1; }
.knowledge-legend span { display: inline-flex; align-items: center; gap: 4px; color: #747e79; font-size: 10px; }
.knowledge-legend i { width: 6px; height: 6px; border-radius: 50%; }
.high { background: #25805f; }
.medium { background: #c68a27; }
.low { background: #c45a50; }
.empty { background: #aeb7b2; }
.knowledge-list { display: grid; }
.knowledge-list article { display: grid; gap: 6px; padding: 13px 0; border-bottom: 1px solid #e1e5e2; }
.point-heading { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 7px; }
.point-heading > span { padding: 2px 5px; border-radius: 4px; color: #fff; font-size: 9px; font-weight: 740; }
.point-heading strong { overflow: hidden; color: #33403a; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.point-heading b { color: #5e6b64; font-size: 11px; }
.knowledge-list article > p { color: #78827d; font-size: 10px; line-height: 1.55; }
.point-example { color: #6d7872; font-size: 9px; line-height: 1.5; }
.mastery-track { height: 5px; overflow: hidden; border-radius: 3px; background: #e5e9e6; }
.mastery-track i { display: block; height: 100%; border-radius: inherit; }
.knowledge-list button { display: inline-flex; align-items: center; gap: 4px; justify-self: end; color: #176b58; font-size: 10px; font-weight: 720; }
.relations { padding-top: 2px; }
.relations header { display: flex; align-items: center; gap: 6px; padding-bottom: 8px; color: #2a6b59; border-bottom: 1px solid #dfe4e1; }
.relations header strong { font-size: 12px; }
.relations header span { margin-left: auto; color: #808984; font-size: 10px; }
.relations p { display: grid; grid-template-columns: minmax(0, 1fr) 14px minmax(0, 1fr); align-items: center; gap: 5px; padding: 8px 0; border-bottom: 1px solid #e5e8e6; font-size: 10px; }
.relations p span { color: #737e78; }
.relations p strong { color: #34413a; }
.relations .relation-empty { display: block; color: #858e89; }
</style>
