/**
 * ArtifactField, extracted from DreamWorkspace.tsx.
 */
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'

export function ArtifactField({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <dt style={styles.artifactLabel}>{label}</dt>
      <dd style={styles.artifactValue}>{value || 'missing'}</dd>
    </div>
  )
}
