import { request } from './http'

export function getProfile() {
  return request('/api/v1/account/profile')
}

export function getMemorySettings() {
  return request('/api/v1/account/memory-settings')
}

export function updateMemorySettings(payload) {
  return request('/api/v1/account/memory-settings', {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}
