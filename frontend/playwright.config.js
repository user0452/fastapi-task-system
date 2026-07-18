import { defineConfig, devices } from '@playwright/test'

const e2eDatabase = process.env.A3_E2E_DATABASE_NAME || 'a3_e2e_test'
const backendPort = Number(process.env.A3_E2E_BACKEND_PORT || 8021)
const frontendPort = Number(process.env.A3_E2E_FRONTEND_PORT || 5186)
const backendURL = `http://127.0.0.1:${backendPort}`
const frontendURL = `http://127.0.0.1:${frontendPort}`
const configuredPython = process.env.A3_PYTHON
const backendCommand = configuredPython
  ? `"${configuredPython}" scripts/run_e2e_backend.py`
  : 'uv run python scripts/run_e2e_backend.py'
const manageWebServers = process.env.PLAYWRIGHT_EXTERNAL_SERVERS !== 'true'


export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.js',
  globalTeardown: './e2e/global-teardown.js',
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [
    ['line'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }]
  ],
  use: {
    baseURL: frontendURL,
    viewport: { width: 1280, height: 800 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],
  webServer: manageWebServers
    ? [
        {
          command: backendCommand,
          cwd: '..',
          url: `${backendURL}/health/ready`,
          env: {
            APP_ENV: 'test',
            ENABLE_LEGACY_ROUTES: 'true',
            A3_MOCK_LLM: 'true',
            A3_MOCK_EMBEDDING: 'true',
            AUTH_RATE_LIMIT_ENABLED: 'false',
            TAVILY_API_KEY: '',
            DATABASE_NAME: e2eDatabase,
            A3_E2E_DATABASE_NAME: e2eDatabase,
            A3_E2E_BACKEND_PORT: String(backendPort)
          },
          reuseExistingServer: false,
          timeout: 60_000
        },
        {
          command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
          cwd: '.',
          url: frontendURL,
          env: { VITE_API_TARGET: backendURL },
          reuseExistingServer: false,
          timeout: 60_000
        }
      ]
    : undefined
})
