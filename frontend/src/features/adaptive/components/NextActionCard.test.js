import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import NextActionCard from './NextActionCard.vue'


describe('NextActionCard', () => {
  it('does not tell learners to upload again when a material is already usable', () => {
    const wrapper = mount(NextActionCard, {
      props: {
        entry: { course: { name: '计算机网络', daily_minutes: 25 }, next_action: null },
        setup: {
          title: '资料已可使用，学习内容需要重新准备',
          reason: '资料已经处理完成，但还没能生成可练习的学习内容。',
          buttonLabel: '查看资料',
          meta: '可在资料页重新准备'
        },
        actionLabel: () => '等待课程准备'
      }
    })

    expect(wrapper.text()).toContain('资料已可使用，学习内容需要重新准备')
    expect(wrapper.text()).toContain('查看资料')
    expect(wrapper.text()).not.toContain('添加资料')
  })
})
