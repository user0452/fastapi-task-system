import { request } from './http'


export function getAdaptiveOverview(courseId) {
  return request(`/api/v1/adaptive/courses/${courseId}/overview`)
}

export function getAdaptiveNextAction(courseId) {
  return request(`/api/v1/adaptive/courses/${courseId}/next-action`)
}

export function getAdaptiveProgress(courseId) {
  return request(`/api/v1/adaptive/courses/${courseId}/progress`)
}

export function getAdaptiveSources(courseId) {
  return request(`/api/v1/adaptive/courses/${courseId}/sources`)
}

export function getAdaptiveObjective(courseId, objectiveId) {
  return request(`/api/v1/adaptive/courses/${courseId}/objectives/${objectiveId}`)
}

export function rebuildAdaptiveCurriculum(courseId, materialId = null) {
  return request(`/api/v1/adaptive/courses/${courseId}/curriculum/rebuild`, {
    method: 'POST',
    body: JSON.stringify({ material_id: materialId })
  })
}

export function addAdaptiveQuestions(courseId, questions) {
  return request(`/api/v1/adaptive/courses/${courseId}/questions`, {
    method: 'POST',
    body: JSON.stringify({ questions })
  })
}

export function startAdaptiveAction(actionId) {
  return request(`/api/v1/adaptive/actions/${actionId}/start`, { method: 'POST' })
}

export function submitAdaptiveAction(actionId, payload) {
  return request(`/api/v1/adaptive/actions/${actionId}/submit`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function startAdaptiveDiagnostic(courseId, questionCount = 6) {
  return request(`/api/v1/adaptive/courses/${courseId}/diagnostic`, {
    method: 'POST',
    body: JSON.stringify({ question_count: questionCount })
  })
}

export function submitAdaptiveDiagnostic(courseId, answers) {
  return request(`/api/v1/adaptive/courses/${courseId}/diagnostic/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers })
  })
}
