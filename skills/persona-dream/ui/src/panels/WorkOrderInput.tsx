/**
 * WorkOrderInput, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { activeDreamPhaseFromLocation, dreamPhaseHashAliases, dreamPhaseHashById, normalizeToCanonicalPhases, phaseNumber, phaseShortLabels } from '../lib/phase'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { Send } from 'lucide-react'

export function WorkOrderInput({
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
