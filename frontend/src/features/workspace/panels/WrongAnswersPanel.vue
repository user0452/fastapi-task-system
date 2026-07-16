<script setup>
import { ref, watch } from 'vue'
import { RotateCcw, XCircle } from 'lucide-vue-next'
import { getWrongAnswers } from '../../../api/learning'


const props = defineProps({ courseId: { type: Number, required: true }, refreshKey: { type: Number, default: 0 } })
defineEmits(['prompt'])
const loading = ref(true)
const items = ref([])

async function load() {
  loading.value = true
  const response = await getWrongAnswers(props.courseId)
  items.value = response.code === 200 ? response.data?.items || [] : []
  loading.value = false
}

watch(() => [props.courseId, props.refreshKey], load, { immediate: true })
</script>

<template>
  <div class="wrong-panel">
    <div v-if="loading" class="panel-state">正在读取错题记录</div>
    <div v-else-if="!items.length" class="panel-empty">
      <XCircle :size="27" /><strong>还没有错题</strong><p>完成练习后，低于 60 分的题目会保留在这里。</p>
    </div>
    <section v-else class="wrong-list">
      <article v-for="item in items" :key="item.id">
        <header>
          <span>{{ item.knowledge_point_name || '课程知识点' }}</span>
          <strong>{{ Number(item.score).toFixed(0) }} 分</strong>
        </header>
        <h3>{{ item.question }}</h3>
        <div><span>你的答案</span><p>{{ item.user_answer }}</p></div>
        <div><span>批改反馈</span><p>{{ item.feedback }}</p></div>
        <button type="button" @click="$emit('prompt', `针对“${item.knowledge_point_name || item.question}”再给我出 3 道题`)" title="针对性重做">
          <RotateCcw :size="14" /> 针对性重做
        </button>
      </article>
    </section>
  </div>
</template>

<style scoped>
.panel-state,
.panel-empty { min-height: 260px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #78827d; text-align: center; }
.panel-state { font-size: 12px; }
.panel-empty svg { color: #a45149; }
.panel-empty strong { color: #35413b; font-size: 13px; }
.panel-empty p { max-width: 250px; font-size: 11px; }
.wrong-list { display: grid; }
.wrong-list article { display: grid; gap: 8px; padding: 14px 0; border-bottom: 1px solid #dfe4e1; }
.wrong-list header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.wrong-list header span { color: #19705a; font-size: 10px; font-weight: 740; }
.wrong-list header strong { color: #aa4d45; font-size: 11px; }
.wrong-list h3 { color: #313e37; font-size: 12px; font-weight: 720; line-height: 1.55; }
.wrong-list article > div { display: grid; gap: 3px; padding-left: 8px; border-left: 2px solid #d7ded9; }
.wrong-list article > div > span { color: #818a85; font-size: 9px; }
.wrong-list article > div > p { color: #626e68; font-size: 10px; line-height: 1.55; }
.wrong-list article > small { color: #8b6a2d; font-size: 9px; line-height: 1.5; }
.wrong-list button { min-height: 31px; display: inline-flex; align-items: center; gap: 5px; justify-self: end; padding: 0 9px; border-radius: 5px; color: #176b58; border: 1px solid #b8cac1; font-size: 10px; font-weight: 730; }
</style>
