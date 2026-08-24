<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { FileText, LoaderCircle, RefreshCw, RotateCcw, Trash2, Upload } from 'lucide-vue-next'
import {
  createCourseTextMaterial,
  deleteCourseMaterial,
  getCourseMaterials,
  retryCourseMaterial,
  uploadCourseMaterial
} from '../../../api/materials'
import { showToast } from '../../../components/common/toast'


const props = defineProps({ courseId: { type: Number, required: true } })
const emit = defineEmits(['processed'])
const mode = ref('file')
const materials = ref([])
const loading = ref(false)
const saving = ref(false)
const deletingId = ref(null)
const title = ref('')
const content = ref('')
const selectedFile = ref(null)
let pollTimer = null
let loadSequence = 0
let hasLoadedOnce = false

const hasProcessing = computed(() => materials.value.some(item =>
  !['ready', 'failed'].includes(item.processing_status)
))

const statusLabels = {
  uploaded: '已上传',
  parsing: '解析中',
  indexing: '索引中',
  ready: '可使用',
  failed: '处理失败'
}

function formatCreatedAt(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).format(date)
}

function schedulePoll() {
  clearTimeout(pollTimer)
  if (hasProcessing.value) pollTimer = setTimeout(() => load(false), 1800)
}

async function load(showLoading = true) {
  const sequence = ++loadSequence
  if (showLoading) loading.value = true
  const response = await getCourseMaterials(props.courseId)
  // Uploading starts a background job while the initial list request may
  // still be in flight. Ignore an older snapshot so it cannot overwrite a
  // newer ready/failed status in the UI.
  if (sequence !== loadSequence) {
    if (showLoading) loading.value = false
    return
  }
  loading.value = false
  if (response.code >= 200 && response.code < 300) {
    const previousReady = materials.value.filter(item => item.processing_status === 'ready').length
    materials.value = response.data?.items || []
    const currentReady = materials.value.filter(item => item.processing_status === 'ready').length
    // A ready material already present on first mount is not a new processing
    // event. Emitting for it would make the parent hide/remount this child,
    // which in turn would emit forever on every remount.
    if (hasLoadedOnce && currentReady > previousReady) emit('processed')
    hasLoadedOnce = true
    schedulePoll()
  } else {
    if (showLoading) showToast({ type: 'error', message: response.message })
    schedulePoll()
  }
}

function chooseFile(event) {
  const file = event.target.files?.[0] || null
  selectedFile.value = file
  if (file && !title.value) title.value = file.name.replace(/\.[^.]+$/, '')
}

async function submit() {
  if (saving.value) return
  if (!title.value.trim()) {
    showToast({ type: 'warning', message: '请填写资料标题' })
    return
  }
  if (mode.value === 'file' && !selectedFile.value) {
    showToast({ type: 'warning', message: '请选择文件' })
    return
  }
  if (mode.value === 'text' && !content.value.trim()) {
    showToast({ type: 'warning', message: '请输入资料内容' })
    return
  }
  saving.value = true
  const response = mode.value === 'file'
    ? await uploadCourseMaterial(props.courseId, { title: title.value.trim(), file: selectedFile.value })
    : await createCourseTextMaterial(props.courseId, { title: title.value.trim(), content: content.value.trim() })
  saving.value = false
  if (response.code >= 200 && response.code < 300) {
    showToast({ type: 'success', message: '资料已提交，正在自动处理' })
    title.value = ''
    content.value = ''
    selectedFile.value = null
    await load(false)
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

async function retry(material) {
  const response = await retryCourseMaterial(material.id)
  if (response.code >= 200 && response.code < 300) {
    showToast({ type: 'success', message: '已重新提交处理' })
    await load(false)
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

async function remove(material) {
  if (deletingId.value !== null) return
  const confirmed = window.confirm(
    `确定删除资料“${material.title}”吗？\n\n对应的检索片段和仅由此资料生成的知识点也会删除，此操作无法恢复。`
  )
  if (!confirmed) return
  deletingId.value = material.id
  const response = await deleteCourseMaterial(material.id)
  deletingId.value = null
  if (response.code === 200) {
    materials.value = materials.value.filter(item => item.id !== material.id)
    schedulePoll()
    emit('processed')
    showToast({ type: 'success', message: '资料及其检索索引已删除' })
  } else {
    showToast({ type: 'error', message: response.message })
  }
}

watch(() => props.courseId, (newCourseId, previousCourseId) => {
  if (previousCourseId !== undefined && newCourseId !== previousCourseId) {
    hasLoadedOnce = false
    materials.value = []
  }
  load()
}, { immediate: true })
onBeforeUnmount(() => clearTimeout(pollTimer))
</script>

<template>
  <div class="materials-workspace">
    <section class="material-editor">
      <div class="editor-heading">
        <div>
          <h3>添加课程资料</h3>
          <p>提交后自动解析、分块和建立索引，不需要手动构建。</p>
        </div>
        <div class="mode-switch" role="tablist" aria-label="资料输入方式">
          <button type="button" :class="{ active: mode === 'file' }" @click="mode = 'file'">上传文件</button>
          <button type="button" :class="{ active: mode === 'text' }" @click="mode = 'text'">手动输入</button>
        </div>
      </div>

      <div class="editor-fields">
        <label>
          <span>资料标题</span>
          <input v-model="title" maxlength="255" placeholder="例如：第三章边界值分析" />
        </label>

        <label v-if="mode === 'file'" class="file-picker">
          <input type="file" accept=".txt,.md,.pdf,.docx" @change="chooseFile" />
          <Upload :size="21" />
          <strong>{{ selectedFile?.name || '选择课程文件' }}</strong>
          <span>TXT、Markdown、PDF 或 DOCX，单文件不超过 100MB</span>
        </label>

        <label v-else>
          <span>资料内容</span>
          <textarea v-model="content" rows="9" maxlength="2000000" placeholder="粘贴讲义、笔记或复习提纲"></textarea>
        </label>
      </div>

      <div class="editor-actions">
        <span>{{ mode === 'file' ? '文件会保存在服务端私有目录' : `${content.length} 字符` }}</span>
        <button class="primary-button" type="button" :disabled="saving" @click="submit">
          <Upload :size="16" /> {{ saving ? '正在提交' : '提交并自动处理' }}
        </button>
      </div>
    </section>

    <section class="materials-list">
      <div class="list-heading">
        <div>
          <h3>已添加资料</h3>
          <span>{{ materials.length }} 份</span>
        </div>
        <button class="icon-button" type="button" title="刷新资料状态" aria-label="刷新资料状态" @click="load(false)">
          <RefreshCw :size="17" />
        </button>
      </div>

      <div v-if="loading" class="list-state">正在读取资料状态</div>
      <div v-else-if="!materials.length" class="list-state">还没有资料，先添加一份讲义或笔记。</div>
      <div v-else class="material-rows">
        <article v-for="material in materials" :key="material.id" class="material-row">
          <span class="material-icon"><FileText :size="18" /></span>
          <div class="material-copy">
            <strong>{{ material.title }}</strong>
            <span class="material-meta" :title="material.filename || '手动输入'">{{ material.filename || '手动输入' }}</span>
            <time class="material-created" :datetime="material.created_at">创建于 {{ formatCreatedAt(material.created_at) }}</time>
            <p v-if="material.processing_error">{{ material.processing_error }}</p>
          </div>
          <span class="status" :class="material.processing_status">
            <i v-if="!['ready', 'failed'].includes(material.processing_status)"></i>
            {{ statusLabels[material.processing_status] || material.processing_status }}
          </span>
          <div class="material-actions">
            <button
              v-if="['ready', 'failed'].includes(material.processing_status)"
              class="icon-button"
              type="button"
              :title="material.processing_status === 'ready' ? '使用最新 RAG 配置重建索引' : '重试处理'"
              :aria-label="material.processing_status === 'ready' ? '重建资料索引' : '重试处理'"
              :disabled="deletingId === material.id"
              @click="retry(material)"
            >
              <RotateCcw :size="16" />
            </button>
            <button
              class="icon-button delete-button"
              type="button"
              title="删除资料"
              :aria-label="`删除资料 ${material.title}`"
              :disabled="deletingId !== null"
              @click="remove(material)"
            >
              <LoaderCircle v-if="deletingId === material.id" :size="16" />
              <Trash2 v-else :size="16" />
            </button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.materials-workspace { display: grid; gap: 24px; }
.material-editor { border: 1px solid var(--border-subtle); border-radius: 8px; background: #ffffff; overflow: hidden; }
.editor-heading,
.editor-actions,
.list-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.editor-heading { padding: 16px 18px; border-bottom: 1px solid var(--border-subtle); }
.editor-heading h3,
.list-heading h3 { font-size: 15px; font-weight: 750; }
.editor-heading p { margin-top: 3px; color: #6c7771; font-size: 11px; }
.mode-switch { display: grid; grid-template-columns: 1fr 1fr; padding: 3px; border-radius: 7px; background: var(--surface-tertiary); }
.mode-switch button { min-width: 86px; height: 30px; padding: 0 10px; border-radius: 5px; color: var(--text-secondary); font-size: 11px; font-weight: 700; }
.mode-switch button.active { color: #155d4b; background: #ffffff; box-shadow: 0 1px 2px rgba(31, 46, 39, .1); }
.editor-fields { display: grid; gap: 14px; padding: 18px; }
.editor-fields label { display: grid; gap: 6px; }
.editor-fields label > span { color: #59655f; font-size: 11px; font-weight: 700; }
.editor-fields input:not([type=file]),
.editor-fields textarea {
  width: 100%;
  padding: 10px 11px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: var(--surface-secondary);
  font-size: 13px;
}
.editor-fields textarea { resize: vertical; line-height: 1.55; }
.editor-fields input:focus,
.editor-fields textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(39,128,106,.11); }
.file-picker {
  min-height: 126px;
  place-items: center;
  align-content: center;
  gap: 4px !important;
  border: 1px dashed #aebbb4;
  border-radius: 7px;
  color: #337563;
  background: var(--surface-secondary);
  cursor: pointer;
}
.file-picker input { position: absolute; inline-size: 1px; block-size: 1px; opacity: 0; }
.file-picker strong { margin-top: 4px; color: #31403a; font-size: 13px; }
.file-picker span { color: #7a847f !important; font-size: 10px !important; font-weight: 500 !important; }
.editor-actions { min-height: 58px; padding: 10px 18px; border-top: 1px solid var(--border-subtle); background: var(--surface-secondary); }
.editor-actions > span { color: var(--text-secondary); font-size: 10px; }
.primary-button { min-height: 36px; display: inline-flex; align-items: center; gap: 7px; padding: 0 14px; border-radius: 6px; color: #ffffff; background: var(--accent); font-size: 12px; font-weight: 750; }
.primary-button:disabled { opacity: .5; }
.materials-list { border-top: 1px solid var(--border-subtle); }
.list-heading { min-height: 58px; padding: 8px 2px; }
.list-heading > div { display: flex; align-items: baseline; gap: 8px; }
.list-heading span { color: #7a847f; font-size: 10px; }
.icon-button { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 6px; color: #637069; }
.icon-button:hover { background: var(--accent-soft); color: var(--accent); }
.list-state { padding: 32px 4px; color: #77817c; border-top: 1px solid var(--border-subtle); font-size: 12px; text-align: center; }
.material-rows { border-top: 1px solid var(--border-subtle); }
.material-row { min-height: 76px; display: grid; grid-template-columns: 34px minmax(0, 1fr) auto auto; align-items: center; gap: 11px; padding: 10px 4px; border-bottom: 1px solid var(--border-subtle); transition: opacity 160ms ease, background 160ms ease; }
.material-icon { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 6px; color: #286a59; background: #e1eee8; }
.material-copy { min-width: 0; display: grid; gap: 2px; }
.material-copy strong,
.material-copy span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.material-copy strong { font-size: 12px; }
.material-copy span { color: #78827d; font-size: 10px; }
.material-copy .material-created { overflow: hidden; color: #87908b; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.material-copy p { color: #a13c35; font-size: 10px; }
.status { display: inline-flex; align-items: center; gap: 5px; padding: 4px 7px; border-radius: 5px; color: var(--text-secondary); background: #eef1ef; font-size: 10px; font-weight: 700; }
.status.ready { color: #146347; background: #dff1e7; }
.status.failed { color: #9c382f; background: #fbe6e3; }
.status i { width: 6px; height: 6px; border: 1px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: spin 700ms linear infinite; }
.material-actions { display: flex; align-items: center; gap: 2px; }
.material-actions .delete-button { color: #858e89; }
.material-actions .delete-button:hover { color: #a23f37; background: #f9e9e7; }
.material-actions button:disabled { opacity: .42; cursor: default; }
.material-actions .delete-button svg { transition: transform 160ms ease; }
.material-actions .delete-button:hover:not(:disabled) svg { transform: scale(1.06); }
.material-actions .delete-button svg.lucide-loader-circle { animation: spin 700ms linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 640px) {
  .editor-heading { align-items: flex-start; flex-direction: column; }
  .mode-switch { width: 100%; }
  .mode-switch button { min-width: 0; }
  .editor-actions { align-items: flex-start; flex-direction: column; }
  .editor-actions .primary-button { width: 100%; justify-content: center; }
  .material-row { grid-template-columns: 32px minmax(0, 1fr) auto; }
  .material-actions { grid-column: 3; }
  .status { grid-column: 3; grid-row: 1; }
}
</style>
