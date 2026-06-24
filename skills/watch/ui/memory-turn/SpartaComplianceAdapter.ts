import type {
  ChatMessage,
  JsonRecord,
  MemoryTurnAdapter,
  MemoryTurnStream,
  StreamingStep,
  StreamingStepId,
  TurnBranch,
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

export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export interface SpartaComplianceAdapterOptions {
  baseUrl?: string
  fetch?: FetchLike
  matrixContext?: UnknownRecord
  gateDepth?: 'light' | 'balanced' | 'strict'
  recallConfidenceThreshold?: number
  evidenceCaseEndpoint?: string
  /**
   * Preferred integration point while extracting SpartaExplorer.handleSend.
   * Pass the existing runTypedEvidenceCaseStream implementation here instead
   * of inventing a new memory-server endpoint.
   */
  runEvidenceCaseStream?: (args: {
    query: string
    input: TurnInput
    emit: (step: StreamingStep) => void
  }) => AsyncIterable<StreamingStep | UnknownRecord | string> | Promise<ChatMessage | UnknownRecord | string>
  onError?: (error: unknown, input: TurnInput) => void
}

interface RecallResult {
  answer?: string
  content?: string
  confidence?: number
  hits?: unknown[]
  citations?: unknown[]
  gate_trace?: unknown
  reasoningSteps?: unknown
  [key: string]: unknown
}

interface ClarifyResult {
  status?: string
  state?: string
  answer?: string
  clarification_question?: string
  question?: string
  options?: unknown[]
  clarifyOptions?: unknown[]
  [key: string]: unknown
}

const EVIDENCE_CASE_COMMAND_RE = /^\s*\/(?:create-)?evidence-case\b/i
const CREATE_FIGURE_COMMAND_RE = /^\s*\/create-figure\b/i
const AQL_COMMAND_RE = /^\s*(?:\/aql\b|aql\s*:)/i

export class SpartaComplianceAdapter implements MemoryTurnAdapter {
  readonly name = 'SpartaComplianceAdapter'
  readonly branch: TurnBranch = 'compliance'

  private readonly baseUrl: string
  private readonly fetchImpl: FetchLike
  private readonly matrixContext?: UnknownRecord
  private readonly gateDepth: 'light' | 'balanced' | 'strict'
  private readonly recallConfidenceThreshold: number
  private readonly evidenceCaseEndpoint: string
  private readonly runEvidenceCaseStream?: SpartaComplianceAdapterOptions['runEvidenceCaseStream']
  private readonly onError?: SpartaComplianceAdapterOptions['onError']
  private abortController: AbortController | undefined

  constructor(options: SpartaComplianceAdapterOptions = {}) {
    this.baseUrl = options.baseUrl ?? ''
    this.fetchImpl = options.fetch ?? fetch.bind(globalThis)
    this.matrixContext = options.matrixContext
    this.gateDepth = options.gateDepth ?? 'balanced'
    this.recallConfidenceThreshold = options.recallConfidenceThreshold ?? 0.75
    this.evidenceCaseEndpoint = options.evidenceCaseEndpoint ?? '/api/create-evidence-case/stream'
    this.runEvidenceCaseStream = options.runEvidenceCaseStream
    this.onError = options.onError
  }

  cancel(): void {
    this.abortController?.abort()
  }

  async *sendTurn(input: TurnInput): MemoryTurnStream {
    this.abortController = new AbortController()
    const signal = input.abortSignal ?? this.abortController.signal
    const query = normalizeTurnText(input)
    const branch = classifySpartaTurn(query, input)
    const emittedSteps: StreamingStep[] = []

    const emit = (step: StreamingStep): StreamingStep => {
      emittedSteps.push(step)
      return step
    }

    try {
      if (!query) {
        const message = makeFinalMessage({
          branch: 'compliance',
          content: 'Ask a SPARTA compliance question or request an evidence case.',
          metadata: { emptyTurn: true },
        })
        yield emit(makeFinalStep(message, 'compliance'))
        return message
      }

      if (branch === 'utility') {
        return yield* this.runUtilityTurn(query, emittedSteps)
      }

      if (branch === 'aql') {
        return yield* this.runAqlTurn(query, input, signal, emittedSteps)
      }

      if (branch === 'evidence-case') {
        return yield* this.runEvidenceCaseTurn(query, input, signal, emittedSteps)
      }

      return yield* this.runComplianceCascade(query, input, signal, emittedSteps)
    } catch (error) {
      this.onError?.(error, input)
      const failed = makeStep({
        id: branch === 'evidence-case' ? 'building-evidence-case' : 'answering',
        branch,
        status: 'failed',
        error: errorToMessage(error),
        liveStatusLabel: branch === 'evidence-case' ? 'Evidence case failed' : 'Answer failed',
      })
      emittedSteps.push(failed)
      yield failed
      const message = makeFinalMessage({
        branch,
        content: `I could not complete this turn: ${errorToMessage(error)}`,
        reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
        metadata: { error: errorToMessage(error) },
      })
      yield makeFinalStep(message, branch)
      return message
    }
  }

  private async *runComplianceCascade(
    query: string,
    input: TurnInput,
    signal: AbortSignal,
    emittedSteps: StreamingStep[],
  ): MemoryTurnStream {
    const branch: TurnBranch = 'compliance'

    yield pushStep(emittedSteps, {
      id: 'extracting-entities',
      branch,
      status: 'running',
      liveStatusLabel: 'Extracting entities…',
    })
    const entities = await this.postJson<UnknownRecord>('/api/extract-entities', {
      text: query,
      query,
      surface: input.surface ?? 'sparta-explorer',
      matrix_context: input.matrixContext ?? this.matrixContext,
    }, signal)
    yield pushStep(emittedSteps, {
      id: 'extracting-entities',
      branch,
      status: 'completed',
      detail: summarizeEntities(entities),
      data: entities,
    })

    yield pushStep(emittedSteps, {
      id: 'looking-in-memory',
      branch,
      status: 'running',
      liveStatusLabel: 'Looking in memory…',
    })
    const trainingRecall = await this.postJson<RecallResult>('/api/memory/recall', {
      query,
      text: query,
      profile: 'intent-training-v2',
      entities,
      matrix_context: input.matrixContext ?? this.matrixContext,
      surface: input.surface ?? 'sparta-explorer',
    }, signal)
    const recallConfidence = numberValue(trainingRecall.confidence)
    yield pushStep(emittedSteps, {
      id: 'looking-in-memory',
      branch,
      status: 'completed',
      detail: recallConfidence === undefined ? 'Recall completed' : `Recall confidence ${recallConfidence.toFixed(2)}`,
      data: trainingRecall,
    })

    const cachedAnswer = extractContentFromUnknown(trainingRecall)
    if (cachedAnswer && recallConfidence !== undefined && recallConfidence >= this.recallConfidenceThreshold) {
      yield pushStep(emittedSteps, {
        id: 'answering',
        branch,
        status: 'completed',
        detail: 'Answered from high-confidence recall cache',
      })
      const message = makeFinalMessage({
        branch,
        content: cachedAnswer,
        reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
        metadata: { entities, recall: trainingRecall, cacheHit: true },
      })
      yield makeFinalStep(message, branch)
      return message
    }

    yield pushStep(emittedSteps, {
      id: 'checking-gates',
      branch,
      status: 'running',
      liveStatusLabel: 'Checking gates…',
    })
    const gateState = evaluateComplianceGates({ entities, trainingRecall, gateDepth: this.gateDepth })
    yield pushStep(emittedSteps, {
      id: 'checking-gates',
      branch,
      status: gateState.ok ? 'completed' : 'completed',
      detail: gateState.summary,
      data: gateState,
    })

    if (gateState.needsClarification) {
      yield pushStep(emittedSteps, {
        id: 'clarifying',
        branch,
        status: 'running',
        liveStatusLabel: 'Checking whether clarification is needed…',
      })
      const clarification = await this.postJson<ClarifyResult>('/api/memory/clarify', {
        query,
        text: query,
        entities,
        recall: trainingRecall,
        gates: gateState,
        matrix_context: input.matrixContext ?? this.matrixContext,
      }, signal)
      yield pushStep(emittedSteps, {
        id: 'clarifying',
        branch,
        status: 'completed',
        data: clarification,
        detail: clarifySummary(clarification),
      })

      if (isInconclusiveClarification(clarification)) {
        const clarificationText =
          extractContentFromUnknown(clarification) ||
          'I need one more detail before I can ground this in SPARTA memory.'
        const message = makeFinalMessage({
          branch,
          content: clarificationText,
          reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
          metadata: {
            entities,
            recall: trainingRecall,
            gates: gateState,
            clarifyOptions: clarification.options ?? clarification.clarifyOptions,
            clarification,
          },
        })
        yield makeFinalStep(message, branch)
        return message
      }
    } else {
      yield pushStep(emittedSteps, {
        id: 'clarifying',
        branch,
        status: 'skipped',
        detail: 'No clarification needed',
      })
    }

    yield pushStep(emittedSteps, {
      id: 'finalizing-intent',
      branch,
      status: 'running',
      liveStatusLabel: 'Finalizing intent…',
    })
    const intent = await this.postJson<UnknownRecord>('/api/memory/intent', {
      query,
      text: query,
      entities,
      recall: trainingRecall,
      gates: gateState,
      matrix_context: input.matrixContext ?? this.matrixContext,
    }, signal)
    yield pushStep(emittedSteps, {
      id: 'finalizing-intent',
      branch,
      status: 'completed',
      detail: intentSummary(intent),
      data: intent,
    })

    yield pushStep(emittedSteps, {
      id: 'getting-results',
      branch,
      status: 'running',
      liveStatusLabel: 'Getting results…',
    })
    const querySpec = recordValue(intent, 'query_spec') ?? recordValue(intent, 'querySpec') ?? intent
    const memoryResults = await this.postJson<RecallResult>('/api/memory/recall', {
      query,
      text: query,
      query_spec: querySpec,
      entities,
      intent,
      matrix_context: input.matrixContext ?? this.matrixContext,
      surface: input.surface ?? 'sparta-explorer',
    }, signal)
    yield pushStep(emittedSteps, {
      id: 'getting-results',
      branch,
      status: 'completed',
      detail: resultSummary(memoryResults),
      data: memoryResults,
    })

    yield pushStep(emittedSteps, {
      id: 'answering',
      branch,
      status: 'running',
      liveStatusLabel: 'Answering…',
    })
    let content = extractContentFromUnknown(memoryResults)
    let fallbackUsed = false
    if (!content) {
      fallbackUsed = true
      const fallback = await this.postJson<UnknownRecord>('/api/scillm', {
        query,
        text: query,
        entities,
        intent,
        recall: memoryResults,
        matrix_context: input.matrixContext ?? this.matrixContext,
        instruction: 'Answer using SPARTA memory context only. State uncertainty when evidence is incomplete.',
      }, signal)
      content = extractContentFromUnknown(fallback) || 'I could not find enough grounded SPARTA memory to answer this turn.'
    }
    yield pushStep(emittedSteps, {
      id: 'answering',
      branch,
      status: 'completed',
      detail: fallbackUsed ? 'Answered with scillm fallback' : 'Answered from memory recall',
    })

    const message = makeFinalMessage({
      branch,
      content,
      reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
      metadata: {
        entities,
        trainingRecall,
        gates: gateState,
        intent,
        memoryResults,
        fallbackUsed,
      },
    })
    yield makeFinalStep(message, branch)
    return message
  }

  private async *runEvidenceCaseTurn(
    query: string,
    input: TurnInput,
    signal: AbortSignal,
    emittedSteps: StreamingStep[],
  ): MemoryTurnStream {
    const branch: TurnBranch = 'evidence-case'
    yield pushStep(emittedSteps, {
      id: 'building-evidence-case',
      branch,
      status: 'running',
      liveStatusLabel: 'Building evidence case…',
    })

    const evidenceQuery = query.replace(EVIDENCE_CASE_COMMAND_RE, '').trim() || query

    if (this.runEvidenceCaseStream) {
      const buffered: StreamingStep[] = []
      const external = await this.runEvidenceCaseStream({
        query: evidenceQuery,
        input,
        emit: (step) => buffered.push(step),
      })

      for (const step of buffered) {
        emittedSteps.push(step)
        yield step
      }

      if (isAsyncIterableValue(external)) {
        let finalContent = ''
        for await (const event of external) {
          const mapped = mapEvidenceEventToStep(event, emittedSteps)
          if (mapped.step) {
            emittedSteps.push(mapped.step)
            yield mapped.step
          }
          if (mapped.content) finalContent += mapped.content
        }
        const content = finalContent.trim() || 'Evidence case completed.'
        const message = makeFinalMessage({
          branch,
          content,
          reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
          metadata: { evidenceQuery, source: 'runEvidenceCaseStream' },
          skillUsed: 'create-evidence-case',
        })
        yield makeFinalStep(message, branch)
        return message
      }

      const content = extractContentFromUnknown(external) || 'Evidence case completed.'
      const message = makeFinalMessage({
        branch,
        content,
        reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
        metadata: { evidenceQuery, source: 'runEvidenceCaseStream' },
        skillUsed: 'create-evidence-case',
      })
      yield makeFinalStep(message, branch)
      return message
    }

    let content = ''
    let receipt: unknown
    for await (const event of this.postJsonStream(this.evidenceCaseEndpoint, {
      query: evidenceQuery,
      text: evidenceQuery,
      matrix_context: input.matrixContext ?? this.matrixContext,
      surface: input.surface ?? 'sparta-explorer',
    }, signal)) {
      const mapped = mapEvidenceEventToStep(event, emittedSteps)
      if (mapped.step) {
        emittedSteps.push(mapped.step)
        yield mapped.step
      }
      if (mapped.content) content += mapped.content
      if (mapped.receipt) receipt = mapped.receipt
    }

    yield pushStep(emittedSteps, {
      id: 'building-evidence-case',
      branch,
      status: 'completed',
      detail: 'Evidence case complete',
      data: receipt,
    })

    const message = makeFinalMessage({
      branch,
      content: content.trim() || 'Evidence case completed.',
      reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
      metadata: { evidenceQuery, receipt },
      skillUsed: 'create-evidence-case',
    })
    yield makeFinalStep(message, branch)
    return message
  }

  private async *runAqlTurn(
    query: string,
    input: TurnInput,
    signal: AbortSignal,
    emittedSteps: StreamingStep[],
  ): MemoryTurnStream {
    const branch: TurnBranch = 'aql'
    const aql = query.replace(AQL_COMMAND_RE, '').trim()
    yield pushStep(emittedSteps, {
      id: 'aql-query',
      branch,
      status: 'running',
      liveStatusLabel: 'Running AQL recall…',
      detail: aql,
    })
    const result = await this.postJson<RecallResult>('/api/memory/recall', {
      type: 'aql',
      query: aql || query,
      text: query,
      matrix_context: input.matrixContext ?? this.matrixContext,
    }, signal)
    yield pushStep(emittedSteps, {
      id: 'aql-query',
      branch,
      status: 'completed',
      data: result,
      detail: resultSummary(result),
    })
    const content = extractContentFromUnknown(result) || 'AQL recall returned no renderable answer.'
    yield pushStep(emittedSteps, {
      id: 'answering',
      branch,
      status: 'completed',
    })
    const message = makeFinalMessage({
      branch,
      content,
      reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
      metadata: { aql, result },
    })
    yield makeFinalStep(message, branch)
    return message
  }

  private async *runUtilityTurn(query: string, emittedSteps: StreamingStep[]): MemoryTurnStream {
    const branch: TurnBranch = 'utility'
    yield pushStep(emittedSteps, {
      id: 'utility-answer',
      branch,
      status: 'running',
      liveStatusLabel: 'Answering directly…',
    })
    const answer = safeArithmeticAnswer(query)
    yield pushStep(emittedSteps, {
      id: 'utility-answer',
      branch,
      status: 'completed',
      detail: answer === undefined ? 'No deterministic utility answer' : 'Computed deterministic answer',
    })
    const message = makeFinalMessage({
      branch,
      content: answer ?? 'I can only answer deterministic utility turns here. Try a SPARTA compliance question instead.',
      reasoningSteps: streamingStepsToThinkingTrace(emittedSteps),
      metadata: { deterministicUtility: answer !== undefined },
    })
    yield makeFinalStep(message, branch)
    return message
  }

  private async postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
    const response = await this.fetchImpl(joinUrl(this.baseUrl, path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    if (!response.ok) {
      throw new Error(`${path} failed with HTTP ${response.status}`)
    }
    const text = await response.text()
    if (!text.trim()) return {} as T
    try {
      return JSON.parse(text) as T
    } catch {
      return { answer: text } as T
    }
  }

  private async *postJsonStream(path: string, body: unknown, signal?: AbortSignal): AsyncGenerator<unknown> {
    const response = await this.fetchImpl(joinUrl(this.baseUrl, path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream, application/x-ndjson, application/json' },
      body: JSON.stringify(body),
      signal,
    })
    if (!response.ok) {
      throw new Error(`${path} failed with HTTP ${response.status}`)
    }
    if (!response.body) {
      yield await response.json()
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        const parsed = parseEventLine(line)
        if (parsed !== undefined) yield parsed
      }
    }
    buffer += decoder.decode()
    for (const line of buffer.split(/\r?\n/)) {
      const parsed = parseEventLine(line)
      if (parsed !== undefined) yield parsed
    }
  }
}

export function classifySpartaTurn(query: string, input?: TurnInput): TurnBranch {
  if (input?.branchHint) return input.branchHint
  if (EVIDENCE_CASE_COMMAND_RE.test(query) || isSpartaEvidenceBoundTurn(query)) return 'evidence-case'
  if (AQL_COMMAND_RE.test(query) || input?.context?.type === 'aql') return 'aql'
  if (isSpartaGeneralUtilityTurn(query) && !CREATE_FIGURE_COMMAND_RE.test(query)) return 'utility'
  return 'compliance'
}

export function isSpartaEvidenceBoundTurn(query: string): boolean {
  const normalized = query.toLowerCase()
  return (
    normalized.includes('evidence case') ||
    normalized.includes('control evidence') ||
    normalized.includes('generate receipts') ||
    normalized.includes('create evidence')
  )
}

export function isSpartaGeneralUtilityTurn(query: string): boolean {
  return safeArithmeticAnswer(query) !== undefined
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

function recordValue(record: unknown, key: string): unknown {
  if (!record || typeof record !== 'object') return undefined
  return (record as UnknownRecord)[key]
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return undefined
}

function arrayLength(value: unknown): number | undefined {
  return Array.isArray(value) ? value.length : undefined
}

function summarizeEntities(entities: UnknownRecord): string {
  const values = ['entities', 'controls', 'domains', 'artifacts']
    .map((key) => [key, arrayLength(recordValue(entities, key))] as const)
    .filter(([, count]) => count !== undefined)
    .map(([key, count]) => `${count} ${key}`)
  return values.length ? values.join(', ') : 'Entity extraction completed'
}

function resultSummary(result: RecallResult): string {
  const hits = arrayLength(result.hits)
  const citations = arrayLength(result.citations)
  const parts: string[] = []
  if (hits !== undefined) parts.push(`${hits} hits`)
  if (citations !== undefined) parts.push(`${citations} citations`)
  return parts.length ? parts.join(', ') : 'Memory results completed'
}

function intentSummary(intent: UnknownRecord): string {
  const type = recordValue(intent, 'intent') ?? recordValue(intent, 'type') ?? recordValue(intent, 'route')
  return typeof type === 'string' ? `Intent: ${type}` : 'Intent finalized'
}

function clarifySummary(clarification: ClarifyResult): string {
  const state = clarification.status ?? clarification.state
  if (state) return `Clarify state: ${state}`
  return 'Clarification checked'
}

function isInconclusiveClarification(clarification: ClarifyResult): boolean {
  const state = (clarification.status ?? clarification.state ?? '').toUpperCase()
  return state === 'INCONCLUSIVE' || state === 'CLARIFY' || Array.isArray(clarification.options) || Array.isArray(clarification.clarifyOptions)
}

function evaluateComplianceGates(args: {
  entities: UnknownRecord
  trainingRecall: RecallResult
  gateDepth: 'light' | 'balanced' | 'strict'
}): { ok: boolean; needsClarification: boolean; summary: string; reasons: string[] } {
  const reasons: string[] = []
  const grounding = recordValue(args.entities, 'grounding_ok')
  const hits = arrayLength(args.trainingRecall.hits) ?? 0
  const confidence = numberValue(args.trainingRecall.confidence) ?? 0

  if (grounding === false) reasons.push('grounding not confirmed')
  if (args.gateDepth !== 'light' && hits === 0 && confidence < 0.5) reasons.push('low recall confidence')
  if (args.gateDepth === 'strict' && confidence < 0.65) reasons.push('strict gate confidence threshold not met')

  return {
    ok: reasons.length === 0,
    needsClarification: reasons.length > 0,
    summary: reasons.length ? `Clarification gate: ${reasons.join('; ')}` : 'Gates passed',
    reasons,
  }
}

function parseEventLine(line: string): unknown | undefined {
  const trimmed = line.trim()
  if (!trimmed || trimmed.startsWith(':')) return undefined
  const payload = trimmed.startsWith('data:') ? trimmed.slice(5).trim() : trimmed
  if (!payload || payload === '[DONE]') return undefined
  try {
    return JSON.parse(payload)
  } catch {
    return payload
  }
}

function mapEvidenceEventToStep(event: unknown, emittedSteps: StreamingStep[]): { step?: StreamingStep; content?: string; receipt?: unknown } {
  if (typeof event === 'string') {
    return { content: event }
  }
  if (isStreamingStepLike(event)) {
    return { step: event }
  }
  if (!event || typeof event !== 'object') return {}

  const record = event as UnknownRecord
  const type = typeof record.type === 'string' ? record.type : undefined
  const content = extractContentFromUnknown(record)
  const receipt = record.receipt ?? record.final_receipt ?? record.evidence_case

  if (type === 'token' || type === 'delta') return { content }
  if (type === 'receipt' || receipt) return { receipt }

  const id = typeof record.step === 'string' ? record.step : typeof record.id === 'string' ? record.id : 'building-evidence-case'
  const status = record.status === 'failed' ? 'failed' : record.status === 'completed' ? 'completed' : 'running'
  return {
    step: makeStep({
      id: id as StreamingStepId,
      branch: 'evidence-case',
      status,
      detail: typeof record.detail === 'string' ? record.detail : undefined,
      data: record,
      liveStatusLabel: 'Building evidence case…',
    }),
    content: type === 'message' ? content : undefined,
  }
}

function isStreamingStepLike(value: unknown): value is StreamingStep {
  return Boolean(
    value &&
      typeof value === 'object' &&
      typeof (value as StreamingStep).id === 'string' &&
      typeof (value as StreamingStep).branch === 'string' &&
      typeof (value as StreamingStep).status === 'string',
  )
}

function isAsyncIterableValue<T>(value: unknown): value is AsyncIterable<T> {
  return Boolean(value && typeof (value as { [Symbol.asyncIterator]?: unknown })[Symbol.asyncIterator] === 'function')
}

export function safeArithmeticAnswer(question: string): string | undefined {
  const expression = question
    .toLowerCase()
    .replace(/^\s*what\s+is\s+/, '')
    .replace(/\bplus\b/g, '+')
    .replace(/\bminus\b/g, '-')
    .replace(/\btimes\b|\bmultiplied\s+by\b/g, '*')
    .replace(/\bdivided\s+by\b/g, '/')
    .replace(/[?=]/g, '')
    .trim()

  if (!/^[\d+\-*/().\s]+$/.test(expression) || !/\d/.test(expression)) return undefined
  try {
    const value = evaluateArithmeticExpression(expression)
    if (!Number.isFinite(value)) return undefined
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(8)))
  } catch {
    return undefined
  }
}

function evaluateArithmeticExpression(expression: string): number {
  const tokens = expression.match(/\d+(?:\.\d+)?|[()+\-*/]/g) ?? []
  let index = 0

  const peek = (): string | undefined => tokens[index]
  const consume = (): string => tokens[index++] ?? ''

  const parseExpression = (): number => {
    let value = parseTerm()
    while (peek() === '+' || peek() === '-') {
      const op = consume()
      const rhs = parseTerm()
      value = op === '+' ? value + rhs : value - rhs
    }
    return value
  }

  const parseTerm = (): number => {
    let value = parseFactor()
    while (peek() === '*' || peek() === '/') {
      const op = consume()
      const rhs = parseFactor()
      value = op === '*' ? value * rhs : value / rhs
    }
    return value
  }

  const parseFactor = (): number => {
    const token = consume()
    if (token === '+') return parseFactor()
    if (token === '-') return -parseFactor()
    if (token === '(') {
      const value = parseExpression()
      if (consume() !== ')') throw new Error('Unbalanced parentheses')
      return value
    }
    const value = Number(token)
    if (!Number.isFinite(value)) throw new Error('Invalid number')
    return value
  }

  const value = parseExpression()
  if (index !== tokens.length) throw new Error('Unexpected token')
  return value
}

void ({} as JsonRecord)
