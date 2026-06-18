import { request } from './http'

export function searchExternalResources(payload) {
  return request('/external-resources/search', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}
