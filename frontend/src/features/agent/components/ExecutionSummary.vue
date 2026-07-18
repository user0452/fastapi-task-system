<script setup>
import { computed } from 'vue'
import { BookOpenCheck, Database, Globe2, ShieldCheck, Wrench } from 'lucide-vue-next'


const props = defineProps({
  summary: { type: Object, default: null }
})

const tools = computed(() => props.summary?.tools || [])
const internalSources = computed(() => props.summary?.internal_sources || [])
const externalSources = computed(() => props.summary?.external_sources || [])
const context = computed(() => props.summary?.context_used || {})
const updates = computed(() => props.summary?.updates || {})
const updateCount = computed(() => (
  (updates.value.memory?.length || 0)
  + (updates.value.roadmap?.length || 0)
  + (updates.value.mastery?.length || 0)
))
const itemCount = computed(() => (
  tools.value.length
  + internalSources.value.length
  + externalSources.value.length
  + Number(context.value.memory_count || 0)
  + updateCount.value
))

const statusLabels = {
  pending: '准备中',
  running: '执行中',
  completed: '成功',
  failed: '失败',
  timeout: '超时',
  waiting_confirmation: '等待确认'
}

function statusLabel(status) {
  return statusLabels[status] || status || '状态未知'
}

function sourceTitle(source, fallback) {
  return source.material_title || source.filename || source.title || fallback
}
</script>

<template>
  <details v-if="summary" class="execution-summary">
    <summary>
      <ShieldCheck :size="13" />
      <span>本次回答依据</span>
      <small>{{ itemCount ? `${itemCount} 项记录` : '未使用额外工具或来源' }}</small>
    </summary>

    <div class="summary-content">
      <section v-if="tools.length" class="summary-section">
        <h4><Wrench :size="12" /> 工具执行</h4>
        <ul class="tool-list">
          <li v-for="(tool, index) in tools" :key="`${tool.name}-${index}`">
            <span class="tool-name">{{ tool.name }}</span>
            <span class="tool-status" :class="tool.status">{{ statusLabel(tool.status) }}</span>
            <small v-if="tool.duration_ms != null">{{ Math.round(tool.duration_ms) }} ms</small>
          </li>
        </ul>
      </section>

      <section v-if="internalSources.length" class="summary-section internal-sources">
        <h4><BookOpenCheck :size="12" /> 课程资料</h4>
        <ul>
          <li v-for="source in internalSources" :key="source.chunk_id">
            <span>{{ sourceTitle(source, '课程片段') }}</span>
            <small v-if="source.page_number">第 {{ source.page_number }} 页</small>
            <small v-else-if="source.heading_path">{{ source.heading_path }}</small>
          </li>
        </ul>
      </section>

      <section v-if="externalSources.length" class="summary-section external-sources">
        <h4><Globe2 :size="12" /> 外部来源</h4>
        <ul>
          <li v-for="(source, index) in externalSources" :key="source.id || source.url || index">
            <a v-if="source.url" :href="source.url" target="_blank" rel="noreferrer">{{ sourceTitle(source, '外部资源') }}</a>
            <span v-else>{{ sourceTitle(source, '外部资源') }}</span>
            <small>{{ source.provider || source.resource_type || '网页' }}</small>
          </li>
        </ul>
      </section>

      <section v-if="context.memory_count || context.weak_point_count || context.recent_turns" class="summary-section context-section">
        <h4><Database :size="12" /> 使用的学习上下文</h4>
        <p>
          <span v-if="context.memory_count">长期记忆 {{ context.memory_count }} 条</span>
          <span v-if="context.weak_point_count">薄弱知识点 {{ context.weak_point_count }} 个</span>
          <span v-if="context.recent_turns">最近对话 {{ context.recent_turns }} 轮</span>
        </p>
      </section>

      <section v-if="updateCount" class="summary-section update-section">
        <h4><Database :size="12" /> 本次更新</h4>
        <p>
          <span v-if="updates.memory?.length">记忆 {{ updates.memory.length }} 项</span>
          <span v-if="updates.roadmap?.length">路线 {{ updates.roadmap.length }} 项</span>
          <span v-if="updates.mastery?.length">掌握度 {{ updates.mastery.length }} 项</span>
        </p>
      </section>

      <p class="summary-note">{{ summary.note || '这里只展示可验证的调用和数据依据。' }}</p>
    </div>
  </details>
</template>

<style scoped>
.execution-summary { margin-top: 10px; border-top: 1px solid #dfe5e1; color: #405149; }
.execution-summary summary { display: flex; align-items: center; gap: 5px; width: fit-content; min-height: 31px; color: #53645c; cursor: pointer; font-size: 10px; font-weight: 760; list-style: none; }
.execution-summary summary::-webkit-details-marker { display: none; }
.execution-summary summary::after { content: '›'; margin-left: 2px; color: #87948e; font-size: 15px; transform: rotate(90deg); transition: transform .18s ease; }
.execution-summary[open] summary::after { transform: rotate(-90deg); }
.execution-summary summary:focus-visible { outline: 2px solid #75aa98; outline-offset: 3px; border-radius: 2px; }
.execution-summary summary small { color: #8a9690; font-size: 9px; font-weight: 600; }
.summary-content { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px 16px; padding: 4px 0 10px; }
.summary-section { min-width: 0; }
.summary-section h4 { display: flex; align-items: center; gap: 4px; margin: 0 0 5px; color: #51615a; font-size: 9px; font-weight: 800; letter-spacing: .04em; }
.summary-section ul { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; }
.summary-section li { display: flex; align-items: center; gap: 6px; min-width: 0; font-size: 10px; }
.summary-section li > :first-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.summary-section li small { margin-left: auto; color: #8a9690; font-size: 8px; white-space: nowrap; }
.tool-name { color: #34443d; font-family: Consolas, "SFMono-Regular", monospace; }
.tool-status { flex: none; padding: 1px 5px; border-radius: 999px; color: #386656; background: rgba(36, 138, 61, .1); font-size: 8px; font-weight: 800; }
.tool-status.failed,
.tool-status.timeout { color: #9a443d; background: #f8e8e6; }
.tool-status.running,
.tool-status.pending,
.tool-status.waiting_confirmation { color: #7b642e; background: #f6efd9; }
.internal-sources { padding-left: 8px; border-left: 2px solid #83aa9d; }
.external-sources { padding-left: 8px; border-left: 2px solid #91adc7; }
.external-sources a { color: #326d8a; text-decoration: underline; text-decoration-color: #b6cedb; text-underline-offset: 2px; }
.context-section p,
.update-section p { display: flex; flex-wrap: wrap; gap: 4px; margin: 0; }
.context-section span,
.update-section span { padding: 2px 6px; border-radius: 999px; color: #4f6259; background: var(--surface-secondary); font-size: 9px; }
.summary-note { grid-column: 1 / -1; margin: 0; color: #8a9690; font-size: 9px; line-height: 1.5; }
@media (max-width: 620px) { .summary-content { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { .execution-summary summary::after { transition: none; } }
</style>
