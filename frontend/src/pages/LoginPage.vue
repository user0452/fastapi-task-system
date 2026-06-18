<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { showToast } from '../components/common/toast'

const router = useRouter()
const auth = useAuthStore()

const activeTab = ref('login')
const loading = ref(false)

const loginForm = ref({ username: '', password: '' })
const regForm = ref({ username: '', password: '', confirm: '' })

async function handleLogin() {
  if (!loginForm.value.username || !loginForm.value.password) {
    showToast({ type: 'warning', message: '请填写用户名和密码' })
    return
  }

  loading.value = true
  const result = await auth.login(loginForm.value.username, loginForm.value.password)
  loading.value = false

  if (result.success) {
    showToast({ type: 'success', message: '登录成功' })
    router.push('/overview')
  } else {
    showToast({ type: 'error', message: result.message })
  }
}

async function handleRegister() {
  if (!regForm.value.username || !regForm.value.password) {
    showToast({ type: 'warning', message: '请填写用户名和密码' })
    return
  }
  if (regForm.value.password !== regForm.value.confirm) {
    showToast({ type: 'warning', message: '两次密码不一致' })
    return
  }
  if (regForm.value.password.length < 6) {
    showToast({ type: 'warning', message: '密码至少 6 位' })
    return
  }

  loading.value = true
  const result = await auth.register(regForm.value.username, regForm.value.password)
  loading.value = false

  if (result.success) {
    showToast({ type: 'success', message: '注册成功，请登录' })
    activeTab.value = 'login'
    loginForm.value.username = regForm.value.username
    loginForm.value.password = ''
  } else {
    showToast({ type: 'error', message: result.message })
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-hero">
      <h1>任务与学习工作台</h1>
      <p>统一管理任务、学习资源、题集和个性化学习计划</p>
      <ul class="login-features">
        <li>任务状态与优先级管理</li>
        <li>学生画像驱动的资源与题集生成</li>
        <li>学习计划预览后再导入任务</li>
        <li>AI 学习助手智能对话</li>
      </ul>
    </div>

    <div class="login-form-container">
      <div class="login-card">
        <h2>欢迎使用</h2>
        <p class="subtitle">使用账号进入学习工作台</p>

        <div class="login-tabs">
          <button
            class="login-tab"
            :class="{ active: activeTab === 'login' }"
            @click="activeTab = 'login'"
          >
            登录
          </button>
          <button
            class="login-tab"
            :class="{ active: activeTab === 'register' }"
            @click="activeTab = 'register'"
          >
            注册
          </button>
        </div>

        <form v-if="activeTab === 'login'" @submit.prevent="handleLogin">
          <div class="form-group">
            <label class="form-label">用户名</label>
            <input
              v-model="loginForm.username"
              type="text"
              class="form-input"
              placeholder="请输入用户名"
              autocomplete="username"
              minlength="3"
              maxlength="30"
              required
            />
          </div>
          <div class="form-group">
            <label class="form-label">密码</label>
            <input
              v-model="loginForm.password"
              type="password"
              class="form-input"
              placeholder="请输入密码"
              autocomplete="current-password"
              minlength="6"
              maxlength="30"
              required
            />
          </div>
          <button type="submit" class="btn btn-primary btn-lg btn-block" :disabled="loading">
            {{ loading ? '登录中...' : '登录' }}
          </button>
        </form>

        <form v-else @submit.prevent="handleRegister">
          <div class="form-group">
            <label class="form-label">用户名</label>
            <input
              v-model="regForm.username"
              type="text"
              class="form-input"
              placeholder="3-30 个字符"
              autocomplete="username"
              minlength="3"
              maxlength="30"
              required
            />
          </div>
          <div class="form-group">
            <label class="form-label">密码</label>
            <input
              v-model="regForm.password"
              type="password"
              class="form-input"
              placeholder="至少 6 位"
              autocomplete="new-password"
              minlength="6"
              maxlength="30"
              required
            />
          </div>
          <div class="form-group">
            <label class="form-label">确认密码</label>
            <input
              v-model="regForm.confirm"
              type="password"
              class="form-input"
              placeholder="再次输入密码"
              autocomplete="new-password"
              minlength="6"
              maxlength="30"
              required
            />
          </div>
          <button type="submit" class="btn btn-primary btn-lg btn-block" :disabled="loading">
            {{ loading ? '注册中...' : '注册' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
