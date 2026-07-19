import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OpenAIConfigSection from './OpenAIConfigSection.vue'
import { getLlmConfig, saveLlmConfig, testLlmConfig } from '../../../api/llmConfig'

vi.mock('../../../api/llmConfig', () => ({
  getLlmConfig: vi.fn(),
  saveLlmConfig: vi.fn(),
  testLlmConfig: vi.fn(),
  deleteLlmConfig: vi.fn()
}))

vi.mock('../../../components/common/toast', () => ({
  showToast: vi.fn()
}))

const storedConfig = {
  provider: 'openai_compatible',
  configured: true,
  enabled: true,
  base_url: 'https://gateway.example/v1',
  model: 'gateway-chat',
  has_api_key: true,
  api_key_hint: '••••1234',
  active_source: 'user',
  server_default_available: true,
  server_default_model: 'server-model'
}

describe('OpenAIConfigSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getLlmConfig.mockResolvedValue({ code: 200, data: storedConfig })
  })

  it('loads masked configuration without rendering the saved secret', async () => {
    const wrapper = mount(OpenAIConfigSection)
    await flushPromises()

    expect(wrapper.text()).toContain('个人 API 已启用')
    expect(wrapper.get('input[type="url"]').element.value).toBe('https://gateway.example/v1')
    expect(wrapper.get('input[type="text"]').element.value).toBe('gateway-chat')
    const secret = wrapper.get('input[type="password"]')
    expect(secret.element.value).toBe('')
    expect(secret.attributes('placeholder')).toContain('••••1234')
    expect(wrapper.html()).not.toContain('sk-user-owned')
  })

  it('saves a new key and tests the current OpenAI-compatible candidate', async () => {
    saveLlmConfig.mockResolvedValue({
      code: 200,
      data: { ...storedConfig, model: 'new-model', api_key_hint: '••••9999' }
    })
    testLlmConfig.mockResolvedValue({
      code: 200,
      data: { ok: true, model: 'new-model', latency_ms: 28 }
    })
    const wrapper = mount(OpenAIConfigSection)
    await flushPromises()

    await wrapper.get('input[type="text"]').setValue('new-model')
    await wrapper.get('input[type="password"]').setValue('sk-new-secret-9999')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(saveLlmConfig).toHaveBeenCalledWith({
      enabled: true,
      base_url: 'https://gateway.example/v1',
      model: 'new-model',
      api_key: 'sk-new-secret-9999'
    })

    await wrapper.findAll('button').find(button => button.text().includes('测试连接')).trigger('click')
    await flushPromises()
    expect(testLlmConfig).toHaveBeenCalledWith({
      base_url: 'https://gateway.example/v1',
      model: 'new-model'
    })
    expect(wrapper.text()).toContain('连接成功 · 28 ms')
  })
})
