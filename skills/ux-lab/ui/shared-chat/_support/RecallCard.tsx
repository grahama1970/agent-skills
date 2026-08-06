/**
 * RecallCard — Collapsible memory recall results with score bars.
 */
import { useState, memo } from 'react'
import { EMBRY } from './EmbryStyle'

export interface RecallItem {
  _key?: string
  _source?: string
  control_id?: string
  name?: string
  question?: string
  problem?: string
  solution?: string
  scores?: { bm25?: number; graph?: number; dense?: number; freshness?: number }
}

export interface RecallCardProps {
  items: RecallItem[]
  resultCount: number
  confidence?: number
}

const ScoreBar = memo(function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
      <span style={{ color: EMBRY.dim, width: 42, textAlign: 'right', fontFamily: 'monospace', fontSize: 12 }}>{label}</span>
      <div style={{ flex: 1, height: 3, background: EMBRY.bgDeep, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(100, value * 100)}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.4s ease' }} />
      </div>
      <span style={{ fontFamily: 'monospace', color: EMBRY.dim, width: 28, fontSize: 12 }}>{value.toFixed(2)}</span>
    </div>
  )
})

function itemLabel(item: RecallItem): string {
  const cid = item.control_id ?? ''
  const text = item.question ?? item.name ?? item.problem ?? item.solution ?? ''
  if (cid && text) return `[${cid}] ${text.slice(0, 100)}`
  if (cid) return cid
  return text.slice(0, 120) || item._key || '?'
}

function sourceColor(src?: string): string {
  if (!src) return EMBRY.dim
  if (src === 'sparta_controls') return EMBRY.accent
  if (src === 'sparta_qra') return EMBRY.blue
  if (src === 'sparta_relationships') return EMBRY.amber
  return EMBRY.green
}

export const RecallCard = memo(function RecallCard({ items, resultCount, confidence }: RecallCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [debugIdx, setDebugIdx] = useState(-1)

  // Calibrate confidence display with context
  const confNorm = confidence != null ? (confidence > 1 ? Math.min(confidence / 100, 1) : confidence) : null
  const confPct = confNorm != null ? Math.round(confNorm * 100) : null
  const confColor = confPct != null ? (confPct > 70 ? EMBRY.green : confPct > 40 ? EMBRY.amber : EMBRY.red) : EMBRY.muted
  const confLabel = confPct != null ? (confPct > 80 ? 'High confidence' : confPct > 50 ? 'Moderate confidence' : 'Low confidence') : ''
  const confTooltip = confPct != null ? `${confLabel}: BM25 lexical + cosine semantic + graph traversal combined score. >${'70'}%=strong match, 40-70%=partial, <40%=weak` : ''

  return (
    <div style={{ margin: '6px 0' }}>
      <button data-qid="recall:toggle" data-qs-action="TOGGLE_RECALL_RESULTS" onClick={() => setExpanded(v => !v)} title="Memory recall results — click to expand" style={{
        display: 'flex', alignItems: 'center', gap: 6, width: '100%',
        fontSize: 13, color: EMBRY.dim, background: 'none', border: 'none',
        cursor: 'pointer', padding: '4px 0', textAlign: 'left',
        minHeight: 44,
      }}>
        {confPct != null && (
          <span style={{ color: confColor, fontWeight: 700, fontFamily: 'monospace', fontSize: 12 }} title={confTooltip}>
            {confPct}%
          </span>
        )}
        <span>Memory recall</span>
        <span style={{ color: EMBRY.muted }}>{'\u00B7'}</span>
        <span>{resultCount} results</span>
        {confLabel && <span style={{ fontSize: 12, color: confColor, opacity: 0.7 }}>{confLabel}</span>}
        <span style={{ marginLeft: 'auto', fontSize: 12, color: EMBRY.muted, transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}>{'\u25BE'}</span>
      </button>
      {expanded && (
        <div style={{ borderLeft: `2px solid ${EMBRY.border}`, marginLeft: 4, paddingLeft: 10, marginTop: 4 }}>
          {items.slice(0, 8).map((item, i) => (
            <div key={item._key ?? i} style={{
              padding: '6px 0',
              borderBottom: i < Math.min(items.length, 8) - 1 ? `1px solid ${EMBRY.border}` : 'none',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {item._source && <span style={{ fontSize: 12, fontWeight: 700, fontFamily: 'monospace', color: sourceColor(item._source), textTransform: 'uppercase', letterSpacing: '0.05em' }}>{item._source.replace('sparta_', '')}</span>}
                <span style={{ fontSize: 13, color: EMBRY.white, fontWeight: 500 }}>{itemLabel(item).slice(0, 80)}</span>
              </div>
              {/* Debug scores — collapsed by default */}
              {item.scores && (
                <details style={{ marginTop: 4 }} open={debugIdx === i} onToggle={(e) => setDebugIdx((e.currentTarget as HTMLDetailsElement).open ? i : -1)}>
                  <summary style={{ fontSize: 12, color: EMBRY.muted, cursor: 'pointer', userSelect: 'none' }}>Retrieval scores (BM25 lexical · Graph traversal · Dense semantic · Freshness)</summary>
                  <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <ScoreBar label="BM25" value={item.scores.bm25 ?? 0} color={EMBRY.accent} />
                    <ScoreBar label="Graph" value={item.scores.graph ?? 0} color={EMBRY.blue} />
                    <ScoreBar label="Dense" value={item.scores.dense ?? 0} color={EMBRY.green} />
                    <ScoreBar label="Fresh" value={item.scores.freshness ?? 0} color={EMBRY.amber} />
                  </div>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
})
