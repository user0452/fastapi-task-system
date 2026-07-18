import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import MemoryPanel from './MemoryPanel.vue'


const agentApi = vi.hoisted(() => ({
  deleteCourseAgentMemory: vi.fn(),
  getCourseAgentMemories: vi.fn(),
  saveCourseAgentMemory: vi.fn(),
  toggleCourseAgentMemoryType: vi.fn(),
  updateCourseAgentMemory: vi.fn()
}))

vi.mock('../../../api/agent', () => agentApi)

const items = [
  {
    id: 1,
    memory_type: 'course_preference',
    content: { text: '先举例，再解释定义' },
    source_type: 'manual',
    source_message_id: null,
    enabled: true,
    updated_at: '2026-07-18T08:00:00Z'
  },
  {
    id: 2,
    memory_type: 'weak_point',
    content: { text: '容易混淆事务隔离级别' },
    source_type: 'chat',
    source_message_id: 18,
    enabled: false,
    updated_at: '2026-07-18T09:00:00Z'
  }
]

function buttonByText(wrapper, text) {
  return wrapper.findAll('button').find(button => button.text().includes(text))
}

describe('MemoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    agentApi.getCourseAgentMemories.mockResolvedValue({ code: 200, data: { items } })
    agentApi.saveCourseAgentMemory.mockResolvedValue({ code: 200, data: items[0] })
    agentApi.updateCourseAgentMemory.mockResolvedValue({ code: 200, data: items[0] })
    agentApi.toggleCourseAgentMemoryType.mockResolvedValue({ code: 200, data: { affected: 1 } })
    agentApi.deleteCourseAgentMemory.mockResolvedValue({ code: 200 })
  })

  it('shows memory source, update time and active state from the API', async () => {
    const wrapper = mount(MemoryPanel, { props: { courseId: 7 } })
    await flushPromises()

    expect(agentApi.getCourseAgentMemories).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('先举例，再解释定义')
    expect(wrapper.text()).toContain('手动添加')
    expect(wrapper.text()).toContain('对话消息 #18')
    expect(buttonByText(wrapper, '重新启用')).toBeTruthy()
  })

  it('updates one memory and can toggle an entire memory type', async () => {
    const wrapper = mount(MemoryPanel, { props: { courseId: 7 } })
    await flushPromises()

    await buttonByText(wrapper, '暂停使用').trigger('click')
    await flushPromises()
    expect(agentApi.updateCourseAgentMemory).toHaveBeenCalledWith(7, 1, { enabled: false })

    await buttonByText(wrapper, '已暂停').trigger('click')
    await flushPromises()
    expect(agentApi.toggleCourseAgentMemoryType).toHaveBeenCalledWith(7, 'weak_point', true)
  })

  it('supports correcting, adding and deleting memory with confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(MemoryPanel, { props: { courseId: 7 } })
    await flushPromises()

    await buttonByText(wrapper, '修正').trigger('click')
    const edit = wrapper.get('article textarea')
    await edit.setValue('先给结论，再给例子')
    await buttonByText(wrapper, '保存').trigger('click')
    await flushPromises()
    expect(agentApi.updateCourseAgentMemory).toHaveBeenCalledWith(7, 1, {
      content: { text: '先给结论，再给例子' }
    })

    await wrapper.get('.memory-heading > button').trigger('click')
    await wrapper.get('.memory-form select').setValue('learning_goal')
    await wrapper.get('.memory-form textarea').setValue('本周完成事务章节')
    await wrapper.get('.memory-form').trigger('submit')
    await flushPromises()
    expect(agentApi.saveCourseAgentMemory).toHaveBeenCalledWith(7, expect.objectContaining({
      memory_type: 'learning_goal',
      content: { text: '本周完成事务章节' }
    }))

    await buttonByText(wrapper, '删除').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect(agentApi.deleteCourseAgentMemory).toHaveBeenCalledWith(7, 1)
    confirm.mockRestore()
  })
})
