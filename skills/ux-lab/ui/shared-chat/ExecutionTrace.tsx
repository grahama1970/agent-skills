import React from 'react'
import type { ChatMessage, ThinkingTraceLikeStep, UnknownRecord } from './memory-turn'
import type { EvidenceCaseData, EvidenceCaseSpan } from './types'

type TraceStatus = 'passed' | 'skipped' | 'blocked' | 'pending'
type TerminalState = 'ANSWER' | 'CLARIFY' | 'DEFLECT' | 'NO_MATCH' | 'INCONCLUSIVE'

export interface ExecutionTraceData {
  entities: {
    anchors: string[]
    validated: string[]
    candidates: string[]
    unresolved: string[]
    suppressed: string[]
  }
  intent: {
    route: string
    confidence?: number | null
    alternates: string[]
  }
  pipeline: {
    extract: TraceStatus
    intent: TraceStatus
    route: TraceStatus
    evidence: TraceStatus
  }
  evidence?: {
    claims: Array<{
      statement: string
      qra_reference: string
      grounded: boolean
    }>
    verdict: string
  } | null
  terminalState: TerminalState
  stopReason?: string
}

const TRACE_STATES: Record<TerminalState, { color: string; label: string; description: string }> = {
  ANSWER: { color: '#3fb950', label: 'SATISFIED', description: 'Current-turn evidence allowed a grounded answer.' },
  CLARIFY: { color: '#d29922', label: 'CLARIFY_REQUIRED', description: 'The route stopped before answer synthesis and requires scope.' },
  DEFLECT: { color: '#ff7b72', label: 'DEFLECTED', description: 'The route failed closed and released no substantive answer.' },
  NO_MATCH: { color: 'var(--text-muted)', label: 'NO_MATCH', description: 'No admissible SPARTA memory or evidence route matched this turn.' },
  INCONCLUSIVE: { color: '#d29922', label: 'INCONCLUSIVE', description: 'The trace did not provide enough state to classify the final route.' },
}

const STATUS_COLORS: Record<TraceStatus, string> = {
  passed: '#3fb950',
  skipped: 'var(--text-muted)',
  blocked: '#ff7b72',
  pending: '#d29922',
}

const ENTITY_PATTERNS = /^[A-Z0-9]{2,}(?:-[A-Z0-9]+)*-\d+$/
const F36_ENTITY_PATTERN = /^F36B?(?:-[A-Z0-9]+)+-\d+$/i

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function asString(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return undefined
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return undefined
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .flatMap((item) => {
      if (typeof item === 'string' || typeof item === 'number') return [String(item)]
      if (!isRecord(item)) return []
      const extracted = pickRecord(item.extracted)
      const id = asString(item.id)
        ?? asString(item.control_id)
        ?? asString(item.entity)
        ?? asString(item.term)
        ?? asString(item.text)
        ?? asString(item.token)
        ?? asString(extracted?.text)
        ?? asString(item.name)
        ?? asString(item.label)
        ?? asString(item.qra_reference)
      return id ? [id] : []
    })
    .filter(Boolean)
}

function entityNodeList(value: unknown): string[] {
  if (!isRecord(value)) return []
  return stringList(value.anchors)
    .concat(stringList(value.validated_context))
    .concat(stringList(value.context_terms))
    .concat(stringList(value.suppressed))
    .concat(stringList(value.unsupported))
}

function nestedNodeList(value: unknown, key: string): string[] {
  if (!isRecord(value)) return []
  const nodes = pickRecord(value.nodes)
  return stringList(nodes?.[key])
}

function unique(items: string[]): string[] {
  return [...new Set(items.map((item) => item.trim()).filter(Boolean))]
}

function pickRecord(...values: unknown[]): UnknownRecord | undefined {
  return values.find(isRecord)
}

function extractReceiptState(receipt: UnknownRecord | undefined): string | undefined {
  const current = pickRecord(receipt?.answerability_receipt, receipt?.current_turn_answerability)
  return asString(current?.state)
}

function collectStringValues(value: unknown, values: string[] = []): string[] {
  if (typeof value === 'string' || typeof value === 'number') {
    values.push(String(value))
    return values
  }
  if (Array.isArray(value)) {
    for (const item of value) collectStringValues(item, values)
    return values
  }
  if (isRecord(value)) {
    for (const nested of Object.values(value)) collectStringValues(nested, values)
  }
  return values
}

function hasUnknownF36Entity(entityContext: UnknownRecord | undefined): boolean {
  if (!entityContext) return false
  const strings = collectStringValues(entityContext)
  const joined = strings.join(' ').toLowerCase()
  const hasF36Token = strings.some((item) => item
    .split(/\s+/)
    .some((token) => F36_ENTITY_PATTERN.test(token.replace(/[`,.;:()[\]{}]/g, ''))))
  if (!hasF36Token) return false
  const agentDecision = pickRecord(entityContext.agent_decision)
  const safeToAnswer = agentDecision?.safe_to_answer
  return (
    joined.includes('unknown_f36_entity')
    || joined.includes('fabricated_id')
    || joined.includes('unsupported')
    || entityContext.grounding_ok === false
    || (agentDecision?.needs_clarification === true && safeToAnswer === false)
  )
}

function deriveStopReason(meta: UnknownRecord, receipt?: UnknownRecord): string | undefined {
  const explicit = asString(meta.extractionStopReason) ?? asString(meta.extraction_stop_reason) ?? asString(meta.stopReason) ?? asString(meta.stop_reason)
  if (explicit) return explicit
  const entityContext = pickRecord(meta.entityContext, meta.entity_context, meta.extract_entities, meta.entities)
  const agentDecision = pickRecord(entityContext?.agent_decision)
  const reason = asString(agentDecision?.reason)
  if (reason) return reason
  if (hasUnknownF36Entity(entityContext)) return 'unknown_f36_entity'
  return asString(receipt?.deflection_reason)
}

function normalizeStatus(step?: ThinkingTraceLikeStep): TraceStatus {
  const status = String(step?.status ?? '').toLowerCase()
  if (status === 'completed' || status === 'done' || status === 'passed') return 'passed'
  if (status === 'failed' || status === 'blocked') return 'blocked'
  if (status === 'skipped') return 'skipped'
  return step ? 'pending' : 'pending'
}

function statusFromSteps(steps: ThinkingTraceLikeStep[], ids: string[]): TraceStatus {
  const step = steps.find((item) => ids.includes(item.id))
  return normalizeStatus(step)
}

function deriveTerminalState(meta: UnknownRecord, receipt?: UnknownRecord): TerminalState {
  const evidenceCase = pickRecord(meta.evidenceCase, meta.evidence_case)
  const responsePolicy = pickRecord(evidenceCase?.response_policy, meta.response_policy)
  const action = String(
    meta.responseAction
      ?? meta.response_action
      ?? receipt?.response_action
      ?? responsePolicy?.response_action
      ?? evidenceCase?.response_action
      ?? '',
  ).toLowerCase()
  const verdict = String(evidenceCase?.verdict ?? '').toLowerCase()
  const receiptState = String(extractReceiptState(receipt) ?? '').toUpperCase()
  const admissible = receipt?.admissible
  const bindingPassed = receipt?.binding_passed
  const entityContext = pickRecord(meta.entityContext, meta.entity_context, meta.extract_entities, meta.entities)
  const agentDecision = pickRecord(entityContext?.agent_decision)
  const decisionReason = String(agentDecision?.reason ?? '').toLowerCase()
  const needsClarification = agentDecision?.needs_clarification === true || agentDecision?.suggested_action === 'ask_clarifying_question'

  if (action === 'clarify' || receiptState === 'NEEDS_CLARIFICATION') return 'CLARIFY'
  if (decisionReason === 'unknown_f36_entity' || hasUnknownF36Entity(entityContext) || needsClarification) return 'CLARIFY'
  if (action === 'deflect' || receiptState === 'UNSUPPORTED' || admissible === false) return 'DEFLECT'
  if (receiptState === 'ANSWERABLE' && action === 'answer' && bindingPassed !== false) return 'ANSWER'
  if (action === 'answer' && (verdict === 'satisfied' || verdict === 'pass' || verdict === 'passed')) return 'ANSWER'
  if (action === 'answer' && verdict && verdict !== 'satisfied') return 'INCONCLUSIVE'
  if (receiptState === 'ERROR') return 'INCONCLUSIVE'
  if (action === 'answer') return 'INCONCLUSIVE'
  return 'NO_MATCH'
}

function deriveEntities(meta: UnknownRecord, spans: EvidenceCaseSpan[], evidenceCase?: EvidenceCaseData, receipt?: UnknownRecord): ExecutionTraceData['entities'] {
  const receiptAnswerability = pickRecord(receipt?.answerability_receipt, receipt?.current_turn_answerability)
  const entityContext = pickRecord(meta.entityContext, meta.entity_context, meta.extract_entities, meta.entities)
  const proofPacket = pickRecord(entityContext?.proof_packet, entityContext?.proofPacket)
  const intent = pickRecord(meta.intent, meta.memoryIntent, meta.memory_intent)
  const agentDecision = pickRecord(entityContext?.agent_decision)

  const spanAnchors = spans
    .map((span) => asString(span.text) ?? asString(span.name) ?? asString(span.id) ?? asString(span.control_id) ?? asString(span.entity))
    .filter((value): value is string => Boolean(value))
  const directEntities = stringList(meta.entities)
  const intentEntities = stringList(intent?.entities)
  const controlIds = stringList(evidenceCase?.control_ids)

  return {
    anchors: unique([
      ...spanAnchors.filter((item) => ENTITY_PATTERNS.test(item)),
      ...directEntities.filter((item) => ENTITY_PATTERNS.test(item)),
      ...intentEntities.filter((item) => ENTITY_PATTERNS.test(item)),
      ...nestedNodeList(entityContext, 'anchors').filter((item) => ENTITY_PATTERNS.test(item)),
      asString(agentDecision?.primary_entity_id) ?? '',
    ]),
    validated: unique([
      ...controlIds,
      ...stringList(receiptAnswerability?.supporting_evidence_refs),
      ...entityNodeList(entityContext?.nodes),
      ...nestedNodeList(entityContext, 'validated_context'),
      ...stringList(entityContext?.valid_entities),
    ]),
    candidates: unique([
      ...stringList(entityContext?.candidate_nodes),
      ...stringList(entityContext?.candidates),
      ...stringList(intent?.candidate_entities),
    ]),
    unresolved: unique([
      ...stringList(entityContext?.unresolved),
      ...stringList(entityContext?.unresolved_terms),
      ...nestedNodeList(entityContext, 'unsupported'),
      ...stringList(proofPacket?.unsupported_nodes),
      ...stringList(proofPacket?.unsupportedNodes),
      ...stringList(receiptAnswerability?.unresolved_items),
    ]),
    suppressed: unique([
      ...stringList(entityContext?.suppressed),
      ...stringList(entityContext?.suppressed_terms),
      ...nestedNodeList(entityContext, 'suppressed'),
      ...stringList(receiptAnswerability?.blocking_items),
      asString(receipt?.deflection_reason) ?? '',
    ]),
  }
}

function deriveEvidence(evidenceCase?: EvidenceCaseData, receipt?: UnknownRecord): ExecutionTraceData['evidence'] {
  if (!evidenceCase && !receipt) return null

  const rawClaims: unknown[] = Array.isArray(evidenceCase?.claims) ? evidenceCase.claims : []
  const claims = rawClaims.flatMap((claim, index) => {
    if (typeof claim === 'string') {
      return [{
        statement: claim,
        qra_reference: evidenceCase?.case_id ?? evidenceCase?.qraKey ?? `claim-${index + 1}`,
        grounded: Boolean(evidenceCase?.case_id || evidenceCase?.qraKey),
      }]
    }
    if (!isRecord(claim)) return []
    const statement = asString(claim.statement) ?? asString(claim.claim) ?? asString(claim.text)
    if (!statement) return []
    return [{
      statement,
      qra_reference: asString(claim.qra_reference) ?? asString(claim.source_ref) ?? asString(claim.source) ?? evidenceCase?.case_id ?? `claim-${index + 1}`,
      grounded: claim.grounded === true || claim.validated === true || Boolean(claim.qra_reference || claim.source_ref),
    }]
  })

  if (claims.length === 0) {
    const current = pickRecord(receipt?.answerability_receipt)
    const refs = stringList(current?.supporting_evidence_refs)
    for (const ref of refs) {
      claims.push({
        statement: `Current-turn answerability cites ${ref}.`,
        qra_reference: ref,
        grounded: true,
      })
    }
  }

  if (claims.length === 0) return null

  return {
    claims,
    verdict: evidenceCase?.verdict ?? asString(pickRecord(receipt?.answerability_receipt)?.state) ?? 'INCONCLUSIVE',
  }
}

export function deriveExecutionTraceData(args: {
  message: ChatMessage
  entitySpans?: EvidenceCaseSpan[]
}): ExecutionTraceData | null {
  const messageRecord = args.message as unknown as UnknownRecord
  const meta = {
    ...messageRecord,
    ...((args.message.metadata ?? {}) as UnknownRecord),
  }
  const explicitTrace = pickRecord(meta.executionTrace, meta.execution_trace, meta.traceData, meta.trace_data)
  if (explicitTrace) return explicitTrace as unknown as ExecutionTraceData

  const evidenceCase = pickRecord(meta.evidenceCase, meta.evidence_case) as unknown as EvidenceCaseData | undefined
  const evidenceResponsePolicy = pickRecord(evidenceCase?.response_policy)
  const receipt = pickRecord(meta.tauChatTurn, meta.tau_chat_turn, meta.receipt)
  const intent = pickRecord(meta.intent, meta.memoryIntent, meta.memory_intent)
  const responseAction = asString(meta.responseAction)
    ?? asString(meta.response_action)
    ?? asString(receipt?.response_action)
    ?? asString(evidenceResponsePolicy?.response_action)
    ?? asString(evidenceCase?.response_action)
  const steps = Array.isArray(args.message.thinkingTrace)
    ? args.message.thinkingTrace
    : Array.isArray(args.message.reasoningSteps)
      ? args.message.reasoningSteps
      : []

  if (!receipt && !intent && !evidenceCase && steps.length === 0 && !responseAction) return null

  const terminalState = deriveTerminalState(meta, receipt)
  const stopReason = deriveStopReason(meta, receipt)
  const extractionBlocked = stopReason === 'unknown_f36_entity'
  const route = responseAction
    ? responseAction.toUpperCase()
    : asString(intent?.action) ?? asString(intent?.route) ?? asString(meta.branch) ?? 'UNKNOWN'

  return {
    entities: deriveEntities(meta, args.entitySpans ?? [], evidenceCase, receipt),
    intent: {
      route,
      confidence: asNumber(intent?.confidence) ?? asNumber(intent?.recall_profile_confidence) ?? null,
      alternates: [
        ...stringList(intent?.top_intents),
        ...stringList(intent?.candidate_intents),
      ],
    },
    pipeline: {
      extract: extractionBlocked ? 'blocked' : statusFromSteps(steps, ['extracting-entities', 'extract_entities']),
      intent: extractionBlocked ? 'skipped' : statusFromSteps(steps, ['finalizing-intent', 'memory_recall', 'memory_intent']),
      route: extractionBlocked ? 'skipped' : receipt ? (terminalState === 'DEFLECT' ? 'blocked' : 'passed') : statusFromSteps(steps, ['getting-results']),
      evidence: terminalState === 'DEFLECT' || terminalState === 'CLARIFY'
        ? 'blocked'
        : evidenceCase || pickRecord(receipt?.answerability_receipt)
          ? 'passed'
          : statusFromSteps(steps, ['building-evidence-case', 'checking-gates']),
    },
    evidence: deriveEvidence(evidenceCase, receipt),
    terminalState,
    ...(stopReason ? { stopReason } : {}),
  }
}

export function ExecutionTrace({ traceData, qid = 'shared-chat:execution-trace' }: { traceData: ExecutionTraceData; qid?: string }): JSX.Element {
  const stateConfig = TRACE_STATES[traceData.terminalState] || TRACE_STATES.NO_MATCH
  const confidence = typeof traceData.intent.confidence === 'number'
    ? `${(traceData.intent.confidence * 100).toFixed(1)}%`
    : 'N/A'

  return (
    <section
      data-qid={qid}
      aria-label="Dynamic execution trace"
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr)',
        gap: 0,
        backgroundColor: 'var(--surface-sunken)',
        border: '1px solid var(--border-default)',
        borderRadius: 8,
        overflow: 'hidden',
        color: 'var(--text-primary)',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        margin: '10px 0 12px',
      }}
    >
      <aside data-qid={`${qid}:entity-rail`} style={{ backgroundColor: 'var(--surface-base)', borderBottom: '1px solid var(--border-subtle)', padding: 14 }}>
        <h4 data-qid={`${qid}:entity-rail:title`} style={titleStyle}>$extract-entities</h4>
        <div data-qid={`${qid}:entity-groups`} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <EntityGroup qid={`${qid}:anchors`} title="Anchors" items={traceData.entities.anchors} color="#58a6ff" bg="rgba(88, 166, 255, 0.1)" />
          <EntityGroup qid={`${qid}:validated`} title="Validated Context" items={traceData.entities.validated} color="#3fb950" bg="rgba(63, 185, 80, 0.1)" />
          <EntityGroup qid={`${qid}:candidates`} title="Candidate Nodes" items={traceData.entities.candidates} color="#c9d1d9" bg="var(--border-subtle)" />
          <EntityGroup qid={`${qid}:unresolved`} title="Unresolved" items={traceData.entities.unresolved} color="#d29922" bg="rgba(210, 153, 34, 0.1)" />
          <EntityGroup qid={`${qid}:suppressed`} title="Suppressed Terms" items={traceData.entities.suppressed} color="#ff7b72" bg="rgba(255, 123, 114, 0.1)" />
        </div>
      </aside>

      <div data-qid={`${qid}:pipeline-surface`} style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
        <div data-qid={`${qid}:gate-timeline`} style={{ display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 16, borderBottom: '1px solid var(--border-subtle)', overflowX: 'auto' }}>
          <PipelineStep qid={`${qid}:step:extract`} name="$extract" status={traceData.pipeline.extract} />
          <PipelineArrow qid={`${qid}:arrow:extract-intent`} />
          <PipelineStep qid={`${qid}:step:intent`} name="$intent" status={traceData.pipeline.intent} />
          <PipelineArrow qid={`${qid}:arrow:intent-route`} />
          <PipelineStep qid={`${qid}:step:route`} name="$route" status={traceData.pipeline.route} />
          <PipelineArrow qid={`${qid}:arrow:route-evidence`} />
          <PipelineStep qid={`${qid}:step:evidence`} name="$evidence" status={traceData.pipeline.evidence} />
        </div>

        <div data-qid={`${qid}:state-grid`} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
          <div data-qid={`${qid}:intent-card`} style={cardStyle}>
            <h4 data-qid={`${qid}:intent:title`} style={titleStyle}>$memory intent</h4>
            <TraceMetric qid={`${qid}:intent:route`} label="Chosen Route" value={traceData.intent.route} color="#58a6ff" />
            <TraceMetric qid={`${qid}:intent:confidence`} label="Confidence" value={confidence} color={typeof traceData.intent.confidence === 'number' && traceData.intent.confidence > 0.8 ? '#3fb950' : '#d29922'} />
            <div data-qid={`${qid}:intent:alternates`} style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 12, paddingTop: 8, borderTop: '1px dashed var(--border-default)' }}>
              Alt Intents: {traceData.intent.alternates.length ? traceData.intent.alternates.join(', ') : 'none recorded'}
            </div>
          </div>

          <div
            data-qid={`${qid}:terminal-state`}
            style={{
              backgroundColor: 'rgba(13, 17, 23, 0.5)',
              border: `1px solid ${stateConfig.color}`,
              borderRadius: 6,
              padding: 12,
              boxShadow: `inset 4px 0 0 ${stateConfig.color}`,
            }}
          >
            <h4 data-qid={`${qid}:terminal-state:title`} style={titleStyle}>Terminal State</h4>
            <div data-qid={`${qid}:terminal-state:value`} style={{ fontSize: 14, fontWeight: 800, color: stateConfig.color, fontFamily: '"SF Mono", Consolas, monospace' }}>
              {traceData.terminalState}
            </div>
            <div data-qid={`${qid}:terminal-state:label`} style={{ marginTop: 4, fontSize: 10, color: stateConfig.color, fontFamily: '"SF Mono", Consolas, monospace' }}>
              {stateConfig.label}
            </div>
            <div data-qid={`${qid}:terminal-state:description`} style={{ marginTop: 8, fontSize: 12, color: '#c9d1d9', lineHeight: 1.45 }}>
              {stateConfig.description}
            </div>
            {traceData.stopReason ? (
              <TraceMetric qid={`${qid}:terminal-state:reason`} label="Stop Reason" value={traceData.stopReason} color={stateConfig.color} />
            ) : null}
          </div>
        </div>

        {traceData.terminalState === 'ANSWER' && traceData.evidence ? (
          <div data-qid={`${qid}:evidence-case`} style={{ marginTop: 8 }}>
            <h4 data-qid={`${qid}:evidence-case:title`} style={titleStyle}>$create-evidence-case (CAE / QRA)</h4>
            <div data-qid={`${qid}:evidence-case:claims`} style={{ display: 'flex', flexDirection: 'column', gap: 2, fontFamily: '"SF Mono", Consolas, monospace', fontSize: 12 }}>
              {traceData.evidence.claims.map((claim, index) => (
                <div key={`${claim.qra_reference}-${index}`} data-qid={`${qid}:evidence-case:claim:${index}`} style={{ display: 'flex', flexDirection: 'column' }}>
                  <div data-qid={`${qid}:evidence-case:claim:${index}:statement`} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', backgroundColor: 'var(--surface-raised)', borderRadius: 4 }}>
                    <span style={{ color: 'var(--text-muted)' }}>|- CLAIM:</span>
                    <span style={{ color: 'var(--text-primary)' }}>{claim.statement}</span>
                  </div>
                  <div data-qid={`${qid}:evidence-case:claim:${index}:grounding`} style={{ padding: '4px 8px 4px 24px', borderLeft: '1px solid var(--border-default)', marginLeft: 12 }}>
                    <span style={{ color: 'var(--text-muted)', marginRight: 8 }}>+ GROUNDING:</span>
                    <span style={{ color: claim.grounded ? '#3fb950' : '#ff7b72' }}>
                      {claim.qra_reference} {claim.grounded ? '(VALIDATED)' : '(UNSUPPORTED)'}
                    </span>
                  </div>
                </div>
              ))}
              <div data-qid={`${qid}:evidence-case:verdict`} style={{ marginTop: 12, padding: 8, backgroundColor: 'rgba(63, 185, 80, 0.1)', border: '1px solid #3fb950', borderRadius: 4, color: '#3fb950', fontWeight: 800 }}>
                VERDICT: {traceData.evidence.verdict}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}

const titleStyle: React.CSSProperties = {
  margin: '0 0 12px 0',
  fontSize: 11,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
}

const cardStyle: React.CSSProperties = {
  backgroundColor: 'var(--surface-raised)',
  border: '1px solid var(--border-default)',
  borderRadius: 6,
  padding: 12,
}

function TraceMetric({ qid, label, value, color }: { qid: string; label: string; value: string; color: string }): JSX.Element {
  return (
    <div data-qid={qid} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
      <span data-qid={`${qid}:label`} style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}:</span>
      <span data-qid={`${qid}:value`} style={{ fontSize: 12, fontFamily: '"SF Mono", Consolas, monospace', color, textAlign: 'right' }}>{value}</span>
    </div>
  )
}

function EntityGroup({ qid, title, items, color, bg }: { qid: string; title: string; items: string[]; color: string; bg: string }): JSX.Element | null {
  if (!items || items.length === 0) return null
  return (
    <div data-qid={qid}>
      <div data-qid={`${qid}:title`} style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>{title}</div>
      <div data-qid={`${qid}:items`} style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {items.map((item, index) => (
          <span
            key={`${item}-${index}`}
            data-qid={`${qid}:item:${index}`}
            title={item}
            style={{
              backgroundColor: bg,
              color,
              padding: '2px 6px',
              borderRadius: 4,
              fontSize: 11,
              fontFamily: '"SF Mono", Consolas, monospace',
              border: `1px solid ${color}40`,
              maxWidth: '100%',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  )
}

function PipelineStep({ qid, name, status }: { qid: string; name: string; status: TraceStatus }): JSX.Element {
  const color = STATUS_COLORS[status]
  return (
    <div data-qid={qid} data-status={status} style={{ display: 'flex', alignItems: 'center', gap: 4, color, fontSize: 11, fontFamily: '"SF Mono", Consolas, monospace', flexShrink: 0 }}>
      <span data-qid={`${qid}:icon`} style={{ display: 'inline-flex', justifyContent: 'center', alignItems: 'center', width: 12, height: 12, borderRadius: '50%', backgroundColor: `${color}20`, border: `1px solid ${color}`, fontSize: 9 }}>
        {status === 'passed' && '✓'}
        {status === 'blocked' && '×'}
        {status === 'skipped' && '-'}
        {status === 'pending' && '?'}
      </span>
      <span data-qid={`${qid}:name`}>{name}</span>
    </div>
  )
}

function PipelineArrow({ qid }: { qid: string }): JSX.Element {
  return <span data-qid={qid} style={{ color: 'var(--border-default)', fontSize: 12, flexShrink: 0 }}>→</span>
}

export default ExecutionTrace
