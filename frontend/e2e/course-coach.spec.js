import { expect, test } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'


test.describe.configure({ mode: 'serial' })

const password = 'A3Demo123!'
const questionBankPath = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'adaptive-question-bank.json')


async function loginSeedCourse(page) {
  await page.goto('/#/login')
  await page.getByPlaceholder('请输入用户名').fill('a3_e2e_0')
  await page.getByPlaceholder('请输入密码').fill(password)
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/#\/today$/)
  await expect(page.locator('.home-next-action')).toBeVisible()
}


async function register(page, testInfo) {
  const username = `adaptive_e2e_${Date.now().toString(36)}_${testInfo.repeatEachIndex}`
  await page.goto('/#/login')
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await page.getByPlaceholder('3-30 个字符').fill(username)
  await page.getByPlaceholder('至少 6 位').fill(password)
  await page.getByPlaceholder('再次输入密码').fill(password)
  await page.locator('form').getByRole('button', { name: '注册', exact: true }).click()
  await page.getByPlaceholder('请输入密码').fill(password)
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/#\/today$/)
}


async function createCourse(page, name) {
  await page.getByRole('button', { name: '新建课程', exact: true }).click()
  await page.getByPlaceholder('例如：软件测试').fill(name)
  await page.getByPlaceholder('例如：掌握核心测试设计方法并完成考试冲刺').fill('建立可评估的课程目标并完成自适应练习')
  await page.getByRole('button', { name: '创建课程助手', exact: true }).click()
  await expect(page).toHaveURL(/#\/learn\/\d+\?view=sources/)
  await expect(page.locator('.adaptive-tutor')).toBeVisible()
  await expect(page.locator('.adaptive-nav')).toContainText('Sources')
}


async function waitForMaterialReady(page, courseId, title) {
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/courses/${courseId}/materials`)
    if (!response.ok()) return `http-${response.status()}`
    const payload = await response.json()
    return payload.data?.items?.find(item => item.title === title)?.processing_status || 'missing'
  }, { timeout: 120_000, intervals: [500, 1_000, 2_000] }).toBe('ready')
}


test('资料、文件题库、诊断、Practice、Tutor Check 与 Student Model 闭环', async ({ page }, testInfo) => {
  test.setTimeout(240_000)
  await register(page, testInfo)
  await createCourse(page, `Adaptive 网络课 ${testInfo.repeatEachIndex + 1}`)

  await page.getByRole('button', { name: '手动输入', exact: true }).click()
  await page.getByPlaceholder('例如：第三章边界值分析').fill('自适应测试课程讲义')
  await page.getByPlaceholder('粘贴讲义、笔记或复习提纲').fill(
    '# 等价类划分\n把输入域划分为有效类和无效类，为每一类选择代表值。\n\n'
    + '# 边界值分析\n检查最小值、最大值、边界附近值和刚好越界的值。\n\n'
    + '# 判定表\n枚举条件和动作的有效组合，把有效规则转换成测试用例。'
  )
  await page.getByRole('button', { name: '提交并自动处理', exact: true }).click()
  const courseId = Number(page.url().match(/#\/learn\/(\d+)/)?.[1])
  await waitForMaterialReady(page, courseId, '自适应测试课程讲义')
  await page.getByRole('button', { name: '刷新资料状态' }).click()
  await expect(page.locator('.material-row').filter({ hasText: '自适应测试课程讲义' }).locator('.status')).toHaveText('可使用', { timeout: 20_000 })

  const questionFile = page.locator('.question-import-form input[type=file]')
  await questionFile.setInputFiles(questionBankPath)
  await page.getByRole('button', { name: '预览题库', exact: true }).click()
  await expect(page.locator('.import-preview')).toContainText('3 条解析')
  await expect(page.locator('.import-preview')).toContainText('3 条已匹配')
  await page.getByRole('button', { name: '确认导入这批题', exact: true }).click()
  await expect(page.locator('.question-list article')).toHaveCount(3)

  await page.getByRole('tab', { name: /Learn/ }).click()
  await expect(page.locator('.action-surface')).toBeVisible()

  await page.getByRole('button', { name: '开始快速诊断', exact: true }).click()
  const diagnostic = page.locator('.diagnostic-surface')
  await expect(diagnostic).toBeVisible()
  const diagnosticAnswers = diagnostic.locator('textarea')
  await expect(diagnosticAnswers).toHaveCount(3)
  for (let index = 0; index < await diagnosticAnswers.count(); index += 1) {
    await diagnosticAnswers.nth(index).fill('不知道')
  }
  await diagnostic.getByRole('button', { name: '提交诊断', exact: true }).click()
  await expect(diagnostic).toContainText('诊断已完成')
  await expect(page.locator('.evidence-result').last()).toContainText('刚刚写入 Evidence')

  await page.getByRole('button', { name: '开始', exact: true }).click()
  const actionForm = page.locator('.action-answer')
  await expect(actionForm).toBeVisible()
  await actionForm.locator('textarea').fill('有效范围是 1 到 10；边界附近和越界值用于验证边界行为。')
  await page.getByRole('button', { name: '提交并更新状态', exact: true }).click()
  await expect(page.locator('.evidence-result').filter({ hasText: '掌握度' })).toContainText('掌握度')

  // Tutor is a grounded interaction layer. This request must return citations,
  // while the explicit Check below is the only Tutor path that writes Evidence.
  await page.getByRole('button', { name: '换一个例子' }).click()
  await expect(page.locator('.tutor-response')).toContainText('教学响应')
  await expect(page.locator('.tutor-response')).toContainText('课程引用')
  await page.getByRole('button', { name: '开始 Tutor Check' }).first().click()
  const checkForm = page.locator('.tutor-check-form').last()
  await expect(checkForm).toBeVisible()
  await checkForm.locator('textarea').fill('我会先判断输入是否在有效范围，再检查边界本身、附近值和越界值。')
  await checkForm.getByRole('button', { name: '提交 Tutor Check', exact: true }).click()
  await expect(page.locator('.evidence-result').filter({ hasText: '掌握度' })).toContainText('刚刚写入 Evidence')

  await page.getByRole('tab', { name: /Progress/ }).click()
  await expect(page.locator('.progress-view')).toBeVisible()
  await expect(page.locator('.objective-row')).toHaveCount(3)
  await expect(page.locator('.objective-detail')).toContainText('最近 Evidence')
  await expect(page.locator('.objective-detail')).toContainText('置信度')

  await page.getByRole('tab', { name: /Sources/ }).click()
  await expect(page.locator('.sources-view')).toBeVisible()
  await expect(page.locator('.source-count-line')).toContainText('3 道题')
})


test('旧入口只重定向到核心区域，移动端保持可用', async ({ page }) => {
  await loginSeedCourse(page)
  await page.goto('/#/progress')
  await expect(page).toHaveURL(/#\/today$/)
  await expect(page.locator('.adaptive-home')).toBeVisible()

  await page.goto('/#/resources')
  await expect(page).toHaveURL(/#\/today$/)
  await expect(page.locator('.adaptive-home')).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/today')
  await expect(page.locator('.adaptive-home')).toBeVisible()
  await expect(page.locator('.home-next-action')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.getByRole('button', { name: '打开课程栏' }).click()
  await page.locator('.mobile-rail .course-link').filter({ hasText: '计算机网络 Mini Course' }).click()
  await expect(page.locator('.adaptive-tutor')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})
