import { request } from './http'

export function getProfile() {
  return request('/profiles/me')
}

export function generateProfile(payload) {
  return request('/profiles/generate', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}
