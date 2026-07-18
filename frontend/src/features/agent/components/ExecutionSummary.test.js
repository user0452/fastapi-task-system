import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ExecutionSummary from './ExecutionSummary.vue'


const summary = {
  tools: [{ name: 'calculator', status: 'completed', duration_ms: 4.7, risk_level: 'read' }],
  internal_sources: [{ chunk_id: 9, material_title: '操作系统讲义', page_number: 3 }],
  external_sources: [{ id: 5, title: '参考文档', url: 'https://example.com/docs', provider: '网页' }],
  context_used: { memory_count: 2, weak_point_count: 1, recent_turns: 4 },
  updates: { memory: [{ id: 2 }], roadmap: [], mastery: [{ id: 8 }] },
  note: '仅展示可验证的调用与数据依据，不包含模型内部推理过程。'
}


describe('ExecutionSummary', () => {
  it('renders distinct sources, tools, context and updates', () => {
    const wrapper = mount(ExecutionSummary, { props: { summary } })

    expect(wrapper.get('summary').text()).toContain('本次回答依据')
    expect(wrapper.find('.execution-summary').attributes()).not.toHaveProperty('open')
    expect(wrapper.text()).toContain('calculator')
    expect(wrapper.text()).toContain('成功')
    expect(wrapper.text()).toContain('操作系统讲义')
    expect(wrapper.text()).toContain('参考文档')
    expect(wrapper.text()).toContain('长期记忆 2 条')
    expect(wrapper.text()).toContain('掌握度 1 项')
    expect(wrapper.text()).not.toContain('思维链')
    expect(wrapper.get('.external-sources a').attributes('href')).toBe('https://example.com/docs')
  })

  it('states clearly when no additional evidence was used', () => {
    const wrapper = mount(ExecutionSummary, {
      props: {
        summary: {
          tools: [], internal_sources: [], external_sources: [],
          context_used: {}, updates: {}, note: '这里只展示可验证记录。'
        }
      }
    })

    expect(wrapper.get('summary').text()).toContain('未使用额外工具或来源')
  })
})
