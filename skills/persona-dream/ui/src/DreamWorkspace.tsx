// @ts-nocheck
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import * as d3 from 'd3'
import {
  AlertTriangle,
  Aperture,
  BookOpen,
  Boxes,
  Camera,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  CheckCircle2,
  Copy,
  ClipboardCheck,
  Code2,
  FileJson,
  Film,
  FileText,
  Filter,
  Gauge,
  GitBranch,
  Grid,
  Image,
  Images,
  Info,
  Layout,
  Lightbulb,
  Lock,
  MapPin,
  Maximize2,
  Mic,
  Mic2,
  Move3D,
  Package,
  PencilLine,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Share2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Sun,
  Table2,
  Users,
  UserRound,
  Volume2,
  CircleDot,
  CloudSun,
  Wand2,
  X,
} from 'lucide-react'
import { useRegisterAction } from './useRegisterAction'
import { highlightWithGlossary, type GlossaryTerm } from './highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from './types'
import { CANONICAL_PHASES, DREAM_SCRIPT_DRAFT_STORAGE_KEY, DREAM_SCRIPT_STATUS_STORAGE_KEY, DREAM_STORY_DRAFT_STORAGE_KEY, DREAM_STORY_STATUS_STORAGE_KEY, crewGateMatchTerms, crewMissingEvidenceFields, phase02RequiredMediaKeys, phase02RequiredTextKeys, phaseIcons, splitStoryObjects, storyRowCategory, storyboardReviewerChecklist, textEncoder, videoProviderFitColumns } from './constants'
import { PipelineErrorBoundary, acceptedStoryboardFrame, activeDreamPhaseFromLocation, assetExtension, authorStyleGuide, buildCardTraceGraph, buildLiveMemoryTraceGraph, chooseCrewPersona, clampNumber, compactCrewText, compactDisplayText, compactStoryStatus, contactSheetDecisionForStoryRow, coverageNoteForScriptRow, crc32, createMissingStage, createStoredZip, crewFitRationale, crewRoleCriteria, crewTauRepairNote, decodeJsonStringLiteral, distinctAssetDescription, downloadBlob, dreamAssetUrl, dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamMemoryResultFromDocument, dreamMemoryResultPriority, dreamNumber, dreamPhaseHashAliases, dreamPhaseHashById, dreamRenderableMediaUrl, dreamStringField, effectiveStageStatus, endpointParts, extractKnownMemoryFieldText, extractPersonaMemoryKey, fileNameFromPath, firstString, fnv1a32, formatProviderContractBlocker, graphKindFromDocument, graphLabelFromDocument, graphMediaSourceFromDocument, graphNodeFromEndpoint, graphThumbFromDocument, groupResearchContext, hasLiveDescriptionReceipt, highlightJsonForProviderContract, highlightJsonLineForProviderContract, humanMemoryCaption, inferStoryLocationAndEnvironment, inferTraceKind, isDisplayableTraceEdge, isExecutionReceiptArtifact, isStagePassed, linkedStoryAssetFromMemoryResult, mediaLockFrameGroups, mediaLockFramesFromPacket, mediaLockGroupTimeRange, mediaLockStatusLabel, memoryConnectionPalette, memoryConnectionSignals, mergeMemoryTomGraph, nodeKindColor, normalizeToCanonicalPhases, nvis, panelHasAcceptedStoryboardFrames, parseDreamJson, parseJsonishText, parseProviderContractAudioSummary, parseStoryDraftJson, payloadArray, payloadObject, persistedHumanIdea, personaMemoryThumbCache, personaText, personaThumbnailUrl, phaseNumber, phaseShortLabels, productionTechniquePackage, providerContractArtifactRole, providerContractAudioValueTone, providerContractJsonTokenStyle, providerContractStatusTone, providerFitDelta, providerFitMax, providerFitValue, readableMemoryText, readableMemoryValue, rebindProviderContractAssetPath, relationshipColor, relaxTraceNodeOverlaps, requiredStageArtifact, roleFitCandidates, rolePrompt, sanitizeZipName, scoreCrewPersona, scriptContractFromDraft, scriptCoverageStatusForRow, scriptCoverageStatusTitle, scriptEntityRows, scriptGlossaryFromContract, scriptStringFromContract, shortProviderHash, shouldIgnoreDreamPaneArrowKey, splitScriptIntoRows, stableJson, stageArtifactSummary, stageImageSummary, stageMissingMessage, statusLabel, statusTone, storyAssetDescriptionFromMemoryDocument, storyAssetDescriptionFromResult, storyContractSummaryFromDraft, storyDisplayText, storyEntityGlossary, storyboardPanelPromptText, storyboardRecord, storyboardShotCode, storyboardStringList, storyboardTargetPanelIds, stripLeadingMemoryFieldLabels, styles, toneStyles, useElementSize, videoProviderArtifactRole, writeUint16, writeUint32 } from './lib'

function PhaseIcon({ phaseId, size = 18 }: { phaseId: string; size?: number }) {
  const Icon = phaseIcons[phaseId] ?? Wand2
  return <Icon size={size} />
}

function StatusBadge({ status }: { status: string }) {
  const tone = statusTone(status)
  const Icon = tone === 'pass' ? CheckCircle2 : tone === 'blocked' ? ShieldAlert : AlertTriangle
  const label = statusLabel(status)
  return (
    <span title={label} aria-label={`Status: ${label}`} style={{ ...styles.badge, ...toneStyles[tone] }}>
      <Icon size={12} />
      {label}
    </span>
  )
}

function GateMiniBadge({ status, label }: { status: string; label: string }) {
  const tone = statusTone(status)
  const Icon = tone === 'pass' ? CheckCircle2 : tone === 'blocked' ? ShieldAlert : AlertTriangle
  return (
    <span title={statusLabel(status)} aria-label={`${label}: ${statusLabel(status)}`} style={{ ...styles.gateMiniBadge, ...toneStyles[tone] }}>
      <Icon size={12} />
      <span>{label}</span>
    </span>
  )
}

function ArtifactField({ label, value }: { label: string; value?: string }) {
  return (
    <div>
      <dt style={styles.artifactLabel}>{label}</dt>
      <dd style={styles.artifactValue}>{value || 'missing'}</dd>
    </div>
  )
}

function StageGateAlert({ stage }: { stage: DreamStage }) {
  if (stage.id !== '03' || !stage.status.toUpperCase().includes('MISSING')) return null
  return (
    <div data-qid="dream:stage-gate-alert:03" style={nvis.stageGateAlert}>
      <span style={{ ...nvis.crewGatePill, ...nvis.crewGatePillMissing }}>
        <AlertTriangle size={12} />
        {stage.status}
      </span>
      <span style={nvis.stageGateAlertText}>
        Action required: Phase 03 crew contract JSON is not saved in this run. Use Project Agent to build the Tau contract artifact.
      </span>
    </div>
  )
}

function StageCard({
  run,
  stage,
  note,
  actionStatus,
  onNoteChange,
  onSubmitAction,
  allStages,
  processing,
  onTriggerMemories,
  memoryResults,
  researchSeed,
  ideaText,
  storyboardProjection,
  revisionQualified,
  humanIdea,
}: {
  run: DreamRun
  stage: DreamStage
  note: string
  actionStatus?: string
  onNoteChange: (value: string) => void
  onSubmitAction: (action: StageAction, noteOverride?: string) => void
  allStages?: DreamStage[]
  processing?: boolean
  onTriggerMemories?: (ideaText: string) => void
  researchSeed?: string
  ideaText?: string
  memoryResults?: ResearchMemoryResult[] | null
  storyboardProjection?: StoryboardConsumerProjection
  revisionQualified: boolean
  humanIdea?: HumanIdeaProjection
}) {
  const ideaStage = allStages?.find((s) => s.id === '01')
  const isBlockedByPrev = stage.id === '02' && ideaStage != null && !isStagePassed(ideaStage)

  return (
    <article data-qid={`dream:stage-card:${stage.id}`} style={{
      ...styles.stageCard,
      ...(stage.id === '01' ? { padding: 0, background: 'transparent', border: 'none', outline: 'none', boxShadow: 'none', backdropFilter: 'none' } : {}),
      ...(stage.id === '02' ? { maxWidth: 'none', justifySelf: 'stretch', padding: '24px 28px' } : {}),
      ...(stage.id === '08' ? { borderRadius: 0 } : {}),
      ...(isBlockedByPrev ? nvis.blockedCard : null),
    }}>
      {stage.id !== '01' && <StageCardHeader stage={stage} />}
      <StageGateAlert stage={stage} />

      <div style={{
        ...styles.stageContentWell,
        ...(stage.id === '01' ? { border: 'none', background: 'transparent', padding: 0, minHeight: 0 } : {}),
        ...(stage.id === '08' ? { borderRadius: 0 } : {}),
      }}>
        {stage.id === '01' && (
          <IdeaMemoryControl
            ideaStage={ideaStage ?? stage}
            memoryStage={allStages?.find((s) => s.id === '02') ?? null}
            onTriggerMemories={onTriggerMemories ?? (() => {})}
            processing={processing ?? false}
            memoryResults={memoryResults}
            humanIdea={humanIdea}
          />
        )}
        {stage.id === '02' && (
          <div style={nvis.storyMatrixBelowBoard}>
            <StoryMatrix
              stage={stage}
              researchSeed={researchSeed}
              ideaText={humanIdea?.text || ideaText || ''}
              linkedAssets={(memoryResults ?? [])
                .filter((result) => dreamRenderableMediaUrl(result.url))
                .map(linkedStoryAssetFromMemoryResult)}
            />
          </div>
        )}
        {stage.id === '03' && (
          <CrewConsole
            stage={stage}
            researchSeed={researchSeed}
            ideaText={humanIdea?.text || ideaText || ''}
            linkedAssets={(memoryResults ?? [])
              .filter((result) => dreamRenderableMediaUrl(result.url))
              .map(linkedStoryAssetFromMemoryResult)}
          />
        )}
        {stage.id === '04' && (
          <>
            <p style={styles.stageSummary}>{stage.summary}</p>
            <ContactSheetBoard stage={stage} />
          </>
        )}
        {stage.id === '05' && (
          <>
            <p style={styles.stageSummary}>{stage.summary}</p>
            <VoiceBoard stage={stage} />
          </>
        )}
        {stage.id === '06' && (
          <ScriptConsole
            stage={stage}
            allStages={allStages ?? []}
            researchSeed={researchSeed}
            ideaText={humanIdea?.text || ideaText || ''}
            linkedAssets={(memoryResults ?? [])
              .filter((result) => dreamRenderableMediaUrl(result.url))
              .map(linkedStoryAssetFromMemoryResult)}
          />
        )}
        {stage.id === '07' && (
          <StoryboardConsole
            stage={stage}
            projection={storyboardProjection}
            revisionQualified={revisionQualified}
          />
        )}
        {stage.id === '08' && (
          <MediaLockPanel stage={stage} projection={storyboardProjection} />
        )}
        {stage.id === '09' && (
          <VideoProviderPanel stage={stage} />
        )}
        {stage.id === '10' && (
          <PipelineErrorBoundary surface="Provider Distillation">
            <ProviderContractPanel stage={stage} />
          </PipelineErrorBoundary>
        )}
        {stage.id === '11' && <ProviderReturnPanel stage={stage} />}
        {!['01', '02', '03', '04', '05', '06', '07', '08', '09', '10'].includes(stage.id) && (
          <>
            <p style={styles.stageSummary}>{stage.summary}</p>
            {stage.failureOrGap && <div style={styles.gapBox}>{stage.failureOrGap}</div>}
            {!stage.failureOrGap && !isStagePassed(stage) && <div style={styles.gapBox}>{stageMissingMessage(stage)}</div>}
          </>
        )}
        {stage.id !== '08' && <StageEvidence stage={stage.id === '07' ? { ...stage, images: [] } : stage} />}
      </div>

    </article>
  )
}

function StageCardHeader({ stage }: { stage: DreamStage }) {
  const headerStatus = effectiveStageStatus(stage)
  const headerPassed = statusTone(headerStatus) === 'pass'

  return (
    <div style={styles.stageHeaderStack}>
      <div style={styles.stageCardHeader}>
        <div style={styles.stageIdentity}>
          <span style={{ ...styles.stageIcon, ...(stage.id === '08' ? { borderRadius: 0 } : null) }}>
            <PhaseIcon phaseId={stage.id} />
          </span>
          <div style={styles.phaseHeaderText}>
            <div style={styles.stageId}>{stage.id.replace(/_/g, ' ')}</div>
            <h2 style={styles.stageTitle}>{phaseShortLabels[stage.id] ?? stage.title}</h2>
            <div style={{ ...styles.stageTitleRule, ...(stage.id === '08' ? { borderRadius: 0 } : null) }} />
          </div>
        </div>
        <div style={styles.stageHeaderActions}>
          {stage.id === '02' && (
            <button
              type="button"
              data-qid="dream:story:header-copy-payload"
              title="Copy full Phase 02 story prompt payload"
              aria-label="Copy full Phase 02 story prompt payload"
              onClick={() => window.dispatchEvent(new Event('dream:copy-story-payload'))}
              style={styles.stageHeaderCopyBtn}
            >
              <Copy size={14} />
              <span style={styles.stageHeaderCopyLabel}>Prompt Payload</span>
            </button>
          )}
          {stage.id === '03' && (
            <button
              type="button"
              data-qid="dream:crew:header-copy-payload"
              title="Copy full Phase 03 crew prompt payload"
              aria-label="Copy full Phase 03 crew prompt payload"
              onClick={() => window.dispatchEvent(new Event('dream:copy-crew-payload'))}
              style={styles.stageHeaderCopyBtn}
            >
              <Copy size={14} />
              <span style={styles.stageHeaderCopyLabel}>Crew Payload</span>
            </button>
          )}
          <StatusBadge status={headerStatus} />
        </div>
      </div>
      {!headerPassed && stage.id !== '11' && (
        <div style={styles.stageStatusHelp}>
          {stage.id === '07' && /MISSING|BLOCKED|FAIL/i.test(headerStatus)
            ? 'Storyboard reviewer rejected the current panels. The accepted frames must use the required storyboard aspect ratio and prove Embry/Kai visual identity against the reference/contact sheets before this phase can pass.'
            : stageMissingMessage(stage)}
        </div>
      )}
    </div>
  )
}

function ProviderReturnPanel({ stage }: { stage: DreamStage }) {
  const video = stage.artifacts.find(
    (artifact) => artifact.kind === 'media' && /\.mp4$/i.test(artifact.path)
  )
  const superseded = /SUPERSEDED/i.test(stage.status)
  if (!video) return null
  return (
    <section data-qid="dream:provider-return-panel" style={{ display: 'grid', gap: 10, marginBottom: 12 }}>
      {superseded && (
        <div style={{ ...styles.gapBox, borderColor: 'rgba(250,204,21,0.45)', color: '#facc15' }}>
          Historical return. Active repaired request pending.
        </div>
      )}
      <video
        data-qid="dream:provider-return-video"
        src={video.url ?? `/api/projects/dream/asset?path=${encodeURIComponent(video.path)}`}
        controls
        preload="metadata"
        playsInline
        style={{ width: '100%', maxHeight: 480, borderRadius: 12, background: '#000', border: '1px solid rgba(148,163,184,0.25)' }}
      />
      <p style={{ margin: 0, fontSize: 12, color: 'rgba(148,163,184,0.9)' }}>{video.label}</p>
    </section>
  )
}

function StageEvidence({ stage }: { stage: DreamStage }) {
  const executionReceipts = stage.artifacts.filter(isExecutionReceiptArtifact)
  const visibleArtifacts = stage.artifacts.filter((artifact) => !isExecutionReceiptArtifact(artifact))

  return (
    <>
      {stage.images.length > 0 && (
        <div style={styles.imageGrid}>
          {stage.images.map((image) => (
            <figure key={image.path} style={styles.imageFigure}>
              <img src={image.url} alt={image.label} style={styles.stageImage} />
              <figcaption style={styles.imageCaption}>{image.label}</figcaption>
            </figure>
          ))}
        </div>
      )}

      {visibleArtifacts.length > 0 && (
        <div style={styles.artifactChips}>
          {visibleArtifacts.map((artifact) => (
            <ArtifactChip key={artifact.path} artifact={artifact} />
          ))}
        </div>
      )}

      {executionReceipts.length > 0 && (
        <details data-qid={`dream:${stage.id}:execution-receipts`} style={styles.receiptAccordion}>
          <summary style={styles.receiptAccordionSummary}>
            <span>View Execution Receipts ({executionReceipts.length})</span>
          </summary>
          <div style={styles.receiptGrid}>
            {executionReceipts.map((artifact) => (
              <ArtifactChip
                key={artifact.path}
                artifact={artifact}
                style={styles.receiptPill}
                iconSize={12}
                label={fileNameFromPath(artifact.label || artifact.path)}
                title={artifact.path}
              />
            ))}
          </div>
        </details>
      )}
    </>
  )
}

function ArtifactChip({
  artifact,
  style = styles.artifactChip,
  iconSize = 13,
  label,
  title,
}: {
  artifact: DreamStage['artifacts'][number]
  style?: CSSProperties
  iconSize?: number
  label?: string
  title?: string
}) {
  const displayLabel = label ?? artifact.label
  return (
    <a
      href={`/api/projects/dream/asset?path=${encodeURIComponent(artifact.path)}`}
      target="_blank"
      rel="noreferrer"
      title={title ?? artifact.label}
      style={style}
    >
      <FileJson size={iconSize} />
      <span style={styles.receiptPillLabel}>{displayLabel}</span>
    </a>
  )
}

function MediaLockPanel({ stage, projection }: { stage: DreamStage; projection?: StoryboardConsumerProjection }) {
  const packetUrl = projection?.packetUrl
  const [frames, setFrames] = useState<MediaLockFrame[]>([])
  const [packetStatus, setPacketStatus] = useState('loading accepted storyboard packet...')
  const frameGroups = mediaLockFrameGroups(frames)

  useEffect(() => {
    let cancelled = false
    async function loadPacket() {
      try {
        if (!packetUrl) throw new Error('storyboard packet missing from the active revision read model')
        const response = await fetch(packetUrl)
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const packet = await response.json()
        const nextFrames = mediaLockFramesFromPacket(packet, projection)
        if (cancelled) return
        setFrames(nextFrames)
        setPacketStatus(nextFrames.length > 0
          ? `PASS_MEDIA_LOCK_SOURCE: ${nextFrames.length} accepted frames loaded from storyboard_packet.json`
          : 'BLOCKED_MEDIA_LOCK: storyboard_packet.json did not expose accepted frames')
      } catch (error) {
        if (cancelled) return
        setFrames([])
        setPacketStatus(`BLOCKED_MEDIA_LOCK_PACKET_LOAD: ${error instanceof Error ? error.message : String(error)}`)
      }
    }
    void loadPacket()
    return () => { cancelled = true }
  }, [packetUrl, projection?.revisionId])

  return (
    <section data-qid="dream:media-lock-panel" style={styles.mediaLockPanel}>
      <p style={styles.stageSummary}>{stage.summary}</p>
      {stage.failureOrGap && !isStagePassed(stage) && <div style={styles.gapBox}>{stage.failureOrGap}</div>}
      <div style={styles.mediaLockStatusBar}>
        <span>Accepted frame lock</span>
        <strong>{packetStatus}</strong>
      </div>
      {frames.length > 0 ? (
        <div style={styles.mediaLockGrid}>
          {frameGroups.map((group) => (
            <section key={group.panelId} style={styles.mediaLockFrameGroup}>
              <div style={styles.mediaLockGroupHeader}>
                <div style={styles.mediaLockGroupTitle}>
                  <strong>{group.panelId}</strong>
                  <span>{mediaLockGroupTimeRange(group.frames)} | {group.frames.length} locked frames</span>
                </div>
                <span style={styles.mediaLockLockedBadge}>LOCKED</span>
              </div>
              <div style={styles.mediaLockGroupFrames}>
                {group.frames.map((frame) => (
                  <article key={frame.id} style={styles.mediaLockFrame}>
                    <img src={frame.url} alt={`${frame.panelId} ${frame.role}`} style={styles.mediaLockThumb} />
                    <div style={styles.mediaLockFrameBody}>
                      <div style={styles.mediaLockFrameTitle}>
                        <strong>{frame.role.replace(/_/g, ' ')}</strong>
                      </div>
                      <div style={styles.mediaLockFacts}>
                        <MediaLockFact label="Status" value={mediaLockStatusLabel(frame.status)} title={frame.status} tone="pass" />
                        <MediaLockFact label="Identity" value={frame.identityStatus} tone="pass" />
                        <MediaLockFact label="Time" value={frame.timeLabel} />
                        <MediaLockFact label="SHA" value={frame.sha256} title={frame.sha256} hash />
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div style={styles.gapBox}>Accepted storyboard frames are not available to the media-lock view yet.</div>
      )}
      <StageEvidence stage={{ ...stage, images: [] }} />
    </section>
  )
}

function MediaLockFact({
  label,
  value,
  title,
  tone,
  hash = false,
}: {
  label: string
  value: string
  title?: string
  tone?: 'pass'
  hash?: boolean
}) {
  return (
    <div style={styles.mediaLockFactRow}>
      <span style={styles.mediaLockFactLabel}>{label}</span>
      <strong
        title={title ?? value}
        style={hash ? styles.mediaLockHashValue : {
          ...styles.mediaLockFactValue,
          ...(tone === 'pass' ? styles.mediaLockPassValue : null),
        }}
      >
        {value}
      </strong>
    </div>
  )
}

function VideoProviderPanel({ stage }: { stage: DreamStage }) {
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

function ProviderContractPanel({ stage }: { stage: DreamStage }) {
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
  const panelPayloadRows = useMemo(() => {
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
                      {row.dialogue.length > 0 ? row.dialogue.map((line, lineIndex) => (
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

function ProviderContractRibbonMetric({
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

function JsonProjectionViewer({
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

function ProviderContractAudioSummary({ value }: { value: string }) {
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

function ProviderContractState({
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

function ProviderContractFrameState({
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

function ProviderContractMetadataRow({
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

function SystemStatusIndicator({ label, status }: { label: string; status: string }) {
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


function StoryboardConsole({
  stage,
  projection,
  revisionQualified,
}: {
  stage: DreamStage
  projection?: StoryboardConsumerProjection
  revisionQualified: boolean
}) {
  const [packet, setPacket] = useState<Record<string, unknown> | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const packetUrl = projection?.packetUrl

  useEffect(() => {
    let cancelled = false
    async function loadPacket() {
      try {
        setLoadError(null)
        if (!packetUrl) throw new Error('storyboard consumer projection missing from the active revision read model')
        const packetResponse = await fetch(packetUrl)
        if (!packetResponse.ok) throw new Error(`storyboard packet HTTP ${packetResponse.status}`)
        const payload = await packetResponse.json()
        if (!cancelled) {
          setPacket(payload)
        }
      } catch (error) {
        if (!cancelled) {
          setPacket(null)
          setLoadError(error instanceof Error ? error.message : String(error))
        }
      }
    }
    void loadPacket()
    return () => { cancelled = true }
  }, [packetUrl])

  const panels = Array.isArray(packet?.panels) ? packet.panels as Array<Record<string, unknown>> : []
  const targetPanelIds = storyboardTargetPanelIds(packet)
  const reviewPanels = targetPanelIds.length > 0
    ? panels.filter((panel) => targetPanelIds.includes(String(panel.panel_id ?? panel.id ?? '')))
    : panels
  const blockers = Array.isArray(packet?.missing_reference_blockers) ? packet.missing_reference_blockers as Array<Record<string, unknown>> : []
  const reviewBlockers = Array.isArray(packet?.review_blockers)
      ? packet.review_blockers.map(String).filter(Boolean)
      : []
  const candidates = Array.isArray(packet?.generated_candidate_panels) ? packet.generated_candidate_panels as Array<Record<string, unknown>> : []
  const panelsHaveAcceptedFrames = reviewPanels.length > 0 && reviewPanels.every(panelHasAcceptedStoryboardFrames)
  const reviewAccepted = Boolean(packet?.accepted) && String(packet?.review_status ?? packet?.status ?? '').includes('PASS')
  const packetStatus = String(packet?.review_status ?? packet?.status ?? (loadError ? 'MISSING_STORYBOARD_PACKET' : 'LOADING_STORYBOARD_PACKET'))
  const status = revisionQualified ? packetStatus : 'BLOCKED_REVISION_NOT_QUALIFIED'
  const isBlocked = !revisionQualified || /BLOCKED|MISSING|REJECTED|ERROR/i.test(status) || !panelsHaveAcceptedFrames || !reviewAccepted
  const targetLabel = targetPanelIds.length > 0 ? targetPanelIds.join(', ') : null
  const panelCountLabel = targetPanelIds.length > 0
    ? `${reviewPanels.length}/${panels.length || reviewPanels.length} target`
    : String(panels.length || '0')

  return (
    <section data-qid="dream:storyboard:console" style={nvis.storyboardConsole}>
      <style>{`
        details[data-storyboard-accordion] > summary::-webkit-details-marker {
          display: none;
        }
        details[data-storyboard-accordion] > summary::marker {
          content: "";
          font-size: 0;
        }
        summary[data-storyboard-accordion-header]:hover {
          background: rgba(255, 255, 255, 0.08) !important;
          color: #e5e7eb !important;
        }
        details[data-storyboard-accordion][open] [data-storyboard-accordion-chevron] {
          transform: rotate(180deg);
        }
      `}</style>
      <div style={nvis.storyboardHeader}>
        <div>
          <div style={nvis.storyboardEyebrow}>Animatic Storyboard</div>
          <h3 style={nvis.storyboardTitle}>
            {targetLabel ? `Targeted proof for ${targetLabel}` : 'Four timed panels for a 10-second video scene'}
          </h3>
        </div>
        <div style={nvis.storyboardMetaRow}>
          <span style={isBlocked ? nvis.storyboardStatusBlocked : nvis.storyboardStatusPass}>
            {isBlocked ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
            {status.replace(/_/g, ' ')}
          </span>
          <span style={nvis.storyboardMetaPill}>{panelCountLabel} panels</span>
          <span style={nvis.storyboardMetaPill}>{String(packet?.duration_seconds ?? '10')}s</span>
        </div>
      </div>

      {(loadError || isBlocked) && (
        <div style={nvis.storyboardBlockerBox}>
          <strong>Storyboard gate is not satisfied.</strong>
          <span>
            {loadError
              ? `Storyboard packet could not be loaded: ${loadError}.`
              : !revisionQualified
                ? 'The active revision is available for read-only inspection but has not passed revision qualification.'
              : reviewBlockers.length
                ? `Panel reviewer rejected this storyboard: ${reviewBlockers[0]}`
              : targetLabel
                ? `Targeted panel proof for ${targetLabel} requires reviewer-accepted start and end frames before it can pass.`
                : 'A single generated image is not a storyboard. Phase 07 requires multiple timed panels with text, references, coverage seed IDs, and reviewer acceptance.'}
          </span>
        </div>
      )}

      {reviewBlockers.length > 0 && (
        <div style={nvis.storyboardBlockerList}>
          <div style={nvis.storyboardBlockerTitle}>Panel reviewer blockers</div>
          {reviewBlockers.slice(0, 8).map((blocker, index) => (
            <div key={`${blocker}-${index}`} style={nvis.storyboardBlockerItem}>
              <div style={nvis.storyboardBlockerErrorText}>{blocker}</div>
              <div style={nvis.storyboardBlockerVerdict}>
                <span style={nvis.storyboardBlockerVerdictLabel}>Reviewer verdict</span>
                <span style={nvis.storyboardBlockerVerdictStatus}>{status}</span>
              </div>
            </div>
          ))}
          {reviewBlockers.length > 8 && (
            <div style={nvis.storyboardBlockerMore}>
              +{reviewBlockers.length - 8} additional reviewer blocker{reviewBlockers.length - 8 === 1 ? '' : 's'} in storyboard_review_verdict.json
            </div>
          )}
        </div>
      )}

      {blockers.length > 0 && (
        <div style={nvis.storyboardBlockerList}>
          <div style={nvis.storyboardBlockerTitle}>Reference blockers before image generation</div>
          {blockers.map((blocker, index) => (
            <div key={`${String(blocker.entity)}-${index}`} style={nvis.storyboardBlockerItem}>
              <span>{String(blocker.entity ?? 'Unknown entity')}</span>
              <small>{String(blocker.reason ?? 'Reference is missing')}</small>
            </div>
          ))}
        </div>
      )}

      {panels.length > 0 && (
        <div style={nvis.storyboardPanelGrid}>
          {panels.map((panel) => (
            <StoryboardPanel
              key={String(panel.panel_id ?? panel.shot)}
              panel={panel}
              projection={projection?.panels.find((candidate) => candidate.panelId === String(panel.panel_id ?? ''))}
            />
          ))}
        </div>
      )}

      {candidates.length > 0 && (
        <div style={nvis.storyboardCandidateStrip}>
          <div style={nvis.storyboardBlockerTitle}>Rejected generated candidate</div>
          {candidates.map((candidate) => {
            return (
              <div key={String(candidate.panel_id ?? candidate.path)} style={nvis.storyboardCandidateRow}>
                <div style={nvis.storyboardReferenceFallback}><Image size={16} /></div>
                <div>
                  <div style={nvis.storyboardCandidateStatus}>{String(candidate.status ?? 'REJECTED')}</div>
                  <div style={nvis.storyboardCandidateReason}>{String(candidate.reason ?? '')}</div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

function StoryboardPanel({
  panel,
  projection,
}: {
  panel: Record<string, unknown>
  projection?: StoryboardPanelProjection
}) {
  const [copyStatus, setCopyStatus] = useState('')
  const range = panel.time_range && typeof panel.time_range === 'object' ? panel.time_range as Record<string, unknown> : {}
  const references = Array.isArray(panel.references) ? panel.references as Array<Record<string, unknown>> : []
  const seeds = Array.isArray(panel.coverage_seed_ids) ? panel.coverage_seed_ids.map(String) : []
  const entities = Array.isArray(panel.required_entities) ? panel.required_entities.map(String) : []
  const startFrame = storyboardRecord(panel.start_frame)
  const endFrame = storyboardRecord(panel.end_frame)
  const cameraPlan = storyboardRecord(panel.camera)
  const lightingPlan = storyboardRecord(panel.lighting)
  const productionNotes = storyboardRecord(panel.production_notes)
  const generationPrompt = storyboardRecord(panel.generation_prompt)
  const actingBeats = storyboardStringList(panel.acting_beats)
  const primaryFrame = acceptedStoryboardFrame(startFrame) || acceptedStoryboardFrame(endFrame)
  const primaryReferenceUrl = projection?.startFrame.url ?? projection?.endFrame.url ?? ''
  const timeLabel = `${String(range.start_s ?? '?')}-${String(range.end_s ?? '?')}`
  const shotText = String(panel.shot ?? 'Missing shot direction')
  const shotCode = storyboardShotCode(shotText)
  const copyPanelPayload = async () => {
    setCopyStatus('Building')
    const payload = {
      schema: 'persona_dream.storyboard_panel_prompt_payload.v1',
      panel_id: panel.panel_id ?? null,
      time_range: range,
      shot: panel.shot ?? null,
      action: panel.action ?? null,
      dialogue: panel.dialogue ?? null,
      required_entities: entities,
      coverage_seed_ids: seeds,
      references,
      start_frame: startFrame,
      end_frame: endFrame,
      camera: cameraPlan,
      lighting: lightingPlan,
      acting_beats: actingBeats,
      production_notes: productionNotes,
      generation_prompt: generationPrompt,
      accepted_frame: primaryFrame || null,
    }
    const panelId = sanitizeZipName(String(panel.panel_id ?? 'storyboard-panel'))
    const jsonPayload = JSON.stringify(payload, null, 2)
    const textPayload = storyboardPanelPromptText(payload)
    const checklistPayload = JSON.stringify(storyboardReviewerChecklist, null, 2)
    const manifestPayload = JSON.stringify({
      schema: 'persona_dream.storyboard_panel_clipboard_bundle.v1',
      panel_id: panel.panel_id ?? null,
      created_at: new Date().toISOString(),
      includes: [
        'panel_prompt_payload.json',
        'panel_prompt_payload.txt',
        'panel_reviewer_checklist.json',
        'accepted_frame/* when available',
        'references/* when available',
      ],
    }, null, 2)
    const filename = `${panelId}-prompt-payload.zip`
    const serverEntries: Array<Record<string, string>> = [
      { name: 'panel_prompt_payload.json', text: jsonPayload },
      { name: 'panel_prompt_payload.txt', text: textPayload },
      { name: 'panel_reviewer_checklist.json', text: checklistPayload },
      { name: 'manifest.json', text: manifestPayload },
    ]
    if (primaryFrame) {
      const raw = String(primaryFrame.path || primaryFrame.image_path || '')
      const extension = assetExtension(raw)
      serverEntries.push({ name: `accepted_frame/${panelId}-accepted-frame.${extension}`, path: raw })
    }
    references.forEach((reference, index) => {
      const raw = String(reference.path || reference.url || '')
      if (!raw || raw.startsWith('http')) return
      const label = sanitizeZipName(String(reference.id ?? reference.title ?? `reference-${index + 1}`))
      const extension = assetExtension(raw)
      serverEntries.push({ name: `references/${String(index + 1).padStart(2, '0')}-${label}.${extension}`, path: raw })
    })

    try {
      const serverCopied = await copyPanelBundleToDesktopClipboard(filename, serverEntries)
      if (serverCopied) {
        setCopyStatus('Copied zip')
        window.setTimeout(() => setCopyStatus(''), 1600)
        return
      }
    } catch {
      // Fall through to browser-only zip/download fallback when the local API is unavailable.
    }

    const entries: ZipFileEntry[] = [
      {
        name: 'panel_prompt_payload.json',
        data: textEncoder.encode(jsonPayload),
      },
      {
        name: 'panel_prompt_payload.txt',
        data: textEncoder.encode(textPayload),
      },
      {
        name: 'panel_reviewer_checklist.json',
        data: textEncoder.encode(checklistPayload),
      },
      {
        name: 'manifest.json',
        data: textEncoder.encode(manifestPayload),
      },
    ]

    const imageEntries = await Promise.all([
      primaryFrame ? fetchZipAsset(
        String(primaryFrame.path || primaryFrame.image_path || ''),
        `accepted_frame/${panelId}-accepted-frame`,
      ) : Promise.resolve(null),
      ...references.map((reference, index) => {
        const raw = String(reference.path || reference.url || '')
        const label = sanitizeZipName(String(reference.id ?? reference.title ?? `reference-${index + 1}`))
        return fetchZipAsset(raw, `references/${String(index + 1).padStart(2, '0')}-${label}`)
      }),
    ])
    entries.push(...imageEntries.filter(Boolean) as ZipFileEntry[])

    const zip = createStoredZip(entries)
    const copied = await copyZipBlobToClipboard(zip)
    if (!copied) downloadBlob(zip, filename)
    setCopyStatus(copied ? 'Copied zip' : 'Downloaded')
    window.setTimeout(() => setCopyStatus(''), 1600)
  }

  return (
    <article data-qid="dream:storyboard:panel" style={nvis.storyboardPanelCard}>
      <div style={nvis.storyboardFrame}>
        {primaryReferenceUrl ? (
          <img
            src={primaryReferenceUrl}
            alt={String(panel.panel_id ?? 'accepted storyboard frame')}
            style={nvis.storyboardFrameImage}
          />
        ) : (
          <div style={nvis.storyboardFrameMissing}>
            <span style={nvis.storyboardFrameGuideLabel}>{String(panel.panel_id ?? 'panel')} · {shotCode}</span>
            <span style={nvis.storyboardFrameGuideLine}>Storyboard frame pending</span>
            <small>Start and end frame specs below</small>
          </div>
        )}
        <div style={nvis.storyboardFrameShade} />
        <div style={nvis.storyboardFrameTop}>
          <span style={nvis.storyboardPanelId}>{String(panel.panel_id ?? 'panel')} · {timeLabel}</span>
          <div style={nvis.storyboardPanelFrameActions}>
            <button
              type="button"
              data-qid={`dream:storyboard:copy-panel:${String(panel.panel_id ?? 'panel')}`}
              title="Copy full panel prompt payload"
              aria-label="Copy full panel prompt payload"
              onClick={() => { void copyPanelPayload() }}
              style={nvis.storyboardCopyButton}
            >
              {copyStatus ? <ClipboardCheck size={13} /> : <Copy size={13} />}
            </button>
          </div>
        </div>
        <div style={nvis.storyboardFrameBottom}>
          <span style={nvis.storyboardShotCode}><Camera size={12} /> {shotCode}</span>
          <span style={nvis.storyboardFrameCaption}>{shotText}</span>
        </div>
      </div>

      <div style={nvis.storyboardPanelBody}>
        <p style={nvis.storyboardAction}>{String(panel.action ?? 'Missing action text')}</p>
        {panel.dialogue && <p style={nvis.storyboardDialogue}>{String(panel.dialogue)}</p>}
        <details data-storyboard-accordion style={nvis.storyboardAccordion}>
          <summary data-storyboard-accordion-header style={nvis.storyboardAccordionHeader}>
            <span>View Generation Specs</span>
            <ChevronDown data-storyboard-accordion-chevron size={14} style={nvis.storyboardAccordionChevron} />
          </summary>
          <div style={nvis.storyboardAccordionContent}>
            <StoryboardPromptBlock prompt={generationPrompt} />
            <div style={nvis.storyboardSupportGrid}>
              <StoryboardSupportBlock
                title="Start Frame"
                body={String(startFrame.description ?? 'Missing start-frame description')}
                items={storyboardStringList(startFrame.visual_requirements)}
              />
              <StoryboardSupportBlock
                title="End Frame"
                body={String(endFrame.description ?? 'Missing end-frame description')}
                items={storyboardStringList(endFrame.visual_requirements)}
              />
              <StoryboardSupportBlock
                title="Camera / Lighting"
                body={`${String(cameraPlan.movement ?? 'Missing camera movement')} ${String(cameraPlan.composition ?? '')}`.trim()}
                items={[
                  String(cameraPlan.camera_equipment ?? 'camera equipment missing'),
                  String(lightingPlan.time_of_day ?? 'time of day missing'),
                  String(lightingPlan.quality ?? 'lighting quality missing'),
                ]}
              />
              <StoryboardSupportBlock
                title="Acting Beats"
                body={actingBeats.length ? actingBeats.join(' ') : 'Missing acting beats'}
                items={[
                  `Producer: ${String(productionNotes.producer ?? 'missing')}`,
                  `Director: ${String(productionNotes.director ?? 'missing')}`,
                  `Scriptwriter: ${String(productionNotes.scriptwriter ?? 'missing')}`,
                ]}
              />
            </div>
          </div>
        </details>
        <div style={nvis.storyboardTrackRow}>
          {seeds.length > 0 && (
            <div style={nvis.storyboardTagGroup}>
              <span style={nvis.storyboardTagLabel}>Seeds</span>
              <div style={nvis.storyboardSeedRow}>
                {seeds.map((seed) => <span key={seed} style={nvis.storyboardSeed}>{seed}</span>)}
              </div>
            </div>
          )}
          {entities.length > 0 && (
            <div style={nvis.storyboardTagGroup}>
              <span style={nvis.storyboardTagLabel}>Entities</span>
              <div style={nvis.storyboardEntityRow}>
                {entities.map((entity) => <span key={entity} style={nvis.storyboardEntity}>{entity}</span>)}
              </div>
            </div>
          )}
        </div>
        {references.length > 0 && (
          <div style={nvis.storyboardReferenceRail}>
            {references.map((reference) => {
              const raw = String(reference.path || reference.url || '')
              const url = dreamAssetUrl(raw)
              const imageEligible = Boolean(url) && String(reference.role ?? '') !== 'rejected_candidate_reference'
              return (
                <div key={String(reference.id ?? reference.title ?? raw)} style={nvis.storyboardReferenceCard}>
                  {imageEligible ? (
                    <img src={url} alt={String(reference.title ?? reference.id ?? 'reference')} style={nvis.storyboardReferenceThumb} />
                  ) : (
                    <div style={nvis.storyboardReferenceFallback}><Image size={16} /></div>
                  )}
                  <div style={nvis.storyboardReferenceText}>
                    <span>{String(reference.title ?? reference.id ?? 'Reference')}</span>
                    <small>{String(reference.role ?? reference.memory_key ?? 'reference')}</small>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </article>
  )
}

function StoryboardPromptBlock({ prompt }: { prompt: Record<string, unknown> }) {
  const panelPrompt = String(prompt.panel_prompt ?? 'Missing storyboard panel generation prompt')
  const startPrompt = String(prompt.start_frame_prompt ?? 'Missing start-frame prompt')
  const endPrompt = String(prompt.end_frame_prompt ?? 'Missing end-frame prompt')
  const requirements = storyboardStringList(prompt.reference_requirements)
  const negativePrompt = String(prompt.negative_prompt ?? 'Missing negative prompt')
  return (
    <div style={nvis.storyboardPromptBlock}>
      <div style={nvis.storyboardPromptHeader}>Panel Generation Prompt</div>
      <p style={nvis.storyboardPromptText}>{panelPrompt}</p>
      <div style={nvis.storyboardPromptPair}>
        <div>
          <span style={nvis.storyboardPromptLabel}>Start</span>
          <p>{startPrompt}</p>
        </div>
        <div>
          <span style={nvis.storyboardPromptLabel}>End</span>
          <p>{endPrompt}</p>
        </div>
      </div>
      {requirements.length > 0 && (
        <div style={nvis.storyboardPromptRequirements}>
          {requirements.map((item) => <span key={item}>{item}</span>)}
        </div>
      )}
      <div style={nvis.storyboardNegativePrompt}>Must not: {negativePrompt}</div>
    </div>
  )
}

function StoryboardSupportBlock({ title, body, items }: { title: string; body: string; items: string[] }) {
  return (
    <div style={nvis.storyboardSupportBlock}>
      <div style={nvis.storyboardSupportTitle}>{title}</div>
      <p style={nvis.storyboardSupportBody}>{body}</p>
      {items.length > 0 && (
        <ul style={nvis.storyboardSupportList}>
          {items.slice(0, 4).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function EvidenceCard({ title, status, children }: { title: string; status: string; children: React.ReactNode }) {
  const tone = statusTone(status)
  const borderColor = tone === 'pass' ? '#00ff88' : tone === 'blocked' ? '#ff4444' : 'rgba(255,255,255,0.13)'
  return (
    <div style={{ ...nvis.evidenceCard, borderColor }}>
      <div style={nvis.evidenceCardHeader}>
        <span style={nvis.evidenceCardTitle}>{title}</span>
        <StatusBadge status={status} />
      </div>
      {children}
    </div>
  )
}

function DirectorConsole({
  rows,
  location,
  environment,
  gateState,
  coreIdea,
  linkedAssets,
}: {
  rows: StoryMatrixRow[]
  location: string
  environment: string
  gateState: string
  coreIdea: string
  linkedAssets: LinkedStoryAsset[]
}) {
  const [creativity, setCreativity] = useState(0.6)
  const [panelCount, setPanelCount] = useState(1)
  const [durationSeconds, setDurationSeconds] = useState(10)
  const [writer, setWriter] = useState('')
  const [writers, setWriters] = useState<StoryWriterOption[]>([])
  const [draft, setDraft] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const [generateStatus, setGenerateStatus] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)

  useEffect(() => {
    let cancelled = false
    try {
      const savedDraft = localStorage.getItem(DREAM_STORY_DRAFT_STORAGE_KEY)
      const savedStatus = localStorage.getItem(DREAM_STORY_STATUS_STORAGE_KEY)
      if (savedDraft) {
        setDraft(savedDraft)
        if (savedStatus) setGenerateStatus(compactStoryStatus(savedStatus))
        return () => { cancelled = true }
      }
      if (savedStatus) setGenerateStatus(compactStoryStatus(savedStatus))
    } catch {
      // Local storage is a convenience cache; generation still works without it.
    }
    fetch('/api/tau/dream/story-draft/latest')
      .then(async (response) => {
        if (!response.ok) return null
        return response.json()
      })
      .then((data) => {
        if (cancelled || !data || typeof data.draft !== 'string' || data.draft.trim().length === 0) return
        updateDraft(data.draft)
        updateGenerateStatus('Loaded latest Tau story')
      })
      .catch(() => {
        // No prior Tau story artifact is acceptable; the user can still draft one.
      })
    return () => { cancelled = true }
  }, [])

  const updateDraft = (nextDraft: string) => {
    setDraft(nextDraft)
    try {
      if (nextDraft) {
        localStorage.setItem(DREAM_STORY_DRAFT_STORAGE_KEY, nextDraft)
      } else {
        localStorage.removeItem(DREAM_STORY_DRAFT_STORAGE_KEY)
      }
    } catch {
      // Ignore storage failures; React state remains authoritative for this session.
    }
  }

  const updateGenerateStatus = (nextStatus: string) => {
    const compact = compactStoryStatus(nextStatus)
    setGenerateStatus(compact)
    try {
      if (compact) {
        localStorage.setItem(DREAM_STORY_STATUS_STORAGE_KEY, compact)
      } else {
        localStorage.removeItem(DREAM_STORY_STATUS_STORAGE_KEY)
      }
    } catch {
      // Ignore storage failures; visible state still updates.
    }
  }

  useRegisterAction('dream:story:writer', {
    app: 'ux-lab',
    action: 'DREAM_STORY_WRITER_SELECT',
    label: 'Select author persona',
    description: 'Choose the Phase 02 author persona from persona_memory',
  })
  useRegisterAction('dream:story:creativity', {
    app: 'ux-lab',
    action: 'DREAM_STORY_CREATIVITY_SET',
    label: 'Set story creativity',
    description: 'Adjust the Phase 02 story creativity control',
  })
  useRegisterAction('dream:story:generate', {
    app: 'ux-lab',
    action: 'DREAM_STORY_GENERATE',
    label: 'Draft treatment',
    description: 'Generate a story treatment from current actors, objects, environment, and dynamics rows',
  })
  useRegisterAction('dream:story:draft', {
    app: 'ux-lab',
    action: 'DREAM_STORY_DRAFT_EDIT',
    label: 'Edit story draft',
    description: 'Edit the Phase 02 generated story treatment',
  })

	  useEffect(() => {
	    let cancelled = false
	    async function loadWriters() {
	      try {
	        const personasResponse = await fetch('/api/memory/list', {
	          method: 'POST',
	          headers: { 'Content-Type': 'application/json' },
	          body: JSON.stringify({
	            collection: 'personas',
	            filters: { doc_type: 'persona_profile' },
	            limit: 200,
	          }),
	        })
	        if (personasResponse.ok) {
	          const personasData = await personasResponse.json()
	          const personaItems = Array.isArray(personasData.documents) ? personasData.documents : []
	          const personaWriters = personaItems
	            .filter((item: Record<string, unknown>) => {
	              if (item.validation_status === 'quarantined' || item.canon_status === 'invalidated' || item.upsert_eligible === false) return false
	              const tags = Array.isArray(item.tags) ? item.tags.map(String) : []
	              const haystack = [
	                item.template,
	                item.source_path,
	                item.runtime_persona_card,
	                item.content,
	                item.writing_style,
	                ...tags,
	              ].join(' ').toLowerCase()
	              return haystack.includes('writer') || haystack.includes('author') || tags.includes('template:writer')
	            })
	            .map((item: Record<string, unknown>) => {
	              const id = String(item.persona_id || item._key || '').trim()
	              const label = String(item.canonical_name || item.display_name || id.replace(/_/g, ' ')).trim()
	              const description = String(item.writing_style || item.runtime_persona_card || item.summary || item.content || '').replace(/\s+/g, ' ').trim()
	              return { id, label, description: description.slice(0, 1200) }
	            })
	            .filter((option: StoryWriterOption) => option.id && option.description)
	          if (personaWriters.length > 0) {
	            if (!cancelled) {
	              setWriters(personaWriters)
	              setWriter((current) => current || personaWriters[0]?.id || '')
	            }
	            return
	          }
	        }

	        const [identityResponse, styleResponse] = await Promise.all([
	          fetch('/api/memory/list', {
	            method: 'POST',
	            headers: { 'Content-Type': 'application/json' },
	            body: JSON.stringify({
	              collection: 'persona_memory',
	              filters: { record_type: 'persona_identity' },
	              limit: 200,
	            }),
	          }),
	          fetch('/api/memory/list', {
	            method: 'POST',
	            headers: { 'Content-Type': 'application/json' },
	            body: JSON.stringify({
	              collection: 'persona_memory',
	              filters: { record_type: 'persona_style' },
	              limit: 200,
	            }),
	          }),
	        ])
	        if (!identityResponse.ok || !styleResponse.ok) return
	        const identityData = await identityResponse.json()
	        const styleData = await styleResponse.json()
	        const identityItems = Array.isArray(identityData.documents) ? identityData.documents : []
	        const styleItems = Array.isArray(styleData.documents) ? styleData.documents : []
	        const writersById = new Map<string, {
	          label: string
	          identityText: string[]
	          styleText: string[]
	        }>()
	        const ensureWriter = (personaId: string) => {
	          const existing = writersById.get(personaId)
	          if (existing) return existing
	          const created = {
	            label: personaId.replace(/^persona_/, '').replace(/_/g, ' '),
	            identityText: [] as string[],
	            styleText: [] as string[],
	          }
	          writersById.set(personaId, created)
	          return created
	        }
	        identityItems.forEach((item: Record<string, unknown>) => {
	          if (item.validation_status === 'quarantined' || item.canon_status === 'invalidated' || item.upsert_eligible === false) return
	          const sourcePath = String(item.source_path ?? '')
	          const text = `${item.retrieval_text ?? ''} ${item.evidence_text ?? ''}`.toLowerCase()
	          if (!sourcePath.includes('/writers/') && !text.includes('template: writer') && !text.includes('writer template') && !text.includes('author')) return
	          const personaId = String(item.persona_id || item._key || '').trim()
	          if (!personaId) return
	          const writerRecord = ensureWriter(personaId)
	          const raw = String(item.evidence_text || item.retrieval_text || personaId)
	          const nameMatch = raw.match(/(?:^|\n)\s*name:\s*([^\n]+)/i)
	            || raw.match(/#\s*([^-#\n]+?)\s*-\s*(?:Science Fiction Writer|Writer|Author)/i)
	          writerRecord.label = (nameMatch?.[1] || writerRecord.label).trim()
	          writerRecord.identityText.push(raw.replace(/\s+/g, ' ').trim())
	        })
	        styleItems.forEach((item: Record<string, unknown>) => {
	          if (item.validation_status === 'quarantined' || item.canon_status === 'invalidated' || item.upsert_eligible === false) return
	          const personaId = String(item.persona_id || item._key || '').trim()
	          if (!personaId || !writersById.has(personaId)) return
	          const raw = String(item.claim_text || item.answer_text || item.evidence_text || item.retrieval_text || '').replace(/\s+/g, ' ').trim()
	          if (raw) ensureWriter(personaId).styleText.push(raw)
	        })
	        const next = [...writersById.entries()]
	          .map(([id, value]) => ({
	            id,
	            label: value.label,
	            description: (value.styleText.length > 0 ? value.styleText : value.identityText).join(' ').slice(0, 900),
	          }))
	          .filter((option) => option.description.trim().length > 0)
	        if (!cancelled) {
	          setWriters(next)
	          setWriter((current) => current || next[0]?.id || '')
        }
      } catch {
        if (!cancelled) setWriters([])
      }
    }
    void loadWriters()
    return () => { cancelled = true }
  }, [])

  const buildStoryPromptPayload = (): StoryPromptPayload => {
    const selectedWriter = writers.find((option) => option.id === writer)
    const requestedAuthor = selectedWriter?.label || writer || 'unselected_author'
    const authorMemoryStyle = selectedWriter?.description || ''
    const expandedAuthorStyleGuide = authorStyleGuide(requestedAuthor, authorMemoryStyle)
    const storyKind = panelCount === 1 ? 'one_panel_10_second_story' : 'multi_panel_story_sequence'
    const targetStoryLengthWords = {
      min: Math.max(35, panelCount * 45),
      max: Math.max(70, panelCount * 90),
    }
    const panelSchema = {
      type: 'object',
      additionalProperties: false,
      required: [
        'shot',
        'action',
        'emotional_turn',
        'dialogue',
      ],
      properties: {
        shot: {
          type: 'string',
          description: 'Camera/framing for this panel.',
        },
        action: {
          type: 'string',
          description: 'What happens in this panel moment.',
        },
        emotional_turn: {
          type: 'string',
          description: 'The visible internal shift.',
        },
        dialogue: {
          type: ['string', 'null'],
          description: 'One short line or null.',
        },
      },
    }
    const authorStyleDirective = {
      requested_author: requestedAuthor,
      style_policy: 'High-level craft traits only; do not directly imitate the living author.',
      memory_style_context: authorMemoryStyle,
      expanded_style_guide: expandedAuthorStyleGuide,
      style_summary: expandedAuthorStyleGuide,
      actionable_traits: [
        'practical problem-solving under physical constraints',
        'clear cause-and-effect scene logic',
        'dry, understated observational humor',
        'technical specificity that changes character choices',
        'characters thinking through immediate problems step by step',
        'exposition that feels like active problem-solving rather than lecturing',
        'conversational, precise, propulsive pacing',
        'reader satisfaction from understanding the problem and the earned solution',
        'tension created by real-world timing, physics, etiquette, and limited information',
        'grounded stakes rather than melodrama',
      ],
      application_to_this_story: [
        'Use swell timing as a procedural problem.',
        'Use the lava reef as a hard physical constraint.',
        'Use heat, humidity, softened wax, glare, and fatigue as active causes of mistakes or hesitation.',
        'Let Embry and Kai reveal character through how they solve or avoid problems in the water.',
        'Move through problem, constraint, attempted solution, complication, and embodied decision.',
        'Keep humor understated and observational, never jokey or detached from the stakes.',
      ],
      prohibited_imitation: [
        'Do not copy the requested author exact prose style.',
        'Do not echo specific phrasing, character types, plots, or scenes from the requested author works.',
        'Do not make the story sound like fan fiction of an existing book.',
      ],
    }
    const creativityDirective = {
      slider_value: creativity,
      label: 'grounded moderate invention',
      actionable_interpretation: 'Stay realistic and physically plausible while allowing selective invented details that intensify tension, character contrast, and scene texture.',
      allowed_inventions: [
        'small work-related phone interruptions',
        'specific family-obligation pressure for Embry',
        'a plausible local-etiquette tension in the lineup',
        'a softened-wax or grip problem caused by heat',
        'a tricky but realistic summer swell set',
        'small practical surf details that clarify risk and decision-making',
      ],
      limits: [
        'no surrealism',
        'no supernatural events',
        'no catastrophic rescue sequence unless explicitly requested',
        'no major new plotline unrelated to the sick-day surf premise',
        'no exaggerated recklessness',
        'no melodramatic confession scene',
        'no ignoring the support matrix',
      ],
      plot_risk_level: 'moderate',
      realism_requirement: 'Every major beat must be explainable through character choice, surf conditions, reef constraints, social etiquette, heat, fatigue, or phone obligations.',
    }
    const beatIds = [
      'opening_image',
      'the_lie',
      'entering_the_water',
      'failed_or_hesitant_attempt',
      'kai_restraint',
      'mid_scene_tension',
      'decisive_set',
      'resolution',
    ]
    const normalizedRows = rows.map((row) => ({
      id: row.id,
      name: row.name,
      category: storyRowCategory(row),
      objects: splitStoryObjects(row.objects),
      environment_ref: 'env-0',
      environment: row.environment,
      dynamics: row.dynamics,
      note: row.note,
      is_complete: row.isComplete,
      contact_sheet: contactSheetDecisionForStoryRow(row),
    }))
    const sourceContext = {
      core_idea: coreIdea,
      author: {
        id: writer || null,
        name: requestedAuthor,
        memory_style_context: authorMemoryStyle,
        expanded_style_guide: expandedAuthorStyleGuide,
      },
      location: {
        place: 'Kahaluʻu Bay',
        region: 'Kona Coast',
        island: 'Big Island',
        weekday: 'Wednesday',
        month: 'June',
        year: 2024,
        time_window: 'daylight surf window',
        display: location,
      },
      environment: {
        id: 'env-0',
        description: environment,
        active_pressures: [
          'sweat',
          'glare',
          'wax softness',
          'saltwater',
          'fatigue',
          'grip changes',
          'footing changes',
          'board control changes',
          'reef caution',
          'social patience',
        ],
      },
      interaction_rows: normalizedRows,
      linked_assets: linkedAssets.map((asset) => ({
        id: asset.id,
        title: asset.title,
        description: asset.description || '',
        memory_key: asset.memoryKey || null,
        media_type: asset.mediaType || 'unknown',
        source: asset.source || null,
        visibility: asset.description ? 'caption_grounded' : 'metadata_only',
      })),
    }
    const generationDirectives = {
      thematic_pivot: 'Autonomy vs. Obligation',
      author_style_directive: authorStyleDirective,
      creativity_directive: creativityDirective,
    }
    const assetPolicy = {
      visibility: linkedAssets.some((asset) => asset.description) ? 'caption_grounded_or_metadata_only' : 'metadata_only',
      rule: 'Use stored media descriptions when present. If a linked asset lacks a description, use its title only and do not invent visual, audio, or video details from an inaccessible URL.',
      allowed_asset_use: [
        'character identity continuity',
        'surfing pose and board continuity',
        'environment and coastline continuity',
        'sound or video reference only when a stored description exists',
      ],
      forbidden_asset_use: [
        'do not infer facial features from a URL',
        'do not infer body type from a URL',
        'do not infer colors or clothing beyond prompt fields and stored descriptions',
        'do not claim to have seen media that is metadata-only',
      ],
    }
    const responseContract = {
      type: 'object',
      additionalProperties: false,
      required: [
        'story',
        'panel_count',
        'duration_seconds',
        'location',
        'environment',
        'panel',
        'panels',
        'interaction_matrix',
        'asset_usage',
        'style_application',
        'quality_checks',
      ],
      properties: {
        story: {
          type: 'string',
          minLength: targetStoryLengthWords.min * 4,
          maxLength: targetStoryLengthWords.max * 9,
          description: `A concise, human-written story beat for ${panelCount} panel(s) and ${durationSeconds} seconds, approximately ${targetStoryLengthWords.min}-${targetStoryLengthWords.max} words.`,
        },
        panel_count: {
          type: 'number',
          const: panelCount,
          description: 'The exact number of story panels requested by the Phase 02 controls.',
        },
        duration_seconds: {
          type: 'number',
          const: durationSeconds,
          description: 'Target duration represented by the requested panel sequence.',
        },
        location: {
          type: 'object',
          additionalProperties: false,
          required: ['place', 'time', 'month', 'year', 'description'],
          properties: {
            place: { type: 'string', description: 'Place name and region from source_context.location.' },
            time: { type: 'string', description: 'Weekday and daylight/time window from source_context.location.' },
            month: { type: 'string', description: 'Month from source_context.location.' },
            year: { type: 'number', description: 'Year from source_context.location.' },
            description: { type: 'string', description: 'Concise setting description used by the story.' },
          },
        },
        environment: {
          type: 'object',
          additionalProperties: false,
          required: ['weather_description', 'active_pressures', 'story_effect'],
          properties: {
            weather_description: { type: 'string', description: 'Descriptive weather and surf conditions characters physically respond to.' },
            active_pressures: {
              type: 'array',
              minItems: 4,
              items: { type: 'string' },
            },
            story_effect: { type: 'string', description: 'How weather, surf, reef, and public beach pressure drive the story beat.' },
          },
        },
        panel: {
          ...panelSchema,
          description: 'Primary or first panel, duplicated from panels[0] for consumers that expect a single panel.',
        },
        panels: {
          type: 'array',
          minItems: panelCount,
          maxItems: panelCount,
          items: panelSchema,
          description: 'Exactly panel_count panels. For one panel, this array contains the same panel as panel.',
        },
        interaction_matrix: {
          type: 'array',
          minItems: rows.length,
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['source_seed_id', 'entity', 'category', 'objects_used', 'environment_interaction', 'story_function', 'visible_in_panel', 'contact_sheet'],
            properties: {
              source_seed_id: { type: 'string', description: 'Copy from source_context.interaction_rows[].id.' },
              entity: { type: 'string', description: 'Copy from source_context.interaction_rows[].name.' },
              category: {
                type: 'string',
                enum: ['character', 'character_object', 'environmental_force', 'location_social_system'],
              },
              objects_used: {
                type: 'array',
                items: { type: 'string' },
              },
              environment_interaction: { type: 'string', description: 'Complete explanation of how heat, humidity, water, reef, light, fatigue, or public etiquette changes this entity/object/force.' },
              story_function: { type: 'string', description: 'Why this row matters to the one-panel story beat and what would be missing if it were removed.' },
              visible_in_panel: { type: 'boolean' },
              contact_sheet: {
                type: 'object',
                additionalProperties: false,
                required: ['required', 'kind', 'status', 'send_to_kling', 'priority', 'rationale'],
                description: 'Whether this row needs a contact sheet/reference pack for Phase 04 video provider preparation.',
                properties: {
                  required: { type: 'boolean', description: 'True when a stable visual reference is needed for this row.' },
                  kind: { type: 'string', enum: ['character', 'prop', 'environment', 'prompt_only'] },
                  status: { type: 'string', enum: ['existing_or_required', 'missing', 'not_needed'] },
                  send_to_kling: { type: 'boolean', description: 'True only when the reference should be part of the video provider element pack.' },
                  priority: { type: 'string', enum: ['required', 'recommended', 'conditional', 'prompt_only'] },
                  rationale: { type: 'string', description: 'One sentence explaining why the row does or does not require a contact sheet.' },
                },
              },
            },
          },
        },
        asset_usage: {
          type: 'array',
          minItems: Math.min(linkedAssets.length, 1),
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['asset_id', 'used_for', 'usage_confidence'],
            properties: {
              asset_id: { type: 'string', description: 'Copy from source_context.linked_assets[].id.' },
              used_for: { type: 'string', description: 'Specific visual, audio, video, or text grounding role in the story.' },
              usage_confidence: { type: 'string', enum: ['metadata_only', 'caption_grounded', 'image_grounded', 'audio_grounded', 'video_grounded'] },
            },
          },
        },
        style_application: {
          type: 'object',
          additionalProperties: false,
          required: ['author_reference_used_as', 'creativity_level_used_as'],
          properties: {
            author_reference_used_as: { type: 'string' },
            creativity_level_used_as: { type: 'string' },
          },
        },
        quality_checks: {
          type: 'object',
          additionalProperties: false,
          required: [
            'covered_seed_ids',
            'missing_seed_ids',
            'used_only_provided_context',
            'no_direct_author_imitation',
            'valid_one_panel_10_second_moment',
          ],
          properties: {
            covered_seed_ids: {
              type: 'array',
              items: { type: 'string' },
            },
            missing_seed_ids: {
              type: 'array',
              items: { type: 'string' },
            },
            used_only_provided_context: { type: 'boolean' },
            no_direct_author_imitation: { type: 'boolean' },
            valid_one_panel_10_second_moment: { type: 'boolean' },
          },
        },
      },
    }
    const invalidIf = [
      'The response includes markdown, prose outside JSON, or a code fence.',
      'The response includes any top-level key not listed in response_contract.required.',
      'The response adds an asset_id that is not present in source_context.linked_assets[].id.',
      'The response omits any completed source_context.interaction_rows[].id from interaction_matrix[].source_seed_id.',
      'The story or panel ignores source_context.environment when describing character or object behavior.',
      'A surfboard appears but the output omits shape, wax state, condition, or age in story, panel, or interaction_matrix.',
      'The output expands into a multi-scene treatment instead of one 10-second panel beat.',
      'The output directly imitates a living author instead of using high-level craft traits.',
      'author_style_directive does not translate the requested author into high-level non-imitative craft traits.',
      'creativity_directive does not convert the slider value into concrete allowed inventions and limits.',
    ]
    const deterministicChecks = [
      'Parse response as JSON.',
      'Reject if any key outside response_contract.properties appears at the top level.',
      'Validate the JSON object against response_contract with additionalProperties=false at every object level.',
      'Check every completed source_context.interaction_rows[].id appears in interaction_matrix[].source_seed_id.',
      'Check every interaction_matrix[] row includes contact_sheet with required, kind, status, send_to_kling, priority, and rationale.',
      'Check every asset_usage[].asset_id exists in source_context.linked_assets[].id.',
      'Check quality_checks.missing_seed_ids is empty.',
      'Check quality_checks.used_only_provided_context, no_direct_author_imitation, and valid_one_panel_10_second_moment are true.',
      'If any interaction row entity contains "surfboard", require the output text to mention shape, wax, condition, or age.',
      'Check style_application explains how the author reference and creativity slider were converted into behavior.',
    ]
    const example = {
      input: {
        context: {
          core_idea: 'Embry and Kai fake a sick day to surf at Kahaluʻu Bay.',
          location: 'Kahaluʻu Bay, Kona Coast · Wednesday · daylight surf window · June · 2024',
          environment: 'Hot humid air, bright glare, lava reef, and soft wax change footing and timing.',
          interaction_rows: [
            {
              id: 'seed-embry',
              name: 'Embry',
              category: 'character',
              objects: ['navy rashguard', 'waxed older white shortboard', 'phone'],
              environment_ref: 'env-0',
              dynamics: 'Glare and fatigue make timing a physical test.',
              note: 'Show salt, sweat, careful rail grip, and hesitation before the wave.',
              is_complete: true,
              contact_sheet: {
                required: true,
                kind: 'character',
                status: 'existing_or_required',
                send_to_kling: true,
                priority: 'required',
                rationale: 'Embry identity continuity must be locked before video provider generation.',
              },
            },
          ],
          linked_assets: [
            {
              id: 'embry_media_asset__example_png',
              title: 'Embry surfing reference',
              description: 'Embry crouches on a white surfboard with lava rocks and green mountains behind her.',
              memoryKey: 'embry_media_asset__example_png',
              mediaType: 'image',
              visibility: 'caption_grounded',
            },
          ],
        },
      },
      expected_output: {
        story: 'Embry’s phone buzzes inside the beach bag just as a clean shoulder stands up over the reef; she squints through the glare, palms slipping on sun-soft wax, and chooses the paddle while Kai, already angled safely outside, only lifts two fingers toward the channel instead of telling her what to do.',
        panel_count: panelCount,
        duration_seconds: durationSeconds,
        location: {
          place: 'Kahaluʻu Bay, Kona Coast, Big Island',
          time: 'Wednesday daylight surf window',
          month: 'June',
          year: 2024,
          description: 'A public Kona Coast surf break where private escape is constrained by shared lineup rules.',
        },
        environment: {
          weather_description: 'Hot, humid coastal air with bright glare, saltwater, summer swell, shallow lava reef, and sun-softened wax.',
          active_pressures: ['heat', 'humidity', 'glare', 'softened wax', 'fatigue', 'lava reef caution', 'local etiquette'],
          story_effect: 'The weather and reef make each surf decision physical: grip, timing, patience, and restraint all matter.',
        },
        panel: {
          shot: 'Low waterline three-quarter shot facing the reef line, with Embry in the foreground on the older white shortboard and Kai farther out, half-turned toward the incoming set.',
          action: 'A June swell rises over the dark lava shapes; Embry commits to the paddle despite sweat, glare, and the phone buzzing onshore.',
          emotional_turn: 'Embry moves from borrowed escape to embodied choice: she is still obligated, still exposed, but the decision is hers.',
          dialogue: null,
        },
        panels: [
          {
            shot: 'Low waterline three-quarter shot facing the reef line, with Embry in the foreground on the older white shortboard and Kai farther out, half-turned toward the incoming set.',
            action: 'A June swell rises over the dark lava shapes; Embry commits to the paddle despite sweat, glare, and the phone buzzing onshore.',
            emotional_turn: 'Embry moves from borrowed escape to embodied choice: she is still obligated, still exposed, but the decision is hers.',
            dialogue: null,
          },
        ],
        interaction_matrix: [
          {
            source_seed_id: 'seed-embry',
            entity: 'Embry',
            category: 'character',
            objects_used: ['navy rashguard', 'waxed older white shortboard', 'phone'],
            environment_interaction: 'Humidity softens wax, glare hides the reef line, and fatigue makes her commitment visible.',
            story_function: 'Turns autonomy into a bodily choice in the exact surf moment.',
            visible_in_panel: true,
            contact_sheet: {
              required: true,
              kind: 'character',
              status: 'existing_or_required',
              send_to_kling: true,
              priority: 'required',
              rationale: 'Embry appears in the panel and needs stable character identity continuity.',
            },
          },
        ],
        asset_usage: [
          {
            asset_id: 'embry_media_asset__example_png',
            used_for: 'Embry body posture, surfboard color, lava rock coastline, and mountain backdrop.',
            usage_confidence: 'caption_grounded',
          },
        ],
        style_application: {
          author_reference_used_as: 'High-level craft guidance: practical cause-and-effect staging, physical constraints, and dry restraint without direct imitation.',
          creativity_level_used_as: 'Grounded moderate invention: a plausible phone buzz and decisive swell heighten the moment without breaking realism.',
        },
        quality_checks: {
          covered_seed_ids: ['seed-embry'],
          missing_seed_ids: [],
          used_only_provided_context: true,
          no_direct_author_imitation: true,
          valid_one_panel_10_second_moment: true,
        },
      },
    }
    const rawPrompt = [
      '## Role',
      'You are the Phase 02 Story author for Embry OS.',
      '',
      '## Task',
      `Generate an original ${panelCount}-panel, ${durationSeconds}-second story beat for the Phase 02 Story pane. Return one JSON object that matches the Output Format section at the end of this prompt.`,
      '',
      '## Input Field Paths',
      '- source_context.core_idea: story directive text.',
      '- source_context.location: place, weekday, daylight/time window, month, and year.',
      '- source_context.environment.description: weather, heat, humidity, swell, reef, light, water, fatigue, and physical constraints.',
      '- source_context.environment.active_pressures[]: specific physical pressures the story must operationalize.',
      '- source_context.interaction_rows[].id: stable row id that must be copied into interaction_matrix[].source_seed_id.',
      '- source_context.interaction_rows[].category: one of character, character_object, environmental_force, location_social_system.',
      '- source_context.interaction_rows[].objects[]: physical objects or body-worn items.',
      '- source_context.interaction_rows[].dynamics: how the row behaves under the environment.',
      '- source_context.interaction_rows[].note: script/panel staging instruction.',
      '- source_context.interaction_rows[].contact_sheet: deterministic Phase 04 reference-pack decision. Copy and refine this into interaction_matrix[].contact_sheet.',
      '- source_context.linked_assets[].id: stable asset id that must be copied into asset_usage[].asset_id.',
      '- source_context.linked_assets[].description: stored image, sound, video, or text description.',
      '- source_context.author.memory_style_context: selected persona memory style that determines how the story is written.',
      '- generation_directives.author_style_directive: high-level, non-imitative author craft traits.',
      '- generation_directives.creativity_directive: slider value translated into concrete generation behavior.',
      '- response_contract: strict JSON schema suitable for Pydantic/dataclass validation.',
      '',
      '## Source Material',
      '<source_context>',
      JSON.stringify(sourceContext, null, 2),
      '</source_context>',
      '',
      '## Generation Directives',
      '<generation_directives>',
      JSON.stringify(generationDirectives, null, 2),
      '</generation_directives>',
      '',
      '## Asset Policy',
      JSON.stringify(assetPolicy, null, 2),
      '',
      '## Constraints',
      '- Use only facts present in source_context and generation_directives.',
      '- Do not imitate any living author directly. Apply generation_directives.author_style_directive as high-level craft guidance only.',
      '- The selected author determines prose behavior. Use source_context.author.memory_style_context and generation_directives.author_style_directive to shape rhythm, humor, technical detail, and causality.',
      '- Apply generation_directives.creativity_directive. Creativity 0.6 means grounded moderate invention, not surrealism or melodrama.',
      '- Treat the environment as plot machinery, not scenery.',
      `- Produce exactly ${panelCount} panel(s) totaling ${durationSeconds} seconds, not a full short story and not an eight-beat treatment.`,
      `- Set panel_count to ${panelCount} and duration_seconds to ${durationSeconds}.`,
      `- Return panels[] with exactly ${panelCount} item(s), and set panel equal to panels[0].`,
      `- Keep story to roughly ${targetStoryLengthWords.min}-${targetStoryLengthWords.max} words so the panel sequence stays focused.`,
      '- Include one interaction_matrix row for every source_context.interaction_rows[] item where is_complete is true.',
      '- The interaction_matrix is the completeness ledger: every character, object, location, environmental force, and relevant pressure used by the story must be explained there.',
      '- Every interaction_matrix row must include contact_sheet. Characters require character contact sheets. Visually specific hero props such as surfboards require prop sheets when visible. Stable locations/environments require compact environment sheets when they anchor a video provider panel. Abstract pressures such as heat, humidity, glare, fatigue, etiquette, and timing are prompt-only unless embodied by a stable visual element.',
      '- Do not mark send_to_kling true for abstract forces alone. Do mark send_to_kling true for Embry, Kai, visible surfboards, and the active surf-break environment when they appear in the panel.',
      '- Include asset_usage rows only for source_context.linked_assets[] entries that influence the story.',
      '- Include top-level location and environment objects. They must be populated from source_context.location and source_context.environment, not omitted.',
      '- Copy asset_usage[].asset_id from source_context.linked_assets[].id.',
      '- Copy interaction_matrix[].source_seed_id from source_context.interaction_rows[].id.',
      '- If Embry, Kai, a surfboard, reef, swell, phone, heat, humidity, glare, wax, or fatigue appears in source_context, show how it changes visible behavior.',
      '- If a surfboard appears, mention shape, wax state, condition, or age in story or interaction_matrix.',
      '- Show Kai competence through restraint and efficient movement, not lecturing.',
      '- Show Embry autonomy through physical choices: hand placement, rail grip, paddle fatigue, uncertain footing, and commitment or withdrawal near reef.',
      '- Keep dialogue sparse, practical, and character-revealing.',
      '- Avoid generic surf cliches, melodrama, reckless danger, and savior dynamics.',
      '',
      '## Invalid Output',
      ...invalidIf.map((item) => `- ${item}`),
      '',
      '## Complete Example',
      'Example input:',
      JSON.stringify(example.input, null, 2),
      '',
      'Expected output:',
      JSON.stringify(example.expected_output, null, 2),
      '',
      '## Output Format',
      'Output NOTHING but one raw JSON object. No markdown fence, heading, preamble, explanation, or trailing notes.',
      'Start with { and end with }.',
      'Return this exact JSON schema:',
      JSON.stringify(responseContract, null, 2),
    ].join('\n')
    return {
      schema: 'dream.story.prompt_payload.v1',
      rationale: {
        purpose: 'Generate one grounded Phase 02 Embry/Kai story treatment JSON object from Phase 02 story inputs.',
        consumer: 'ux-lab /dream#story Author Console -> /api/tau/dream/story-draft -> Tau story-writer/story-editor loop.',
        why_this_matters: 'Bad output breaks storyboard generation by inventing assets, omitting environment physics, or producing prose that cannot populate the interaction matrix.',
        input: [
          'context.core_idea',
          'context.location',
          'context.environment',
          'context.interaction_rows[]',
          'context.linked_assets[]',
          'author_profile',
        ],
        output: 'JSON object matching response_contract; consumed by Tau story agents and the Phase 02 Story Area.',
        last_reviewed: '2026-07-01 by Graham/Codex',
      },
      metadata: {
        phase: '02',
        timestamp: new Date().toISOString(),
        gate_state: gateState,
      },
      model: {
        provider: 'tau',
        model: 'gpt-5.5',
        reasoning_effort: 'medium',
        temperature: creativity,
      },
      task: {
        kind: storyKind,
        panel_count: panelCount,
        target_duration_seconds: durationSeconds,
        target_story_length_words: targetStoryLengthWords,
        output_format: 'strict_json',
      },
      generation_directives: generationDirectives,
      source_context: sourceContext,
      asset_policy: assetPolicy,
      context: {
        thematic_pivot: 'Autonomy vs. Obligation',
        core_idea: coreIdea,
        location,
        environment,
        interaction_rows: normalizedRows.map((row) => ({
          id: row.id,
          name: row.name,
          objects: row.objects.join(', '),
          environment: row.environment,
          dynamics: row.dynamics,
          note: row.note,
          isComplete: row.is_complete,
          contact_sheet: row.contact_sheet,
        })),
        linked_assets: linkedAssets,
      },
      author_profile: {
        persona_id: writer || null,
        persona: requestedAuthor,
        persona_context: selectedWriter?.description || null,
        creativity_index: creativity,
      },
      response_contract: responseContract,
      output_contract: responseContract,
      validation: {
        deterministic_checks: deterministicChecks,
        invalid_if: invalidIf,
      },
      example,
      messages: [
        {
          role: 'system',
          content: 'You are the Phase 02 Story author for Embry OS. Follow the user prompt exactly. Return only the requested JSON object.',
        },
        {
          role: 'user',
          content: rawPrompt,
        },
      ],
    }
  }

  const generateDraft = async () => {
    const payload = buildStoryPromptPayload()
    setIsGenerating(true)
    updateGenerateStatus('Dispatching Tau story loop...')
    try {
      const response = await fetch('/api/tau/dream/story-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payload }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof data?.error === 'string'
          ? data.error
          : typeof data?.detail === 'string'
            ? data.detail
            : `HTTP ${response.status}`
        throw new Error(message)
      }
      const story = typeof data?.story_contract?.story === 'string' && data.story_contract.story.trim().length > 0
        ? data.story_contract.story.trim()
        : JSON.stringify(data, null, 2)
      updateDraft(story)
      const receipt = typeof data?.manifest_path === 'string' ? data.manifest_path : 'Tau receipt unavailable'
      updateGenerateStatus(`Tau story loop ${data?.status || 'returned'}: ${receipt}`)
    } catch (error) {
      updateGenerateStatus(`Draft failed: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setIsGenerating(false)
    }
  }

  const copyDebugPayload = async () => {
    const payload = buildStoryPromptPayload()
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    setCopyStatus('Copied')
    window.setTimeout(() => setCopyStatus(''), 1800)
  }
  useEffect(() => {
    const handleHeaderCopy = () => { void copyDebugPayload() }
    window.addEventListener('dream:copy-story-payload', handleHeaderCopy)
    return () => window.removeEventListener('dream:copy-story-payload', handleHeaderCopy)
  })
  const storyText = useMemo(() => storyDisplayText(draft), [draft])
  const storyGlossary = useMemo(() => storyEntityGlossary(draft), [draft])
  const selectedWriterForDisplay = writers.find((option) => option.id === writer)
  const writerStylePreview = authorStyleGuide(
    selectedWriterForDisplay?.label || writer || 'unselected_author',
    selectedWriterForDisplay?.description || ''
  )
  return (
    <section data-qid="dream:story:director-console" style={nvis.directorConsole}>
      <div data-qid="dream:story:core-idea" style={nvis.directorIdeaBand}>
        <span style={nvis.directorLabel}><Lightbulb size={12} /> Core Idea</span>
        <p style={nvis.directorIdeaText}>{coreIdea || 'No core idea supplied for this story pass.'}</p>
      </div>
      <div style={nvis.directorControls}>
        <span style={nvis.directorLabel}><UserRound size={12} /> Author</span>
        <div style={nvis.directorCommandColumn}>
          <div style={nvis.directorCommandStrip}>
            <label style={nvis.directorAuthorGroup}>
              <span style={nvis.directorSelectWrap}>
                <select
                  data-qid="dream:story:writer"
                  data-qs-action="DREAM_STORY_WRITER_SELECT"
                  title="Choose author persona"
                  value={writer}
                  onChange={(event) => setWriter(event.target.value)}
                  style={nvis.directorSelect}
                >
                  {writers.length === 0 && <option value="">No memory writers found</option>}
                  {writers.map((option) => (
                    <option key={option.id} value={option.id}>{option.label}</option>
                  ))}
                </select>
                <ChevronDown size={13} style={nvis.directorSelectIcon} />
              </span>
            </label>
            <label style={nvis.directorSliderGroup}>
              <span style={nvis.directorSliderHeader}>
                <span style={nvis.directorLabel}><Gauge size={12} /> Creativity</span>
                <span style={nvis.directorValue}>{creativity.toFixed(1)}</span>
              </span>
              <input
                data-qid="dream:story:creativity"
                data-qs-action="DREAM_STORY_CREATIVITY_SET"
                title="Adjust story creativity"
                aria-label="Adjust story creativity"
                type="range"
                min="0.2"
                max="1.2"
                step="0.1"
                value={creativity}
                onChange={(event) => setCreativity(Number(event.target.value))}
                style={nvis.directorRange}
              />
            </label>
            <label style={nvis.directorNumberGroup}>
              <span style={nvis.directorLabel}><Clapperboard size={12} /> Panels</span>
              <input
                data-qid="dream:story:panel-count"
                data-qs-action="DREAM_STORY_PANEL_COUNT_SET"
                title="Set story panel count"
                aria-label="Set story panel count"
                type="number"
                min="1"
                max="8"
                step="1"
                value={panelCount}
                onChange={(event) => setPanelCount(Math.max(1, Math.min(8, Math.round(Number(event.target.value) || 1))))}
                style={nvis.directorNumberInput}
              />
            </label>
            <label style={nvis.directorNumberGroup}>
              <span style={nvis.directorLabel}><Play size={12} /> Seconds</span>
              <input
                data-qid="dream:story:duration-seconds"
                data-qs-action="DREAM_STORY_DURATION_SET"
                title="Set story duration in seconds"
                aria-label="Set story duration in seconds"
                type="number"
                min="1"
                max="120"
                step="1"
                value={durationSeconds}
                onChange={(event) => setDurationSeconds(Math.max(1, Math.min(120, Math.round(Number(event.target.value) || 10))))}
                style={nvis.directorNumberInput}
              />
            </label>
            <button
              type="button"
              data-qid="dream:story:generate"
              data-qs-action="DREAM_STORY_GENERATE"
              title="Dispatch Phase 02 story prompt payload to Tau"
              disabled={isGenerating}
              onClick={() => { void generateDraft() }}
              style={{
                ...nvis.directorGenerateBtn,
                ...(isGenerating ? nvis.directorBtnDisabled : null),
              }}
            >
              <Sparkles size={14} />
              {isGenerating ? 'Dispatching' : 'Draft Story'}
            </button>
            <button
              type="button"
              data-qid="dream:story:copy-debug-payload"
              title="Copy Phase 02 story prompt payload JSON"
              onClick={() => { void copyDebugPayload() }}
              style={nvis.directorDebugBtn}
            >
              {copyStatus ? <ClipboardCheck size={13} /> : <Copy size={13} />}
              {copyStatus || 'Copy Payload'}
            </button>
          </div>
          <div data-qid="dream:story:author-style" style={nvis.directorInlineStylePreview}>
            <span style={nvis.directorInlineStyleLabel}><FileText size={12} /> Author Style</span>
            <p style={nvis.directorStyleText}>{writerStylePreview}</p>
          </div>
        </div>
      </div>
      {generateStatus && (
        <div data-qid="dream:story:generation-status" style={nvis.directorStatusRow}>
          <span style={nvis.directorLabel}><CheckCircle2 size={12} /> Status</span>
          <span style={nvis.directorStatus}>{compactStoryStatus(generateStatus)}</span>
        </div>
      )}
      <div style={nvis.directorStoryAreaWrap}>
        <span style={nvis.directorLabel}><BookOpen size={12} /> Story Area</span>
        <div style={nvis.directorStoryContent}>
          <div
            data-qid="dream:story:highlighted-canvas"
            title="Generated story with memory and interaction-matrix entity highlighting"
            style={nvis.directorStoryCanvas}
          >
            {storyText
              ? highlightWithGlossary(storyText, storyGlossary)
              : <span style={nvis.directorStoryPlaceholder}>Generate the Phase 02 story beat here.</span>}
          </div>
          <details style={nvis.directorJsonDetails}>
            <summary style={nvis.directorJsonSummary}>Edit JSON payload</summary>
            <textarea
              data-qid="dream:story:draft"
              data-qs-action="DREAM_STORY_DRAFT_EDIT"
              title="Story JSON draft area"
              value={draft}
              onChange={(event) => updateDraft(event.target.value)}
              placeholder="Generated strict story JSON will appear here..."
              style={nvis.directorStoryArea}
            />
          </details>
        </div>
      </div>
    </section>
  )
}

function StoryMatrix({
  stage,
  researchSeed,
  ideaText,
  linkedAssets = [],
}: {
  stage: DreamStage
  researchSeed?: string
  ideaText?: string
  linkedAssets?: LinkedStoryAsset[]
}) {
  const [assetDescriptions, setAssetDescriptions] = useState<Record<string, string>>({})
  const storySetting = useMemo(() => {
    const seed = ideaText || researchSeed || stage.summary || ''
    return inferStoryLocationAndEnvironment(seed, stage.artifacts)
  }, [researchSeed, ideaText, stage.summary, stage.artifacts])

  useEffect(() => {
    let cancelled = false
    const memoryKeys = Array.from(new Set(linkedAssets.map((asset) => asset.memoryKey || asset.id).filter((key) => Boolean(key) && !String(key).startsWith('asset-'))))
    if (memoryKeys.length === 0) {
      setAssetDescriptions({})
      return () => { cancelled = true }
    }
    async function loadAssetDescriptions() {
      try {
        const docs = await memoryByKeysDocuments('persona_memory', memoryKeys)
        if (cancelled) return
        const next: Record<string, string> = {}
        docs.forEach((doc) => {
          const key = String(doc._key ?? '')
          const description = storyAssetDescriptionFromMemoryDocument(doc)
          if (key && description) next[key] = description
        })
        setAssetDescriptions(next)
      } catch {
        if (!cancelled) setAssetDescriptions({})
      }
    }
    void loadAssetDescriptions()
    return () => { cancelled = true }
  }, [linkedAssets])

  const enrichedLinkedAssets = useMemo(() => linkedAssets.map((asset) => {
    const key = asset.memoryKey || asset.id
    return {
      ...asset,
      description: assetDescriptions[key] || asset.description || '',
    }
  }), [linkedAssets, assetDescriptions])

  const entityRows = useMemo<StoryMatrixRow[]>(() => {
    const fromArtifacts = stage.artifacts.filter((a) =>
      a.label.toLowerCase().includes('entity') || a.label.toLowerCase().includes('character') || a.label.toLowerCase().includes('object')
    )
    if (fromArtifacts.length > 0) {
      return fromArtifacts.map((a, i) => ({
        id: `${i}`,
        name: a.label.replace(/\.[^.]+$/, ''),
        objects: a.kind || 'described',
        environment: storySetting.environment,
        dynamics: a.kind || 'present',
        note: `${a.label.replace(/\.[^.]+$/, '')} must be staged against ${storySetting.environment}.`,
        isComplete: isStagePassed(stage),
      }))
    }
    const seed = ideaText || researchSeed || stage.summary || ''
    const extracted: Array<{ name: string; objects: string; dynamics: string; note: string }> = []
    const lower = seed.toLowerCase()
    if (lower.includes('embry')) extracted.push({
      name: 'Embry',
      objects: 'navy rashguard, phone, family obligations, borrowed/older shortboard',
      dynamics: 'Heat and humidity make her physically exposed: sweat, glare, and tired paddling turn autonomy into a bodily choice, not just an idea.',
      note: 'Script/panels should show sweat, squinting, salt on skin, careful hand placement, and fatigue in her paddle cadence before dialogue explains anything.',
    })
    if (lower.includes('kai')) extracted.push({
      name: 'Kai',
      objects: 'black rashguard, phone call, surf ritual, familiar shortboard',
      dynamics: 'Reads the swell while managing heat, glare, and patience; his competence shows in conserving effort instead of forcing the moment.',
      note: 'Stage Kai as physically adapted to the heat: calm breathing, economical paddling, shaded glances at the reef line, and small gestures that guide Embry without lecturing.',
    })
    if (lower.includes('surf') || lower.includes('board') || lower.includes('wave')) {
      extracted.push({
        name: 'Embry surfboard',
        objects: 'White shortboard, performance shape, visibly waxed deck, likely older/borrowed, rail pressure matters over shallow reef.',
        dynamics: 'Humidity and sun soften wax and make footing less certain; the board forces Embry to commit cleanly despite tired arms and slick contact points.',
        note: 'Panel details should include wax smears, sun glare on the deck, hands gripping rails, and foot placement uncertainty as the board reacts to chop and reef proximity.',
      })
      extracted.push({
        name: 'Kai surfboard',
        objects: 'White shortboard with darker underside/rail marks, well-used and waxed, familiar enough for quick reef-line decisions.',
        dynamics: 'A waxed, familiar board lets Kai compensate for heat, chop, and glare; restraint is visible when he waits rather than wasting energy.',
        note: 'Use the board as proof of familiarity: worn rail marks, confident trim angle, efficient turns, and quick corrections under humid, high-glare conditions.',
      })
    }
    if (lower.includes('swell') || lower.includes('wave') || lower.includes('surf')) {
      extracted.push({ name: 'June Swell', objects: 'sets, tide window, wave face', dynamics: 'Creates the timing pressure that makes hesitation and trust visible.', note: 'Panels need repeating set rhythm: quiet water, approaching lump, glare on the face, then a fast decision point.' })
    }
    if (lower.includes('reef') || lower.includes('rock') || lower.includes('lava')) {
      extracted.push({ name: 'Lava Reef', objects: 'sharp rock, shallow line, safe channel', dynamics: 'Turns the environment into a hard boundary rather than background scenery.', note: 'Show the reef as a physical rule: dark shapes below clear water, shallow consequences, and characters adjusting line and timing around it.' })
    }
    if (lower.includes('kona') || lower.includes('coast') || lower.includes('kahalu')) {
      extracted.push({ name: 'Kona Coast', objects: 'bay, local etiquette, reef break', dynamics: 'Holds the scene inside a public place where local rules shape private choices.', note: 'Script beats should include public beach pressure, waiting turns, reading locals, and the contrast between private escape and shared water.' })
    }
    if (extracted.length === 0 && seed) {
      seed.split(/[.!?]+/).forEach((s, i) => {
        const trimmed = s.trim()
        if (trimmed && i < 4) {
          extracted.push({ name: `Beat ${i + 1}`, objects: trimmed.slice(0, 48), dynamics: 'described in context', note: `Translate this beat into physical panel behavior under ${storySetting.environment}.` })
        }
      })
    }
    return extracted.map((e, i) => ({
      ...e,
      environment: storySetting.environment,
      id: `seed-${i}`,
      isComplete: Boolean(e.objects && e.dynamics && e.note && storySetting.environment !== 'MISSING'),
    }))
  }, [storySetting.environment, researchSeed, ideaText, stage])

  const memoryAnchorForEntity = (name: string, id: string) => {
    const lower = name.toLowerCase()
    if (lower.includes('embry')) return 'embry_age19_23_b01_memory_012'
    if (lower.includes('kai')) return 'embry_age15_19_b03_memory_016'
    if (lower.includes('reef') || lower.includes('kona') || lower.includes('swell')) return 'environment_surf_context'
    return id
  }

  return (
    <div style={nvis.matrixCard} data-qid="story-matrix">
      <DirectorConsole
        rows={entityRows}
        location={storySetting.location}
        environment={storySetting.environment}
        gateState={stage.status}
        coreIdea={ideaText || researchSeed || stage.summary || ''}
        linkedAssets={enrichedLinkedAssets}
      />
      <div style={nvis.matrixMetaGrid}>
        <div style={nvis.matrixMetaItem}>
          <span style={nvis.matrixMetaLabel}><MapPin size={12} /> Location</span>
          <span style={nvis.matrixMetaValue}>{storySetting.location}</span>
        </div>
        <div style={nvis.matrixMetaItem}>
          <span style={nvis.matrixMetaLabel}><CloudSun size={12} /> Environment</span>
          <span style={nvis.matrixMetaValue}>{storySetting.environment}</span>
        </div>
      </div>
      <h3 style={nvis.matrixSectionTitle}><Table2 size={12} /> Interaction Matrix</h3>
      <table style={nvis.matrixTable}>
        <thead>
          <tr style={nvis.matrixHeaderRow}>
            <th style={nvis.matrixTh}>Entity</th>
            <th style={nvis.matrixTh}>Objects</th>
            <th style={nvis.matrixTh}>Environment</th>
            <th style={nvis.matrixTh}>Dynamics</th>
            <th style={nvis.matrixTh}>Story Note</th>
            <th style={nvis.matrixTh}>Contact Sheet</th>
            <th style={nvis.matrixTh}>Status</th>
          </tr>
        </thead>
        <tbody>
          {entityRows.length === 0 && (
            <tr><td colSpan={7} style={{ ...nvis.matrixTd, textAlign: 'center', color: '#ff4444' }}>No entities extracted. Story matrix is empty.</td></tr>
          )}
          {entityRows.map((e) => {
            const contactSheet = contactSheetDecisionForStoryRow(e)
            return (
              <tr key={e.id} style={nvis.matrixRow}>
                <td style={nvis.matrixTd}>
                  <span
                    className="entity-link"
                    data-memory-id={memoryAnchorForEntity(e.name, e.id)}
                    aria-label={`${e.name} is grounded by ${memoryAnchorForEntity(e.name, e.id)}`}
                  >
                    {e.name}
                  </span>
                </td>
                <td style={{ ...nvis.matrixTd, color: e.objects ? '#e2e8f0' : '#ff4444' }}>{e.objects || 'MISSING'}</td>
                <td style={{ ...nvis.matrixTd, color: e.environment !== 'MISSING' ? '#e2e8f0' : '#ff4444' }}>{e.environment}</td>
                <td style={{ ...nvis.matrixTd, color: e.dynamics ? '#e2e8f0' : '#ff4444' }}>{e.dynamics || 'MISSING'}</td>
                <td style={{ ...nvis.matrixTd, color: e.note ? '#cbd5e1' : '#ff4444' }}>{e.note || 'MISSING'}</td>
                <td style={nvis.matrixTd}>
                  <span
                    title={contactSheet.rationale}
                    style={contactSheet.required ? nvis.matrixReadyPill : nvis.matrixMutedPill}
                  >
                    {contactSheet.required ? <CheckCircle2 size={12} /> : <CircleDot size={12} />}
                    {contactSheet.required ? 'Yes' : 'No'} · {contactSheet.kind.replace('_', ' ')}
                  </span>
                </td>
                <td style={nvis.matrixTd}>
                  {e.isComplete
                    ? <span style={nvis.matrixReadyPill}><CheckCircle2 size={12} /> Ready</span>
                    : (
                      <button
                        type="button"
                        data-qid={`dream:story:link-residue:${e.id}`}
                        title={`Choose a recalled source for ${e.name}`}
                        onClick={() => { window.location.hash = 'idea' }}
                        style={nvis.matrixPendingPill}
                      >
                        <span style={nvis.pathTraceHop}>PATH_01</span>
                        <ChevronRight size={9} />
                        <span>Source Needed</span>
                        <ChevronRight size={9} />
                        <span style={nvis.pathTraceTarget}>Target</span>
                      </button>
                    )
                  }
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <AssetProvenanceStrip assets={enrichedLinkedAssets} />
    </div>
  )
}

function CrewConsole({
  stage,
  researchSeed,
  ideaText,
  linkedAssets = [],
}: {
  stage: DreamStage
  researchSeed?: string
  ideaText?: string
  linkedAssets?: LinkedStoryAsset[]
}) {
  const storySetting = useMemo(() => inferStoryLocationAndEnvironment(ideaText || researchSeed || stage.summary || '', stage.artifacts), [ideaText, researchSeed, stage.summary, stage.artifacts])
  const [candidates, setCandidates] = useState<CrewPersonaOption[]>([])
  const [storyDraft, setStoryDraft] = useState('')
  const [creativity, setCreativity] = useState(0.4)
  const [producerId, setProducerId] = useState('')
  const [scriptwriterId, setScriptwriterId] = useState('')
  const [directorId, setDirectorId] = useState('')
  const [status, setStatus] = useState('Loading story contract and persona candidates...')
  const [copyStatus, setCopyStatus] = useState('')

  useEffect(() => {
    let cancelled = false
    async function loadCrewContext() {
      try {
        const [candidateItems, storyResponse] = await Promise.all([
          loadCrewPersonaCandidates(),
          fetch('/api/tau/dream/story-draft/latest').then(async (response) => response.ok ? response.json() : null).catch(() => null),
        ])
        if (cancelled) return
        setCandidates(candidateItems)
        const draft = typeof storyResponse?.draft === 'string' ? storyResponse.draft : ''
        setStoryDraft(draft)
        const producer = chooseCrewPersona('producer', candidateItems)
        const scriptwriter = producer ? chooseCrewPersona('scriptwriter', candidateItems, [producer.id]) : null
        const director = producer && scriptwriter ? chooseCrewPersona('director', candidateItems, [producer.id, scriptwriter.id]) : null
        setProducerId((current) => current || producer?.id || '')
        setScriptwriterId((current) => current || scriptwriter?.id || '')
        setDirectorId((current) => current || director?.id || '')
        setStatus(candidateItems.length > 0
          ? `Loaded ${candidateItems.length} persona candidates and ${draft ? 'latest story contract' : 'no latest story contract'}`
          : 'No persona candidates returned from memory')
      } catch (error) {
        if (!cancelled) setStatus(`Crew context failed: ${error instanceof Error ? error.message : String(error)}`)
      }
    }
    void loadCrewContext()
    return () => { cancelled = true }
  }, [])

  const personaById = useMemo(() => new Map(candidates.map((candidate) => [candidate.id, candidate])), [candidates])
  const producer = personaById.get(producerId) ?? null
  const scriptwriter = personaById.get(scriptwriterId) ?? null
  const director = personaById.get(directorId) ?? null
  const storyContract = useMemo(() => storyContractSummaryFromDraft(storyDraft), [storyDraft])
  const productionPackage = useMemo(() => productionTechniquePackage(storyContract, linkedAssets), [storyContract, linkedAssets])

  const crewPayload = useMemo(() => ({
    schema: 'dream.crew.prompt_payload.v1',
    metadata: {
      phase: '03',
      gate_state: stage.status,
      created_at: new Date().toISOString(),
      source_story_phase: '02',
    },
    controls: {
      creativity,
      sequence: ['producer', 'scriptwriter', 'director'],
      selection_policy: 'Select Producer first. Then select Scriptwriter using the story plus selected Producer. Then select Director using the story plus selected Producer and Scriptwriter.',
    },
    source_context: {
      core_idea: ideaText || researchSeed || stage.summary || '',
      story_text: storyContract.story,
      story_contract: storyContract.parsed,
      interaction_matrix: storyContract.interactionMatrix,
      location: storyContract.location || storySetting.location,
      environment: storyContract.environment || storySetting.environment,
      linked_assets: linkedAssets,
    },
    candidate_pool: candidates.map((candidate) => ({
      id: candidate.id,
      name: candidate.label,
      source: candidate.source,
      roles: candidate.roles,
      source_paths: candidate.sourcePaths,
      persona_context: candidate.description,
    })),
    current_manual_overrides: {
      producer: producer ? { id: producer.id, name: producer.label, persona_context: producer.description, thumbnail_path: producer.thumbnailPath, source_paths: producer.sourcePaths } : null,
      scriptwriter: scriptwriter ? { id: scriptwriter.id, name: scriptwriter.label, persona_context: scriptwriter.description, thumbnail_path: scriptwriter.thumbnailPath, source_paths: scriptwriter.sourcePaths } : null,
      director: director ? { id: director.id, name: director.label, persona_context: director.description, thumbnail_path: director.thumbnailPath, source_paths: director.sourcePaths } : null,
    },
    visible_selection_rationales: {
      producer: crewFitRationale('producer', producer, storyContract),
      scriptwriter: producer ? crewFitRationale('scriptwriter', scriptwriter, storyContract) : 'Waiting for Producer selection and rationale.',
      director: producer && scriptwriter ? crewFitRationale('director', director, storyContract) : 'Waiting for Producer and Scriptwriter selections and rationales.',
    },
    cinematic_technique_selector_handoff: {
      skill: 'cinematic-technique-selector',
      purpose: 'After crew roles are selected, choose the DoP/camera/lens/lighting/color Look Lock and Script DNA for downstream storyboard/provider prompts.',
      required_context: ['core_idea', 'story_text', 'interaction_matrix', 'location', 'environment', 'linked_assets', 'producer_selection', 'scriptwriter_selection', 'director_selection'],
      preliminary_look_lock: productionPackage,
      output_required: ['technique_selection.json', 'look_lock', 'script_dna', 'shot_bible', 'continuity_lock'],
    },
    prompts: {
      producer_prompt: rolePrompt('producer', 'the accepted Phase 02 Embry/Kai story contract'),
      scriptwriter_prompt: [
        rolePrompt('scriptwriter', 'the accepted Phase 02 Embry/Kai story contract'),
        producer ? `Selected Producer context: ${producer.label} — ${producer.description}` : 'Selected Producer context is missing and must be resolved first.',
      ].join('\n\n'),
      director_prompt: [
        rolePrompt('director', 'the accepted Phase 02 Embry/Kai story contract'),
        producer ? `Selected Producer context: ${producer.label} — ${producer.description}` : 'Selected Producer context is missing.',
        scriptwriter ? `Selected Scriptwriter context: ${scriptwriter.label} — ${scriptwriter.description}` : 'Selected Scriptwriter context is missing and must be resolved before Director.',
      ].join('\n\n'),
    },
    response_contract: {
      type: 'object',
      additionalProperties: false,
      required: ['producer_selection', 'scriptwriter_selection', 'director_selection', 'quality_checks'],
      properties: {
        producer_selection: { type: 'object', description: 'First selected crew role.' },
        scriptwriter_selection: { type: 'object', description: 'Second selected crew role, conditioned on producer_selection.' },
        director_selection: { type: 'object', description: 'Third selected crew role, conditioned on producer_selection and scriptwriter_selection.' },
        quality_checks: { type: 'object', description: 'Coverage and sequencing checks.' },
      },
    },
  }), [candidates, creativity, director, ideaText, linkedAssets, producer, productionPackage, researchSeed, scriptwriter, stage.status, stage.summary, storyContract, storySetting.environment, storySetting.location])

  useEffect(() => {
    const handleHeaderCopy = () => { void copyCrewPayload() }
    window.addEventListener('dream:copy-crew-payload', handleHeaderCopy)
    return () => window.removeEventListener('dream:copy-crew-payload', handleHeaderCopy)
  })

  const regenerateCrewDefaults = () => {
    const nextProducer = chooseCrewPersona('producer', candidates)
    const nextScriptwriter = nextProducer ? chooseCrewPersona('scriptwriter', candidates, [nextProducer.id]) : null
    const nextDirector = nextProducer && nextScriptwriter ? chooseCrewPersona('director', candidates, [nextProducer.id, nextScriptwriter.id]) : null
    setProducerId(nextProducer?.id || '')
    setScriptwriterId(nextScriptwriter?.id || '')
    setDirectorId(nextDirector?.id || '')
    setStatus(`Regenerated crew prompts: Producer → Scriptwriter → Director from ${candidates.length} candidates`)
  }

  const copyCrewPayload = async () => {
    await navigator.clipboard.writeText(JSON.stringify(crewPayload, null, 2))
    setCopyStatus('Copied')
    window.setTimeout(() => setCopyStatus(''), 1800)
  }

  const roleCard = (role: CrewRole, selected: CrewPersonaOption | null, value: string, onChange: (value: string) => void, disabled = false) => {
    const avoid = role === 'producer'
      ? []
      : role === 'scriptwriter'
        ? [producer?.id].filter(Boolean) as string[]
        : [producer?.id, scriptwriter?.id].filter(Boolean) as string[]
    const options = roleFitCandidates(role, candidates, avoid)
    const thumbUrl = personaThumbnailUrl(selected)
    return (
      <section style={{ ...nvis.dataSpine, ...(disabled ? nvis.crewRoleCardDisabled : null) }}>
        <div style={nvis.spineIconSlot}>
          {thumbUrl ? (
            <img src={thumbUrl} alt={selected?.label ?? role} title={selected?.thumbnailConfidence ? `Thumbnail confidence: ${selected.thumbnailConfidence}` : selected?.label} style={nvis.crewPersonaThumb} />
          ) : (
            <span style={nvis.spineIconCircle}>
              {role === 'producer' ? <Package size={15} /> : role === 'scriptwriter' ? <PencilLine size={15} /> : <Film size={15} />}
            </span>
          )}
        </div>
        <div style={nvis.spineContent}>
          <div style={nvis.crewRoleHeader}>
            <span style={nvis.moduleLabel}>{role === 'scriptwriter' ? 'Scriptwriter' : role}</span>
            <span style={nvis.directorSelectWrap}>
              <select
                data-qid={`dream:crew:${role}`}
                value={value}
                onChange={(event) => onChange(event.target.value)}
                style={nvis.directorSelect}
                title={`Choose ${role}`}
                disabled={disabled}
              >
                {(disabled || options.length === 0) && <option value="">{disabled ? 'Waiting on upstream role' : 'No role-fit candidates'}</option>}
                {options.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>{candidate.label}</option>
                ))}
              </select>
              <ChevronDown size={13} style={nvis.directorSelectIcon} />
            </span>
          </div>
          <p style={nvis.moduleBody}>{selected ? compactCrewText(selected.description, 420) : disabled ? 'This selection activates after the upstream role exists.' : 'No role-fit persona selected from memory.'}</p>
          <p style={nvis.crewRationale}>{crewPayload.visible_selection_rationales[role]}</p>
        </div>
      </section>
    )
  }

  const hasProducer = Boolean(producer)
  const hasScriptwriter = Boolean(scriptwriter)
  const storyPreview = compactCrewText(storyContract.story || 'No accepted story text loaded from Phase 02 yet.', 520)
  const matrixCount = storyContract.interactionMatrix.length
  const crewStep = hasProducer && hasScriptwriter ? 3 : hasProducer ? 2 : 1
  const gateMissing = stage.status.toUpperCase().includes('MISSING')

  return (
    <section data-qid="dream:crew:console" style={nvis.crewConsole}>
      <div style={nvis.crewTopBar}>
        <div>
          <div style={nvis.crewTopMeta}>
            <div style={nvis.directorLabel}><Users size={13} /> Sequential Crew Selection</div>
            <span style={nvis.crewStepPill}>Step {crewStep} of 3</span>
            <span style={{ ...nvis.crewGatePill, ...(gateMissing ? nvis.crewGatePillMissing : nvis.crewGatePillReady) }}>
              {gateMissing ? <AlertTriangle size={12} /> : <CheckCircle2 size={12} />}
              {stage.status}
            </span>
          </div>
          <p style={nvis.crewIntro}>Producer is selected first, then Scriptwriter, then Director. Each prompt receives the full idea, story, interaction matrix, location, environment, and linked assets.</p>
        </div>
        <div style={nvis.crewActions}>
          <label style={nvis.directorSliderGroup}>
            <span style={nvis.directorSliderHeader}>
              <span style={nvis.directorLabel}><Gauge size={12} /> Creativity</span>
              <span style={nvis.directorValue}>{creativity.toFixed(1)}</span>
            </span>
            <input
              data-qid="dream:crew:creativity"
              type="range"
              min="0.0"
              max="1.0"
              step="0.1"
              value={creativity}
              onChange={(event) => setCreativity(Number(event.target.value))}
              style={nvis.directorRange}
            />
          </label>
          <div style={nvis.crewButtonGroup}>
            <button type="button" data-qid="dream:crew:regenerate" onClick={regenerateCrewDefaults} style={nvis.directorGenerateBtn}><RefreshCw size={13} /> Regenerate Crew</button>
            <button type="button" data-qid="dream:crew:copy-payload" onClick={() => { void copyCrewPayload() }} style={nvis.directorDebugBtn}>{copyStatus ? <ClipboardCheck size={13} /> : <Copy size={13} />}{copyStatus || 'Copy Payload'}</button>
          </div>
        </div>
      </div>
      <div style={nvis.contextSummaryBar}>
        <section style={nvis.crewContextCard}>
          <span style={nvis.crewRoleLabel}><Lightbulb size={13} /> Idea</span>
          <p style={nvis.crewContextText}>{compactCrewText(ideaText || researchSeed || stage.summary || 'No core idea loaded.', 360)}</p>
        </section>
        <section style={nvis.crewContextCard}>
          <span style={nvis.crewRoleLabel}><BookOpen size={13} /> Story</span>
          <p style={nvis.crewContextText}>{storyPreview}</p>
        </section>
        <section style={nvis.crewContextCard}>
          <span style={nvis.crewRoleLabel}><Table2 size={13} /> Interaction Matrix</span>
          <p style={nvis.crewContextText}>{matrixCount > 0 ? `${matrixCount} rows collapsed into the copied crew payload.` : 'No interaction matrix rows loaded yet.'}</p>
        </section>
        <section style={nvis.crewContextCard}>
          <span style={nvis.crewRoleLabel}><Images size={13} /> Linked Assets</span>
          <div style={nvis.crewThumbStrip}>
            {linkedAssets.slice(0, 6).map((asset) => (
              <img key={asset.id} src={asset.url} alt={asset.title} title={asset.description || asset.title} style={nvis.crewThumb} />
            ))}
            {linkedAssets.length === 0 && <span style={nvis.crewContextText}>No image thumbnails loaded.</span>}
          </div>
        </section>
      </div>
      <div style={nvis.crewMainWorkspace}>
        <div style={nvis.crewSectionHeader}>Active Crew Selection</div>
        {roleCard('producer', producer, producerId, setProducerId)}
        {roleCard('scriptwriter', scriptwriter, scriptwriterId, setScriptwriterId, !hasProducer)}
        {roleCard('director', director, directorId, setDirectorId, !hasProducer || !hasScriptwriter)}
      </div>
      <div style={nvis.directorStatusRow}>
        <span style={nvis.directorLabel}><CheckCircle2 size={12} /> Status</span>
        <span style={nvis.directorStatus}>{status}</span>
      </div>
      <section style={nvis.crewProductionSection} data-qid="dream:crew:production-technique">
        <span style={nvis.crewRoleLabel}><Wand2 size={13} /> Camera, Lighting, and Look Lock</span>
        <div style={nvis.crewMainWorkspace}>
          <section style={nvis.dataSpine}><div style={nvis.spineIconSlot}><span style={nvis.spineIconCircle}><Camera size={15} /></span></div><div style={nvis.spineContent}><span style={nvis.moduleLabel}>Camera</span><div style={nvis.moduleTitle}>Water-Safe Capture Package</div><p style={nvis.moduleBody}>{productionPackage.camera_package}</p></div></section>
          <section style={nvis.dataSpine}><div style={nvis.spineIconSlot}><span style={nvis.spineIconCircle}><Aperture size={15} /></span></div><div style={nvis.spineContent}><span style={nvis.moduleLabel}>Lens</span><div style={nvis.moduleTitle}>Waterline Realism</div><p style={nvis.moduleBody}>{productionPackage.lens_package}</p></div></section>
          <section style={nvis.dataSpine}><div style={nvis.spineIconSlot}><span style={nvis.spineIconCircle}><Sun size={15} /></span></div><div style={nvis.spineContent}><span style={nvis.moduleLabel}>Lighting</span><div style={nvis.moduleTitle}>Natural Daylight Surf Window</div><p style={nvis.moduleBody}>{productionPackage.lighting_strategy}</p></div></section>
          <section style={nvis.dataSpine}><div style={nvis.spineIconSlot}><span style={nvis.spineIconCircle}><Move3D size={15} /></span></div><div style={nvis.spineContent}><span style={nvis.moduleLabel}>Movement</span><div style={nvis.moduleTitle}>Swell-Timed Camera Logic</div><p style={nvis.moduleBody}>{productionPackage.movement_rules}</p></div></section>
        </div>
      </section>
    </section>
  )
}

function AssetProvenancePreview({ asset }: { asset: LinkedStoryAsset }) {
  const [broken, setBroken] = useState(false)
  const mediaType = dreamInferMediaType(asset.url, asset.mediaType)
  const isImage = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'svg', 'avif'].includes(mediaType)
  const isAudio = ['wav', 'mp3', 'ogg', 'flac', 'm4a'].includes(mediaType)
  const Icon = isAudio ? Volume2 : Film

  if (isImage && !broken) {
    return <img src={asset.url} alt={asset.title} style={nvis.assetThumbImage} onError={() => setBroken(true)} />
  }
  return (
    <span aria-label={isAudio ? 'Audio asset' : 'Video asset'} style={{ ...nvis.scriptAssetFallback, width: '100%', height: '100%' }}>
      <Icon size={18} />
    </span>
  )
}

function AssetProvenanceStrip({ assets }: { assets: LinkedStoryAsset[] }) {
  useRegisterAction('dream:story:asset-preview', {
    app: 'ux-lab',
    action: 'DREAM_STORY_ASSET_PREVIEW',
    label: 'Preview linked visual asset',
    description: 'Open the linked visual asset that grounds a Phase 02 story beat',
  })

  return (
    <section data-qid="dream:story:asset-provenance" style={nvis.assetStrip}>
      <h3 style={nvis.assetStripTitle}><Images size={12} /> Linked Visual Assets</h3>
      {assets.length === 0 ? (
        <div style={nvis.assetStripEmpty}>No linked visual assets yet. Recalled media from Phase 01 appears here after memory extraction.</div>
      ) : (
        <table style={nvis.assetTable}>
          <thead>
            <tr style={nvis.assetTableHeaderRow}>
              <th style={nvis.assetTableTh}>Image</th>
              <th style={nvis.assetTableTh}>Description</th>
              <th style={nvis.assetTableTh}>Source</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((asset) => {
              const description = distinctAssetDescription(asset)
              return <tr key={asset.id} style={nvis.assetTableRow}>
                <td style={nvis.assetTableThumbCell}>
                  <button
                    type="button"
                    data-qid={`dream:story:asset:${asset.id}`}
                    data-qs-action="DREAM_STORY_ASSET_PREVIEW"
                    title={`Preview linked asset: ${asset.title}`}
                    onClick={() => window.open(asset.url, '_blank', 'noopener,noreferrer')}
                    style={nvis.assetThumbButton}
                  >
                    <AssetProvenancePreview asset={asset} />
                  </button>
                </td>
                <td style={nvis.assetTableDescription}>
                  <span style={nvis.assetTableTitle}>{asset.title}</span>
                  {description && <span style={nvis.assetTableCaption}>{description}</span>}
                </td>
                <td style={nvis.assetTableSource}>{asset.memoryKey || asset.source || asset.id}</td>
              </tr>
            })}
          </tbody>
        </table>
      )}
    </section>
  )
}

function VoiceBoard({ stage }: { stage: DreamStage }) {
  const ready = isStagePassed(stage)
  const toneOptions = [
    { value: 'neutral_warm', label: 'Neutral warm' },
    { value: 'calm_precise', label: 'Calm precise' },
    { value: 'careful_concerned', label: 'Careful concerned' },
    { value: 'serious_low_energy', label: 'Serious low energy' },
    { value: 'memory_confident', label: 'Memory confident' },
    { value: 'memory_uncertain', label: 'Memory uncertain' },
    { value: 'curious_searching', label: 'Curious searching' },
    { value: 'playful_light', label: 'Playful light' },
    { value: 'relieved', label: 'Relieved' },
    { value: 'firm_boundary', label: 'Firm boundary' },
    { value: 'identity_clarification', label: 'Identity clarification' },
    { value: 'one_at_a_time_interrupt', label: 'One at a time interrupt' },
    { value: 'deflect_calm', label: 'Deflect calm' },
    { value: 'grief_safe', label: 'Grief safe' },
    { value: 'wait_presence', label: 'Wait presence' },
  ]
  const pauseOptions = [
    { value: '0', label: 'No pause' },
    { value: '250', label: '250ms' },
    { value: '500', label: '500ms' },
    { value: '750', label: '750ms' },
  ]
  const voiceProfiles = useMemo(() => ([
    {
      id: 'embry',
      name: 'Embry',
      role: 'Lead voice',
      thumbnail: '/mnt/storage12tb/media/personas/embry/assets/surfing/embry_surfing_big_island_2024.png',
      refAudio: '/mnt/storage12tb/skills/persona-dream/outputs/horus-embry-tea-void-sparta-r13-regenerated/bakeoff/runs/voice_route_refresh_20260609T0800Z/reference/embry_authorized_ref_30s_8s.wav',
      status: 'Chatterbox reference available',
      defaultText: "Kai, wait. If we paddle now, we're cutting across the lineup.",
    },
    {
      id: 'kai',
      name: 'Kai',
      role: 'Secondary voice',
      thumbnail: '/mnt/storage12tb/media/personas/kai_akana/assets/contact_sheets/kai_akana_character_sheet.png',
      refAudio: '/mnt/storage12tb/skills/persona-dream/outputs/kai-voice-kling-reference-20260703/kai_kling_chatterbox_reference_30s.wav',
      status: '30s Kai reference ready',
      defaultText: "One more set. Watch the reef line, then angle left.",
    },
  ]), [])
  const [auditionText, setAuditionText] = useState<Record<string, string>>(() => Object.fromEntries(voiceProfiles.map((profile) => [profile.id, profile.defaultText])))
  const [tone, setTone] = useState<Record<string, string>>(() => Object.fromEntries(voiceProfiles.map((profile) => [profile.id, 'neutral_warm'])))
  const [pauseBeforeMs, setPauseBeforeMs] = useState<Record<string, string>>(() => Object.fromEntries(voiceProfiles.map((profile) => [profile.id, '250'])))
  const [renderStatus, setRenderStatus] = useState<Record<string, string>>({})

  const playReference = (profile: typeof voiceProfiles[number]) => {
    const url = dreamAssetUrl(profile.refAudio)
    if (!url) return
    const audio = new Audio(url)
    void audio.play()
  }

  const renderDemo = async (profile: typeof voiceProfiles[number]) => {
    const text = (auditionText[profile.id] || '').trim()
    if (!text) {
      setRenderStatus((current) => ({ ...current, [profile.id]: 'Enter audition text first.' }))
      return
    }
    setRenderStatus((current) => ({ ...current, [profile.id]: 'Rendering through Chatterbox...' }))
    try {
      const response = await fetch('/api/projects/dream/voices/audition', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          character: profile.id,
          text,
          refAudioPath: profile.refAudio,
          tone: tone[profile.id] || 'neutral_warm',
          pauseBeforeMs: Number(pauseBeforeMs[profile.id] || 0),
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok || payload?.status !== 'ok' || !payload?.audioUrl) {
        setRenderStatus((current) => ({
          ...current,
          [profile.id]: payload?.error || 'Chatterbox audition failed; server did not return audio.',
        }))
        return
      }
      const delayMs = Number(payload.pauseBeforeMs ?? pauseBeforeMs[profile.id] ?? 0)
      setRenderStatus((current) => ({ ...current, [profile.id]: `Rendered ${payload.durationSeconds ?? 'audio'}s demo${delayMs ? ` with ${delayMs}ms pause` : ''}.` }))
      const audio = new Audio(payload.audioUrl)
      window.setTimeout(() => { void audio.play() }, Number.isFinite(delayMs) ? delayMs : 0)
    } catch (error) {
      setRenderStatus((current) => ({
        ...current,
        [profile.id]: error instanceof Error ? error.message : 'Chatterbox audition request failed.',
      }))
    }
  }

  return (
    <div data-qid="voice-plugin" style={nvis.voicePlugin}>
      <div style={nvis.voiceHeaderRow}>
        <span style={nvis.voiceMeta}><Mic2 size={13} /> Chatterbox / provider voice references</span>
        <span style={ready ? nvis.matrixReadyPill : nvis.matrixMutedPill}>{ready ? 'Voice gate ready' : 'Voice gate pending'}</span>
      </div>
      {voiceProfiles.map((profile) => {
        const status = renderStatus[profile.id]
        return (
          <div key={profile.id} data-qid={`dream:voice-card:${profile.id}`} style={nvis.voiceChannelCard}>
            <div style={nvis.voicePortraitFrame}>
              <img src={dreamAssetUrl(profile.thumbnail)} alt={`${profile.name} thumbnail`} style={nvis.voicePortrait} />
            </div>
            <div style={nvis.voiceCardBody}>
              <div style={nvis.voiceCardTopline}>
                <span style={nvis.voiceName}>{profile.name}</span>
                <span style={nvis.voiceRole}>{profile.role}</span>
              </div>
              <span style={nvis.voiceStatus}>{profile.status}</span>
              <textarea
                style={nvis.voiceAuditionTextarea}
                value={auditionText[profile.id] || ''}
                onChange={(event) => setAuditionText((current) => ({ ...current, [profile.id]: event.target.value }))}
                placeholder={`Type ${profile.name}'s demo line...`}
                data-qid={`dream:voice:text:${profile.id}`}
                data-qs-action="DREAM_VOICE_AUDITION_TEXT"
              />
              <div style={nvis.voicePerformanceRow}>
                <label style={nvis.voiceControlLabel}>
                  Tone
                  <select
                    value={tone[profile.id] || 'neutral_warm'}
                    onChange={(event) => setTone((current) => ({ ...current, [profile.id]: event.target.value }))}
                    style={nvis.voiceSelect}
                    data-qid={`dream:voice:tone:${profile.id}`}
                    data-qs-action="DREAM_VOICE_TONE"
                  >
                    {toneOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
                <label style={nvis.voiceControlLabel}>
                  Playback pause
                  <select
                    value={pauseBeforeMs[profile.id] || '0'}
                    onChange={(event) => setPauseBeforeMs((current) => ({ ...current, [profile.id]: event.target.value }))}
                    style={nvis.voiceSelect}
                    data-qid={`dream:voice:pause:${profile.id}`}
                    data-qs-action="DREAM_VOICE_PAUSE"
                  >
                    {pauseOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
              </div>
              <div style={nvis.voiceActionRow}>
                <button
                  type="button"
                  data-qid={`dream:voice-reference:${profile.id}`}
                  data-qs-action="DREAM_VOICE_PLAY_REFERENCE"
                  title={`Play ${profile.name} reference sample`}
                  onClick={() => playReference(profile)}
                  style={nvis.voiceGhostBtn}
                >
                  <Volume2 size={14} />
                  Reference
                </button>
                <button
                  type="button"
                  data-qid={`dream:voice-render:${profile.id}`}
                  data-qs-action="DREAM_VOICE_RENDER_DEMO"
                  title={`Render ${profile.name} demo through Chatterbox`}
                  onClick={() => { void renderDemo(profile) }}
                  style={nvis.voicePrimaryBtn}
                >
                  <Play size={13} />
                  Demo Voice
                </button>
                {status && <span style={nvis.voiceRenderStatus}>{status}</span>}
              </div>
            </div>
          </div>
        )
      })}
      <div style={nvis.voiceCommitRow}>
        <span style={nvis.voiceMeta}>Kai reference is shared by Chatterbox local ref_audio and provider voice upload.</span>
        <button
          type="button"
          data-qid="dream:voice-commit"
          data-qs-action="DREAM_VOICE_COMMIT"
          disabled={!ready}
          style={{ ...nvis.voiceCommitBtn, ...(!ready ? nvis.disabled : null) }}
        >
          <RotateCcw size={12} />
          Commit
        </button>
      </div>
    </div>
  )
}

function ScriptCoverageTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return null
  return (
    <div data-qid="dream:script:interaction-matrix-coverage" style={nvis.scriptCoverage}>
      <div style={nvis.scriptCoverageTitle}><Table2 size={12} /> Interaction Matrix Coverage</div>
      <div style={nvis.scriptCoverageGrid}>
        {rows.map((row, index) => {
          const entity = String(row.entity ?? row.name ?? row.source_seed_id ?? `row-${index + 1}`)
          const described = row.described_in_script === true || row.covered === true || row.covered_in_script === true
          const objects = Array.isArray(row.objects_used) ? row.objects_used : Array.isArray(row.objects) ? row.objects : []
          return (
            <div key={`${String(row.source_seed_id ?? entity)}-${index}`} style={nvis.scriptCoverageRow}>
              <div style={nvis.scriptCoverageMeta}>
                <span style={nvis.scriptElementTag}>{String(row.source_seed_id ?? `seed-${index}`)}</span>
                <span style={described ? nvis.scriptCoverageReady : nvis.scriptCoverageMissing}>{described ? 'Described' : 'Needs detail'}</span>
              </div>
              <div style={nvis.scriptCoverageEntity}>{entity}</div>
              <div style={nvis.scriptCoverageText}>{String(row.environment_interaction ?? row.script_evidence ?? row.script_function ?? row.dynamics ?? '')}</div>
              {!described && <div style={nvis.scriptCoverageBlocker}>Reviewer must route this back to script-writer until described or max retries is exceeded.</div>}
              {objects.length > 0 && <div style={nvis.scriptCoverageObjects}>{objects.map((object) => String(object)).join(', ')}</div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ScriptTable({
  draft,
  storyContract,
  durationSeconds,
}: {
  draft: string
  storyContract: ReturnType<typeof storyContractSummaryFromDraft>
  durationSeconds: number
}) {
  const contract = scriptContractFromDraft(draft)
  const script = scriptStringFromContract(contract, draft)
  const rows = splitScriptIntoRows(script)
  const coverageRows = scriptEntityRows(contract, storyContract)
  const glossary = scriptGlossaryFromContract(contract, storyContract)

  if (!script) {
    return <span style={nvis.directorStoryPlaceholder}>Generate the Phase 06 screenplay script here.</span>
  }

  const rowDuration = rows.length > 0 ? durationSeconds / rows.length : durationSeconds
  const durationLabel = (index: number) => {
    const start = index * rowDuration
    const end = Math.min(durationSeconds, (index + 1) * rowDuration)
    return `${start.toFixed(1)}-${end.toFixed(1)}s`
  }

  return (
    <div data-qid="dream:script:structured-table" style={nvis.scriptTableShell}>
      {rows.map((row, index) => {
        const status = scriptCoverageStatusForRow(index, coverageRows)
        const statusStyle = status === 'verified'
          ? nvis.scriptStatusNodeVerified
          : status === 'failed'
            ? nvis.scriptStatusNodeFailed
            : nvis.scriptStatusNodePending
        return (
          <div
            key={`${row.element}-${index}`}
            style={{
              ...nvis.scriptTableRow,
              ...(status === 'failed' ? nvis.scriptTableRowFailed : null),
            }}
          >
            <span
              data-qid={`dream:script:status-node:${index}`}
              data-status={status}
              title={scriptCoverageStatusTitle(status, index, coverageRows)}
              style={{ ...nvis.scriptStatusNodeBase, ...statusStyle }}
            />
            <div style={nvis.scriptBeatHeader}>
              <span style={nvis.scriptElementTag}>{row.element}</span>
              <span style={nvis.scriptDurationTag}>{durationLabel(index)}</span>
            </div>
            <div style={nvis.scriptContentBlock}>{highlightWithGlossary(row.content, glossary)}</div>
            <div style={nvis.scriptNotesCell}>{coverageNoteForScriptRow(index, coverageRows)}</div>
          </div>
        )
      })}
      <ScriptCoverageTable rows={coverageRows} />
    </div>
  )
}

function ScriptAssetTile({ asset }: { asset: LinkedStoryAsset }) {
  const [broken, setBroken] = useState(false)
  const mediaType = dreamInferMediaType(asset.url, asset.mediaType)
  const isImage = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'avif'].includes(mediaType)
  const isVideo = ['mp4', 'mov', 'webm', 'avi'].includes(mediaType)
  const isAudio = ['wav', 'mp3', 'ogg'].includes(mediaType)
  const Icon = isAudio ? Volume2 : isVideo ? Film : isImage ? Image : FileText
  const label = asset.title || asset.id
  return (
    <button
      type="button"
      data-qid={`dream:script:asset:${asset.id}`}
      title={`${label}${asset.description ? ` — ${asset.description}` : ''}`}
      onClick={() => asset.url && window.open(asset.url, '_blank', 'noopener,noreferrer')}
      style={nvis.scriptAssetTile}
    >
      {isImage && asset.url && !broken ? (
        <img
          src={asset.url}
          alt={label}
          style={nvis.scriptAssetThumb}
          onError={() => setBroken(true)}
        />
      ) : (
        <span style={nvis.scriptAssetFallback}>
          <Icon size={18} />
        </span>
      )}
      <span style={nvis.scriptAssetTitle}>{compactCrewText(label, 58)}</span>
      <span style={nvis.scriptAssetMeta}>{isAudio ? 'audio' : isVideo ? 'video' : isImage ? 'image' : 'text'}</span>
    </button>
  )
}

function ScriptConsole({
  stage,
  allStages,
  researchSeed,
  ideaText,
  linkedAssets,
}: {
  stage: DreamStage
  allStages: DreamStage[]
  researchSeed?: string
  ideaText?: string
  linkedAssets: LinkedStoryAsset[]
}) {
  const storyStage = allStages.find((s) => s.id === '02')
  const crewStage = allStages.find((s) => s.id === '03')
  const contactStage = allStages.find((s) => s.id === '04')
  const voicesStage = allStages.find((s) => s.id === '05')
  const [creativity, setCreativity] = useState(0.5)
  const [sceneCount, setSceneCount] = useState(1)
  const [targetPages, setTargetPages] = useState(1)
  const [durationSeconds, setDurationSeconds] = useState(10)
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState('')
  const [storyDraftSource, setStoryDraftSource] = useState('')
  const [copyStatus, setCopyStatus] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)

  useEffect(() => {
    let cancelled = false
    try {
      setDraft(localStorage.getItem(DREAM_SCRIPT_DRAFT_STORAGE_KEY) || '')
      setStatus(localStorage.getItem(DREAM_SCRIPT_STATUS_STORAGE_KEY) || '')
      const cachedStory = localStorage.getItem(DREAM_STORY_DRAFT_STORAGE_KEY) || ''
      if (cachedStory) setStoryDraftSource(cachedStory)
    } catch {
      // Local storage is only a cache for the visible draft.
    }
    fetch('/api/tau/dream/story-draft/latest')
      .then(async (response) => {
        if (!response.ok) return null
        return response.json()
      })
      .then((data) => {
        if (cancelled || !data || typeof data.draft !== 'string' || data.draft.trim().length === 0) return
        setStoryDraftSource(data.draft)
        try {
          localStorage.setItem(DREAM_STORY_DRAFT_STORAGE_KEY, data.draft)
        } catch {
          // The fetched Tau artifact remains in React state.
        }
      })
      .catch(() => {
        // Missing latest-story endpoint keeps the script pane fail-closed.
      })
    fetch('/api/tau/dream/script-draft/latest')
      .then(async (response) => {
        if (!response.ok) return null
        return response.json()
      })
      .then((data) => {
        if (cancelled || !data) return
        const nextDraft = data.script_contract && typeof data.script_contract === 'object'
          ? JSON.stringify(data.script_contract, null, 2)
          : typeof data.draft === 'string'
            ? data.draft
            : ''
        if (nextDraft.trim().length === 0) return
        setDraft(nextDraft)
        const nextStatus = typeof data.status === 'string' ? `Tau script loop ${data.status}` : 'Tau script loaded'
        setStatus(nextStatus)
        try {
          localStorage.setItem(DREAM_SCRIPT_DRAFT_STORAGE_KEY, nextDraft)
          localStorage.setItem(DREAM_SCRIPT_STATUS_STORAGE_KEY, nextStatus)
        } catch {
          // The fetched Tau artifact remains in React state.
        }
      })
      .catch(() => {
        // Missing latest-script endpoint leaves the pane ready for manual generation.
      })
    return () => { cancelled = true }
  }, [])

  const updateDraft = (nextDraft: string) => {
    setDraft(nextDraft)
    try {
      if (nextDraft) localStorage.setItem(DREAM_SCRIPT_DRAFT_STORAGE_KEY, nextDraft)
      else localStorage.removeItem(DREAM_SCRIPT_DRAFT_STORAGE_KEY)
    } catch {
      // Keep React state authoritative when local storage is unavailable.
    }
  }

  const updateStatus = (nextStatus: string) => {
    setStatus(nextStatus)
    try {
      if (nextStatus) localStorage.setItem(DREAM_SCRIPT_STATUS_STORAGE_KEY, nextStatus)
      else localStorage.removeItem(DREAM_SCRIPT_STATUS_STORAGE_KEY)
    } catch {
      // Visible status remains in React state.
    }
  }

  const storyDraft = storyDraftSource
  const storyContract = storyContractSummaryFromDraft(storyDraft)
  const storySetting = inferStoryLocationAndEnvironment(ideaText || researchSeed || storyStage?.summary || stage.summary || '', stage.artifacts)

  const buildScriptPayload = () => {
    const sourceContext = {
      core_idea: ideaText || researchSeed || stage.summary || '',
      story_text: storyContract.story || storyStage?.summary || '',
      story_contract: storyDraft ? parseStoryDraftJson(storyDraft) : null,
      interaction_matrix: storyContract.interactionMatrix,
      location: storySetting.location,
      environment: storySetting.environment,
      linked_assets: linkedAssets.map((asset) => ({
        id: asset.id,
        title: asset.title,
        url: asset.url,
        description: asset.description || '',
        source: asset.source || asset.memoryKey || asset.id,
        media_type: asset.mediaType || '',
      })),
      contact_sheets: {
        artifacts: stageArtifactSummary(contactStage),
        images: stageImageSummary(contactStage),
      },
      voices: {
        artifacts: stageArtifactSummary(voicesStage),
        images: stageImageSummary(voicesStage),
      },
      crew: {
        artifacts: stageArtifactSummary(crewStage),
        images: stageImageSummary(crewStage),
      },
    }
    const responseContract = {
      type: 'object',
      additionalProperties: false,
      required: [
        'script',
        'scene_count',
        'target_pages',
        'dialogue_blocks',
        'action_blocks',
        'environment_continuity',
        'voice_direction',
        'asset_usage',
        'interaction_matrix_coverage',
        'quality_checks',
      ],
      properties: {
        script: {
          type: 'string',
          description: 'Screenplay-formatted script text for the requested scene/page count.',
        },
        scene_count: { type: 'number' },
        target_pages: { type: 'number' },
        dialogue_blocks: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['character', 'line', 'tone', 'source_context'],
            properties: {
              character: { type: 'string' },
              line: { type: 'string' },
              tone: { type: 'string' },
              source_context: { type: 'string' },
            },
          },
        },
        action_blocks: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['beat', 'physical_action', 'environment_driver'],
            properties: {
              beat: { type: 'string' },
              physical_action: { type: 'string' },
              environment_driver: { type: 'string' },
            },
          },
        },
        environment_continuity: {
          type: 'array',
          items: { type: 'string' },
        },
        voice_direction: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['character', 'delivery', 'pause_or_tone_note'],
            properties: {
              character: { type: 'string' },
              delivery: { type: 'string' },
              pause_or_tone_note: { type: 'string' },
            },
          },
        },
        asset_usage: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['asset_id', 'used_for', 'script_continuity_note'],
            properties: {
              asset_id: { type: 'string' },
              used_for: { type: 'string' },
              script_continuity_note: { type: 'string' },
            },
          },
        },
        interaction_matrix_coverage: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['source_seed_id', 'covered_in_script', 'script_function', 'script_evidence', 'environmental_realism_evidence', 'missing_script_details'],
            properties: {
              source_seed_id: { type: 'string' },
              covered_in_script: { type: 'boolean', const: true },
              script_function: { type: 'string' },
              script_evidence: { type: 'string', description: 'Exact script line, beat, or sentence proving this row is described.' },
              environmental_realism_evidence: { type: 'string', description: 'Concrete visible evidence for how heat, humidity, water, reef, light, fatigue, or etiquette affects the entity/object.' },
              missing_script_details: {
                type: 'array',
                maxItems: 0,
                items: { type: 'string' },
                description: 'Must be empty. Any item means script-reviewer must return NEEDS_CHANGES and route back to script-writer.',
              },
            },
          },
        },
        quality_checks: {
          type: 'object',
          additionalProperties: false,
          required: [
            'uses_phase02_story',
            'covers_interaction_matrix',
            'uses_contact_sheet_context',
            'uses_voice_context',
            'does_not_invent_unprovided_assets',
          ],
          properties: {
            uses_phase02_story: { type: 'boolean' },
            covers_interaction_matrix: { type: 'boolean' },
            uses_contact_sheet_context: { type: 'boolean' },
            uses_voice_context: { type: 'boolean' },
            does_not_invent_unprovided_assets: { type: 'boolean' },
          },
        },
      },
    }
    const prompt = [
      'Create the Phase 06 screenplay script for persona-dream.',
      '',
      'Use the accepted prior pane artifacts as the only source of truth.',
      'The script must be generated by the Tau DAG in tau_orchestration. Do not run this as a one-shot prompt.',
      'Tau must dispatch script-writer first, then script-reviewer. The reviewer may either PASS or route back to script-writer while attempts remain. If attempts are exhausted, return BLOCKED_MAX_RETRIES with the failed source_seed_id rows.',
      '',
      'Do not create a new story. Adapt the Phase 02 story contract into screenplay form.',
      'Every character, object, and environmental pressure used by the story must remain explainable through the interaction matrix.',
      'Reviewer gate: every source_context.interaction_matrix row must have one matching interaction_matrix_coverage row with covered_in_script=true, non-empty script_evidence, non-empty environmental_realism_evidence, and missing_script_details=[].',
      'If any interaction_matrix_coverage row has covered_in_script=false, missing_script_details length > 0, or vague evidence, script-reviewer must return NEEDS_CHANGES and Tau must route back to script-writer while attempts remain.',
      'Reject PASS if Embry, Kai, either surfboard, June Swell, Lava Reef, Kona Coast, heat, humidity, glare, saltwater, softened wax, fatigue, or local etiquette are only mentioned but not visibly described in the script.',
      'Reject PASS if the script includes timestamp notation in the screenplay body. Duration belongs in metadata/table rows, not in screenplay text.',
      'Reject PASS if $extract-entities coverage cannot map highlighted character/object/environment mentions back to source_context.interaction_matrix.',
      'Use voice context for delivery notes, but do not invent unavailable voices.',
      'Use contact sheets and linked assets as continuity references, not as extra plot.',
      '',
      '<source_context>',
      JSON.stringify(sourceContext, null, 2),
      '</source_context>',
      '',
      '<response_contract>',
      JSON.stringify(responseContract, null, 2),
      '</response_contract>',
      '',
      'Return one raw JSON object only. No markdown. No comments. No keys outside the response contract.',
    ].join('\n')
    const dagHashMaterial = {
      phase: '06',
      task: {
        kind: 'phase_06_script',
        scene_count: sceneCount,
        target_pages: targetPages,
        duration_seconds: durationSeconds,
      },
      source_context: sourceContext,
      response_contract: responseContract,
      creator_agent: 'script-writer',
      reviewer_agent: 'script-reviewer',
      max_retries: 2,
    }
    const dagGoalHash = `fnv1a32:${fnv1a32(stableJson(dagHashMaterial))}`
    return {
      schema: 'dream.script.prompt_payload.v1',
      metadata: {
        phase: '06',
        gate_state: stage.status,
        timestamp: new Date().toISOString(),
      },
      tau_orchestration: {
        required: true,
        schema: 'tau.dag_contract.v1',
        dag_id: 'persona-dream-phase-06-script',
        goal: {
          goal_id: 'persona-dream-phase-06-script',
          goal_version: 1,
          goal_hash: dagGoalHash,
          goal_hash_algorithm: 'fnv1a32',
          goal_hash_material: dagHashMaterial,
        },
        target: {
          project: 'persona-dream',
          pane: '06 Script',
          route: '/dream#script',
          output_artifact: 'script_contract.json',
          output_artifact_schema: 'dream.script.contract.v1',
          artifact_root: 'experiments/goal-locked-subagents/proofs/persona-dream-script-ui-dispatch/**/run',
          memory_persistence: {
            required: true,
            collections: ['persona_dream_projects', 'persona_memory'],
            graph_edges: ['project->script_contract', 'script_contract->interaction_matrix_rows', 'script_contract->linked_assets'],
            indexes: ['ArangoSearch BM25 View', 'Arango graph traversal', 'Qdrant semantic vectors'],
          },
        },
        limits: {
          max_iterations: 2,
          max_retries: 2,
          default_timeout_seconds: 300,
          fail_fast: true,
        },
        entry_node: 'script-writer',
        terminal_nodes: ['human'],
        nodes: [
          {
            id: 'script-writer',
            agent: 'script-writer',
            executor: 'local',
            role: 'creator',
            max_attempts: 2,
            input_refs: ['source_context', 'response_contract', 'messages[1].content'],
            output: 'strict JSON matching response_contract',
            required_evidence: [
              'script_contract.json',
              'entity_environment_script_table.json',
              'interaction_matrix_coverage.json',
              'realism_contract.json',
              'persona_memory_grounding_ledger.json',
            ],
          },
          {
            id: 'script-reviewer',
            agent: 'script-reviewer',
            executor: 'local',
            role: 'reviewer',
            max_attempts: 2,
            input_refs: ['script-writer.output', 'source_context.interaction_matrix', 'response_contract'],
            output: 'PASS_SCRIPT_CONTRACT or NEEDS_CHANGES with failed source_seed_id rows',
            required_evidence: [
              'script-reviewer-verdict.json',
              'validate_script_contract.json',
              'interaction_matrix_coverage_verdict.json',
              'extract_entities_coverage.json',
              'memory_persistence_receipt.json',
            ],
          },
          {
            id: 'human',
            agent: 'human',
            executor: 'human',
            role: 'terminal',
            receives: ['PASS_SCRIPT_CONTRACT', 'BLOCKED_MAX_RETRIES'],
          },
        ],
        edges: [
          { from: 'script-writer', to: 'script-reviewer' },
          {
            from: 'script-reviewer',
            to: 'script-writer',
            condition: 'NEEDS_CHANGES and script-writer.attempts_remaining > 0',
            repair_payload: 'failed source_seed_id rows, missing_script_details, missing entity/environment evidence',
          },
          {
            from: 'script-reviewer',
            to: 'human',
            condition: 'PASS_SCRIPT_CONTRACT or BLOCKED_MAX_RETRIES',
          },
        ],
        required_evidence: [
          'script_contract.json',
          'script-reviewer-verdict.json',
          'validate_script_contract.json',
          'entity_environment_script_table.json',
          'interaction_matrix_coverage.json',
          'extract_entities_coverage.json',
          'memory_persistence_receipt.json',
        ],
        pass_condition: 'script-reviewer returns PASS_SCRIPT_CONTRACT and every interaction_matrix_coverage row has covered_in_script=true, non-empty script_evidence, non-empty environmental_realism_evidence, and missing_script_details=[]',
        stop_condition: 'PASS_SCRIPT_CONTRACT, or max_retries is exceeded and Tau returns BLOCKED_MAX_RETRIES with failed source_seed_id rows',
        fail_closed_on: [
          'missing_goal_hash',
          'missing_required_evidence',
          'malformed_script_contract',
          'missing_interaction_matrix_row',
          'covered_in_script_false',
          'missing_script_evidence',
          'missing_environmental_realism_evidence',
          'missing_script_details_non_empty',
          'missing_extract_entities_coverage',
          'missing_memory_persistence_receipt',
          'screenplay_body_contains_timestamps',
          'entity_mentioned_without_description',
          'max_attempts_exceeded',
        ],
      },
      model: {
        provider: 'tau',
        default_creator_model: 'gpt-5.5',
        reasoning_effort: 'medium',
        reviewer_model: 'moonshotai/Kimi-K2.6-TEE',
        creativity,
      },
      task: {
        kind: 'phase_06_script',
        scene_count: sceneCount,
        target_pages: targetPages,
        duration_seconds: durationSeconds,
        output_format: 'strict_json',
      },
      source_context: sourceContext,
      response_contract: responseContract,
      messages: [
        {
          role: 'system',
          content: 'You are the Phase 06 script creator/reviewer loop for persona-dream. Return strict JSON only.',
        },
        {
          role: 'user',
          content: prompt,
        },
      ],
    }
  }

  const copyPayload = async () => {
    await navigator.clipboard.writeText(JSON.stringify(buildScriptPayload(), null, 2))
    setCopyStatus('Copied')
    window.setTimeout(() => setCopyStatus(''), 1800)
  }

  const generateScript = async () => {
    const payload = buildScriptPayload()
    setIsGenerating(true)
    updateStatus('Dispatching Tau script loop...')
    try {
      const response = await fetch('/api/tau/dream/script-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payload }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof data?.error === 'string'
          ? data.error
          : typeof data?.detail === 'string'
            ? data.detail
            : `HTTP ${response.status}`
        if (message === 'tau_script_runner_missing') {
          const blockedPayload = {
            status: 'BLOCKED',
            blocker: message,
            detail: typeof data?.detail === 'string' ? data.detail : 'Tau Phase 06 script runner is missing.',
            tau_issue: typeof data?.tau_issue === 'string' ? data.tau_issue : 'https://github.com/grahama1970/tau/issues/47',
            mocked: data?.mocked === true,
            live: data?.live === true,
            out_dir: typeof data?.out_dir === 'string' ? data.out_dir : null,
            artifacts: data?.artifacts ?? null,
            counts: data?.counts ?? null,
          }
          updateDraft(JSON.stringify(blockedPayload, null, 2))
          updateStatus(`Blocked: ${message} · ${blockedPayload.tau_issue}`)
          return
        }
        throw new Error(message)
      }
      const scriptDraft = data?.script_contract && typeof data.script_contract === 'object'
        ? JSON.stringify(data.script_contract, null, 2)
        : typeof data?.script_contract?.script === 'string' && data.script_contract.script.trim().length > 0
          ? data.script_contract.script.trim()
          : JSON.stringify(data, null, 2)
      updateDraft(scriptDraft)
      updateStatus(`Tau script loop ${data?.status || 'returned'}`)
    } catch (error) {
      updateStatus(`Script failed: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setIsGenerating(false)
    }
  }

  const matrixCount = storyContract.interactionMatrix.length

  return (
    <section data-qid="dream:script:console" style={nvis.crewConsole}>
      <div style={nvis.crewTopBar}>
        <div style={nvis.crewTopMeta}>
          <p data-qid="dream:script:phase-description" style={nvis.scriptPhaseDescription}>
            Generate screenplay JSON from the accepted idea, Phase 02 story, interaction matrix, crew choices, contact sheets, voices, and linked assets.
          </p>
        </div>
        <div style={nvis.crewActions}>
          <label style={nvis.directorSliderGroup}>
            <span style={nvis.directorSliderHeader}>
              <span style={nvis.directorLabel}><Gauge size={12} /> Creativity</span>
              <span style={nvis.directorValue}>{creativity.toFixed(1)}</span>
            </span>
            <input
              data-qid="dream:script:creativity"
              title="Adjust script creativity"
              type="range"
              min="0.2"
              max="1.2"
              step="0.1"
              value={creativity}
              onChange={(event) => setCreativity(Number(event.target.value))}
              style={nvis.directorRange}
            />
          </label>
          <label style={nvis.directorNumberGroup}>
            <span style={nvis.directorLabel}><Clapperboard size={12} /> Scenes</span>
            <input
              data-qid="dream:script:scene-count"
              title="Set script scene count"
              type="number"
              min="1"
              max="8"
              value={sceneCount}
              onChange={(event) => setSceneCount(Math.max(1, Math.min(8, Math.round(Number(event.target.value) || 1))))}
              style={nvis.directorNumberInput}
            />
          </label>
          <label style={nvis.directorNumberGroup}>
            <span style={nvis.directorLabel}><FileText size={12} /> Pages</span>
            <input
              data-qid="dream:script:target-pages"
              title="Set target script pages"
              type="number"
              min="1"
              max="20"
              value={targetPages}
              onChange={(event) => setTargetPages(Math.max(1, Math.min(20, Math.round(Number(event.target.value) || 1))))}
              style={nvis.directorNumberInput}
            />
          </label>
          <label style={nvis.directorNumberGroup}>
            <span style={nvis.directorLabel}><Play size={12} /> Duration</span>
            <input
              data-qid="dream:script:duration-seconds"
              title="Set target script duration in seconds"
              type="number"
              min="1"
              max="180"
              value={durationSeconds}
              onChange={(event) => setDurationSeconds(Math.max(1, Math.min(180, Math.round(Number(event.target.value) || 10))))}
              style={nvis.directorNumberInput}
            />
            <span style={nvis.directorValue}>sec</span>
          </label>
        </div>
      </div>

      <div style={nvis.scriptPayloadGroup}>
        <section style={nvis.scriptPayloadCard}>
          <span style={nvis.scriptPayloadLabel}><Lightbulb size={13} /> Idea</span>
          <p style={nvis.scriptPayloadContent}>{compactCrewText(ideaText || researchSeed || stage.summary || 'No core idea loaded.', 300)}</p>
        </section>
        <section style={nvis.scriptPayloadCard}>
          <span style={nvis.scriptPayloadLabel}><BookOpen size={13} /> Story</span>
          <p style={nvis.scriptPayloadContent}>{compactCrewText(storyContract.story || storyStage?.summary || 'No accepted Phase 02 story loaded.', 360)}</p>
        </section>
        <section style={nvis.scriptPayloadCard}>
          <span style={nvis.scriptPayloadLabel}><Table2 size={13} /> Matrix</span>
          <p style={nvis.scriptPayloadContent}>{matrixCount > 0 ? `${matrixCount} interaction rows included in the script payload.` : 'No interaction matrix rows loaded from Phase 02.'}</p>
        </section>
        <section style={nvis.scriptPayloadCard}>
          <span style={nvis.crewRoleLabel}><Images size={13} /> Assets</span>
          <div style={nvis.scriptAssetGrid}>
            {linkedAssets.slice(0, 6).map((asset) => (
              <ScriptAssetTile key={asset.id} asset={asset} />
            ))}
            {linkedAssets.length === 0 && <span style={nvis.crewContextText}>No linked assets loaded.</span>}
          </div>
        </section>
      </div>

      {status && (
        <div data-qid="dream:script:status" style={nvis.directorStatusRow}>
          <span style={nvis.directorLabel}><CheckCircle2 size={12} /> Status</span>
          <span style={nvis.directorStatus}>{status}</span>
        </div>
      )}

      <div style={nvis.scriptStoryAreaWrap}>
        <div style={nvis.scriptSectionHeader}>
          <span style={nvis.scriptSectionRule} />
          <span style={nvis.scriptSectionTitle}><FileText size={13} /> Script Area</span>
          <span style={nvis.scriptSectionRuleWide} />
        </div>
        <div style={nvis.directorStoryContent}>
          <div data-qid="dream:script:canvas" style={nvis.directorStoryCanvas}>
            <ScriptTable draft={draft} storyContract={storyContract} durationSeconds={durationSeconds} />
          </div>
          <details style={nvis.directorJsonDetails}>
            <summary style={nvis.directorJsonSummary}>Edit Script JSON</summary>
            <textarea
              data-qid="dream:script:draft"
              title="Script JSON draft area"
              value={draft}
              onChange={(event) => updateDraft(event.target.value)}
              placeholder="Generated strict script JSON will appear here..."
              style={nvis.directorStoryArea}
            />
          </details>
        </div>
      </div>

      <div data-qid="dream:script:action-bar" style={nvis.scriptActionBar}>
        <button
          type="button"
          data-qid="dream:script:copy-payload:footer"
          title="Copy Phase 06 script prompt payload JSON"
          onClick={() => { void copyPayload() }}
          style={nvis.directorDebugBtn}
        >
          {copyStatus ? <ClipboardCheck size={13} /> : <Copy size={13} />}
          {copyStatus || 'Copy Payload'}
        </button>
        <button
          type="button"
          data-qid="dream:script:generate:footer"
          title="Dispatch Phase 06 script payload to Tau"
          disabled={isGenerating}
          onClick={() => { void generateScript() }}
          style={{ ...nvis.directorGenerateBtn, ...(isGenerating ? nvis.directorBtnDisabled : null) }}
        >
          <Sparkles size={14} />
          {isGenerating ? 'Dispatching' : 'Generate Script'}
        </button>
      </div>
    </section>
  )
}

function ResearchPane({ research, ideaSeed }: { research: ResearchMemoryResult[]; ideaSeed: string }) {
  const groupedResearch = groupResearchContext(research)
  return (
    <aside data-qid="research-pane" style={nvis.researchPane}>
      <div style={nvis.researchPaneHeader}>
        <h4 style={nvis.researchPaneTitle}>Research Context</h4>
        <span style={nvis.researchPaneBadge}>Brave Search</span>
      </div>
      <div style={{ color: '#64748b', fontSize: 10, letterSpacing: '0.04em', marginBottom: 12 }}>
        Seed: <span style={{ color: '#e2e8f0' }}>"{ideaSeed.slice(0, 60)}{ideaSeed.length > 60 ? '...' : ''}"</span>
      </div>
      <div style={nvis.researchList}>
        {groupedResearch.map((group) => (
          <details key={group.label} style={nvis.researchAccordion}>
            <summary style={nvis.researchAccordionSummary}>
              <span>{group.label} ({group.items.length})</span>
            </summary>
            <div style={nvis.researchAccordionContent}>
              {group.items.map((r, itemIndex) => (
                <div key={`${r.url ?? r.memoryKey ?? group.label}-${itemIndex}`} style={nvis.researchCard}>
                  <a href={r.url} target="_blank" rel="noreferrer" style={nvis.researchLink}>{readableMemoryText(r.title || r.memoryKey || 'Memory residue')}</a>
                  <p style={nvis.researchSnippet}>{readableMemoryText(r.snippet || r.title || '')}</p>
                </div>
              ))}
            </div>
          </details>
        ))}
      </div>
    </aside>
  )
}

function MediaModal({ url, mediaType, onClose }: { url: string; mediaType?: string; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])
  const isVideo = ['mp4','mov','avi','webm'].includes(mediaType || '')
  const isAudio = ['wav','mp3','ogg'].includes(mediaType || '')
  return createPortal(
    <div
      onClick={onClose}
      data-qid="dream:memory:media-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Memory media preview"
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,0.58)', backdropFilter: 'blur(5px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'zoom-out', padding: 24,
      }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        onClick={(e) => e.stopPropagation()}
        style={nvis.memoryInspectorModal}
      >
        <button
          type="button"
          data-qid="dream:memory:media-modal-close"
          data-qs-action="DREAM_MEMORY_CLOSE_MEDIA"
          title="Close memory media preview"
          aria-label="Close memory media preview"
          onClick={onClose}
          style={nvis.modalCloseBtn}
        >
          <X size={17} />
        </button>
        {isVideo ? (
          <video src={url} controls autoPlay style={nvis.memoryInspectorMedia} />
        ) : isAudio ? (
          <div style={nvis.memoryInspectorAudio}>
            <audio src={url} controls autoPlay style={{ width: '100%' }} />
          </div>
        ) : (
          <img src={url} alt="" style={nvis.memoryInspectorMedia} />
        )}
      </motion.div>
    </div>,
    document.body
  )
}

function TraceGraphOverlay({
  graph,
  ideaText,
  anchorRect,
  onClose,
}: {
  graph: TraceGraph
  ideaText: string
  anchorRect?: TraceAnchorRect | null
  onClose: () => void
}) {
  const [hopLimit, setHopLimit] = useState<1 | 2 | 3 | 99>(2)
  const [liveGraph, setLiveGraph] = useState(graph)
  const [memoryStatus, setMemoryStatus] = useState<'idle' | 'loading' | 'loaded' | 'miss' | 'error'>('idle')
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState(graph.rootId)
  const [activeRootNode, setActiveRootNode] = useState<TraceGraphNode>(graph.nodes.find((node) => node.id === graph.rootId) ?? graph.nodes[0])
  const [wrapRef, size] = useElementSize<HTMLDivElement>()
  const svgRef = useRef<SVGSVGElement | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [zoomTransform, setZoomTransform] = useState<d3.ZoomTransform>(d3.zoomIdentity)
  const [layoutPulse, setLayoutPulse] = useState(0)
  const [showTraceLinks, setShowTraceLinks] = useState(false)
  const [playingAudioNodeId, setPlayingAudioNodeId] = useState<string | null>(null)
  const [videoNode, setVideoNode] = useState<TraceGraphNode | null>(null)
  void ideaText

  useEffect(() => {
    setLiveGraph(graph)
    setSelectedNodeId(graph.rootId)
    setActiveRootNode(graph.nodes.find((node) => node.id === graph.rootId) ?? graph.nodes[0])
    setVideoNode(null)
    setPlayingAudioNodeId(null)
    audioRef.current?.pause()
  }, [graph])

  const activeBaseGraph = useMemo<TraceGraph>(() => {
    const root = activeRootNode ?? graph.nodes.find((node) => node.id === graph.rootId) ?? graph.nodes[0]
    return {
      ...graph,
      rootId: root.id,
      memoryEndpoint: root.id,
      title: root.label,
      source: graph.source,
      nodes: [{ ...root, hop: 0 }],
      links: [],
    }
  }, [activeRootNode, graph])

  useEffect(() => {
    let cancelled = false
    async function loadMemoryNeighborhood() {
      const rootEndpoint = activeBaseGraph.memoryEndpoint ?? activeBaseGraph.rootId
      if (!endpointParts(rootEndpoint)) {
        setMemoryStatus('miss')
        setLiveGraph(activeBaseGraph)
        return
      }
      setMemoryStatus('loading')
      setLiveGraph(activeBaseGraph)
      try {
        const edgeCollections = ['persona_memory_edges', 'tom_edges', 'persona_memory_entity_edges', 'persona_entity_edges']
        const firstHopBatches = await Promise.all(edgeCollections.flatMap((collection) => [
          memoryEdgeDocuments(collection, rootEndpoint, '_from').catch(() => []),
          memoryEdgeDocuments(collection, rootEndpoint, '_to').catch(() => []),
        ]))
        const firstHopRows = firstHopBatches.flat()
        const firstHopEndpoints = Array.from(new Set(firstHopRows.flatMap((edge) => [String(edge._from || ''), String(edge._to || '')]).filter(Boolean)))
          .filter((endpoint) => endpoint !== rootEndpoint)
          .slice(0, 8)
        const secondHopCollections = ['persona_memory_edges', 'tom_edges', 'persona_memory_entity_edges']
        const secondHopBatches = await Promise.all(firstHopEndpoints.flatMap((endpoint) => secondHopCollections.flatMap((collection) => [
          memoryEdgeDocuments(collection, endpoint, '_from').catch(() => []),
          memoryEdgeDocuments(collection, endpoint, '_to').catch(() => []),
        ])))
        const recallMediaBatches = await Promise.all(firstHopEndpoints.map((endpoint) => {
          const key = endpointParts(endpoint)?.key ?? endpoint
          return memoryRecallDocuments(
            `media_to_story_memory tom_media_grounding surf ritual Kai Embry audio video image ${key} ${activeBaseGraph.title}`,
            ['persona_memory_edges', 'tom_edges'],
            18,
          ).catch(() => [])
        }))
        const rowById = new Map<string, Record<string, unknown>>()
        ;[...firstHopRows, ...secondHopBatches.flat(), ...recallMediaBatches.flat()].filter((edge) => isDisplayableTraceEdge(edge, rootEndpoint)).forEach((edge, index) => {
          const from = String(edge._from || '')
          const to = String(edge._to || '')
          if (!from || !to) return
          const edgeKey = String(edge._id || edge._key || `${from}->${to}:${edge.relationship_type || edge.tom_state_type || index}`)
          rowById.set(edgeKey, edge)
        })
        const rows = Array.from(rowById.values()).slice(0, 22)
        const endpoints = Array.from(new Set([rootEndpoint, ...rows.flatMap((edge) => [String(edge._from || ''), String(edge._to || '')]).filter(Boolean)]))
        const hydrated = await Promise.all(endpoints.map(async (endpoint) => [endpoint, await memoryListByEndpoint(endpoint).catch(() => null)] as const))
        const docsByEndpoint = new Map<string, Record<string, unknown> | null>(hydrated)
        if (cancelled) return
        setLiveGraph(buildLiveMemoryTraceGraph(activeBaseGraph, rows, docsByEndpoint))
        setMemoryStatus(rows.length > 0 ? 'loaded' : 'miss')
      } catch {
        if (!cancelled) {
          setLiveGraph(activeBaseGraph)
          setMemoryStatus('error')
        }
      }
    }
    void loadMemoryNeighborhood()
    return () => { cancelled = true }
  }, [activeBaseGraph])

  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const selection = d3.select(svg)
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.45, 2.4])
      .on('zoom', (event) => setZoomTransform(event.transform))
    selection.call(zoom)
    selection.on('dblclick.zoom', null)
    return () => {
      selection.on('.zoom', null)
    }
  }, [])

  const filteredGraph = useMemo(() => {
    if (hopLimit === 99) return liveGraph
    const nodes = liveGraph.nodes.filter((node) => node.hop <= hopLimit)
    const nodeIds = new Set(nodes.map((node) => node.id))
    const links = liveGraph.links.filter((link) => link.hop <= hopLimit && nodeIds.has(link.source) && nodeIds.has(link.target))
    return { ...liveGraph, nodes, links }
  }, [liveGraph, hopLimit])

  useEffect(() => {
    let frame = 0
    let cancelled = false
    setLayoutPulse(0)
    setShowTraceLinks(false)
    const tick = () => {
      if (cancelled) return
      frame += 1
      setLayoutPulse(frame)
      if (frame < 64) window.setTimeout(tick, 34)
    }
    const edgeTimer = window.setTimeout(() => {
      if (!cancelled) setShowTraceLinks(true)
    }, 2600)
    tick()
    return () => {
      cancelled = true
      window.clearTimeout(edgeTimer)
    }
  }, [filteredGraph.rootId, filteredGraph.nodes.length, filteredGraph.links.length, hopLimit])

  const layout = useMemo(() => {
    const width = size.width
    const height = size.height
    const nodes = filteredGraph.nodes.map((node) => ({ ...node }))
    const links = filteredGraph.links.map((link) => ({ ...link }))
    nodes.forEach((node, index) => {
      const angle = (-Math.PI / 2) + index * ((Math.PI * 2) / Math.max(1, nodes.length))
      const ring = node.id === filteredGraph.rootId ? 0 : index % 2 === 0 ? 0.28 : 0.38
      const radius = Math.min(width, height) * ring
      ;(node as TraceGraphNode & d3.SimulationNodeDatum).x = width * 0.5 + Math.cos(angle) * radius
      ;(node as TraceGraphNode & d3.SimulationNodeDatum).y = height * 0.5 + Math.sin(angle) * radius
      if (node.id === filteredGraph.rootId) {
        ;(node as TraceGraphNode & d3.SimulationNodeDatum).fx = width * 0.5
        ;(node as TraceGraphNode & d3.SimulationNodeDatum).fy = height * 0.5
      }
    })
    const simulation = d3.forceSimulation(nodes as Array<TraceGraphNode & d3.SimulationNodeDatum>)
      .force('link', d3.forceLink<TraceGraphNode & d3.SimulationNodeDatum, TraceGraphLink & d3.SimulationLinkDatum<TraceGraphNode & d3.SimulationNodeDatum>>(links as Array<TraceGraphLink & d3.SimulationLinkDatum<TraceGraphNode & d3.SimulationNodeDatum>>).id((node) => node.id).distance((link) => 122 + link.hop * 42).strength(0.32))
      .force('charge', d3.forceManyBody().strength(-420))
      .force('center', d3.forceCenter(width * 0.5, height * 0.5))
      .force('x', d3.forceX(width * 0.5).strength(0.035))
      .force('y', d3.forceY(height * 0.5).strength(0.035))
      .force('collision', d3.forceCollide<TraceGraphNode & d3.SimulationNodeDatum>().radius((node) => node.radius + 32).iterations(4).strength(1))
      .stop()
    for (let i = 0; i < Math.min(140, 6 + layoutPulse * 2); i += 1) simulation.tick()
    simulation.stop()
    const extents = nodes.reduce(
      (acc, node) => {
        const x = (node as TraceGraphNode & d3.SimulationNodeDatum).x ?? width * 0.5
        const y = (node as TraceGraphNode & d3.SimulationNodeDatum).y ?? height * 0.5
        const pad = node.radius + 44
        return {
          minX: Math.min(acc.minX, x - pad),
          maxX: Math.max(acc.maxX, x + pad),
          minY: Math.min(acc.minY, y - pad),
          maxY: Math.max(acc.maxY, y + pad),
        }
      },
      { minX: Number.POSITIVE_INFINITY, maxX: Number.NEGATIVE_INFINITY, minY: Number.POSITIVE_INFINITY, maxY: Number.NEGATIVE_INFINITY }
    )
    const shiftX = width * 0.5 - (extents.minX + extents.maxX) / 2
    const shiftY = height * 0.5 - (extents.minY + extents.maxY) / 2
    relaxTraceNodeOverlaps(nodes as Array<TraceGraphNode & d3.SimulationNodeDatum>, width, height)
    nodes.forEach((node) => {
      const datum = node as TraceGraphNode & d3.SimulationNodeDatum
      const pad = node.radius + 58
      datum.x = clampNumber((datum.x ?? width * 0.5) + shiftX, pad, width - pad)
      datum.y = clampNumber((datum.y ?? height * 0.5) + shiftY, pad, height - pad)
    })
    relaxTraceNodeOverlaps(nodes as Array<TraceGraphNode & d3.SimulationNodeDatum>, width, height)
    nodes.forEach((node) => {
      const datum = node as TraceGraphNode & d3.SimulationNodeDatum
      const pad = node.radius + 58
      datum.x = clampNumber(datum.x ?? width * 0.5, pad, width - pad)
      datum.y = clampNumber(datum.y ?? height * 0.5, pad, height - pad)
    })
    return { nodes: nodes as Array<TraceGraphNode & d3.SimulationNodeDatum>, links: links as Array<TraceGraphLink & d3.SimulationLinkDatum<TraceGraphNode & d3.SimulationNodeDatum>> }
  }, [filteredGraph, size, layoutPulse])

  const hopLabel = hopLimit === 99 ? 'All hops' : `${hopLimit}-Hop`
  const cycleHopLimit = () => {
    setHopLimit((current) => current === 1 ? 2 : current === 2 ? 3 : current === 3 ? 99 : 1)
  }
  const viewportWidth = typeof window === 'undefined' ? 1440 : window.innerWidth
  const viewportHeight = typeof window === 'undefined' ? 900 : window.innerHeight
  const region = anchorRect ?? { left: 240, top: 104, width: viewportWidth - 560, height: viewportHeight - 128 }
  const panelWidth = Math.min(760, Math.max(560, Math.min(region.width, 720)), viewportWidth - 48)
  const panelHeight = Math.min(560, Math.max(430, Math.min(region.height + 120, viewportHeight * 0.64)), viewportHeight - 48)
  const panelLeft = clampNumber(region.left + (region.width - panelWidth) / 2, 24, viewportWidth - panelWidth - 24)
  const panelTop = clampNumber(region.top + Math.min(28, region.height * 0.08), 72, viewportHeight - panelHeight - 24)
  const currentNode = filteredGraph.nodes.find((node) => node.id === (hoveredNodeId ?? selectedNodeId)) ?? filteredGraph.nodes.find((node) => node.id === filteredGraph.rootId) ?? filteredGraph.nodes[0]
  const currentNodeText = currentNode ? (currentNode.source_ref || currentNode.label) : graph.title

  const handleNodeClick = (node: TraceGraphNode) => {
    setSelectedNodeId(node.id)
    setHoveredNodeId(null)
    if (node.kind === 'audio' && node.mediaUrl) {
      if (!audioRef.current) audioRef.current = new Audio()
      const audio = audioRef.current
      if (playingAudioNodeId === node.id && !audio.paused) {
        audio.pause()
        setPlayingAudioNodeId(null)
        return
      }
      audio.src = node.mediaUrl
      audio.onended = () => setPlayingAudioNodeId(null)
      void audio.play().then(() => setPlayingAudioNodeId(node.id)).catch(() => setPlayingAudioNodeId(null))
      return
    }
    if (node.kind === 'video' && node.mediaUrl) {
      setVideoNode(node)
      return
    }
    setActiveRootNode({ ...node, hop: 0 })
    setHopLimit(1)
  }

  return createPortal(
    <div data-qid="dream:memory:trace-graph-overlay" role="dialog" aria-modal="false" aria-label="Memory relationship trace graph" style={nvis.traceOverlayBackdrop} onClick={onClose}>
      <motion.div
        onClick={(event) => event.stopPropagation()}
        initial={{ opacity: 0, scale: 0.94, y: 18 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 360, damping: 26, mass: 0.75 }}
        style={{ ...nvis.traceOverlayPanel, left: panelLeft, top: panelTop, width: panelWidth, height: panelHeight }}
      >
        <div style={nvis.traceHeader}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
            <CircleDot size={16} style={{ color: '#4a9eff', flexShrink: 0 }} />
            <span style={nvis.traceTitle}>{currentNodeText}</span>
          </div>
          <div style={nvis.traceToolbar}>
            <button
              type="button"
              data-qid="dream:trace:hop-cycle"
              data-qs-action="DREAM_TRACE_SET_HOP"
              title={`Showing assets up to ${hopLimit === 99 ? 'all' : hopLimit} connection${hopLimit === 1 ? '' : 's'} away. Click to change hop depth.`}
              onClick={cycleHopLimit}
              style={nvis.traceHopCycle}
            >
              <GitBranch size={14} />
              <span>{hopLimit === 99 ? 'Related (all)' : `Related (${hopLimit}°)`}</span>
            </button>
          </div>
          <div style={nvis.traceIconBar}>
            <button type="button" data-qid="dream:trace:close" data-qs-action="DREAM_TRACE_CLOSE" title="Close relationship graph" onClick={onClose} style={nvis.traceIconButton}><X size={18} /></button>
          </div>
        </div>
        <div style={nvis.traceBody}>
          <div ref={wrapRef} style={nvis.traceGraphCanvas}>
            <svg ref={svgRef} data-qid="dream:trace:graph-svg" width="100%" height="100%" viewBox={`0 0 ${size.width} ${size.height}`} role="img" aria-label="Persisted memory relationship graph" style={nvis.traceSvg}>
              <defs>
                <filter id="trace-glow" x="-40%" y="-40%" width="180%" height="180%">
                  <feGaussianBlur stdDeviation="4" result="coloredBlur" />
                  <feMerge>
                    <feMergeNode in="coloredBlur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              <g transform={zoomTransform.toString()}>
              <g data-trace-layer="edges">
              {showTraceLinks && layout.links.map((link) => {
                const source = link.source as TraceGraphNode & d3.SimulationNodeDatum
                const target = link.target as TraceGraphNode & d3.SimulationNodeDatum
                const sx = source.x ?? 0
                const sy = source.y ?? 0
                const tx = target.x ?? 0
                const ty = target.y ?? 0
                const dx = tx - sx
                const dy = ty - sy
                const duplicateIndex = filteredGraph.links.filter((other) => other.source === link.source && other.target === link.target).findIndex((other) => other.id === link.id)
                const normal = duplicateIndex <= 0 ? 0 : (duplicateIndex % 2 === 0 ? 1 : -1) * (duplicateIndex * 12)
                const c1x = sx + dx * 0.42 - dy * 0.08 + normal
                const c1y = sy + dy * 0.24 + dx * 0.08
                const c2x = tx - dx * 0.42 - dy * 0.08 + normal
                const c2y = ty - dy * 0.24 + dx * 0.08
                const curve = `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${tx} ${ty}`
                return (
                  <g key={link.id}>
                    <motion.path
                      data-trace-edge="true"
                      d={curve}
                      fill="none"
                      stroke={nodeKindColor('memory')}
                      strokeOpacity={0.42}
                      strokeWidth={1.15}
                      strokeDasharray={link.hop >= 3 ? '4 5' : undefined}
                      initial={{ pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      transition={{ type: 'spring', stiffness: 220, damping: 26, delay: 0.42 + 0.08 * link.hop }}
                    />
                  </g>
                )
              })}
              </g>
              <g data-trace-layer="nodes">
              {layout.nodes.map((node) => {
                const showNodeLabel = false
                return (
                  <motion.g
                    key={node.id}
                    onMouseEnter={() => setHoveredNodeId(node.id)}
                    onMouseLeave={() => setHoveredNodeId((current) => current === node.id ? null : current)}
                    onClick={() => handleNodeClick(node)}
                    initial={{ opacity: 0, x: size.width * 0.48, y: size.height * 0.52, scale: node.id === filteredGraph.rootId ? 0.9 : 0.58 }}
                    animate={{ opacity: 1, x: node.x ?? 0, y: node.y ?? 0, scale: 1 }}
                    transition={{ type: 'spring', stiffness: 300, damping: 22, mass: 0.7, delay: 0.035 * node.hop }}
                    data-trace-node-kind={node.kind}
                  >
                    <circle r={Math.max(26, node.radius + 16)} fill="transparent" pointerEvents="all" />
                    <circle r={node.radius + 8} fill={node.color} opacity={0.14} filter="url(#trace-glow)" />
                    {node.id === selectedNodeId && (
                      <motion.circle
                        r={node.radius + 13}
                        fill="none"
                        stroke="#f8fafc"
                        strokeWidth={2}
                        strokeOpacity={0.86}
                        initial={{ scale: 0.92, opacity: 0 }}
                        animate={{ scale: [1, 1.08, 1], opacity: [0.72, 1, 0.72] }}
                        transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
                      />
                    )}
                    <circle r={node.radius} fill="rgba(10,15,25,0.94)" stroke={node.color} strokeWidth={node.id === filteredGraph.rootId ? 4 : 2.5} />
                    <foreignObject x={-node.radius + 6} y={-node.radius + 6} width={(node.radius - 6) * 2} height={(node.radius - 6) * 2}>
                      {(node.kind === 'media' || node.kind === 'video') && node.thumbnailUrl ? (
                        <div style={nvis.traceNodeMediaPanel}>
                          <img src={node.thumbnailUrl} alt="" style={nvis.traceNodeMediaImage} />
                          <span style={nvis.traceNodeIconOverlay}>
                            {node.kind === 'video' ? <Film size={13} /> : <Image size={13} />}
                          </span>
                        </div>
                      ) : (
                        <div style={nvis.traceNodeGlyphPanel}>
                          {node.kind === 'audio' ? <Volume2 size={playingAudioNodeId === node.id ? 18 : 16} /> : node.kind === 'video' ? <Film size={16} /> : node.kind === 'media' ? <Image size={16} /> : node.kind === 'person' ? <UserRound size={16} /> : node.kind === 'place' ? <MapPin size={16} /> : node.kind === 'object' ? <Package size={16} /> : <FileText size={16} />}
                        </div>
                      )}
                    </foreignObject>
                    {showNodeLabel && (
                      <foreignObject x={-92} y={node.radius + 12} width={184} height={42} style={{ overflow: 'visible' }}>
                        <div style={nvis.traceNodeLabelBox}>
                          <div style={nvis.traceNodeLabelText}>{node.label}</div>
                          <div style={nvis.traceNodeKindText}>{node.kind.replace('_', ' ')}</div>
                        </div>
                      </foreignObject>
                    )}
                  </motion.g>
                )
              })}
              </g>
              </g>
            </svg>
            {currentNode && currentNode.kind === 'memory' && (
              <div data-qid="dream:trace:node-preview" style={nvis.traceTextPreviewFloating}>
                <div style={nvis.traceTextPreviewMeta}>Text memory</div>
                <div>{currentNodeText.slice(0, 260)}</div>
              </div>
            )}
            {videoNode?.mediaUrl && (
              <div data-qid="dream:trace:video-player" style={nvis.traceVideoPlayer}>
                <div style={nvis.traceVideoHeader}>
                  <span>{videoNode.label}</span>
                  <button type="button" title="Close video" onClick={() => setVideoNode(null)} style={nvis.traceVideoClose}><X size={14} /></button>
                </div>
                <video src={videoNode.mediaUrl} controls autoPlay style={nvis.traceVideoElement} />
              </div>
            )}
          </div>
        </div>
        <table style={nvis.traceHiddenTable}>
          <caption>Memory trace graph nodes and links</caption>
          <tbody>
            {filteredGraph.nodes.map((node) => (
              <tr key={node.id}><th>{node.label}</th><td>{node.kind}</td><td>{node.tom_state_type || ''}</td><td>{node.tom_tags?.join(', ') || ''}</td></tr>
            ))}
          </tbody>
        </table>
      </motion.div>
    </div>,
    document.body
  )
}

function GraphModal({ signals, sourceKind, label, onClose }: {
  signals: MemoryConnectionSignal[]
  sourceKind: string
  label: string
  onClose: () => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!containerRef.current || signals.length === 0) return
    const w = containerRef.current.clientWidth || 600
    const h = containerRef.current.clientHeight || 400
    const nodes = [
      { id: 'source', label: sourceKind, group: 1 },
      ...signals.map((s, i) => ({ id: s.id, label: s.tomKind, group: 2, color: s.color })),
      { id: 'target', label: 'Story', group: 3 },
    ]
    const links = [
      ...signals.map((s) => ({ source: 'source', target: s.id })),
      ...signals.map((s) => ({ source: s.id, target: 'target' })),
    ]
    const svg = d3.select(containerRef.current).append('svg').attr('width', w).attr('height', h)
    const g = svg.append('g')
    const zoom = d3.zoom<SVGSVGElement, unknown>().on('zoom', (event) => g.attr('transform', event.transform))
    svg.call(zoom)
    const simulation = d3.forceSimulation(nodes as any)
      .force('link', d3.forceLink(links).distance(100))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(w / 2, h / 2))
    const link = g.append('g').selectAll('line').data(links).join('line')
      .attr('stroke', 'rgba(255,255,255,0.15)').attr('stroke-width', 1.5)
    const node = g.append('g').selectAll('circle').data(nodes).join('circle')
      .attr('r', 20).attr('fill', (d: any) => d.color || '#4a9eff').attr('stroke', 'rgba(255,255,255,0.2)').attr('stroke-width', 1)
      .call(d3.drag<any, any>()
        .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null })
      )
    const label_g = g.append('g').selectAll('text').data(nodes).join('text')
      .text((d: any) => d.label).attr('text-anchor', 'middle').attr('dy', 35)
      .attr('fill', '#9ca3af').attr('font-size', 10)
    simulation.on('tick', () => {
      link.attr('x1', (d: any) => d.source.x).attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x).attr('y2', (d: any) => d.target.y)
      node.attr('cx', (d: any) => d.x).attr('cy', (d: any) => d.y)
      label_g.attr('x', (d: any) => d.x).attr('y', (d: any) => d.y)
    })
    return () => { svg.remove() }
  }, [signals, sourceKind])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(12px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'zoom-out',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: '80vw', height: '80vh', cursor: 'default' }}>
        <div style={{ color: '#64748b', fontSize: 10, textAlign: 'center', marginBottom: 8, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          Semantic connections &mdash; {label.slice(0, 60)}
        </div>
        <div ref={containerRef} style={{ width: '100%', height: '100%', borderRadius: 12, overflow: 'hidden', background: 'rgba(0,0,0,0.3)' }} />
      </div>
    </div>
  )
}

function TextExpandModal({ text, onClose }: { text: string; onClose: () => void }) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])
  return createPortal(
    <div onClick={onClose} role="dialog" aria-modal="true" aria-label="Full memory text" style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.58)', backdropFilter: 'blur(5px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      cursor: 'zoom-out', padding: 24,
    }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(640px, calc(100vw - 48px))',
          maxHeight: '80vh', overflow: 'auto',
          background: '#0c0c0c', borderRadius: 12,
          border: '1px solid rgba(255,255,255,0.1)',
          padding: 28, cursor: 'default',
        }}
      >
        <button type="button" onClick={onClose} style={{
          float: 'right', width: 28, height: 28,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: 'none', background: 'transparent', color: '#64748b',
          cursor: 'pointer', borderRadius: 6,
        }}>
          <X size={16} />
        </button>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: '#e2e8f0', whiteSpace: 'pre-wrap' }}>{text}</p>
      </motion.div>
    </div>,
    document.body
  )
}

function MemoryLinker({
  memory,
  ideaText,
  entitySuggestions,
  activeConnection,
  onConnectionHover,
  onLink,
  onDragStart,
}: {
  memory: { id: string; label: string; score?: number; subtitle?: string; imageUrl?: string; mediaType?: string; memoryKey?: string; mediaUrl?: string }
  ideaText: string
  entitySuggestions: string[]
  activeConnection: string | null
  onConnectionHover: (connectionId: string | null) => void
  onLink: (memoryId: string, entity: string) => void
  onDragStart?: (id: string, label: string) => void
}) {
  const [linking, setLinking] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [graphAnchor, setGraphAnchor] = useState<TraceAnchorRect | null>(null)
  const [hovered, setHovered] = useState(false)
  const [textModalOpen, setTextModalOpen] = useState(false)
  const textRef = useRef<HTMLDivElement>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [showFade, setShowFade] = useState(false)
  const [audioPlaying, setAudioPlaying] = useState(false)
  useEffect(() => {
    const el = textRef.current
    if (el) {
      setShowFade(el.scrollHeight > el.clientHeight)
    }
  }, [memory.label])
  const qidSafe = memory.id.replace(/[^a-z0-9_-]+/gi, '-').slice(0, 80)
  const signals = useMemo(() => memoryConnectionSignals(memory), [memory])
  const sharesActiveConnection = activeConnection ? signals.some((signal) => signal.id === activeConnection) : false
  const isVideo = ['mp4','mov','avi','webm'].includes(memory.mediaType || '')
  const isAudio = ['wav','mp3','ogg'].includes(memory.mediaType || '')
  const isMedia = Boolean(memory.imageUrl)
  const openMedia = (event: { preventDefault: () => void; stopPropagation: () => void }) => {
    event.preventDefault()
    event.stopPropagation()
    if (isAudio) {
      const audio = audioRef.current
      if (!audio) return
      const playbackUrl = memory.mediaUrl || memory.imageUrl || ''
      if (audio.paused) {
        if (audio.src !== playbackUrl) audio.src = playbackUrl
        void audio.play()
        setAudioPlaying(true)
      } else {
        audio.pause()
        setAudioPlaying(false)
      }
      return
    }
    setModalOpen(true)
  }
  const sourceKind = isAudio ? 'Audio' : isVideo ? 'Video' : isMedia ? 'Image' : 'Text'
  const traceGraph = useMemo(() => buildCardTraceGraph(memory, ideaText, signals), [ideaText, memory, signals])
  const detailControl = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, opacity: hovered ? 1 : 0, transition: 'opacity 150ms ease' }}>
      {signals.length > 0 && (
        <button
          type="button"
          data-qid={`dream:memory:graph:${qidSafe}`}
          data-qs-action="DREAM_MEMORY_TRACE_GRAPH"
          onClick={(e) => {
            e.preventDefault(); e.stopPropagation()
            const masonry = document.querySelector('[data-qid="dream:memory:masonry"]')
            const rect = (masonry ?? e.currentTarget.closest('[data-qid^="dream:memory-node:"]'))?.getBoundingClientRect()
            setGraphAnchor(rect ? { left: rect.left, top: rect.top, width: rect.width, height: rect.height } : null)
          }}
          style={nvis.graphGhostBtn}
          title="Open Theory-of-Mind trace graph"
        >
          <Share2 size={13} />
        </button>
      )}
      {signals.length > 0 && (
        <div style={{ width: 1, height: 12, background: 'rgba(255,255,255,0.12)', flexShrink: 0, alignSelf: 'center' }} />
      )}
      <button
        type="button"
        data-qid={`dream:memory:link:${qidSafe}`}
        data-qs-action="DREAM_MEMORY_LINK"
        title="Expand memory details"
        onClick={(e) => { e.stopPropagation(); setLinking(!linking) }}
        style={nvis.chevronBtn}
      >
        <ChevronRight size={14} />
      </button>
      {linking && (
        <select
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => { onLink(memory.id, e.target.value); setLinking(false) }}
          defaultValue=""
          style={nvis.memorySelect}
          data-qid={`dream:memory:link-select:${qidSafe}`}
          data-qs-action="DREAM_MEMORY_LINK"
          aria-haspopup="listbox"
          title="Pin memory to entity"
        >
          <option value="" disabled>Link to...</option>
          {entitySuggestions.map((e) => (<option key={e} value={e}>{e}</option>))}
        </select>
      )}
    </div>
  )
  return (
    <div
      data-qid={`dream:memory-node:${qidSafe}`}
      data-connection-ids={signals.map((signal) => signal.id).join(' ')}
      className={`memory-masonry-card ${memory.imageUrl ? 'memory-masonry-card-media' : 'memory-masonry-card-text text-node-well'}`}
      draggable={!isMedia}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => {
        setHovered(false)
        onConnectionHover(null)
      }}
      onDragStart={(e) => {
        if (onDragStart) onDragStart(memory.id, memory.label)
        e.dataTransfer.setData('text/plain', `${memory.subtitle || memory.id}: ${memory.label}`)
        e.dataTransfer.effectAllowed = 'link'
      }}
      style={isMedia
        ? {
          ...nvis.memoryMediaCard,
          ...(sharesActiveConnection ? nvis.memorySemanticActive : null),
          ...(activeConnection && !sharesActiveConnection ? nvis.memorySemanticDim : null),
        }
        : {
          ...(sharesActiveConnection ? nvis.memorySemanticActive : null),
          ...(activeConnection && !sharesActiveConnection ? nvis.memorySemanticDim : null),
        }}
    >
      {modalOpen && isMedia && !isAudio && <MediaModal url={(memory.mediaUrl || memory.imageUrl)!} mediaType={memory.mediaType} onClose={() => setModalOpen(false)} />}
      {graphAnchor && <TraceGraphOverlay graph={traceGraph} ideaText={ideaText} anchorRect={graphAnchor} onClose={() => setGraphAnchor(null)} />}
      {isMedia ? (
        <>
          <div
            role="button"
            tabIndex={0}
            data-qid={`dream:memory:open-media:${qidSafe}`}
            data-qs-action="DREAM_MEMORY_OPEN_MEDIA"
            aria-label={`Open memory ${isAudio ? 'audio' : isVideo ? 'media' : 'image'}: ${memory.subtitle || memory.label}`}
            onClick={openMedia}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' && event.key !== ' ') return
              openMedia(event)
            }}
            onPointerDown={(e) => e.stopPropagation()}
            style={nvis.memoryMediaButton}
          >
            {isVideo ? (
              <video
                src={memory.mediaUrl || memory.imageUrl}
                poster={memory.imageUrl}
                controls
                preload="metadata"
                onClick={(event) => event.stopPropagation()}
                draggable={false}
                style={nvis.memoryFullBleedMedia}
              />
            ) : isAudio ? (
              <div style={nvis.memoryAudioPreview}>
                <audio
                  ref={audioRef}
                  src={memory.mediaUrl || memory.imageUrl}
                  preload="metadata"
                  onEnded={() => setAudioPlaying(false)}
                  onPause={() => setAudioPlaying(false)}
                  onPlay={() => setAudioPlaying(true)}
                />
                <Volume2 size={22} />
                <span style={{ color: '#e2e8f0', fontSize: 12, letterSpacing: '0.16em', textTransform: 'uppercase' }}>
                  {audioPlaying ? 'Pause audio' : 'Play audio'}
                </span>
              </div>
            ) : (
              <img src={memory.imageUrl} alt="" draggable={false} style={nvis.memoryFullBleedMedia} />
            )}
          </div>
          <div className="memory-card-shelf" style={nvis.memoryMediaShelf}>
            <p style={{ ...nvis.memoryOverlayText, color: hovered ? 'rgba(255,255,255,1)' : 'rgba(255,255,255,0.75)', textShadow: hovered ? '0 0 12px rgba(255,255,255,0.15)' : 'none' }}>{memory.label}</p>
            {detailControl}
          </div>
        </>
      ) : (
        <>
          <div className="text-node-content-wrap" onClick={() => setTextModalOpen(true)}>
            <div ref={textRef} className="text-node-content">{memory.label}</div>
            {showFade && <div className="text-node-fade" />}
          </div>
          <div className="text-node-actions" style={{ opacity: hovered ? 1 : 0, pointerEvents: hovered ? 'auto' as const : 'none' as const }}>
            {detailControl}
          </div>
          {textModalOpen && <TextExpandModal text={memory.label} onClose={() => setTextModalOpen(false)} />}
        </>
      )}
      {hovered && (
        <div style={nvis.pinCallout}>
          <div style={nvis.pinHudHeader}>
            <GitBranch size={12} style={{ color: '#4a9eff', flexShrink: 0 }} />
            <span style={nvis.pinHudTitle}>{memory.subtitle || memory.label.slice(0, 40)}</span>
          </div>
          <div style={nvis.pinHudBody}>{memory.label}</div>
          <div style={nvis.pinHudFooter}>
            {memory.score != null && <span>{memory.score}% confidence</span>}
            {memory.subtitle && <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}>{memory.subtitle}</span>}
            {signals.length > 0 && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                {signals.map((s) => (
                  <span key={s.id} style={{ width: 5, height: 5, borderRadius: '50%', background: s.color, display: 'inline-block' }} />
                ))}
                {signals.length} hop{signals.length > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function IdeaMemoryControl({
  ideaStage,
  memoryStage,
  onTriggerMemories,
  processing,
  memoryResults,
  humanIdea,
}: {
  ideaStage: DreamStage | null
  memoryStage: DreamStage | null
  onTriggerMemories: (ideaText: string) => void
  processing: boolean
  memoryResults?: ResearchMemoryResult[] | null
  humanIdea?: HumanIdeaProjection
}) {
  const [localIdea, setLocalIdea] = useState(persistedHumanIdea(humanIdea))
  const [linkedEntities, setLinkedEntities] = useState<Record<string, string>>({})
  const [debouncedIdea, setDebouncedIdea] = useState(localIdea)
  const [ideaFocused, setIdeaFocused] = useState(false)
  const [activeMemoryConnection, setActiveMemoryConnection] = useState<string | null>(null)

  const lastTriggered = useRef('')
  const ideaInputRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedIdea(localIdea), 1500)
    return () => clearTimeout(t)
  }, [localIdea])

  useEffect(() => {
    setLocalIdea(persistedHumanIdea(humanIdea))
  }, [humanIdea?.ideaSha256])
  useEffect(() => {
    const input = ideaInputRef.current
    if (!input) return
    if (document.activeElement === input) return
    if (input.innerText !== localIdea) input.innerText = localIdea
  }, [localIdea])
  useEffect(() => {
    if (debouncedIdea && debouncedIdea.length > 10 && debouncedIdea !== lastTriggered.current && !processing) {
      lastTriggered.current = debouncedIdea
      onTriggerMemories(debouncedIdea)
    }
  }, [debouncedIdea, onTriggerMemories, processing])
  const memories = useMemo(() => {
    if (memoryResults && memoryResults.length > 0) {
      const mapped = memoryResults.slice(0, 16).map((r, i) => ({
        id: r.memoryKey ? `persona_memory/${r.memoryKey}` : `mem-research-${i}`,
        label: humanMemoryCaption(r),
        subtitle: r.title || '',
        imageUrl: dreamRenderableMediaUrl(r.url) ? r.url : '',
        mediaType: r.mediaType || '',
        memoryKey: r.memoryKey,
        mediaUrl: dreamRenderableMediaUrl(r.mediaUrl || r.url) ? (r.mediaUrl || r.url || '') : '',
        score: r.score,
      })) as Array<{ id: string; label: string; subtitle: string; imageUrl: string; mediaType: string; memoryKey?: string; mediaUrl?: string; score?: number }>
      const media = mapped.filter((m) => Boolean(m.imageUrl))
      const textOnly = mapped.filter((m) => !m.imageUrl)
      const mixed: typeof mapped = []
      const max = Math.max(media.length, textOnly.length)
      for (let i = 0; i < max; i += 1) {
        if (media[i]) mixed.push(media[i])
        if (textOnly[i]) mixed.push(textOnly[i])
      }
      return mixed
    }
    return (memoryStage?.artifacts ?? []).slice(0, 12).map((a, i) => ({
      id: a.path || `mem-${i}`,
      label: a.label.replace(/\.[^.]+$/, ''),
      score: undefined,
    }))
  }, [memoryResults, memoryStage?.artifacts])

  const entitySuggestions = useMemo(() => {
    const words = localIdea.split(/\s+/).filter((w) => /^[A-Z]/.test(w) && w.length > 2)
    return [...new Set(words)].slice(0, 8)
  }, [localIdea])

  const handleLink = (memoryId: string, entity: string) => {
    setLinkedEntities((prev) => ({ ...prev, [memoryId]: entity }))
  }

  const handleDragStart = (id: string, _label: string) => {
    // no-op, dataTransfer is set by the MemoryLinker
  }

  const allLinked = memories.length === 0 || memories.every((m) => linkedEntities[m.id] != null)

  return (
    <div data-qid="phase-01-02-root" style={ideaFocused ? { ...nvis.ideaMemoryCanvas, ...nvis.ideaMemoryCanvasEditing } : nvis.ideaMemoryCanvas}>
      <section data-qid="dream:memory:board" style={nvis.memoryBoardSection}>
        <div style={nvis.ideaComposer}>
          <div style={nvis.ideaComposerHeader}>
            <span style={nvis.ideaComposerLabel}>Core Creative Directive</span>
            <button
              type="button"
              data-qid="dream:idea:focus-edit"
              data-qs-action="DREAM_IDEA_COMPOSE"
              title="Edit Directive"
              aria-label="Edit Directive"
              className="idea-edit-affordance"
              onClick={() => {
                ideaInputRef.current?.focus()
                setIdeaFocused(true)
              }}
              style={nvis.ideaEditAffordance}
            >
              <PencilLine size={13} />
              <span>Edit</span>
            </button>
          </div>
          <div
            ref={ideaInputRef}
            contentEditable={!humanIdea}
            suppressContentEditableWarning
            onInput={(e) => setLocalIdea(e.currentTarget.innerText)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                e.preventDefault()
                onTriggerMemories(localIdea)
              }
            }}
            onFocus={() => setIdeaFocused(true)}
            onBlur={() => setIdeaFocused(false)}
            data-qid="dream:idea:composer"
            data-qs-action="DREAM_IDEA_COMPOSE"
            data-empty={localIdea.trim().length === 0 ? 'true' : 'false'}
            aria-label="Type a core idea to recall memories"
            style={nvis.ideaComposerInput}
          >
            {localIdea}
          </div>
          {humanIdea && (
            <div data-qid="dream:idea:persisted-identity" style={{ marginTop: 8, color: '#64748b', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              Persisted explicit human idea · {humanIdea.ideaId} · {humanIdea.ideaSha256.slice(0, 18)}…
            </div>
          )}
          <div style={nvis.ideaComposerActions}>
            <button
              type="button"
              onClick={() => onTriggerMemories(localIdea)}
              disabled={processing || localIdea.trim().length <= 10}
              style={processing ? { ...nvis.ideaComposerAction, opacity: 0.95, color: '#ffaa00' } : nvis.ideaComposerAction}
            >
              <span style={processing ? { ...nvis.ideaComposerDot, background: '#ffaa00' } : nvis.ideaComposerDot} />
              {processing ? 'Recalling Memory Residue' : 'Extract Memory Residue'}
            </button>
          </div>
        </div>
        {processing && memories.length === 0 && (
          <div style={{ color: '#ffaa00', fontSize: 11, padding: 12, textAlign: 'center' }}>Loading memory residue...</div>
        )}
        {!processing && memories.length > 0 && (
          <div data-qid="dream:memory:masonry" className="memory-masonry-board" style={nvis.memoryMasonry}>
            {memories.slice(0, 12).map((m) => (
              <MemoryLinker
                key={m.id}
                memory={m}
                ideaText={localIdea}
                entitySuggestions={entitySuggestions}
                activeConnection={activeMemoryConnection}
                onConnectionHover={setActiveMemoryConnection}
                onLink={handleLink}
                onDragStart={handleDragStart}
              />
            ))}
          </div>
        )}
        {!processing && memories.length === 0 && (
          <div style={{ color: '#ff4444', fontSize: 11, padding: 12, textAlign: 'center', border: '1px dashed rgba(255,255,255,0.08)', borderRadius: 8, background: 'rgba(0,0,0,0.15)' }}>
            NO_LINKED_MEMORIES — memories from persona recall appear here
          </div>
        )}
        {memories.length > 0 && !allLinked && (
          <div style={{ color: '#ffaa00', fontSize: 10, marginTop: 8, letterSpacing: '0.04em', textAlign: 'center' }}>
            Some memories remain unlinked. Link residue cards before proceeding.
          </div>
        )}
      </section>
    </div>
  )
}

function ContactSheetBoard({ stage }: { stage: DreamStage }) {
  const [requirementSheets, setRequirementSheets] = useState<ContactSheetRequirementAsset[]>([])
  const [previewSheet, setPreviewSheet] = useState<ContactSheetDisplayAsset | null>(null)
  const requirementsArtifact = stage.artifacts.find((artifact) => artifact.label.endsWith('contact_sheet_requirements.json'))
  useEffect(() => {
    let cancelled = false
    async function loadRequirementSheets() {
      if (!requirementsArtifact) {
        setRequirementSheets([])
        return
      }
      try {
        const response = await fetch(`/api/projects/dream/asset?path=${encodeURIComponent(requirementsArtifact.path)}`)
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const payload = await response.json()
        const rows = Array.isArray(payload.requirements) ? payload.requirements : []
        const next = new Map<string, ContactSheetRequirementAsset>()
        rows.forEach((row: Record<string, unknown>) => {
          const entity = String(row.entity || '')
          const entityType = String(row.entity_type || '')
          const assets = Array.isArray(row.existing_assets) ? row.existing_assets : []
          assets.forEach((asset) => {
            if (!asset || typeof asset !== 'object') return
            const item = asset as Record<string, unknown>
            const rawUrl = String(item.url || item.source || '')
            const url = dreamAssetUrl(rawUrl)
            const id = String(item.asset_id || item.memory_key || rawUrl)
            if (!url || !id) return
            next.set(id, {
              id,
              url,
              label: String(item.title || entity || id),
              entity,
              entityType,
            })
          })
        })
        if (!cancelled) setRequirementSheets(Array.from(next.values()))
      } catch (error) {
        console.warn('Failed to load contact sheet requirements', error)
        if (!cancelled) setRequirementSheets([])
      }
    }
    void loadRequirementSheets()
    return () => { cancelled = true }
  }, [requirementsArtifact?.path])

  const sheets: ContactSheetDisplayAsset[] = stage.images.length > 0
    ? stage.images.map((img) => ({ id: img.path, url: img.url, label: img.label }))
    : requirementSheets
  const hasRequirementArtifacts = stage.artifacts.length > 0

  return (
    <div data-qid="contact-sheet-grid" style={nvis.contactSheetGrid}>
      {sheets.length > 0 ? sheets.map((sheet) => (
        <div
          key={sheet.id}
          className="contact-sheet-card"
          role="button"
          tabIndex={0}
          aria-label={`Open contact sheet preview for ${sheet.label}`}
          data-qid="dream:contact-sheet:card"
          data-qs-action="open-contact-sheet-preview"
          style={nvis.contactSheetCard}
          onClick={() => setPreviewSheet(sheet)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              setPreviewSheet(sheet)
            }
          }}
        >
          <img src={sheet.url} alt={sheet.label} style={nvis.contactSheetThumb} />
          {sheet.entity && (
            <div style={nvis.contactSheetCaption}>
              <span>{sheet.entity}</span>
              <span>{sheet.entityType}</span>
            </div>
          )}
          <div className="contact-sheet-overlay" style={nvis.contactSheetOverlay}>
            <button
              type="button"
              data-qid="dream:contact-sheet:open-preview"
              data-qs-action="open-contact-sheet-preview"
              style={nvis.contactSheetAction}
              onClick={(event) => {
                event.stopPropagation()
                setPreviewSheet(sheet)
              }}
            >
              Open Preview
            </button>
          </div>
        </div>
      )) : (
        <div style={nvis.contactSheetEmpty}>
          <span style={{ color: hasRequirementArtifacts ? '#a7f3d0' : '#ff4444', marginBottom: 8, fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
            {hasRequirementArtifacts ? 'CONTACT_SHEET_REQUIREMENTS_READY' : 'NO_CONTACT_SHEETS'}
          </span>
          {hasRequirementArtifacts && (
            <span style={{ color: '#94a3b8', fontSize: 12, textAlign: 'center', maxWidth: 420, lineHeight: 1.5 }}>
              Phase 04 has a saved requirements contract. Existing character sheets and missing prop/environment reference sheets are listed in the JSON artifacts below.
            </span>
          )}
          <button
            type="button"
            data-qs-action="generate-sheets"
            style={nvis.contactSheetTrigger}
          >
            Trigger Contact Sheet Agent
          </button>
        </div>
      )}
      {previewSheet && (
        <MediaModal url={previewSheet.url} mediaType="png" onClose={() => setPreviewSheet(null)} />
      )}
    </div>
  )
}

function StageWorkOrderBox({
  run,
  stage,
  note,
  actionStatus,
  onNoteChange,
  onSubmitAction,
}: {
  run: DreamRun
  stage: DreamStage
  note: string
  actionStatus?: string
  onNoteChange: (value: string) => void
  onSubmitAction: (action: StageAction, noteOverride?: string) => void
}) {
  return (
      <div style={styles.stageActionBox}>
        <textarea
          data-qid={`dream:stage-edit:${stage.id}`}
          data-qs-action="DREAM_STAGE_EDIT_NOTES"
          title={`Edit or repair notes for ${stage.title}`}
          value={note}
          onChange={(event) => onNoteChange(event.target.value)}
          placeholder="Describe the edit, missing evidence, or reviewer repair needed for this stage..."
          style={styles.stageTextarea}
        />
        <div style={styles.stageActionRow}>
          <button
            type="button"
            data-qid={`dream:stage-action:rerun:${stage.id}`}
            data-qs-action="DREAM_STAGE_RERUN"
            title={`Create rerun work order for ${stage.title}`}
            onClick={() => onSubmitAction('rerun')}
            style={styles.stageActionButton}
          >
            <Play size={14} />
            Rerun stage
          </button>
          <button
            type="button"
            data-qid={`dream:stage-action:edit:${stage.id}`}
            data-qs-action="DREAM_STAGE_EDIT"
            title={`Create edit work order for ${stage.title}`}
            onClick={() => onSubmitAction('edit')}
            style={styles.stageActionButton}
          >
            <PencilLine size={14} />
            Save edit request
          </button>
          <button
            type="button"
            data-qid={`dream:stage-action:ask-agent:${stage.id}`}
            data-qs-action="DREAM_STAGE_ASK_AGENT"
            title={`Ask project agent to repair ${stage.title}`}
            onClick={() => onSubmitAction('ask-agent')}
            style={styles.stageActionButton}
          >
            <Send size={14} />
            Ask agent
          </button>
        </div>
        <div style={styles.stageActionMeta}>
          {actionStatus || `Creates an agent work order for ${run.title}.`}
        </div>
      </div>
  )
}

function WorkOrderInput({
  selectedStage,
  note,
  disabled,
  onNoteChange,
  onCommit,
}: {
  selectedStage: DreamStage | null
  note: string
  disabled: boolean
  onNoteChange: (value: string) => void
  onCommit: () => void
}) {
  return (
    <div data-qid="dream:work-order:constructor" style={styles.workOrderConstructor}>
      <label style={styles.workOrderLabel}>
        Create work order: {selectedStage ? `${phaseNumber(selectedStage.id)} ${phaseShortLabels[selectedStage.id] ?? selectedStage.title}` : 'No phase selected'}
      </label>
      <textarea
        data-qid="dream:agent:prompt"
        data-qs-action="DREAM_AGENT_PROMPT"
        title="Describe the repair required for the selected Dream phase"
        value={note}
        onChange={(event) => onNoteChange(event.target.value)}
        disabled={disabled}
        placeholder="Describe the repair required..."
        style={styles.agentTextarea}
      />
      <button
        type="button"
        data-qid="dream:agent:ask-repair"
        data-qs-action="DREAM_STAGE_ASK_AGENT"
        title="Commit project-agent repair work order"
        disabled={disabled}
        onClick={onCommit}
        style={{ ...styles.commitWorkOrderButton, ...(disabled ? styles.disabledButton : null) }}
      >
        <Send size={14} />
        Commit Work Order
      </button>
    </div>
  )
}

function AgentPane({
  selectedRun,
  selectedStage,
  note,
  activePhaseId,
  research,
  ideaSeed,
  onNoteChange,
  onSubmitAction,
}: {
  selectedRun: DreamRun | null
  selectedStage: DreamStage | null
  note: string
  activePhaseId: string
  research?: ResearchMemoryResult[] | null
  ideaSeed?: string
  onNoteChange: (value: string) => void
  onSubmitAction: (action: StageAction, noteOverride?: string) => void
}) {
  const disabled = !selectedRun || !selectedStage
  const selectedStageStatus = selectedStage ? effectiveStageStatus(selectedStage) : ''
  const selectedStageMissing = /MISSING|BLOCKED|FAIL/i.test(selectedStageStatus)
  const selectedStagePassed = selectedStage != null && statusTone(selectedStageStatus) === 'pass'
  const agentGuidance = (() => {
    if (!selectedStage) return 'Select a Dream run and phase before creating work orders.'
    if (selectedStage.id === '01') {
      return selectedStagePassed
        ? ''
        : 'The Idea Core appears insufficient. Define the character\'s core motivation or the environment\'s physical constraints.'
    }
    if (selectedStage.id === '02') {
      return isStagePassed(selectedStage)
        ? 'Live media descriptions and TOM graph links are present for Phase 02 story generation.'
        : 'Found unlinked memories. Linking them to the protagonist will improve story consistency in Phase 03.'
    }
    if (selectedStage.id === '03') {
      return selectedStageMissing
        ? 'Crew choices exist in the UI, but Phase 03 still needs a saved crew contract JSON artifact in the run folder.'
        : ''
    }
    if (selectedStage.id === '07' && selectedStageMissing) {
      return 'Storyboard reviewer rejected the current panels. The accepted frames must use the required storyboard aspect ratio and prove Embry/Kai visual identity against the reference/contact sheets before this phase can pass.'
    }
    return stageMissingMessage(selectedStage)
  })()
  return (
    <aside data-qid="inspector-pane" className="contextual-inspector panel-container panel-transition" style={styles.agentPane}>
      {research && research.length > 0 && (
        <ResearchPane research={research} ideaSeed={ideaSeed ?? ''} />
      )}
      <div style={styles.agentPaneHeader}>
        <div style={styles.detailEyebrow}>PROJECT AGENT</div>
        <h2 style={styles.agentPaneTitle}>{selectedStagePassed ? 'Phase status' : 'Phase repair chat'}</h2>
      </div>
      <div key={selectedStage?.id ?? 'none'} style={styles.agentContextMotion}>
        <div style={styles.agentContext}>
          <ArtifactField label="Run" value={selectedRun?.title} />
          <ArtifactField label="Active phase" value={selectedStage ? `${phaseNumber(selectedStage.id)} ${phaseShortLabels[selectedStage.id] ?? selectedStage.title}` : undefined} />
          <ArtifactField label="Gate state" value={selectedStage ? statusLabel(selectedStageStatus) : undefined} />
          {selectedRun && (
            <div style={{ fontSize: 10, color: '#64748b', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {selectedRun.runRoot.split('/').pop()}
            </div>
          )}
          <input type="hidden" name="activePhaseId" value={activePhaseId} />
        </div>
        {agentGuidance && (
          <div style={{
            ...(selectedStagePassed ? styles.agentSuccessBox : styles.gapBox),
            ...(selectedStage?.id === '01' || selectedStage?.id === '02' ? nvis.inspectorPrompt : null),
          }}>
            {agentGuidance}
          </div>
        )}
        {selectedStage?.id === '03' && selectedStageMissing && (
          <button
            type="button"
            data-qid="dream:agent:queue-crew-contract"
            data-qs-action="DREAM_QUEUE_CREW_CONTRACT"
            title="Queue Tau creator-reviewer loop to write the missing Phase 03 crew contract artifact"
            disabled={disabled}
            onClick={() => {
              const note = crewTauRepairNote()
              onNoteChange(note)
              onSubmitAction('ask-agent', note)
            }}
            style={{ ...styles.stageActionButton, ...(disabled ? styles.disabledButton : null), marginTop: 10, width: '100%', justifyContent: 'center' }}
          >
            <Send size={14} />
            Queue Crew Contract Build
          </button>
        )}
      </div>
      {!selectedStagePassed && (
        <>
          <WorkOrderInput
            selectedStage={selectedStage}
            note={note}
            disabled={disabled}
            onNoteChange={onNoteChange}
            onCommit={() => onSubmitAction('ask-agent')}
          />
          <div style={styles.stageActionRow}>
            <button
              type="button"
              data-qid="dream:agent:rerun"
              data-qs-action="DREAM_STAGE_RERUN"
              title="Write rerun work order"
              disabled={disabled}
              onClick={() => onSubmitAction('rerun')}
              style={{ ...styles.stageActionButton, ...(disabled ? styles.disabledButton : null) }}
            >
              <Play size={14} />
              Rerun phase
            </button>
          </div>
        </>
      )}
    </aside>
  )
}

function PipelineNav({
  activePhaseId,
  onPhaseChange,
  klingReady,
  processingPhaseId,
  phases,
}: {
  activePhaseId: string
  onPhaseChange: (phaseId: string) => void
  klingReady: boolean
  processingPhaseId?: string | null
  phases?: DreamStage[]
}) {
  const activeStage = phases?.find((stage) => stage.id === activePhaseId)
  const mediaLockCanAdvance = activePhaseId === '08' && !!activeStage && isStagePassed(activeStage)
  const ctaReady = klingReady || mediaLockCanAdvance
  const ctaLabel = mediaLockCanAdvance ? 'Video Provider' : 'Deploy Video'
  const ctaTitle = mediaLockCanAdvance
    ? 'Media lock passed. Continue to Phase 09 Video Provider.'
    : klingReady
      ? 'All phases pass. Submit to selected provider.'
      : 'Blocked: some phases have not passed.'

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (shouldIgnoreDreamPaneArrowKey(e)) return
      const idx = CANONICAL_PHASES.findIndex((p) => p.id === activePhaseId)
      if (idx < 0) return
      if (e.key === 'ArrowRight' && idx < CANONICAL_PHASES.length - 1) {
        e.preventDefault()
        onPhaseChange(CANONICAL_PHASES[idx + 1].id)
      }
      if (e.key === 'ArrowLeft' && idx > 0) {
        e.preventDefault()
        onPhaseChange(CANONICAL_PHASES[idx - 1].id)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activePhaseId, onPhaseChange])

  return (
    <header data-qid="pipeline-nav" style={nvis.pipelineNav}>
      <nav style={nvis.pipelineNavInner} aria-label="Dream pipeline phases">
        {CANONICAL_PHASES.map((p) => {
          const active = activePhaseId === p.id
          const stage = phases?.find((s) => s.id === p.id)
          const tone = stage ? statusTone(stage.status) : 'unknown'
          const iconColor = processingPhaseId === p.id ? '#ffaa00'
            : tone === 'pass' ? '#00ff88'
            : tone === 'blocked' ? '#ff4444'
            : tone === 'dry' ? '#4a9eff'
            : '#64748b'
          return (
            <button
              key={p.id}
              type="button"
              data-qid={`timeline-${p.id}`}
              data-qs-action="DREAM_STAGE_NAVIGATE"
              title={`Phase ${p.id}: ${p.label} · ${stage?.status ?? 'MISSING'}`}
              aria-label={`Navigate to phase ${p.id}: ${p.label}. Status ${statusLabel(stage?.status ?? 'MISSING')}`}
              aria-current={active ? 'step' : undefined}
              onClick={() => onPhaseChange(p.id)}
              style={{
                ...nvis.pipelinePhaseBtn,
                ...(active ? nvis.pipelinePhaseBtnActive : null),
                ...(processingPhaseId === p.id ? { animation: 'dream-pulse 1.5s ease-in-out infinite' } : null),
              }}
            >
              <p.icon size={16} style={{ color: iconColor }} />
              {active && (
                <span style={nvis.pipelinePhaseLabel}>
                  {p.id} {p.label}
                </span>
              )}
              {active && <div style={nvis.pipelineUnderline} />}
            </button>
          )
        })}
      </nav>
      <button
        data-qid="kling-deploy"
        disabled={!ctaReady}
        onClick={() => {
          if (mediaLockCanAdvance) onPhaseChange('09')
        }}
        style={{
          ...nvis.klingDeployBtn,
          ...(ctaReady ? nvis.klingDeployBtnReady : nvis.disabled),
        }}
        title={ctaTitle}
      >
        {ctaLabel}
      </button>
    </header>
  )
}

function KlingGate({ selectedRun, stages }: { selectedRun: DreamRun | null; stages: DreamStage[] }) {
  const upstream = stages.filter((stage) => stage.id !== '12')
  const failing = upstream.filter((stage) => !isStagePassed(stage))
  const allPassed = upstream.length > 0 && failing.length === 0 && !!selectedRun?.paidCallAuthorized
  return (
    <div
      data-qid="dream:kling-gate"
      style={styles.klingGate}
      title={allPassed ? 'Video provider deploy gate is ready.' : `Blocked by: ${failing.map((stage) => phaseNumber(stage.id)).join(', ') || 'missing upstream phases or paid authorization'}`}
    >
      <div style={styles.gateBadgesRow}>
        <GateMiniBadge status={allPassed ? 'KLING_READY' : 'BLOCKED'} label="Gate" />
        <GateMiniBadge status={selectedRun?.paidCallAuthorized ? 'PAID_AUTHORIZED' : 'NO_PAID_AUTH'} label="Auth" />
        <GateMiniBadge status={selectedRun?.klingCalled ? 'KLING_CALLED' : 'NO_KLING_RESPONSE'} label="Return" />
      </div>
      <button
        type="button"
        data-qid="dream:kling:deploy"
        data-qs-action="DREAM_KLING_DEPLOY"
        title={allPassed ? 'Submit accepted packet to selected provider' : `Blocked by: ${failing.map((stage) => phaseNumber(stage.id)).join(', ') || 'missing upstream phases or paid authorization'}`}
        disabled={!allPassed}
        style={{ ...styles.deployButton, ...(allPassed ? styles.deployButtonReady : styles.disabledButton) }}
      >
        {allPassed ? 'Deploy to Provider' : 'Blocked: Review phases'}
      </button>
    </div>
  )
}

export function DreamWorkspace() {
  const [runsResponse, setRunsResponse] = useState<DreamRunsResponse | null>(null)
  const [runDetail, setRunDetail] = useState<DreamRunDetailResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string>('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailRefreshNonce, setDetailRefreshNonce] = useState(0)
  const [stageNotes, setStageNotes] = useState<Record<string, string>>({})
  const [stageActionStatus, setStageActionStatus] = useState<Record<string, string>>({})
  const [railCollapsed, setRailCollapsed] = useState(false)
  const initialDreamStage = (() => {
    if (typeof window === 'undefined') return ''
    const phaseFromLocation = activeDreamPhaseFromLocation()
    if (phaseFromLocation) return phaseFromLocation
    return localStorage.getItem('dream_active_phase') || ''
  })()
  const [selectedStageId, setSelectedStageId] = useState<string>(initialDreamStage)
  useEffect(() => {
    if (selectedStageId) localStorage.setItem('dream_active_phase', selectedStageId)
  }, [selectedStageId])
  useEffect(() => {
    const applyHashPhase = () => {
      const phaseId = activeDreamPhaseFromLocation()
      if (phaseId) setSelectedStageId(phaseId)
    }
    applyHashPhase()
    window.addEventListener('hashchange', applyHashPhase)
    return () => window.removeEventListener('hashchange', applyHashPhase)
  }, [])
  const [processingPhase, setProcessingPhase] = useState<string | null>(null)
  const [pipelineStatus, setPipelineStatus] = useState<'IDLE' | 'ANALYZING' | 'ERROR'>('IDLE')
  const [researchResults, setResearchResults] = useState<ResearchMemoryResult[] | null>(null)
  const [phase02MediaGate, setPhase02MediaGate] = useState<Phase02MediaGate | null>(null)
  const ideaTextRef = useRef('')
  const directionRef = useRef(1)
  const [slideDir, setSlideDir] = useState(1)

  useRegisterAction('dream:button:refresh', {
    app: 'ux-lab',
    action: 'DREAM_REFRESH_RUNS',
    label: 'Refresh Dream runs',
    description: 'Reload persona-dream video provider run artifacts',
  })
  useRegisterAction('dream:input:search', {
    app: 'ux-lab',
    action: 'DREAM_SEARCH_RUNS',
    label: 'Search Dream runs',
    description: 'Filter persona-dream run artifacts by title, status, or path',
  })
  useRegisterAction('dream:item:run', {
    app: 'ux-lab',
    action: 'DREAM_SELECT_RUN',
    label: 'Select Dream run',
    description: 'Open a persona-dream video provider run artifact',
  })
  useRegisterAction('dream:stage:navigate', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_NAVIGATE',
    label: 'Navigate Dream stage',
    description: 'Jump to a persona-dream pipeline phase panel',
  })
  useRegisterAction('dream:stage:rerun', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_RERUN',
    label: 'Rerun Dream stage',
    description: 'Create a persona-dream stage rerun work order for the project agent',
  })
  useRegisterAction('dream:stage:edit', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_EDIT',
    label: 'Edit Dream stage',
    description: 'Create a persona-dream stage edit work order with human or project-agent repair notes',
  })
  useRegisterAction('dream:stage:ask-agent', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_ASK_AGENT',
    label: 'Ask Dream project agent',
    description: 'Create a project-agent repair work order for the selected Dream stage',
  })
  useRegisterAction('dream:voice:preview', {
    app: 'ux-lab',
    action: 'DREAM_VOICE_PREVIEW',
    label: 'Preview Dream voice',
    description: 'Preview Orpheus/TTS voice evidence when a speaking character voice is ready',
  })
  useRegisterAction('dream:kling:deploy', {
    app: 'ux-lab',
    action: 'DREAM_KLING_DEPLOY',
    label: 'Deploy Dream packet to provider',
    description: 'Submit to the selected video provider only when all upstream preflight gates pass and paid-call authorization is present',
  })
  useRegisterAction('dream:stage:edit-notes', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_EDIT_NOTES',
    label: 'Edit Dream stage notes',
    description: 'Capture repair notes for a persona-dream stage work order',
  })
  useRegisterAction('dream:rail:toggle', {
    app: 'ux-lab',
    action: 'DREAM_RAIL_TOGGLE',
    label: 'Toggle Dream run rail',
    description: 'Collapse or expand the Dream run list rail',
  })
  useRegisterAction('dream:idea:composer', {
    app: 'ux-lab',
    action: 'DREAM_IDEA_COMPOSE',
    label: 'Compose Dream idea',
    description: 'Type a core idea that drives debounced Brave Search and memory recall for the masonry board',
  })
  useRegisterAction('dream:memory:open-media', {
    app: 'ux-lab',
    action: 'DREAM_MEMORY_OPEN_MEDIA',
    label: 'Open memory media',
    description: 'Open a memory image, video, or audio asset in the floating preview inspector',
  })
  useRegisterAction('dream:memory:close-media', {
    app: 'ux-lab',
    action: 'DREAM_MEMORY_CLOSE_MEDIA',
    label: 'Close memory media',
    description: 'Close the floating memory media preview inspector',
  })
  useRegisterAction('dream:memory:link', {
    app: 'ux-lab',
    action: 'DREAM_MEMORY_LINK',
    label: 'Link memory to entity',
    description: 'Associate a memory residue card with a detected story entity',
  })
  useRegisterAction('dream:memory:trace-graph', {
    app: 'ux-lab',
    action: 'DREAM_MEMORY_TRACE_GRAPH',
    label: 'Open memory trace graph',
    description: 'Open the D3 Theory-of-Mind relationship graph for a recalled memory card',
  })

  const loadRuns = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch('/api/projects/dream/runs')
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json() as DreamRunsResponse
      setRunsResponse(data)
      setSelectedId((current) => current || data.runs[0]?.id || '')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setRunsResponse(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadRuns()
  }, [])

  const filteredRuns = useMemo(() => {
    const runs = runsResponse?.runs ?? []
    const needle = query.trim().toLowerCase()
    if (!needle) return runs
    return runs.filter((run) => [
      run.title,
      run.id,
      run.status,
      run.source,
      run.runRoot,
    ].some((value) => value.toLowerCase().includes(needle)))
  }, [query, runsResponse?.runs])

  const selectedRun = useMemo(() => {
    return filteredRuns.find((run) => run.id === selectedId) ?? filteredRuns[0] ?? null
  }, [filteredRuns, selectedId])

  useEffect(() => {
    if (selectedRun && selectedRun.id !== selectedId) setSelectedId(selectedRun.id)
  }, [selectedId, selectedRun])

  useEffect(() => {
    if (!selectedRun) {
      setRunDetail(null)
      return
    }
    const controller = new AbortController()
    setDetailLoading(true)
    setDetailError(null)
    fetch(`/api/projects/dream/run-detail?root=${encodeURIComponent(selectedRun.runRoot)}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return await response.json() as DreamRunDetailResponse
      })
      .then((data) => {
        ideaTextRef.current = data.consumers?.humanIdea?.text ?? ''
        setRunDetail(data)
      })
      .catch((err) => {
        if ((err as Error).name !== 'AbortError') {
          setDetailError(err instanceof Error ? err.message : String(err))
          setRunDetail(null)
        }
      })
      .finally(() => setDetailLoading(false))
    return () => controller.abort()
  }, [selectedRun?.runRoot, detailRefreshNonce])

  useEffect(() => {
    const raw = runDetail?.stages ?? []
    if (raw.length === 0) {
      setSelectedStageId('')
      return
    }
    const canonical = normalizeToCanonicalPhases(raw)
    const hashStageId = activeDreamPhaseFromLocation()
    if (hashStageId && canonical.some((stage) => stage.id === hashStageId)) {
      if (selectedStageId !== hashStageId) setSelectedStageId(hashStageId)
      return
    }
    if (!canonical.some((stage) => stage.id === selectedStageId)) {
      setSelectedStageId(canonical[0].id)
    }
  }, [runDetail?.stages, selectedStageId])

  const resolveLegacyStageId = (canonicalId: string): string => {
    const raw = runDetail?.stages ?? []
    const phase = CANONICAL_PHASES.find(p => p.id === canonicalId)
    if (!phase) return canonicalId
    const matching = raw.find(s => (phase.legacyIds as readonly string[]).includes(s.id))
    return matching?.id ?? canonicalId
  }

  const submitStageAction = async (stageId: string, action: StageAction, noteOverride?: string) => {
    if (!selectedRun) return
    setStageActionStatus((current) => ({ ...current, [stageId]: 'writing work order...' }))
    const requestedBy = action === 'ask-agent' ? 'project_agent' : 'human'
    const backendAction = action === 'edit' ? 'edit' : 'rerun'
    const stageNote = noteOverride ?? stageNotes[stageId] ?? ''
    const notes = action === 'ask-agent'
      ? `[project-agent repair request]\n${stageNote}`.trim()
      : stageNote
    if (noteOverride != null) {
      setStageNotes((current) => ({ ...current, [stageId]: noteOverride }))
    }
    const backendStageId = resolveLegacyStageId(stageId)
    try {
      const response = await fetch('/api/projects/dream/stage-work-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          runRoot: selectedRun.runRoot,
          stageId: backendStageId,
          action: backendAction,
          requestedBy,
          notes,
        }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.error ?? `HTTP ${response.status}`)
      setStageActionStatus((current) => ({
        ...current,
        [stageId]: `work order: ${payload.workOrderPath}`,
      }))
      setDetailRefreshNonce((value) => value + 1)
    } catch (err) {
      setStageActionStatus((current) => ({
        ...current,
        [stageId]: `work order failed: ${err instanceof Error ? err.message : String(err)}`,
      }))
    }
  }

  const navigateToStage = (stageId: string) => {
    const oldIdx = CANONICAL_PHASES.findIndex((p) => p.id === selectedStageId)
    const newIdx = CANONICAL_PHASES.findIndex((p) => p.id === stageId)
    const dir = newIdx >= oldIdx ? 1 : -1
    directionRef.current = dir
    setSlideDir(dir)
    setSelectedStageId(stageId)
    const slug = dreamPhaseHashById[stageId]
    if (slug) {
      const path = window.location.pathname.replace(/\/+$/, '')
      const hashParts = window.location.hash.replace(/^#/, '').split('/').filter(Boolean)
      const nextUrl = path === '/dream'
        ? `/dream#${slug}`
        : hashParts[0] === 'dream' || path === '' || path === '/'
          ? `/#dream/${slug}`
          : `/dream#${slug}`
      if (`${window.location.pathname}${window.location.hash}` !== nextUrl) {
        window.history.replaceState(null, '', nextUrl)
      }
    }
  }

  const pendingIdeaRef = useRef<string | null>(null)

  const handleAutoExtract = async (ideaText: string) => {
    if (!selectedRun) {
      pendingIdeaRef.current = ideaText
      return
    }
    ideaTextRef.current = ideaText
    setProcessingPhase('02')
    setPipelineStatus('ANALYZING')

    try {
      const [searchRes, memoryRes] = await Promise.all([
        fetch('/api/projects/dream/brave-search', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: ideaText }),
        }),
        fetch('/api/memory/recall', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            q: `Embry Kai surf Big Island media contact sheets audio video ${ideaText}`,
            collections: ['persona_memory'],
            tags: ['persona:embry'],
            k: 24,
          }),
        }),
      ])
      const allResults: ResearchMemoryResult[] = []
      const webResults: ResearchMemoryResult[] = []
      if (searchRes.ok) {
        const searchData = await searchRes.json()
        if (searchData.results?.length > 0) webResults.push(...searchData.results)
      }
      if (memoryRes.ok) {
        const memoryData = await memoryRes.json()
        const nodes = Array.isArray(memoryData.items)
          ? memoryData.items as Array<Record<string, unknown>>
          : Array.isArray(memoryData.results)
            ? memoryData.results as Array<Record<string, unknown>>
            : Array.isArray(memoryData.nodes)
              ? memoryData.nodes as Array<Record<string, unknown>>
              : []
        const keys = [...new Set(nodes
          .map((node) => typeof node._key === 'string' ? node._key : extractPersonaMemoryKey({
            id: dreamStringField(node, ['id', 'title', 'name', 'label']),
            label: dreamStringField(node, ['description', 'text', 'retrieval_text', 'content']),
            subtitle: dreamStringField(node, ['snippet', 'summary']),
            imageUrl: dreamStringField(node, ['source_path', 'image_path', 'url', 'path']),
            mediaType: dreamStringField(node, ['media_type', 'asset_type']),
          }))
          .filter((key): key is string => Boolean(key)))]
        const hydratedDocs = keys.length > 0
          ? await memoryByKeysDocuments('persona_memory', keys.slice(0, 24), undefined, [
            '_key',
            'title',
            'name',
            'label',
            'description',
            'media_description',
            'vlm_description',
            'video_description',
            'audio_caption',
            'text_summary',
            'story_prompt_summary',
            'summary',
            'text',
            'retrieval_text',
            'content',
            'source_path',
            'image_path',
            'thumbnail_path',
            'poster_path',
            'keyframe_path',
            'url',
            'asset_url',
            'public_url',
            'path',
            'media_type',
            'mime_type',
            'asset_type',
            'persona_id',
          ]).catch(() => [])
          : []
        const hydratedByKey = new Map(hydratedDocs.map((doc) => [String(doc._key ?? ''), doc]))
        nodes.slice(0, 18).forEach((node, index) => {
          const key = typeof node._key === 'string' ? node._key : keys[index]
          const hydrated = key ? hydratedByKey.get(key) : undefined
          const doc = hydrated ? { ...node, ...hydrated, score: node.score } : node
          const result = dreamMemoryResultFromDocument(doc, index)
          if (result.url || result.snippet || result.title) allResults.push(result)
        })
      }
      const rankedResults = [...allResults, ...webResults]
        .sort((a, b) => dreamMemoryResultPriority(a) - dreamMemoryResultPriority(b))
      if (rankedResults.length > 0) setResearchResults(rankedResults)
      setProcessingPhase(null)
      setPipelineStatus('IDLE')
    } catch {
      setPipelineStatus('ERROR')
      setProcessingPhase(null)
    }
  }

  useEffect(() => {
    if (selectedRun && pendingIdeaRef.current) {
      const idea = pendingIdeaRef.current
      pendingIdeaRef.current = null
      handleAutoExtract(idea)
    }
  }, [selectedRun?.id])

  useEffect(() => {
    let cancelled = false
    loadPhase02MediaGate()
      .then((gate) => {
        if (!cancelled) setPhase02MediaGate(gate)
      })
      .catch(() => {
        if (!cancelled) {
          setPhase02MediaGate({
            status: 'MISSING',
            describedCount: 0,
            requiredCount: phase02RequiredMediaKeys.length + phase02RequiredTextKeys.length,
            personaEdgeCount: 0,
            tomEdgeCount: 0,
          })
        }
      })
    return () => { cancelled = true }
  }, [selectedRun?.id])

  const backendStages = runDetail?.stages ?? []
  const revisionQualified = (runDetail?.revisionQualification as RevisionQualification | undefined)?.state === 'ACTIVE_CONSISTENT'
  const stages = useMemo(() => {
    const normalized = normalizeToCanonicalPhases(backendStages)
    if (!revisionQualified || phase02MediaGate?.status !== 'PASS') return normalized
    return normalized.map((stage) => stage.id === '02'
      ? {
          ...stage,
          status: 'PASS',
          summary: `Live media/story memory gate passed: ${phase02MediaGate.describedCount}/${phase02MediaGate.requiredCount} required assets and text memories described; ${phase02MediaGate.personaEdgeCount} media edges and ${phase02MediaGate.tomEdgeCount} TOM edges found.`,
          failureOrGap: null,
        }
      : stage)
  }, [backendStages, phase02MediaGate, revisionQualified])
  const selectedStage = stages.find((stage) => stage.id === selectedStageId) ?? stages[0] ?? null
  const klingReady = revisionQualified && stages.length > 0 && stages.every((p) => isStagePassed(p)) && !!selectedRun?.paidCallAuthorized

  const pageVariants = {
    initial: (dir: number) => ({ opacity: 0, x: dir > 0 ? 20 : -20 }),
    in: { opacity: 1, x: 0, transition: { duration: 0.2, ease: [0.22, 1, 0.36, 1] } },
    out: (dir: number) => ({ opacity: 0, x: dir > 0 ? -20 : 20, transition: { duration: 0.15 } }),
  }

  return (
    <div
      data-qid="dream:workspace"
      style={{
        ...styles.workspace,
        gridTemplateColumns: railCollapsed ? '56px minmax(0, 1fr) 340px' : '320px minmax(0, 1fr) 340px',
      }}
    >
      <style>{`
        @keyframes dream-phase-fade-up {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes dream-agent-slide {
          from { opacity: 0; transform: translateX(10px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes slide-in-right {
          from { opacity: 0; transform: translateX(20px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes slide-in-left {
          from { opacity: 0; transform: translateX(-20px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes dream-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        @keyframes dream-soft-fade {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        [data-qid="dream:idea:composer"][data-empty="true"]::before {
          content: "What is the intent of this session?";
          color: #334155;
          pointer-events: none;
        }
        [data-qid="dream:idea:composer"]:hover,
        [data-qid="dream:idea:composer"]:focus {
          border-bottom-color: rgba(74, 158, 255, 0.42) !important;
        }
        [data-qid="dream:idea:composer"] + div:hover {
          opacity: 1 !important;
        }
        .idea-edit-affordance {
          opacity: 1;
          transition: color 180ms ease, border-color 180ms ease, background 180ms ease;
        }
        .dream-phase-content {
          will-change: transform, opacity;
          backface-visibility: hidden;
          perspective: 1000px;
        }
        .contextual-inspector {
          box-shadow: -10px 0 20px rgba(0,0,0,0.3);
          background: #111111;
        }
        [data-qid="contact-sheet-grid"] {
          padding: 1rem;
          background: #111111;
          border-radius: 4px;
        }
        .contact-sheet-card:hover .contact-sheet-overlay {
          opacity: 1 !important;
        }
        .memory-link-select, .memory-media-overlay { opacity: 0; transition: opacity 200ms ease, transform 200ms ease, color 160ms ease; }
        .memory-masonry-board {
          column-width: 220px;
          column-gap: 24px;
        }
        @media (max-width: 760px) {
          .memory-masonry-board { column-width: 100%; }
        }
        .memory-masonry-card {
          break-inside: avoid;
          page-break-inside: avoid;
          margin-bottom: 24px;
        }
        .memory-masonry-card:hover .memory-link-select,
        .memory-masonry-card:focus-within .memory-link-select { opacity: 1; }
        .memory-masonry-card:hover {
          transform: translateY(-4px);
        }
        .memory-masonry-card:hover,
        .memory-masonry-card:focus-within {
          border-color: rgba(74, 158, 255, 0.32) !important;
          box-shadow: 0 16px 34px rgba(0, 0, 0, 0.22) !important;
        }
        .memory-masonry-card-media:hover img,
        .memory-masonry-card-media:hover video,
        .memory-masonry-card-media:focus-within img,
        .memory-masonry-card-media:focus-within video {
          transform: scale(1.045);
        }
        .memory-masonry-card:hover .memory-card-shelf,
        .memory-masonry-card:focus-within .memory-card-shelf {
          transform: translateY(0) !important;
        }
        .memory-card-shelf {
          transform: translateY(100%);
        }
        .text-node-well {
          position: relative;
          padding: 12px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          background: #0c0c0c;
        }
        .text-node-content-wrap {
          position: relative;
          max-height: 126px;
          overflow: hidden;
          cursor: pointer;
        }
        .text-node-content {
          font-size: 14px;
          line-height: 1.5;
          color: #e2e8f0;
        }
        .text-node-fade {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 32px;
          background: linear-gradient(to bottom, transparent, #0c0c0c);
          pointer-events: none;
        }
        .text-node-actions {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          padding: 6px 12px;
          background: rgba(0, 0, 0, 0.75);
          backdrop-filter: blur(4px);
          border-radius: 16px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          display: flex;
          gap: 8px;
          transition: opacity 0.2s;
        }
        .text-node-actions button {
          color: rgba(255, 255, 255, 0.55);
          transition: color 0.15s ease;
        }
        .text-node-actions button:hover {
          color: rgba(255, 255, 255, 0.85) !important;
        }

      `}</style>
      <aside data-qid="dream:rail:runs" style={railCollapsed ? { ...styles.rail, ...styles.railCollapsed } : styles.rail}>
        <div style={railCollapsed ? styles.railCollapsedHeader : styles.railHeader}>
          {railCollapsed ? (
            <button
              type="button"
              data-qid="dream:rail:toggle"
              data-qs-action="DREAM_RAIL_TOGGLE"
              title="Expand Dream run list"
              onClick={() => setRailCollapsed(false)}
              style={styles.iconButton}
            >
              <ChevronRight size={16} />
            </button>
          ) : null}
          {!railCollapsed && (
            <>
          <div style={styles.railTitleRow}>
            <div>
              <div style={styles.eyebrow}>Dream Library</div>
              <h2 style={styles.railTitle}>Persona Dream</h2>
            </div>
            <button
              type="button"
              data-qid="dream:rail:toggle"
              data-qs-action="DREAM_RAIL_TOGGLE"
              title="Collapse Dream run list"
              onClick={() => setRailCollapsed(true)}
              style={styles.iconButton}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              data-qid="dream:button:refresh"
              data-qs-action="DREAM_REFRESH_RUNS"
              title="Refresh Dream runs"
              onClick={() => {
                void loadRuns()
                setDetailRefreshNonce((value) => value + 1)
              }}
              style={styles.iconButton}
            >
              <RefreshCw size={16} style={loading ? styles.spinIcon : undefined} />
            </button>
          </div>
          <label style={styles.searchWrap}>
            <Search size={16} color="#64748b" />
            <input
              data-qid="dream:input:search"
              data-qs-action="DREAM_SEARCH_RUNS"
              title="Search Dream runs"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter runs, status, paths"
              style={styles.searchInput}
            />
          </label>
            </>
          )}
        </div>

        {!railCollapsed && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            {loading && <div style={{ ...styles.stateBox, margin: 12 }}>Loading source artifacts...</div>}
            {!loading && error && <div style={{ ...styles.errorBox, margin: 12 }}>Dream run source unavailable: {error}</div>}
            {!loading && !error && filteredRuns.length === 0 && (
              <div style={{ ...styles.emptyBox, margin: 12 }}>
                No persona-dream runs matched the current filter.
              </div>
            )}
            {!loading && !error && filteredRuns.length > 0 && (
              <>
                <div style={{ padding: '14px 14px 6px' }}>
                  <div style={{ color: '#4a9eff', fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 700, marginBottom: 10 }}>Active Preflight</div>
                  {filteredRuns.filter((r) => r.status === 'RUNNING' || r.status === 'LIVE' || r.status === 'active').length === 0 && (
                    <div style={{ color: '#64748b', fontSize: 13, fontStyle: 'italic', marginBottom: 10 }}>No active runs</div>
                  )}
                  {filteredRuns.filter((r) => r.status === 'RUNNING' || r.status === 'LIVE' || r.status === 'active').map((run) => (
                    <button
                      key={`active-${run.id}`}
                      type="button"
                      data-qid={`dream:item:run:${run.id}`}
                      data-qs-action="DREAM_SELECT_RUN"
                      title={`Open Dream run: ${run.title}`}
                      onClick={() => setSelectedId(run.id)}
                      style={{
                        ...styles.runCard,
                        ...(selectedRun?.id === run.id ? styles.runCardSelected : null),
                        marginBottom: 8,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 14, fontWeight: 700, color: '#e2e8f0' }}>{run.title}</span>
                        <span style={{ color: '#00ff88', fontSize: 11, letterSpacing: '0.06em' }}>● LIVE</span>
                      </div>
                    </button>
                  ))}
                </div>
                <div style={{ flex: 1, overflow: 'auto', padding: '6px 14px 14px' }}>
                  <div style={{ color: '#64748b', fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 10 }}>Archives</div>
                  {filteredRuns.filter((r) => r.status !== 'RUNNING' && r.status !== 'LIVE' && r.status !== 'active').map((run) => (
                    <button
                      key={`archive-${run.id}`}
                      type="button"
                      data-qid={`dream:item:run:${run.id}`}
                      data-qs-action="DREAM_SELECT_RUN"
                      title={`Open Dream run: ${run.title}`}
                      onClick={() => setSelectedId(run.id)}
                      style={{
                        display: 'block',
                        width: '100%',
                        textAlign: 'left',
                        padding: '10px 0',
                        border: 'none',
                        borderBottom: '1px solid rgba(255,255,255,0.06)',
                        background: 'transparent',
                        color: selectedRun?.id === run.id ? '#e2e8f0' : '#64748b',
                        fontSize: 13,
                        cursor: 'pointer',
                      }}
                    >
                      {run.title}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </aside>

      <section data-qid="dream:detail" style={styles.detail}>
        {selectedRun ? (
          <>
	          <PipelineNav
	            activePhaseId={selectedStage?.id ?? ''}
	            onPhaseChange={navigateToStage}
	            klingReady={klingReady}
	            phases={stages}
	          />
          <div style={styles.stageBoard}>
            {detailLoading && <div style={styles.stateBox}>Loading pipeline phase cards...</div>}
            {detailError && <div style={styles.errorBox}>Stage detail unavailable: {detailError}</div>}
            {!detailLoading && !detailError && stages.length === 0 && (
              <div style={styles.emptyBox}>No stage ledger was found for this run. This remains blocked until source stage artifacts exist.</div>
            )}
            {!detailLoading && selectedStage && (
              <AnimatePresence mode="popLayout" custom={slideDir}>
                <motion.div
                  key={selectedStage.id}
                  id={`dream-stage-${selectedStage.id}`}
                  className="dream-phase-content"
                  custom={slideDir}
                  variants={pageVariants as any}
                  initial="initial"
                  animate="in"
                  exit="out"
                  style={styles.stageAnchor}
                >
                  <StageCard
                  run={selectedRun}
                  stage={selectedStage}
                  note={stageNotes[selectedStage.id] ?? ''}
                  actionStatus={stageActionStatus[selectedStage.id]}
                  allStages={stages}
                  researchSeed={researchResults?.map((r) => r.title + ' ' + r.snippet).join(' ')}
                  ideaText={ideaTextRef.current}
                  memoryResults={researchResults}
                  storyboardProjection={runDetail?.consumers?.storyboard}
                  humanIdea={runDetail?.consumers?.humanIdea}
                  revisionQualified={revisionQualified}
                  onTriggerMemories={handleAutoExtract}
                  onNoteChange={(value) => setStageNotes((current) => ({ ...current, [selectedStage.id]: value }))}
                  onSubmitAction={(action, noteOverride) => void submitStageAction(selectedStage.id, action, noteOverride)}
                />
              </motion.div>
            </AnimatePresence>
            )}
          </div>
          </>
        ) : (
          <div style={styles.noReport}>
            <ShieldAlert size={40} color="#fcd34d" />
            <div style={styles.noReportTitle}>Dream project has no source runs</div>
            <p style={styles.noReportCopy}>No placeholder data is shown. Add or generate persona-dream artifacts, then refresh this project.</p>
          </div>
        )}
      </section>
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
        <AgentPane
          selectedRun={selectedRun}
          selectedStage={selectedStage}
          note={selectedStage ? stageNotes[selectedStage.id] ?? '' : ''}
          activePhaseId={selectedStageId}
          research={researchResults}
          ideaSeed={ideaTextRef.current}
          onNoteChange={(value) => {
            if (!selectedStage) return
            setStageNotes((current) => ({ ...current, [selectedStage.id]: value }))
          }}
          onSubmitAction={(action, noteOverride) => {
            if (!selectedStage) return
            void submitStageAction(selectedStage.id, action, noteOverride)
          }}
        />
      </div>
    </div>
  )
}

