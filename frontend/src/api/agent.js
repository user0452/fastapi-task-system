import { request } from './http'

export function sendAgentMessage(payload) {
  return request('/agent/chat', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

function handleUnauthorized() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  window.dispatchEvent(new CustomEvent('auth:expired'))
  window.location.hash = '/login'
}

export async function sendAgentMessageStream(payload, handlers = {}) {
  const token = localStorage.getItem('token')
  const response = await fetch('/agent/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify(payload)
  })

  if (!response.ok) {
    if (response.status === 401) {
      handleUnauthorized()
    }

    let message = '请求失败'
    try {
      const payload = await response.json()
      message = payload?.detail || payload?.message || message
    } catch {
      message = response.statusText || message
    }
    throw new Error(message)
  }

  if (!response.body) {
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  function handleEvent(event) {
    if (event.type === 'status') {
      handlers.onStatus?.(event.message || '')
    } else if (event.type === 'reply_delta') {
      handlers.onDelta?.(event.delta || '')
    } else if (event.type === 'result') {
      handlers.onResult?.(event.data)
    } else if (event.type === 'error') {
      throw new Error(event.message || 'AI助手处理失败')
    } else if (event.type === 'done') {
      handlers.onDone?.()
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const rawLine of lines) {
      const line = rawLine.trim()
      if (!line) continue

      const event = JSON.parse(line)
      handleEvent(event)
    }
  }

  const tail = buffer.trim()
  if (tail) {
    const event = JSON.parse(tail)
    handleEvent(event)
  }
}
