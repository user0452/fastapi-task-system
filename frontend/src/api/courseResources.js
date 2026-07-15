import { request } from './http'


export function searchCourseResources(courseId, payload) {
  return request(`/api/v1/courses/${courseId}/external-resources/search`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function getCourseResources(courseId) {
  return request(`/api/v1/courses/${courseId}/external-resources`)
}

export function recordResourceInteraction(courseId, resourceId, interactionType, value = {}) {
  return request(`/api/v1/courses/${courseId}/external-resources/${resourceId}/interactions`, {
    method: 'POST',
    body: JSON.stringify({ interaction_type: interactionType, value })
  })
}

export function checkCourseResource(courseId, resourceId) {
  return request(`/api/v1/courses/${courseId}/external-resources/${resourceId}/check`, {
    method: 'POST'
  })
}
