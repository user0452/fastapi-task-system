import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const materialApi = vi.hoisted(() => ({ getKnowledgeGraph: vi.fn() }))
const learningApi = vi.hoisted(() => ({ getCourseProgress: vi.fn() }))

vi.mock('../../../api/materials', () => materialApi)
vi.mock('../../../api/learning', () => learningApi)
vi.mock('../components/KnowledgeGraphCanvas.vue', () => ({
  __esModule: true,
  __isTeleport: false,
  __isKeepAlive: false,
  __isSuspense: false,
  default: {
    props: ['points', 'relations', 'selectedId', 'showLabels'],
    emits: ['select'],
    template: '<button class="mock-graph" @click="$emit(\'select\', points[1]?.id || points[0]?.id)">{{ points.length }} / {{ relations.length }}</button>'
  }
}))

import KnowledgePanel from './KnowledgePanel.vue'


const graph = {
  points: [
    {
      id: 1,
      name: '等价类划分',
      summary: '将输入域划分为代表性集合',
      category: '测试设计',
      knowledge_level: 'concept',
      evidence: [{ chunk_id: 11, chunk_index: 0, material_title: '测试讲义', snippet: '等价类用于减少重复测试。' }]
    },
    {
      id: 2,
      name: '边界值分析',
      summary: '检查边界及其附近值',
      category: '测试设计',
      knowledge_level: 'method',
      evidence: [{ chunk_id: 12, chunk_index: 1, material_title: '测试讲义', snippet: '边界是缺陷高发位置。' }]
    },
    {
      id: 3,
      name: '决策表',
      summary: '组合多个条件',
      category: '组合分析',
      knowledge_level: 'method',
      evidence: []
    }
  ],
  relations: [{
    id: 21,
    source_point_id: 1,
    target_point_id: 2,
    source_name: '等价类划分',
    target_name: '边界值分析',
    relation_type: 'prerequisite',
    confidence: 0.9
  }]
}

describe('KnowledgePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    materialApi.getKnowledgeGraph.mockResolvedValue({ code: 200, data: graph })
    learningApi.getCourseProgress.mockResolvedValue({
      code: 200,
      data: { knowledge_points: [{ id: 1, mastery: 85 }, { id: 2, mastery: 55 }] }
    })
  })

  it('renders only real API nodes, filters them, and exposes evidence and chat actions', async () => {
    const wrapper = mount(KnowledgePanel, { props: { courseId: 8 } })
    await flushPromises()

    expect(wrapper.text()).toContain('3 个节点 · 1 条关系')
    expect(wrapper.text()).toContain('等价类用于减少重复测试')
    expect(wrapper.get('.mock-graph').text()).toBe('3 / 1')

    await wrapper.get('.mock-graph').trigger('click')
    expect(wrapper.text()).toContain('边界是缺陷高发位置')
    await wrapper.get('.detail-actions button').trigger('click')
    expect(wrapper.emitted('prompt')[0][0]).toContain('边界值分析')

    await wrapper.get('.search-field input').setValue('决策表')
    expect(wrapper.get('.mock-graph').text()).toBe('1 / 0')
    await wrapper.get('.graph-summary button').trigger('click')
    expect(wrapper.findAll('.knowledge-list article')).toHaveLength(1)
    expect(wrapper.text()).toContain('决策表')
  })

  it('keeps an explicit empty state instead of inventing demo nodes', async () => {
    materialApi.getKnowledgeGraph.mockResolvedValue({ code: 200, data: { points: [], relations: [] } })
    learningApi.getCourseProgress.mockResolvedValue({ code: 200, data: { knowledge_points: [] } })
    const wrapper = mount(KnowledgePanel, { props: { courseId: 9 } })
    await flushPromises()

    expect(wrapper.text()).toContain('还没有知识点')
    expect(wrapper.text()).toContain('不会显示演示节点')
    expect(wrapper.find('.mock-graph').exists()).toBe(false)
  })
})
