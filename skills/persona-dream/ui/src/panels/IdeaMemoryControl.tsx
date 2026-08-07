/**
 * IdeaMemoryControl, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import * as d3 from 'd3'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from '../types'
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from '../lib/dream'
import { persistedHumanIdea } from '../lib/idea'
import { buildLiveMemoryTraceGraph, dreamMemoryResultFromDocument, dreamMemoryResultPriority, extractKnownMemoryFieldText, extractPersonaMemoryKey, humanMemoryCaption, linkedStoryAssetFromMemoryResult, memoryConnectionPalette, memoryConnectionSignals, mergeMemoryTomGraph, personaMemoryThumbCache, readableMemoryText, readableMemoryValue, stripLeadingMemoryFieldLabels } from '../lib/memory'
import { nvis } from '../styles'
import { MemoryLinker } from './MemoryLinker'
import { PencilLine } from 'lucide-react'

export function IdeaMemoryControl({
  ideaStage,
  memoryStage,
  onTriggerMemories,
  processing,
  memoryResults,
  humanIdea,
}: {
  ideaStage: DreamStage | null
  memoryStage: DreamStage | null
  onTriggerMemories: (ideaText: string) => void
  processing: boolean
  memoryResults?: ResearchMemoryResult[] | null
  humanIdea?: HumanIdeaProjection
}) {
  const [localIdea, setLocalIdea] = useState(persistedHumanIdea(humanIdea))
  const [linkedEntities, setLinkedEntities] = useState<Record<string, string>>({})
  const [debouncedIdea, setDebouncedIdea] = useState(localIdea)
  const [ideaFocused, setIdeaFocused] = useState(false)
  const [activeMemoryConnection, setActiveMemoryConnection] = useState<string | null>(null)

  const lastTriggered = useRef('')
  const ideaInputRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const t = setTimeout(() => setDebouncedIdea(localIdea), 1500)
    return () => clearTimeout(t)
  }, [localIdea])

  useEffect(() => {
    setLocalIdea(persistedHumanIdea(humanIdea))
  }, [humanIdea?.ideaSha256])
  useEffect(() => {
    const input = ideaInputRef.current
    if (!input) return
    if (document.activeElement === input) return
    if (input.innerText !== localIdea) input.innerText = localIdea
  }, [localIdea])
  useEffect(() => {
    if (debouncedIdea && debouncedIdea.length > 10 && debouncedIdea !== lastTriggered.current && !processing) {
      lastTriggered.current = debouncedIdea
      onTriggerMemories(debouncedIdea)
    }
  }, [debouncedIdea, onTriggerMemories, processing])
  const memories = useMemo(() => {
    if (memoryResults && memoryResults.length > 0) {
      const mapped = memoryResults.slice(0, 16).map((r, i) => ({
        id: r.memoryKey ? `persona_memory/${r.memoryKey}` : `mem-research-${i}`,
        label: humanMemoryCaption(r),
        subtitle: r.title || '',
        imageUrl: dreamRenderableMediaUrl(r.url) ? r.url : '',
        mediaType: r.mediaType || '',
        memoryKey: r.memoryKey,
        mediaUrl: dreamRenderableMediaUrl(r.mediaUrl || r.url) ? (r.mediaUrl || r.url || '') : '',
        score: r.score,
      })) as Array<{ id: string; label: string; subtitle: string; imageUrl: string; mediaType: string; memoryKey?: string; mediaUrl?: string; score?: number }>
      const media = mapped.filter((m) => Boolean(m.imageUrl))
      const textOnly = mapped.filter((m) => !m.imageUrl)
      const mixed: typeof mapped = []
      const max = Math.max(media.length, textOnly.length)
      for (let i = 0; i < max; i += 1) {
        if (media[i]) mixed.push(media[i])
        if (textOnly[i]) mixed.push(textOnly[i])
      }
      return mixed
    }
    return (memoryStage?.artifacts ?? []).slice(0, 12).map((a, i) => ({
      id: a.path || `mem-${i}`,
      label: a.label.replace(/\.[^.]+$/, ''),
      score: undefined,
    }))
  }, [memoryResults, memoryStage?.artifacts])

  const entitySuggestions = useMemo(() => {
    const words = localIdea.split(/\s+/).filter((w) => /^[A-Z]/.test(w) && w.length > 2)
    return [...new Set(words)].slice(0, 8)
  }, [localIdea])

  const handleLink = (memoryId: string, entity: string) => {
    setLinkedEntities((prev) => ({ ...prev, [memoryId]: entity }))
  }

  const handleDragStart = (id: string, _label: string) => {
    // no-op, dataTransfer is set by the MemoryLinker
  }

  const allLinked = memories.length === 0 || memories.every((m) => linkedEntities[m.id] != null)

  return (
    <div data-qid="phase-01-02-root" style={ideaFocused ? { ...nvis.ideaMemoryCanvas, ...nvis.ideaMemoryCanvasEditing } : nvis.ideaMemoryCanvas}>
      <section data-qid="dream:memory:board" style={nvis.memoryBoardSection}>
        <div style={nvis.ideaComposer}>
          <div style={nvis.ideaComposerHeader}>
            <span style={nvis.ideaComposerLabel}>Core Creative Directive</span>
            <button
              type="button"
              data-qid="dream:idea:focus-edit"
              data-qs-action="DREAM_IDEA_COMPOSE"
              title="Edit Directive"
              aria-label="Edit Directive"
              className="idea-edit-affordance"
              onClick={() => {
                ideaInputRef.current?.focus()
                setIdeaFocused(true)
              }}
              style={nvis.ideaEditAffordance}
            >
              <PencilLine size={13} />
              <span>Edit</span>
            </button>
          </div>
          <div
            ref={ideaInputRef}
            contentEditable={!humanIdea}
            suppressContentEditableWarning
            onInput={(e) => setLocalIdea(e.currentTarget.innerText)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                e.preventDefault()
                onTriggerMemories(localIdea)
              }
            }}
            onFocus={() => setIdeaFocused(true)}
            onBlur={() => setIdeaFocused(false)}
            data-qid="dream:idea:composer"
            data-qs-action="DREAM_IDEA_COMPOSE"
            data-empty={localIdea.trim().length === 0 ? 'true' : 'false'}
            aria-label="Type a core idea to recall memories"
            style={nvis.ideaComposerInput}
          >
            {localIdea}
          </div>
          {humanIdea && (
            <div data-qid="dream:idea:persisted-identity" style={{ marginTop: 8, color: '#64748b', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              Persisted explicit human idea · {humanIdea.ideaId} · {humanIdea.ideaSha256.slice(0, 18)}…
            </div>
          )}
          <div style={nvis.ideaComposerActions}>
            <button
              type="button"
              onClick={() => onTriggerMemories(localIdea)}
              disabled={processing || localIdea.trim().length <= 10}
              style={processing ? { ...nvis.ideaComposerAction, opacity: 0.95, color: '#ffaa00' } : nvis.ideaComposerAction}
            >
              <span style={processing ? { ...nvis.ideaComposerDot, background: '#ffaa00' } : nvis.ideaComposerDot} />
              {processing ? 'Recalling Memory Residue' : 'Extract Memory Residue'}
            </button>
          </div>
        </div>
        {processing && memories.length === 0 && (
          <div style={{ color: '#ffaa00', fontSize: 11, padding: 12, textAlign: 'center' }}>Loading memory residue...</div>
        )}
        {!processing && memories.length > 0 && (
          <div data-qid="dream:memory:masonry" className="memory-masonry-board" style={nvis.memoryMasonry}>
            {memories.slice(0, 12).map((m) => (
              <MemoryLinker
                key={m.id}
                memory={m}
                ideaText={localIdea}
                entitySuggestions={entitySuggestions}
                activeConnection={activeMemoryConnection}
                onConnectionHover={setActiveMemoryConnection}
                onLink={handleLink}
                onDragStart={handleDragStart}
              />
            ))}
          </div>
        )}
        {!processing && memories.length === 0 && (
          <div style={{ color: '#ff4444', fontSize: 11, padding: 12, textAlign: 'center', border: '1px dashed rgba(255,255,255,0.08)', borderRadius: 8, background: 'rgba(0,0,0,0.15)' }}>
            NO_LINKED_MEMORIES — memories from persona recall appear here
          </div>
        )}
        {memories.length > 0 && !allLinked && (
          <div style={{ color: '#ffaa00', fontSize: 10, marginTop: 8, letterSpacing: '0.04em', textAlign: 'center' }}>
            Some memories remain unlinked. Link residue cards before proceeding.
          </div>
        )}
      </section>
    </div>
  )
}
