/**
 * ProviderReturnPanel, extracted from DreamWorkspace.tsx.
 */
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'

export function ProviderReturnPanel({ stage }: { stage: DreamStage }) {
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
        src={(video as { url?: string }).url ?? `/api/projects/dream/asset?path=${encodeURIComponent(video.path)}`}
        controls
        preload="metadata"
        playsInline
        style={{ width: '100%', maxHeight: 480, borderRadius: 12, background: '#000', border: '1px solid rgba(148,163,184,0.25)' }}
      />
      <p style={{ margin: 0, fontSize: 12, color: 'rgba(148,163,184,0.9)' }}>{video.label}</p>
    </section>
  )
}
