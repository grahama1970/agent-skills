/**
 * InlineEvidenceCase — SPARTA compliance audit object for chat answers.
 *
 * Compact by default unless defaultExpanded (lean-in). Expanded state shows claims, citations, gate trace, and
 * reviewer actions. The final answer is rendered separately by ChatWell.
 */

import { useMemo, useState, type MouseEvent, type ReactNode } from 'react'
import {
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  Maximize2,
  Info,
  AlertCircle,
  FileSearch,
  ShieldAlert,
  XCircle,
} from 'lucide-react'
import { useRegisterAction } from '../../hooks/useRegisterAction'
import type { EvidenceCaseData } from './types'
import { EMBRY } from '../sparta/common/EmbryStyle'
import {
  deriveArtifactStateLine,
  deriveEvidenceTierBadge,
  deriveReceiptRailTone,
  deriveReceiptReason,
  deriveReceiptStateLine,
  deriveReceiptSummary,
  evidenceTierBadgeTone,
  receiptShowsDraftToken,
} from './evidenceCaseReceipt'
import { useChatReadable } from './chatReadableContext'

export interface InlineEvidenceCaseProps {
  data: EvidenceCaseData
  onViewDetails?: () => void
  /** Focus the right-hand Evidence Workspace (Trace tab). */
  onOpenInWorkspace?: () => void
  /** Focus Evidence Workspace on Sources tab (artifact line click). */
  onOpenInSources?: () => void
  loading?: boolean
  /** When true, show a compact receipt only — adjudication lives in EvidenceWorkspace. */
  receiptMode?: boolean
  /** Metadata row lives in MessageFooter — keep summary + optional details only */
  unifiedFooter?: boolean
  defaultExpanded?: boolean
}

const STATE_LABELS = {
  bound: 'Evidence bound',
  pending: 'Trace pending',
  notApproved: 'Not approved',
}

function caseId(data: EvidenceCaseData) {
  const versionCaseId = data.evidence_case_version?.case_id
  if (data.case_id) return data.case_id
  if (data.qraKey) return data.qraKey
  if (typeof versionCaseId === 'string' || typeof versionCaseId === 'number') return String(versionCaseId)
  return 'EC-PENDING'
}

function normalizeVerdict(data: EvidenceCaseData) {
  const raw = String(data.verdict || '').toLowerCase()
  if (raw === 'satisfied' || raw === 'pass' || raw === 'passed') return 'Evidence bound'
  if (raw === 'not_satisfied' || raw === 'fail' || raw === 'failed') return 'Artifact not bound'
  return 'Trace pending'
}

function approvalState(data: EvidenceCaseData) {
  const state = String(data.approval_state || data.human_review_state || '').toLowerCase()
  if (state === 'approved') return 'Approved'
  if (state === 'rejected') return 'Rejected'
  return STATE_LABELS.notApproved
}

function boundArtifactLabel(data: EvidenceCaseData) {
  return data.artifact?.name || data.bound_artifact || 'Artifact pending'
}

function isAuditInvalidHash(hash: unknown) {
  const value = String(hash ?? '').toLowerCase()
  return value.includes('demo') || value.includes('mock') || value.includes('pending')
}

function statusColor(label: string) {
  if (label === 'Approved') return EMBRY.green
  if (label === 'Artifact not bound' || label === 'Rejected') return EMBRY.red
  if (label === 'Evidence bound') return EMBRY.blue
  return EMBRY.amber
}

function receiptSummary(data: EvidenceCaseData) {
  const claims = deriveClaims(data)
  if (claims[0]) return claims[0]
  if (data.gate_summary) return data.gate_summary
  return 'Evidence case generated; open workspace for full trace.'
}

function deriveClaims(data: EvidenceCaseData) {
  if (Array.isArray(data.claims) && data.claims.length > 0) return data.claims
  const controls = data.control_ids ?? []
  const gates = data.gate_trace ?? data.metadata?.gate_trace ?? []
  const fallback = [
    data.artifact?.name ? `Artifact is bound to ${data.artifact.name}.` : null,
    controls.length > 0 ? `Detected entities include ${controls.slice(0, 4).join(', ')}.` : null,
    gates.length > 0 ? `${gates.filter(g => g.passed).length}/${gates.length} evidence gates passed.` : data.gate_summary,
  ].filter(Boolean) as string[]
  return fallback.length > 0 ? fallback : ['Evidence case generated; full claim extraction is pending.']
}

function deriveCitations(data: EvidenceCaseData) {
  if (Array.isArray(data.citations) && data.citations.length > 0) return data.citations
  const sourceTraceability = data.source_traceability ? Object.keys(data.source_traceability) : []
  return sourceTraceability.slice(0, 5)
}

function citationLabel(citation: string, index: number) {
  if (/^chatwell\b/i.test(citation)) return `Generated-answer turn, not a source citation: ${citation}`
  if (/^capec-\d+/i.test(citation)) return `Source anchor ${index + 1}: ${citation} relationship text pending source-page excerpt`
  if (/^mitre|^attack|^t\d{4}/i.test(citation)) return `Source anchor ${index + 1}: ${citation} technique text pending source-page excerpt`
  return `Source anchor ${index + 1}: ${citation}`
}

function Pill({ label, color, title }: { label: string; color: string; title: string }) {
  return (
    <span
      tabIndex={0}
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        minHeight: 24,
        padding: '3px 8px',
        borderRadius: 999,
        border: `1px solid ${color}55`,
        backgroundColor: `${color}16`,
        color,
        fontSize: 11,
        fontWeight: 700,
        fontFamily: 'var(--font-mono)',
        overflowWrap: 'anywhere',
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: color }} />
      {label}
    </span>
  )
}

function ActionButton({
  qid,
  action,
  title,
  children,
  tone = EMBRY.dim,
  onClick,
  disabled = false,
  describedBy,
}: {
  qid: string
  action: string
  title: string
  children: ReactNode
  tone?: string
  onClick?: () => void
  disabled?: boolean
  describedBy?: string
}) {
  return (
    <button
      data-qid={qid}
      data-qs-action={action}
      title={title}
      disabled={disabled}
      aria-disabled={disabled}
      aria-describedby={describedBy}
      onClick={disabled ? undefined : onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        minHeight: 44,
        minWidth: 44,
        padding: '0 10px',
        borderRadius: 8,
        border: disabled ? `1px solid ${EMBRY.border}` : `1px solid ${EMBRY.border}`,
        backgroundColor: disabled ? '#07090c' : EMBRY.bgPanel,
        color: disabled ? '#5d6572' : tone,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.48 : 1,
        filter: disabled ? 'grayscale(1)' : undefined,
        fontSize: 12,
        fontWeight: 700,
      }}
    >
      {children}
    </button>
  )
}

export function InlineEvidenceCase({ data, onViewDetails, onOpenInWorkspace, onOpenInSources, loading, receiptMode = false, unifiedFooter = false, defaultExpanded = false }: InlineEvidenceCaseProps) {
  const CHAT_READABLE = useChatReadable()
  const [expanded, setExpanded] = useState(receiptMode ? false : defaultExpanded)
  const id = caseId(data)
  const evidenceState = boundArtifactLabel(data) === 'Artifact pending' ? normalizeVerdict(data) : STATE_LABELS.bound
  const traceState = data.trace_state || STATE_LABELS.pending
  const approval = approvalState(data)
  const boundArtifact = boundArtifactLabel(data)
  const artifactHash = data.artifact?.sha256 || data.artifact_hash
  const auditInvalidHash = isAuditInvalidHash(artifactHash)
  const claims = useMemo(() => deriveClaims(data), [data])
  const citations = useMemo(() => deriveCitations(data), [data])
  const gates = data.gate_trace ?? data.metadata?.gate_trace ?? []
  const gateCount = data.gates_total || data.metadata?.gates_total || gates.length
  const gatePassed = data.gates_passed || data.metadata?.gates_passed || gates.filter(g => g.passed).length
  const entities = data.control_ids ?? []
  const traceStateRaw = String(data.trace_state ?? '').toLowerCase()
  const gatesComplete = gateCount > 0 && gatePassed >= gateCount
  const canApproveOrExport = gatesComplete && traceStateRaw === 'bound' && approval === 'Approved' && !auditInvalidHash
  const blockedActionReason = canApproveOrExport
    ? ''
    : 'Approve, reject, and export are disabled until all evidence gates pass, source-page provenance is bound, mock artifacts are replaced, and reviewer approval is complete.'

  useRegisterAction('evidence-case:action:toggle', { app: 'sparta-explorer', action: 'EVIDENCE_CASE_TOGGLE', label: 'Toggle evidence case', description: 'Expand or collapse the inline evidence case audit trail' })
  useRegisterAction('evidence-case:action:approve', { app: 'sparta-explorer', action: 'EVIDENCE_CASE_APPROVE', label: 'Approve case', description: 'Approve the selected evidence case after review' })
  useRegisterAction('evidence-case:action:reject', { app: 'sparta-explorer', action: 'EVIDENCE_CASE_REJECT', label: 'Reject case', description: 'Reject the selected evidence case' })
  useRegisterAction('evidence-case:action:request-more', { app: 'sparta-explorer', action: 'EVIDENCE_CASE_REQUEST_MORE', label: 'Request more evidence', description: 'Request additional evidence for the selected case' })
  useRegisterAction('evidence-case:action:open-source', { app: 'sparta-explorer', action: 'EVIDENCE_CASE_OPEN_SOURCE', label: 'Open source page', description: 'Open the source document or extracted page for the selected case' })
  useRegisterAction('evidence-case:action:export', { app: 'sparta-explorer', action: 'EVIDENCE_CASE_EXPORT', label: 'Export audit packet', description: 'Export the selected evidence case as an audit packet' })

  const openWorkspace = onOpenInWorkspace ?? onViewDetails

  const [receiptDetailsOpen, setReceiptDetailsOpen] = useState(false)

  if (receiptMode && unifiedFooter) {
    return null
  }

  if (receiptMode) {
    const stateLine = deriveReceiptStateLine(data)
    const reason = deriveReceiptReason(data)
    const artifactState = deriveArtifactStateLine(data)
    const summary = deriveReceiptSummary(data)
    const railTone = deriveReceiptRailTone(data)
    const railColor = railTone === 'satisfied' ? EMBRY.green : railTone === 'blocked' ? EMBRY.red : EMBRY.amber
    const tierBadge = deriveEvidenceTierBadge(data)
    const tierTone = evidenceTierBadgeTone(tierBadge)
    const showDraft = receiptShowsDraftToken(data)

    const handleOpenSources = onOpenInSources
      ? (event: MouseEvent) => {
          event.stopPropagation()
          onOpenInSources()
        }
      : undefined

    const metaStyle = {
      color: EMBRY.muted,
      fontSize: CHAT_READABLE.metadataSize,
      lineHeight: 1.45,
      fontFamily: CHAT_READABLE.fontSans,
    } as const

    return (
      <div
        data-qid={`evidence-case:container:${id}`}
        title={`Evidence case ${id}`}
        style={{
          display: 'block',
          width: '100%',
          marginTop: unifiedFooter ? 0 : CHAT_READABLE.blockGap,
          padding: unifiedFooter ? 0 : '10px 0 0',
          borderTop: unifiedFooter ? 'none' : `1px solid ${EMBRY.border}33`,
          textAlign: 'left',
        }}
      >
        {summary && !unifiedFooter ? (
          <div data-qid={`evidence-case:summary:${id}`} style={{ color: EMBRY.dim, fontSize: CHAT_READABLE.metaSize, lineHeight: CHAT_READABLE.lineHeight, fontFamily: CHAT_READABLE.fontSans, marginBottom: 8 }}>
            {summary}
          </div>
        ) : null}

        {unifiedFooter ? (
          <button
            type="button"
            data-qid={`evidence-case:details-toggle:${id}`}
            data-qs-action="EVIDENCE_CASE_TOGGLE_DETAILS"
            title="Show receipt details"
            aria-expanded={receiptDetailsOpen}
            onClick={() => setReceiptDetailsOpen(v => !v)}
            style={{
              minHeight: 44,
              padding: 0,
              border: 'none',
              background: 'transparent',
              color: EMBRY.dim,
              cursor: 'pointer',
              fontSize: CHAT_READABLE.metadataSize,
              fontFamily: CHAT_READABLE.fontSans,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              marginBottom: receiptDetailsOpen ? 8 : 0,
            }}
          >
            <Info size={15} aria-hidden />
            {receiptDetailsOpen ? 'Hide receipt details' : 'Receipt details'}
          </button>
        ) : (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <div
            data-qid={`evidence-case:metadata-bar:${id}`}
            style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, flex: 1, minWidth: 0, ...metaStyle }}
          >
            <span data-qid={`evidence-case:id:${id}`} style={{ color: EMBRY.muted, fontFamily: CHAT_READABLE.fontMono }}>{id}</span>
            <span data-qid={`evidence-case:tier-badge:${id}`} style={{ display: 'inline-flex', alignItems: 'center', padding: '2px 8px', borderRadius: 8, fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: tierTone.color, background: tierTone.bg, border: `1px solid ${tierTone.border}` }}>{tierBadge}</span>
            <span data-qid={`evidence-case:state:${id}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: railColor }}>
              {railTone !== 'satisfied' ? <AlertCircle size={12} aria-hidden /> : null}
              {stateLine}
            </span>
            {showDraft ? <span data-qid={`evidence-case:draft:${id}`}>draft</span> : null}
            <button
              type="button"
              data-qid={`evidence-case:details-toggle:${id}`}
              data-qs-action="EVIDENCE_CASE_TOGGLE_DETAILS"
              title="Show receipt details"
              aria-expanded={receiptDetailsOpen}
              onClick={() => setReceiptDetailsOpen(v => !v)}
              style={{
                minWidth: 44,
                minHeight: 44,
                width: 44,
                height: 44,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: 'none',
                background: 'transparent',
                color: EMBRY.dim,
                cursor: 'pointer',
                padding: 0,
              }}
            >
              <Info size={15} aria-hidden />
            </button>
          </div>
          {openWorkspace ? (
            <button
              type="button"
              data-qid={`evidence-case:open-workspace:${id}`}
              data-qs-action="EVIDENCE_CASE_OPEN_WORKSPACE"
              title="Expand evidence case in workspace"
              aria-label={`Expand evidence case ${id} in workspace`}
              onClick={(event) => {
                event.stopPropagation()
                openWorkspace()
              }}
              style={{
                flexShrink: 0,
                width: 44,
                height: 44,
                minWidth: 44,
                minHeight: 44,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 8,
                border: `1px solid ${EMBRY.border}44`,
                background: 'transparent',
                color: EMBRY.dim,
                cursor: 'pointer',
              }}
            >
              <Maximize2 size={16} aria-hidden />
            </button>
          ) : null}
        </div>
        )}

        {receiptDetailsOpen ? (
          <div style={{ marginTop: 8, ...metaStyle }}>
            <div data-qid={`evidence-case:reason:${id}`}>{reason}</div>
            <button
              type="button"
              data-qid={`evidence-case:artifact:${id}`}
              data-qs-action="EVIDENCE_CASE_OPEN_SOURCES"
              title={onOpenInSources ? 'Open source artifact in Evidence Workspace' : `Artifact: ${artifactState}`}
              onClick={handleOpenSources}
              disabled={!onOpenInSources}
              style={{
                marginTop: 6,
                minHeight: 44,
                padding: 0,
                border: 'none',
                background: 'transparent',
                textAlign: 'left',
                color: onOpenInSources ? EMBRY.blue : EMBRY.muted,
                textDecoration: onOpenInSources ? 'underline' : 'none',
                cursor: onOpenInSources ? 'pointer' : 'default',
                fontSize: CHAT_READABLE.metadataSize,
                fontFamily: CHAT_READABLE.fontSans,
              }}
            >
              {artifactState}
            </button>
          </div>
        ) : null}
      </div>
    )
  }



  if (loading) {
    return (
      <section
        data-qid={`evidence-case:skeleton:${id}`}
        title="Building evidence case"
        style={{
          backgroundColor: EMBRY.bgPanel,
          border: `1px solid ${EMBRY.border}`,
          borderLeft: `3px solid ${EMBRY.amber}`,
          borderRadius: 8,
          padding: 14,
          marginTop: 8,
          color: EMBRY.dim,
          fontSize: 12,
        }}
      >
        Building deterministic Evidence Case...
      </section>
    )
  }

  return (
    <section
      data-qid={`evidence-case:container:${id}`}
      data-qs-action="EVIDENCE_CASE_CONTAINER"
      title={`Evidence Case ${id}: ${evidenceState}; ${traceState}; ${approval}`}
      aria-label={`Evidence Case ${id}`}
      style={{
        backgroundColor: EMBRY.bgDeep,
        border: `1px solid ${EMBRY.border}`,
        borderLeft: `3px solid ${EMBRY.amber}`,
        borderRadius: 8,
        padding: 14,
        marginTop: 8,
        maxWidth: 760,
      }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 12, alignItems: 'start' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ color: EMBRY.white, fontSize: 12, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              Evidence Case
            </span>
            <span data-qid={`evidence-case:id:${id}`} title={`Case ID: ${id}`} style={{ color: EMBRY.dim, fontSize: 12, fontFamily: 'var(--font-mono)', overflowWrap: 'anywhere' }}>
              {id}
            </span>
          </div>
          {expanded ? (
            <>
              <div data-qid={`evidence-case:artifact:${id}`} title={`Bound artifact: ${boundArtifact}`} style={{ color: EMBRY.white, fontSize: 13, lineHeight: 1.5, overflowWrap: 'anywhere' }}>
                Bound artifact: <span style={{ fontFamily: 'var(--font-mono)' }}>{boundArtifact}</span>
              </div>
              <div data-qid={`evidence-case:provenance-distinction:${id}`} title="Artifact binding is not citation provenance" style={{ color: EMBRY.amber, fontSize: 11, lineHeight: 1.45, marginTop: 4 }}>
                Artifact binding only confirms the file is attached; source-page citation provenance is still blocked.
              </div>
              {artifactHash && (
                <div data-qid={`evidence-case:artifact-hash:${id}`} title={auditInvalidHash ? `Mock artifact hash: ${artifactHash}` : `Artifact SHA256: ${artifactHash}`} style={{ color: auditInvalidHash ? EMBRY.amber : EMBRY.dim, fontSize: 11, fontFamily: 'var(--font-mono)', overflowWrap: 'anywhere', marginTop: 2, fontWeight: auditInvalidHash ? 800 : 400 }}>
                  {auditInvalidHash ? 'MOCK HASH: ' : 'SHA256: '}{artifactHash}
                </div>
              )}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 9 }}>
                <Pill label={evidenceState} color={statusColor(evidenceState)} title={`Evidence binding state: ${evidenceState}`} />
                <Pill label={traceState} color={statusColor(traceState)} title={`Trace state: ${traceState}`} />
                <Pill label={approval} color={statusColor(approval)} title={`Approval state: ${approval}`} />
                <Pill label={`${claims.length} claim${claims.length === 1 ? '' : 's'}`} color={EMBRY.dim} title={`${claims.length} claims in this audit case`} />
                <Pill label={`${citations.length} citation${citations.length === 1 ? '' : 's'}`} color={EMBRY.dim} title={`${citations.length} citations or source anchors in this audit case`} />
              </div>
              <div data-qid={`evidence-case:citation-preview:${id}`} title={citations.length > 0 ? `Citation anchors pending source-page excerpts: ${citations.join(', ')}` : 'Citations pending'} style={{ color: citations.length > 0 ? EMBRY.dim : EMBRY.amber, fontSize: 11, lineHeight: 1.45, marginTop: 8, overflowWrap: 'anywhere' }}>
                Citations: anchors only, not audit citations until provenance is bound: {citations.length > 0 ? citations.slice(0, 4).map(citationLabel).join(' · ') : 'pending source-page extraction'}
              </div>
            </>
          ) : null}
          {!expanded ? (
            <div data-qid={`evidence-case:summary:${id}`} style={{ color: EMBRY.dim, fontSize: 11, lineHeight: 1.45, marginTop: 6, overflowWrap: 'anywhere' }}>
              {evidenceState} · {traceState} · {approval}
              {boundArtifact !== 'Artifact pending' ? ` · ${boundArtifact}` : ''}
            </div>
          ) : null}
        </div>
        <button
          type="button"
          data-qid={`evidence-case:toggle:${id}`}
          data-qs-action="EVIDENCE_CASE_TOGGLE"
          title={expanded ? 'Collapse evidence case' : 'Expand audit trail'}
          aria-label={expanded ? 'Collapse evidence case' : 'Expand audit trail'}
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 32,
            height: 32,
            minWidth: 32,
            minHeight: 32,
            padding: 0,
            borderRadius: 6,
            border: `1px solid ${EMBRY.border}`,
            backgroundColor: 'transparent',
            color: EMBRY.dim,
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          {expanded ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />}
        </button>
      </div>

      {expanded ? (
        <div data-qid={`evidence-case:body:${id}`}>
          <div data-qid={`evidence-case:preview:${id}`} title="Evidence case claim preview" style={{ color: EMBRY.dim, fontSize: 12, lineHeight: 1.45, marginTop: 10, overflowWrap: 'anywhere' }}>
            {claims.slice(0, 2).join(' ')}
            {approval !== 'Approved' ? ' This answer is draft-only until approval is complete.' : ''}
          </div>

          <div style={{ color: EMBRY.dim, fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', margin: '14px 0 8px' }}>
            Reviewer Actions
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            <ActionButton qid={`evidence-case:approve:${id}`} action="EVIDENCE_CASE_APPROVE" title={canApproveOrExport ? 'Approve case' : blockedActionReason} disabled={!canApproveOrExport} describedBy={!canApproveOrExport ? `evidence-case:blocked-actions:${id}` : undefined} tone={EMBRY.green}><CheckCircle size={14} />Approve</ActionButton>
            <ActionButton qid={`evidence-case:reject:${id}`} action="EVIDENCE_CASE_REJECT" title={canApproveOrExport ? 'Reject case' : blockedActionReason} disabled={!canApproveOrExport} describedBy={!canApproveOrExport ? `evidence-case:blocked-actions:${id}` : undefined} tone={EMBRY.red}><XCircle size={14} />Reject</ActionButton>
            <ActionButton qid={`evidence-case:request-more:${id}`} action="EVIDENCE_CASE_REQUEST_MORE" title="Request more evidence" tone={EMBRY.amber}><ShieldAlert size={14} />More evidence</ActionButton>
            <ActionButton qid={`evidence-case:open-source:${id}`} action="EVIDENCE_CASE_OPEN_SOURCE" title="Open source page or extracted record" tone={EMBRY.blue} onClick={onViewDetails}><FileSearch size={14} />Open source</ActionButton>
            <ActionButton qid={`evidence-case:export:${id}`} action="EVIDENCE_CASE_EXPORT" title={canApproveOrExport ? 'Export audit packet' : blockedActionReason} disabled={!canApproveOrExport} describedBy={!canApproveOrExport ? `evidence-case:blocked-actions:${id}` : undefined} tone={EMBRY.dim}><Download size={14} />Export</ActionButton>
          </div>
          {!canApproveOrExport && (
            <div id={`evidence-case:blocked-actions:${id}`} style={{ color: EMBRY.amber, fontSize: 11, lineHeight: 1.45, marginTop: 8 }}>
              {blockedActionReason}
            </div>
          )}

          <div data-qid={`evidence-case:expanded:${id}`} title="Expanded evidence case audit trail" style={{ borderTop: `1px solid ${EMBRY.border}`, marginTop: CHAT_READABLE.blockGap, paddingTop: 12 }}>
            {entities.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
                {entities.map(entity => (
                  <span key={entity} tabIndex={0} title={`${entity}: bound entity in this evidence case`} style={{ color: EMBRY.blue, border: `1px solid ${EMBRY.blue}55`, backgroundColor: `${EMBRY.blue}14`, borderRadius: 999, padding: '3px 8px', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                    {entity}
                  </span>
                ))}
              </div>
            )}

            <div style={{ color: EMBRY.dim, fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 6 }}>
              Claims
            </div>
            <ol style={{ margin: 0, paddingLeft: 18, color: EMBRY.white, fontSize: 12, lineHeight: 1.55 }}>
              {claims.map((claim, index) => (
                <li key={`${claim}-${index}`} data-qid={`evidence-case:claim:${id}:${index}`} title={`Claim ${index + 1}: ${claim}`} style={{ marginBottom: 6, overflowWrap: 'anywhere' }}>
                  {claim}
                </li>
              ))}
            </ol>

            {citations.length > 0 && (
              <>
                <div style={{ color: EMBRY.dim, fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', margin: '12px 0 6px' }}>
                  Citation anchors pending source-page excerpts
                </div>
                <div style={{ color: EMBRY.amber, fontSize: 11, lineHeight: 1.45, marginBottom: 6 }}>
                  Anchors are not audit-ready citations until trace provenance binds the source page and excerpt.
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {citations.map((citation, index) => (
                    <span key={`${citation}-${index}`} data-qid={`evidence-case:citation:${id}:${index}`} title={`Citation anchor ${index + 1}: ${citation}; source-page excerpt pending`} style={{ color: EMBRY.dim, fontSize: 12, fontFamily: 'var(--font-mono)', overflowWrap: 'anywhere' }}>
                      {citationLabel(citation, index)}
                    </span>
                  ))}
                </div>
              </>
            )}

            {gateCount > 0 && (
              <>
                <div style={{ color: EMBRY.dim, fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', margin: '12px 0 6px' }}>
                  Trace Gates
                </div>
                <div data-qid={`evidence-case:gates:${id}`} title={`${gatePassed}/${gateCount} gates passed`} style={{ color: EMBRY.white, fontSize: 12, marginBottom: 8 }}>
                  {gatePassed}/{gateCount} gates passed
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {gates.map((gate, index) => (
                    <div key={`${gate.gate}-${index}`} data-qid={`evidence-case:gate:${id}:${index}`} title={`${gate.gate}: ${gate.detail}`} style={{ display: 'grid', gridTemplateColumns: '18px minmax(0, 1fr)', gap: 8, alignItems: 'start', color: EMBRY.dim, fontSize: 12 }}>
                      <span style={{ color: gate.passed ? EMBRY.green : EMBRY.red }}>{gate.passed ? <CheckCircle size={14} /> : <XCircle size={14} />}</span>
                      <span style={{ overflowWrap: 'anywhere' }}><span style={{ color: EMBRY.white }}>{gate.gate}</span> — {gate.detail}</span>
                    </div>
                  ))}
                </div>
                {gatePassed < gateCount && (
                  <div data-qid={`evidence-case:next-step:${id}`} title="Next step to resolve blocked evidence gates" style={{ color: EMBRY.amber, fontSize: 12, lineHeight: 1.45, marginTop: 10 }}>
                    Next step: request more evidence or rerun the evidence case after binding source-page provenance; approval and export remain blocked until all required gates pass.
                  </div>
                )}
              </>
            )}

            {onViewDetails && (
              <button
                data-qid={`evidence-case:view-details:${id}`}
                data-qs-action="EVIDENCE_CASE_VIEW_DETAILS"
                title="View full evidence case"
                onClick={onViewDetails}
                style={{
                  marginTop: 10,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  minHeight: 44,
                  padding: '0 10px',
                  borderRadius: 8,
                  border: `1px solid ${EMBRY.border}`,
                  backgroundColor: EMBRY.bgPanel,
                  color: EMBRY.dim,
                  cursor: 'pointer',
                  fontSize: 12,
                }}
              >
                <ExternalLink size={14} />
                Full case record
              </button>
            )}
          </div>

          {approval !== 'Approved' && (
            <div data-qid={`evidence-case:draft-warning:${id}`} title="Fail-closed draft warning" style={{ color: EMBRY.amber, fontSize: 12, fontWeight: 800, lineHeight: 1.45, marginTop: 10, padding: '8px 10px', border: `1px solid ${EMBRY.amber}`, borderRadius: 6, backgroundColor: `${EMBRY.amber}14` }}>
              Draft-only: trace provenance or reviewer approval is incomplete.
            </div>
          )}
        </div>
      ) : null}

    </section>
  )
}
