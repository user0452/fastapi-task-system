<script setup>
import { computed, ref } from 'vue'
import { Bookmark, BookmarkCheck, Check, ExternalLink, Play, ThumbsUp, Video } from 'lucide-vue-next'
import { recordResourceInteraction } from '../../../api/courseResources'
import { showToast } from '../../../components/common/toast'


const props = defineProps({
  resource: { type: Object, required: true },
  courseId: { type: Number, required: true },
  compact: { type: Boolean, default: false }
})
const emit = defineEmits(['updated', 'practice'])
const imageFailed = ref(false)
const busy = ref(false)

const state = computed(() => props.resource.interaction || {})

async function interact(type) {
  if (busy.value) return
  busy.value = true
  const response = await recordResourceInteraction(props.courseId, props.resource.id, type)
  busy.value = false
  if (response.code === 200) emit('updated', response.data)
  else showToast({ type: 'error', message: response.message })
}

function openResource() {
  window.open(props.resource.canonical_url, '_blank', 'noopener,noreferrer')
  interact('opened')
}
</script>

<template>
  <article class="resource-video" :class="{ compact }">
    <button class="video-cover" type="button" :title="`打开 ${resource.title}`" @click="openResource">
      <img v-if="resource.thumbnail_url && !imageFailed" :src="resource.thumbnail_url" :alt="resource.title" @error="imageFailed = true" />
      <span v-else class="cover-placeholder"><Video :size="26" /><small>{{ resource.provider }}</small></span>
      <span class="play-mark"><Play :size="15" fill="currentColor" /></span>
      <span v-if="resource.duration_label" class="duration">{{ resource.duration_label }}</span>
    </button>
    <div class="video-copy">
      <span class="video-source">{{ resource.provider }}<template v-if="resource.author"> · {{ resource.author }}</template></span>
      <strong>{{ resource.title }}</strong>
      <p>{{ resource.reason || resource.summary }}</p>
    </div>
    <footer class="video-actions">
      <button type="button" title="打开视频" aria-label="打开视频" @click="openResource"><ExternalLink :size="15" /></button>
      <button
        type="button"
        :title="state.saved ? '取消收藏' : '收藏视频'"
        :aria-label="state.saved ? '取消收藏' : '收藏视频'"
        :class="{ active: state.saved }"
        @click="interact(state.saved ? 'unsaved' : 'saved')"
      >
        <BookmarkCheck v-if="state.saved" :size="15" /><Bookmark v-else :size="15" />
      </button>
      <button
        type="button"
        :title="state.completed ? '标记为未看完' : '标记已看完'"
        :aria-label="state.completed ? '标记为未看完' : '标记已看完'"
        :class="{ active: state.completed }"
        @click="interact(state.completed ? 'uncompleted' : 'completed')"
      ><Check :size="15" /></button>
      <button
        type="button"
        title="这个资源有帮助"
        aria-label="这个资源有帮助"
        :class="{ active: state.helpful === true }"
        @click="interact('helpful')"
      ><ThumbsUp :size="15" /></button>
      <button class="practice-action" type="button" @click="$emit('practice', resource)">看完做题</button>
    </footer>
  </article>
</template>

<style scoped>
.resource-video { min-width: 0; overflow: hidden; border: 1px solid #d8dedb; border-radius: 7px; background: #fff; }
.video-cover { width: 100%; aspect-ratio: 16 / 9; display: block; overflow: hidden; background: #e8ece9; }
.video-cover img { width: 100%; height: 100%; object-fit: cover; transition: transform 220ms ease; }
.video-cover:hover img { transform: scale(1.025); }
.cover-placeholder { width: 100%; height: 100%; display: grid; place-items: center; align-content: center; gap: 4px; color: #66736c; background: #e5ebe7; }
.cover-placeholder small { font-size: 10px; text-transform: uppercase; }
.play-mark { position: absolute; left: 10px; bottom: 9px; width: 29px; height: 29px; display: grid; place-items: center; border-radius: 50%; color: #fff; background: rgba(20, 28, 24, .78); }
.duration { position: absolute; right: 7px; bottom: 7px; padding: 2px 5px; border-radius: 3px; color: #fff; background: rgba(15, 20, 18, .78); font-size: 10px; font-variant-numeric: tabular-nums; }
.video-copy { min-width: 0; display: grid; gap: 3px; padding: 9px 10px 7px; }
.video-source { color: #27715d; font-size: 10px; font-weight: 740; text-transform: capitalize; }
.video-copy strong { display: -webkit-box; overflow: hidden; color: #303b36; font-size: 12px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.video-copy p { display: -webkit-box; overflow: hidden; color: #74807a; font-size: 10px; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.video-actions { height: 38px; display: flex; align-items: center; gap: 2px; padding: 4px 7px; border-top: 1px solid #e4e8e5; }
.video-actions button:not(.practice-action) { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 5px; color: #707b75; }
.video-actions button:hover,
.video-actions button.active { color: #176b58; background: #e6efea; }
.video-actions .practice-action { min-height: 28px; margin-left: auto; padding: 0 7px; border-radius: 5px; color: #185f4e; border: 1px solid #b8cac1; font-size: 10px; font-weight: 760; }
.compact { display: grid; grid-template-columns: 105px minmax(0, 1fr); }
.compact .video-cover { grid-row: 1 / span 2; aspect-ratio: auto; height: 100%; min-height: 104px; }
.compact .video-actions { grid-column: 2; }
.compact .video-copy p { -webkit-line-clamp: 1; }
</style>
