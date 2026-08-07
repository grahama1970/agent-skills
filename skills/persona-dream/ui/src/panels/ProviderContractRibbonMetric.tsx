/**
 * ProviderContractRibbonMetric, extracted from DreamWorkspace.tsx.
 */
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { nvis } from '../styles'

export function ProviderContractRibbonMetric({
  label,
  value,
  tone,
}: {
  label: string
  value: unknown
  tone: 'pass' | 'dry' | 'blocked'
}) {
  const toneStyle = tone === 'pass'
    ? nvis.providerContractRibbonValuePass
    : tone === 'dry'
      ? nvis.providerContractRibbonValueDry
      : nvis.providerContractRibbonValueBlocked
  return (
    <div style={nvis.providerContractRibbonMetric}>
      <span style={nvis.providerContractRibbonLabel}>{label}</span>
      <strong style={{ ...nvis.providerContractRibbonValue, ...toneStyle }} title={String(value ?? '')}>{dreamDisplayCode(String(value ?? 'missing'))}</strong>
    </div>
  )
}
