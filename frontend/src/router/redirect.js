const LEGACY_PANEL_TO_VIEW = {
  overview: 'progress',
  progress: 'progress',
  materials: 'sources',
  resources: 'sources',
  plan: 'learn',
  practice: 'learn',
  today: 'learn',
  diagnostic: 'learn',
  knowledge: 'progress',
  wrong: 'progress',
  memory: 'learn'
}


export function safePostLoginRoute(value) {
  if (value === '/today') return '/today'
  if (typeof value !== 'string') return ''
  const match = value.match(/^\/learn\/([1-9]\d*)(?:\?([^#]*))?$/)
  if (!match) return ''

  const result = new URLSearchParams()
  const incoming = new URLSearchParams(match[2] || '')
  const view = incoming.get('view') || LEGACY_PANEL_TO_VIEW[incoming.get('panel')]
  if (['learn', 'progress', 'sources'].includes(view)) result.set('view', view)
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
