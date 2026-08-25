import { spawnSync } from 'node:child_process'


export function runPython(args, options = {}) {
  const configuredPython = process.env.A3_PYTHON
  const command = configuredPython || process.env.UV_COMMAND || 'uv'
  const commandArgs = configuredPython ? args : ['run', 'python', ...args]
  return spawnSync(command, commandArgs, options)
}


export function e2eEnvironment() {
  return {
    ...process.env,
    APP_ENV: 'test',
    A3_MOCK_LLM: 'true',
    A3_MOCK_EMBEDDING: 'true',
    AUTH_RATE_LIMIT_ENABLED: 'false',
    TAVILY_API_KEY: '',
    DATABASE_NAME: process.env.A3_E2E_DATABASE_NAME || 'a3_e2e_test'
  }
}
