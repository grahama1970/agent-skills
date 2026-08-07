/**
 * StageCardHeader, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { activeDreamPhaseFromLocation, dreamPhaseHashAliases, dreamPhaseHashById, normalizeToCanonicalPhases, phaseNumber, phaseShortLabels } from '../lib/phase'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from '../lib/stage'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from '../lib/status'
import { PhaseIcon } from './PhaseIcon'
import { StatusBadge } from './StatusBadge'
import { Copy } from 'lucide-react'

export function StageCardHeader({ stage }: { stage: DreamStage }) {
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
