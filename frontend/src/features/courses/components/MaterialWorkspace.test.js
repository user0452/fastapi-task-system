import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import MaterialWorkspace from './MaterialWorkspace.vue'
import { deleteCourseMaterial, getCourseMaterials } from '../../../api/materials'


vi.mock('../../../api/materials', () => ({
  createCourseTextMaterial: vi.fn(),
  deleteCourseMaterial: vi.fn(),
  getCourseMaterials: vi.fn(),
  retryCourseMaterial: vi.fn(),
  uploadCourseMaterial: vi.fn()
}))

vi.mock('../../../components/common/toast', () => ({ showToast: vi.fn() }))

describe('MaterialWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getCourseMaterials.mockResolvedValue({
      code: 200,
      data: {
        items: [{
          id: 18,
          title: 'Hadoop 复习资料',
          filename: 'hadoop.pdf',
          created_at: '2026-07-15T12:34:00',
          content_preview: 'HDFS 与 MapReduce',
          processing_status: 'ready'
        }]
      }
    })
  })

  it('shows creation time and deletes a confirmed material', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    deleteCourseMaterial.mockResolvedValue({ code: 200, data: { deleted: true } })
    const wrapper = mount(MaterialWorkspace, { props: { courseId: 24 } })
    await flushPromises()

    expect(wrapper.text()).toContain('创建于')
    expect(wrapper.text()).toContain('2026')
    const processedBeforeDelete = wrapper.emitted('processed')?.length || 0
    await wrapper.get('.delete-button').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledOnce()
    expect(deleteCourseMaterial).toHaveBeenCalledWith(18)
    expect(wrapper.text()).not.toContain('Hadoop 复习资料')
    expect(wrapper.emitted('processed')).toHaveLength(processedBeforeDelete + 1)
    confirm.mockRestore()
  })
})
