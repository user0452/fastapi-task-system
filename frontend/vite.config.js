import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiTarget = process.env.VITE_API_TARGET || 'http://127.0.0.1:8010'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': apiTarget,
      '/users': apiTarget,
      '/tasks': apiTarget,
      '/materials': apiTarget,
      '/profiles': apiTarget,
      '/resources': apiTarget,
      '/external-resources': apiTarget,
      '/quizzes': apiTarget,
      '/evaluations': apiTarget,
      '/plans': apiTarget,
      '/agent': apiTarget,
      '/ai': apiTarget
    }
  },
  build: {
    outDir: '../static/vue',
    emptyOutDir: true
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.js'],
    css: true
  }
})
