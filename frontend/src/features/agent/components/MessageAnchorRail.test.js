import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MessageAnchorRail from './MessageAnchorRail.vue'


const messages = [
  { id: 11, role: 'user', content: '解释边界值分析' },
  { id: 12, role: 'assistant', content: '边界值分析是……' },
  { id: 13, role: 'user', content: '再给我三个练习题' }
]

describe('MessageAnchorRail', () => {
  it('renders compact bars for current conversation user messages and highlights by stable id', async () => {
    const wrapper = mount(MessageAnchorRail, {
      props: { messages, activeMessageId: 13 }
    })

    const items = wrapper.findAll('.anchor-item')
    expect(items).toHaveLength(2)
    expect(wrapper.findAll('.anchor-bar')).toHaveLength(2)
    expect(wrapper.findAll('.anchor-row')[1].classes()).toContain('active')
    expect(items[1].attributes('aria-current')).toBe('location')
    expect(items[0].attributes('aria-label')).toContain('解释边界值分析')

    await items[0].trigger('click')
    expect(wrapper.emitted('jump')).toEqual([[11]])
  })

  it('expands all bars with question summaries on hover', async () => {
    const wrapper = mount(MessageAnchorRail, {
      props: { messages }
    })

    const slot = wrapper.get('.message-anchor-slot')
    const rail = wrapper.get('.message-anchor-rail')
    const rows = wrapper.findAll('.anchor-row')

    expect(slot.classes()).not.toContain('expanded')
    await rail.trigger('mouseenter')
    expect(slot.classes()).toContain('expanded')
    expect(wrapper.text()).toContain('解释边界值分析')
    expect(wrapper.text()).toContain('再给我三个练习题')

    await rows[0].trigger('mouseenter')
    expect(rows[0].classes()).toContain('previewing')

    await rail.trigger('mouseleave')
    expect(slot.classes()).not.toContain('expanded')
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
