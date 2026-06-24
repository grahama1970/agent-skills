/**
 * Shared memory turn orchestration seam for ux-lab chat surfaces.
 *
 * This file is intentionally UI-framework neutral. Host components render the
 * returned StreamingStep objects through ComplianceChatWell + ThinkingTrace and
 * append the final ChatMessage through the same message-list path.
 */

export type ChatRole = 'user' | 'assistant' | 'system' | 'tool'

export type TurnBranch =
  | 'evidence-case'
  | 'compliance'
  | 'utility'
  | 'aql'
  | 'watch'
  | 'personaplex'

export type TurnSurface =
  | 'sparta-explorer'
  | 'watch'
  | 'final-site'
  | 'shared-chat'

export type DisclosureVariant = 'thinking' | 'evidence-case' | 'none'

export type StreamingStepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped'

export type StreamingStepKind = 'step' | 'token' | 'message' | 'final' | 'error'

/**
 * Step ids are deliberately aligned with thinkingTraceHelpers.ts and the
 * existing Watch inline reasoning ids. Keep these stable: they are the bridge
 * between adapter events and ThinkingTrace rendering.
 */
export type StreamingStepId =
  | 'building-evidence-case'
  | 'extracting-entities'
  | 'looking-in-memory'
  | 'checking-gates'
  | 'clarifying'
  | 'finalizing-intent'
  | 'getting-results'
  | 'answering'
  | 'watch-scene-context'
  | 'connecting-personaplex'
  | 'persona-recall'
  | 'persona-answer'
  | 'utility-answer'
  | 'aql-query'
  | (string & {})

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue }

export type JsonRecord = Record<string, JsonValue>
export type UnknownRecord = Record<string, unknown>

export interface ThinkingTraceLikeStep {
  id: string
  label: string
  status?: StreamingStepStatus
  detail?: string
  disclosureVariant?: DisclosureVariant
  icon?: 'shield' | 'sparkles' | 'sparkle' | 'mic' | 'memory' | 'search' | 'check'
  startedAt?: string
  completedAt?: string
  data?: unknown
}

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  createdAt: string
  /** Compatibility with existing ChatWell-style message metadata. */
  title?: string
  footer?: string
  skillUsed?: string
  evidenceCase?: boolean
  reasoningSteps?: ThinkingTraceLikeStep[]
  thinkingTrace?: ThinkingTraceLikeStep[]
  metadata?: UnknownRecord
}

export interface TurnInput {
  text: string
  /** Optional alias for older callers that pass query/question. */
  query?: string
  question?: string
  mode?: 'compliance' | 'personaplex'
  surface?: TurnSurface
  branchHint?: TurnBranch
  messages?: ChatMessage[]
  context?: UnknownRecord
  matrixContext?: UnknownRecord
  abortSignal?: AbortSignal
}

export interface StreamingStep {
  kind: StreamingStepKind
  id: StreamingStepId
  label: string
  status: StreamingStepStatus
  branch: TurnBranch
  disclosureVariant: DisclosureVariant
  liveStatusLabel?: string
  detail?: string
  messageDelta?: string
  message?: ChatMessage
  data?: unknown
  error?: string
  startedAt?: string
  completedAt?: string
}

export type MemoryTurnStream = AsyncGenerator<StreamingStep, ChatMessage | void, unknown>
export type MemoryTurnResult = MemoryTurnStream | Promise<ChatMessage>

export interface MemoryTurnAdapter {
  name: string
  branch: TurnBranch
  sendTurn(input: TurnInput): MemoryTurnResult
  cancel?(): void
}

export interface BranchDefinition {
  branch: TurnBranch
  label: string
  disclosureVariant: DisclosureVariant
  liveStatusLabel: string
  stepIds: StreamingStepId[]
}

export const MEMORY_TURN_BRANCH_TABLE: Record<TurnBranch, BranchDefinition> = {
  'evidence-case': {
    branch: 'evidence-case',
    label: 'Evidence case',
    disclosureVariant: 'evidence-case',
    liveStatusLabel: 'Building evidence case…',
    stepIds: ['building-evidence-case', 'checking-gates', 'answering'],
  },
  compliance: {
    branch: 'compliance',
    label: 'Compliance answer',
    disclosureVariant: 'thinking',
    liveStatusLabel: 'Thinking…',
    stepIds: [
      'extracting-entities',
      'looking-in-memory',
      'checking-gates',
      'clarifying',
      'finalizing-intent',
      'getting-results',
      'answering',
    ],
  },
  utility: {
    branch: 'utility',
    label: 'Utility answer',
    disclosureVariant: 'thinking',
    liveStatusLabel: 'Thinking…',
    stepIds: ['utility-answer'],
  },
  aql: {
    branch: 'aql',
    label: 'AQL answer',
    disclosureVariant: 'thinking',
    liveStatusLabel: 'Looking in memory…',
    stepIds: ['aql-query', 'looking-in-memory', 'answering'],
  },
  watch: {
    branch: 'watch',
    label: 'Watch answer',
    disclosureVariant: 'thinking',
    liveStatusLabel: 'Checking the scene memory…',
    stepIds: [
      'watch-scene-context',
      'extracting-entities',
      'looking-in-memory',
      'finalizing-intent',
      'getting-results',
      'answering',
    ],
  },
  personaplex: {
    branch: 'personaplex',
    label: 'PersonaPlex answer',
    disclosureVariant: 'thinking',
    liveStatusLabel: 'Show thinking',
    stepIds: ['connecting-personaplex', 'persona-recall', 'persona-answer'],
  },
}

export const STREAMING_STEP_LABELS: Record<string, string> = {
  'building-evidence-case': 'Building evidence case',
  'extracting-entities': 'Extracting entities',
  'looking-in-memory': 'Looking in memory',
  'checking-gates': 'Checking gates',
  clarifying: 'Checking whether clarification is needed',
  'finalizing-intent': 'Finalizing intent',
  'getting-results': 'Getting results',
  answering: 'Answering',
  'watch-scene-context': 'Reading scene context',
  'connecting-personaplex': 'Connecting to PersonaPlex',
  'persona-recall': 'Loading persona memory',
  'persona-answer': 'Composing persona response',
  'utility-answer': 'Answering directly',
  'aql-query': 'Running AQL recall',
}

export function normalizeTurnText(input: TurnInput): string {
  return (input.text || input.query || input.question || '').trim()
}

export function makeMessageId(prefix = 'msg'): string {
  const random = Math.random().toString(36).slice(2, 10)
  return `${prefix}-${Date.now().toString(36)}-${random}`
}

export function branchDefinition(branch: TurnBranch): BranchDefinition {
  return MEMORY_TURN_BRANCH_TABLE[branch]
}

export function pendingStepsForBranch(branch: TurnBranch): StreamingStep[] {
  const definition = branchDefinition(branch)
  return definition.stepIds.map((id) =>
    makeStep({
      id,
      branch,
      status: 'pending',
      disclosureVariant: definition.disclosureVariant,
      liveStatusLabel: definition.liveStatusLabel,
    }),
  )
}

export function makeStep(args: {
  id: StreamingStepId
  branch: TurnBranch
  status?: StreamingStepStatus
  label?: string
  disclosureVariant?: DisclosureVariant
  liveStatusLabel?: string
  detail?: string
  messageDelta?: string
  data?: unknown
  error?: string
  kind?: StreamingStepKind
}): StreamingStep {
  const definition = branchDefinition(args.branch)
  const status = args.status ?? 'running'
  const timestamp = new Date().toISOString()
  return {
    kind: args.kind ?? (args.error ? 'error' : 'step'),
    id: args.id,
    label: args.label ?? STREAMING_STEP_LABELS[args.id] ?? args.id,
    status,
    branch: args.branch,
    disclosureVariant: args.disclosureVariant ?? definition.disclosureVariant,
    liveStatusLabel: args.liveStatusLabel ?? definition.liveStatusLabel,
    detail: args.detail,
    messageDelta: args.messageDelta,
    data: args.data,
    error: args.error,
    startedAt: status === 'running' || status === 'pending' ? timestamp : undefined,
    completedAt: status === 'completed' || status === 'failed' || status === 'skipped' ? timestamp : undefined,
  }
}

export function makeFinalMessage(args: {
  branch: TurnBranch
  content: string
  metadata?: UnknownRecord
  reasoningSteps?: ThinkingTraceLikeStep[]
  idPrefix?: string
  skillUsed?: string
}): ChatMessage {
  return {
    id: makeMessageId(args.idPrefix ?? args.branch),
    role: 'assistant',
    content: args.content,
    createdAt: new Date().toISOString(),
    evidenceCase: args.branch === 'evidence-case',
    skillUsed: args.skillUsed ?? (args.branch === 'evidence-case' ? 'create-evidence-case' : undefined),
    reasoningSteps: args.reasoningSteps,
    thinkingTrace: args.reasoningSteps,
    metadata: {
      branch: args.branch,
      disclosureVariant: branchDefinition(args.branch).disclosureVariant,
      ...(args.metadata ?? {}),
    },
  }
}

export function makeFinalStep(message: ChatMessage, branch: TurnBranch): StreamingStep {
  const definition = branchDefinition(branch)
  return {
    kind: 'final',
    id: 'answering',
    label: 'Final answer',
    status: 'completed',
    branch,
    disclosureVariant: definition.disclosureVariant,
    liveStatusLabel: definition.liveStatusLabel,
    message,
    completedAt: new Date().toISOString(),
  }
}

export function streamingStepToThinkingTraceStep(step: StreamingStep): ThinkingTraceLikeStep {
  return {
    id: step.id,
    label: step.label,
    status: step.status,
    detail: step.detail ?? step.error,
    disclosureVariant: step.disclosureVariant,
    icon: step.disclosureVariant === 'evidence-case' ? 'shield' : 'sparkles',
    startedAt: step.startedAt,
    completedAt: step.completedAt,
    data: step.data,
  }
}

export function streamingStepsToThinkingTrace(steps: StreamingStep[]): ThinkingTraceLikeStep[] {
  const latestById = new Map<string, ThinkingTraceLikeStep>()
  for (const step of steps) {
    if (step.kind === 'final' || step.kind === 'token' || step.kind === 'message') continue
    latestById.set(step.id, streamingStepToThinkingTraceStep(step))
  }
  return [...latestById.values()]
}

export function liveStatusLabelFromSteps(steps: StreamingStep[], fallback = 'Thinking…'): string {
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    const step = steps[index]
    if (step.status === 'running') return step.liveStatusLabel ?? step.label
  }
  const last = steps[steps.length - 1]
  return last?.liveStatusLabel ?? fallback
}

export function isAsyncIterable<T>(value: unknown): value is AsyncIterable<T> {
  return Boolean(value && typeof (value as { [Symbol.asyncIterator]?: unknown })[Symbol.asyncIterator] === 'function')
}

export async function collectMemoryTurn(result: MemoryTurnResult): Promise<{
  message: ChatMessage
  steps: StreamingStep[]
}> {
  const awaited = await result
  if (!isAsyncIterable<StreamingStep>(awaited)) {
    return { message: awaited as ChatMessage, steps: [] }
  }

  const steps: StreamingStep[] = []
  let finalFromStep: ChatMessage | undefined
  const iterator = awaited[Symbol.asyncIterator]()

  for (;;) {
    const next = await iterator.next()
    if (next.done) {
      const returned = next.value as ChatMessage | void
      const message = finalFromStep ?? returned
      if (!message) {
        throw new Error('MemoryTurnAdapter stream finished without a final ChatMessage')
      }
      return { message, steps }
    }

    const step = next.value as StreamingStep
    steps.push(step)
    if (step.kind === 'final' && step.message) {
      finalFromStep = step.message
    }
  }
}

export function errorToMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  return 'Unknown error'
}

export function getRecordValue(record: unknown, key: string): unknown {
  if (!record || typeof record !== 'object') return undefined
  return (record as UnknownRecord)[key]
}

export function pickFirstString(record: unknown, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = getRecordValue(record, key)
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return undefined
}

export function extractContentFromUnknown(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  const direct = pickFirstString(value, ['answer', 'content', 'message', 'response', 'text', 'final'])
  if (direct) return direct

  const nestedKeys = ['data', 'result', 'packet', 'answerPacket', 'payload']
  for (const key of nestedKeys) {
    const nested = getRecordValue(value, key)
    const nestedContent = pickFirstString(nested, ['answer', 'content', 'message', 'response', 'text', 'final'])
    if (nestedContent) return nestedContent
  }

  return ''
}
