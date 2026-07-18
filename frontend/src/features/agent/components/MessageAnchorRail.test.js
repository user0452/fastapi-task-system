import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MessageAnchorRail from './MessageAnchorRail.vue'


const messages = [
  { id: 11, role: 'user', content: '解释边界值分析' },
  { id: 12, role: 'assistant', content: '边界值分析是……' },
  { id: 13, role: 'user', content: '再给我三个练习题' }
]

describe('MessageAnchorRail', () => {
  it('lists only current conversation user messages and highlights by stable id', async () => {
    const wrapper = mount(MessageAnchorRail, {
      props: { messages, activeMessageId: 13 }
    })

    const items = wrapper.findAll('.anchor-item')
    expect(items).toHaveLength(2)
    expect(wrapper.text()).not.toContain('边界值分析是')
    expect(items[1].classes()).toContain('active')
    expect(items[1].attributes('aria-current')).toBe('location')

    await items[0].trigger('click')
    expect(wrapper.emitted('jump')).toEqual([[11]])
  })

  it('closes the mobile drawer after jumping', async () => {
    const wrapper = mount(MessageAnchorRail, {
      props: { messages, mobileOpen: true }
    })

    await wrapper.findAll('.anchor-item')[0].trigger('click')
    expect(wrapper.emitted('jump')).toEqual([[11]])
    expect(wrapper.emitted('close-mobile')).toHaveLength(1)
  })
})
