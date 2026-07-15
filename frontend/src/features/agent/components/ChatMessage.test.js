import { describe, expect, it } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import ChatMessage from './ChatMessage.vue'


const baseMessage = {
  id: 1,
  role: 'assistant',
  content: '已加载今日学习。',
  sources: [],
  tool_calls: {
    cards: [{ type: 'today', data: { items: [{ id: 1 }], estimated_minutes: 30 } }],
    actions: [{ type: 'navigate', label: '打开今日学习', to: '/today' }]
  }
}


describe('ChatMessage', () => {
  it('renders tool cards and emits navigation actions', async () => {
    const wrapper = mount(ChatMessage, {
      props: { message: baseMessage },
      global: { stubs: { RouterLink: RouterLinkStub } }
    })

    expect(wrapper.text()).toContain('1 项 · 30 分钟')
    await wrapper.get('.message-actions button').trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['/today']])
  })

  it('shows pending confirmation but not an already executed action', async () => {
    const pending = {
      ...baseMessage,
      tool_calls: {
        confirmation: { id: 8, summary: '删除任务“测试”', status: 'pending' }
      }
    }
    const wrapper = mount(ChatMessage, {
      props: { message: pending },
      global: { stubs: { RouterLink: RouterLinkStub } }
    })

    await wrapper.get('.confirmation-actions .danger').trigger('click')
    expect(wrapper.emitted('decide')?.[0]?.[1]).toBe(true)

    await wrapper.setProps({
      message: {
        ...pending,
        tool_calls: { confirmation: { ...pending.tool_calls.confirmation, status: 'executed' } }
      }
    })
    expect(wrapper.find('.confirmation-bar').exists()).toBe(false)
    expect(wrapper.text()).toContain('该操作已执行')
  })

  it('renders sanitized Markdown and hides internal source markers', () => {
    const wrapper = mount(ChatMessage, {
      props: {
        message: {
          ...baseMessage,
          content: '## Hadoop ⭐\n\n**HDFS** 负责存储。[chunk_id=852]\n\n| 组件 | 作用 |\n| --- | --- |\n| HDFS | 存储 |\n\n<script>alert(1)</script>'
        }
      }
    })

    expect(wrapper.find('.markdown-body h2').text()).toBe('Hadoop')
    expect(wrapper.find('.markdown-body strong').text()).toBe('HDFS')
    expect(wrapper.find('.markdown-body table').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('chunk_id')
    expect(wrapper.text()).not.toContain('⭐')
    expect(wrapper.find('script').exists()).toBe(false)
  })
})
