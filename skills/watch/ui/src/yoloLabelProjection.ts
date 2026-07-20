export type ProjectedYoloTrackLabel = {
  characterName: string
  actorName?: string
  confidence?: number
}

type ProjectionEvent = {
  sequence?: number
  action: string
  track_id: string
  time_seconds?: number | null
  character_name?: string
  actor_name?: string
  confidence?: number
  created_at?: string
}

function eventTimeSeconds(event: ProjectionEvent): number | null {
  return typeof event.time_seconds === 'number' && Number.isFinite(event.time_seconds)
    ? event.time_seconds
    : null
}

export function projectYoloTrackLabelAtTime(input: {
  trackId: string
  timeSeconds: number
  events: ProjectionEvent[]
  labels: Record<string, {
    characterName?: string
    actorName?: string
    confidence?: number
  }>
}): ProjectedYoloTrackLabel | null {
  const boundedTime = Number.isFinite(input.timeSeconds) ? Math.max(0, input.timeSeconds) : 0
  const trackEvents = input.events
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => event.track_id === input.trackId)

  const timedEvents = trackEvents
    .filter(({ event }) => eventTimeSeconds(event) != null)
    .filter(({ event }) => (eventTimeSeconds(event) ?? Number.POSITIVE_INFINITY) <= boundedTime)
    .sort((a, b) => {
      const timeA = eventTimeSeconds(a.event) ?? 0
      const timeB = eventTimeSeconds(b.event) ?? 0
      if (timeA !== timeB) return timeA - timeB
      const sequenceA = typeof a.event.sequence === 'number' ? a.event.sequence : null
      const sequenceB = typeof b.event.sequence === 'number' ? b.event.sequence : null
      if (sequenceA != null && sequenceB != null) return sequenceA - sequenceB
      if (sequenceA != null) return -1
      if (sequenceB != null) return 1
      return a.index - b.index
    })

  let current: ProjectedYoloTrackLabel | null = null
  for (const { event } of timedEvents) {
    if (
      event.action === 'reject'
      || event.action === 'reset'
      || event.action === 'reject_box'
      || event.action === 'reset_box'
    ) {
      current = null
      continue
    }
    if (event.action === 'accept' && event.character_name && event.character_name !== 'Unassigned') {
      current = {
        characterName: event.character_name,
        actorName: event.actor_name || undefined,
        confidence: typeof event.confidence === 'number' ? event.confidence : undefined,
      }
    }
  }

  if (timedEvents.length > 0) return current
  const hasAnyTimedTrackEvent = trackEvents.some(({ event }) => eventTimeSeconds(event) != null)
  if (hasAnyTimedTrackEvent) return null

  const fallback = input.labels[input.trackId]
  return fallback?.characterName
    ? {
        characterName: fallback.characterName,
        actorName: fallback.actorName,
        confidence: fallback.confidence,
      }
    : null
}
