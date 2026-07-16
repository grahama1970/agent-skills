import type { UnknownRecord } from './MemoryTurnAdapter'

export interface EmbryVoiceAudioAuthority {
  authority?: string
  artifactId?: string
  url?: string
  path?: string
  sha256?: string
  durationMs?: number
  localPlayback?: UnknownRecord | null
  envelope?: UnknownRecord
}

export interface EmbryTurnAuthority {
  turnId: string
  userText: string
  assistantText: string
  personaId: string
  speakerId?: string
  sessionId?: string
  createdAt: string
  memoryFirst: true
  simultaneousTextVoice: true
  receiptPath?: string
  audioAuthority?: EmbryVoiceAudioAuthority
  audioArtifacts: UnknownRecord[]
  memoryTrace?: unknown
  tauTrace?: unknown
  live?: boolean
  mocked?: boolean
}
