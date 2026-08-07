import { Lock } from 'lucide-react'
/**
 * ProviderContractFrameState, extracted from DreamWorkspace.tsx.
 */
import { assetExtension, dreamAssetUrl } from '../lib/asset'
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { formatProviderContractBlocker, highlightJsonForProviderContract, highlightJsonLineForProviderContract, parseProviderContractAudioSummary, providerContractArtifactRole, providerContractAudioValueTone, providerContractJsonTokenStyle, providerContractStatusTone, providerFitDelta, providerFitMax, providerFitValue, rebindProviderContractAssetPath, shortProviderHash, videoProviderArtifactRole } from '../lib/provider'
import { nvis } from '../styles'
import { ProviderContractMetadataRow } from './ProviderContractMetadataRow'

export function ProviderContractFrameState({
  label,
  asset,
  selected,
  selectedField,
  providerUrl,
}: {
  label: string
  asset?: Record<string, unknown>
  selected: boolean
  selectedField: string
  providerUrl: unknown
}) {
  const assetId = String(asset?.asset_id ?? 'missing')
  const publicationStatus = String(asset?.publication_status ?? 'MISSING')
  const probeStatus = String(asset?.url_probe_status ?? 'MISSING')
  const urlValue = typeof providerUrl === 'string' && providerUrl.trim() ? 'present' : 'missing'
  const imageUrl = dreamAssetUrl(String(asset?.local_path ?? asset?.path ?? ''))
  return (
    <div style={nvis.providerContractFrameState}>
      <div style={nvis.providerContractFrameHeader}>
        <strong>{label}</strong>
        <span>{assetId}</span>
      </div>
      {imageUrl && (
        <div style={nvis.providerContractFramePreview}>
          <img src={imageUrl} alt={`${assetId} locked pre-contract frame`} style={nvis.providerContractFrameImage} />
          <span style={nvis.providerContractFrameCaption}>
            <Lock size={11} style={nvis.providerContractFrameCaptionIcon} />
            Pre-contract media lock
          </span>
        </div>
      )}
      <div style={nvis.providerContractFrameRows}>
        <ProviderContractMetadataRow label="SHA" value={shortProviderHash(String(asset?.sha256 ?? 'missing'))} title={String(asset?.sha256 ?? 'missing')} tone="muted" />
        <ProviderContractMetadataRow label="Lock" value={dreamDisplayCode(String(asset?.media_lock_status ?? 'missing'))} title={String(asset?.media_lock_status ?? 'missing')} tone={String(asset?.media_lock_status ?? '').includes('LOCKED') ? 'warning' : 'neutral'} />
        <ProviderContractMetadataRow label="Identity" value={dreamDisplayCode(String(asset?.identity_continuity_status ?? 'missing'))} title={String(asset?.identity_continuity_status ?? 'missing')} tone={String(asset?.identity_continuity_status ?? '').toUpperCase() === 'PASS' ? 'success' : 'neutral'} />
        <ProviderContractMetadataRow label="Publication" value={dreamDisplayCode(publicationStatus)} title={publicationStatus} tone={publicationStatus.includes('NOT_PUBLISHED') ? 'warning' : 'neutral'} />
        <ProviderContractMetadataRow label="Probe" value={dreamDisplayCode(probeStatus)} title={probeStatus} tone={probeStatus === 'NOT_RUN' ? 'neutral' : 'muted'} />
        {selected && (
          <>
            <ProviderContractMetadataRow label={selectedField} value={urlValue} title={urlValue} tone={urlValue === 'present' ? 'success' : 'warning'} />
          </>
        )}
      </div>
    </div>
  )
}
