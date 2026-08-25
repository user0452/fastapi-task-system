import DOMPurify from 'dompurify'
import { marked } from 'marked'


export function renderSafeMarkdown(value) {
  const source = String(value || '').trim()
  if (!source) return ''
  const html = marked.parse(source, {
    async: false,
    breaks: true,
    gfm: true
  })
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true }
  })
}
