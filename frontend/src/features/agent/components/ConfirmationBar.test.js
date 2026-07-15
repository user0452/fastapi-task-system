import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConfirmationBar from './ConfirmationBar.vue'


const confirmation = {
  id: 31,
  summary: '删除任务“复习边界值”',
  status: 'pending'
}


describe('ConfirmationBar', () => {
  it('emits explicit cancel and confirm decisions', async () => {
    const wrapper = mount(ConfirmationBar, { props: { confirmation } })
    const buttons = wrapper.findAll('button')

    await buttons[0].trigger('click')
    await buttons[1].trigger('click')

    expect(wrapper.emitted('decide')).toEqual([[false], [true]])
  })

  it('disables both decisions while an action is running', () => {
    const wrapper = mount(ConfirmationBar, { props: { confirmation, busy: true } })

    expect(wrapper.findAll('button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
  })
})
