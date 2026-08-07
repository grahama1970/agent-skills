/**
 * StageGateAlert, extracted from DreamWorkspace.tsx.
 */
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { nvis } from '../styles'
import { AlertTriangle } from 'lucide-react'

export function StageGateAlert({ stage }: { stage: DreamStage }) {
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
