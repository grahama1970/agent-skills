/**
 * StageCard, extracted from DreamWorkspace.tsx.
 */
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { buildLiveMemoryTraceGraph, dreamMemoryResultFromDocument, dreamMemoryResultPriority, extractKnownMemoryFieldText, extractPersonaMemoryKey, humanMemoryCaption, linkedStoryAssetFromMemoryResult, memoryConnectionPalette, memoryConnectionSignals, mergeMemoryTomGraph, personaMemoryThumbCache, readableMemoryText, readableMemoryValue, stripLeadingMemoryFieldLabels } from '../lib/memory'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from '../lib/stage'
import { nvis } from '../styles'
import { ContactSheetBoard } from './ContactSheetBoard'
import { CrewConsole } from './CrewConsole'
import { IdeaMemoryControl } from './IdeaMemoryControl'
import { MediaLockPanel } from './MediaLockPanel'
import { ProviderContractPanel } from './ProviderContractPanel'
import { ProviderReturnPanel } from './ProviderReturnPanel'
import { ScriptConsole } from './ScriptConsole'
import { StageCardHeader } from './StageCardHeader'
import { StageEvidence } from './StageEvidence'
import { StageGateAlert } from './StageGateAlert'
import { StoryMatrix } from './StoryMatrix'
import { StoryboardConsole } from './StoryboardConsole'
import { VideoProviderPanel } from './VideoProviderPanel'
import { VoiceBoard } from './VoiceBoard'

export function StageCard({
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
