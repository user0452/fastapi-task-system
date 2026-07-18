const MARKDOWN_IMAGES = /!\[([^\]]*)\]\([^)]*\)/g
const MARKDOWN_LINKS = /\[([^\]]+)\]\([^)]*\)/g
const MARKDOWN_DECORATION = /(^|\s)(#{1,6}|>|[-+*]|\d+\.)\s+|[`*_~]/g

function attachmentKind(message) {
  const attachments = [
    ...(Array.isArray(message?.attachments) ? message.attachments : []),
    ...(Array.isArray(message?.files) ? message.files : [])
  ]
  if (message?.image_url || message?.images?.length || attachments.some(item => String(item?.type || item?.mime_type || '').startsWith('image'))) {
    return 'image'
  }
  if (attachments.length || message?.file) return 'file'
  return ''
}

function cleanedMessageText(message) {
  const content = String(message?.content || '')
  const firstParagraph = content.split(/\n\s*\n/)[0] || ''
  return firstParagraph
    .replace(MARKDOWN_IMAGES, '$1')
    .replace(MARKDOWN_LINKS, '$1')
    .replace(MARKDOWN_DECORATION, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

function fallbackTitle(message) {
  const kind = attachmentKind(message)
  if (kind === 'image') return '发送了一张图片'
  if (kind === 'file') return '上传了一个文件'
  return '发送了一条消息'
}

function truncateText(text, maxLength) {
  const characters = Array.from(text)
  return characters.length > maxLength
    ? `${characters.slice(0, maxLength).join('')}…`
    : text
}

export function createMessageAnchorTitle(message, maxLength = 28) {
  const cleaned = cleanedMessageText(message)
  if (cleaned) return truncateText(cleaned, maxLength)
  return fallbackTitle(message)
}

export function createMessageAnchorPreview(message, maxLength = 72) {
  const cleaned = cleanedMessageText(message)
  if (cleaned) return truncateText(cleaned, maxLength)
  return fallbackTitle(message)
}

export function createMessageAnchors(messages) {
  return (messages || [])
    .filter(message => message?.role === 'user' && message?.id != null)
    .map(message => ({
      id: message.id,
      title: createMessageAnchorTitle(message),
      preview: createMessageAnchorPreview(message)
    }))
}
