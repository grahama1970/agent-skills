/**
 * StageEvidence, extracted from DreamWorkspace.tsx.
 */
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from '../lib/status'
import { fileNameFromPath } from '../lib/text'
import { ArtifactChip } from './ArtifactChip'

export function StageEvidence({ stage }: { stage: DreamStage }) {
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
