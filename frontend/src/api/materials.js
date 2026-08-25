import { request } from './http'

export function getCourseMaterials(courseId) {
  return request(`/api/v1/courses/${courseId}/materials`)
}

export function searchCourseMaterials(courseId, query, topK = 5) {
  return request(`/api/v1/courses/${courseId}/materials/search`, {
    method: 'POST',
    body: JSON.stringify({ query, top_k: topK })
  })
}

export function createCourseTextMaterial(courseId, payload) {
  return request(`/api/v1/courses/${courseId}/materials/text`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function uploadCourseMaterial(courseId, { title, file }) {
  const formData = new FormData()
  formData.append('title', title)
  formData.append('file', file)
  return request(`/api/v1/courses/${courseId}/materials/upload`, {
    method: 'POST',
    body: formData
  })
}

export function retryCourseMaterial(materialId) {
  return request(`/api/v1/materials/${materialId}/retry`, { method: 'POST' })
}

export function deleteCourseMaterial(materialId) {
  return request(`/api/v1/materials/${materialId}`, { method: 'DELETE' })
}
