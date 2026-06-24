import type {
  ChatMessage,
  MemoryTurnAdapter,
  MemoryTurnStream,
  StreamingStep,
  UnknownRecord,
} from './MemoryTurnAdapter'

import {
  errorToMessage,
  extractContentFromUnknown,
  makeFinalMessage,
  makeFinalStep,
  makeStep,
  normalizeTurnText,
  streamingStepsToThinkingTrace,
} from './MemoryTurnAdapter'

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export interface WatchSceneRow {
  id?: string
  rowIndex?: number
  timecode?: string
  start?: string
  end?: string
  description?: string
  text?: string
  [key: string]: unknown
}

export type WatchChatAdapterProps = {
  projectLabel?: 'Watch'
  reportPath: string
  answerModel: string
  sceneContext?: { timecode?: string; rowIndex?: number; movieTitle?: string; movieSegment?: string }
  onMatchedRows?: (rows: WatchSceneRow[]) => void
  onAnnotationTab?: () => void
}

export interface WatchChatAdapterOptions extends WatchChatAdapterProps {
  baseUrl?: string
  fetch?: FetchLike
  endpoint?: string
  onError?: (error: unknown, input: unknown) => void
}

const WATCH_PENDING_STEPS: Array<{
  id: 'extracting-entities' | 'looking-in-memory' | 'finalizing-intent' | 'getting-results' | 'answering'
  label: string
  liveStatusLabel: string
}> = [
  { id: 'extracting-entities', label: 'Extracting scene entities', liveStatusLabel: 'Extracting scene entities…' },
  { id: 'looking-in-memory', label: 'Looking in Watch memory', liveStatusLabel: 'Looking in Watch memory…' },
  { id: 'finalizing-intent', label: 'Finalizing scene intent', liveStatusLabel: 'Finalizing scene intent…' },
  { id: 'getting-results', label: 'Getting scene results', liveStatusLabel: 'Getting scene results…' },
  { id: 'answering', label: 'Answering from scene evidence', liveStatusLabel: 'Answering from scene evidence…' },
]

export class WatchChatAdapter implements MemoryTurnAdapter {
  readonly name = 'WatchChatAdapter'
  readonly branch = 'watch' as const

  private readonly baseUrl: string
  private readonly endpoint: string
  private readonly fetchImpl: FetchLike
  private readonly props: WatchChatAdapterProps
  private readonly onError?: WatchChatAdapterOptions['onError']
  private abortController: AbortController | undefined

  constructor(options: WatchChatAdapterOptions) {
    this.baseUrl = options.baseUrl ?? ''
    this.endpoint = options.endpoint ?? '/api/projects/watch/question'
    this.fetchImpl = options.fetch ?? fetch.bind(globalThis)
    this.props = {
      projectLabel: options.projectLabel ?? 'Watch',
      reportPath: options.reportPath,
      answerModel: options.answerModel,
      sceneContext: options.sceneContext,
      onMatchedRows: options.onMatchedRows,
      onAnnotationTab: options.onAnnotationTab,
    }
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
          branch: 'watch',
          content: 'Ask a question about the current Watch report or scene.',
          metadata: { emptyTurn: true, qid: 'watch:chat:adapter:send' },
        })
        yield makeFinalStep(message, 'watch')
        return message
      }

      if (this.props.sceneContext) {
        yield pushStep(emittedSteps, {
          id: 'watch-scene-context',
          branch: 'watch',
          status: 'completed',
          liveStatusLabel: 'Reading scene context…',
          detail: sceneContextLabel(this.props.sceneContext),
          data: this.props.sceneContext,
        })
      } else {
        yield pushStep(emittedSteps, {
          id: 'watch-scene-context',
          branch: 'watch',
          status: 'skipped',
          detail: 'No scene row selected',
        })
      }

      for (const step of WATCH_PENDING_STEPS) {
        yield pushStep(emittedSteps, {
          id: step.id,
          label: step.label,
          branch: 'watch',
          status: step.id === 'extracting-entities' ? 'running' : 'pending',
          liveStatusLabel: step.liveStatusLabel,
        })
      }

      const packet = await this.postQuestion(question, signal, input.context)
      const reasoningSteps = normalizeReasoningSteps(packet)
      const matchedRows = extractMatchedRows(packet)
      if (matchedRows.length) this.props.onMatchedRows?.(matchedRows)
      if (shouldOpenAnnotationTab(packet)) this.props.onAnnotationTab?.()

      for (const step of WATCH_PENDING_STEPS) {
        yield pushStep(emittedSteps, {
          id: step.id,
          label: step.label,
          branch: 'watch',
          status: 'completed',
          detail: reasoningSteps[step.id],
          data: reasonDataForStep(packet, step.id),
        })
      }

      const content = extractContentFromUnknown(packet) || 'Watch returned no answer for this question.'
      const message = makeFinalMessage({
        branch: 'watch',
        content,
        reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
        metadata: {
          qid: 'watch:chat:adapter:send',
          projectLabel: this.props.projectLabel ?? 'Watch',
          reportPath: this.props.reportPath,
          answerModel: this.props.answerModel,
          sceneContext: this.props.sceneContext,
          answerPacket: packet,
          matchedRows,
        },
      })
      yield makeFinalStep(message, 'watch')
      return message
    } catch (error) {
      this.onError?.(error, input)
      yield pushStep(emittedSteps, {
        id: 'answering',
        branch: 'watch',
        status: 'failed',
        error: errorToMessage(error),
        liveStatusLabel: 'Watch ask failed',
      })
      const message = makeFinalMessage({
        branch: 'watch',
        content: `Watch could not answer this turn: ${errorToMessage(error)}`,
        reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
        metadata: { error: errorToMessage(error), qid: 'watch:chat:adapter:send' },
      })
      yield makeFinalStep(message, 'watch')
      return message
    }
  }

  private async postQuestion(question: string, signal?: AbortSignal, context?: UnknownRecord): Promise<UnknownRecord> {
    const response = await this.fetchImpl(joinUrl(this.baseUrl, this.endpoint), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        report_path: this.props.reportPath,
        answer_model: this.props.answerModel,
        scene_context: this.props.sceneContext,
        context,
      }),
      signal,
    })
    if (!response.ok) {
      throw new Error(`${this.endpoint} failed with HTTP ${response.status}`)
    }
    const text = await response.text()
    if (!text.trim()) return {}
    try {
      return JSON.parse(text) as UnknownRecord
    } catch {
      return { answer: text }
    }
  }
}

function pushStep(
  emittedSteps: StreamingStep[],
  args: Parameters<typeof makeStep>[0],
): StreamingStep {
  const step = makeStep(args)
  emittedSteps.push(step)
  return step
}

function joinUrl(baseUrl: string, path: string): string {
  if (/^https?:\/\//i.test(path)) return path
  if (!baseUrl) return path
  return `${baseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`
}

function sceneContextLabel(sceneContext: NonNullable<WatchChatAdapterProps['sceneContext']>): string {
  const parts = [sceneContext.movieTitle, sceneContext.movieSegment, sceneContext.timecode]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
  if (typeof sceneContext.rowIndex === 'number') parts.push(`row ${sceneContext.rowIndex}`)
  return parts.length ? parts.join(' · ') : 'Scene context attached'
}

function normalizeReasoningSteps(packet: UnknownRecord): Record<string, string> {
  const raw = packet.reasoningSteps ?? packet.reasoning_steps ?? packet.steps ?? packet.trace
  const normalized: Record<string, string> = {}
  if (Array.isArray(raw)) {
    for (const step of raw) {
      if (!step || typeof step !== 'object') continue
      const record = step as UnknownRecord
      const id = typeof record.id === 'string' ? record.id : typeof record.step === 'string' ? record.step : undefined
      const detail = typeof record.detail === 'string'
        ? record.detail
        : typeof record.label === 'string'
          ? record.label
          : typeof record.message === 'string'
            ? record.message
            : undefined
      if (id && detail) normalized[id] = detail
    }
  } else if (raw && typeof raw === 'object') {
    for (const [key, value] of Object.entries(raw as UnknownRecord)) {
      if (typeof value === 'string') normalized[key] = value
    }
  }
  return normalized
}

function extractMatchedRows(packet: UnknownRecord): WatchSceneRow[] {
  const candidates = [
    packet.matchedRows,
    packet.matched_rows,
    packet.rows,
    packet.sceneRows,
    packet.scene_rows,
    nested(packet, 'answerPacket', 'matchedRows'),
    nested(packet, 'packet', 'matched_rows'),
  ]
  for (const candidate of candidates) {
    if (Array.isArray(candidate)) return candidate.filter(isWatchSceneRow)
  }
  return []
}

function isWatchSceneRow(value: unknown): value is WatchSceneRow {
  return Boolean(value && typeof value === 'object')
}

function nested(record: UnknownRecord, first: string, second: string): unknown {
  const value = record[first]
  if (!value || typeof value !== 'object') return undefined
  return (value as UnknownRecord)[second]
}

function shouldOpenAnnotationTab(packet: UnknownRecord): boolean {
  return packet.openAnnotationTab === true || packet.open_annotation_tab === true || packet.annotationTab === true
}

function reasonDataForStep(packet: UnknownRecord, stepId: string): unknown {
  const reasonData = packet.reasoningData ?? packet.reasoning_data
  if (reasonData && typeof reasonData === 'object') {
    return (reasonData as UnknownRecord)[stepId]
  }
  return undefined
}
