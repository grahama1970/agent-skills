/**
 * JsonProjectionViewer, extracted from DreamWorkspace.tsx.
 */
import { formatProviderContractBlocker, highlightJsonForProviderContract, highlightJsonLineForProviderContract, parseProviderContractAudioSummary, providerContractArtifactRole, providerContractAudioValueTone, providerContractJsonTokenStyle, providerContractStatusTone, providerFitDelta, providerFitMax, providerFitValue, rebindProviderContractAssetPath, shortProviderHash, videoProviderArtifactRole } from '../lib/provider'
import { nvis } from '../styles'
import { Code2 } from 'lucide-react'

export function JsonProjectionViewer({
  jsonPayload,
  label,
  compact = false,
}: {
  jsonPayload: unknown
  label: string
  compact?: boolean
}) {
  const formattedJson = typeof jsonPayload === 'string' ? jsonPayload : JSON.stringify(jsonPayload ?? {}, null, 2)
  return (
    <div style={nvis.providerContractSyntaxShell}>
      <div style={nvis.providerContractSyntaxToolbar}>
        <Code2 size={12} />
        <span>{label}</span>
      </div>
      <pre style={{ ...nvis.providerContractSyntaxHighlighter, maxHeight: compact ? 220 : 360 }}>
        <code style={nvis.providerContractSyntaxCode}>{highlightJsonForProviderContract(formattedJson)}</code>
      </pre>
    </div>
  )
}
