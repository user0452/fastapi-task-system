import DOMPurify from 'dompurify'
import { marked } from 'marked'


const INTERNAL_SOURCE_MARKER = /[ \t]*\[chunk_id\s*=\s*\d+\]/gi
const DECORATIVE_SYMBOLS = /(?:⭐|🌟|✨|✅|⚠️?|📌|😊|🙂)/gu
const ALLOWED_TAGS = [
  'h1', 'h2', 'h3', 'h4', 'p', 'br', 'strong', 'em', 'del',
  'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'hr',
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a'
]

export function normalizeAssistantMarkdown(content) {
  return String(content || '')
    .replace(INTERNAL_SOURCE_MARKER, '')
    .replace(DECORATIVE_SYMBOLS, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function renderAssistantMarkdown(content) {
  const normalized = normalizeAssistantMarkdown(content)
  if (!normalized) return ''
  const html = marked.parse(normalized, {
    async: false,
    breaks: false,
    gfm: true
  })
  const sanitized = DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: ['href', 'title'],
    ALLOW_UNKNOWN_PROTOCOLS: false
  })
  return sanitized.replace(
    /<pre><code>([\s\S]*?)<\/code><\/pre>/g,
    '<div class="code-block"><button type="button" class="code-copy-button">复制</button><pre><code>$1</code></pre></div>'
  )
}
