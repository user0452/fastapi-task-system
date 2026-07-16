import { expect, test } from '@playwright/test'


test.describe.configure({ mode: 'serial' })

const password = 'A3Demo123!'

function username(testInfo) {
  return `a3_e2e_${testInfo.repeatEachIndex}`
}

async function login(page, testInfo) {
  await page.goto('/#/login')
  await page.getByPlaceholder('请输入用户名').fill(username(testInfo))
  await page.getByPlaceholder('请输入密码').fill(password)
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/#\/today$/)
}

async function openSeedCourse(page) {
  await page.locator('.course-link').filter({ hasText: '软件测试冲刺' }).click()
  await expect(page).toHaveURL(/#\/learn\/\d+/)
  await expect(page.locator('.course-identity').getByText('软件测试冲刺', { exact: true })).toBeVisible()
}

async function createCourse(page, name, goal) {
  await page.getByRole('button', { name: '新建课程', exact: true }).click()
  await page.getByPlaceholder('例如：软件测试').fill(name)
  await page.getByPlaceholder('例如：掌握核心测试设计方法并完成考试冲刺').fill(goal)
  await page.getByRole('button', { name: '创建课程助手', exact: true }).click()
  await expect(page).toHaveURL(/#\/learn\/\d+\?panel=materials/)
  await expect(page.locator('.course-identity').getByText(name, { exact: true })).toBeVisible()
}

async function sendMessage(page, text) {
  const composer = page.locator('.chat-composer textarea')
  await composer.fill(text)
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  await expect(page.locator('.chat-message.user').last()).toContainText(text)
  await expect.poll(async () => {
    return (await page.locator('.chat-message.assistant').last().locator('.message-text').textContent())?.trim().length || 0
  }).toBeGreaterThan(0)
}

test('注册后创建课程助手并上传资料自动建立知识图谱', async ({ page }, testInfo) => {
  test.setTimeout(90_000)
  const flowUsername = `a3_e2e_flow_${Date.now().toString(36)}_${testInfo.repeatEachIndex}`
  const courseName = `浏览器课程 ${testInfo.repeatEachIndex + 1}`

  await page.goto('/#/login')
  await page.getByRole('button', { name: '注册', exact: true }).click()
  await page.getByPlaceholder('3-30 个字符').fill(flowUsername)
  await page.getByPlaceholder('至少 6 位').fill(password)
  await page.getByPlaceholder('再次输入密码').fill(password)
  await page.locator('form').getByRole('button', { name: '注册', exact: true }).click()
  await page.getByPlaceholder('请输入密码').fill(password)
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/#\/today$/)

  await createCourse(page, courseName, '验证资料、知识点与课程助手闭环')
  await page.getByPlaceholder('例如：第三章边界值分析').fill('自动索引测试讲义')
  await page.locator('input[type="file"]').setInputFiles({
    name: 'browser-flow.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(
      '等价类划分将输入域分成有效类和无效类。边界值分析检查边界及附近值。判定表用于组合多个条件。',
      'utf8'
    )
  })
  await page.getByRole('button', { name: '提交并自动处理', exact: true }).click()
  await expect(page.getByText('自动索引测试讲义', { exact: true })).toBeVisible()
  await expect(page.getByText('可使用', { exact: true })).toBeVisible({ timeout: 40_000 })

  await page.getByRole('tab', { name: '知识点', exact: true }).click()
  await expect.poll(() => page.locator('.knowledge-list article').count()).toBeGreaterThanOrEqual(3)
  await expect(page.locator('.relations')).toBeVisible()
  await page.reload()
  await expect(page).toHaveURL(/panel=knowledge/)
  await expect.poll(() => page.locator('.knowledge-list article').count()).toBeGreaterThanOrEqual(3)
})

test('三门课程拥有独立助手、资料和对话历史', async ({ page }, testInfo) => {
  test.setTimeout(90_000)
  await login(page, testInfo)
  const suffix = testInfo.repeatEachIndex + 1
  const courseA = `课程隔离甲 ${suffix}`
  const courseB = `课程隔离乙 ${suffix}`
  const markerA = `甲课程专属消息-${suffix}`
  const markerB = `乙课程专属消息-${suffix}`

  await createCourse(page, courseA, '只学习甲课程内容')
  await page.getByRole('button', { name: '手动输入', exact: true }).click()
  await page.getByPlaceholder('例如：第三章边界值分析').fill('甲课程资料')
  await page.getByPlaceholder('粘贴讲义、笔记或复习提纲').fill('甲课程独有概念，包含甲课程专属知识与三个应用场景。')
  await page.getByRole('button', { name: '提交并自动处理', exact: true }).click()
  await expect(page.getByText('可使用', { exact: true })).toBeVisible({ timeout: 40_000 })
  await page.getByRole('button', { name: '关闭课程面板', exact: true }).click()
  await sendMessage(page, markerA)

  await createCourse(page, courseB, '只学习乙课程内容')
  await page.getByRole('button', { name: '手动输入', exact: true }).click()
  await page.getByPlaceholder('例如：第三章边界值分析').fill('乙课程资料')
  await page.getByPlaceholder('粘贴讲义、笔记或复习提纲').fill('乙课程独有概念，包含乙课程专属知识与三个典型案例。')
  await page.getByRole('button', { name: '提交并自动处理', exact: true }).click()
  await expect(page.getByText('可使用', { exact: true })).toBeVisible({ timeout: 40_000 })
  await page.getByRole('button', { name: '关闭课程面板', exact: true }).click()
  await sendMessage(page, markerB)

  await expect(page.locator('.course-link')).toHaveCount(3)
  await page.locator('.course-link').filter({ hasText: courseA }).click()
  await expect(page.locator('.message-list')).toContainText(markerA)
  await expect(page.locator('.message-list')).not.toContainText(markerB)
  await page.locator('.course-link').filter({ hasText: courseB }).click()
  await expect(page.locator('.message-list')).toContainText(markerB)
  await expect(page.locator('.message-list')).not.toContainText(markerA)
})

test('课程回答展示可展开的内部资料与外部网页来源气泡', async ({ page }, testInfo) => {
  await login(page, testInfo)
  await openSeedCourse(page)
  await sendMessage(page, '根据课程资料讲解边界值分析。')
  const sourcedAnswer = page.locator('.chat-message.assistant:has(.source-bubble.rag)').last()
  await expect(sourcedAnswer.locator('.source-label')).toHaveText('来源')
  const firstSource = sourcedAnswer.locator('.source-bubble.rag').first()
  await expect(firstSource).toContainText('软件测试设计方法讲义')
  await firstSource.click()
  await expect(sourcedAnswer.locator('.source-original')).toContainText('边界值')

  await page.route('https://img.youtube.com/**', route => route.abort())
  await sendMessage(page, '我想去网上学边界值分析，推荐几个视频。')
  const latestAssistant = page.locator('.chat-message.assistant:has(.source-bubble.web)').last()
  await expect(latestAssistant.locator('.source-bubble.web')).toHaveCount(4)
  await latestAssistant.locator('.source-bubble.web').first().click()
  await expect(latestAssistant.locator('.source-original')).not.toBeEmpty()
  await expect(latestAssistant.getByRole('link', { name: '打开网页', exact: true })).toBeVisible()

  await page.reload()
  await expect(
    page.locator('.chat-message.assistant:has(.source-bubble.web)').last().locator('.source-bubble.web')
  ).toHaveCount(4)
})

test('聊天内做题后更新掌握度、错题和后续计划', async ({ page }, testInfo) => {
  await login(page, testInfo)
  await openSeedCourse(page)
  await sendMessage(page, '围绕边界值分析给我出 3 道题。')

  const practice = page.locator('.practice-card').last()
  await expect(practice.locator('textarea')).toHaveCount(3)
  await practice.locator('textarea').nth(0).fill('不知道。')
  await practice.locator('textarea').nth(1).fill('说明边界本身、边界附近值和刚好越界值，并给出测试输入。')
  await practice.locator('textarea').nth(2).fill('结合输入范围设计有效与无效测试用例并说明预期结果。')
  await practice.getByRole('button', { name: '提交并更新掌握度', exact: true }).click()
  await expect(practice.getByText(/个知识点已更新/)).toBeVisible()

  await page.getByRole('button', { name: '打开课程面板', exact: true }).click()
  await page.getByRole('tab', { name: '练习', exact: true }).click()
  await expect(page.locator('.practice-metrics')).toContainText('1')
  await page.getByRole('tab', { name: '错题', exact: true }).click()
  await expect(page.locator('.wrong-list article')).toHaveCount(1)
  await page.getByRole('tab', { name: '知识点', exact: true }).click()
  await expect(page.locator('.knowledge-list article').filter({ hasText: '边界值分析' }).first()).toBeVisible()
  await page.getByRole('tab', { name: '计划', exact: true }).click()
  await expect.poll(() => page.locator('.session-list article').count()).toBeGreaterThanOrEqual(7)
  await expect(page.locator('.session-list').getByText('掌握度为', { exact: false }).first()).toBeVisible()

  await page.reload()
  await expect(page).toHaveURL(/panel=plan/)
  const workspaceUrl = page.url()
  await page.getByRole('button', { name: '退出登录', exact: true }).click()
  await expect(page).toHaveURL(/#\/login\?redirect=/)
  await page.getByPlaceholder('请输入用户名').fill(username(testInfo))
  await page.getByPlaceholder('请输入密码').fill(password)
  await page.locator('form').getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(workspaceUrl)
  await expect(page.locator('.course-inspector')).toBeVisible()
  await expect(page.getByRole('tab', { name: '计划', exact: true })).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('button', { name: '关闭课程面板', exact: true }).click()
  await expect(page.locator('.practice-card').last()).toContainText('个知识点已更新')
})

test('课程面板开关不丢草稿，旧地址重定向且危险操作仍需确认', async ({ page, request }, testInfo) => {
  const loginResponse = await request.post('/api/v1/auth/login', {
    data: { username: username(testInfo), password }
  })
  expect(loginResponse.status()).toBe(200)
  const taskResponse = await request.post('/tasks', {
    data: { title: 'E2E 二次确认任务', description: '自动化验收', status: 'todo', priority: 'medium' }
  })
  expect(taskResponse.status()).toBe(200)
  const task = (await taskResponse.json()).data

  await login(page, testInfo)
  await openSeedCourse(page)
  const draft = '这是一条尚未发送的课程草稿'
  await page.locator('.chat-composer textarea').fill(draft)
  await page.getByRole('button', { name: '打开课程面板', exact: true }).click()
  await expect(page.locator('.course-inspector')).toBeVisible()
  await page.getByRole('button', { name: '关闭课程面板', exact: true }).click()
  await expect(page.locator('.chat-composer textarea')).toHaveValue(draft)

  await page.goto('/#/progress')
  await expect(page).toHaveURL(/#\/learn\/\d+\?panel=overview/)
  await page.getByRole('button', { name: '关闭课程面板', exact: true }).click()
  await sendMessage(page, `删除任务 ${task.id}`)
  await expect(page.getByRole('button', { name: '确认执行', exact: true })).toBeVisible()
  expect((await request.get(`/tasks/${task.id}`)).status()).toBe(200)
  await page.getByRole('button', { name: '确认执行', exact: true }).click()
  await expect(page.locator('.message-list').getByText('任务已删除。', { exact: true })).toBeVisible()
  expect((await request.get(`/tasks/${task.id}`)).status()).toBe(404)
})

test('mobile course workspace keeps navigation, chat and inspector usable', async ({ page }, testInfo) => {
  await login(page, testInfo)
  await openSeedCourse(page)
  await page.setViewportSize({ width: 390, height: 844 })

  await expect(page.locator('.mobile-bar')).toBeVisible()
  await expect(page.locator('.workspace-chat')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

  await page.locator('.chat-header > button').click()
  const inspector = page.locator('.course-inspector')
  await expect(inspector).toBeVisible()
  await page.waitForTimeout(220)
  const inspectorBox = await inspector.boundingBox()
  expect(inspectorBox?.x).toBeLessThan(1)
  expect(inspectorBox?.width).toBeGreaterThanOrEqual(389)
  await expect(page.locator('.inspector-tabs button')).toHaveCount(8)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

  await page.locator('.inspector-header button').click()
  await expect(inspector).toBeHidden()
  const chatBox = await page.locator('.workspace-chat').boundingBox()
  expect(chatBox?.width).toBeGreaterThanOrEqual(389)

  await page.locator('.mobile-bar button').first().click()
  await expect(page.locator('.mobile-rail .course-rail')).toBeVisible()
  const railBox = await page.locator('.mobile-rail .course-rail').boundingBox()
  expect(railBox?.width).toBeLessThanOrEqual(328)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

test('新版工作台可完成诊断并提交今日学习', async ({ page }, testInfo) => {
  test.setTimeout(90_000)
  await login(page, testInfo)
  await openSeedCourse(page)
  await page.getByRole('button', { name: '打开课程面板', exact: true }).click()
  await page.getByRole('tab', { name: '诊断', exact: true }).click()

  const diagnostic = page.locator('.diagnostic-workspace')
  const diagnosticAnswers = diagnostic.locator('textarea')
  await expect(diagnosticAnswers).toHaveCount(6)
  for (let index = 0; index < await diagnosticAnswers.count(); index += 1) {
    await diagnosticAnswers.nth(index).fill(`诊断作答 ${index + 1}`)
  }
  await diagnostic.locator('.diagnostic-actions button').click()
  await expect(diagnostic.locator('.diagnostic-complete')).toBeVisible()
  await diagnostic.locator('.diagnostic-complete button').click()

  await expect(page).toHaveURL(/#\/learn\/\d+\?panel=today/)
  const today = page.locator('.today-page')
  await expect(today).toBeVisible()
  await today.locator('.study-actions button').click()
  const practiceAnswers = today.locator('.practice-block textarea')
  for (let index = 0; index < await practiceAnswers.count(); index += 1) {
    await practiceAnswers.nth(index).fill(`今日学习作答 ${index + 1}`)
  }
  await today.locator('.study-actions button').click()
  await expect(today.locator('.completion-view')).toBeVisible()
})
