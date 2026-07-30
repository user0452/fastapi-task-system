import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'


const password = 'A3Demo123!'
const viewports = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1180, height: 800 },
  { width: 1024, height: 768 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 }
]
const frontendDir = path.dirname(fileURLToPath(new URL('../package.json', import.meta.url)))
const outputDir = path.resolve(frontendDir, '..', 'artifacts', 'screenshots', 'after')

async function expectFullyContained(child, parent, viewportWidth) {
  const [childBox, parentBox] = await Promise.all([child.boundingBox(), parent.boundingBox()])
  expect(childBox).not.toBeNull()
  expect(parentBox).not.toBeNull()
  expect(childBox.x).toBeGreaterThanOrEqual(parentBox.x - 1)
  expect(childBox.x + childBox.width).toBeLessThanOrEqual(parentBox.x + parentBox.width + 1)
  expect(childBox.x).toBeGreaterThanOrEqual(-1)
  expect(childBox.x + childBox.width).toBeLessThanOrEqual(viewportWidth + 1)
}

test('关键视口保持可读、无横向溢出并输出验收截图', async ({ page }, testInfo) => {
  await page.goto('/#/login')
  await page.getByPlaceholder('请输入用户名').fill(`a3_e2e_${testInfo.repeatEachIndex}`)
  await page.getByPlaceholder('请输入密码').fill(password)
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/#\/today$/)
  await page.locator('.toast-close').click()

  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await expect(page.locator('.today-hero')).toBeVisible()
    await expect(page.locator('.budget-result')).toBeVisible()
    await expectFullyContained(
      page.locator('.budget-result'),
      page.locator('.budget-control'),
      viewport.width
    )
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width)
    await page.screenshot({
      path: path.join(outputDir, `${viewport.width}x${viewport.height}-today.png`),
      fullPage: true
    })
  }

  await page.setViewportSize(viewports[0])
  await page.locator('.course-link').filter({ hasText: '软件测试冲刺' }).click()
  await expect(page.locator('.workspace-chat')).toBeVisible()

  for (const viewport of viewports) {
    await page.setViewportSize(viewport)
    await expect(page.locator('.workspace-chat')).toBeVisible()
    await expect(page.locator('.chat-composer textarea')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width)
    await page.screenshot({
      path: path.join(outputDir, `${viewport.width}x${viewport.height}-workspace.png`),
      fullPage: true
    })
  }
})
