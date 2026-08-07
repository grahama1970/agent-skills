/**
 * GateMiniBadge, extracted from DreamWorkspace.tsx.
 */
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from '../lib/status'
import { AlertTriangle, CheckCircle2, ShieldAlert } from 'lucide-react'

export function GateMiniBadge({ status, label }: { status: string; label: string }) {
  const tone = statusTone(status)
  const Icon = tone === 'pass' ? CheckCircle2 : tone === 'blocked' ? ShieldAlert : AlertTriangle
  return (
    <span title={statusLabel(status)} aria-label={`${label}: ${statusLabel(status)}`} style={{ ...styles.gateMiniBadge, ...toneStyles[tone] }}>
      <Icon size={12} />
      <span>{label}</span>
    </span>
  )
}
