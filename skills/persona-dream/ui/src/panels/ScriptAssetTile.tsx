/**
 * ScriptAssetTile, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { chooseCrewPersona, compactCrewText, crewFitRationale, crewRoleCriteria, crewTauRepairNote, scoreCrewPersona } from '../lib/crew'
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { nvis } from '../styles'
import { FileText, Film, Volume2 } from 'lucide-react'

export function ScriptAssetTile({ asset }: { asset: LinkedStoryAsset }) {
  const [broken, setBroken] = useState(false)
  const mediaType = dreamInferMediaType(asset.url, asset.mediaType)
  const isImage = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'avif'].includes(mediaType)
  const isVideo = ['mp4', 'mov', 'webm', 'avi'].includes(mediaType)
  const isAudio = ['wav', 'mp3', 'ogg'].includes(mediaType)
  const Icon = isAudio ? Volume2 : isVideo ? Film : isImage ? Image : FileText
  const label = asset.title || asset.id
  return (
    <button
      type="button"
      data-qid={`dream:script:asset:${asset.id}`}
      title={`${label}${asset.description ? ` — ${asset.description}` : ''}`}
      onClick={() => asset.url && window.open(asset.url, '_blank', 'noopener,noreferrer')}
      style={nvis.scriptAssetTile}
    >
      {isImage && asset.url && !broken ? (
        <img
          src={asset.url}
          alt={label}
          style={nvis.scriptAssetThumb}
          onError={() => setBroken(true)}
        />
      ) : (
        <span style={nvis.scriptAssetFallback}>
          <Icon size={18} />
        </span>
      )}
      <span style={nvis.scriptAssetTitle}>{compactCrewText(label, 58)}</span>
      <span style={nvis.scriptAssetMeta}>{isAudio ? 'audio' : isVideo ? 'video' : isImage ? 'image' : 'text'}</span>
    </button>
  )
}
