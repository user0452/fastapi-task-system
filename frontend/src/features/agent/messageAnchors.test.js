import { describe, expect, it } from 'vitest'
import { createMessageAnchors, createMessageAnchorTitle } from './messageAnchors'


describe('message anchor titles', () => {
  it('uses only user messages and creates stable id based items', () => {
    expect(createMessageAnchors([
      { id: 7, role: 'user', content: '## 第一段 **重点**\n继续说明\n\n第二段' },
      { id: 8, role: 'assistant', content: '回答' },
      { id: 9, role: 'user', content: '第二个问题' }
    ])).toEqual([
      {
        id: 7,
        title: '第一段 重点 继续说明',
        preview: '第一段 重点 继续说明'
      },
      {
        id: 9,
        title: '第二个问题',
        preview: '第二个问题'
      }
    ])
  })

  it('compresses whitespace, removes markdown and truncates locally', () => {
    const title = createMessageAnchorTitle({
      content: '请阅读 [课程资料](https://example.com) 并解释这个非常非常非常非常非常非常长的问题'
    }, 20)

    expect(title).toBe('请阅读 课程资料 并解释这个非常非常非常…')
  })

  it('provides useful fallbacks for non text messages', () => {
    expect(createMessageAnchorTitle({ content: '', images: [{ id: 1 }] })).toBe('发送了一张图片')
    expect(createMessageAnchorTitle({ content: '', attachments: [{ type: 'application/pdf' }] })).toBe('上传了一个文件')
    expect(createMessageAnchorTitle({ content: '' })).toBe('发送了一条消息')
  })
})
