/**
 * ChatWell — Shared chat interface for SPARTA Explorer and Embry Terminal.
 *
 * Layout ported from Embry Terminal:
 * - User messages: right-aligned bubbles
 * - System messages: flush left, no bubble
 * - RecallCard: collapsible score breakdown
 * - GateChain: collapsible evidence gate timeline
 * - Tool actions: muted collapsible lines
 * - Thumbs feedback on system messages
 */
import { useState, useRef, useEffect, useCallback, type ReactNode } from 'react'
import { Shield } from 'lucide-react'
import { EMBRY, fwBadge } from '../sparta/common/EmbryStyle'
import { highlightEntities, highlightWithGlossary, type GlossaryTerm } from './highlightEntities'
import { MarkdownRenderer } from './MarkdownRenderer'
import { SkillPalette } from './SkillPalette'
import { InlineEvidenceCase } from './InlineEvidenceCase'
import { SpartaHudInput, type ReasoningStep } from '../sparta/query/SpartaHudInput'
import { RecallCard } from '../sparta/query/RecallCard'
import { GateChain } from '../sparta/query/GateChain'
import { BuildingEvidenceCase, type BuildingStep } from '../sparta/shared/BuildingEvidenceCase'
import { ThreatMatrixCard } from '../sparta/query/ThreatMatrixCard'
import { ToolAction } from './ToolAction'
import type {
  ChatMessage, Skill, EntityRef, EvidenceGate, CascadeLayer,
  ThreatMatrixSummary, RecallItem,
} from './types'

// ChatMessage, EntityRef, EvidenceGate, CascadeLayer, ThreatMatrixSummary, RecallItem
// are all imported from shared-chat/types — re-export for consumers.
export type { ChatMessage, ThreatMatrixSummary, EntityRef, EvidenceGate, CascadeLayer } from './types'

/** Live streaming step for evidence case progression */
export interface StreamingStep {
  id: string
  type: string
  skill?: string
  status: 'pending' | 'running' | 'done' | 'failed'
  summary: string
  detail?: string
  duration?: number
  startedAt?: number
}

export interface ComplianceComplianceChatWellProps {
  messages: ChatMessage[]
  onSend?: (query: string, type: 'natural' | 'aql') => void
  renderExtras?: (msg: ChatMessage) => ReactNode
  /** Override default SPARTA shield / user bubble-only layout */
  renderAvatar?: (msg: ChatMessage) => ReactNode
  onClarifyClick?: (question: string) => void
  onFeedback?: (msgId: string, feedback: 'up' | 'down') => void
  onRunEvidenceCase?: (msg: ChatMessage) => void
  evidenceCaseLoading?: string | null
  onNavigateMatrix?: () => void
  /** Skills list for / palette — if provided, typing / triggers skill autocomplete */
  skills?: Skill[]
  /** Composer placeholder (transport room, terminals) */
  composerPlaceholder?: string
  /** 'transport' uses collaboration bubbles + slim HUD */
  surfaceVariant?: 'default' | 'transport'
  /** Entity click handler — clicking AC-17, CWE-79, /assess triggers this */
  onEntityClick?: (entity: string, type: string) => void
  /** Starter questions from sparta_qra — replaces hardcoded defaults when provided */
  starterQuestions?: string[]
  /** Warning shown when chat is available only for verification/pre-signoff use */
  preSignoffWarning?: string
  /** Downgrades default starters to verification-only prompts before data-quality signoff */
  starterMode?: 'normal' | 'verification'
  /** True when agent is streaming a response */
  isStreaming?: boolean
  /** Live steps during evidence case/agent execution */
  streamingSteps?: StreamingStep[]
}

const LAYER_COLORS: Record<CascadeLayer, string> = {
  recall: EMBRY.green,
  intent: EMBRY.blue,
  llm: EMBRY.amber,
  aql: EMBRY.accent,
}

// ToolAction imported from shared-chat (COTS compliant: 44px touch, 13px font, tooltip)

// ── Message Component ────────────────────────────────────────────────────

function MessageItem({
  msg, onFeedback, onClarifyClick, onRunEvidenceCase, evidenceCaseLoading, renderExtras, renderAvatar, onNavigateMatrix, onEntityClick, surfaceVariant,
}: {
  msg: ChatMessage
  onFeedback?: (id: string, fb: 'up' | 'down') => void
  onClarifyClick?: (q: string) => void
  onRunEvidenceCase?: (msg: ChatMessage) => void
  evidenceCaseLoading?: string | null
  renderExtras?: (msg: ChatMessage) => ReactNode
  /** Override default SPARTA shield / user bubble-only layout */
  renderAvatar?: (msg: ChatMessage) => ReactNode
  onNavigateMatrix?: () => void
  onEntityClick?: (entity: string, type: string) => void
  surfaceVariant?: 'default' | 'transport'
}) {
  const isUser = msg.role === 'user'

  // Get glossary from evidence case if available (domain phrases from /create-evidence-case daemon)
  const glossary: GlossaryTerm[] = msg.evidenceCase?.glossary || []
  const answerContent = msg.evidenceCase?.answer || msg.content.replace(/^Evidence Case:.*\n?/i, '')

  // Use highlightWithGlossary when daemon glossary is available, else fallback to static patterns
  const highlight = (text: string) => glossary.length > 0
    ? highlightWithGlossary(text, glossary, onEntityClick)
    : highlightEntities(text, onEntityClick)

  // ── User message: right-aligned bubble ──
  if (isUser) {
    const userAvatar = renderAvatar?.(msg)
    if (surfaceVariant === 'transport') {
      const collab = msg.transportCollaborator || 'human'
      return (
        <div className={`transport-message transport-message--${collab}`} style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'flex-end', gap: 10, padding: '12px 0' }}>
          <div className="transport-message__bubble" style={{ maxWidth: 'min(85%, 520px)' }}>
            <div className="transport-message__body">{highlight(msg.content)}</div>
            {renderExtras?.(msg)}
          </div>
          {userAvatar}
        </div>
      )
    }
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'flex-end', gap: 10, padding: '10px 0' }}>
        <div style={{
          maxWidth: '85%', padding: '10px 14px',
          borderRadius: '14px 14px 4px 14px',
          background: `${EMBRY.blue}22`,
          border: `1px solid ${EMBRY.blue}44`,
          fontSize: 12, lineHeight: 1.6, color: EMBRY.white,
          fontFamily: msg.type === 'aql' ? 'monospace' : 'inherit',
        }}>
          {highlight(msg.content)}
        </div>
        {userAvatar}
      </div>
    )
  }

  // ── Agent/system message: shield identity + operational surface ──
  const layerColor = msg.cascadeLayer ? LAYER_COLORS[msg.cascadeLayer] : EMBRY.border

  if (surfaceVariant === 'transport') {
    const collab = msg.transportCollaborator || 'unknown'
    return (
      <div className={`transport-message transport-message--${collab}`} style={{ display: 'grid', gridTemplateColumns: '36px minmax(0, 1fr)', gap: 12, padding: '12px 0', alignItems: 'start' }}>
        {renderAvatar?.(msg) ?? <div style={{ width: 28, height: 28 }} />}
        <div className="transport-message__surface" style={{ minWidth: 0 }}>
          <div className="transport-message__speaker">{msg.agent || collab}</div>
          {msg.skillUsed && <ToolAction label={`/${msg.skillUsed}`} qid={`chat:skill:${msg.skillUsed}`} />}
          <div className="transport-message__body">{highlight(answerContent)}</div>
          {renderExtras?.(msg)}
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '32px minmax(0, 1fr)', gap: 10, padding: '10px 0', alignItems: 'start' }}>
      {renderAvatar?.(msg) ?? (
        <div
          aria-label="SPARTA agent"
          title="SPARTA agent"
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: EMBRY.amber,
            backgroundColor: `${EMBRY.amber}10`,
            border: `1px solid ${EMBRY.border}`,
          }}
        >
          <Shield size={18} strokeWidth={1.7} />
        </div>
      )}
      <div style={{
        padding: '10px 12px', margin: 0,
        borderRadius: 8, borderLeft: `3px solid ${layerColor}`,
        background: `${layerColor}06`,
        minWidth: 0,
      }}>
        {/* Tool action line */}
        {msg.skillUsed && <ToolAction label={`Ran /${msg.skillUsed}`} qid={`chat:skill:${msg.skillUsed}`} />}

        {/* Cascade layer indicator */}
        {msg.cascadeLayer && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 6 }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: layerColor,
              boxShadow: `0 0 4px ${layerColor}`,
            }} />
            <span style={{
              fontSize: 10, color: layerColor,
              fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em',
              fontFamily: 'monospace',
            }}>
              {msg.cascadeLayer}
            </span>
          </div>
        )}

        {/* Evidence Case — primary audit object, separated from final answer */}
        {msg.evidenceCase && (
          <InlineEvidenceCase data={msg.evidenceCase} />
        )}

        {msg.evidenceCase && (
          <div
            data-qid={`chat:answer-divider:${msg.id ?? 'message'}`}
            title="Final answer begins below; it is grounded by the Evidence Case above"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              color: EMBRY.dim,
              fontSize: 10,
              fontWeight: 900,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              margin: '16px 0 8px',
            }}
          >
            <span style={{ height: 1, flex: 1, backgroundColor: EMBRY.border }} />
            Answer
            <span style={{ height: 1, flex: 1, backgroundColor: EMBRY.border }} />
          </div>
        )}

        {/* Content — shared MarkdownRenderer with entity highlighting */}
        <div style={{ fontSize: 12, lineHeight: 1.6, color: EMBRY.white }}>
          {msg.evidenceCase && msg.evidenceCase.human_review_state !== 'approved' && (
            <div
              data-qid={`chat:draft-warning:${msg.id ?? 'message'}`}
              title="Draft-only answer warning"
              style={{ color: EMBRY.amber, fontSize: 11, marginBottom: 8 }}
            >
              Draft-only: trace provenance or reviewer approval is incomplete.
            </div>
          )}
          {msg.type === 'aql' ? (
            <pre style={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', margin: 0 }}>{answerContent}</pre>
          ) : (
            <MarkdownRenderer content={answerContent} onEntityClick={onEntityClick} />
          )}
        </div>

      {/* RecallCard — only when no evidenceCase (fallback for non-evidence messages) */}
      {!msg.evidenceCase && msg.recallItems && msg.recallItems.length > 0 && (
        <RecallCard
          items={msg.recallItems}
          resultCount={msg.resultCount ?? msg.recallItems.length}
        />
      )}

      {/* Inline threat matrix card */}
      {msg.matrixSummary && (
        <ThreatMatrixCard summary={msg.matrixSummary} onNavigate={onNavigateMatrix} />
      )}

      {/* Entity pills */}
      {msg.entities && msg.entities.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
          {msg.entities.map((e, i) => (
            <button key={i} data-qid={`chat:entity:${e.id}`} data-qs-action={`NAVIGATE_ENTITY_${e.id.replace(/[^A-Za-z0-9]/g, '_').toUpperCase()}`} tabIndex={0} onClick={() => onEntityClick?.(e.id, e.exists ? 'control' : 'cwe')} style={{
              ...fwBadge(e.exists ? 'SPARTA' : 'CWE'),
              opacity: e.exists ? 1 : 0.5,
              cursor: 'pointer',
              minHeight: 44, minWidth: 44,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }} title={`${e.id} — ${e.exists ? 'found in corpus' : 'not found'}`}>
              {e.label}
            </button>
          ))}
        </div>
      )}

      {/* GateChain — only when no evidenceCase (fallback for legacy verdict format) */}
      {!msg.evidenceCase && msg.verdict && (
        <GateChain
          gates={msg.verdict.gates}
          verdict={msg.verdict.state}
          tier={msg.verdict.tier}
        />
      )}

      {/* Run Evidence Case button */}
      {onRunEvidenceCase && msg.entities && msg.entities.some(e => e.exists) && !msg.verdict && (
        <button
          data-qid={`chat:evidence-case:${msg.id}`} data-qs-action="run-evidence-case" title="Run evidence case for this message" onClick={() => onRunEvidenceCase(msg)}
          disabled={evidenceCaseLoading === msg.id}
          style={{
            marginTop: 6, fontSize: 12, fontWeight: 700,
            padding: '10px 16px', borderRadius: 12, minHeight: 44,
            border: `1px solid ${EMBRY.accent}66`,
            backgroundColor: evidenceCaseLoading === msg.id ? `${EMBRY.accent}08` : `${EMBRY.accent}18`,
            color: EMBRY.accent,
            cursor: evidenceCaseLoading === msg.id ? 'wait' : 'pointer',
            letterSpacing: '0.05em', textTransform: 'uppercase',
            opacity: evidenceCaseLoading === msg.id ? 0.6 : 1,
          }}
        >
          {evidenceCaseLoading === msg.id ? 'Running\u2026' : 'Run Evidence Case'}
        </button>
      )}

      {/* Clarify chips */}
      {msg.clarifyOptions && msg.clarifyOptions.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
          {msg.clarifyOptions.map((c, i) => (
            <button key={i} data-qid={`chat:clarify:${i}`} title={c.question} onClick={() => onClarifyClick?.(c.question)} style={{
              fontSize: 12, padding: '3px 8px', borderRadius: 12,
              border: `1px solid ${EMBRY.accent}44`, backgroundColor: `${EMBRY.accent}12`,
              color: EMBRY.accent, cursor: 'pointer',
            }}>
              {c.question}
            </button>
          ))}
        </div>
      )}

      {/* QuerySpec collapsible */}
      {msg._querySpec && (
        <details style={{ marginTop: 6, fontSize: 10 }}>
          <summary style={{ color: EMBRY.dim, cursor: 'pointer' }}>QuerySpec</summary>
          <pre style={{
            color: EMBRY.dim, fontSize: 12, whiteSpace: 'pre-wrap',
            marginTop: 4, padding: 6, backgroundColor: EMBRY.bgDeep,
            borderRadius: 4, overflow: 'auto', maxHeight: 150,
          }}>
            {JSON.stringify(msg._querySpec, null, 2)}
          </pre>
        </details>
      )}

      {/* Thumbs */}
      {onFeedback && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
          <button
            data-qid={`chat:feedback-up:${msg.id}`}
            data-qs-action="FEEDBACK_HELPFUL"
            title="Helpful response"
            onClick={() => msg.id && onFeedback(msg.id, 'up')}
            style={{
              background: 'none', border: `1px solid ${EMBRY.border}`, borderRadius: 6,
              cursor: 'pointer', fontSize: 14,
              minWidth: 44, minHeight: 44,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              opacity: msg.feedback === 'up' ? 1 : 0.5,
              color: msg.feedback === 'up' ? EMBRY.green : EMBRY.dim,
              filter: msg.feedback === 'up' ? `drop-shadow(0 0 4px ${EMBRY.green})` : 'none',
            }}
          >
            {'\u25B2'}
          </button>
          <button
            data-qid={`chat:feedback-down:${msg.id}`}
            data-qs-action="FEEDBACK_NOT_HELPFUL"
            title="Not helpful"
            onClick={() => msg.id && onFeedback(msg.id, 'down')}
            style={{
              background: 'none', border: `1px solid ${EMBRY.border}`, borderRadius: 6,
              cursor: 'pointer', fontSize: 14,
              minWidth: 44, minHeight: 44,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              opacity: msg.feedback === 'down' ? 1 : 0.5,
              color: msg.feedback === 'down' ? EMBRY.red : EMBRY.dim,
              filter: msg.feedback === 'down' ? `drop-shadow(0 0 4px ${EMBRY.red})` : 'none',
            }}
          >
            {'\u25BC'}
          </button>
        </div>
      )}

        {renderExtras?.(msg)}
      </div>
    </div>
  )
}

// ── Main ChatWell ────────────────────────────────────────────────────────

export function ComplianceChatWell({ messages, onSend, renderExtras, renderAvatar, onClarifyClick, onFeedback, onRunEvidenceCase, evidenceCaseLoading, onNavigateMatrix, skills, onEntityClick, starterQuestions, preSignoffWarning, starterMode = 'normal', isStreaming, streamingSteps, composerPlaceholder, surfaceVariant = 'default' }: ComplianceChatWellProps) {
  const [input, setInput] = useState('')
  const [showPalette, setShowPalette] = useState(false)
  const [skillFilter, setSkillFilter] = useState('')
  const paletteKeyHandler = useRef<((e: React.KeyboardEvent) => boolean) | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  const handleSend = useCallback(() => {
    if (!input.trim()) return
    onSend?.(input.trim(), 'natural')
    setInput('')
    setShowPalette(false)
  }, [input, onSend])

  const applyInputValue = useCallback((val: string) => {
    setInput(val)
    const lastWord = val.split(/\s+/).pop() || ''
    if (lastWord.startsWith('/') && lastWord.length > 1) {
      setShowPalette(true)
      setSkillFilter(lastWord.slice(1))
    } else if (lastWord === '/' && skills && skills.length > 0) {
      setShowPalette(true)
      setSkillFilter('')
    } else {
      setShowPalette(false)
    }
  }, [skills])

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    applyInputValue(e.target.value)
  }, [applyInputValue])

  const handleSkillSelect = useCallback((name: string) => {
    const words = input.split(/\s+/)
    words[words.length - 1] = `/${name} `
    setInput(words.join(' '))
    setShowPalette(false)
  }, [input])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (showPalette && paletteKeyHandler.current?.(e)) return
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }, [handleSend, showPalette])

  const hasConversation = messages.length > 0 || isStreaming
  const composerDockHeight = 104

  return (
    <div className={surfaceVariant === 'transport' ? 'transport-chat-well' : undefined} style={{
      display: 'flex', flexDirection: 'column', flex: 1, height: '100%', minHeight: 0, overflow: 'hidden',
      background: surfaceVariant === 'transport' ? 'transparent' : EMBRY.bg,
    }}>
      {/* Messages — scrollable, full height */}
      <div style={{
        flex: 1,
        minHeight: 0,
        overflow: 'auto',
        padding: hasConversation ? '8px 16px 8px 16px' : '0 16px 6px 16px',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {messages.length === 0 && (
          <div style={{ padding: '0', display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center', marginBottom: 0 }}>
            {preSignoffWarning ? (
              <div data-qid="chat:readiness:warning" style={{ width: '100%', border: `1px solid ${EMBRY.amber}66`, background: '#241a06', color: EMBRY.amber, padding: '10px 12px', borderRadius: 8, fontSize: 11, lineHeight: 1.45 }}>
                {preSignoffWarning}
              </div>
            ) : null}
            <div style={{ color: EMBRY.muted, fontSize: 11, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>
              {starterMode === 'verification' ? 'Verification prompts only' : 'Ask a question'}
            </div>
            {(starterQuestions ?? (starterMode === 'verification' ? [
              'Verify current coverage blockers before answering broadly',
              'Inspect the ISO and ATT&CK Mobile quality gaps',
              'Show the evidence gates required before conversation-lab',
              'Run a read-only readiness check for Brandon, Margaret, and Jennifer',
            ] : [
              'Show me the F-36 threat matrix',
              'What SPARTA controls cover supply chain attacks?',
              'Which controls have no evidence cases?',
              'Run an evidence case for firmware tampering on avionics',
              'What is our CMMC Level 2 compliance posture?',
              'Show controls related to CWE-287 authentication bypass',
            ])).map((q, i) => (
              <button key={q} data-qid={`chat:starter:${i}`} data-qs-action="send-starter-question" title={q} onClick={() => onSend?.(q, 'natural')} style={{
                background: `${EMBRY.accent}08`, border: `1px solid ${EMBRY.accent}22`,
                borderRadius: 8, padding: '10px 16px', cursor: 'pointer',
                color: EMBRY.dim, fontSize: 12, textAlign: 'left', width: '100%',
                minWidth: 44, minHeight: 44, transition: 'border-color 0.15s ease, color 0.15s ease',
              }} onMouseEnter={e => { e.currentTarget.style.borderColor = EMBRY.accent; e.currentTarget.style.color = EMBRY.white }}
                 onMouseLeave={e => { e.currentTarget.style.borderColor = `${EMBRY.accent}22`; e.currentTarget.style.color = EMBRY.dim }}>
                {q}
              </button>
            ))}
          </div>
        )}
        {messages.map((msg) => (
          <MessageItem
            key={msg.id}
            msg={msg}
            onFeedback={onFeedback}
            onClarifyClick={onClarifyClick}
            onRunEvidenceCase={onRunEvidenceCase}
            evidenceCaseLoading={evidenceCaseLoading}
            renderExtras={renderExtras}
            renderAvatar={renderAvatar}
            onNavigateMatrix={onNavigateMatrix}
            onEntityClick={onEntityClick}
            surfaceVariant={surfaceVariant}
          />
        ))}
        {/* Live streaming gate progression — animated evidence case building */}
        {isStreaming && (
          <BuildingEvidenceCase
            steps={streamingSteps?.map(s => ({
              id: s.id,
              type: s.type,
              status: s.status,
              summary: s.summary,
              detail: s.detail,
              duration: s.duration,
            })) ?? []}
            isStreaming={isStreaming}
            title="Building Evidence Case"
          />
        )}
        <div ref={chatEndRef} />
      </div>

      {/* 2026 Modern Tactical Command Bar — Glassmorphic Floating HUD */}
      <div style={{ position: 'relative', flexShrink: 0, height: composerDockHeight }}>
        {showPalette && skills && skills.length > 0 && (
          <div style={{ position: 'absolute', bottom: 72, left: 16, right: 16, zIndex: 101 }}>
            <SkillPalette
              filter={skillFilter}
              skills={skills}
              onSelect={handleSkillSelect}
              onClose={() => setShowPalette(false)}
              onKeyNav={handler => { paletteKeyHandler.current = handler }}
            />
          </div>
        )}
        <SpartaHudInput
          value={input}
          onValueChange={applyInputValue}
          onSend={(query, type) => onSend?.(query, type)}
          onSkillsOpen={() => {
            if (skills && skills.length > 0) {
              setShowPalette(true)
              setSkillFilter('')
            }
          }}
          placeholder={composerPlaceholder}
          isThinking={isStreaming}
          thinkingLabel={isStreaming ? 'Building Evidence Case' : 'CAE Trace'}
          reasoningSteps={streamingSteps ?? []}
          variant={surfaceVariant === 'transport' ? 'transport' : 'sparta'}
        />
      </div>
    </div>
  )
}
