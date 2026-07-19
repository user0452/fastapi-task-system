import { beforeEach, describe, expect, it, vi } from 'vitest'
import { request } from './http'
import { updateMemorySettings } from './profiles'

vi.mock('./http', () => ({ request: vi.fn() }))

describe('profiles API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('serializes memory settings as JSON', () => {
    const payload = {
      learning_memory_enabled: true,
      sensitive_memory_enabled: false
    }

    updateMemorySettings(payload)

    expect(request).toHaveBeenCalledWith('/api/v1/account/memory-settings', {
      method: 'PATCH',
      body: JSON.stringify(payload)
    })
  })
})
