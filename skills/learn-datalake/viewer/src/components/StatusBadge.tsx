import { NVIS } from '../theme'

type Status = 'running' | 'stopped' | 'error' | 'timeout' | 'success' | 'warning'

const STATUS_CONFIG: Record<Status, { color: string; icon: string; label: string }> = {
  running: { color: NVIS.green, icon: '\u25CF', label: 'Running' },
  stopped: { color: NVIS.dim, icon: '\u25CB', label: 'Stopped' },
  error: { color: NVIS.red, icon: '\u2716', label: 'Error' },
  timeout: { color: NVIS.dim, icon: '\u29D6', label: 'Timeout' },
  success: { color: NVIS.green, icon: '\u2714', label: 'Success' },
  warning: { color: NVIS.amber, icon: '\u26A0', label: 'Warning' },
}

interface StatusBadgeProps {
  status: string
  label?: string
  size?: 'sm' | 'md'
}

export function StatusBadge({ status, label, size = 'sm' }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status as Status] ?? STATUS_CONFIG.stopped
  const displayLabel = label ?? config.label
  const fontSize = size === 'sm' ? 11 : 13
  const padding = size === 'sm' ? '2px 8px' : '4px 12px'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize,
        fontFamily: 'monospace',
        padding,
        borderRadius: 4,
        color: config.color,
        backgroundColor: `${config.color}15`,
        border: `1px solid ${config.color}30`,
      }}
    >
      <span>{config.icon}</span>
      {displayLabel}
    </span>
  )
}
