import { request } from './http'

export function getQuizzes(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/quizzes${query ? '?' + query : ''}`)
}

export function generateQuiz(payload) {
  return request('/quizzes/generate', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function getQuiz(quizSetId) {
  return request(`/quizzes/${quizSetId}`)
}

export function getEvaluations(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/evaluations${query ? '?' + query : ''}`)
}

export function submitEvaluation(payload) {
  return request('/evaluations/submit', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function getEvaluation(evaluationId) {
  return request(`/evaluations/${evaluationId}`)
}
