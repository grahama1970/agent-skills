/**
 * SystemStatusIndicator, extracted from DreamWorkspace.tsx.
 */
import { nvis } from '../styles'


export function SystemStatusIndicator({ label, status }: { label: string; status: string }) {
  const isLoaded = status === 'loaded'
  const isError = status === 'error'
  return (
    <div style={nvis.systemStatusIndicator}>
      <span style={nvis.systemStatusLabel}>{label}</span>
      <span style={nvis.systemStatusValue}>
        <span style={isLoaded ? nvis.systemStatusDotLoaded : isError ? nvis.systemStatusDotError : nvis.systemStatusDotMissing} />
        <strong style={isLoaded ? nvis.systemStatusTextLoaded : isError ? nvis.systemStatusTextError : nvis.systemStatusTextMissing}>
          {status}
        </strong>
      </span>
    </div>
  )
}
