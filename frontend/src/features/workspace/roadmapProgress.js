function clamp(value) {
  return Math.max(0, Math.min(Number(value) || 0, 100))
}


export function calculateRoadmapProgress(roadmap) {
  if (Number.isFinite(Number(roadmap?.overall_progress))) {
    return Math.round(clamp(roadmap.overall_progress))
  }
  const stages = roadmap?.stages || []
  if (!stages.length) return 0
  const minutesPerDay = Math.max(1, Number(roadmap?.daily_minutes) || 30)
  const weighted = stages.map(stage => {
    const sessionMinutes = (stage.daily_sessions || []).reduce(
      (sum, session) => sum + Math.max(0, Number(session.estimated_minutes) || 0),
      0
    )
    return {
      progress: clamp(stage.progress),
      weight: sessionMinutes || Math.max(0, Number(stage.estimated_days) || 0) * minutesPerDay
    }
  })
  const totalWeight = weighted.reduce((sum, stage) => sum + stage.weight, 0)
  if (!totalWeight) {
    return Math.round(weighted.reduce((sum, stage) => sum + stage.progress, 0) / stages.length)
  }
  return Math.round(
    weighted.reduce((sum, stage) => sum + stage.progress * stage.weight, 0) / totalWeight
  )
}
