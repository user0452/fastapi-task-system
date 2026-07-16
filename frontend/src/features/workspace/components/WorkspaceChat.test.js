import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const agentApi = vi.hoisted(() => ({
  decideAgentAction: vi.fn(),
  getCourseAgentWorkspace: vi.fn(),
  sendAgentMessageStream: vi.fn()
}))

vi.mock('../../../api/agent', () => agentApi)
vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/learn/1', query: {} }),
  useRouter: () => ({ replace: vi.fn() })
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
    HTMLElement.prototype.scrollTo = vi.fn()
    agentApi.getCourseAgentWorkspace.mockImplementation(courseId => Promise.resolve({
      code: 200,
      data: {
        session: { id: courseId * 10 },
        agent: { id: courseId },
        messages: []
      }
    }))
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
