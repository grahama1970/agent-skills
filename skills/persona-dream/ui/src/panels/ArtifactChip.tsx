/**
 * ArtifactChip, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { FileJson } from 'lucide-react'

export function ArtifactChip({
  artifact,
  style = styles.artifactChip,
  iconSize = 13,
  label,
  title,
}: {
  artifact: DreamStage['artifacts'][number]
  style?: CSSProperties
  iconSize?: number
  label?: string
  title?: string
}) {
  const displayLabel = label ?? artifact.label
  return (
    <a
      href={`/api/projects/dream/asset?path=${encodeURIComponent(artifact.path)}`}
      target="_blank"
      rel="noreferrer"
      title={title ?? artifact.label}
      style={style}
    >
      <FileJson size={iconSize} />
      <span style={styles.receiptPillLabel}>{displayLabel}</span>
    </a>
  )
}
