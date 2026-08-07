/**
 * ProviderContractPanel, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type {ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ProviderContractPanelRow, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry} from '../types'
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { formatProviderContractBlocker, highlightJsonForProviderContract, highlightJsonLineForProviderContract, parseProviderContractAudioSummary, providerContractArtifactRole, providerContractAudioValueTone, providerContractJsonTokenStyle, providerContractStatusTone, providerFitDelta, providerFitMax, providerFitValue, rebindProviderContractAssetPath, shortProviderHash, videoProviderArtifactRole } from '../lib/provider'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from '../lib/status'
import { firstString, payloadArray, payloadObject } from '../lib/text'
import { nvis } from '../styles'
import { JsonProjectionViewer } from './JsonProjectionViewer'
import { ProviderContractAudioSummary } from './ProviderContractAudioSummary'
import { ProviderContractFrameState } from './ProviderContractFrameState'
import { ProviderContractRibbonMetric } from './ProviderContractRibbonMetric'
import { ProviderContractState } from './ProviderContractState'
import { SystemStatusIndicator } from './SystemStatusIndicator'
import { AlertTriangle, Clapperboard, ClipboardCheck, Copy, Info, ShieldAlert, Table2 } from 'lucide-react'

export function ProviderContractPanel({ stage }: { stage: DreamStage }) {
  const contractArtifacts = useMemo(() => {
    const byRole = new Map<string, DreamArtifact>()
    for (const artifact of stage.artifacts) {
      const role = providerContractArtifactRole(artifact)
      if (role && !byRole.has(role)) byRole.set(role, artifact)
    }
    return [...byRole.entries()].map(([role, artifact]) => ({ role, artifact }))
  }, [stage.artifacts])
  const [loaded, setLoaded] = useState<LoadedVideoArtifact[]>([])
  const revisionRoot = useMemo(() => {
    const marker = '/phase_10_provider_contract/'
    const artifactPath = stage.artifacts.find((artifact) => artifact.path.includes(marker))?.path
    return artifactPath ? artifactPath.slice(0, artifactPath.indexOf(marker)) : null
  }, [stage.artifacts])

  useEffect(() => {
    let cancelled = false
    async function loadArtifacts() {
      const next: LoadedVideoArtifact[] = []
      for (const item of contractArtifacts) {
        try {
          const response = await fetch(`/api/projects/dream/asset?path=${encodeURIComponent(item.artifact.path)}`)
          if (!response.ok) throw new Error(`HTTP ${response.status}`)
          const payload = await response.json()
          next.push({
            ...item,
            payload: payloadObject(payload),
          })
        } catch (error) {
          next.push({
            ...item,
            payload: null,
            error: error instanceof Error ? error.message : String(error),
          })
        }
      }
      if (!cancelled) setLoaded(next)
    }
    void loadArtifacts()
    return () => { cancelled = true }
  }, [contractArtifacts])

  const byRole = useMemo(() => new Map(loaded.map((item) => [item.role, item])), [loaded])
  const contract = byRole.get('contract')?.payload ?? null
  const receipt = byRole.get('contract_receipt')?.payload ?? null
  const gateReceipt = byRole.get('gate_receipt')?.payload ?? null
  const payloadByPanel = byRole.get('payload_by_panel')?.payload ?? null
  const fieldMappingDocument = byRole.get('field_mapping')?.payload ?? null
  const publicationReceipt = byRole.get('publication_receipt')?.payload ?? null
  const probeReceipt = byRole.get('probe_receipt')?.payload ?? null
  const schemaReceipt = byRole.get('schema_receipt')?.payload ?? null
  const reviewReceipt = byRole.get('review_receipt')?.payload ?? null
  const submittedRequest = byRole.get('submitted_request')?.payload ?? null
  const returnEnvelope = byRole.get('return_envelope')?.payload ?? null
  const shotBible = byRole.get('shot_bible')?.payload ?? null
  const submittedBody = payloadObject(submittedRequest?.provider_request_body)
  const requestBody = submittedBody
    ?? payloadObject(payloadByPanel?.assembled_request_preview)
    ?? payloadObject(payloadObject(contract?.provider_request)?.body)
  const providerRequest = {
    status: firstString(payloadByPanel?.status, payloadObject(contract?.provider_request)?.status) ?? 'MISSING_PROVIDER_REQUEST',
    body: requestBody,
    submitted: Boolean(returnEnvelope) || submittedRequest?.submitted === true || payloadByPanel?.submitted === true || receipt?.submitted === true,
  }
  const providerInput = payloadObject(requestBody?.input) ?? requestBody
  const submittedPrompts = payloadArray(providerInput?.multi_prompt)
  const lookLock = payloadObject(shotBible?.look_lock)
  const sourceShots = payloadArray(shotBible?.shots)
  const contractPanels = payloadArray(contract?.panels)
  const projectedPanels = payloadArray(payloadByPanel?.panel_payloads)
  const publicationComplete = dreamNumber(publicationReceipt?.assets_published) != null
    && dreamNumber(publicationReceipt?.assets_published) === dreamNumber(publicationReceipt?.assets_required)
  const mediaPlan = {
    status: firstString(publicationReceipt?.status) ?? 'MISSING_PROVIDER_MEDIA_PUBLICATION_RECEIPT',
    asset_count: dreamNumber(publicationReceipt?.assets_required) ?? contractPanels.length * 2,
    provider_accessible_url_created: publicationComplete,
  }
  const costContract = { status: 'BLOCKED_COST_ESTIMATE_UNVERIFIED', paid_call_authorized: false }
  const entitlementContract = { status: 'BLOCKED_PROVIDER_ENTITLEMENT_UNVERIFIED', fal_api_key_observed: false }
  const asyncContract = { status: 'MISSING_ASYNC_RETURN_CONTRACT', selected_async_mode: null }
  const manualAcceptance = { status: 'MISSING', accepted: false }
  const fieldMapping = payloadArray(fieldMappingDocument?.mappings ?? contract?.field_mapping)
  const publicationAssets = contractPanels.flatMap((panel) => {
    const lockedMedia = payloadObject(panel.locked_media)
    const start = payloadObject(lockedMedia?.start_frame)
    const end = payloadObject(lockedMedia?.end_frame)
    return [
      start ? {
        ...start,
        panel_id: panel.panel_id,
        frame_role: 'start_frame',
        local_path: rebindProviderContractAssetPath(String(start.absolute_path ?? start.relative_path ?? ''), revisionRoot),
        media_lock_status: start.status,
        identity_continuity_status: start.identity_continuity_status ?? 'NOT_RECORDED',
        publication_status: start.provider_accessible_url ? 'PUBLISHED' : publicationReceipt?.status,
        url_probe_status: start.provider_accessible_url ? probeReceipt?.status : 'NOT_RUN',
      } : null,
      end ? {
        ...end,
        panel_id: panel.panel_id,
        frame_role: 'end_frame',
        local_path: rebindProviderContractAssetPath(String(end.absolute_path ?? end.relative_path ?? ''), revisionRoot),
        media_lock_status: end.status,
        identity_continuity_status: end.identity_continuity_status ?? 'NOT_RECORDED',
        publication_status: end.provider_accessible_url ? 'PUBLISHED' : publicationReceipt?.status,
        url_probe_status: end.provider_accessible_url ? probeReceipt?.status : 'NOT_RUN',
      } : null,
    ].filter(Boolean) as Array<Record<string, unknown>>
  })
  const contractPanelPayloads = contractPanels.map((panel, index) => {
    const panelId = String(panel.panel_id ?? `panel_${index + 1}`)
    const lockedMedia = payloadObject(panel.locked_media)
    const start = publicationAssets.find((asset) => asset.panel_id === panelId && asset.frame_role === 'start_frame')
    const end = publicationAssets.find((asset) => asset.panel_id === panelId && asset.frame_role === 'end_frame')
    const providerIntent = payloadObject(panel.distilled_provider_intent)
    const sourceAudio = payloadObject(panel.source_audio)
    const projected = projectedPanels.find((item) => item.panel_id === panelId)
    const projectedInput = payloadObject(projected?.provider_payload_projection) ?? {}
    return {
      panel_id: panelId,
      accepted_start_frame: start,
      accepted_end_frame: end,
      source_evidence: {
        action: panel.source_storyboard_action,
        dialogue: panel.source_dialogue,
        voice_status: sourceAudio?.voice_id_status ?? sourceAudio?.dialogue_status,
      },
      distillation: {
        audio_strategy: sourceAudio?.dialogue_status,
        voice_status: sourceAudio?.voice_id_status,
        omitted_context_ref: providerIntent?.omitted_context_ref,
      },
      provider_payload_projection: {
        model: firstString(payloadByPanel?.endpoint, contract?.provider_endpoint),
        input: {
          ...projectedInput,
          aspect_ratio: providerIntent?.aspect_ratio,
          start_image_url: start?.provider_accessible_url ?? null,
          end_image_url: end?.provider_accessible_url ?? null,
        },
        submitted: false,
      },
    }
  })
  const requestBodyJson = JSON.stringify(requestBody ?? {}, null, 2)
  const dryRunBlockers: string[] = []
  const liveBlockers = [...new Set([
    ...dreamList(payloadByPanel?.blockers),
    ...dreamList(receipt?.blockers),
    ...dreamList(reviewReceipt?.blockers),
  ])]
  const nonClaims = [...new Set([
    ...dreamList(payloadObject(contract?.claims)?.does_not_prove),
    ...dreamList(payloadObject(payloadByPanel?.claims)?.does_not_prove),
    ...dreamList(payloadObject(receipt?.claims)?.does_not_prove),
  ])]
  const providerId = firstString(submittedRequest?.provider_id, contract?.selected_provider, payloadByPanel?.provider, schemaReceipt?.provider) ?? 'missing'
  const endpoint = firstString(submittedRequest?.endpoint, contract?.provider_endpoint, payloadByPanel?.endpoint, schemaReceipt?.model_endpoint) ?? 'missing'
  const status = firstString(contract?.status, receipt?.status, gateReceipt?.status) ?? 'MISSING_PHASE10_PROVIDER_CONTRACT'
  const liveSubmitStatus = firstString(payloadByPanel?.status, receipt?.live_submit_status, gateReceipt?.live_submit_status) ?? 'DRY_RUN_NOT_LIVE_SUBMITTABLE'
  const payloadHash = firstString(submittedRequest?.request_body_sha256, payloadByPanel?.payload_sha256, receipt?.payload_sha256) ?? 'missing'
  const submitted = providerRequest.submitted
  const paidCallAuthorized = contract?.paid_call_authorized ?? receipt?.paid_call_authorized
  const providerLive = contract?.live_provider_call ?? payloadByPanel?.live_provider_call ?? receipt?.live_provider_call
  const providerAttempts = dreamNumber(contract?.actual_provider_call_attempts) ?? dreamNumber(receipt?.actual_provider_call_attempts) ?? 0
  const hasContract = Boolean(contract)
  const panelPayloadRows = useMemo<ProviderContractPanelRow[]>(() => {
    if (contractPanelPayloads.length > 0) {
      return contractPanelPayloads.map((panelPayload, index) => {
        const projection = payloadObject(panelPayload.provider_payload_projection)
        const projectionInput = payloadObject(projection?.input)
        const sourceEvidence = payloadObject(panelPayload.source_evidence)
        const distillation = payloadObject(panelPayload.distillation)
        const panelId = String(panelPayload.panel_id ?? `panel_${index + 1}`)
        const submittedPrompt = payloadObject(submittedPrompts[index])
        const sourceShot = sourceShots.find((item) => item.panel_id === panelId)
        return {
          panelId,
          start: payloadObject(panelPayload.accepted_start_frame) ?? undefined,
          end: payloadObject(panelPayload.accepted_end_frame) ?? undefined,
          duration: submittedPrompt?.duration ?? projectionInput?.duration,
          selected: Boolean(projectionInput?.start_image_url || projectionInput?.end_image_url)
            && projectionInput?.start_image_url === providerInput?.start_image_url
            && projectionInput?.end_image_url === providerInput?.end_image_url,
          sourceEvidence,
          distillation,
          dialogue: Array.isArray(sourceEvidence?.dialogue)
            ? sourceEvidence.dialogue.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
            : [],
          submittedPrompt,
          sourceShot,
          lookLock,
          panelRequestJson: JSON.stringify(submittedPrompt ?? projection ?? {}, null, 2),
          panelSummary: `dialogue=${dreamBooleanLabel(sourceEvidence?.dialogue)} / voice=${String(sourceEvidence?.voice_status ?? 'missing')} / duration=${String(projectionInput?.duration ?? 'missing')} / aspect=${String(projectionInput?.aspect_ratio ?? 'missing')}`,
        }
      })
    }
    const byPanel = new Map<string, { panelId: string; start?: Record<string, unknown>; end?: Record<string, unknown> }>()
    for (const asset of publicationAssets) {
      const assetId = String(asset.asset_id ?? '')
      const match = assetId.match(/^(sb_\d+)\.(start|end)_frame$/)
      if (!match) continue
      const panelId = match[1]
      const frameKind = match[2] as 'start' | 'end'
      const row = byPanel.get(panelId) ?? { panelId }
      row[frameKind] = asset
      byPanel.set(panelId, row)
    }
    const selectedStart = String(providerInput?.start_frame_asset_id ?? '')
    const selectedEnd = String(providerInput?.end_frame_asset_id ?? '')
    const baseInput = providerInput ?? {}
    const baseRequest = requestBody ?? {}
    return Array.from(byPanel.values())
      .sort((a, b) => a.panelId.localeCompare(b.panelId))
      .map((row) => {
        const startAssetId = String(row.start?.asset_id ?? `${row.panelId}.start_frame`)
        const endAssetId = String(row.end?.asset_id ?? `${row.panelId}.end_frame`)
        const startTime = dreamNumber(row.start?.time_s)
        const endTime = dreamNumber(row.end?.time_s)
        const duration = startTime != null && endTime != null && endTime > startTime
          ? Number((endTime - startTime).toFixed(3))
          : baseInput.duration
        const panelRequest = {
          ...baseRequest,
          input: {
            ...baseInput,
            duration,
            end_frame_asset_id: endAssetId,
            end_image_url: row.end?.provider_accessible_url ?? null,
            image_url: row.start?.provider_accessible_url ?? null,
            start_frame_asset_id: startAssetId,
          },
          submitted: false,
        }
        return {
          ...row,
          duration,
          dialogue: [] as Array<Record<string, unknown>>,
          submittedPrompt: null,
          sourceShot: null,
          lookLock: null,
          selected: startAssetId === selectedStart && endAssetId === selectedEnd,
          panelRequestJson: JSON.stringify(panelRequest, null, 2),
          panelSummary: `image_url=${dreamBooleanLabel(row.start?.provider_accessible_url)} / end_image_url=${dreamBooleanLabel(row.end?.provider_accessible_url)} / duration=${String(duration ?? 'missing')} / aspect=${String(baseInput.aspect_ratio ?? 'missing')}`,
        }
      })
  }, [contractPanelPayloads, publicationAssets, providerInput, requestBody, submittedPrompts, sourceShots, lookLock])
  const [copyStatus, setCopyStatus] = useState('')
  const copyRequestBody = async () => {
    try {
      await navigator.clipboard.writeText(requestBodyJson)
      setCopyStatus('Copied')
      window.setTimeout(() => setCopyStatus(''), 1600)
    } catch {
      setCopyStatus('Copy failed')
      window.setTimeout(() => setCopyStatus(''), 1800)
    }
  }

  return (
    <section data-qid="dream:provider-contract-panel" style={nvis.providerContractPanel}>
      <style>{`
        [data-phase10-interactive]:focus-visible {
          outline: 2px solid #4a9eff;
          outline-offset: 2px;
        }
        details[data-provider-contract-details] > summary::-webkit-details-marker {
          display: none;
        }
        details[data-provider-contract-details] > summary::marker {
          content: "";
          font-size: 0;
        }
      `}</style>
      <p style={styles.stageSummary}>{stage.summary}</p>

      {!hasContract && (
        <div style={nvis.providerContractMissing}>
          <div>
            <strong>Phase 10 provider contract is not present in this run.</strong>
            <span>
              This surface is fail-closed. It needs a local provider contract artifact before it can display request mapping or live-readiness blockers.
            </span>
          </div>
          <pre style={nvis.providerContractCommand}>{`skills/persona-dream/run.sh write-phase10-provider-contract \\
  --video-provider-packet <run-root>/video_provider_packet/video_provider_packet.json \\
  --registry-refresh-receipt <run-root>/provider_registry_refresh_receipt.v1.json \\
  --output-root <run-root>/phase10_provider_contract \\
  --json

skills/persona-dream/run.sh check-phase10-provider-contract \\
  --fixtures-root skills/persona-dream/tests/fixtures/phase10-provider-contract \\
  --receipt-out /tmp/persona-dream-phase10-provider-contract/check_receipt.json \\
  --json`}</pre>
        </div>
      )}

      <div style={nvis.providerContractRibbon}>
        <ProviderContractRibbonMetric label="Provider" value={`${providerId} ${endpoint}`} tone={hasContract ? 'pass' : 'blocked'} />
        <ProviderContractRibbonMetric label="Request" value={`${dreamDisplayCode(String(providerRequest?.status ?? 'missing'))} / payload ${shortProviderHash(payloadHash)}`} tone={hasContract ? 'dry' : 'blocked'} />
        <ProviderContractRibbonMetric label="Boundary" value={`${providerAttempts} calls / live=${dreamBooleanLabel(providerLive)} / paid=${dreamBooleanLabel(paidCallAuthorized)} / submitted=${dreamBooleanLabel(submitted)}`} tone={providerAttempts === 0 && submitted !== true ? 'pass' : 'blocked'} />
        <ProviderContractRibbonMetric label="Gate state" value={`${dreamDisplayCode(status)} / ${dreamDisplayCode(liveSubmitStatus)}`} tone={statusTone(status) === 'pass' ? 'pass' : 'blocked'} />
      </div>

      {panelPayloadRows.length > 0 && (
        <section style={nvis.providerContractSection}>
          <h3 style={nvis.matrixSectionTitle}><Clapperboard size={12} /> Panel distillation review</h3>
          <div style={nvis.providerContractPanelPayloadList}>
            {panelPayloadRows.map((row) => (
              <div key={row.panelId} style={row.selected ? nvis.providerContractPanelPayloadSelected : nvis.providerContractPanelPayload}>
                <div style={nvis.providerContractPanelPayloadHeader}>
                  <strong>{row.panelId}</strong>
                  <span>{row.selected ? 'selected provider projection' : 'panel provider projection'}</span>
                </div>
                <div style={nvis.providerContractPanelPayloadFrames}>
                  <ProviderContractFrameState label="Start" asset={row.start} selectedField="image_url" selected={row.selected} providerUrl={providerInput?.image_url} />
                  <ProviderContractFrameState label="End" asset={row.end} selectedField="end_image_url" selected={row.selected} providerUrl={providerInput?.end_image_url} />
                </div>
                <div style={row.selected ? nvis.providerContractPanelPayloadJson : nvis.providerContractPanelPayloadJsonMuted}>
                  <div style={nvis.providerContractDistillationTextBlock}>
                    <div style={nvis.providerContractDistillationTextItem}>
                      <span style={nvis.providerContractDistillationLabel}>Exact submitted Kling prompt</span>
                      <p style={nvis.providerContractDistillationText}>
                        {String(row.submittedPrompt?.prompt ?? 'No hash-bound Phase 11 prompt found')}
                      </p>
                      <code style={nvis.providerContractDistillationAudio}>
                        duration={String(row.submittedPrompt?.duration ?? 'missing')}s / generate_audio={dreamBooleanLabel(providerInput?.generate_audio)}
                      </code>
                    </div>
                    <div style={nvis.providerContractDistillationTextItem}>
                      <span style={nvis.providerContractDistillationLabel}>Source action</span>
                      <p style={nvis.providerContractDistillationText} title={String(row.sourceEvidence?.action ?? 'missing')}>
                        {String(row.sourceEvidence?.action ?? 'missing')}
                      </p>
                    </div>
                    <div style={nvis.providerContractDistillationTextItem}>
                      <span style={nvis.providerContractDistillationLabel}>Source dialogue</span>
                      {(row.dialogue ?? []).length > 0 ? (row.dialogue ?? []).map((line, lineIndex) => (
                        <p key={`${row.panelId}-dialogue-${lineIndex}`} style={nvis.providerContractDistillationText}>
                          <strong>{String(line.speaker ?? 'Unknown')}:</strong>{' '}
                          {String(line.text ?? 'missing')}
                          {line.voice_direction ? ` (${String(line.voice_direction)})` : ''}
                        </p>
                      )) : (
                        <p style={nvis.providerContractDistillationText}>No dialogue</p>
                      )}
                    </div>
                    <div style={nvis.providerContractDistillationTextItem}>
                      <span style={nvis.providerContractDistillationLabel}>Distilled audio</span>
                      <code style={nvis.providerContractDistillationAudio} title={String(row.distillation?.audio_strategy ?? row.distillation?.voice_status ?? 'missing')}>
                        {dreamDisplayCode(String(row.distillation?.audio_strategy ?? row.distillation?.voice_status ?? 'missing'))}
                      </code>
                    </div>
                    <div style={nvis.providerContractDistillationTextItem}>
                      <span style={nvis.providerContractDistillationLabel}>Shot cinematography</span>
                      <p style={nvis.providerContractDistillationText}>
                        {[
                          `equipment: ${String(row.lookLock?.camera_format ?? 'missing')}`,
                          `lens: ${String(row.lookLock?.lens ?? 'missing')}`,
                          `framing: ${String(row.sourceShot?.framing ?? 'missing')}`,
                          `movement: ${String(row.sourceShot?.camera_movement ?? 'missing')}`,
                          `focus: ${String(row.sourceShot?.focus_target ?? 'missing')}`,
                          `lighting: ${String(row.lookLock?.lighting ?? 'missing')}`,
                          `grade: ${String(row.lookLock?.color_grade ?? 'missing')}`,
                          `atmosphere: ${String(row.lookLock?.atmosphere_texture ?? 'missing')}`,
                        ].join('\n')}
                      </p>
                    </div>
                  </div>
                  <ProviderContractAudioSummary value={row.panelSummary} />
                  <details data-provider-contract-details data-phase10-interactive style={nvis.providerContractPanelPayloadDetails}>
                    <summary data-phase10-interactive style={nvis.providerContractPanelPayloadSummary}>
                      <span>{row.selected ? 'Final provider JSON projection' : 'Panel provider JSON projection'}</span>
                      <span>{row.selected ? 'dry run / blocked' : 'not selected / blocked'}</span>
                    </summary>
                    <JsonProjectionViewer jsonPayload={row.panelRequestJson} label="Provider JSON payload" compact />
                  </details>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div style={nvis.providerContractSplit}>
        <section style={nvis.providerContractSection}>
          <h3 style={nvis.matrixSectionTitle}><Table2 size={12} /> Field mapping</h3>
          {fieldMapping.length > 0 ? (
            <div style={nvis.providerContractMapping}>
              <div style={nvis.providerContractMappingHeader}>
                <span style={nvis.providerContractMappingHeaderField}>Provider field</span>
                <span style={nvis.providerContractMappingHeaderSource}>Source</span>
                <span style={nvis.providerContractMappingHeaderStatus}>Status</span>
              </div>
              {fieldMapping.map((item, index) => {
                const mappingStatus = firstString(item.status) ?? 'MISSING'
                return (
                  <div key={`${String(item.provider_field ?? index)}-${index}`} style={nvis.providerContractMappingRow}>
                    <span style={nvis.providerContractMappingField} title={String(item.provider_field ?? '')}>{String(item.provider_field ?? 'missing')}</span>
                    <span style={nvis.providerContractMappingSource} title={String(item.source ?? item.source_artifact ?? '')}>{String(item.source ?? item.source_artifact ?? 'missing')}</span>
                    <span style={nvis.providerContractMappingStatus}>
                      <strong style={providerContractStatusTone(mappingStatus)} title={mappingStatus}>{dreamDisplayCode(mappingStatus)}</strong>
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <div style={styles.gapBox}>No field mapping was loaded. The contract gate must reject provider-submit work without mapping evidence.</div>
          )}
        </section>

        <section style={nvis.providerContractSection}>
          <h3 style={nvis.matrixSectionTitle}><ShieldAlert size={12} /> Live-readiness boundary</h3>
          <div style={nvis.providerContractBoundaryGrid}>
            <ProviderContractState label="Media URLs" value={mediaPlan?.status} detail={`${dreamNumber(mediaPlan?.asset_count) ?? 0} assets / published=${dreamBooleanLabel(mediaPlan?.provider_accessible_url_created)}`} />
            <ProviderContractState label="Cost" value={costContract?.status} detail={`paid=${dreamBooleanLabel(costContract?.paid_call_authorized)}`} />
            <ProviderContractState label="Entitlement" value={entitlementContract?.status} detail={`fal key observed=${dreamBooleanLabel(entitlementContract?.fal_api_key_observed)}`} />
            <ProviderContractState label="Return" value={asyncContract?.status} detail={`mode=${firstString(asyncContract?.selected_async_mode) ?? 'missing'}`} />
            <ProviderContractState label="Manual" value={manualAcceptance?.status} detail={`accepted=${dreamBooleanLabel(manualAcceptance?.accepted)}`} />
          </div>
        </section>
      </div>

      <div style={nvis.providerContractValidationGrid}>
        <section style={{ ...nvis.providerContractSection, ...nvis.providerContractBlockersPanel }}>
          <h3 style={nvis.matrixSectionTitle}><AlertTriangle size={12} /> Blockers</h3>
          <div style={nvis.providerContractBlockerGrid}>
            {(dryRunBlockers.length > 0 ? dryRunBlockers : ['NO_PHASE10_DRY_RUN_BLOCKERS_REPORTED']).map((blocker) => (
              <span key={blocker} style={dryRunBlockers.length > 0 ? nvis.providerContractBlockerPill : nvis.providerContractNeutralPill} title={blocker}>{formatProviderContractBlocker(blocker)}</span>
            ))}
            {liveBlockers.map((blocker) => (
              <span key={blocker} style={nvis.providerContractLiveBlockerPill} title={blocker}>{formatProviderContractBlocker(blocker)}</span>
            ))}
          </div>
        </section>

        <section style={{ ...nvis.providerContractSection, ...nvis.providerContractNonClaimsPanel }}>
          <h3 style={nvis.matrixSectionTitle}><Info size={12} /> Non-claims</h3>
          {nonClaims.length > 0 ? (
            <ul style={nvis.providerContractNonClaims}>
              {nonClaims.slice(0, 12).map((claim) => (
                <li key={claim} style={nvis.providerContractNonClaimItem}>
                  <Info size={13} style={nvis.providerContractNonClaimIcon} />
                  <span>{claim}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div style={styles.gapBox}>Non-claims were not found. Phase 10 must not imply live provider readiness without explicit non-claims.</div>
          )}
        </section>
      </div>

      <details data-provider-contract-details data-phase10-interactive style={nvis.providerContractDetails}>
        <summary data-phase10-interactive style={nvis.providerContractSummary}>
          <span>View provider request body</span>
          <span style={nvis.providerContractSummaryMeta}>{shortProviderHash(payloadHash)}</span>
        </summary>
        <div style={nvis.providerContractJsonToolbar}>
          <span>JSON request payload</span>
          <button
            type="button"
            data-phase10-interactive
            data-qid="dream:provider-distillation:copy-payload"
            data-qs-action="DREAM_PROVIDER_DISTILLATION_COPY_PAYLOAD"
            onClick={() => { void copyRequestBody() }}
            style={nvis.providerContractCopyButton}
            title="Copy provider request JSON payload"
          >
            {copyStatus === 'Copied' ? <ClipboardCheck size={13} /> : <Copy size={13} />}
            {copyStatus || 'Copy payload'}
          </button>
        </div>
        <JsonProjectionViewer jsonPayload={requestBodyJson} label="JSON request payload" />
      </details>

      <div style={nvis.videoProviderReceiptRow}>
        {['contract', 'payload_by_panel', 'field_mapping', 'omitted_context', 'publication_receipt', 'probe_receipt', 'schema_receipt', 'review_receipt', 'contract_receipt'].map((role) => {
          const item = byRole.get(role)
          const label = role.replace(/_/g, ' ')
          return <SystemStatusIndicator key={role} label={label} status={item?.payload ? 'loaded' : item?.error ? 'error' : 'missing'} />
        })}
      </div>
    </section>
  )
}
