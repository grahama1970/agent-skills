import { NVIS } from '../theme'

interface ProgressBarProps {
  value: number // 0-100
  label?: string
  color?: string
  height?: number
}

export function ProgressBar({ value, label, color, height = 6 }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, value))
  const barColor = color ?? (pct >= 90 ? NVIS.green : pct >= 70 ? NVIS.amber : NVIS.red)

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? `${Math.round(pct)}%`}
        style={{
          flex: 1,
          height,
          backgroundColor: `${NVIS.dim}20`,
          borderRadius: height / 2,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            backgroundColor: barColor,
            borderRadius: height / 2,
            transition: 'width 0.3s ease',
          }}
        />
      </div>
      {label !== undefined && (
        <span aria-hidden="true" style={{ fontSize: 11, color: NVIS.dim, minWidth: 36, textAlign: 'right' }}>{label}</span>
      )}
    </div>
  )
}
