import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CourseRail from './CourseRail.vue'


function mountRail(courses) {
  return mount(CourseRail, {
    props: { courses, currentId: courses[0]?.id, username: 'tester' },
    global: {
      stubs: {
        RouterLink: { props: ['to'], template: '<a><slot /></a>' }
      }
    }
  })
}

describe('CourseRail adaptive course navigation', () => {
  it('shows simple daily study context instead of a roadmap stage', () => {
    const wrapper = mountRail([{
      id: 3,
      name: '软件测试',
      daily_minutes: 30,
      status: 'active'
    }])

    expect(wrapper.text()).toContain('30 分钟/天')
    expect(wrapper.text()).not.toContain('总进度')
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
  })

  it('shows material and diagnostic readiness states', () => {
    const wrapper = mountRail([{
      id: 4,
      name: '新课程',
      daily_minutes: 30,
      status: 'diagnostic_pending'
    }])

    expect(wrapper.text()).toContain('等待初始诊断')
  })
})
