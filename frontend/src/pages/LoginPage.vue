<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { showToast } from '../components/common/toast'
import { safePostLoginRoute } from '../router/redirect'

const router = useRouter()
const route = useRoute()
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
    router.push(safePostLoginRoute(route.query.redirect) || '/today')
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
      <h1>A3 专科学习 AI</h1>
      <p>每门课程都有自己的对话、知识库、练习与掌握记录。</p>
      <div class="login-flow" aria-label="课程学习流程">
        <span>课程 AI</span>
        <span>资料知识库</span>
        <span>聊天内练习</span>
        <span>掌握与计划</span>
      </div>
    </div>

    <div class="login-form-container">
      <div class="login-card">
        <h2>{{ activeTab === 'login' ? '继续学习' : '建立学习账号' }}</h2>
        <p class="subtitle">{{ activeTab === 'login' ? '登录后回到课程 AI 工作区' : '注册后创建第一门课程 AI' }}</p>

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

<style scoped>
.login-page {
  --login-ink: var(--text-primary);
  --login-muted: var(--text-secondary);
  --login-teal: var(--accent);
  --login-teal-deep: var(--accent-hover);
  --login-blue: var(--accent);
  --login-surface: rgba(255, 255, 255, 0.88);

  position: relative;
  isolation: isolate;
  overflow: hidden;
  min-height: 100svh;
  background: var(--gradient-soft-page);
}

.login-page::before,
.login-page::after {
  position: absolute;
  z-index: -1;
  display: block;
  content: '';
  pointer-events: none;
  border-radius: 50%;
}

.login-page::before {
  width: min(48vw, 45rem);
  aspect-ratio: 1;
  top: -26rem;
  left: -22rem;
  background: rgba(79, 124, 255, 0.13);
}

.login-page::after {
  width: min(38vw, 34rem);
  aspect-ratio: 1;
  right: -18rem;
  bottom: -20rem;
  background: rgba(75, 190, 196, 0.1);
}

.login-hero,
.login-form-container {
  position: relative;
  z-index: 1;
}

.login-hero {
  padding: clamp(3rem, 7vw, 6.5rem);
  color: var(--login-ink);
  background: transparent;
  animation: login-hero-reveal 620ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.login-hero h1 {
  max-width: 620px;
  margin-bottom: 1.15rem;
  color: var(--login-ink);
  font-size: clamp(3rem, 5.1vw, 4.9rem);
  font-weight: 670;
  line-height: 1.04;
  letter-spacing: -0.065em;
}

.login-hero p {
  max-width: 500px;
  margin-bottom: 2.15rem;
  color: var(--login-muted);
  font-size: clamp(1rem, 1.4vw, 1.15rem);
  line-height: 1.75;
}

.login-flow {
  width: fit-content;
  max-width: 100%;
  gap: 0.5rem 1.45rem;
  padding: 0.75rem 1rem;
  border: 1px solid rgba(52, 120, 246, 0.12);
  border-left: 3px solid var(--accent);
  border-radius: 0 1rem 1rem 0;
  background: rgba(52, 120, 246, 0.07);
  box-shadow: var(--shadow-small);
}

.login-flow span {
  color: var(--login-teal-deep);
  font-size: 0.8125rem;
  font-weight: 700;
  letter-spacing: 0.015em;
}

.login-flow span:not(:last-child)::after {
  right: -0.95rem;
  width: 0.25rem;
  height: 0.25rem;
  border-radius: 999px;
  background: #7ea5f2;
}

.login-form-container {
  padding: clamp(2rem, 5.5vw, 5rem);
  border-left: 1px solid rgba(23, 34, 54, 0.07);
  background: rgba(245, 245, 247, .7);
}

.login-card {
  width: min(100%, 430px);
  padding: clamp(1.75rem, 3.4vw, 2.75rem);
  border: 1px solid rgba(23, 34, 54, 0.1);
  border-radius: 1.75rem;
  background: var(--login-surface);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.86) inset,
    0 24px 65px rgba(36, 44, 67, 0.13),
    0 4px 14px rgba(36, 44, 67, 0.05);
  animation: login-card-reveal 680ms 80ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.login-card h2 {
  margin-bottom: 0.4rem;
  color: var(--login-ink);
  font-size: clamp(1.65rem, 2.3vw, 2rem);
  font-weight: 640;
  letter-spacing: -0.04em;
}

.login-card .subtitle {
  margin-bottom: 1.75rem;
  color: var(--login-muted);
  font-size: 0.9375rem;
  line-height: 1.6;
}

.login-tabs {
  gap: 0.3rem;
  margin-bottom: 1.75rem;
  padding: 0.3rem;
  border: 1px solid rgba(23, 34, 54, 0.08);
  border-radius: 1rem;
  background: var(--surface-tertiary);
}

.login-tab {
  min-height: 2.75rem;
  border: 0;
  border-radius: 0.75rem;
  background: transparent;
  color: var(--text-secondary);
  font-family: inherit;
  font-weight: 700;
  letter-spacing: 0.01em;
  cursor: pointer;
  transition:
    color 180ms ease,
    background-color 180ms ease,
    box-shadow 180ms ease,
    transform 180ms ease;
}

.login-tab:hover {
  color: var(--login-teal-deep);
}

.login-tab.active {
  color: var(--login-teal-deep);
  background: #fff;
  box-shadow: var(--shadow-small);
}

.login-tab:focus-visible,
.login-card .form-input:focus-visible,
.login-card .btn-primary:focus-visible {
  outline: 3px solid rgba(62, 124, 232, 0.32);
  outline-offset: 2px;
}

.login-card .form-group {
  margin-bottom: 1.2rem;
}

.login-card .form-label {
  margin-bottom: 0.5rem;
  color: #415067;
  font-size: 0.8125rem;
  font-weight: 700;
  letter-spacing: 0.025em;
}

.login-card .form-input {
  min-height: 3.2rem;
  padding: 0.85rem 1rem;
  border: 1px solid rgba(23, 34, 54, 0.14);
  border-radius: 0.875rem;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 1px 2px rgba(23, 34, 54, 0.025) inset;
  color: var(--login-ink);
  font-size: 0.975rem;
  transition:
    border-color 180ms ease,
    box-shadow 180ms ease,
    background-color 180ms ease;
}

.login-card .form-input::placeholder {
  color: #9aa6b5;
}

.login-card .form-input:hover {
  border-color: rgba(52, 120, 246, 0.42);
  border-bottom-color: rgba(52, 120, 246, 0.42);
}

.login-card .form-input:focus {
  border-color: var(--login-teal);
  border-bottom-color: var(--login-teal);
  border-bottom-width: 1px;
  background: #fff;
  box-shadow: var(--shadow-focus);
}

.login-card .btn-primary {
  min-height: 3.35rem;
  margin-top: 0.35rem;
  border: 1px solid transparent;
  border-radius: 14px;
  background: var(--gradient-brand);
  box-shadow:
    0 12px 24px rgba(79, 124, 255, 0.23),
    0 1px 0 rgba(255, 255, 255, 0.2) inset;
  color: #fff;
  font-weight: 620;
  letter-spacing: 0.02em;
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    background 180ms ease;
}

.login-card .btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  background: var(--gradient-brand);
  box-shadow:
    0 16px 30px rgba(79, 124, 255, 0.26),
    0 0 0 4px rgba(62, 124, 232, 0.08),
    0 1px 0 rgba(255, 255, 255, 0.2) inset;
}

.login-card .btn-primary:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 8px 16px rgba(79, 124, 255, 0.2);
}

.login-card .btn-primary:disabled {
  opacity: 0.58;
}

@keyframes login-hero-reveal {
  from {
    opacity: 0;
    transform: translateY(18px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes login-card-reveal {
  from {
    opacity: 0;
    transform: translateY(20px) scale(0.985);
  }

  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (max-width: 760px) {
  .login-page {
    grid-template-columns: minmax(0, 1fr);
    background-size: 32px 32px, 32px 32px, auto;
  }

  .login-hero {
    min-height: auto;
    padding: 4.5rem clamp(1.5rem, 7vw, 3rem) 3rem;
  }

  .login-hero h1 {
    max-width: 10ch;
    font-size: clamp(2.7rem, 12vw, 3.65rem);
  }

  .login-hero p {
    margin-bottom: 1.5rem;
  }

  .login-form-container {
    padding: 1rem clamp(1rem, 5vw, 1.5rem) 2.5rem;
    border-top: 1px solid rgba(23, 34, 54, 0.07);
    border-left: 0;
  }

  .login-card {
    max-width: 34rem;
    border-radius: 1.5rem;
  }
}

@media (max-width: 420px) {
  .login-flow {
    gap: 0.55rem 1.15rem;
    padding: 0.7rem 0.8rem;
  }

  .login-flow span {
    font-size: 0.75rem;
  }

  .login-flow span:not(:last-child)::after {
    right: -0.75rem;
  }

  .login-card {
    padding: 1.5rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .login-hero,
  .login-card,
  .login-tab,
  .login-card .form-input,
  .login-card .btn-primary {
    animation: none;
    transition-duration: 0.01ms;
  }
}
</style>
