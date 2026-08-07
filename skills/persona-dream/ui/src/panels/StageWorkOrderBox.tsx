/**
 * StageWorkOrderBox, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { PencilLine, Play, Send } from 'lucide-react'

export function StageWorkOrderBox({
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
