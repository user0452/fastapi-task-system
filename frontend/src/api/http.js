export async function request(path, options = {}) {
  const token = localStorage.getItem('token')
  const headers = { ...(options.headers || {}) }
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData

  if (options.body && !isFormData && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  try {
    const response = await fetch(path, { ...options, headers })
    const text = await response.text()
    let payload = null

    if (text) {
      try {
        payload = JSON.parse(text)
      } catch {
        payload = { message: text }
      }
    }

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('username')
        window.dispatchEvent(new CustomEvent('auth:expired'))
        window.location.hash = '/login'
      }
      return {
        code: response.status,
        message: payload?.detail || payload?.message || '请求失败',
        data: payload
      }
    }

    return payload || { code: response.status, message: 'success', data: null }
  } catch (err) {
    return {
      code: 0,
      message: err.message || '网络错误',
      data: null
    }
  }
}
