import { request } from './http'

export function getMaterials(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/materials${query ? '?' + query : ''}`)
}

export function createMaterial(payload) {
  return request('/materials', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function uploadMaterial({ courseName, title, file }) {
  const formData = new FormData()
  formData.append('course_name', courseName)
  formData.append('title', title)
  formData.append('file', file)

  return request('/materials/upload', {
    method: 'POST',
    body: formData
  })
}

export function buildMaterialIndex(materialId) {
  return request(`/materials/${materialId}/build-index`, {
    method: 'POST'
  })
}

export function ragSearch(payload) {
  return request('/materials/rag-search', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}
