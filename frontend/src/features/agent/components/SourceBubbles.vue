<script setup>
import { computed, ref } from 'vue'
import { ExternalLink, FileText, Globe2, LoaderCircle } from 'lucide-vue-next'
import { getCourseMaterialChunk } from '../../../api/agent'

const props = defineProps({
  citations: { type: Array, default: () => [] },
  resources: { type: Array, default: () => [] },
  courseId: { type: Number, default: null }
})

const openId = ref(null)
const loadingId = ref(null)
const details = ref({})

const sources = computed(() => [
  ...props.citations.map(item => ({
    id: `rag-${item.chunk_id}`,
    kind: 'rag',
    title: item.material_title || '课程资料',
    meta: `${item.page_number ? `第 ${item.page_number} 页 · ` : ''}片段 ${Number(item.chunk_index || 0) + 1}`,
    preview: item.snippet || '',
    chunkId: item.chunk_id
  })),
  ...props.resources.map(item => ({
    id: `web-${item.id || item.canonical_url}`,
    kind: 'web',
    title: item.title || '联网来源',
    meta: item.provider || '网页',
    preview: item.summary || item.description || '',
    href: item.canonical_url || item.url
  }))
])

async function toggle(source) {
  if (openId.value === source.id) {
    openId.value = null
    return
  }
  openId.value = source.id
  if (source.kind !== 'rag' || details.value[source.id] || !props.courseId) return
  loadingId.value = source.id
  try {
    const response = await getCourseMaterialChunk(props.courseId, source.chunkId)
    details.value[source.id] = response.data
  } finally {
    loadingId.value = null
  }
}
</script>

<template>
  <section v-if="sources.length" class="source-footnotes" aria-label="回答来源">
    <span class="source-label">来源</span>
    <div class="source-bubble-row">
      <div v-for="source in sources" :key="source.id" class="source-item">
        <button class="source-bubble" :class="source.kind" type="button" @click="toggle(source)">
          <FileText v-if="source.kind === 'rag'" :size="12" />
          <Globe2 v-else :size="12" />
          <span>{{ source.title }}</span>
          <small>{{ source.meta }}</small>
        </button>
        <Transition name="source-reveal">
          <div v-if="openId === source.id" class="source-detail">
            <div class="source-detail-head">
              <strong>{{ source.title }}</strong>
              <span>{{ source.meta }}</span>
            </div>
            <div v-if="loadingId === source.id" class="source-loading"><LoaderCircle :size="14" /> 正在读取原文</div>
            <template v-else-if="source.kind === 'rag'">
              <p class="source-original">{{ details[source.id]?.chunk_text || '暂时无法读取该资料片段。' }}</p>
              <small v-if="details[source.id]?.heading_path">{{ details[source.id].heading_path }}</small>
            </template>
            <template v-else>
              <p class="source-original">{{ source.preview || '该来源未提供摘要。' }}</p>
              <a v-if="source.href" :href="source.href" target="_blank" rel="noreferrer"><ExternalLink :size="12" /> 打开网页</a>
            </template>
          </div>
        </Transition>
      </div>
    </div>
  </section>
</template>

<style scoped>
.source-footnotes { display: grid; gap: 5px; margin-top: 11px; padding-top: 8px; border-top: 1px solid color-mix(in srgb, var(--ink-soft, #5d6b65) 17%, transparent); }
.source-label { color: #77847d; font-size: 9px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.source-bubble-row { display: flex; flex-wrap: wrap; gap: 5px; }
.source-item { position: relative; }
.source-bubble { display: inline-flex; align-items: center; gap: 4px; min-height: 25px; max-width: 220px; padding: 0 8px; border: 1px solid #d9e6e0; border-radius: 999px; color: #35695a; background: #f5faf7; font-size: 9px; transition: border-color .18s ease, background .18s ease, transform .18s ease; }
.source-bubble:hover { transform: translateY(-1px); border-color: #77b4a0; background: #e9f5ef; }
.source-bubble.web { color: #46627d; border-color: #dae3ec; background: #f6f9fc; }
.source-bubble.web:hover { border-color: #93b3cf; background: #edf5fc; }
.source-bubble span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 750; }
.source-bubble small { color: inherit; opacity: .62; white-space: nowrap; }
.source-detail { position: absolute; z-index: 6; top: calc(100% + 6px); left: 0; width: min(420px, calc(100vw - 72px)); padding: 11px 12px; border: 1px solid #d6e4dd; border-radius: 10px; color: #33423b; background: #ffffff; box-shadow: 0 12px 28px rgba(24, 59, 47, .13); }
.source-detail-head { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 7px; }
.source-detail-head strong { font-size: 11px; }
.source-detail-head span, .source-detail small { color: #77847d; font-size: 9px; }
.source-original { max-height: 220px; overflow: auto; color: #4b5b53; font-size: 11px; line-height: 1.65; white-space: pre-wrap; }
.source-loading { display: inline-flex; align-items: center; gap: 5px; color: #738078; font-size: 10px; }
.source-loading svg { animation: source-spin .8s linear infinite; }
.source-detail a { display: inline-flex; align-items: center; gap: 4px; margin-top: 8px; color: #2d789e; font-size: 10px; font-weight: 750; }
.source-reveal-enter-active, .source-reveal-leave-active { transition: opacity .16s ease, transform .16s ease; }
.source-reveal-enter-from, .source-reveal-leave-to { opacity: 0; transform: translateY(-4px); }
@keyframes source-spin { to { transform: rotate(360deg); } }
@media (max-width: 620px) { .source-detail { position: fixed; left: 16px; right: 16px; bottom: 16px; top: auto; width: auto; max-height: 56vh; overflow: auto; } }
</style>
