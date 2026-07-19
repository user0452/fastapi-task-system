<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { CheckCircle2, Eye, EyeOff, KeyRound, LoaderCircle, PlugZap, Save } from 'lucide-vue-next'
import { getLlmConfig, saveLlmConfig, testLlmConfig } from '../../../api/llmConfig'
import { showToast } from '../../../components/common/toast'

const form = reactive({
  enabled: false,
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini',
  api_key: ''
})
const saved = ref(null)
const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const showKey = ref(false)
const connection = ref(null)

const canSubmit = computed(() => Boolean(form.base_url.trim() && form.model.trim()))
const statusLabel = computed(() => {
  if (loading.value) return '读取中'
  if (saved.value?.enabled) return '个人 API 已启用'
  if (saved.value?.configured) return '已保存 · 未启用'
  return '使用服务端默认'
})

function applyConfig(config) {
  saved.value = config
  form.enabled = Boolean(config?.enabled)
  if (config?.base_url) form.base_url = config.base_url
  if (config?.model) form.model = config.model
  form.api_key = ''
  connection.value = null
}

function requestPayload(includeEnabled = false) {
  const payload = {
    base_url: form.base_url.trim(),
    model: form.model.trim()
  }
  if (includeEnabled) payload.enabled = form.enabled
  if (form.api_key.trim()) payload.api_key = form.api_key.trim()
  return payload
}

async function loadConfig() {
  loading.value = true
  const response = await getLlmConfig()
  loading.value = false
  if (response.code === 200) {
    applyConfig(response.data)
  } else {
    showToast({ type: 'error', message: response.message || '模型配置读取失败' })
  }
}

async function saveConfig() {
  if (!canSubmit.value || saving.value) return
  saving.value = true
  connection.value = null
  const response = await saveLlmConfig(requestPayload(true))
  saving.value = false
  if (response.code === 200) {
    applyConfig(response.data)
    showToast({ type: 'success', message: '模型 API 配置已保存' })
  } else {
    showToast({ type: 'error', message: response.message || '模型配置保存失败' })
  }
}

async function testConnection() {
  if (!canSubmit.value || testing.value) return
  testing.value = true
  connection.value = null
  const response = await testLlmConfig(requestPayload())
  testing.value = false
  if (response.code === 200) {
    connection.value = {
      ok: true,
      message: `连接成功 · ${response.data.latency_ms} ms`
    }
    showToast({ type: 'success', message: 'OpenAI 兼容 API 连接成功' })
  } else {
    connection.value = { ok: false, message: response.message || '连接失败' }
  }
}

onMounted(loadConfig)
</script>

<template>
  <section class="api-section">
    <div class="section-heading">
      <KeyRound :size="19" />
      <div>
        <h2>模型 API</h2>
        <p>配置任意兼容 OpenAI <code>/chat/completions</code> 的服务。</p>
      </div>
      <span class="api-status" :class="{ active: saved?.enabled }">{{ statusLabel }}</span>
    </div>

    <div v-if="loading" class="loading-row">
      <LoaderCircle :size="17" class="spin" /> 正在读取模型配置
    </div>

    <form v-else class="api-form" @submit.prevent="saveConfig">
      <label class="toggle-row">
        <div>
          <strong>使用个人 API</strong>
          <span>启用后，聊天、练习、评估和资料提取优先使用此配置。</span>
        </div>
        <input v-model="form.enabled" type="checkbox" />
        <i></i>
      </label>

      <div class="field-grid">
        <label class="field base-url-field">
          <span>API Base URL</span>
          <input
            v-model="form.base_url"
            type="url"
            autocomplete="url"
            placeholder="https://api.openai.com/v1"
            required
          />
          <small>保留版本路径，例如 <code>/v1</code>；不要填写 <code>/chat/completions</code>。</small>
        </label>

        <label class="field">
          <span>模型名称</span>
          <input v-model="form.model" type="text" autocomplete="off" placeholder="gpt-4o-mini" required />
          <small>填写服务商实际开放的模型 ID。</small>
        </label>

        <label class="field key-field">
          <span>API Key</span>
          <div class="secret-input">
            <input
              v-model="form.api_key"
              :type="showKey ? 'text' : 'password'"
              autocomplete="new-password"
              spellcheck="false"
              :placeholder="saved?.has_api_key ? `已保存 ${saved.api_key_hint}，留空则不修改` : 'sk-…'"
            />
            <button type="button" :aria-label="showKey ? '隐藏 API Key' : '显示 API Key'" @click="showKey = !showKey">
              <EyeOff v-if="showKey" :size="16" />
              <Eye v-else :size="16" />
            </button>
          </div>
          <small>密钥经服务端加密保存，之后仅显示末四位。</small>
        </label>
      </div>

      <div class="api-actions">
        <p v-if="connection" class="connection-result" :class="{ success: connection.ok }" role="status">
          <CheckCircle2 v-if="connection.ok" :size="15" />
          {{ connection.message }}
        </p>
        <p v-else class="fallback-note">
          {{ saved?.server_default_available ? `关闭时使用服务端默认模型 ${saved.server_default_model}` : '关闭时需要服务端已配置默认模型' }}
        </p>
        <button class="secondary-button" type="button" :disabled="!canSubmit || testing" @click="testConnection">
          <LoaderCircle v-if="testing" :size="15" class="spin" />
          <PlugZap v-else :size="15" />
          {{ testing ? '正在测试' : '测试连接' }}
        </button>
        <button class="primary-button" type="submit" :disabled="!canSubmit || saving">
          <LoaderCircle v-if="saving" :size="15" class="spin" />
          <Save v-else :size="15" />
          {{ saving ? '正在保存' : '保存配置' }}
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.api-section {
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-large);
  background: var(--surface-card);
  box-shadow: var(--shadow-small), var(--shadow-hairline);
}
.section-heading {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 20px 22px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--accent);
}
.section-heading > div { min-width: 0; flex: 1; }
.section-heading h2 { color: var(--text-primary); font-size: 17px; font-weight: var(--weight-semibold); }
.section-heading p { margin-top: 4px; color: var(--text-secondary); font-size: 13px; line-height: 1.55; }
.section-heading code,
.field code { font-family: inherit; color: var(--text-primary); }
.api-status {
  flex: none;
  padding: 5px 9px;
  border-radius: var(--radius-round);
  color: var(--text-secondary);
  background: var(--surface-tertiary);
  font-size: 11px;
  font-weight: 600;
}
.api-status.active { color: var(--success); background: var(--success-soft); }
.loading-row { display: flex; align-items: center; gap: 9px; padding: 26px 22px; color: var(--text-secondary); font-size: 13px; }
.api-form { display: grid; }
.toggle-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 22px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
}
.toggle-row > div { flex: 1; display: grid; gap: 4px; }
.toggle-row strong { font-size: 14px; }
.toggle-row span { color: var(--text-secondary); font-size: 12px; }
.toggle-row input { position: absolute; opacity: 0; }
.toggle-row i {
  position: relative;
  width: 44px;
  height: 26px;
  border-radius: var(--radius-round);
  background: #c7c8cd;
  transition: background var(--duration-fast) var(--ease-standard);
}
.toggle-row i::after {
  content: '';
  position: absolute;
  left: 3px;
  top: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--surface-primary);
  transition: transform var(--duration-fast) var(--ease-standard);
}
.toggle-row input:checked + i { background: var(--accent); }
.toggle-row input:checked + i::after { transform: translateX(18px); }
.field-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(220px, .6fr);
  gap: 17px 18px;
  padding: 20px 22px 22px;
}
.field { min-width: 0; display: grid; gap: 7px; }
.field > span { color: var(--text-secondary); font-size: 13px; font-weight: 600; }
.field input {
  width: 100%;
  height: var(--control-lg);
  padding: 0 13px;
  border: 1px solid var(--border-strong);
  border-radius: 13px;
  color: var(--text-primary);
  background: var(--surface-secondary);
  font-size: 14px;
  transition: border-color var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard);
}
.field input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); outline: 0; }
.field small { color: var(--text-tertiary); font-size: 11px; line-height: 1.45; }
.key-field { grid-column: 1 / -1; }
.secret-input { position: relative; }
.secret-input input { padding-right: 44px; }
.secret-input button {
  position: absolute;
  right: 7px;
  top: 7px;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: var(--text-secondary);
}
.secret-input button:hover { color: var(--accent); background: var(--surface-tertiary); }
.api-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 22px;
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-secondary);
}
.fallback-note,
.connection-result { min-width: 0; flex: 1; color: var(--text-tertiary); font-size: 12px; }
.connection-result { color: var(--danger); }
.connection-result.success { display: flex; align-items: center; gap: 6px; color: var(--success); }
.primary-button,
.secondary-button {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 14px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
}
.primary-button { color: var(--text-inverse); background: var(--gradient-brand); box-shadow: var(--shadow-brand); }
.secondary-button { color: var(--accent); border: 1px solid var(--border-accent); background: var(--surface-primary); }
.primary-button:disabled,
.secondary-button:disabled { opacity: .5; cursor: not-allowed; }
.spin { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 680px) {
  .section-heading { flex-wrap: wrap; }
  .api-status { margin-left: 31px; }
  .field-grid { grid-template-columns: 1fr; }
  .key-field { grid-column: auto; }
  .api-actions { align-items: stretch; flex-wrap: wrap; }
  .fallback-note,
  .connection-result { flex-basis: 100%; }
  .primary-button,
  .secondary-button { flex: 1; }
}
</style>
