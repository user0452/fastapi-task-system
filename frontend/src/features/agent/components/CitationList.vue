<script setup>
import { FileText } from 'lucide-vue-next'


defineProps({
  citations: { type: Array, default: () => [] },
  courseId: { type: Number, default: null }
})
</script>

<template>
  <div v-if="citations.length" class="citation-list">
    <span class="citation-label">资料引用</span>
    <router-link
      v-for="(citation, index) in citations"
      :key="citation.chunk_id"
      :to="courseId
        ? { path: `/learn/${courseId}`, query: { panel: 'materials', material_id: citation.material_id, chunk: citation.chunk_id } }
        : { path: '/courses', query: { tab: 'materials', material_id: citation.material_id, chunk: citation.chunk_id } }"
      class="citation-row"
    >
      <FileText :size="14" />
      <span>
        <strong>[{{ index + 1 }}] {{ citation.material_title }}</strong>
        <small>
          {{ citation.page_number ? `第 ${citation.page_number} 页 · ` : '' }}片段 {{ citation.chunk_index + 1 }} · 匹配 {{ Math.round(Number(citation.score) * 100) }}%
        </small>
        <p>{{ citation.snippet }}</p>
      </span>
    </router-link>
  </div>
</template>

<style scoped>
.citation-list { display: grid; gap: 5px; margin-top: 10px; padding-top: 9px; border-top: 1px solid #dde3df; }
.citation-label { color: #6d7872; font-size: 9px; font-weight: 750; }
.citation-row { display: grid; grid-template-columns: 17px minmax(0, 1fr); gap: 5px; padding: 7px 8px; border-radius: 5px; color: #52605a; background: #f2f5f3; }
.citation-row:hover { color: #175d4c; background: #e6efea; }
.citation-row svg { margin-top: 1px; }
.citation-row span { min-width: 0; display: grid; gap: 1px; }
.citation-row strong,
.citation-row small,
.citation-row p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.citation-row strong { font-size: 9px; }
.citation-row small { color: #7a847f; font-size: 8px; }
.citation-row p { color: #68736d; font-size: 8px; }
</style>
