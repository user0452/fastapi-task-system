import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'


const mocks = vi.hoisted(() => ({
  ensureLoaded: vi.fn(),
  getTodayOverview: vi.fn(),
  push: vi.fn()
}))

vi.mock('../../api/learning', () => ({ getTodayOverview: mocks.getTodayOverview }))
vi.mock('../../stores/course', () => ({
  useCourseStore: () => ({ ensureLoaded: mocks.ensureLoaded, error: '' })
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))

import GlobalTodayPage from './GlobalTodayPage.vue'


function responseFor(minutes) {
  const recommended = Math.min(minutes, 45)
  return {
    code: 200,
    data: {
      items: [{
        course: {
          id: 1,
          name: '软件测试',
          goal: '掌握测试设计方法',
          daily_minutes: 45,
          roadmap_summary: { current_stage_name: '边界值分析', overall_progress: 38 }
        },
        session: {
          id: 10,
          status: 'planned',
          estimated_minutes: 45,
          items: [{ id: 11, title: '完成边界值练习' }]
        },
        recommendation: {
          rank: 1,
          priority_score: 82,
          requested_minutes: 45,
          recommended_minutes: recommended,
          budget_limited: recommended < 45,
          reasons: ['考试日期临近', '薄弱知识点较多']
        }
      }],
      budget: {
        available_minutes: minutes,
        requested_minutes: 45,
        recommended_minutes: recommended,
        unallocated_minutes: Math.max(minutes - recommended, 0),
        limited: minutes < 45
      },
      summary: {
        course_count: 1,
        total_minutes: 45,
        recommended_minutes: recommended,
        total_items: 1,
        completed: 0,
        with_session: 1
      }
    }
  }
}

describe('GlobalTodayPage budget planning', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.ensureLoaded.mockResolvedValue(undefined)
    mocks.getTodayOverview.mockImplementation(minutes => Promise.resolve(responseFor(minutes)))
  })

  it('loads the default budget and renders server-backed recommendations', async () => {
    const wrapper = mount(GlobalTodayPage)
    await flushPromises()

    expect(mocks.getTodayOverview).toHaveBeenCalledWith(90)
    expect(wrapper.get('.budget-options').attributes('role')).toBe('group')
    expect(wrapper.get('.budget-options').attributes('aria-label')).toBe('选择今日可用学习时间')
    expect(wrapper.findAll('.budget-options button')).toHaveLength(4)
    expect(wrapper.get('[data-minutes="90"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.budget-result').attributes('aria-live')).toBe('polite')
    expect(wrapper.get('.budget-result').text()).toContain('45 / 90 分钟')
    expect(wrapper.text()).toContain('推荐 45 分钟')
    expect(wrapper.text()).toContain('考试日期临近')
    expect(wrapper.text()).toContain('薄弱知识点较多')
  })

  it('replans when the learner selects a different available time', async () => {
    const wrapper = mount(GlobalTodayPage)
    await flushPromises()

    await wrapper.get('[data-minutes="30"]').trigger('click')
    await flushPromises()

    expect(mocks.getTodayOverview).toHaveBeenLastCalledWith(30)
    expect(wrapper.get('[data-minutes="30"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.budget-result').text()).toContain('30 / 30 分钟')
    expect(wrapper.get('.budget-result').text()).toContain('总需求 45 分钟；建议本次投入 30 分钟')
    expect(wrapper.text()).toContain('原课程计划 45 分钟；建议本次投入 30 分钟')
    expect(wrapper.text()).toContain('不会删减或改写原课程计划')
  })

  it('prevents overlapping refreshes while a recommendation request is pending', async () => {
    let resolveOverview
    mocks.getTodayOverview.mockReturnValueOnce(new Promise(resolve => {
      resolveOverview = resolve
    }))
    const wrapper = mount(GlobalTodayPage)
    await flushPromises()

    const refresh = wrapper.get('[aria-label="刷新今日总览"]')
    expect(refresh.attributes()).toHaveProperty('disabled')
    await refresh.trigger('click')
    expect(mocks.getTodayOverview).toHaveBeenCalledTimes(1)

    resolveOverview(responseFor(90))
    await flushPromises()
    expect(wrapper.get('[aria-label="刷新今日总览"]').attributes()).not.toHaveProperty('disabled')
  })
})
