import { defineConfig } from '@playwright/test'


export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.js',
  globalTeardown: './e2e/global-teardown.js',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [['line']],
  use: {
    baseURL: 'http://127.0.0.1:5176',
    channel: 'chrome',
    viewport: { width: 1280, height: 800 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  webServer: [
    {
      command: '.\\.venv\\Scripts\\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8011',
      cwd: '..',
      url: 'http://127.0.0.1:8011/health/ready',
      env: {
        APP_ENV: 'test',
        A3_MOCK_LLM: 'true',
        A3_MOCK_EMBEDDING: 'true',
        AUTH_RATE_LIMIT_ENABLED: 'false',
        TAVILY_API_KEY: ''
      },
      reuseExistingServer: false,
      timeout: 60_000
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5176',
      cwd: '.',
      url: 'http://127.0.0.1:5176',
      env: { VITE_API_TARGET: 'http://127.0.0.1:8011' },
      reuseExistingServer: false,
      timeout: 60_000
    }
  ]
})
