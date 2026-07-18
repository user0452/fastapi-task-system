import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SessionList from './SessionList.vue'


const session = {
  id: 7,
  title: '边界值复习',
  course_name: '软件测试',
  last_message: '今天应该练什么？',
  updated_at: '2026-07-12T08:00:00'
}


describe('SessionList', () => {
  it('shows an actionable empty state', () => {
    const wrapper = mount(SessionList, { props: { sessions: [] } })

    expect(wrapper.text()).toContain('还没有历史对话')
    expect(wrapper.get('[aria-label="新建对话"]').exists()).toBe(true)
  })

  it('selects and archives the requested session', async () => {
    const wrapper = mount(SessionList, { props: { sessions: [session], activeId: 7 } })

    await wrapper.get('.session-select').trigger('click')
    await wrapper.get('.archive-action').trigger('click')

    expect(wrapper.emitted('select')).toEqual([[session]])
    expect(wrapper.emitted('archive')).toEqual([[session]])
    expect(wrapper.get('.session-item').classes()).toContain('active')
  })
})
