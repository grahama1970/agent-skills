import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useRegisterAction } from './_support/useRegisterAction'
import type { ChatMessage, UnknownRecord } from './memory-turn'
import { deriveExecutionTraceData } from './ExecutionTrace'
import { MarkdownRenderer } from './MarkdownRenderer'
import type { EvidenceCaseData, EvidenceCaseSpan } from './types'

interface CompactChatInterfaceProps {
  messages: ChatMessage[]
  isProcessing: boolean
  onSubmit: (text: string) => void | Promise<void>
  onViewTrace?: (payload: UnknownRecord) => void
  connectionState?: 'CONNECTING' | 'ONLINE' | 'OFFLINE'
  qid?: string
  placeholder?: string
}

export default function CompactChatInterface({
  messages,
  isProcessing,
  onSubmit,
  onViewTrace,
  connectionState = 'ONLINE',
  qid = 'shared-chat:compact-terminal',
  placeholder = "Issue command (try 'analyze')...",
}: CompactChatInterfaceProps): JSX.Element {
  const [input, setInput] = useState('')
  const [isInputFocused, setIsInputFocused] = useState(false)
  const endOfFeedRef = useRef<HTMLDivElement | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useRegisterAction(`${qid}:input`, {
    app: 'shared-chat',
    action: 'COMPACT_CHAT_DRAFT',
    label: 'Draft compact chat command',
    description: 'Type a command into the compact terminal chat composer',
  })
  useRegisterAction(`${qid}:view-trace`, {
    app: 'shared-chat',
    action: 'COMPACT_CHAT_VIEW_TRACE',
    label: 'View compact chat trace',
    description: 'Open the selected compact terminal trace payload',
  })

  useEffect(() => {
    endOfFeedRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isProcessing])

  useEffect(() => {
    if (!textareaRef.current) return
    textareaRef.current.style.height = '24px'
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`
  }, [input])

  const canAcceptInput = connectionState === 'ONLINE' && !isProcessing

  const submit = async () => {
    const trimmed = input.trim()
    if (!trimmed || !canAcceptInput) return
    setInput('')
    await onSubmit(trimmed)
  }

  const renderedMessages = useMemo(() => messages, [messages])

  return (
    <div data-qid={qid} style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div
        className="custom-scrollbar"
        data-qid={`${qid}:messages`}
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          backgroundColor: 'transparent',
        }}
      >
        {renderedMessages.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.5, fontStyle: 'italic' }}>
            Console initialized. Awaiting telemetry input.
          </div>
        )}

        {renderedMessages.map((message, index) => (
          <CompactMessage key={message.id ?? `${message.role}-${index}`} message={message} qid={`${qid}:message:${index}`} onViewTrace={onViewTrace} />
        ))}

        {isProcessing && (
          <div
            data-qid={`${qid}:processing`}
            style={{
              display: 'flex',
              gap: 12,
              color: 'var(--text-muted)',
              fontSize: 12,
              fontFamily: '"SF Mono", Consolas, monospace',
            }}
          >
            <div style={{ width: 2, backgroundColor: 'var(--border-default)', flexShrink: 0 }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingBottom: 8 }}>
              <div style={{ opacity: 0.5, animation: 'compact-chat-console-reveal 0.1s ease-out forwards' }}>
                ❯ Initiating protocol scan...
              </div>
              <div style={{ opacity: 0, animation: 'compact-chat-console-reveal 0.1s ease-out forwards', animationDelay: '0.6s' }}>
                ❯ Cross-referencing telemetry logs...
              </div>
              <div
                style={{
                  opacity: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  color: '#58a6ff',
                  animation: 'compact-chat-console-reveal 0.1s ease-out forwards',
                  animationDelay: '1.2s',
                }}
              >
                <span>❯ Compiling payload</span>
                <span
                  style={{
                    width: 6,
                    height: 12,
                    backgroundColor: '#58a6ff',
                    display: 'inline-block',
                    animation: 'compact-chat-blink 1s step-end infinite',
                  }}
                />
              </div>
            </div>
          </div>
        )}

        <style>{`
          @keyframes compact-chat-blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0; }
          }
          @keyframes compact-chat-console-reveal {
            0% { opacity: 0; transform: translateY(2px); }
            100% { opacity: 1; transform: translateY(0); }
          }
        `}</style>
        <div ref={endOfFeedRef} data-qid={`${qid}:feed-end`} style={{ height: 1, width: '100%', flexShrink: 0 }} />
      </div>

      <div
        style={{
          borderTop: '1px solid',
          borderColor: isInputFocused ? '#58a6ff' : 'var(--border-subtle)',
          padding: '12px 16px',
          backgroundColor: 'var(--surface-base)',
          flexShrink: 0,
          display: 'flex',
          gap: 8,
          alignItems: 'flex-end',
          borderRadius: 0,
          transition: 'border-color 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
          position: 'relative',
          zIndex: 1,
        }}
      >
        <span style={{ color: canAcceptInput ? '#58a6ff' : '#484f58', fontSize: 14, paddingBottom: 2, userSelect: 'none', transition: 'color 0.2s' }}>
          ❯
        </span>
        <textarea
          ref={textareaRef}
          data-qid={`${qid}:input`}
          data-qs-action="COMPACT_CHAT_DRAFT"
          title="Console command input"
          value={input}
          onChange={(event) => setInput(event.currentTarget.value)}
          onFocus={() => setIsInputFocused(true)}
          onBlur={() => setIsInputFocused(false)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void submit()
            }
          }}
          placeholder={isProcessing ? 'Processing...' : connectionState === 'OFFLINE' ? 'Console offline...' : connectionState === 'CONNECTING' ? 'Connecting...' : placeholder}
          disabled={!canAcceptInput}
          rows={1}
          style={{
            flex: 1,
            backgroundColor: 'transparent',
            border: 'none',
            color: 'var(--text-primary)',
            caretColor: 'var(--text-primary)',
            fontSize: 13,
            lineHeight: 1.5,
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
            resize: 'none',
            outline: 'none',
            boxShadow: 'none',
            padding: 0,
            maxHeight: 120,
            overflowY: 'auto',
          }}
        />
      </div>
    </div>
  )
}

function CompactMessage({ message, qid, onViewTrace }: { message: ChatMessage; qid: string; onViewTrace?: (payload: UnknownRecord) => void }): JSX.Element {
  const isUser = message.role === 'user'
  const meta = (message.metadata ?? {}) as UnknownRecord
  const evidenceCase = (meta.evidenceCase ?? meta.evidence_case ?? message.evidenceCase) as EvidenceCaseData | undefined
  const entitySpans = (Array.isArray(meta.entitySpans)
    ? meta.entitySpans
    : Array.isArray(meta.entity_spans)
      ? meta.entity_spans
      : Array.isArray(evidenceCase?.spans)
        ? evidenceCase.spans
        : []) as EvidenceCaseSpan[]
  const traceData = !isUser ? deriveExecutionTraceData({ message }) : null
  const hasStructuredEvidence = Boolean(evidenceCase)
  const timestamp = formatMessageTime(message)
  const tracePayload: UnknownRecord = {
    caseId: evidenceCase?.case_id ?? evidenceCase?.qraKey ?? message.id ?? qid,
    timestamp: message.createdAt ?? message.timestamp ?? Date.now(),
    role: message.role,
    content: message.content,
    traceData,
    evidenceCase,
    metadata: message.metadata,
    reasoningSteps: message.reasoningSteps ?? message.thinkingTrace,
    entities: message.entities,
    verdict: message.verdict,
  }

  if (isUser) {
    return (
      <div data-qid={qid} data-role="user" style={{ display: 'flex', gap: 8, color: 'var(--text-primary)', fontSize: 13, lineHeight: 1.5 }}>
        <span style={{ color: '#58a6ff', userSelect: 'none', flexShrink: 0 }}>❯</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ color: '#484f58', fontFamily: '"SF Mono", Consolas, monospace', fontSize: 10, marginBottom: 2 }}>
            OPERATOR {timestamp}
          </div>
          <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            <MarkdownRenderer content={message.content} entitySpans={entitySpans} sidebarMode />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div data-qid={qid} data-role={message.role} style={{ display: 'flex', gap: 10, color: message.role === 'system' ? 'var(--text-muted)' : '#c9d1d9', fontSize: 13, lineHeight: 1.5 }}>
      <div style={{ width: 2, backgroundColor: message.role === 'system' ? 'transparent' : 'var(--border-default)', flexShrink: 0, marginTop: 4, marginBottom: 4 }} />
      <div style={{ minWidth: 0, flex: 1, fontStyle: message.role === 'system' ? 'italic' : 'normal' }}>
        <div style={{ color: '#484f58', fontFamily: '"SF Mono", Consolas, monospace', fontSize: 10, marginBottom: 4 }}>
          {message.role === 'system' ? 'SYSTEM' : 'SPARTA'} {timestamp}
        </div>
        {evidenceCase && (
          <CompactEvidenceBlock
            data={evidenceCase}
            qid={`${qid}:evidence-case`}
            onViewTrace={onViewTrace ? () => onViewTrace(tracePayload) : undefined}
          />
        )}
        {!hasStructuredEvidence && onViewTrace && traceData && (
          <TraceActionControl data-qid={`${qid}:view-trace`} qid={`${qid}:view-trace`} onClick={() => onViewTrace(tracePayload)} />
        )}
        {!hasStructuredEvidence && message.content && <MarkdownRenderer content={message.content} sidebarMode />}
      </div>
    </div>
  )
}

function CompactEvidenceBlock({ data, qid, onViewTrace }: { data: EvidenceCaseData; qid: string; onViewTrace?: () => void }): JSX.Element {
  const verdict = String(data.verdict || 'INCONCLUSIVE').toUpperCase()
  const action = String(data.response_policy?.response_action ?? data.response_action ?? 'clarify').toUpperCase()
  const severity = verdict === 'SATISFIED' && action === 'ANSWER' ? 'SATISFIED' : action === 'DEFLECT' ? 'DEFLECTED' : 'CLARIFY'
  const severityColor = severity === 'SATISFIED' ? '#3fb950' : severity === 'DEFLECTED' ? '#ff7b72' : '#f2cc60'
  const nodes = data.control_ids?.length
    ? data.control_ids
    : (data.glossary ?? []).map(term => term.term).filter(Boolean).slice(0, 6)
  const claims = data.claims?.length ? data.claims : data.answer ? [data.answer] : ['No substantive answer released without an evidence-case answer route.']

  useRegisterAction(`${qid}:view-trace`, {
    app: 'shared-chat',
    action: 'COMPACT_CHAT_VIEW_TRACE',
    label: 'View evidence execution trace',
    description: 'Open the full execution trace for this evidence case',
  })
  useRegisterAction(`${qid}:execute-isolate`, {
    app: 'shared-chat',
    action: 'COMPACT_CHAT_ISOLATE_NODES',
    label: 'Isolate evidence nodes',
    description: 'Isolate affected evidence nodes from this compact chat evidence case',
  })

  return (
    <div
      data-qid={qid}
      style={{
        border: '1px solid var(--border-default)',
        backgroundColor: 'var(--surface-base)',
        padding: 12,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        fontFamily: '"SF Mono", Consolas, "Liberation Mono", Menlo, Courier, monospace',
        fontSize: 11,
        marginTop: 10,
      }}
    >
      <div data-qid={`${qid}:header`} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 8, gap: 10 }}>
        <span style={{ color: 'var(--text-muted)', minWidth: 0 }}>
          CASE: <span style={{ color: 'var(--text-primary)' }}>{data.case_id ?? data.qraKey ?? 'EC-PENDING'}</span>
        </span>
        <span
          data-qid={`${qid}:severity`}
          style={{
            color: severityColor,
            backgroundColor: `${severityColor}1a`,
            border: `1px solid ${severityColor}66`,
            padding: '2px 6px',
            fontWeight: 700,
            letterSpacing: '0.5px',
            flexShrink: 0,
          }}
        >
          {severity}
        </span>
      </div>

      <div data-qid={`${qid}:nodes`} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ color: 'var(--text-muted)' }}>AFFECTED_NODES:</span>
        {nodes.length ? nodes.map(node => (
          <div key={node} style={{ color: '#58a6ff', padding: '4px 8px', backgroundColor: 'rgba(88, 166, 255, 0.05)', border: '1px solid rgba(88, 166, 255, 0.18)' }}>
            {node}
          </div>
        )) : (
          <div style={{ color: '#d29922', padding: '4px 8px', backgroundColor: 'rgba(210, 153, 34, 0.08)', border: '1px solid rgba(210, 153, 34, 0.22)' }}>
            NO_GROUNDED_NODES
          </div>
        )}
      </div>

      <div data-qid={`${qid}:claims`} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ color: 'var(--text-muted)' }}>CLAIMS:</span>
        {claims.slice(0, 3).map((claim, index) => (
          <div key={`${index}-${claim}`} style={{ color: '#c9d1d9', lineHeight: 1.45, borderLeft: '2px solid var(--border-default)', paddingLeft: 8 }}>
            {claim}
          </div>
        ))}
      </div>

      <div data-qid={`${qid}:actions`} style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
        <button
          type="button"
          data-qid={`${qid}:execute-isolate`}
          data-qs-action="COMPACT_CHAT_ISOLATE_NODES"
          title="Isolate affected nodes"
          disabled
          style={{
            width: '100%',
            background: 'rgba(33, 38, 45, 0.25)',
            border: '1px solid var(--border-default)',
            color: '#5d6572',
            padding: 8,
            fontSize: 11,
            cursor: 'not-allowed',
            fontFamily: 'inherit',
            textAlign: 'left',
            display: 'flex',
            justifyContent: 'space-between',
            borderRadius: 0,
          }}
        >
          <span data-qid={`${qid}:execute-isolate:label`}>[EXECUTE] ISOLATE_NODES</span>
          <span data-qid={`${qid}:execute-isolate:status`} style={{ color: '#484f58' }}>LOCKED</span>
        </button>
        {onViewTrace && <TraceActionControl data-qid={`${qid}:view-trace`} qid={`${qid}:view-trace`} onClick={onViewTrace} />}
      </div>
    </div>
  )
}

function TraceActionControl({ qid, onClick }: { qid: string; 'data-qid'?: string; onClick: () => void }): JSX.Element {
  return (
    <button
      type="button"
      data-qid={qid}
      data-qs-action="COMPACT_CHAT_VIEW_TRACE"
      title="View execution trace payload"
      onClick={onClick}
      style={{
        width: '100%',
        background: 'transparent',
        border: '1px solid var(--border-default)',
        color: 'var(--text-muted)',
        padding: 8,
        fontSize: 11,
        cursor: 'pointer',
        fontFamily: '"SF Mono", Consolas, monospace',
        textAlign: 'left',
        display: 'flex',
        justifyContent: 'space-between',
        borderRadius: 0,
      }}
      onMouseEnter={(event) => {
        event.currentTarget.style.borderColor = 'var(--text-muted)'
        event.currentTarget.style.color = '#c9d1d9'
      }}
      onMouseLeave={(event) => {
        event.currentTarget.style.borderColor = 'var(--border-default)'
        event.currentTarget.style.color = 'var(--text-muted)'
      }}
    >
      <span>[VIEW] EXECUTION_TRACE</span>
      <span style={{ color: '#484f58' }}>→</span>
    </button>
  )
}

function formatMessageTime(message: ChatMessage): string {
  const date = message.createdAt
    ? new Date(message.createdAt)
    : typeof message.timestamp === 'number'
      ? new Date(message.timestamp)
      : null
  if (!date || Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
