import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const learningApi = vi.hoisted(() => ({
  getLearningRoadmap: vi.fn(),
  getStudyPlan: vi.fn(),
  rescheduleLearningSession: vi.fn(),
  retryLearningRoadmap: vi.fn()
}))

vi.mock('../../../api/learning', () => learningApi)
vi.mock('../../../components/common/toast', () => ({ showToast: vi.fn() }))

import PlanPanel from './PlanPanel.vue'


const readyRoadmap = {
  id: 9,
  status: 'ready',
  generation_method: 'rules_v1',
  stages: [
    {
      id: 91,
      position: 1,
      name: '目标定标与基础诊断',
      goal: '记录真实学习起点',
      status: 'completed',
      progress: 100,
      estimated_days: 2,
      completion_condition: '完成诊断',
      adaptation_reason: '诊断已完成',
      recommended_content: ['完成入门诊断'],
      knowledge_points: [],
      daily_sessions: []
    },
    {
      id: 92,
      position: 2,
      name: '核心知识构建',
      goal: '建立核心知识结构',
      status: 'active',
      progress: 62,
      estimated_days: 10,
      completion_condition: '平均掌握度达到 70%',
      adaptation_reason: '练习结果为 65 分',
      recommended_content: ['按知识关系学习'],
      knowledge_points: [{ id: 7, name: '边界值分析', mastery: 62 }],
      daily_sessions: [{ id: 31 }]
    }
  ]
}

const dailyPlan = {
  title: '课程每日计划',
  start_date: '2026-07-18',
  end_date: '2026-07-25',
  sessions: [{
    id: 31,
    scheduled_date: '2026-07-18',
    status: 'planned',
    estimated_minutes: 30,
    items: [{ title: '边界值练习' }]
  }]
}

describe('PlanPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    learningApi.getLearningRoadmap.mockResolvedValue({ code: 200, data: readyRoadmap })
    learningApi.getStudyPlan.mockResolvedValue({ code: 200, data: dailyPlan })
  })

  it('separates durable stages from the daily execution plan and exposes evidence', async () => {
    const wrapper = mount(PlanPanel, { props: { courseId: 4 } })
    await flushPromises()

    expect(wrapper.text()).toContain('长期阶段路线')
    expect(wrapper.text()).toContain('每日执行计划')
    expect(wrapper.text()).toContain('核心知识构建')
    expect(wrapper.text()).toContain('平均掌握度达到 70%')
    expect(wrapper.text()).toContain('已关联 1 个真实每日学习单元')
    expect(wrapper.text()).toContain('边界值练习')
    expect(wrapper.get('[aria-label="核心知识构建进度"]').attributes('aria-valuenow')).toBe('62')

    await wrapper.get('.stage-evidence button').trigger('click')
    expect(wrapper.emitted('prompt')[0][0]).toContain('边界值分析')
  })

  it('shows a durable failure and replaces it only after an explicit retry succeeds', async () => {
    learningApi.getLearningRoadmap.mockResolvedValue({
      code: 200,
      data: { id: 9, status: 'failed', last_error: '生成器不可用', stages: [] }
    })
    learningApi.getStudyPlan.mockResolvedValue({ code: 200, data: null })
    learningApi.retryLearningRoadmap.mockResolvedValue({ code: 200, data: readyRoadmap })
    const wrapper = mount(PlanPanel, { props: { courseId: 4 } })
    await flushPromises()

    expect(wrapper.text()).toContain('生成器不可用')
    await wrapper.get('.roadmap-state.failed button').trigger('click')
    await flushPromises()

    expect(learningApi.retryLearningRoadmap).toHaveBeenCalledWith(4)
    expect(wrapper.text()).toContain('核心知识构建')
    expect(wrapper.emitted('data-changed')).toHaveLength(1)
  })
})
