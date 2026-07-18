<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'


echarts.use([GraphChart, TooltipComponent, CanvasRenderer])

const props = defineProps({
  points: { type: Array, default: () => [] },
  relations: { type: Array, default: () => [] },
  selectedId: { type: Number, default: null },
  showLabels: { type: Boolean, default: true }
})
const emit = defineEmits(['select'])
const host = ref(null)
let chart = null
let resizeObserver = null

const degree = computed(() => {
  const values = new Map(props.points.map(point => [Number(point.id), 0]))
  props.relations.forEach(relation => {
    const source = Number(relation.source_point_id)
    const target = Number(relation.target_point_id)
    values.set(source, (values.get(source) || 0) + 1)
    values.set(target, (values.get(target) || 0) + 1)
  })
  return values
})

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function masteryStyle(mastery) {
  if (mastery >= 80) return { color: '#23735a', border: '#155b47' }
  if (mastery >= 60) return { color: '#77906f', border: '#536f4d' }
  if (mastery > 0) return { color: '#b46b5f', border: '#8f4e45' }
  return { color: '#a7b0ab', border: '#77827c' }
}

function option() {
  const compact = props.points.length > 120
  return {
    animationDurationUpdate: compact ? 0 : 240,
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: '#fff',
      borderColor: '#cfd8d3',
      textStyle: { color: '#33403a', fontSize: 11 },
      formatter(params) {
        if (params.dataType === 'edge') {
          const relation = params.data.raw
          return `<strong>${escapeHtml(relation.source_name)} → ${escapeHtml(relation.target_name)}</strong><br>${escapeHtml(relation.relation_type)} · 可信度 ${Math.round(Number(relation.confidence || 0) * 100)}%`
        }
        const point = params.data.raw
        return `<strong>${escapeHtml(point.name)}</strong><br>掌握度 ${Math.round(Number(point.mastery || 0))}%<br>${escapeHtml(point.category || point.knowledge_level || '未分类')}`
      }
    },
    series: [{
      type: 'graph',
      layout: 'force',
      data: props.points.map(point => {
        const mastery = Number(point.mastery || 0)
        const style = masteryStyle(mastery)
        const selected = Number(point.id) === Number(props.selectedId)
        return {
          id: String(point.id),
          name: point.name,
          value: mastery,
          raw: point,
          symbolSize: Math.min(58, 30 + (degree.value.get(Number(point.id)) || 0) * 3),
          draggable: true,
          itemStyle: {
            color: style.color,
            borderColor: selected ? '#173f34' : style.border,
            borderWidth: selected ? 4 : 1.5,
            shadowBlur: selected ? 8 : 0,
            shadowColor: 'rgba(23, 63, 52, .22)'
          },
          label: {
            show: props.showLabels && !compact,
            color: '#27342e',
            fontSize: 9,
            width: 82,
            overflow: 'truncate',
            position: 'bottom',
            distance: 4
          }
        }
      }),
      links: props.relations.map(relation => ({
        source: String(relation.source_point_id),
        target: String(relation.target_point_id),
        raw: relation,
        lineStyle: {
          width: 1 + Number(relation.confidence || 0) * 1.5,
          color: relation.relation_type === 'prerequisite' ? '#7b9b8e' : '#a9b4ae',
          opacity: .72,
          curveness: .08
        }
      })),
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 6],
      edgeLabel: {
        show: props.showLabels && props.relations.length <= 40,
        formatter: params => params.data.raw.relation_type,
        color: '#6f7a74',
        fontSize: 8,
        backgroundColor: 'rgba(248,250,248,.82)',
        padding: [1, 2]
      },
      roam: true,
      scaleLimit: { min: .35, max: 3 },
      force: {
        initLayout: 'circular',
        repulsion: compact ? 85 : 130,
        gravity: .08,
        edgeLength: [62, 118],
        friction: .55,
        layoutAnimation: !compact
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3, opacity: 1 }
      }
    }]
  }
}

function render() {
  if (!chart) return
  chart.setOption(option(), { notMerge: true, lazyUpdate: false })
}

function resetView() {
  if (!chart) return
  chart.dispatchAction({ type: 'restore' })
  chart.resize()
}

function relayout() {
  render()
}

onMounted(async () => {
  await nextTick()
  if (!host.value) return
  chart = echarts.init(host.value, null, { renderer: 'canvas' })
  chart.on('click', params => {
    if (params.dataType === 'node') emit('select', Number(params.data.id))
  })
  render()
  if (window.ResizeObserver) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(host.value)
  } else window.addEventListener('resize', resetView)
})

watch(() => [props.points, props.relations, props.selectedId, props.showLabels], render, { deep: true })

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', resetView)
  chart?.dispose()
  chart = null
})

defineExpose({ resetView, relayout })
</script>

<template>
  <div
    ref="host"
    class="graph-canvas"
    role="img"
    :aria-label="`知识图谱，${points.length} 个节点，${relations.length} 条关系。可缩放、平移和拖拽节点。`"
  ></div>
</template>

<style scoped>
.graph-canvas { width: 100%; height: 390px; min-height: 320px; background: #f5f7f5; border: 1px solid #dce2de; }
@media (max-width: 820px) { .graph-canvas { height: 360px; } }
</style>
