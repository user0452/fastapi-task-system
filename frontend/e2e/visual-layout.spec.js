import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'


const viewports = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 }
]
const frontendDir = path.dirname(fileURLToPath(new URL('../package.json', import.meta.url)))
const outputDir = path.resolve(frontendDir, '..', 'artifacts', 'screenshots', 'after')

test('学习产品核心页面保持可读、无横向溢出并输出验收截图', async ({ page }) => {
  await page.goto('/#/login')
  await page.getByPlaceholder('请输入用户名').fill('a3_e2e_1')
  await page.getByPlaceholder('请输入密码').fill('A3Demo123!')
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/#\/home$/)

  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await expect(page.locator('.adaptive-home')).toBeVisible()
    await expect(page.locator('.next-action-card')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width)
    await page.screenshot({ path: path.join(outputDir, `${viewport.width}x${viewport.height}-adaptive-home.png`), fullPage: true })
  }

  await page.setViewportSize(viewports[0])
  await page.locator('.course-link').filter({ hasText: '计算机网络 Mini Course' }).click()
  await expect(page.locator('.adaptive-tutor')).toBeVisible()

  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await expect(page.locator('.adaptive-tutor')).toBeVisible()
    await expect(page.locator('.learn-layout')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width)
    await page.screenshot({ path: path.join(outputDir, `${viewport.width}x${viewport.height}-adaptive-course.png`), fullPage: true })
  }
})
