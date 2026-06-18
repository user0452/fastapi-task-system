import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/users': 'http://127.0.0.1:8000',
      '/tasks': 'http://127.0.0.1:8000',
      '/materials': 'http://127.0.0.1:8000',
      '/profiles': 'http://127.0.0.1:8000',
      '/resources': 'http://127.0.0.1:8000',
      '/external-resources': 'http://127.0.0.1:8000',
      '/quizzes': 'http://127.0.0.1:8000',
      '/evaluations': 'http://127.0.0.1:8000',
      '/plans': 'http://127.0.0.1:8000',
      '/agent': 'http://127.0.0.1:8000',
      '/ai': 'http://127.0.0.1:8000'
    }
  },
  build: {
    outDir: '../static/vue',
    emptyOutDir: true
  }
})
