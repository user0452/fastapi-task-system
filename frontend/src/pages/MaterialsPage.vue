<script setup>
import { ref, onMounted } from 'vue'
import {
  getMaterials,
  createMaterial,
  uploadMaterial,
  buildMaterialIndex,
  ragSearch
} from '../api/materials'
import { showToast } from '../components/common/toast'
import EmptyState from '../components/common/EmptyState.vue'
import LoadingState from '../components/common/LoadingState.vue'
import { BookOpen } from 'lucide-vue-next'

const materials = ref([])
const total = ref(0)
const loading = ref(false)

const formMode = ref('text')
const form = ref({ course_name: '', title: '', content: '' })
const file = ref(null)
const saving = ref(false)

const ragTopic = ref('')
const ragCourse = ref('')
const ragLoading = ref(false)
const ragHits = ref([])

const buildingId = ref(null)

onMounted(() => {
  loadMaterials()
})

async function loadMaterials() {
  loading.value = true
  const res = await getMaterials({ page: 1, size: 50 })
  loading.value = false
  if (res.code === 200) {
    materials.value = res.data?.list || res.data?.items || res.data || []
    total.value = res.data?.total || materials.value.length
  }
}

function onFileChange(e) {
  file.value = e.target.files[0]
  if (file.value && !form.value.title) {
    form.value.title = file.value.name.replace(/\.[^.]+$/, '')
  }
}

async function handleSave() {
  if (!form.value.course_name || !form.value.title) {
    showToast({ type: 'warning', message: '请填写课程名和标题' })
    return
  }

  saving.value = true
  let res

  if (formMode.value === 'file' && file.value) {
    res = await uploadMaterial({
      courseName: form.value.course_name,
      title: form.value.title,
      file: file.value
    })
  } else {
    if (!form.value.content) {
      showToast({ type: 'warning', message: '请输入正文内容' })
      saving.value = false
      return
    }
    res = await createMaterial(form.value)
  }

  saving.value = false

  if (res.code === 200 || res.code === 201) {
    showToast({ type: 'success', message: '保存成功' })
    form.value = { course_name: '', title: '', content: '' }
    file.value = null
    loadMaterials()
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

async function handleBuildIndex(m) {
  buildingId.value = m.material_id || m.id
  const res = await buildMaterialIndex(buildingId.value)
  buildingId.value = null

  if (res.code === 200) {
    const chunks = res.data?.chunk_count || res.data?.chunks || '?'
    showToast({ type: 'success', message: `索引构建完成，共 ${chunks} 个分块` })
  } else {
    showToast({ type: 'error', message: res.message })
  }
}

function selectMaterial(m) {
  ragCourse.value = m.course_name || ''
}

async function handleRagSearch() {
  if (!ragCourse.value) {
    showToast({ type: 'warning', message: '请填写课程名称' })
    return
  }
  if (!ragTopic.value) {
    showToast({ type: 'warning', message: '请填写检索主题' })
    return
  }

  ragLoading.value = true
  const res = await ragSearch({
    course_name: ragCourse.value,
    topic: ragTopic.value
  })
  ragLoading.value = false

  if (res.code === 200) {
    ragHits.value = res.data?.list || res.data?.hits || res.data || []
    if (ragHits.value.length === 0) {
      showToast({ type: 'info', message: '未找到相关内容' })
    }
  } else {
    showToast({ type: 'error', message: res.message })
  }
}
</script>

<template>
  <div class="materials-page">
    <div class="page-header">
      <h1>课程知识库</h1>
      <span class="badge badge-primary">共 {{ total }} 份资料</span>
    </div>

    <div class="materials-form">
      <div class="card">
        <div class="card-header">
          <h3>录入资料</h3>
          <div>
            <button
              class="btn btn-sm"
              :class="formMode === 'text' ? 'btn-primary' : 'btn-secondary'"
              @click="formMode = 'text'"
            >正文</button>
            <button
              class="btn btn-sm"
              :class="formMode === 'file' ? 'btn-primary' : 'btn-secondary'"
              @click="formMode = 'file'"
            >上传文件</button>
          </div>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label class="form-label">课程名称</label>
            <input v-model="form.course_name" class="form-input" placeholder="如：高等数学" />
          </div>
          <div class="form-group">
            <label class="form-label">标题</label>
            <input v-model="form.title" class="form-input" placeholder="如：第一章 函数与极限" />
          </div>
          <div v-if="formMode === 'text'" class="form-group">
            <label class="form-label">正文内容</label>
            <textarea
              v-model="form.content"
              class="form-textarea"
              rows="8"
              placeholder="粘贴课程内容..."
            ></textarea>
          </div>
          <div v-else class="form-group">
            <label class="form-label">选择文件</label>
            <input type="file" class="form-input" @change="onFileChange" accept=".txt,.md,.pdf,.docx" />
            <p v-if="file" class="form-hint">
              已选择：{{ file.name }}
            </p>
          </div>
        </div>
        <div class="card-footer">
          <button class="btn btn-primary" :disabled="saving" @click="handleSave">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <div class="materials-list">
      <div class="card">
        <div class="card-header">
          <h3>资料列表</h3>
          <button class="btn btn-ghost btn-sm" @click="loadMaterials">刷新</button>
        </div>
        <div class="card-body">
          <LoadingState v-if="loading" />
          <EmptyState v-else-if="materials.length === 0" :icon="BookOpen" title="暂无资料" desc="在左侧录入或上传课程资料" />
          <div v-else class="table-container">
            <table class="data-table">
              <thead>
                <tr>
                  <th>课程</th>
                  <th>标题</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="m in materials"
                  :key="m.material_id || m.id"
                  @click="selectMaterial(m)"
                >
                  <td>{{ m.course_name }}</td>
                  <td>{{ m.title }}</td>
                  <td>
                    <button
                      class="btn btn-sm btn-secondary"
                      :disabled="buildingId === (m.material_id || m.id)"
                      @click.stop="handleBuildIndex(m)"
                    >
                      {{ buildingId === (m.material_id || m.id) ? '构建中...' : '构建索引' }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <div class="rag-section">
      <div class="card">
        <div class="card-header">
          <h3>RAG 检索验证</h3>
        </div>
        <div class="card-body">
          <div class="rag-form-row">
            <div class="form-group">
              <label class="form-label">课程名称 *</label>
              <input v-model="ragCourse" class="form-input" placeholder="输入课程名称" />
            </div>
            <div class="form-group">
              <label class="form-label">检索主题 *</label>
              <input
                v-model="ragTopic"
                class="form-input"
                placeholder="输入检索主题..."
                @keyup.enter="handleRagSearch"
              />
            </div>
            <div class="form-group">
              <button class="btn btn-primary" :disabled="ragLoading" @click="handleRagSearch">
                {{ ragLoading ? '检索中...' : '检索' }}
              </button>
            </div>
          </div>

          <div v-if="ragHits.length" class="rag-results">
            <div v-for="(hit, i) in ragHits" :key="i" class="rag-hit">
              <div class="rag-hit-header">
                <span class="rag-hit-score">相似度: {{ hit.score?.toFixed(4) || '—' }}</span>
                <span class="rag-hit-meta">
                  分块 #{{ hit.chunk_index ?? '—' }} |
                  资料ID: {{ hit.material_id || '—' }}
                </span>
              </div>
              <div class="rag-hit-content">{{ hit.chunk_text || hit.snippet || hit.content || '' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
