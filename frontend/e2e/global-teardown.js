import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { e2eEnvironment, runPython } from './python-command.js'


export default async function globalTeardown() {
  const frontendDir = path.dirname(fileURLToPath(new URL('../package.json', import.meta.url)))
  const rootDir = path.resolve(frontendDir, '..')
  const result = runPython(
    [
      'scripts/seed_demo.py',
      '--username-prefix',
      'a3_e2e',
      '--count',
      '0',
      '--purge-prefix',
      '--require-test-database'
    ],
    { cwd: rootDir, encoding: 'utf8', env: e2eEnvironment() }
  )
  if (result.status !== 0) {
    throw new Error(`E2E 数据清理失败：${result.stderr || result.stdout}`)
  }
}
