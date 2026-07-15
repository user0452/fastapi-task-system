import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'


export default async function globalTeardown() {
  const frontendDir = path.dirname(fileURLToPath(new URL('../package.json', import.meta.url)))
  const rootDir = path.resolve(frontendDir, '..')
  const python = path.join(rootDir, '.venv', 'Scripts', 'python.exe')
  const result = spawnSync(
    python,
    [
      'scripts/seed_demo.py',
      '--username-prefix',
      'a3_e2e',
      '--count',
      '0',
      '--purge-prefix'
    ],
    { cwd: rootDir, encoding: 'utf8' }
  )
  if (result.status !== 0) {
    throw new Error(`E2E 数据清理失败：${result.stderr || result.stdout}`)
  }
}
