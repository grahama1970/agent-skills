/**
 * ThreatMatrixCard — Inline compact threat matrix summary for chat messages.
 * Shows coverage bar + counts + "View Full Matrix →" navigation button.
 */
import { memo } from 'react'
import { EMBRY } from './EmbryStyle'

export interface ThreatMatrixSummary {
  totalTechniques: number
  totalTactics: number
  satisfied: number
  inconclusive: number
  notSatisfied: number
  noEvidence: number
  datalake: string
}

interface ThreatMatrixCardProps {
  summary: ThreatMatrixSummary
  onNavigate?: () => void
}

export const ThreatMatrixCard = memo(function ThreatMatrixCard({ summary, onNavigate }: ThreatMatrixCardProps) {
  const { totalTechniques, totalTactics, satisfied, inconclusive, notSatisfied, noEvidence, datalake } = summary
  const coveredPct = totalTechniques > 0 ? Math.round((satisfied / totalTechniques) * 100) : 0
  const pctColor = coveredPct > 50 ? EMBRY.green : coveredPct > 20 ? EMBRY.amber : EMBRY.red

  return (
    <div style={{
      margin: '8px 0', padding: '12px 14px', borderRadius: 8,
      background: EMBRY.bgCard, border: `1px solid ${EMBRY.border}`,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 900, color: EMBRY.white, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            {datalake} Threat Matrix
          </div>
          <div style={{ fontSize: 9, color: EMBRY.dim, marginTop: 1 }}>
            {totalTechniques} techniques · {totalTactics} tactics
          </div>
        </div>
        <span style={{ fontSize: 18, fontWeight: 900, fontFamily: 'monospace', color: pctColor }}>
          {coveredPct}%
        </span>
      </div>

      {/* Coverage bar */}
      <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', background: EMBRY.bgDeep }}>
        {totalTechniques > 0 && <>
          <div style={{ width: `${(satisfied / totalTechniques) * 100}%`, background: EMBRY.green, transition: 'width 0.4s' }} />
          <div style={{ width: `${(inconclusive / totalTechniques) * 100}%`, background: EMBRY.amber, transition: 'width 0.4s' }} />
          <div style={{ width: `${(notSatisfied / totalTechniques) * 100}%`, background: EMBRY.red, transition: 'width 0.4s' }} />
        </>}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 12, marginTop: 6 }}>
        {[
          { label: 'satisfied', count: satisfied, color: EMBRY.green },
          { label: 'inconclusive', count: inconclusive, color: EMBRY.amber },
          { label: 'not satisfied', count: notSatisfied, color: EMBRY.red },
          { label: 'no evidence', count: noEvidence, color: EMBRY.muted },
        ].map(({ label, count, color }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
            <span style={{ fontSize: 9, color: EMBRY.dim }}>{count} {label}</span>
          </div>
        ))}
      </div>

      {/* Navigate button */}
      {onNavigate && (
        <button data-qid="threat-matrix:action" data-qs-action="VIEW_FULL_THREAT_MATRIX" title="View the full threat matrix with all techniques and coverage details" onClick={onNavigate} style={{
          marginTop: 10, width: '100%', padding: '6px 0', borderRadius: 6,
          border: `1px solid ${EMBRY.accent}44`, background: `${EMBRY.accent}12`,
          color: EMBRY.accent, fontSize: 10, fontWeight: 700,
          cursor: 'pointer', letterSpacing: '0.05em',
          minHeight: 44,
        }}>
          View Full Threat Matrix →
        </button>
      )}
    </div>
  )
})
