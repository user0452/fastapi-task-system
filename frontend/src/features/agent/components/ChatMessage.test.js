import { describe, expect, it, vi } from 'vitest'
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

  it('shows live activity state while the assistant is streaming', () => {
    const wrapper = mount(ChatMessage, {
      props: {
        message: {
          ...baseMessage,
          content: '',
          streaming: true,
          activity: {
            phase: 'web_search',
            message: '正在联网搜索：边界值分析',
            tool: 'search_external_resources'
          }
        }
      }
    })

    expect(wrapper.get('.activity-chip').text()).toContain('正在联网搜索：边界值分析')
    expect(wrapper.get('.activity-chip').classes()).toContain('tone-search')
  })

  it('adds a copy control to code blocks', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText }
    })
    const wrapper = mount(ChatMessage, {
      props: { message: { ...baseMessage, content: '```python\nprint(42)\n```' } }
    })

    await wrapper.get('.code-copy-button').trigger('click')
    expect(writeText).toHaveBeenCalledWith('print(42)\n')
    expect(wrapper.get('.code-copy-button').text()).toBe('已复制')
  })

  it('renders the persisted execution summary for assistant messages', () => {
    const wrapper = mount(ChatMessage, {
      props: {
        message: {
          ...baseMessage,
          tool_calls: {
            ...baseMessage.tool_calls,
            execution_summary: {
              tools: [{ name: 'calculator', status: 'completed', duration_ms: 3 }],
              internal_sources: [],
              external_sources: [],
              context_used: { memory_count: 1 },
              updates: {},
              note: '仅展示可验证记录。'
            }
          }
        }
      }
    })

    expect(wrapper.get('.execution-summary summary').text()).toContain('本次回答依据')
    expect(wrapper.text()).toContain('calculator')
    expect(wrapper.text()).toContain('长期记忆 1 条')
  })

  it('presents a semantic learning turn using only persisted message fields', () => {
    const wrapper = mount(ChatMessage, {
      props: {
        turnGoal: '解释边界值分析，并给我针对性练习。',
        message: {
          ...baseMessage,
          sources: [{ chunk_id: 7 }],
          tool_calls: {
            cards: [{
              type: 'practice',
              data: { id: 9, questions: [{ id: 1 }, { id: 2 }, { id: 3 }] }
            }],
            actions: [{ type: 'open_panel', panel: 'practice', label: '查看做题记录' }],
            execution_summary: {
              internal_sources: [{ chunk_id: 7 }],
              external_sources: [{ id: 2 }],
              context_used: { memory_count: 1, weak_point_count: 2 },
              updates: {}
            }
          }
        }
      },
      global: {
        stubs: {
          PracticeCard: true,
          SourceBubbles: true,
          ExecutionSummary: true
        }
      }
    })

    const section = wrapper.get('.learning-turn')
    expect(section.attributes('aria-labelledby')).toBe('learning-turn-title-1')
    expect(section.get('h3').text()).toBe('本轮学习进度')
    expect(section.findAll('dt').map(item => item.text())).toEqual([
      '本轮目标',
      '依据',
      '练习/掌握度更新',
      '下一步'
    ])
    expect(section.text()).toContain('解释边界值分析，并给我针对性练习。')
    expect(section.text()).toContain('课程资料 1 条，外部来源 1 条，学习记忆 1 条，薄弱知识点 2 个')
    expect(section.text()).toContain('练习 3 道，等待完成')
    expect(section.text()).toContain('完成并提交 3 道练习')
  })

  it('immediately reflects a completed practice and mastery changes in the same learning turn', async () => {
    const result = {
      evaluation: { score: 86 },
      mastery_changes: [
        { knowledge_point_id: 11, delta: 0.12 },
        { knowledge_point_id: 12, delta: 0.08 }
      ]
    }
    const message = {
      ...baseMessage,
      tool_calls: {
        cards: [{
          type: 'practice',
          data: { id: 9, questions: [{ id: 1 }, { id: 2 }] }
        }],
        actions: [{ type: 'open_panel', panel: 'practice', label: '查看做题记录' }]
      }
    }
    const wrapper = mount(ChatMessage, {
      props: {
        turnGoal: '完成两道边界值练习',
        message
      },
      global: {
        stubs: {
          PracticeCard: {
            emits: ['completed'],
            data: () => ({ result }),
            template: '<button class="complete-practice" type="button" @click="$emit(\'completed\', result)">提交练习</button>'
          },
          SourceBubbles: true,
          ExecutionSummary: true
        }
      }
    })

    const section = wrapper.get('.learning-turn')
    expect(section.text()).toContain('练习 2 道，等待完成')
    expect(section.text()).toContain('完成并提交 2 道练习')

    await wrapper.get('.complete-practice').trigger('click')

    expect(section.text()).toContain('练习已完成，掌握度更新 2 项')
    expect(section.text()).toContain('查看做题记录')
    expect(section.text()).not.toContain('等待完成')
    expect(section.text()).not.toContain('完成并提交 2 道练习')
    expect(wrapper.emitted('data-changed')).toEqual([[result]])
    expect(message.tool_calls.cards[0].data.result).toBeUndefined()
  })

  it('states empty turn updates without inventing evidence or actions', () => {
    const wrapper = mount(ChatMessage, {
      props: {
        turnGoal: '复述刚才的定义',
        message: { id: 2, role: 'assistant', content: '请先复述。', sources: [], tool_calls: {} }
      }
    })

    expect(wrapper.get('.learning-turn').text()).toContain('未附加可核对记录')
    expect(wrapper.get('.learning-turn').text()).toContain('本轮暂无练习或掌握度更新')
    expect(wrapper.get('.learning-turn').text()).toContain('暂无待执行操作')
  })
})
