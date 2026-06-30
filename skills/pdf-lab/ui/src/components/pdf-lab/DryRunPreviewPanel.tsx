/**
 * DryRunPreviewPanel — renders the Phase 3 dry-run preview JSON.
 *
 * Reads a DryRunResult (from dry_run_preview.py) and renders the
 * three-state UI: Resolved / Rejected / Conflicts + Warnings + Summary
 * + Export gate.
 *
 * Visual contract (locked per WebGPT round 7):
 *  - Every resolved token shows a primary promotion badge AND a
 *    secondary "L" subscript marker indicating line-evidence (Phase 1
 *    verdict: pdf_oxide.block.v2 has no native token bboxes).
 *  - approximate_bbox primary badge fires only if extractor emits
 *    below-line quality (impossible today with pdf_oxide.block.v2;
 *    visual treatment defined for future-proofing).
 *  - Export gate: button enabled iff (conflicts.length === 0 OR all
 *    conflicts have a disposition).
 *  - Per locked contract: artifact export is NOT blocked by conflicts;
 *    only GRAPH PROMOTION is gated.
 */
import { useMemo, useState } from 'react'
import './DryRunPreviewPanel.css'

type PromotionBadge =
  | 'auto_promote_candidate'
  | 'queued_for_review'
  | 'warning_only'
  | 'approximate_bbox'

interface ResolvedToken {
  region_id: string
  token_text: string
  canonical_target: string
  fragment?: string | null
  collection: string
  parser_kind: string
  oscal_agreement: string
  char_span: [number, number]
  bbox_quality: 'token' | 'span' | 'line' | 'element' | 'approximate' | 'unavailable'
  evidence_geometry_claim: string
  promotion_badge: PromotionBadge
}
interface RejectedToken {
  region_id: string
  token_text: string
  char_span: [number, number]
  reject_reason: string
  parser_kind: string
}
interface ConflictToken {
  region_id: string
  token_text: string
  canonical_target: string
  parser_kind: string
  oscal_agreement: string
  char_span: [number, number]
}
interface Warning { kind: string; region_id?: string; message: string }

export interface DryRunResult {
  resolved: ResolvedToken[]
  rejected: RejectedToken[]
  conflicts: ConflictToken[]
  warnings: Warning[]
  summary: {
    resolved_count: number
    rejected_count: number
    conflict_count: number
    warning_count: number
  }
}

interface Props {
  result: DryRunResult
  onExport: () => void
  onDiscard?: () => void
}

const BADGE_LABEL: Record<PromotionBadge, string> = {
  auto_promote_candidate: 'auto-promote',
  queued_for_review:      'queued',
  warning_only:           'warning',
  approximate_bbox:       '~bbox',
}

export function DryRunPreviewPanel({ result, onExport, onDiscard }: Props) {
  // Per-conflict disposition state. Required when conflicts.length > 0
  // before export becomes enabled (per locked contract).
  const [dispositions, setDispositions] = useState<Record<string, 'accept_pdf' | 'accept_oscal' | 'needs_investigation'>>({})
  const [queueAll, setQueueAll] = useState(false)

  const exportEnabled = useMemo(() => {
    if (result.conflicts.length === 0) return true
    if (queueAll) return true
    return result.conflicts.every(c => dispositions[c.region_id + c.char_span.join(',')] !== undefined)
  }, [result.conflicts, dispositions, queueAll])

  return (
    <div className="pdf-lab-dry-run-panel" data-qid="pdf-lab:labeling:dry-run-preview">
      <div className="pdf-lab-dry-run-header">
        <span className="pdf-lab-dry-run-summary">
          <span className="pdf-lab-dry-run-state resolved">✓ Resolved ({result.summary.resolved_count})</span>
          <span className="pdf-lab-dry-run-state rejected">✗ Rejected ({result.summary.rejected_count})</span>
          <span className="pdf-lab-dry-run-state conflict">⚠ Conflicts ({result.summary.conflict_count})</span>
          {result.summary.warning_count > 0 && (
            <span className="pdf-lab-dry-run-state warning">! Warnings ({result.summary.warning_count})</span>
          )}
        </span>
      </div>

      {result.resolved.length > 0 && (
        <details className="pdf-lab-dry-run-section is-resolved" open={result.resolved.length <= 5}>
          <summary>Resolved ({result.resolved.length})</summary>
          <ul>
            {result.resolved.map((r, i) => (
              <li key={i} data-qid={`pdf-lab:labeling:dry-run-resolved-${i}`}>
                <code className="pdf-lab-dry-run-token">{r.token_text}</code>
                {' → '}
                <code className="pdf-lab-dry-run-target">{r.collection}/{r.canonical_target}</code>
                <span className={`pdf-lab-dry-run-badge pdf-lab-dry-run-badge-${r.promotion_badge}`}>
                  {BADGE_LABEL[r.promotion_badge]}
                </span>
                {r.bbox_quality === 'line' && (
                  <span className="pdf-lab-dry-run-line-marker" title="Line-evidence (pdf_oxide.block.v2 does not emit native token bboxes; Phase 1 verdict)">L</span>
                )}
                {r.bbox_quality === 'element' && (
                  <span className="pdf-lab-dry-run-line-marker" title="Element-evidence">E</span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      {result.rejected.length > 0 && (
        <details className="pdf-lab-dry-run-section is-rejected" open>
          <summary>Rejected ({result.rejected.length})</summary>
          <ul>
            {result.rejected.map((r, i) => (
              <li key={i} data-qid={`pdf-lab:labeling:dry-run-rejected-${i}`}>
                <code className="pdf-lab-dry-run-token">{r.token_text}</code>
                <span className="pdf-lab-dry-run-reject-reason"> — {r.reject_reason}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {result.conflicts.length > 0 && (
        <details className="pdf-lab-dry-run-section is-conflict" open>
          <summary>Conflicts ({result.conflicts.length})</summary>
          <div className="pdf-lab-dry-run-queue-all">
            <label>
              <input type="checkbox" checked={queueAll}
                onChange={e => setQueueAll(e.target.checked)} />
              Queue all conflicts for review (one-shot disposition)
            </label>
          </div>
          {!queueAll && (
            <ul>
              {result.conflicts.map((c, i) => {
                const key = c.region_id + c.char_span.join(',')
                const choice = dispositions[key]
                return (
                  <li key={i}>
                    <code>{c.token_text}</code>
                    {' → '}
                    <code>{c.canonical_target}</code>
                    <span className="pdf-lab-dry-run-conflict-agreement"> ({c.oscal_agreement})</span>
                    <div className="pdf-lab-dry-run-disposition">
                      {(['accept_pdf', 'accept_oscal', 'needs_investigation'] as const).map(opt => (
                        <label key={opt}>
                          <input type="radio" name={`disp-${key}`}
                            checked={choice === opt}
                            onChange={() => setDispositions(prev => ({ ...prev, [key]: opt }))} />
                          {opt.replace(/_/g, ' ')}
                        </label>
                      ))}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </details>
      )}

      {result.warnings.length > 0 && (
        <details className="pdf-lab-dry-run-section is-warning" open>
          <summary>Warnings ({result.warnings.length})</summary>
          <ul>
            {result.warnings.map((w, i) => (
              <li key={i} data-qid={`pdf-lab:labeling:dry-run-warning-${i}`}>
                <code className="pdf-lab-dry-run-warning-kind">{w.kind}</code>
                <span className="pdf-lab-dry-run-warning-msg"> — {w.message}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="pdf-lab-dry-run-actions">
        <button aria-label="Action"
          className="pdf-lab-dry-run-export"
          data-qid="pdf-lab:labeling:dry-run-export"
          disabled={!exportEnabled}
          onClick={onExport}
          title={exportEnabled
            ? "Write expected_elements.json + cross_ref_*.json artifacts (graph promotion is separately gated)"
            : `Resolve ${result.conflicts.length} conflict disposition(s) first`}
        >
          Export expected_elements.json
        </button>
        {onDiscard && (
          <button aria-label="Action" className="pdf-lab-dry-run-discard" onClick={onDiscard}>
            Discard preview
          </button>
        )}
        <span className="pdf-lab-dry-run-gate-note">
          Artifact export is NOT blocked by conflicts. Graph promotion (Phase 6) is separately gated.
        </span>
      </div>
    </div>
  )
}
