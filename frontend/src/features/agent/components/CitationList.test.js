import { describe, expect, it } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import CitationList from './CitationList.vue'


const citations = [
  {
    chunk_id: 21,
    material_id: 9,
    material_title: '边界值讲义',
    page_number: 3,
    chunk_index: 1,
    score: 0.91,
    snippet: '边界及其相邻值最容易出现缺陷。'
  },
  {
    chunk_id: 22,
    material_id: 9,
    material_title: '边界值讲义',
    page_number: null,
    chunk_index: 2,
    score: 0.8,
    snippet: '还需要覆盖刚好越界的输入。'
  }
]


describe('CitationList', () => {
  it('renders every source with score and snippet', () => {
    const wrapper = mount(CitationList, {
      props: { citations },
      global: { stubs: { RouterLink: RouterLinkStub } }
    })

    expect(wrapper.findAll('.citation-row')).toHaveLength(2)
    expect(wrapper.text()).toContain('匹配 91%')
    expect(wrapper.text()).toContain('边界及其相邻值最容易出现缺陷')
  })

  it('links a citation back to its material and chunk', () => {
    const wrapper = mount(CitationList, {
      props: { citations: [citations[0]] },
      global: { stubs: { RouterLink: RouterLinkStub } }
    })

    expect(wrapper.findComponent(RouterLinkStub).props('to')).toEqual({
      path: '/courses',
      query: { tab: 'materials', material_id: 9, chunk: 21 }
    })
  })
})
