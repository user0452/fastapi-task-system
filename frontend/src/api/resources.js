import { request } from './http'

export function getResources(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/resources${query ? '?' + query : ''}`)
}

export function generateResource(payload) {
  return request('/resources/generate', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function getResource(resourceId) {
  return request(`/resources/${resourceId}`)
}
