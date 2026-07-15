import { request } from './http'

export function getProfile() {
  return request('/api/v1/account/profile')
}
