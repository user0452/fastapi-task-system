<script setup>
import { computed, ref, watch } from 'vue'
import { Brain, Check, Pencil, Plus, Trash2, X } from 'lucide-vue-next'
import {
  deleteCourseAgentMemory,
  getCourseAgentMemories,
  saveCourseAgentMemory,
  toggleCourseAgentMemoryType,
  updateCourseAgentMemory
} from '../../../api/agent'


const props = defineProps({
  courseId: { type: Number, required: true },
  refreshKey: { type: Number, default: 0 }
})
const emit = defineEmits(['data-changed'])

const memoryTypes = [
  { value: 'course_preference', label: '学习偏好' },
  { value: 'mastered_content', label: '已掌握内容' },
  { value: 'weak_point', label: '长期薄弱点' },
  { value: 'error_pattern', label: '常见错误' },
  { value: 'learning_goal', label: '最近学习目标' },
  { value: 'course_context', label: '重要课程上下文' }
]
const sourceLabels = {
  manual: '手动添加',
  manual_edit: '手动修正',
  chat: '课程对话',
  system: '学习系统'
}

const loading = ref(true)
const error = ref('')
const memories = ref([])
const busyId = ref(null)
const editingId = ref(null)
const editText = ref('')
const adding = ref(false)
const newType = ref('course_preference')
const newText = ref('')

const groupedMemories = computed(() => {
  const groups = new Map()
  for (const memory of memories.value) {
    if (!groups.has(memory.memory_type)) groups.set(memory.memory_type, [])
    groups.get(memory.memory_type).push(memory)
  }
  return [...groups.entries()].map(([type, items]) => ({
    type,
    label: typeLabel(type),
    items,
    enabled: items.every(item => item.enabled)
  }))
})

function typeLabel(type) {
  return memoryTypes.find(item => item.value === type)?.label || type
}

function displayContent(content) {
  if (!content || typeof content !== 'object') return String(content || '')
  const preferredKeys = ['text', 'value', 'summary', 'goal', 'preference', 'description']
  const key = preferredKeys.find(item => typeof content[item] === 'string')
  if (key) return content[key]
  return Object.entries(content)
    .map(([name, value]) => `${name}：${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join('\n')
}

function editedContent(memory, text) {
  const current = memory.content || {}
  const stringEntry = Object.entries(current).find(([, value]) => typeof value === 'string')
  if (stringEntry && Object.keys(current).length === 1) return { [stringEntry[0]]: text }
  return { text }
}

function formatDate(value) {
  if (!value) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
  }).format(new Date(value))
}

function sourceLabel(memory) {
  if (memory.source_message_id) return `对话消息 #${memory.source_message_id}`
  return sourceLabels[memory.source_type] || '来源未标注'
}

async function load() {
  loading.value = true
  error.value = ''
  const response = await getCourseAgentMemories(props.courseId)
  if (response.code === 200) memories.value = response.data?.items || []
  else error.value = response.message || '记忆加载失败'
  loading.value = false
}

async function addMemory() {
  const content = newText.value.trim()
  if (!content) return
  busyId.value = 'new'
  error.value = ''
  const response = await saveCourseAgentMemory(props.courseId, {
    memory_key: `manual_${Date.now().toString(36)}`,
    memory_type: newType.value,
    content: { text: content }
  })
  busyId.value = null
  if (response.code !== 200) {
    error.value = response.message || '记忆保存失败'
    return
  }
  newText.value = ''
  adding.value = false
  await load()
  emit('data-changed')
}

function startEdit(memory) {
  editingId.value = memory.id
  editText.value = displayContent(memory.content)
}

async function saveEdit(memory) {
  const content = editText.value.trim()
  if (!content) return
  busyId.value = memory.id
  const response = await updateCourseAgentMemory(props.courseId, memory.id, {
    content: editedContent(memory, content)
  })
  busyId.value = null
  if (response.code !== 200) {
    error.value = response.message || '记忆更新失败'
    return
  }
  editingId.value = null
  await load()
  emit('data-changed')
}

async function toggleMemory(memory) {
  busyId.value = memory.id
  const response = await updateCourseAgentMemory(props.courseId, memory.id, {
    enabled: !memory.enabled
  })
  busyId.value = null
  if (response.code !== 200) {
    error.value = response.message || '记忆状态更新失败'
    return
  }
  await load()
  emit('data-changed')
}

async function toggleGroup(group) {
  busyId.value = `type:${group.type}`
  const response = await toggleCourseAgentMemoryType(props.courseId, group.type, !group.enabled)
  busyId.value = null
  if (response.code !== 200) {
    error.value = response.message || '记忆类型状态更新失败'
    return
  }
  await load()
  emit('data-changed')
}

async function removeMemory(memory) {
  if (!window.confirm(`删除这条“${typeLabel(memory.memory_type)}”记忆？删除后不会再用于回答。`)) return
  busyId.value = memory.id
  const response = await deleteCourseAgentMemory(props.courseId, memory.id)
  busyId.value = null
  if (response.code !== 200) {
    error.value = response.message || '记忆删除失败'
    return
  }
  await load()
  emit('data-changed')
}

watch(() => [props.courseId, props.refreshKey], load, { immediate: true })
</script>

<template>
  <div class="memory-panel">
    <header class="memory-heading">
      <div>
        <span>长期记忆</span>
        <h2>系统记住了什么</h2>
        <p>只有启用的记忆会进入课程对话。你可以随时修正、暂停或删除。</p>
      </div>
      <button type="button" aria-label="添加课程记忆" title="添加课程记忆" @click="adding = !adding">
        <X v-if="adding" :size="15" /><Plus v-else :size="15" />
      </button>
    </header>

    <form v-if="adding" class="memory-form" @submit.prevent="addMemory">
      <label>记忆类型
        <select v-model="newType">
          <option v-for="type in memoryTypes" :key="type.value" :value="type.value">{{ type.label }}</option>
        </select>
      </label>
      <label>希望系统记住的内容
        <textarea v-model="newText" rows="3" maxlength="2000" placeholder="例如：解释概念时先给例子，再给定义"></textarea>
      </label>
      <button class="primary-button" type="submit" :disabled="!newText.trim() || busyId === 'new'">保存记忆</button>
    </form>

    <p v-if="error" class="memory-error" role="alert">{{ error }}</p>
    <div v-if="loading" class="memory-state">正在读取课程记忆</div>
    <div v-else-if="!memories.length" class="memory-state empty">
      <Brain :size="24" />
      <strong>这门课程还没有长期记忆</strong>
      <span>对话仍会使用课程资料与当前学习状态。</span>
    </div>

    <div v-else class="memory-groups">
      <section v-for="group in groupedMemories" :key="group.type" class="memory-group">
        <header>
          <div><strong>{{ group.label }}</strong><span>{{ group.items.length }} 条</span></div>
          <button
            type="button"
            class="group-toggle"
            :class="{ enabled: group.enabled }"
            :disabled="busyId === `type:${group.type}`"
            :aria-label="`${group.label}${group.enabled ? '全部暂停' : '全部启用'}`"
            @click="toggleGroup(group)"
          >{{ group.enabled ? '启用中' : '已暂停' }}</button>
        </header>

        <article v-for="memory in group.items" :key="memory.id" class="memory-row" :class="{ disabled: !memory.enabled }">
          <template v-if="editingId === memory.id">
            <textarea v-model="editText" rows="4" maxlength="2000" aria-label="修正记忆内容"></textarea>
            <div class="edit-actions">
              <button type="button" :disabled="!editText.trim() || busyId === memory.id" @click="saveEdit(memory)"><Check :size="13" /> 保存</button>
              <button type="button" @click="editingId = null"><X :size="13" /> 取消</button>
            </div>
          </template>
          <template v-else>
            <p>{{ displayContent(memory.content) }}</p>
            <div class="memory-meta">
              <span>{{ sourceLabel(memory) }}</span>
              <span>更新于 {{ formatDate(memory.updated_at) }}</span>
            </div>
            <div class="memory-actions">
              <button type="button" @click="startEdit(memory)"><Pencil :size="12" /> 修正</button>
              <button type="button" :disabled="busyId === memory.id" @click="toggleMemory(memory)">{{ memory.enabled ? '暂停使用' : '重新启用' }}</button>
              <button type="button" class="delete-button" :disabled="busyId === memory.id" @click="removeMemory(memory)"><Trash2 :size="12" /> 删除</button>
            </div>
          </template>
        </article>
      </section>
    </div>
  </div>
</template>

<style scoped>
.memory-panel { display: grid; gap: 16px; }
.memory-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-bottom: 14px; border-bottom: 1px solid #dce2de; }
.memory-heading span { color: #17705b; font-size: 9px; font-weight: 800; letter-spacing: .08em; }
.memory-heading h2 { margin-top: 3px; color: #28352f; font-size: 15px; }
.memory-heading p { max-width: 310px; margin-top: 5px; color: #748079; font-size: 10px; line-height: 1.55; }
.memory-heading > button { width: 31px; height: 31px; flex: none; display: grid; place-items: center; border: 1px solid #c9d7d0; border-radius: 5px; color: #176b58; background: #fff; }
.memory-form { display: grid; gap: 9px; padding: 12px 0 15px; border-bottom: 1px solid #dfe4e1; }
.memory-form label { display: grid; gap: 4px; color: #53615a; font-size: 10px; font-weight: 700; }
.memory-form select,
.memory-form textarea,
.memory-row textarea { width: 100%; border: 1px solid #ccd7d1; border-radius: 5px; color: #334039; background: #fff; font-size: 11px; }
.memory-form select { min-height: 34px; padding: 0 8px; }
.memory-form textarea,
.memory-row textarea { resize: vertical; padding: 8px 9px; line-height: 1.55; }
.memory-form :focus-visible,
.memory-row :focus-visible { outline: 2px solid #75aa98; outline-offset: 2px; }
.primary-button { min-height: 33px; justify-self: start; padding: 0 11px; border-radius: 5px; color: #fff; background: #176b58; font-size: 10px; font-weight: 760; }
.primary-button:disabled { opacity: .45; }
.memory-error { padding: 8px 9px; color: #963f39; background: #f9eae8; font-size: 10px; }
.memory-state { min-height: 220px; display: grid; place-items: center; color: #7b8780; font-size: 11px; }
.memory-state.empty { align-content: center; gap: 7px; text-align: center; }
.memory-state.empty svg { color: #4e8070; }
.memory-state.empty strong { color: #3a4741; font-size: 12px; }
.memory-state.empty span { color: #7d8882; font-size: 9px; }
.memory-groups { display: grid; gap: 20px; }
.memory-group > header { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-bottom: 7px; border-bottom: 1px solid #dfe4e1; }
.memory-group > header div { display: flex; align-items: baseline; gap: 6px; }
.memory-group > header strong { color: #344139; font-size: 11px; }
.memory-group > header span { color: #8a948f; font-size: 8px; }
.group-toggle { min-height: 25px; padding: 0 7px; border: 1px solid #d7ddd9; border-radius: 999px; color: #8a6b34; background: #faf5e9; font-size: 8px; font-weight: 750; }
.group-toggle.enabled { color: #28705a; border-color: #c6dbd3; background: #edf6f2; }
.memory-row { display: grid; gap: 7px; padding: 11px 0; border-bottom: 1px solid #e4e8e5; }
.memory-row.disabled { opacity: .62; }
.memory-row > p { color: #34423b; font-size: 11px; line-height: 1.65; white-space: pre-wrap; }
.memory-meta { display: flex; flex-wrap: wrap; gap: 5px 12px; color: #87918c; font-size: 8px; }
.memory-actions,
.edit-actions { display: flex; flex-wrap: wrap; gap: 5px; }
.memory-actions button,
.edit-actions button { min-height: 27px; display: inline-flex; align-items: center; gap: 4px; padding: 0 7px; border: 1px solid #d2dbd6; border-radius: 4px; color: #52625a; background: #fff; font-size: 8px; font-weight: 720; }
.memory-actions button:hover,
.edit-actions button:hover { color: #176b58; border-color: #9dbbad; }
.memory-actions .delete-button { margin-left: auto; color: #9a4b43; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; } }
</style>
