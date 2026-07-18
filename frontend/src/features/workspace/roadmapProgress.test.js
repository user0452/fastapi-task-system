import { describe, expect, it } from 'vitest'
import { calculateRoadmapProgress } from './roadmapProgress'


describe('calculateRoadmapProgress', () => {
  it('prefers the backend unified progress field and clamps it', () => {
    expect(calculateRoadmapProgress({ overall_progress: 63.6, stages: [] })).toBe(64)
    expect(calculateRoadmapProgress({ overall_progress: 130, stages: [] })).toBe(100)
  })

  it('weights real sessions by minutes and estimates remaining stages by duration', () => {
    expect(calculateRoadmapProgress({
      daily_minutes: 30,
      stages: [
        { progress: 100, estimated_days: 2, daily_sessions: [] },
        {
          progress: 50,
          estimated_days: 10,
          daily_sessions: [{ estimated_minutes: 120 }]
        }
      ]
    })).toBe(67)
  })

  it('falls back to the simple average only when duration data is missing', () => {
    expect(calculateRoadmapProgress({
      stages: [{ progress: -20 }, { progress: 140 }]
    })).toBe(50)
  })
})
