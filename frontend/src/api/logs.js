import { request } from './http'

export function getOperationLogs(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/api/v1/audit/logs${query ? '?' + query : ''}`)
}
