import { afterEach, describe, expect, it, vi } from 'vitest'
import { formatCurrentTimestampMinute, sendAgentMessageStream } from './agent'


function localTime(offsetMinutes) {
  return {
    getTimezoneOffset: () => -offsetMinutes,
    getFullYear: () => 2026,
    getMonth: () => 6,
    getDate: () => 12,
    getHours: () => 9,
    getMinutes: () => 7
  }
}

describe('formatCurrentTimestampMinute', () => {
  it('formats the local time to minute precision with a positive UTC offset', () => {
    expect(formatCurrentTimestampMinute(localTime(8 * 60))).toBe('2026-07-12 09:07 UTC+08:00')
  })

  it('preserves negative offsets including half-hour zones', () => {
    expect(formatCurrentTimestampMinute(localTime(-(5 * 60 + 30)))).toBe(
      '2026-07-12 09:07 UTC-05:30'
    )
  })
})

describe('sendAgentMessageStream', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('cancels and releases the reader when streaming is interrupted', async () => {
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    const reader = {
      read: vi.fn().mockRejectedValue(abortError),
      cancel: vi.fn().mockResolvedValue(undefined),
      releaseLock: vi.fn()
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: { getReader: () => reader }
    }))

    await expect(sendAgentMessageStream({ message: 'test' })).rejects.toMatchObject({
      name: 'AbortError'
    })

    expect(reader.cancel).toHaveBeenCalledOnce()
    expect(reader.releaseLock).toHaveBeenCalledOnce()
  })
})
