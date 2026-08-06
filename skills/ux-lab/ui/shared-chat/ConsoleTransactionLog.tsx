import { useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Database,
  AlertTriangle,
} from 'lucide-react'
import type { EvidenceCaseData } from './types'
import ThinkingTrace from './ThinkingTrace'
import { useRegisterAction } from './_support/useRegisterAction'
import { MemoryPipelineDag } from './MemoryPipelineDag'

export type ConsoleTraceStep = {
  id?: string
  label?: string
  status?: string
  detail?: string
  icon?: string
  data?: unknown
}

const palette = {
  bg: '#0d0d0f',
  panel: 'rgba(15,23,42,0.4)',
  panelStrong: 'rgba(255,255,255,0.025)',
  border: 'rgba(51,65,85,0.6)',
  borderStrong: 'rgba(255,255,255,0.08)',
  text: '#cbd5e1',
  muted: '#94a3b8',
  dim: '#64748b',
  accent: '#7dd3fc',
  blue: '#38bdf8',
  warn: '#d29922',
  fail: '#ff7b72',
}

function qidToken(value: string, fallback = 'item'): string {
  const token = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
  return token || fallback
}

export function ConsoleExecutionTraceLog({
  steps,
  receiptId,
  isGenerating = false,
}: {
  steps: ConsoleTraceStep[]
  receiptId?: string
  isGenerating?: boolean
}): JSX.Element {
  const traceSteps = steps.map((step, index) => ({
    id: step.id ?? `console-step-${index}`,
    label: step.label ?? consoleStepCommand(step),
    status: step.status,
    detail: step.detail,
    icon: step.icon,
    data: step.data,
  }))

  return (
    <section
      data-qid="shared-chat:daemon-execution-trace"
      style={{
        marginBottom: 16,
        fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        minWidth: 0,
        maxWidth: '100%',
        overflow: 'visible',
      }}
    >
      <ThinkingTrace
        steps={traceSteps}
        label="Show thinking"
        currentLabel={isGenerating ? 'Thinking...' : undefined}
        leadingIcon="none"
        placement="footer"
        displayMode="full"
        defaultOpen
        isStreaming={isGenerating}
        dataQid="shared-chat:daemon-execution-trace"
      />
      <MemoryPipelineDag steps={traceSteps} receiptId={receiptId} />
      {receiptId ? (
        <span style={{ display: 'none' }} data-qid="shared-chat:daemon-execution-trace:receipt">
          {receiptId}
        </span>
      ) : null}
    </section>
  )
}

export function ConsoleEvidenceCaseBlock({ data, isGenerating = false }: { data: EvidenceCaseData; isGenerating?: boolean }): JSX.Element {
  const memoryAnswer = data.memory_answer
  const answerBlocks = Array.isArray(memoryAnswer?.answer_blocks)
    ? memoryAnswer.answer_blocks
    : Array.isArray(data.answer_blocks)
      ? data.answer_blocks
      : []
  const answerText = stripCitationListEcho(data.answer ?? data.description ?? '')

  return (
    <>
      {answerBlocks.length > 0
        ? <ConsoleMemoryAnswer data={data} />
        : answerText
          ? <ConsoleAgentResponse answer={answerText} isGenerating={isGenerating} />
          : null}
      <ConsoleEvidencePayload data={data} />
    </>
  )
}

function ConsoleMemoryAnswer({ data }: { data: EvidenceCaseData }): JSX.Element {
  const memoryAnswer = data.memory_answer
  const answerBlocks = Array.isArray(memoryAnswer?.answer_blocks)
    ? memoryAnswer.answer_blocks
    : Array.isArray(data.answer_blocks)
      ? data.answer_blocks
      : []
  const missingArtifacts = Array.isArray(memoryAnswer?.missing_artifacts) ? memoryAnswer.missing_artifacts : []
  const status = String(memoryAnswer?.status ?? '').toLowerCase()

  return (
    <section
      data-qid="console-chat.answer"
      data-answer-status={status || undefined}
      style={{
        marginBottom: 16,
        display: 'grid',
        gap: 12,
        fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}
    >
      {answerBlocks.map((block, index) => {
        const type = qidToken(String(block.type ?? `block-${index + 1}`), `block-${index + 1}`)
        return (
          <div
            key={`${type}-${index}`}
            data-qid={`console-chat.answer.${type}`}
            style={{
              display: 'grid',
              gap: 5,
              paddingBottom: index < answerBlocks.length - 1 ? 8 : 0,
              borderBottom: index < answerBlocks.length - 1 ? '1px solid rgba(148, 163, 184, 0.12)' : 0,
            }}
          >
            <div style={{ color: '#EDEDED', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap', minWidth: 0 }}>
              {String(block.text ?? '')}
            </div>
          </div>
        )
      })}
      {status === 'insufficient_evidence' && missingArtifacts.length > 0 ? (
        <div
          data-qid="console-chat.answer.evidence-gap"
          style={{
            color: '#facc15',
            fontSize: 13,
            lineHeight: 1.45,
            padding: '10px 12px',
            border: '1px solid rgba(250, 204, 21, 0.26)',
            borderRadius: 6,
            background: 'rgba(113, 63, 18, 0.15)',
          }}
        >
          No approved relationship was found in the authorized scope.
        </div>
      ) : null}
    </section>
  )
}

export function ConsoleAgentResponse({ answer }: { answer: string; isGenerating?: boolean }): JSX.Element {
  const normalizedAnswer = dedupeRepeatedParagraphs(answer)
  const isTerminalFailure = isTerminalFailureText(normalizedAnswer)

  if (isTerminalFailure) {
    return <ConsoleTerminalAlert message={normalizedAnswer} />
  }

  return (
    <section
      data-qid="shared-chat:daemon-response"
      style={{
        marginBottom: 16,
        fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}
    >
      <div style={{ color: '#EDEDED', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap', flex: 1, minWidth: 0 }}>
        {normalizedAnswer}
      </div>
    </section>
  )
}

export function ConsoleTerminalAlert({ message }: { message: string }): JSX.Element {
  return (
    <section
      data-qid="shared-chat:terminal-failure-alert"
      style={{
        marginBottom: 16,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
        padding: '12px 14px',
        borderRadius: 10,
        border: '1px solid rgba(248, 113, 113, 0.42)',
        background: 'rgba(127, 29, 29, 0.18)',
        color: '#fecaca',
        fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}
    >
      <div
        aria-hidden="true"
        style={{
          width: 24,
          height: 24,
          borderRadius: '50%',
          background: 'rgba(248, 113, 113, 0.16)',
          color: '#f87171',
          display: 'grid',
          placeItems: 'center',
          flexShrink: 0,
          marginTop: 1,
        }}
      >
        <AlertTriangle size={15} aria-hidden="true" />
      </div>
      <div style={{ display: 'grid', gap: 5, minWidth: 0 }}>
        <div style={{ color: '#fca5a5', fontSize: 12, fontWeight: 800, letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Terminal Failure
        </div>
        <div style={{ color: '#f8fafc', fontSize: 14, lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>
          {message}
        </div>
      </div>
    </section>
  )
}

export function ConsoleEvidencePayload({ data }: { data: EvidenceCaseData }): JSX.Element {
  const [isEvidenceExpanded, setEvidenceExpanded] = useState(false)
  useRegisterAction('shared-chat:evidence-case-terminal:toggle', {
    app: 'shared-chat',
    action: 'SHARED_CHAT_TOGGLE_SOURCES_EVIDENCE',
    label: 'Toggle sources and evidence',
    description: 'Expand or collapse the sources and evidence attached to this answer',
  })
  useRegisterAction('console-chat:action:open-evidence', {
    app: 'sparta-explorer',
    action: 'open-evidence',
    label: 'Open evidence',
    description: 'Open the bounded evidence object referenced by the memory answer',
  })
  useRegisterAction('console-chat:action:open-control', {
    app: 'sparta-explorer',
    action: 'open-control',
    label: 'Open control',
    description: 'Open the bounded control object referenced by the memory answer',
  })
  useRegisterAction('console-chat:action:create-evidence-case', {
    app: 'sparta-explorer',
    action: 'create-evidence-case',
    label: 'Create evidence case',
    description: 'Create an evidence case from bounded canonical evidence references',
  })
  const receipt = data.case_id ?? data.qraKey ?? data.bound_artifact ?? data.artifact?.name ?? 'unbound'
  const rows = evidenceArtifactRows(data)

  return (
    <section
      data-qid="console-chat.evidence"
      style={{
        marginTop: 2,
        marginBottom: 12,
        border: '1px solid rgba(148, 163, 184, 0.14)',
        borderRadius: 8,
        display: 'block',
        overflow: 'hidden',
        background: 'rgba(15, 23, 42, 0.22)',
        fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}
    >
      <button
        type="button"
        data-qid="shared-chat:evidence-case-terminal:toggle"
        data-qs-action="SHARED_CHAT_TOGGLE_SOURCES_EVIDENCE"
        onClick={() => setEvidenceExpanded((value) => !value)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          width: '100%',
          padding: '10px 12px',
          background: 'transparent',
          border: 0,
          color: '#EDEDED',
          fontSize: 12,
          cursor: 'pointer',
          transition: 'background-color 0.2s',
        }}
        onMouseEnter={(event) => {
          event.currentTarget.style.backgroundColor = 'rgba(15, 23, 42, 0.45)'
        }}
        onMouseLeave={(event) => {
          event.currentTarget.style.backgroundColor = 'transparent'
        }}
        title={isEvidenceExpanded ? 'Hide sources and evidence' : 'Show sources and evidence'}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <Database size={14} color="#94a3b8" aria-hidden="true" />
          <span style={{ fontWeight: 500, whiteSpace: 'nowrap' }}>Sources & Evidence</span>
          <span style={{ background: 'rgba(148, 163, 184, 0.10)', padding: '2px 8px', borderRadius: 12, fontSize: 11, color: '#94a3b8', marginLeft: 2 }}>
            {rows.length}
          </span>
          <span style={{ color: palette.dim, fontSize: 10, fontFamily: 'var(--font-mono, monospace)', fontWeight: 400, opacity: 0.75, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            ID: {String(receipt).slice(0, 12)}
          </span>
        </span>
        {isEvidenceExpanded ? <ChevronDown size={14} color="#888" aria-hidden="true" /> : <ChevronRight size={14} color="#888" aria-hidden="true" />}
      </button>

      {isEvidenceExpanded && rows.length > 0 ? (
        <div
          className="terminal-scrollbar"
          data-qid="shared-chat:evidence-artifacts:buffer"
          style={{
            display: 'grid',
            gap: 8,
            overflowY: 'visible',
            padding: '12px 16px',
            background: '#0A0A0A',
            borderTop: '1px solid #222',
          }}
        >
          {rows.map((row, index) => (
            <div
              key={`${row.ref}-${index}`}
              data-qid={`shared-chat:evidence-artifact:${index + 1}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: 0,
                background: 'transparent',
                borderRadius: 4,
                minWidth: 0,
              }}
            >
              <span style={{ background: '#222', color: '#EDEDED', padding: '2px 6px', borderRadius: 4, fontSize: 10, fontWeight: 600, flexShrink: 0 }}>
                {index + 1}
              </span>
              <span title={row.summary} style={{ color: '#888', fontSize: 12, fontFamily: 'var(--font-mono, monospace)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {row.ref}
              </span>
              {row.action ? (
                <button
                  type="button"
                  data-qs-action={row.action}
                  data-evidence-id={row.targetRef}
                  title={`Open ${row.ref}`}
                  style={{
                    marginLeft: 'auto',
                    minWidth: 44,
                    minHeight: 32,
                    border: '1px solid rgba(148, 163, 184, 0.24)',
                    borderRadius: 6,
                    background: 'rgba(15, 23, 42, 0.45)',
                    color: '#cbd5e1',
                    cursor: 'pointer',
                    fontSize: 11,
                    fontWeight: 700,
                  }}
                >
                  Open
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : isEvidenceExpanded ? (
        <div style={{ color: palette.dim, fontSize: 12 }}>No attached evidence artifacts.</div>
      ) : null}
    </section>
  )
}

function consoleStepCommand(step: ConsoleTraceStep): string {
  const id = String(step.id ?? '').toLowerCase()
  if (id.includes('extract')) return '$extract-entities'
  if (id.includes('watch-scene')) return '$watch_content_recall'
  if (id.includes('memory') || id.includes('recall')) return '$memory_intent'
  if (id.includes('gate') || id.includes('checking')) return '$gate_check'
  if (id.includes('evidence')) return '$create-evidence-case'
  if (id.includes('result')) return '$memory_result_fetch'
  if (id.includes('answer')) return '$response_released'
  if (id.includes('aql')) return '$aql-query'
  if (id.includes('voice') || id.includes('chatterbox')) return '$embry_voice_render'
  return `$${qidToken(step.label ?? step.id ?? 'step', 'step')}`
}

function evidenceArtifactRows(data: EvidenceCaseData): Array<{ ref: string; summary: string; action?: string; targetRef?: string }> {
  const memoryCitations = Array.isArray(data.memory_answer?.citations) ? data.memory_answer.citations : []
  if (memoryCitations.length > 0) {
    const actions = Array.isArray(data.memory_answer?.actions) ? data.memory_answer.actions : []
    return memoryCitations.map((citation) => {
      const canonicalRef = String(citation.canonical_ref ?? citation.id ?? 'evidence')
      const action = actions.find((item) => item.target_ref === canonicalRef)?.name
      return {
        ref: String(citation.title ?? canonicalRef),
        summary: String(citation.source_locator ?? canonicalRef),
        action: action ? String(action) : canonicalRef.includes('sparta_controls/') ? 'open-control' : 'open-evidence',
        targetRef: canonicalRef,
      }
    })
  }
  const citations = Array.isArray(data.citations) ? data.citations : []
  const claims = Array.isArray(data.claims) ? data.claims : []
  if (citations.length > 0) {
    return citations.map((citation, index) => ({
      ref: citation,
      summary: claims[index] ?? data.gate_trace?.[index]?.detail ?? 'source-page excerpt pending',
    }))
  }
  if (claims.length > 0) {
    return claims.map((claim, index) => ({
      ref: data.case_id ?? data.qraKey ?? `claim-${index + 1}`,
      summary: claim,
    }))
  }
  const gates = data.gate_trace ?? data.metadata?.gate_trace ?? []
  return gates.map((gate, index) => ({
    ref: gate.gate || `gate-${index + 1}`,
    summary: gate.detail || (gate.passed ? 'gate passed' : 'gate failed'),
  }))
}

export function stripCitationListEcho(content: string): string {
  if (!content) return content
  return dedupeRepeatedParagraphs(content)
    .replace(/\n?\s*Top cited evidence:\s*[\s\S]*$/i, '')
    .replace(/\n?\s*Cited artifacts:\s*[\s\S]*$/i, '')
    .trimEnd()
}

export function dedupeRepeatedParagraphs(content: string): string {
  const paragraphs = content.split(/\n{2,}/)
  const seen = new Set<string>()
  const next: string[] = []
  for (const paragraph of paragraphs) {
    const normalized = paragraph.replace(/\s+/g, ' ').trim().toLowerCase()
    if (!normalized) {
      next.push(paragraph)
      continue
    }
    if (seen.has(normalized)) continue
    seen.add(normalized)
    next.push(paragraph)
  }
  return next.join('\n\n')
}

export function isTerminalFailureText(content: string): boolean {
  return /could not complete|answerability check|entity grounding failed|0\/\d+\s+gate\(s\)\s+passed|gate\(s\)\s+failed|process stopped/i.test(content)
}
