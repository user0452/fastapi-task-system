import { describe, expect, it } from 'vitest'
import { postLoginRouteFromHash, safePostLoginRoute } from './redirect'


describe('safePostLoginRoute', () => {
  it('restores one of the three Adaptive Tutor areas', () => {
    expect(safePostLoginRoute('/learn/42?view=sources&material_id=8&chunk=13')).toBe(
      '/learn/42?view=sources&material_id=8&chunk=13'
    )
  })

  it('maps old bookmarks to a core area without restoring retired panels', () => {
    expect(safePostLoginRoute('/learn/42?panel=plan')).toBe('/learn/42?view=learn')
    expect(safePostLoginRoute('/learn/42?panel=memory')).toBe('/learn/42?view=learn')
  })

  it('drops unknown parameters and invalid views', () => {
    expect(safePostLoginRoute('/learn/42?view=admin&next=https://example.com')).toBe('/learn/42')
  })

  it.each(['https://example.com', '//example.com', '/learn/not-a-number', '/settings', ''])(
    'rejects unsafe redirect %s',
    value => expect(safePostLoginRoute(value)).toBe('')
  )
})


describe('postLoginRouteFromHash', () => {
  it('keeps the core course route across repeated 401 redirects', () => {
    const route = '/learn/42?view=progress'
    expect(postLoginRouteFromHash(`#${route}`)).toBe(route)
    expect(postLoginRouteFromHash(`#/login?redirect=${encodeURIComponent(route)}`)).toBe(route)
  })

  it('does not recover an unsafe redirect from the login route', () => {
    expect(postLoginRouteFromHash('#/login?redirect=https%3A%2F%2Fexample.com')).toBe('')
  })
})
