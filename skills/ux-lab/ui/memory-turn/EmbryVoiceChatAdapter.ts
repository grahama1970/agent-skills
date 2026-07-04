import {
  ChatMessage,
  MemoryTurnAdapter,
  MemoryTurnStream,
  StreamingStep,
  UnknownRecord,
  errorToMessage,
  extractContentFromUnknown,
  makeFinalMessage,
  makeFinalStep,
  makeStep,
  normalizeTurnText,
  streamingStepsToThinkingTrace,
} from './MemoryTurnAdapter'

export type EmbryVoiceFetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export interface EmbryVoiceChatAdapterOptions {
  baseUrl?: string
  endpoint?: string
  fetch?: EmbryVoiceFetchLike
  personaId?: string
  speakerId?: string
  sessionId?: string
  useBlessedQraCache?: boolean
  onError?: (error: unknown, input: unknown) => void
}

const EMBRY_VOICE_STEPS: Array<{
  id: string
  label: string
  liveStatusLabel: string
}> = [
  { id: 'speaker-resolve', label: 'Resolving speaker', liveStatusLabel: 'Resolving speaker…' },
  { id: 'memory-intent', label: 'Classifying memory intent', liveStatusLabel: 'Checking memory intent…' },
  { id: 'memory-recall', label: 'Looking in speaker memory', liveStatusLabel: 'Looking in memory…' },
  { id: 'tau-render-request', label: 'Preparing Tau voice request', liveStatusLabel: 'Preparing voice…' },
  { id: 'chatterbox-audio', label: 'Rendering Chatterbox audio', liveStatusLabel: 'Rendering voice…' },
]

export class EmbryVoiceChatAdapter implements MemoryTurnAdapter {
  readonly name = 'EmbryVoiceChatAdapter'
  readonly branch = 'personaplex' as const

  private readonly baseUrl: string
  private readonly endpoint: string
  private readonly fetchImpl: EmbryVoiceFetchLike
  private readonly personaId: string
  private readonly speakerId?: string
  private readonly sessionId?: string
  private readonly useBlessedQraCache: boolean
  private readonly onError?: EmbryVoiceChatAdapterOptions['onError']
  private abortController: AbortController | undefined

  constructor(options: EmbryVoiceChatAdapterOptions = {}) {
    this.baseUrl = options.baseUrl ?? ''
    this.endpoint = options.endpoint ?? '/api/projects/embry/voice-chat/turn'
    this.fetchImpl = options.fetch ?? fetch.bind(globalThis)
    this.personaId = options.personaId ?? 'embry'
    this.speakerId = options.speakerId
    this.sessionId = options.sessionId
    this.useBlessedQraCache = options.useBlessedQraCache ?? true
    this.onError = options.onError
  }

  cancel(): void {
    this.abortController?.abort()
  }

  async *sendTurn(input: { text: string; abortSignal?: AbortSignal; context?: UnknownRecord }): MemoryTurnStream {
    this.abortController = new AbortController()
    const signal = input.abortSignal ?? this.abortController.signal
    const question = normalizeTurnText({ text: input.text })
    const emittedSteps: StreamingStep[] = []

    try {
      if (!question) {
        const message = makeFinalMessage({
          branch: 'personaplex',
          content: 'Ask Embry a voice-chat turn.',
          metadata: { emptyTurn: true, qid: 'embry:voice-chat:adapter:send' },
        })
        yield makeFinalStep(message, 'personaplex')
        return message
      }

      for (const step of EMBRY_VOICE_STEPS) {
        yield pushStep(emittedSteps, {
          id: step.id,
          label: step.label,
          branch: 'personaplex',
          status: step.id === 'speaker-resolve' ? 'running' : 'pending',
          liveStatusLabel: step.liveStatusLabel,
        })
      }

      const packet = await this.postVoiceTurn(question, signal, input.context)
      const completedDetails = detailsFromPacket(packet)
      for (const step of EMBRY_VOICE_STEPS) {
        yield pushStep(emittedSteps, {
          id: step.id,
          label: step.label,
          branch: 'personaplex',
          status: 'completed',
          detail: completedDetails[step.id],
          data: dataForStep(packet, step.id),
        })
      }

      const content =
        extractContentFromUnknown(packet) ||
        extractContentFromUnknown(packet.final_response) ||
        'Embry returned a voice turn without display text.'

      const message = makeFinalMessage({
        branch: 'personaplex',
        content,
        idPrefix: 'embry-voice',
        skillUsed: 'embry-chatterbox-voice',
        reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
        metadata: {
          qid: 'embry:voice-chat:adapter:send',
          personaId: this.personaId,
          speakerId: this.speakerId,
          sessionId: this.sessionId,
          simultaneousTextVoice: true,
          answerPacket: packet,
          audioArtifacts: extractAudioArtifacts(packet),
          receiptPath: stringValue(packet.receipt_path ?? packet.receiptPath),
          memoryFirst: true,
        },
      })
      yield makeFinalStep(message, 'personaplex')
      return message
    } catch (error) {
      this.onError?.(error, input)
      yield pushStep(emittedSteps, {
        id: 'chatterbox-audio',
        branch: 'personaplex',
        status: 'failed',
        error: errorToMessage(error),
        liveStatusLabel: 'Embry voice turn failed',
      })
      const message = makeFinalMessage({
        branch: 'personaplex',
        content: `Embry could not complete that voice turn: ${errorToMessage(error)}`,
        reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
        metadata: { error: errorToMessage(error), qid: 'embry:voice-chat:adapter:send' },
      })
      yield makeFinalStep(message, 'personaplex')
      return message
    }
  }

  private async postVoiceTurn(question: string, signal?: AbortSignal, context?: UnknownRecord): Promise<UnknownRecord> {
    const response = await this.fetchImpl(joinUrl(this.baseUrl, this.endpoint), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        text: question,
        persona_id: this.personaId,
        speaker_id: this.speakerId,
        session_id: this.sessionId,
        use_blessed_qra_cache: this.useBlessedQraCache,
        require_memory_first: true,
        simultaneous_text_voice: true,
        context,
      }),
      signal,
    })
    if (!response.ok) throw new Error(`${this.endpoint} failed with HTTP ${response.status}`)
    const text = await response.text()
    if (!text.trim()) return {}
    try {
      return JSON.parse(text) as UnknownRecord
    } catch {
      return { answer: text }
    }
  }
}

function pushStep(emittedSteps: StreamingStep[], args: Parameters<typeof makeStep>[0]): StreamingStep {
  const step = makeStep(args)
  emittedSteps.push(step)
  return step
}

function joinUrl(baseUrl: string, path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  if (!baseUrl) return path
  return `${baseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`
}

function detailsFromPacket(packet: UnknownRecord): Record<string, string | undefined> {
  return {
    'speaker-resolve': statusDetail(packet.speaker_resolution ?? packet.speakerResolution, 'speaker'),
    'memory-intent': statusDetail(packet.intent ?? packet.memory_intent ?? packet.memoryIntent, 'intent'),
    'memory-recall': statusDetail(packet.recall ?? packet.memory_recall ?? packet.memoryRecall, 'recall'),
    'tau-render-request': statusDetail(packet.tau ?? packet.tau_voice_render ?? packet.tauVoiceRender, 'tau'),
    'chatterbox-audio': audioDetail(packet),
  }
}

function statusDetail(value: unknown, label: string): string | undefined {
  if (!value || typeof value !== 'object') return undefined
  const record = value as UnknownRecord
  const status = stringValue(record.status ?? record.action ?? record.route)
  const confidence = numberValue(record.confidence ?? record.score)
  const suffix = confidence === undefined ? '' : ` (${confidence.toFixed(3)})`
  return status ? `${label}: ${status}${suffix}` : undefined
}

function audioDetail(packet: UnknownRecord): string | undefined {
  const artifacts = extractAudioArtifacts(packet)
  if (artifacts.length) return `${artifacts.length} playable audio artifact${artifacts.length === 1 ? '' : 's'}`
  return statusDetail(packet.chatterbox ?? packet.audio ?? packet.voice, 'audio')
}

function dataForStep(packet: UnknownRecord, stepId: string): unknown {
  if (stepId === 'speaker-resolve') return packet.speaker_resolution ?? packet.speakerResolution
  if (stepId === 'memory-intent') return packet.intent ?? packet.memory_intent ?? packet.memoryIntent
  if (stepId === 'memory-recall') return packet.recall ?? packet.memory_recall ?? packet.memoryRecall
  if (stepId === 'tau-render-request') return packet.tau ?? packet.tau_voice_render ?? packet.tauVoiceRender
  if (stepId === 'chatterbox-audio') return { audioArtifacts: extractAudioArtifacts(packet) }
  return packet
}

function extractAudioArtifacts(packet: UnknownRecord): UnknownRecord[] {
  const candidates = [
    packet.audioArtifacts,
    packet.audio_artifacts,
    packet.audio,
    packet.wavs,
    nested(packet, 'chatterbox', 'audio_artifacts'),
    nested(packet, 'voice', 'audio_artifacts'),
    nested(packet, 'tau', 'audio_artifacts'),
  ]
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate.filter(isRecord)
    if (isRecord(candidate)) return [candidate]
  }
  return []
}

function nested(record: UnknownRecord, first: string, second: string): unknown {
  const value = record[first]
  if (!isRecord(value)) return undefined
  return value[second]
}

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value && typeof value === 'object')
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function numberValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}
