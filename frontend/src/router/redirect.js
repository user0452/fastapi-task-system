const VALID_PANELS = new Set(['overview', 'knowledge', 'plan', 'practice', 'wrong', 'materials'])


export function safePostLoginRoute(value) {
  if (value === '/today') return '/today'
  if (typeof value !== 'string') return ''
  const match = value.match(/^\/learn\/([1-9]\d*)(?:\?([^#]*))?$/)
  if (!match) return ''

  const result = new URLSearchParams()
  const incoming = new URLSearchParams(match[2] || '')
  const panel = incoming.get('panel')
  if (VALID_PANELS.has(panel)) result.set('panel', panel)
  for (const key of ['material_id', 'chunk']) {
    const field = incoming.get(key)
    if (field && /^\d+$/.test(field)) result.set(key, field)
  }
  const query = result.toString()
  return `/learn/${match[1]}${query ? `?${query}` : ''}`
}


export function postLoginRouteFromHash(value) {
  const current = typeof value === 'string' ? value.replace(/^#/, '') : ''
  const direct = safePostLoginRoute(current)
  if (direct) return direct

  const loginMatch = current.match(/^\/login(?:\?([^#]*))?$/)
  if (!loginMatch) return ''
  const saved = new URLSearchParams(loginMatch[1] || '').get('redirect')
  return safePostLoginRoute(saved)
}
