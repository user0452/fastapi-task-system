import { expect, test } from '@playwright/test'


test.describe.configure({ mode: 'serial' })

const password = 'A3Demo123!'

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
  await expect(page).toHaveURL(/#\/learn\/\d+\?panel=materials/)
  await expect(page.locator('.adaptive-tutor')).toBeVisible()
  await expect(page.locator('.adaptive-nav')).toContainText('Sources')
}

test('课程资料与题库驱动诊断、Evidence 和下一动作闭环', async ({ page }, testInfo) => {
  test.setTimeout(180_000)
  await register(page, testInfo)
  await createCourse(page, `Adaptive 网络课 ${testInfo.repeatEachIndex + 1}`)

  await page.getByRole('button', { name: '手动输入', exact: true }).click()
  await page.getByPlaceholder('例如：第三章边界值分析').fill('自适应网络课程讲义')
  await page.getByPlaceholder('粘贴讲义、笔记或复习提纲').fill(
    '# 等价类划分\n把输入域划分为有效类和无效类，为每一类选择代表值。\n\n'
    + '# 边界值分析\n检查最小值、最大值、边界附近值和刚好越界的值。\n\n'
    + '# 判定表\n枚举条件和动作的有效组合，把有效规则转换成测试用例。'
  )
  await page.getByRole('button', { name: '提交并自动处理', exact: true }).click()
  const courseId = Number(page.url().match(/#\/learn\/(\d+)/)?.[1])
  await expect.poll(async () => {
    const response = await page.request.get(`/api/v1/courses/${courseId}/materials`)
    if (!response.ok()) return `http-${response.status()}`
    const payload = await response.json()
    return payload.data?.items?.find(item => item.title === '自适应网络课程讲义')?.processing_status || 'missing'
  }, { timeout: 120_000, intervals: [500, 1_000, 2_000] }).toBe('ready')
  await page.getByRole('button', { name: '刷新资料状态' }).click()
  await expect(page.locator('.material-row').filter({ hasText: '自适应网络课程讲义' }).locator('.status')).toHaveText('可使用', { timeout: 20_000 })

  const objectiveSelect = page.locator('.question-form select').first()
  await expect(objectiveSelect.locator('option')).toHaveCount(4, { timeout: 20_000 })
  await objectiveSelect.selectOption({ index: 1 })
  await page.locator('.question-form textarea').nth(0).fill('给定范围 1 到 10，请列出边界及刚好越界的测试值。')
  const answer = '应检查 0、1、2、9、10、11，分别覆盖刚好越界、边界本身和边界附近的输入。'
  await page.locator('.question-form textarea').nth(1).fill(answer)
  await page.getByRole('button', { name: '添加到题库', exact: true }).click()
  await expect(page.locator('.question-list article')).toHaveCount(1)

  await page.getByRole('tab', { name: /Learn/ }).click()
  await expect(page.locator('.action-surface')).toBeVisible()

  await page.getByRole('button', { name: '开始快速诊断', exact: true }).click()
  const diagnostic = page.locator('.diagnostic-surface')
  await expect(diagnostic).toBeVisible()
  await expect(diagnostic.locator('textarea')).toHaveCount(1)
  await diagnostic.locator('textarea').fill(answer)
  await diagnostic.getByRole('button', { name: '提交诊断', exact: true }).click()
  await expect(diagnostic).toContainText('诊断已完成')

  await page.getByRole('button', { name: '开始', exact: true }).click()
  await page.locator('.action-answer textarea').fill('我会先识别输入范围，再说明边界本身、附近值和越界值。')
  await page.getByRole('button', { name: '提交并更新状态', exact: true }).click()
  await expect(page.locator('.evidence-result')).toContainText('刚刚写入 Evidence')
  await expect(page.locator('.evidence-result')).toContainText('掌握度')

  await page.getByRole('tab', { name: /Progress/ }).click()
  await expect(page.locator('.progress-view')).toBeVisible()
  await expect(page.locator('.objective-row')).toHaveCount(3)
  await expect(page.locator('.objective-detail')).toContainText('最近 Evidence')
  await expect(page.locator('.objective-detail')).toContainText('置信度')

  await page.getByRole('tab', { name: /Sources/ }).click()
  await expect(page.locator('.sources-view')).toBeVisible()
  await expect(page.locator('.source-count-line')).toContainText('1 道题')
})

test('演示课程首屏展示可解释的错误修复动作并能更新状态', async ({ page }) => {
  await loginSeedCourse(page)
  await page.locator('.home-next-action').getByRole('button', { name: '开始下一动作', exact: true }).click()
  await expect(page).toHaveURL(/#\/learn\/\d+\?view=learn/)
  await expect(page.locator('.action-surface')).toBeVisible()
  await expect(page.locator('.action-reason')).toContainText('错误模式')
  await page.getByRole('button', { name: '开始', exact: true }).click()
  await expect(page.locator('.question-block')).toBeVisible()
  await page.locator('.action-answer textarea').fill('应检查 10、11、12 位，分别覆盖刚好低于下界、边界本身和刚好高于上界的情况。')
  await page.getByRole('button', { name: '提交并更新状态', exact: true }).click()
  await expect(page.locator('.evidence-result')).toContainText('刚刚写入 Evidence')
  await expect(page.locator('.action-surface')).toBeVisible()

  await page.getByRole('tab', { name: /Progress/ }).click()
  await expect(page.locator('.objective-detail')).toContainText('当前没有 active misconception')
})

test('旧入口只重定向到三块核心区域，移动端保持可用', async ({ page }) => {
  await loginSeedCourse(page)
  await page.goto('/#/progress')
  await expect(page).toHaveURL(/#\/learn\/\d+\?panel=overview/)
  await expect(page.locator('.progress-view')).toBeVisible()

  await page.goto('/#/resources')
  await expect(page).toHaveURL(/#\/learn\/\d+\?panel=materials/)
  await expect(page.locator('.sources-view')).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/#/today')
  await expect(page.locator('.adaptive-home')).toBeVisible()
  await expect(page.locator('.home-next-action')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.getByRole('button', { name: '打开课程栏' }).click()
  await page.locator('.mobile-rail .course-link').filter({ hasText: '软件测试冲刺' }).click()
  await expect(page.locator('.adaptive-tutor')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})
