import { request } from './http'

export function getTasks(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/tasks${query ? '?' + query : ''}`)
}

export function createTask(payload) {
  return request('/tasks', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function updateTask(taskId, payload) {
  return request(`/tasks/${taskId}`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}

export function deleteTask(taskId) {
  return request(`/tasks/${taskId}`, {
    method: 'DELETE'
  })
}
