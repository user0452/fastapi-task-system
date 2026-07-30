import { beforeEach, describe, expect, it, vi } from 'vitest'


const http = vi.hoisted(() => ({ request: vi.fn() }))

vi.mock('./http', () => ({ request: http.request }))

import { getTodayOverview } from './learning'


describe('getTodayOverview', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends the selected available-minute budget', () => {
    getTodayOverview(60)

    expect(http.request).toHaveBeenCalledWith(
      '/api/v1/study/today-overview?available_minutes=60'
    )
  })

  it('uses the backend default budget used by the Today UI', () => {
    getTodayOverview()

    expect(http.request).toHaveBeenCalledWith(
      '/api/v1/study/today-overview?available_minutes=90'
    )
  })
})
