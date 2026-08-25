import { describe, expect, it } from 'vitest'
import { renderSafeMarkdown } from './markdown'


describe('renderSafeMarkdown', () => {
  it('renders tutor headings, lists, emphasis, and fenced code', () => {
    const html = renderSafeMarkdown('## 判断步骤\n\n**先看状态。**\n\n- Java 17\n- Maven\n\n```xml\n<parent>demo</parent>\n```')

    expect(html).toContain('<h2>判断步骤</h2>')
    expect(html).toContain('<strong>先看状态。</strong>')
    expect(html).toContain('<ul>')
    expect(html).toContain('<code class="language-xml">')
  })

  it('removes unsafe HTML before it reaches v-html', () => {
    const html = renderSafeMarkdown('正常内容 <img src=x onerror="alert(1)"><script>alert(1)</script>')

    expect(html).toContain('正常内容')
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('<script')
  })
})
