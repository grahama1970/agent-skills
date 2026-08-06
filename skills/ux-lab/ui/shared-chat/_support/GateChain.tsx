/**
 * GateChain — Collapsible evidence gate timeline.
 */
import { useState, memo } from 'react'
import { EMBRY } from './EmbryStyle'

export interface GateStep {
  gate: string
  passed: boolean
  detail: string
  duration?: number
}

export interface GateChainProps {
  gates: GateStep[]
  verdict: string
  tier?: string
}

const StatusDot = memo(function StatusDot({ passed }: { passed: boolean }) {
  const color = passed ? EMBRY.green : EMBRY.red
  return (
    <div style={{
      width: 18, height: 18, borderRadius: '50%',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 9, fontWeight: 700, color,
      background: `${color}15`, border: `1px solid ${color}40`,
      flexShrink: 0, zIndex: 2,
    }}>
      {passed ? '\u2713' : '\u2717'}
    </div>
  )
})

function verdictColor(verdict: string): string {
  const v = verdict.toUpperCase()
  if (v === 'SATISFIED') return EMBRY.green
  if (v === 'INCONCLUSIVE') return EMBRY.amber
  return EMBRY.red
}

export const GateChain = memo(function GateChain({ gates, verdict, tier }: GateChainProps) {
  const [expanded, setExpanded] = useState(false)
  const passed = gates.filter(g => g.passed).length
  const color = verdictColor(verdict)
  const tierLabel = tier === 'T2' ? ' [LLM]' : ''

  return (
    <div style={{ margin: '6px 0', background: EMBRY.bgCard, border: `1px solid ${color}33`, borderRadius: 8, overflow: 'hidden' }}>
      <button data-qid="gate-chain:toggle" data-qs-action="TOGGLE_GATE_CHAIN" title="Toggle evidence gates" onClick={() => setExpanded(v => !v)} style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 12px', background: 'none', border: 'none', textAlign: 'left', cursor: 'pointer',
        minHeight: 44,
      }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}` }} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: 11, fontWeight: 700, color }}>{verdict.toUpperCase()}{tierLabel}</span>
          <span style={{ fontSize: 9, color: EMBRY.dim, fontFamily: 'monospace', marginTop: 1 }}>{passed}/{gates.length} gates passed</span>
        </div>
        <span style={{ fontSize: 10, color: EMBRY.muted, transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>{'\u25BE'}</span>
      </button>
      {expanded && (
        <div style={{ padding: '4px 12px 12px 12px', position: 'relative' }}>
          <div style={{ position: 'absolute', left: 20, top: 12, bottom: 20, width: 1, borderLeft: `1px dashed ${color}40`, zIndex: 0 }} />
          {gates.map((g, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, position: 'relative', marginBottom: i < gates.length - 1 ? 8 : 0 }}>
              <StatusDot passed={g.passed} />
              <div style={{ flex: 1, minWidth: 0, paddingTop: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 10, fontFamily: 'monospace', fontWeight: 600, color: EMBRY.blue, textTransform: 'uppercase' }}>
                    {g.gate.replace(/^step_\d+_/, '')}
                  </span>
                  {g.duration && <span style={{ fontSize: 9, fontFamily: 'monospace', color: EMBRY.muted, marginLeft: 'auto' }}>
                    {g.duration < 1000 ? `${g.duration}ms` : `${(g.duration / 1000).toFixed(1)}s`}
                  </span>}
                </div>
                {g.detail && <div style={{ fontSize: 10, color: EMBRY.dim, marginTop: 2, lineHeight: 1.4 }}>{g.detail.slice(0, 200)}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
})
