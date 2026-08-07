/**
 * ProviderContractState, extracted from DreamWorkspace.tsx.
 */
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { formatProviderContractBlocker, highlightJsonForProviderContract, highlightJsonLineForProviderContract, parseProviderContractAudioSummary, providerContractArtifactRole, providerContractAudioValueTone, providerContractJsonTokenStyle, providerContractStatusTone, providerFitDelta, providerFitMax, providerFitValue, rebindProviderContractAssetPath, shortProviderHash, videoProviderArtifactRole } from '../lib/provider'
import { nvis } from '../styles'

export function ProviderContractState({
  label,
  value,
  detail,
}: {
  label: string
  value: unknown
  detail?: string
}) {
  const status = String(value ?? 'MISSING')
  return (
    <div style={nvis.providerContractStateCard}>
      <span style={nvis.providerContractStateLabel}>{label}</span>
      <strong style={providerContractStatusTone(status)}>{dreamDisplayCode(status)}</strong>
      {detail && <span style={nvis.providerContractStateDetail}>{dreamDisplayCode(detail)}</span>}
    </div>
  )
}
