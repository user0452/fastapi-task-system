import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import OverviewPanel from './OverviewPanel.vue'


const learningApi = vi.hoisted(() => ({
  getCourseWorkspaceOverview: vi.fn()
}))

vi.mock('../../../api/learning', () => learningApi)

describe('OverviewPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    learningApi.getCourseWorkspaceOverview.mockResolvedValue({
      code: 200,
      data: {
        progress: {
          session_completed: 2,
          session_total: 4,
          knowledge_points: [
            { id: 1, mastery: 30 },
            { id: 2, mastery: 70 },
            { id: 3, mastery: 90 }
          ],
          weak_points: [{ id: 1 }],
          recent_changes: [{
            id: 4,
            knowledge_point_name: '事务隔离',
            before_value: 45,
            after_value: 62,
            reason: '练习评估更新',
            formula: 'before×0.70+score×0.30',
            weight: 0.3
          }]
        },
        practice: { attempts: 2, wrong: 1, accuracy: 75 },
        plan: { sessions: [{ id: 9, status: 'planned', scheduled_date: '2026-07-19', items: [] }] },
        roadmap: {
          status: 'ready',
          overall_progress: 61,
          stages: [
            { id: 1, name: '核心机制', status: 'active', progress: 50, goal: '掌握核心原理' },
            { id: 2, name: '综合练习', status: 'completed', progress: 100, goal: '完成综合题' }
          ],
          adjustments: [{ id: 2, reason: '根据最近练习提高事务章节优先级' }]
        },
        today: { id: 3, status: 'completed', items: [] }
      }
    })
  })

  it('visualizes only persisted route, mastery and evaluation data', async () => {
    const wrapper = mount(OverviewPanel, { props: { courseId: 7 } })
    await flushPromises()

    expect(learningApi.getCourseWorkspaceOverview).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('路线进度61%')
    expect(wrapper.text()).toContain('今日学习已完成')
    expect(wrapper.text()).toContain('核心机制')
    expect(wrapper.text()).toContain('根据最近练习提高事务章节优先级')
    expect(wrapper.text()).toContain('待加强 1')
    expect(wrapper.text()).toContain('巩固中 1')
    expect(wrapper.text()).toContain('已掌握 1')
    expect(wrapper.text()).toContain('事务隔离')
    expect(wrapper.text()).toContain('before×0.70+score×0.30')
    expect(wrapper.text()).toContain('2 次 · 1 错题')
    expect(wrapper.findAll('.distribution-bar i')).toHaveLength(3)
  })

  it('shows explicit empty and generating states without synthetic metrics', async () => {
    learningApi.getCourseWorkspaceOverview.mockResolvedValue({
      code: 200,
      data: {
        progress: { session_completed: 0, session_total: 0, knowledge_points: [], weak_points: [], recent_changes: [] },
        practice: { attempts: 0, wrong: 0 },
        plan: null,
        roadmap: { status: 'generating', stages: [] },
        today: null
      }
    })

    const wrapper = mount(OverviewPanel, { props: { courseId: 8 } })
    await flushPromises()

    expect(wrapper.text()).toContain('正在根据课程目标生成路线')
    expect(wrapper.text()).toContain('完成诊断后会显示真实知识点分布')
    expect(wrapper.text()).toContain('完成练习评估后会显示真实掌握度变化')
    expect(wrapper.text()).toContain('今日学习无任务')
  })
})
