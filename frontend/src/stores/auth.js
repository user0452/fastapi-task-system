import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, register as apiRegister } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')

  const isLoggedIn = computed(() => !!token.value)

  async function login(user, password) {
    const res = await apiLogin(user, password)
    if (res.code === 200 && res.data) {
      token.value = res.data.token || res.data.access_token || ''
      username.value = user
      localStorage.setItem('token', token.value)
      localStorage.setItem('username', user)
      return { success: true }
    }
    return { success: false, message: res.message || '登录失败' }
  }

  async function register(user, password) {
    const res = await apiRegister(user, password)
    if (res.code === 200 || res.code === 201) {
      return { success: true }
    }
    return { success: false, message: res.message || '注册失败' }
  }

  function logout() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('username')
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('auth:expired', logout)
  }

  function restore() {
    token.value = localStorage.getItem('token') || ''
    username.value = localStorage.getItem('username') || ''
  }

  return {
    token,
    username,
    isLoggedIn,
    login,
    register,
    logout,
    restore
  }
})
