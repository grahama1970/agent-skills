export type EmbryProjectionAnnotation = {
  id: string
  mention: string
  start: number
  end: number
  kind: string
  grounded: boolean
  source: string
  extraction_event_id: string
  extraction_result_sha256: string
}

export type EmbryProjectionTraceStep = {
  id: string
  event_id: string
  sequence: number
  event_type: string
  label: string
  status: 'completed'
  detail: string
  created_at: string
  receipt_hash: string
}

export type EmbryProjectionAudio = {
  artifact_id: string
  state: 'audio_ready'
  url: string
  sha256: string
  bytes: number
  content_type: string
  channels: number
  sample_rate_hz: number
  duration_ms: number
  playback_enabled: false
}

export type EmbryProjectionMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  content_sha256: string
  created_at: string
  annotations: EmbryProjectionAnnotation[]
  reasoning_steps?: EmbryProjectionTraceStep[]
  audio_artifacts?: EmbryProjectionAudio[]
  provenance: Record<string, unknown>
}

export type EmbryChatProjectionV1 = {
  schema: 'embry.chat_projection.v1'
  live: true
  mocked: false
  projection_only: true
  session_id: string
  turn_id: string
  source_event_id: string
  source_sequence: number
  journal: { through_sequence: number; event_count: number; sha256: string }
  messages: EmbryProjectionMessage[]
  hashes: Record<string, string>
  projection_sha256: string
}

export interface JournalProjectionSource {
  load(input: { sessionId: string; turnId: string; signal?: AbortSignal }): Promise<EmbryChatProjectionV1>
}

export function createJournalProjectionSource(baseUrl = '/api/projects/embry'): JournalProjectionSource {
  return {
    async load({ sessionId, turnId, signal }) {
      const response = await fetch(`${baseUrl}/sessions/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(turnId)}/chat-projection`, { signal })
      if (!response.ok) throw new Error(`journal_projection_http_${response.status}`)
      const projection = await response.json() as EmbryChatProjectionV1
      if (projection.schema !== 'embry.chat_projection.v1' || projection.session_id !== sessionId || projection.turn_id !== turnId || !projection.projection_only || projection.mocked) {
        throw new Error('journal_projection_contract_invalid')
      }
      return projection
    },
  }
}
