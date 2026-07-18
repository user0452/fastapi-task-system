import { describe, expect, it } from 'vitest'
import { postLoginRouteFromHash, safePostLoginRoute } from './redirect'


describe('safePostLoginRoute', () => {
  it('restores a valid course panel and citation location', () => {
    expect(safePostLoginRoute('/learn/42?panel=materials&material_id=8&chunk=13')).toBe(
      '/learn/42?panel=materials&material_id=8&chunk=13'
    )
  })

  it('restores the active session and every current workspace panel', () => {
    for (const panel of ['overview', 'today', 'diagnostic', 'knowledge', 'plan', 'practice', 'wrong', 'memory', 'materials']) {
      expect(safePostLoginRoute(`/learn/42?session=17&panel=${panel}`)).toBe(
        `/learn/42?panel=${panel}&session=17`
      )
    }
  })

  it('drops unknown parameters and invalid panels', () => {
    expect(safePostLoginRoute('/learn/42?panel=admin&next=https://example.com')).toBe('/learn/42')
  })

  it.each(['https://example.com', '//example.com', '/learn/not-a-number', '/settings', ''])(
    'rejects unsafe redirect %s',
    value => expect(safePostLoginRoute(value)).toBe('')
  )
})


describe('postLoginRouteFromHash', () => {
  it('keeps the original course route across repeated 401 redirects', () => {
    const route = '/learn/42?panel=practice'
    expect(postLoginRouteFromHash(`#${route}`)).toBe(route)
    expect(postLoginRouteFromHash(`#/login?redirect=${encodeURIComponent(route)}`)).toBe(route)
  })

  it('does not recover an unsafe redirect from the login route', () => {
    expect(postLoginRouteFromHash('#/login?redirect=https%3A%2F%2Fexample.com')).toBe('')
  })
})
