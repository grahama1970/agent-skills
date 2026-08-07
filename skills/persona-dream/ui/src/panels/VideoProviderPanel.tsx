/**
 * VideoProviderPanel, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { CANONICAL_PHASES, DREAM_SCRIPT_DRAFT_STORAGE_KEY, DREAM_SCRIPT_STATUS_STORAGE_KEY, DREAM_STORY_DRAFT_STORAGE_KEY, DREAM_STORY_STATUS_STORAGE_KEY, crewGateMatchTerms, crewMissingEvidenceFields, phase02RequiredMediaKeys, phase02RequiredTextKeys, phaseIcons, splitStoryObjects, storyRowCategory, storyboardReviewerChecklist, textEncoder, videoProviderFitColumns } from '../constants'
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { formatProviderContractBlocker, highlightJsonForProviderContract, highlightJsonLineForProviderContract, parseProviderContractAudioSummary, providerContractArtifactRole, providerContractAudioValueTone, providerContractJsonTokenStyle, providerContractStatusTone, providerFitDelta, providerFitMax, providerFitValue, rebindProviderContractAssetPath, shortProviderHash, videoProviderArtifactRole } from '../lib/provider'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { firstString, payloadArray, payloadObject } from '../lib/text'
import { nvis } from '../styles'
import { Gauge, ShieldCheck } from 'lucide-react'

export function VideoProviderPanel({ stage }: { stage: DreamStage }) {
  const providerArtifacts = useMemo(() => {
    const byRole = new Map<string, DreamArtifact>()
    for (const artifact of stage.artifacts) {
      const role = videoProviderArtifactRole(artifact)
      if (role && !byRole.has(role)) byRole.set(role, artifact)
    }
    return [...byRole.entries()].map(([role, artifact]) => ({ role, artifact }))
  }, [stage.artifacts])
  const [loaded, setLoaded] = useState<LoadedVideoArtifact[]>([])

  useEffect(() => {
    let cancelled = false
    async function loadArtifacts() {
      const next: LoadedVideoArtifact[] = []
      for (const item of providerArtifacts) {
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
  }, [providerArtifacts])

  const byRole = useMemo(() => new Map(loaded.map((item) => [item.role, item])), [loaded])
  const selection = byRole.get('selection')?.payload ?? null
  const scenePacket = byRole.get('scene_packet')?.payload ?? null
  const payloadMapping = byRole.get('payload_mapping')?.payload ?? null
  const finalGate = byRole.get('final_gate')?.payload ?? null
  const registry = byRole.get('registry_preflight')?.payload ?? null

  const providers = payloadArray(selection?.providers ?? selection?.scorecard ?? registry?.providers)
  const recommendedProvider = firstString(
    selection?.recommended_provider_id,
    selection?.selected_provider_id,
    selection?.provider_id,
    scenePacket?.provider,
    scenePacket?.provider_id,
  ) ?? 'NO_PROVIDER_SELECTED'
  const selectionStatus = firstString(
    selection?.selection_status,
    selection?.status,
    finalGate?.status,
  ) ?? (selection ? 'SELECTION_RECEIPT_PRESENT' : 'MISSING_PROVIDER_SELECTION')
  const sceneStatus = firstString(scenePacket?.status, scenePacket?.live_submit_status) ?? 'MISSING_DRY_RUN_PACKET'
  const liveSubmitStatus = firstString(scenePacket?.live_submit_status, finalGate?.live_submit_status) ?? 'DRY_RUN_NOT_LIVE_SUBMITTABLE'
  const blockers = [
    ...dreamList(selection?.blockers),
    ...dreamList(finalGate?.blockers),
    ...dreamList(finalGate?.live_call_blockers),
    ...dreamList(scenePacket?.live_call_blockers),
  ]
  const imageList = Array.isArray(scenePacket?.image_list) ? scenePacket?.image_list : []
  const elementList = Array.isArray(scenePacket?.element_list) ? scenePacket?.element_list : []
  const multiPrompt = Array.isArray(scenePacket?.multi_prompt) ? scenePacket?.multi_prompt : []
  const providerFacingImageCount = dreamNumber(selection?.provider_facing_image_count)
    ?? dreamNumber(scenePacket?.provider_facing_image_count)
    ?? imageList.length
  const elementCount = dreamNumber(selection?.element_count)
    ?? dreamNumber(scenePacket?.element_count)
    ?? elementList.length
  const multiPromptCount = dreamNumber(selection?.multi_prompt_count)
    ?? dreamNumber(scenePacket?.multi_prompt_count)
    ?? multiPrompt.length
  const paidCallAuthorized = scenePacket?.paid_call_authorized ?? selection?.paid_call_authorized ?? finalGate?.paid_call_authorized
  const submitted = scenePacket?.submitted ?? payloadMapping?.submitted ?? selection?.submitted ?? finalGate?.submitted

  return (
    <section data-qid="dream:video-provider-panel" style={nvis.videoProviderPanel}>
      <p style={styles.stageSummary}>{stage.summary}</p>
      <div style={nvis.videoProviderGrid}>
        <div style={nvis.videoProviderCard}>
          <span style={nvis.videoProviderLabel}>Recommended provider</span>
          <strong style={nvis.videoProviderValue}>{dreamDisplayCode(recommendedProvider)}</strong>
          <span style={{ ...nvis.matrixReadyPill, alignSelf: 'flex-start' }}>{dreamDisplayCode(selectionStatus)}</span>
        </div>
        <div style={nvis.videoProviderCard}>
          <span style={nvis.videoProviderLabel}>Dry-run packet</span>
          <strong style={nvis.videoProviderValue}>{dreamDisplayCode(sceneStatus)}</strong>
          <span style={nvis.videoProviderSubtle}>{dreamDisplayCode(liveSubmitStatus)}</span>
        </div>
        <div style={nvis.videoProviderCard}>
          <span style={nvis.videoProviderLabel}>Provider-facing inputs</span>
          <strong style={nvis.videoProviderValue}>{providerFacingImageCount}/{elementCount}/{multiPromptCount}</strong>
          <span style={nvis.videoProviderSubtle}>images / elements / timed prompts</span>
        </div>
        <div style={nvis.videoProviderCard}>
          <span style={nvis.videoProviderLabel}>Live call state</span>
          <strong style={nvis.videoProviderValue}>submitted={dreamBooleanLabel(submitted)}</strong>
          <span style={nvis.videoProviderSubtle}>paid_call_authorized={dreamBooleanLabel(paidCallAuthorized)}</span>
        </div>
      </div>

      <div style={nvis.videoProviderSplit}>
        <div style={nvis.videoProviderSection}>
          <h3 style={nvis.matrixSectionTitle}><Gauge size={12} /> Provider scorecard</h3>
          {providers.length > 0 ? (
            <div style={nvis.videoProviderScoreMatrix}>
              <div style={nvis.videoProviderScoreHeader}>
                <span>Provider</span>
                <span>State</span>
                {videoProviderFitColumns.map((column) => (
                  <span key={column.key} title={column.title} style={nvis.videoProviderFeatureHeader}>{column.label}</span>
                ))}
                <span style={nvis.videoProviderScoreHeaderCell}>Score</span>
              </div>
              {providers.slice(0, 6).map((provider, index) => {
                const providerId = firstString(provider.provider_id, provider.id, provider.name) ?? `provider_${index + 1}`
                const score = dreamNumber(provider.score)
                const providerBlockers = dreamList(provider.blockers)
                const isRecommended = providerId === recommendedProvider
                return (
                  <div key={providerId} style={{
                    ...nvis.videoProviderScoreMatrixRow,
                    ...(isRecommended ? nvis.videoProviderScoreMatrixRowSelected : null),
                  }}>
                    <div style={isRecommended ? nvis.videoProviderRecommendedName : undefined}>
                      <strong>{providerId}</strong>
                    </div>
                    <div>
                      <div style={nvis.videoProviderSubtle}>
                        dry={dreamBooleanLabel(provider.eligible_for_dry_run)} live={dreamBooleanLabel(provider.eligible_for_live_submit)}
                      </div>
                      {providerBlockers.length > 0 && <div style={nvis.videoProviderTinyMuted}>{providerBlockers.length} blk</div>}
                    </div>
                    {videoProviderFitColumns.map((column) => {
                      const delta = providerFitDelta(provider, providers, column.key)
                      return (
                        <div key={column.key} title={`${column.title}: ${providerFitValue(provider, column.key) ?? 'missing'}`} style={delta != null && delta < 0 ? nvis.videoProviderPenaltyCell : nvis.videoProviderNeutralCell}>
                          {delta == null ? 'n/a' : delta < 0 ? delta : '-'}
                        </div>
                      )
                    })}
                    <div style={nvis.videoProviderScoreFinalCell}>
                      <span style={score != null && score >= 90 ? nvis.matrixReadyPill : nvis.matrixPendingPill}>
                        {score ?? 'n/a'}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div style={styles.gapBox}>No provider scorecard receipt was found for this run.</div>
          )}
        </div>

        <div style={nvis.videoProviderSection}>
          <h3 style={nvis.matrixSectionTitle}><ShieldCheck size={12} /> Blockers and non-live boundary</h3>
          {blockers.length > 0 ? (
            <ul style={nvis.videoProviderBlockerList}>
              {[...new Set(blockers)].slice(0, 8).map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          ) : (
            <div style={styles.gapBox}>No live-call blockers were surfaced by the loaded receipts. Treat as not provider-ready until final gate evidence exists.</div>
          )}
        </div>
      </div>

      <div style={nvis.videoProviderReceiptRow}>
        {['selection', 'scene_packet', 'payload_mapping', 'final_gate', 'registry_preflight'].map((role) => {
          const item = byRole.get(role)
          const label = role.replace(/_/g, ' ')
          return (
            <div key={role} style={item?.payload ? nvis.videoProviderReceiptReady : nvis.videoProviderReceiptMissing}>
              <span>{label}</span>
              <strong>{item?.payload ? 'loaded' : item?.error ? 'error' : 'missing'}</strong>
            </div>
          )
        })}
      </div>
    </section>
  )
}
