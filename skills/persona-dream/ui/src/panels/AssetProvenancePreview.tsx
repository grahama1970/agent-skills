/**
 * AssetProvenancePreview, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { nvis } from '../styles'
import { Film, Volume2 } from 'lucide-react'

export function AssetProvenancePreview({ asset }: { asset: LinkedStoryAsset }) {
  const [broken, setBroken] = useState(false)
  const mediaType = dreamInferMediaType(asset.url, asset.mediaType)
  const isImage = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'svg', 'avif'].includes(mediaType)
  const isAudio = ['wav', 'mp3', 'ogg', 'flac', 'm4a'].includes(mediaType)
  const Icon = isAudio ? Volume2 : Film

  if (isImage && !broken) {
    return <img src={asset.url} alt={asset.title} style={nvis.assetThumbImage} onError={() => setBroken(true)} />
  }
  return (
    <span aria-label={isAudio ? 'Audio asset' : 'Video asset'} style={{ ...nvis.scriptAssetFallback, width: '100%', height: '100%' }}>
      <Icon size={18} />
    </span>
  )
}
