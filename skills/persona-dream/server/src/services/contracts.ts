export interface DreamResearchResult {
  title: string
  url: string
  snippet: string
}

export interface DreamResearchResponse {
  status: 'ok'
  query: string
  results: DreamResearchResult[]
  total: number
}

export interface DreamResearchPort {
  search(query: string): Promise<DreamResearchResponse>
}

export interface VoiceAuditionRequest {
  character?: unknown
  text?: unknown
  refAudioPath?: unknown
  tone?: unknown
  paralinguisticCue?: unknown
  emotionTag?: unknown
  deliveryStage?: unknown
  pauseBeforeMs?: unknown
  pauseAfterMs?: unknown
  // Weighted-emotion inputs from persona-dream arc_state (operator model:
  // verdict -> emotion; intensity is a WEIGHT on the emotion). Optional; when
  // absent, defaults are derived from `tone`.
  intensity?: unknown
  valence?: unknown
}

export interface VoiceAuditionPort {
  audition(request: VoiceAuditionRequest): Promise<Record<string, unknown>>
}
