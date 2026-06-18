import { createApp, h } from 'vue'
import Toast from './Toast.vue'

export function showToast({ type = 'info', title = '', message = '', duration = 3000 }) {
  const container = document.getElementById('toast-container')
  if (!container) return

  const wrapper = document.createElement('div')
  container.appendChild(wrapper)

  const app = createApp({
    render() {
      return h(Toast, { type, title, message, duration })
    }
  })

  app.mount(wrapper)

  setTimeout(() => {
    app.unmount()
    wrapper.remove()
  }, duration + 500)
}
