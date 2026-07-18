import { request } from './http'


export function getLatestDiagnostic(courseId) {
  return request(`/api/v1/courses/${courseId}/diagnostic`)
}

export function generateDiagnostic(courseId, questionCount = 6) {
  return request(`/api/v1/courses/${courseId}/diagnostic`, {
    method: 'POST',
    body: JSON.stringify({ question_count: questionCount })
  })
}

export function submitDiagnostic(quizId, answers) {
  return request(`/api/v1/diagnostics/${quizId}/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers })
  })
}

export function getTodayLearning(courseId) {
  return request(`/api/v1/study/today?course_id=${courseId}`)
}

export function getTodayOverview() {
  return request('/api/v1/study/today-overview')
}

export function getCourseWorkspaceOverview(courseId) {
  return request(`/api/v1/courses/${courseId}/workspace-overview`)
}

export function startLearningSession(sessionId) {
  return request(`/api/v1/study/sessions/${sessionId}/start`, { method: 'POST' })
}

export function submitLearningSession(sessionId, answers, actualMinutes) {
  return request(`/api/v1/study/sessions/${sessionId}/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers, actual_minutes: actualMinutes || null })
  })
}

export function getCourseProgress(courseId) {
  return request(`/api/v1/courses/${courseId}/progress`)
}

export function getStudyPlan(courseId) {
  return request(`/api/v1/courses/${courseId}/study-plan`)
}

export function getLearningRoadmap(courseId) {
  return request(`/api/v1/courses/${courseId}/roadmap`)
}

export function retryLearningRoadmap(courseId, reason = '用户在计划面板手动重试') {
  return request(`/api/v1/courses/${courseId}/roadmap/retry`, {
    method: 'POST',
    body: JSON.stringify({ reason })
  })
}

export function rescheduleLearningSession(sessionId, payload) {
  return request(`/api/v1/study/sessions/${sessionId}/schedule`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export function generatePractice(courseId, payload = {}) {
  return request(`/api/v1/courses/${courseId}/practice`, {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function submitPractice(quizId, answers) {
  return request(`/api/v1/practices/${quizId}/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers })
  })
}

export function getPracticeStats(courseId) {
  return request(`/api/v1/courses/${courseId}/practice-stats`)
}

export function getWrongAnswers(courseId) {
  return request(`/api/v1/courses/${courseId}/wrong-answers`)
}
