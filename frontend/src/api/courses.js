import { request } from './http'


export function getCourses(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/api/v1/courses${query ? `?${query}` : ''}`)
}

export function getCurrentCourse() {
  return request('/api/v1/courses/current')
}

export function createCourse(payload) {
  return request('/api/v1/courses', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function updateCourse(courseId, payload) {
  return request(`/api/v1/courses/${courseId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export function selectCourse(courseId) {
  return request(`/api/v1/courses/${courseId}/select`, { method: 'POST' })
}

export function archiveCourse(courseId) {
  return request(`/api/v1/courses/${courseId}`, { method: 'DELETE' })
}
