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

describe('CourseRail roadmap summaries', () => {
  it('shows the current durable stage and its real progress', () => {
    const wrapper = mountRail([{
      id: 3,
      name: '软件测试',
      daily_minutes: 30,
      roadmap_summary: {
        status: 'ready',
        current_stage_name: '核心知识构建',
        current_stage_progress: 62
      }
    }])

    expect(wrapper.text()).toContain('核心知识构建 · 62%')
    const progress = wrapper.get('[role="progressbar"]')
    expect(progress.attributes('aria-valuenow')).toBe('62')
    expect(progress.get('i').attributes('style')).toContain('width: 62%')
  })

  it('surfaces failed generation instead of displaying a fabricated stage', () => {
    const wrapper = mountRail([{
      id: 4,
      name: '失败课程',
      daily_minutes: 30,
      roadmap_summary: { status: 'failed', last_error: '生成失败' }
    }])

    expect(wrapper.text()).toContain('路线生成失败 · 可在计划页重试')
    expect(wrapper.find('[role="progressbar"]').exists()).toBe(false)
  })
})
