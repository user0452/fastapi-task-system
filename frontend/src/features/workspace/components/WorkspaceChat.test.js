import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const agentApi = vi.hoisted(() => ({
  archiveAgentSession: vi.fn(),
  createAgentSession: vi.fn(),
  decideAgentAction: vi.fn(),
  getAgentSessions: vi.fn(),
  getCourseAgentWorkspace: vi.fn(),
  sendAgentMessageStream: vi.fn()
}))

const routerMock = vi.hoisted(() => ({
  route: { path: '/learn/1', query: {} },
  replace: vi.fn(),
  push: vi.fn()
}))

vi.mock('../../../api/agent', () => agentApi)
vi.mock('vue-router', () => ({
  useRoute: () => routerMock.route,
  useRouter: () => ({ replace: routerMock.replace, push: routerMock.push })
}))
vi.mock('../../../components/common/toast', () => ({ showToast: vi.fn() }))

import WorkspaceChat from './WorkspaceChat.vue'


function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

function mountChat(courseId = 1) {
  return mount(WorkspaceChat, {
    props: {
      courseId,
      course: { id: courseId, name: `课程 ${courseId}` }
    },
    global: {
      stubs: {
        ChatMessage: {
          props: ['message'],
          template: '<div class="message-content">{{ message.content }}</div>'
        }
      }
    }
  })
}

describe('WorkspaceChat stream isolation', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    routerMock.route.path = '/learn/1'
    routerMock.route.query = {}
    routerMock.replace.mockImplementation(async target => {
      routerMock.route.path = target.path
      routerMock.route.query = target.query || {}
    })
    HTMLElement.prototype.scrollTo = vi.fn()
    window.matchMedia = vi.fn().mockReturnValue({ matches: false })
    agentApi.getAgentSessions.mockImplementation(params => Promise.resolve({
      code: 200,
      data: {
        items: [{ id: Number(params.course_id) * 10, title: `课程 ${params.course_id} 会话` }]
      }
    }))
    agentApi.getCourseAgentWorkspace.mockImplementation(courseId => Promise.resolve({
      code: 200,
      data: {
        session: { id: courseId * 10 },
        agent: { id: courseId },
        messages: []
      }
    }))
  })

  it('restores the routed session and requests only the current course sessions', async () => {
    routerMock.route.query = { session: '12' }
    agentApi.getAgentSessions.mockResolvedValue({
      code: 200,
      data: {
        items: [
          { id: 11, title: '基础概念' },
          { id: 12, title: '边界值复习' }
        ]
      }
    })
    const wrapper = mountChat(1)
    await flushPromises()

    expect(agentApi.getAgentSessions).toHaveBeenCalledWith({
      page: 1,
      size: 100,
      course_id: 1
    })
    expect(agentApi.getCourseAgentWorkspace).toHaveBeenCalledWith(1, {
      message_limit: 100,
      session_id: 12
    })
    wrapper.unmount()
  })

  it('builds a current conversation outline and keeps history in the header drawer', async () => {
    agentApi.getCourseAgentWorkspace.mockResolvedValue({
      code: 200,
      data: {
        session: { id: 10 },
        agent: { id: 1 },
        messages: [
          { id: 31, role: 'user', content: '解释边界值分析' },
          { id: 32, role: 'assistant', content: '边界值分析是……' },
          { id: 33, role: 'user', content: '再给我三个练习题' }
        ]
      }
    })
    const wrapper = mountChat(1)
    await flushPromises()

    const outlineItems = wrapper.findAll('.anchor-item')
    expect(outlineItems).toHaveLength(2)
    expect(wrapper.findAll('.anchor-bar')).toHaveLength(2)
    expect(wrapper.get('#chat-message-31').attributes('data-message-role')).toBe('user')
    expect(wrapper.get('#chat-message-33').attributes('data-message-id')).toBe('33')
    expect(outlineItems[0].attributes('aria-label')).toContain('解释边界值分析')

    await outlineItems[0].trigger('click')
    expect(HTMLElement.prototype.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'smooth' }))

    expect(wrapper.find('.history-drawer').exists()).toBe(false)
    await wrapper.get('.history-action').trigger('click')
    expect(wrapper.get('.history-drawer').attributes('aria-label')).toBe('历史对话')
    expect(wrapper.get('.history-drawer').text()).toContain('课程 1 会话')
    wrapper.unmount()
  })

  it('opens already at the latest messages after restoring conversation history', async () => {
    agentApi.getCourseAgentWorkspace.mockResolvedValue({
      code: 200,
      data: {
        session: { id: 10 },
        agent: { id: 1 },
        messages: [
          { id: 31, role: 'user', content: '最早的问题' },
          { id: 32, role: 'assistant', content: '最早的回答' },
          { id: 33, role: 'user', content: '最新的问题' },
          { id: 34, role: 'assistant', content: '最新的回答' }
        ]
      }
    })
    const wrapper = mountChat(1)
    await flushPromises()
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('#chat-message-34').exists()).toBe(true)
    // Restored history is pinned via scrollTop, not an animated scrollTo.
    expect(wrapper.find('.chat-viewport').classes()).not.toContain('is-pinning')
    wrapper.unmount()
  })

  it('ignores stale stream callbacks after switching courses', async () => {
    const stream = deferred()
    let handlers
    let options
    agentApi.sendAgentMessageStream.mockImplementation((_payload, nextHandlers, nextOptions) => {
      handlers = nextHandlers
      options = nextOptions
      return stream.promise
    })
    const wrapper = mountChat(1)
    await flushPromises()

    const sending = wrapper.vm.send('第一门课的问题')
    await flushPromises()
    await wrapper.setProps({ courseId: 2, course: { id: 2, name: '课程 2' } })
    await flushPromises()

    expect(options.signal.aborted).toBe(true)
    expect(() => handlers.onDelta('旧课程增量')).not.toThrow()
    expect(() => handlers.onResult({
      session: { id: 10 },
      agent: { id: 1 },
      message: { id: 99, role: 'assistant', content: '旧课程结果' },
      reply: '旧课程结果'
    })).not.toThrow()
    stream.resolve()
    await sending
    await flushPromises()

    expect(wrapper.text()).not.toContain('旧课程增量')
    expect(wrapper.text()).not.toContain('旧课程结果')
    wrapper.unmount()
  })

  it('aborts the reader and makes late callbacks harmless on unmount', async () => {
    const stream = deferred()
    let handlers
    let options
    agentApi.sendAgentMessageStream.mockImplementation((_payload, nextHandlers, nextOptions) => {
      handlers = nextHandlers
      options = nextOptions
      return stream.promise
    })
    const wrapper = mountChat(1)
    await flushPromises()

    const sending = wrapper.vm.send('卸载测试')
    await flushPromises()
    wrapper.unmount()

    expect(options.signal.aborted).toBe(true)
    expect(() => handlers.onDelta('卸载后的增量')).not.toThrow()
    stream.resolve()
    await sending
  })
})
