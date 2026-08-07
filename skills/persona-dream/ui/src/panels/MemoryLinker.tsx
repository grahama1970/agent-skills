/**
 * MemoryLinker, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { buildLiveMemoryTraceGraph, dreamMemoryResultFromDocument, dreamMemoryResultPriority, extractKnownMemoryFieldText, extractPersonaMemoryKey, humanMemoryCaption, linkedStoryAssetFromMemoryResult, memoryConnectionPalette, memoryConnectionSignals, mergeMemoryTomGraph, personaMemoryThumbCache, readableMemoryText, readableMemoryValue, stripLeadingMemoryFieldLabels } from '../lib/memory'
import { buildCardTraceGraph } from '../lib/trace'
import { nvis } from '../styles'
import { MediaModal } from './MediaModal'
import { TextExpandModal } from './TextExpandModal'
import { TraceGraphOverlay } from './TraceGraphOverlay'
import { ChevronRight, GitBranch, Share2, Volume2 } from 'lucide-react'

export function MemoryLinker({
  memory,
  ideaText,
  entitySuggestions,
  activeConnection,
  onConnectionHover,
  onLink,
  onDragStart,
}: {
  memory: { id: string; label: string; score?: number; subtitle?: string; imageUrl?: string; mediaType?: string; memoryKey?: string; mediaUrl?: string }
  ideaText: string
  entitySuggestions: string[]
  activeConnection: string | null
  onConnectionHover: (connectionId: string | null) => void
  onLink: (memoryId: string, entity: string) => void
  onDragStart?: (id: string, label: string) => void
}) {
  const [linking, setLinking] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [graphAnchor, setGraphAnchor] = useState<TraceAnchorRect | null>(null)
  const [hovered, setHovered] = useState(false)
  const [textModalOpen, setTextModalOpen] = useState(false)
  const textRef = useRef<HTMLDivElement>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [showFade, setShowFade] = useState(false)
  const [audioPlaying, setAudioPlaying] = useState(false)
  useEffect(() => {
    const el = textRef.current
    if (el) {
      setShowFade(el.scrollHeight > el.clientHeight)
    }
  }, [memory.label])
  const qidSafe = memory.id.replace(/[^a-z0-9_-]+/gi, '-').slice(0, 80)
  const signals = useMemo(() => memoryConnectionSignals(memory), [memory])
  const sharesActiveConnection = activeConnection ? signals.some((signal) => signal.id === activeConnection) : false
  const isVideo = ['mp4','mov','avi','webm'].includes(memory.mediaType || '')
  const isAudio = ['wav','mp3','ogg'].includes(memory.mediaType || '')
  const isMedia = Boolean(memory.imageUrl)
  const openMedia = (event: { preventDefault: () => void; stopPropagation: () => void }) => {
    event.preventDefault()
    event.stopPropagation()
    if (isAudio) {
      const audio = audioRef.current
      if (!audio) return
      const playbackUrl = memory.mediaUrl || memory.imageUrl || ''
      if (audio.paused) {
        if (audio.src !== playbackUrl) audio.src = playbackUrl
        void audio.play()
        setAudioPlaying(true)
      } else {
        audio.pause()
        setAudioPlaying(false)
      }
      return
    }
    setModalOpen(true)
  }
  const sourceKind = isAudio ? 'Audio' : isVideo ? 'Video' : isMedia ? 'Image' : 'Text'
  const traceGraph = useMemo(() => buildCardTraceGraph(memory, ideaText, signals), [ideaText, memory, signals])
  const detailControl = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, opacity: hovered ? 1 : 0, transition: 'opacity 150ms ease' }}>
      {signals.length > 0 && (
        <button
          type="button"
          data-qid={`dream:memory:graph:${qidSafe}`}
          data-qs-action="DREAM_MEMORY_TRACE_GRAPH"
          onClick={(e) => {
            e.preventDefault(); e.stopPropagation()
            const masonry = document.querySelector('[data-qid="dream:memory:masonry"]')
            const rect = (masonry ?? e.currentTarget.closest('[data-qid^="dream:memory-node:"]'))?.getBoundingClientRect()
            setGraphAnchor(rect ? { left: rect.left, top: rect.top, width: rect.width, height: rect.height } : null)
          }}
          style={nvis.graphGhostBtn}
          title="Open Theory-of-Mind trace graph"
        >
          <Share2 size={13} />
        </button>
      )}
      {signals.length > 0 && (
        <div style={{ width: 1, height: 12, background: 'rgba(255,255,255,0.12)', flexShrink: 0, alignSelf: 'center' }} />
      )}
      <button
        type="button"
        data-qid={`dream:memory:link:${qidSafe}`}
        data-qs-action="DREAM_MEMORY_LINK"
        title="Expand memory details"
        onClick={(e) => { e.stopPropagation(); setLinking(!linking) }}
        style={nvis.chevronBtn}
      >
        <ChevronRight size={14} />
      </button>
      {linking && (
        <select
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => { onLink(memory.id, e.target.value); setLinking(false) }}
          defaultValue=""
          style={nvis.memorySelect}
          data-qid={`dream:memory:link-select:${qidSafe}`}
          data-qs-action="DREAM_MEMORY_LINK"
          aria-haspopup="listbox"
          title="Pin memory to entity"
        >
          <option value="" disabled>Link to...</option>
          {entitySuggestions.map((e) => (<option key={e} value={e}>{e}</option>))}
        </select>
      )}
    </div>
  )
  return (
    <div
      data-qid={`dream:memory-node:${qidSafe}`}
      data-connection-ids={signals.map((signal) => signal.id).join(' ')}
      className={`memory-masonry-card ${memory.imageUrl ? 'memory-masonry-card-media' : 'memory-masonry-card-text text-node-well'}`}
      draggable={!isMedia}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => {
        setHovered(false)
        onConnectionHover(null)
      }}
      onDragStart={(e) => {
        if (onDragStart) onDragStart(memory.id, memory.label)
        e.dataTransfer.setData('text/plain', `${memory.subtitle || memory.id}: ${memory.label}`)
        e.dataTransfer.effectAllowed = 'link'
      }}
      style={isMedia
        ? {
          ...nvis.memoryMediaCard,
          ...(sharesActiveConnection ? nvis.memorySemanticActive : null),
          ...(activeConnection && !sharesActiveConnection ? nvis.memorySemanticDim : null),
        }
        : {
          ...(sharesActiveConnection ? nvis.memorySemanticActive : null),
          ...(activeConnection && !sharesActiveConnection ? nvis.memorySemanticDim : null),
        }}
    >
      {modalOpen && isMedia && !isAudio && <MediaModal url={(memory.mediaUrl || memory.imageUrl)!} mediaType={memory.mediaType} onClose={() => setModalOpen(false)} />}
      {graphAnchor && <TraceGraphOverlay graph={traceGraph} ideaText={ideaText} anchorRect={graphAnchor} onClose={() => setGraphAnchor(null)} />}
      {isMedia ? (
        <>
          <div
            role="button"
            tabIndex={0}
            data-qid={`dream:memory:open-media:${qidSafe}`}
            data-qs-action="DREAM_MEMORY_OPEN_MEDIA"
            aria-label={`Open memory ${isAudio ? 'audio' : isVideo ? 'media' : 'image'}: ${memory.subtitle || memory.label}`}
            onClick={openMedia}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' && event.key !== ' ') return
              openMedia(event)
            }}
            onPointerDown={(e) => e.stopPropagation()}
            style={nvis.memoryMediaButton}
          >
            {isVideo ? (
              <video
                src={memory.mediaUrl || memory.imageUrl}
                poster={memory.imageUrl}
                controls
                preload="metadata"
                onClick={(event) => event.stopPropagation()}
                draggable={false}
                style={nvis.memoryFullBleedMedia}
              />
            ) : isAudio ? (
              <div style={nvis.memoryAudioPreview}>
                <audio
                  ref={audioRef}
                  src={memory.mediaUrl || memory.imageUrl}
                  preload="metadata"
                  onEnded={() => setAudioPlaying(false)}
                  onPause={() => setAudioPlaying(false)}
                  onPlay={() => setAudioPlaying(true)}
                />
                <Volume2 size={22} />
                <span style={{ color: '#e2e8f0', fontSize: 12, letterSpacing: '0.16em', textTransform: 'uppercase' }}>
                  {audioPlaying ? 'Pause audio' : 'Play audio'}
                </span>
              </div>
            ) : (
              <img src={memory.imageUrl} alt="" draggable={false} style={nvis.memoryFullBleedMedia} />
            )}
          </div>
          <div className="memory-card-shelf" style={nvis.memoryMediaShelf}>
            <p style={{ ...nvis.memoryOverlayText, color: hovered ? 'rgba(255,255,255,1)' : 'rgba(255,255,255,0.75)', textShadow: hovered ? '0 0 12px rgba(255,255,255,0.15)' : 'none' }}>{memory.label}</p>
            {detailControl}
          </div>
        </>
      ) : (
        <>
          <div className="text-node-content-wrap" onClick={() => setTextModalOpen(true)}>
            <div ref={textRef} className="text-node-content">{memory.label}</div>
            {showFade && <div className="text-node-fade" />}
          </div>
          <div className="text-node-actions" style={{ opacity: hovered ? 1 : 0, pointerEvents: hovered ? 'auto' as const : 'none' as const }}>
            {detailControl}
          </div>
          {textModalOpen && <TextExpandModal text={memory.label} onClose={() => setTextModalOpen(false)} />}
        </>
      )}
      {hovered && (
        <div style={nvis.pinCallout}>
          <div style={nvis.pinHudHeader}>
            <GitBranch size={12} style={{ color: '#4a9eff', flexShrink: 0 }} />
            <span style={nvis.pinHudTitle}>{memory.subtitle || memory.label.slice(0, 40)}</span>
          </div>
          <div style={nvis.pinHudBody}>{memory.label}</div>
          <div style={nvis.pinHudFooter}>
            {memory.score != null && <span>{memory.score}% confidence</span>}
            {memory.subtitle && <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}>{memory.subtitle}</span>}
            {signals.length > 0 && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                {signals.map((s) => (
                  <span key={s.id} style={{ width: 5, height: 5, borderRadius: '50%', background: s.color, display: 'inline-block' }} />
                ))}
                {signals.length} hop{signals.length > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
