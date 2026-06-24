import type {
  ChatMessage,
  MemoryTurnAdapter,
  MemoryTurnStream,
  StreamingStep,
  StreamingStepId,
  TurnInput,
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

export interface PersonaPlexProtocolLike {
  sendTurn?: (args: PersonaPlexProtocolTurnArgs) => AsyncIterable<unknown> | Promise<unknown>
  streamTurn?: (args: PersonaPlexProtocolTurnArgs) => AsyncIterable<unknown> | Promise<unknown>
  ask?: (args: PersonaPlexProtocolTurnArgs) => AsyncIterable<unknown> | Promise<unknown>
}

export interface PersonaPlexProtocolTurnArgs {
  text: string
  query: string
  messages?: unknown[]
  context?: UnknownRecord
  nvisTokens?: UnknownRecord
  signal?: AbortSignal
}

export interface WebSocketLike {
  readyState: number
  send(data: string): void
  close(code?: number, reason?: string): void
  addEventListener(type: 'open' | 'message' | 'error' | 'close', listener: (event: Event | MessageEvent | CloseEvent) => void, options?: AddEventListenerOptions): void
  removeEventListener(type: 'open' | 'message' | 'error' | 'close', listener: (event: Event | MessageEvent | CloseEvent) => void): void
}

export interface PersonaPlexAdapterOptions {
  wsUrl?: string
  protocol?: PersonaPlexProtocolLike
  createSocket?: (url: string) => WebSocketLike
  personaId?: string
  surface?: string
  onError?: (error: unknown, input: TurnInput) => void
}

export class PersonaPlexAdapter implements MemoryTurnAdapter {
  readonly name = 'PersonaPlexAdapter'
  readonly branch = 'personaplex' as const

  private readonly wsUrl: string
  private readonly protocol?: PersonaPlexProtocolLike
  private readonly createSocket?: (url: string) => WebSocketLike
  private readonly personaId: string
  private readonly surface: string
  private readonly onError?: PersonaPlexAdapterOptions['onError']
  private activeSocket: WebSocketLike | undefined
  private abortController: AbortController | undefined

  constructor(options: PersonaPlexAdapterOptions = {}) {
    this.wsUrl = options.wsUrl ?? 'ws://127.0.0.1:8788/ws'
    this.protocol = options.protocol
    this.createSocket = options.createSocket
    this.personaId = options.personaId ?? 'embry'
    this.surface = options.surface ?? 'final-site/chat/personaplex'
    this.onError = options.onError
  }

  cancel(): void {
    this.abortController?.abort()
    this.activeSocket?.close(1000, 'turn cancelled')
  }

  async *sendTurn(input: TurnInput): MemoryTurnStream {
    this.abortController = new AbortController()
    const signal = input.abortSignal ?? this.abortController.signal
    const text = normalizeTurnText(input)
    const emittedSteps: StreamingStep[] = []
    const nvisTokens = extractNvisTokens(input)

    try {
      if (!text) {
        const message = makeFinalMessage({
          branch: 'personaplex',
          content: 'Ask PersonaPlex a question.',
          metadata: { emptyTurn: true, nvisTokens },
        })
        yield makeFinalStep(message, 'personaplex')
        return message
      }

      yield pushStep(emittedSteps, {
        id: 'connecting-personaplex',
        branch: 'personaplex',
        status: 'running',
        liveStatusLabel: 'Connecting to PersonaPlex…',
      })

      const stream = this.protocol ? await this.openProtocolStream(input, text, nvisTokens, signal) : undefined
      if (stream) {
        return yield* this.consumePersonaEvents(stream, text, nvisTokens, emittedSteps, 'personaplexProtocol')
      }

      return yield* this.consumePersonaEvents(
        this.openRawWebSocketStream(input, text, nvisTokens, signal),
        text,
        nvisTokens,
        emittedSteps,
        'websocket',
      )
    } catch (error) {
      this.onError?.(error, input)
      yield pushStep(emittedSteps, {
        id: 'persona-answer',
        branch: 'personaplex',
        status: 'failed',
        error: errorToMessage(error),
        liveStatusLabel: 'PersonaPlex turn failed',
      })
      const message = makeFinalMessage({
        branch: 'personaplex',
        content: `PersonaPlex could not complete this turn: ${errorToMessage(error)}`,
        reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
        metadata: { error: errorToMessage(error), nvisTokens, personaId: this.personaId },
      })
      yield makeFinalStep(message, 'personaplex')
      return message
    }
  }

  private async openProtocolStream(
    input: TurnInput,
    text: string,
    nvisTokens: UnknownRecord,
    signal: AbortSignal,
  ): Promise<AsyncIterable<unknown> | undefined> {
    if (!this.protocol) return undefined
    const args: PersonaPlexProtocolTurnArgs = {
      text,
      query: text,
      messages: input.messages,
      context: {
        ...(input.context ?? {}),
        personaId: this.personaId,
        surface: this.surface,
      },
      nvisTokens,
      signal,
    }
    const candidate = this.protocol.streamTurn?.(args) ?? this.protocol.sendTurn?.(args) ?? this.protocol.ask?.(args)
    if (!candidate) return undefined
    const awaited = await candidate
    if (isAsyncIterableValue(awaited)) return awaited
    return (async function* singleton(): AsyncGenerator<unknown> {
      yield awaited
    })()
  }

  private async *consumePersonaEvents(
    events: AsyncIterable<unknown>,
    text: string,
    nvisTokens: UnknownRecord,
    emittedSteps: StreamingStep[],
    transport: 'personaplexProtocol' | 'websocket',
  ): MemoryTurnStream {
    let content = ''
    let finalPayload: unknown
    let sawRecall = false
    let sawAnswer = false

    for await (const event of events) {
      const mapped = mapPersonaPlexEvent(event)

      if (mapped.step) {
        if (mapped.step.id === 'persona-recall') sawRecall = true
        if (mapped.step.id === 'persona-answer') sawAnswer = true
        emittedSteps.push(mapped.step)
        yield mapped.step
      }

      if (mapped.delta) content += mapped.delta
      if (mapped.finalPayload !== undefined) finalPayload = mapped.finalPayload
      if (mapped.finalText) content = mapped.finalText
    }

    if (!sawRecall) {
      yield pushStep(emittedSteps, {
        id: 'persona-recall',
        branch: 'personaplex',
        status: 'completed',
        detail: 'Persona memory stream completed',
      })
    }
    if (!sawAnswer) {
      yield pushStep(emittedSteps, {
        id: 'persona-answer',
        branch: 'personaplex',
        status: 'completed',
        detail: 'Persona response completed',
      })
    }

    const finalText = content.trim() || extractContentFromUnknown(finalPayload) || 'PersonaPlex completed without a renderable answer.'
    const message = makeFinalMessage({
      branch: 'personaplex',
      content: finalText,
      reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
      metadata: {
        transport,
        prompt: text,
        nvisTokens,
        personaId: this.personaId,
        finalPayload,
        deprecatedLayout: 'PersonaPlexChatWell grid/CSS is gallery-only; production renders through ComplianceChatWell.',
      },
    })
    yield makeFinalStep(message, 'personaplex')
    return message
  }

  private async *openRawWebSocketStream(
    input: TurnInput,
    text: string,
    nvisTokens: UnknownRecord,
    signal: AbortSignal,
  ): AsyncGenerator<unknown> {
    const socketFactory = this.createSocket ?? defaultCreateSocket
    const socket = socketFactory(this.wsUrl)
    this.activeSocket = socket

    await waitForSocketOpen(socket, signal)
    yield {
      type: 'step',
      step: 'connecting-personaplex',
      status: 'completed',
      detail: 'PersonaPlex websocket connected',
    }

    socket.send(JSON.stringify({
      type: 'turn',
      text,
      query: text,
      question: text,
      persona_id: this.personaId,
      surface: this.surface,
      messages: input.messages,
      context: input.context,
      nvisTokens,
      nvis_tokens: nvisTokens,
    }))

    for await (const message of socketMessages(socket, signal)) {
      yield message
      if (isTerminalPersonaEvent(message)) break
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

function defaultCreateSocket(url: string): WebSocketLike {
  if (typeof WebSocket === 'undefined') {
    throw new Error('PersonaPlexAdapter requires a WebSocket implementation or personaplexProtocol injection')
  }
  return new WebSocket(url)
}

function extractNvisTokens(input: TurnInput): UnknownRecord {
  const context = input.context ?? {}
  const tokens: UnknownRecord = {}
  const explicit = context.nvisTokens ?? context.nvis_tokens
  if (explicit && typeof explicit === 'object') {
    Object.assign(tokens, explicit as UnknownRecord)
  }

  for (const [key, value] of Object.entries(context)) {
    if (/^EMBRY\./.test(key)) tokens[key] = value
  }
  return tokens
}

function mapPersonaPlexEvent(event: unknown): {
  step?: StreamingStep
  delta?: string
  finalText?: string
  finalPayload?: unknown
} {
  const parsed = parseMaybeJson(event)
  if (typeof parsed === 'string') return { delta: parsed }
  if (!parsed || typeof parsed !== 'object') return {}

  const record = parsed as UnknownRecord
  const type = stringValue(record.type ?? record.event ?? record.kind)
  const phase = stringValue(record.phase ?? record.step ?? record.stage)
  const status = normalizeStatus(record.status)
  const text = extractContentFromUnknown(record)

  if (type === 'token' || type === 'delta' || type === 'assistant_delta') return { delta: text }
  if (type === 'final' || type === 'done' || type === 'assistant_message' || type === 'complete') {
    return { finalText: text, finalPayload: record }
  }

  const stepId = personaStepId(phase ?? type)
  if (stepId) {
    return {
      step: makeStep({
        id: stepId,
        branch: 'personaplex',
        status,
        detail: stringValue(record.detail ?? record.message ?? record.label),
        data: record,
        liveStatusLabel: stepId === 'persona-answer' ? 'Composing persona response…' : 'Loading persona memory…',
      }),
      delta: type === 'message' ? text : undefined,
    }
  }

  if (text) return { delta: text }
  return {}
}

function personaStepId(value: string | undefined): StreamingStepId | undefined {
  if (!value) return undefined
  const normalized = value.toLowerCase()
  if (normalized.includes('connect')) return 'connecting-personaplex'
  if (normalized.includes('memory') || normalized.includes('recall') || normalized.includes('retrieve')) return 'persona-recall'
  if (normalized.includes('answer') || normalized.includes('respond') || normalized.includes('compose')) return 'persona-answer'
  if (normalized === 'thinking' || normalized === 'trace' || normalized === 'step') return 'persona-recall'
  return undefined
}

function normalizeStatus(value: unknown): 'pending' | 'running' | 'completed' | 'failed' | 'skipped' {
  const text = stringValue(value)?.toLowerCase()
  if (text === 'pending' || text === 'running' || text === 'completed' || text === 'failed' || text === 'skipped') return text
  if (text === 'done' || text === 'complete' || text === 'ok') return 'completed'
  if (text === 'error') return 'failed'
  return 'running'
}

function parseMaybeJson(event: unknown): unknown {
  if (typeof MessageEvent !== 'undefined' && event instanceof MessageEvent) {
    return parseMaybeJson(event.data)
  }
  if (typeof event !== 'string') return event
  try {
    return JSON.parse(event)
  } catch {
    return event
  }
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function isAsyncIterableValue<T>(value: unknown): value is AsyncIterable<T> {
  return Boolean(value && typeof (value as { [Symbol.asyncIterator]?: unknown })[Symbol.asyncIterator] === 'function')
}

function isTerminalPersonaEvent(event: unknown): boolean {
  const parsed = parseMaybeJson(event)
  if (!parsed || typeof parsed !== 'object') return false
  const type = stringValue((parsed as UnknownRecord).type ?? (parsed as UnknownRecord).event ?? (parsed as UnknownRecord).kind)?.toLowerCase()
  return type === 'final' || type === 'done' || type === 'complete' || type === 'assistant_message'
}

async function waitForSocketOpen(socket: WebSocketLike, signal: AbortSignal): Promise<void> {
  if (socket.readyState === 1) return
  await new Promise<void>((resolve, reject) => {
    const onOpen = (): void => cleanup(resolve)
    const onError = (): void => cleanup(() => reject(new Error('PersonaPlex websocket failed to open')))
    const onAbort = (): void => cleanup(() => reject(new DOMException('Aborted', 'AbortError')))
    const cleanup = (finish: () => void): void => {
      socket.removeEventListener('open', onOpen)
      socket.removeEventListener('error', onError)
      signal.removeEventListener('abort', onAbort)
      finish()
    }
    socket.addEventListener('open', onOpen)
    socket.addEventListener('error', onError)
    signal.addEventListener('abort', onAbort, { once: true })
  })
}

async function* socketMessages(socket: WebSocketLike, signal: AbortSignal): AsyncGenerator<unknown> {
  const queue: unknown[] = []
  let done = false
  let failure: Error | undefined
  let wake: (() => void) | undefined

  const notify = (): void => {
    wake?.()
    wake = undefined
  }

  const onMessage = (event: Event | MessageEvent): void => {
    const data = 'data' in event ? event.data : event
    queue.push(parseMaybeJson(data))
    notify()
  }
  const onClose = (): void => {
    done = true
    notify()
  }
  const onError = (): void => {
    failure = new Error('PersonaPlex websocket error')
    done = true
    notify()
  }
  const onAbort = (): void => {
    failure = new DOMException('Aborted', 'AbortError')
    done = true
    socket.close(1000, 'aborted')
    notify()
  }

  socket.addEventListener('message', onMessage)
  socket.addEventListener('close', onClose)
  socket.addEventListener('error', onError)
  signal.addEventListener('abort', onAbort, { once: true })

  try {
    while (!done || queue.length > 0) {
      if (failure) throw failure
      if (queue.length > 0) {
        yield queue.shift()
        continue
      }
      await new Promise<void>((resolve) => {
        wake = resolve
      })
    }
    if (failure) throw failure
  } finally {
    socket.removeEventListener('message', onMessage)
    socket.removeEventListener('close', onClose)
    socket.removeEventListener('error', onError)
    signal.removeEventListener('abort', onAbort)
  }
}
