/**
 * MediaLockFact, extracted from DreamWorkspace.tsx.
 */
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'

export function MediaLockFact({
  label,
  value,
  title,
  tone,
  hash = false,
}: {
  label: string
  value: string
  title?: string
  tone?: 'pass'
  hash?: boolean
}) {
  return (
    <div style={styles.mediaLockFactRow}>
      <span style={styles.mediaLockFactLabel}>{label}</span>
      <strong
        title={title ?? value}
        style={hash ? styles.mediaLockHashValue : {
          ...styles.mediaLockFactValue,
          ...(tone === 'pass' ? styles.mediaLockPassValue : null),
        }}
      >
        {value}
      </strong>
    </div>
  )
}
