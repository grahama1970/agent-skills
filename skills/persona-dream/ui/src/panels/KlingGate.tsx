/**
 * KlingGate, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { activeDreamPhaseFromLocation, dreamPhaseHashAliases, dreamPhaseHashById, normalizeToCanonicalPhases, phaseNumber, phaseShortLabels } from '../lib/phase'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from '../lib/stage'
import { GateMiniBadge } from './GateMiniBadge'

export function KlingGate({ selectedRun, stages }: { selectedRun: DreamRun | null; stages: DreamStage[] }) {
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
