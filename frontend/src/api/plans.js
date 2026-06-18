import { request } from './http'

export function previewPlan(payload) {
  return request('/plans/preview', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function confirmPlan(payload) {
  return request('/plans/confirm', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}
