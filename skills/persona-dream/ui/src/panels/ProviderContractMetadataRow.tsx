/**
 * ProviderContractMetadataRow, extracted from DreamWorkspace.tsx.
 */
import { nvis } from '../styles'


export function ProviderContractMetadataRow({
  label,
  value,
  title,
  tone,
}: {
  label: string
  value: string
  title?: string
  tone: 'success' | 'warning' | 'neutral' | 'muted'
}) {
  const valueStyle = tone === 'success'
    ? nvis.providerContractMetaValueSuccess
    : tone === 'warning'
      ? nvis.providerContractMetaValueWarning
      : tone === 'muted'
        ? nvis.providerContractMetaValueMuted
        : nvis.providerContractMetaValue
  return (
    <div style={nvis.providerContractMetadataRow}>
      <span style={nvis.providerContractMetaLabel}>{label}</span>
      <code style={valueStyle} title={title ?? value}>{value}</code>
    </div>
  )
}
