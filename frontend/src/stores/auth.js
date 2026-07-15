import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getCurrentUser,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister
} from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const authenticated = ref(false)
  const initialized = ref(false)
  const username = ref('')

  const isLoggedIn = computed(() => authenticated.value)

  async function login(user, password) {
    const res = await apiLogin(user, password)
    if (res.code === 200 && res.data) {
      authenticated.value = true
      initialized.value = true
      username.value = res.data.username || user
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

  async function logout() {
    if (authenticated.value) await apiLogout()
    clearSession()
  }

  function clearSession() {
    authenticated.value = false
    initialized.value = true
    username.value = ''
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('auth:expired', clearSession)
  }

  async function restore() {
    if (initialized.value) return authenticated.value
    const res = await getCurrentUser()
    authenticated.value = res.code === 200 && !!res.data
    username.value = authenticated.value ? res.data.username : ''
    initialized.value = true
    return authenticated.value
  }

  return {
    initialized,
    username,
    isLoggedIn,
    login,
    register,
    logout,
    restore
  }
})
