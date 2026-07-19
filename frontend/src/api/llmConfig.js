import { request } from './http'

export function getLlmConfig() {
  return request('/api/v1/account/llm-config')
}

export function saveLlmConfig(payload) {
  return request('/api/v1/account/llm-config', { method: 'PUT', body: JSON.stringify(payload) })
}

export function testLlmConfig(payload) {
  return request('/api/v1/account/llm-config/test', { method: 'POST', body: JSON.stringify(payload) })
}

export function deleteLlmConfig() {
  return request('/api/v1/account/llm-config', { method: 'DELETE' })
}
