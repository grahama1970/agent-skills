/**
 * ProviderContractAudioSummary, extracted from DreamWorkspace.tsx.
 */
import { formatProviderContractBlocker, highlightJsonForProviderContract, highlightJsonLineForProviderContract, parseProviderContractAudioSummary, providerContractArtifactRole, providerContractAudioValueTone, providerContractJsonTokenStyle, providerContractStatusTone, providerFitDelta, providerFitMax, providerFitValue, rebindProviderContractAssetPath, shortProviderHash, videoProviderArtifactRole } from '../lib/provider'
import { nvis } from '../styles'

export function ProviderContractAudioSummary({ value }: { value: string }) {
  const pairs = parseProviderContractAudioSummary(value)
  if (pairs.length === 0) {
    return <code style={nvis.providerContractPanelSummary}>{value}</code>
  }
  return (
    <div style={nvis.providerContractAudioPillRow} aria-label="Distilled audio parameters">
      {pairs.map((pair) => (
        <span key={`${pair.label}:${pair.value}`} style={nvis.providerContractAudioPill} title={`${pair.label}=${pair.value}`}>
          <span style={nvis.providerContractAudioPillLabel}>{pair.label}</span>
          <span style={{
            ...nvis.providerContractAudioPillValue,
            ...(providerContractAudioValueTone(pair.value) === 'warning' ? nvis.providerContractAudioPillValueWarning : nvis.providerContractAudioPillValueNeutral),
          }}>
            {pair.value}
          </span>
        </span>
      ))}
    </div>
  )
}
