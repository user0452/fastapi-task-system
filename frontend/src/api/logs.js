import { request } from './http'

export function getOperationLogs(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/ai/operation_logs${query ? '?' + query : ''}`)
}
