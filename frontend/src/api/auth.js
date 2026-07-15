import { request } from './http'

export function login(username, password) {
  return request('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  })
}

export function register(username, password) {
  return request('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  })
}

export function getCurrentUser() {
  return request('/api/v1/auth/me')
}

export function logout() {
  return request('/api/v1/auth/logout', { method: 'POST' })
}
