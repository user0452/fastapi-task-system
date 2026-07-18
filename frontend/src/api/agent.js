import { request } from './http'
import { postLoginRouteFromHash } from '../router/redirect'


export function formatCurrentTimestampMinute(now = new Date()) {
  const pad = value => String(value).padStart(2, '0')
  const offsetMinutes = -now.getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const hours = pad(Math.floor(Math.abs(offsetMinutes) / 60))
  const minutes = pad(Math.abs(offsetMinutes) % 60)
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())} UTC${sign}${hours}:${minutes}`
}

function timestamped(payload) {
  return { ...(payload || {}), current_time: formatCurrentTimestampMinute() }
}

export function getAgentSessions(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/api/v1/agent/sessions${query ? `?${query}` : ''}`)
}

export function getAgentTools() {
  return request('/api/v1/agent/tools')
}

export function getCourseAgentWorkspace(courseId, params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/api/v1/agent/courses/${courseId}/workspace${query ? `?${query}` : ''}`)
}

export function getCourseMaterialChunk(courseId, chunkId) {
  return request(`/api/v1/courses/${courseId}/materials/chunks/${chunkId}`)
}

export function saveCourseAgentMemory(courseId, payload) {
  return request(`/api/v1/agent/courses/${courseId}/memories`, {
    method: 'PUT',
    body: JSON.stringify(payload)
  })
}

export function getCourseAgentMemories(courseId) {
  return request(`/api/v1/agent/courses/${courseId}/memories`)
}

export function updateCourseAgentMemory(courseId, memoryId, payload) {
  return request(`/api/v1/agent/courses/${courseId}/memories/${memoryId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export function toggleCourseAgentMemoryType(courseId, memoryType, enabled) {
  return request(`/api/v1/agent/courses/${courseId}/memory-types/${encodeURIComponent(memoryType)}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled })
  })
}

export function deleteCourseAgentMemory(courseId, memoryId) {
  return request(`/api/v1/agent/courses/${courseId}/memories/${memoryId}`, {
    method: 'DELETE'
  })
}

export function createAgentSession(payload = {}) {
  return request('/api/v1/agent/sessions', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function getAgentSession(sessionId, params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`/api/v1/agent/sessions/${sessionId}${query ? `?${query}` : ''}`)
}

export function archiveAgentSession(sessionId) {
  return request(`/api/v1/agent/sessions/${sessionId}/archive`, { method: 'POST' })
}

export function decideAgentAction(actionId, confirmed) {
  return request(`/api/v1/agent/actions/${actionId}/decision`, {
    method: 'POST',
    body: JSON.stringify({ confirmed })
  })
}

export function sendAgentMessage(payload) {
  return request('/api/v1/agent/chat', {
    method: 'POST',
    body: JSON.stringify(timestamped(payload))
  })
}

function expireAuth() {
  const redirect = postLoginRouteFromHash(window.location.hash)
  window.dispatchEvent(new CustomEvent('auth:expired'))
  window.location.hash = redirect ? `/login?redirect=${encodeURIComponent(redirect)}` : '/login'
}

export async function sendAgentMessageStream(payload, handlers = {}, options = {}) {
  const response = await fetch('/api/v1/agent/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    credentials: 'same-origin',
    signal: options.signal,
    body: JSON.stringify(timestamped(payload))
  })

  if (!response.ok) {
    if (response.status === 401) expireAuth()
    let message = response.statusText || '请求失败'
    try {
      const body = await response.json()
      message = typeof body?.detail === 'string' ? body.detail : body?.message || message
    } catch {
      // Keep the HTTP status message when the body is not JSON.
    }
    throw new Error(message)
  }
  if (!response.body) throw new Error('当前浏览器不支持流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let completed = false

  function dispatch(event) {
    if (event.type === 'status') {
      handlers.onStatus?.(event.message || '', {
        phase: event.phase || 'thinking',
        tool: event.tool || null
      })
    }
    if (event.type === 'reply_delta') handlers.onDelta?.(event.delta || '')
    if (event.type === 'result') handlers.onResult?.(event.data)
    if (event.type === 'done') handlers.onDone?.()
    if (event.type === 'error') throw new Error(event.message || 'AI 助教处理失败')
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const rawLine of lines) {
        if (rawLine.trim()) dispatch(JSON.parse(rawLine))
      }
    }
    if (buffer.trim()) dispatch(JSON.parse(buffer))
    completed = true
  } finally {
    if (!completed) {
      try {
        await reader.cancel()
      } catch {
        // The browser may already have released the stream after an abort.
      }
    }
    reader.releaseLock()
  }
}
