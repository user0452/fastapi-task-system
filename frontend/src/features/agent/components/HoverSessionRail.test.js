import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import HoverSessionRail from './HoverSessionRail.vue'


const sessions = [
  { id: 7, title: '边界值复习', last_message: '继续做题' },
  { id: 8, title: '判定表练习', last_message: '梳理条件桩' }
]

describe('HoverSessionRail', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('expands on hover and closes after a stable delay', async () => {
    vi.useFakeTimers()
    const wrapper = mount(HoverSessionRail, {
      props: { sessions, activeId: 7 }
    })

    await wrapper.get('.hover-session-rail').trigger('mouseenter')
    expect(wrapper.find('.expanded-session-panel').exists()).toBe(true)

    await wrapper.get('.hover-session-rail').trigger('mouseleave')
    await vi.advanceTimersByTimeAsync(199)
    expect(wrapper.get('.hover-session-rail').classes()).toContain('expanded')
    await vi.advanceTimersByTimeAsync(1)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.hover-session-rail').classes()).not.toContain('expanded')
  })

  it('switches from a collapsed marker and exposes the title as a tooltip', async () => {
    const wrapper = mount(HoverSessionRail, {
      props: { sessions, activeId: 7 }
    })
    const markers = wrapper.findAll('.session-marker')

    expect(markers[1].attributes('title')).toBe('判定表练习')
    await markers[1].trigger('click')
    expect(wrapper.emitted('select')).toEqual([[sessions[1]]])
  })

  it('keeps a manually expanded rail locked after the pointer leaves', async () => {
    vi.useFakeTimers()
    const wrapper = mount(HoverSessionRail, {
      props: { sessions, activeId: 7 }
    })

    await wrapper.get('.expand-control').trigger('click')
    expect(wrapper.get('.expand-control').attributes('aria-expanded')).toBe('true')

    await wrapper.get('.hover-session-rail').trigger('mouseleave')
    await vi.advanceTimersByTimeAsync(200)
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.hover-session-rail').classes()).toContain('expanded')
    expect(wrapper.get('.expand-control').attributes('aria-expanded')).toBe('true')

    await wrapper.get('.hover-session-rail').trigger('keydown', { key: 'Escape' })
    expect(wrapper.get('.hover-session-rail').classes()).not.toContain('expanded')
  })

  it('uses a drawer on mobile and closes after selection', async () => {
    const wrapper = mount(HoverSessionRail, {
      props: { sessions, activeId: 7, mobileOpen: true }
    })

    expect(wrapper.get('.session-rail-slot').classes()).toContain('mobile-open')
    await wrapper.findAll('.session-select')[1].trigger('click')
    expect(wrapper.emitted('select')).toEqual([[sessions[1]]])
    expect(wrapper.emitted('close-mobile')).toHaveLength(1)
  })
})
