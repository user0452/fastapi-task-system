import { beforeEach, describe, expect, it, vi } from 'vitest'
import { request } from './http'
import { saveLlmConfig, testLlmConfig } from './llmConfig'

vi.mock('./http', () => ({ request: vi.fn() }))

describe('llmConfig API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('serializes saved OpenAI-compatible settings as JSON', () => {
    const payload = {
      enabled: true,
      base_url: 'https://gateway.example/v1',
      model: 'gateway-chat',
      api_key: 'sk-test'
    }
    saveLlmConfig(payload)
    expect(request).toHaveBeenCalledWith('/api/v1/account/llm-config', {
      method: 'PUT',
      body: JSON.stringify(payload)
    })
  })

  it('serializes connection-test candidates as JSON', () => {
    const payload = {
      base_url: 'https://gateway.example/v1',
      model: 'gateway-chat'
    }
    testLlmConfig(payload)
    expect(request).toHaveBeenCalledWith('/api/v1/account/llm-config/test', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  })
})
