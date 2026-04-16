import { NVIS } from '../theme'

interface MetricCardProps {
  label: string
  value: string | number
  delta?: number
  /** If true, higher values are "good" (delta up = green). If false, lower is good (delta down = green). */
  higherIsGood?: boolean
  color?: string
}

export function MetricCard({ label, value, delta, higherIsGood = true, color }: MetricCardProps) {
  let deltaColor: string = NVIS.dim
  let deltaIcon = ''
  if (delta !== undefined && delta !== 0) {
    const isPositive = delta > 0
    const isGood = higherIsGood ? isPositive : !isPositive
    deltaColor = isGood ? NVIS.green : NVIS.red
    deltaIcon = isPositive ? '\u25B2' : '\u25BC'
  }

  return (
    <div
      style={{
        backgroundColor: NVIS.surface,
        border: `1px solid ${NVIS.borderSolid}`,
        borderRadius: 6,
        padding: '12px 16px',
      }}
    >
      <div style={{ fontSize: 11, color: NVIS.dim, marginBottom: 4 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 20, fontWeight: 600, color: color ?? NVIS.white }}>{value}</span>
        {delta !== undefined && delta !== 0 && (
          <span style={{ fontSize: 11, color: deltaColor }}>
            {deltaIcon} {Math.abs(delta).toFixed(1)}
          </span>
        )}
      </div>
    </div>
  )
}
