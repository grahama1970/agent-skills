/**
 * StatusBadge, extracted from DreamWorkspace.tsx.
 */
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from '../lib/status'
import { AlertTriangle, CheckCircle2, ShieldAlert } from 'lucide-react'

export function StatusBadge({ status }: { status: string }) {
  const tone = statusTone(status)
  const Icon = tone === 'pass' ? CheckCircle2 : tone === 'blocked' ? ShieldAlert : AlertTriangle
  const label = statusLabel(status)
  return (
    <span title={label} aria-label={`Status: ${label}`} style={{ ...styles.badge, ...toneStyles[tone] }}>
      <Icon size={12} />
      {label}
    </span>
  )
}
