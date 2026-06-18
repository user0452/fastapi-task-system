import { request } from './http'

export function login(username, password) {
  return request('/users/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  })
}

export function register(username, password) {
  return request('/users/register', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  })
}
