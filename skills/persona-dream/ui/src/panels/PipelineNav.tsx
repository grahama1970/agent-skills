/**
 * PipelineNav, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { CANONICAL_PHASES, DREAM_SCRIPT_DRAFT_STORAGE_KEY, DREAM_SCRIPT_STATUS_STORAGE_KEY, DREAM_STORY_DRAFT_STORAGE_KEY, DREAM_STORY_STATUS_STORAGE_KEY, crewGateMatchTerms, crewMissingEvidenceFields, phase02RequiredMediaKeys, phase02RequiredTextKeys, phaseIcons, splitStoryObjects, storyRowCategory, storyboardReviewerChecklist, textEncoder, videoProviderFitColumns } from '../constants'
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from '../lib/stage'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from '../lib/status'
import { nvis } from '../styles'

export function PipelineNav({
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
