import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, onMounted, reactive, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const agentApi = vi.hoisted(() => ({
  archiveAgentSession: vi.fn(),
  createAgentSession: vi.fn(),
  decideAgentAction: vi.fn(),
  getAgentSessions: vi.fn(),
  getCourseAgentWorkspace: vi.fn(),
  sendAgentMessageStream: vi.fn()
}))
const showToast = vi.hoisted(() => vi.fn())

vi.mock('../../../api/agent', () => agentApi)
vi.mock('../../../components/common/toast', () => ({ showToast }))

import { useCourseAgentChat } from './useCourseAgentChat'


function workspace(sessionId, content = '') {
  return {
    code: 200,
    data: {
      session: { id: sessionId, title: `会话 ${sessionId}` },
      agent: { id: 1, name: '课程助手' },
      messages: content ? [{ id: sessionId * 10, role: 'user', content }] : []
    }
  }
}

async function mountChat({ query = {}, sessions = [{ id: 11, title: '最新会话' }] } = {}) {
  const route = reactive({ path: '/learn/1', query: { ...query } })
  const router = {
    replace: vi.fn(async target => {
      route.path = target.path
      route.query = { ...(target.query || {}) }
    })
  }
  const courseId = ref(1)
  let chat
  const Harness = defineComponent({
    setup() {
      chat = useCourseAgentChat({ courseId, route, router })
      onMounted(() => chat.initialize())
      return () => h('div')
    }
  })

  agentApi.getAgentSessions.mockResolvedValue({ code: 200, data: { items: sessions } })
  const wrapper = mount(Harness)
  await flushPromises()
  return { chat, courseId, route, router, wrapper }
}

describe('useCourseAgentChat route recovery', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    agentApi.getCourseAgentWorkspace.mockImplementation((_courseId, params) => (
      Promise.resolve(workspace(Number(params.session_id || 11), `内容 ${params.session_id || 11}`))
    ))
  })

  it('loads a valid routed session that is outside the first session page', async () => {
    const { chat, wrapper } = await mountChat({ query: { session: '812' } })

    expect(agentApi.getCourseAgentWorkspace).toHaveBeenCalledWith(1, {
      message_limit: 100,
      session_id: 812
    })
    expect(chat.activeId.value).toBe(812)
    expect(chat.sessions.value[0].id).toBe(812)
    wrapper.unmount()
  })

  it('restores the latest session when Back removes the session query', async () => {
    const sessionItems = [{ id: 12, title: '旧会话' }, { id: 11, title: '最新会话' }]
    const { chat, route, wrapper } = await mountChat({
      query: { session: '12' },
      sessions: sessionItems
    })

    route.query = {}
    await flushPromises()

    expect(chat.activeId.value).toBe(12)
    expect(route.query).toEqual({})
    expect(agentApi.getCourseAgentWorkspace).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('restores the latest session when Back removes a non-latest session query', async () => {
    const sessionItems = [{ id: 11, title: '最新会话' }, { id: 12, title: '旧会话' }]
    const { chat, route, wrapper } = await mountChat({
      query: { session: '12' },
      sessions: sessionItems
    })

    route.query = {}
    await flushPromises()

    expect(chat.activeId.value).toBe(11)
    expect(route.query).toEqual({})
    expect(agentApi.getCourseAgentWorkspace).toHaveBeenLastCalledWith(1, {
      message_limit: 100,
      session_id: 11
    })
    wrapper.unmount()
  })

  it('switches sessions when Forward adds another valid session query', async () => {
    const sessionItems = [{ id: 11, title: '最新会话' }, { id: 12, title: '旧会话' }]
    const { chat, route, wrapper } = await mountChat({ sessions: sessionItems })

    route.query = { session: '12' }
    await flushPromises()

    expect(chat.activeId.value).toBe(12)
    expect(route.query).toEqual({ session: '12' })
    expect(agentApi.getCourseAgentWorkspace).toHaveBeenLastCalledWith(1, {
      message_limit: 100,
      session_id: 12
    })
    wrapper.unmount()
  })

  it.each([
    [404, '会话不存在'],
    [409, '该会话属于另一门课程']
  ])('clears an invalid routed session with status %s and restores the latest session', async (code, message) => {
    agentApi.getCourseAgentWorkspace.mockImplementation((_courseId, params) => {
      if (Number(params.session_id) === 999) {
        return Promise.resolve({ code, message, data: null })
      }
      return Promise.resolve(workspace(Number(params.session_id || 11)))
    })
    const { chat, route, router, wrapper } = await mountChat({ query: { session: '999' } })

    expect(chat.activeId.value).toBe(11)
    expect(route.query).toEqual({})
    expect(router.replace).toHaveBeenCalledWith({ path: '/learn/1', query: {} })
    expect(showToast).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('clears the previous course session before loading the next course', async () => {
    agentApi.getCourseAgentWorkspace.mockImplementation((courseId, params) => (
      Promise.resolve(workspace(Number(params.session_id || courseId * 10 + 1)))
    ))
    const { chat, courseId, route, wrapper } = await mountChat({ query: { session: '12' } })
    agentApi.getAgentSessions.mockImplementation(params => Promise.resolve({
      code: 200,
      data: { items: [{ id: Number(params.course_id) * 10 + 1, title: '最新会话' }] }
    }))

    courseId.value = 2
    await chat.switchCourse()
    await flushPromises()

    expect(route.query).toEqual({})
    expect(chat.activeId.value).toBe(21)
    expect(agentApi.getCourseAgentWorkspace).not.toHaveBeenCalledWith(2, {
      message_limit: 100,
      session_id: 12
    })
    wrapper.unmount()
  })
})
