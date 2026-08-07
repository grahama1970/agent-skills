import { ResearchPane } from './ResearchPane'
/**
 * AgentPane, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { chooseCrewPersona, compactCrewText, crewFitRationale, crewRoleCriteria, crewTauRepairNote, scoreCrewPersona } from '../lib/crew'
import { activeDreamPhaseFromLocation, dreamPhaseHashAliases, dreamPhaseHashById, normalizeToCanonicalPhases, phaseNumber, phaseShortLabels } from '../lib/phase'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from '../lib/stage'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from '../lib/status'
import { nvis } from '../styles'
import { ArtifactField } from './ArtifactField'
import { WorkOrderInput } from './WorkOrderInput'
import { Play, Send } from 'lucide-react'

export function AgentPane({
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
