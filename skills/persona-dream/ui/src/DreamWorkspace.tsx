// @ts-nocheck
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import * as d3 from 'd3'
import {
  AlertTriangle,
  Aperture,
  BookOpen,
  Boxes,
  Camera,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clapperboard,
  CheckCircle2,
  Copy,
  ClipboardCheck,
  Code2,
  FileJson,
  Film,
  FileText,
  Filter,
  Gauge,
  GitBranch,
  Grid,
  Image,
  Images,
  Info,
  Layout,
  Lightbulb,
  Lock,
  MapPin,
  Maximize2,
  Mic,
  Mic2,
  Move3D,
  Package,
  PencilLine,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Share2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Sun,
  Table2,
  Users,
  UserRound,
  Volume2,
  CircleDot,
  CloudSun,
  Wand2,
  X,
} from 'lucide-react'
import { useRegisterAction } from './useRegisterAction'
import { highlightWithGlossary, type GlossaryTerm } from './highlightEntities'
import type { ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry } from './types'
import { CANONICAL_PHASES, DREAM_SCRIPT_DRAFT_STORAGE_KEY, DREAM_SCRIPT_STATUS_STORAGE_KEY, DREAM_STORY_DRAFT_STORAGE_KEY, DREAM_STORY_STATUS_STORAGE_KEY, crewGateMatchTerms, crewMissingEvidenceFields, phase02RequiredMediaKeys, phase02RequiredTextKeys, phaseIcons, splitStoryObjects, storyRowCategory, storyboardReviewerChecklist, textEncoder, videoProviderFitColumns } from './constants'
import { assetExtension, dreamAssetUrl } from './lib/asset'
import { crc32, downloadBlob, fnv1a32, writeUint16, writeUint32 } from './lib/binary'
import { contactSheetDecisionForStoryRow } from './lib/contact'
import { chooseCrewPersona, compactCrewText, crewFitRationale, crewRoleCriteria, crewTauRepairNote, scoreCrewPersona } from './lib/crew'
import { dreamBooleanLabel, dreamDisplayCode, dreamExtractPathFromText, dreamInferMediaType, dreamList, dreamNumber, dreamRenderableMediaUrl, dreamStringField, parseDreamJson, shouldIgnoreDreamPaneArrowKey } from './lib/dream'
import { endpointParts, graphKindFromDocument, graphLabelFromDocument, graphNodeFromEndpoint, graphThumbFromDocument } from './lib/graph'
import { persistedHumanIdea } from './lib/idea'
import { graphMediaSourceFromDocument, mediaLockFrameGroups, mediaLockFramesFromPacket, mediaLockGroupTimeRange, mediaLockStatusLabel } from './lib/media'
import { buildLiveMemoryTraceGraph, dreamMemoryResultFromDocument, dreamMemoryResultPriority, extractKnownMemoryFieldText, extractPersonaMemoryKey, humanMemoryCaption, linkedStoryAssetFromMemoryResult, memoryConnectionPalette, memoryConnectionSignals, mergeMemoryTomGraph, personaMemoryThumbCache, readableMemoryText, readableMemoryValue, stripLeadingMemoryFieldLabels } from './lib/memory'
import { authorStyleGuide, groupResearchContext, personaText, personaThumbnailUrl, productionTechniquePackage, roleFitCandidates, rolePrompt } from './lib/persona'
import { activeDreamPhaseFromLocation, dreamPhaseHashAliases, dreamPhaseHashById, normalizeToCanonicalPhases, phaseNumber, phaseShortLabels } from './lib/phase'
import { formatProviderContractBlocker, highlightJsonForProviderContract, highlightJsonLineForProviderContract, parseProviderContractAudioSummary, providerContractArtifactRole, providerContractAudioValueTone, providerContractJsonTokenStyle, providerContractStatusTone, providerFitDelta, providerFitMax, providerFitValue, rebindProviderContractAssetPath, shortProviderHash, videoProviderArtifactRole } from './lib/provider'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from './lib/react'
import { coverageNoteForScriptRow, distinctAssetDescription, hasLiveDescriptionReceipt, scriptContractFromDraft, scriptCoverageStatusForRow, scriptCoverageStatusTitle, scriptEntityRows, scriptGlossaryFromContract, scriptStringFromContract, splitScriptIntoRows, storyAssetDescriptionFromMemoryDocument, storyAssetDescriptionFromResult } from './lib/script'
import { createMissingStage, effectiveStageStatus, isStagePassed, requiredStageArtifact, stageArtifactSummary, stageImageSummary, stageMissingMessage } from './lib/stage'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from './lib/status'
import { compactStoryStatus, inferStoryLocationAndEnvironment, parseStoryDraftJson, storyContractSummaryFromDraft, storyDisplayText, storyEntityGlossary } from './lib/story'
import { acceptedStoryboardFrame, panelHasAcceptedStoryboardFrames, storyboardPanelPromptText, storyboardRecord, storyboardShotCode, storyboardStringList, storyboardTargetPanelIds } from './lib/storyboard'
import { AgentPane } from './panels/AgentPane'
import { ArtifactChip } from './panels/ArtifactChip'
import { ArtifactField } from './panels/ArtifactField'
import { AssetProvenancePreview } from './panels/AssetProvenancePreview'
import { AssetProvenanceStrip } from './panels/AssetProvenanceStrip'
import { ContactSheetBoard } from './panels/ContactSheetBoard'
import { CrewConsole } from './panels/CrewConsole'
import { DirectorConsole } from './panels/DirectorConsole'
import { EvidenceCard } from './panels/EvidenceCard'
import { GateMiniBadge } from './panels/GateMiniBadge'
import { GraphModal } from './panels/GraphModal'
import { IdeaMemoryControl } from './panels/IdeaMemoryControl'
import { JsonProjectionViewer } from './panels/JsonProjectionViewer'
import { KlingGate } from './panels/KlingGate'
import { MediaLockFact } from './panels/MediaLockFact'
import { MediaLockPanel } from './panels/MediaLockPanel'
import { MediaModal } from './panels/MediaModal'
import { MemoryLinker } from './panels/MemoryLinker'
import { PhaseIcon } from './panels/PhaseIcon'
import { PipelineNav } from './panels/PipelineNav'
import { ProviderContractAudioSummary } from './panels/ProviderContractAudioSummary'
import { ProviderContractFrameState } from './panels/ProviderContractFrameState'
import { ProviderContractMetadataRow } from './panels/ProviderContractMetadataRow'
import { ProviderContractPanel } from './panels/ProviderContractPanel'
import { ProviderContractRibbonMetric } from './panels/ProviderContractRibbonMetric'
import { ProviderContractState } from './panels/ProviderContractState'
import { ProviderReturnPanel } from './panels/ProviderReturnPanel'
import { ResearchPane } from './panels/ResearchPane'
import { ScriptAssetTile } from './panels/ScriptAssetTile'
import { ScriptConsole } from './panels/ScriptConsole'
import { ScriptCoverageTable } from './panels/ScriptCoverageTable'
import { ScriptTable } from './panels/ScriptTable'
import { StageCard } from './panels/StageCard'
import { StageCardHeader } from './panels/StageCardHeader'
import { StageEvidence } from './panels/StageEvidence'
import { StageGateAlert } from './panels/StageGateAlert'
import { StageWorkOrderBox } from './panels/StageWorkOrderBox'
import { StatusBadge } from './panels/StatusBadge'
import { StoryMatrix } from './panels/StoryMatrix'
import { StoryboardConsole } from './panels/StoryboardConsole'
import { StoryboardPanel } from './panels/StoryboardPanel'
import { StoryboardPromptBlock } from './panels/StoryboardPromptBlock'
import { StoryboardSupportBlock } from './panels/StoryboardSupportBlock'
import { SystemStatusIndicator } from './panels/SystemStatusIndicator'
import { TextExpandModal } from './panels/TextExpandModal'
import { TraceGraphOverlay } from './panels/TraceGraphOverlay'
import { VideoProviderPanel } from './panels/VideoProviderPanel'
import { VoiceBoard } from './panels/VoiceBoard'
import { WorkOrderInput } from './panels/WorkOrderInput'
import { compactDisplayText, decodeJsonStringLiteral, fileNameFromPath, firstString, parseJsonishText, payloadArray, payloadObject, stableJson } from './lib/text'
import { buildCardTraceGraph, inferTraceKind, isDisplayableTraceEdge, relaxTraceNodeOverlaps } from './lib/trace'
import { createStoredZip, sanitizeZipName } from './lib/zip'
import { nvis } from './styles'

export function DreamWorkspace() {
  const [runsResponse, setRunsResponse] = useState<DreamRunsResponse | null>(null)
  const [runDetail, setRunDetail] = useState<DreamRunDetailResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string>('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailRefreshNonce, setDetailRefreshNonce] = useState(0)
  const [stageNotes, setStageNotes] = useState<Record<string, string>>({})
  const [stageActionStatus, setStageActionStatus] = useState<Record<string, string>>({})
  const [railCollapsed, setRailCollapsed] = useState(false)
  const initialDreamStage = (() => {
    if (typeof window === 'undefined') return ''
    const phaseFromLocation = activeDreamPhaseFromLocation()
    if (phaseFromLocation) return phaseFromLocation
    return localStorage.getItem('dream_active_phase') || ''
  })()
  const [selectedStageId, setSelectedStageId] = useState<string>(initialDreamStage)
  useEffect(() => {
    if (selectedStageId) localStorage.setItem('dream_active_phase', selectedStageId)
  }, [selectedStageId])
  useEffect(() => {
    const applyHashPhase = () => {
      const phaseId = activeDreamPhaseFromLocation()
      if (phaseId) setSelectedStageId(phaseId)
    }
    applyHashPhase()
    window.addEventListener('hashchange', applyHashPhase)
    return () => window.removeEventListener('hashchange', applyHashPhase)
  }, [])
  const [processingPhase, setProcessingPhase] = useState<string | null>(null)
  const [pipelineStatus, setPipelineStatus] = useState<'IDLE' | 'ANALYZING' | 'ERROR'>('IDLE')
  const [researchResults, setResearchResults] = useState<ResearchMemoryResult[] | null>(null)
  const [phase02MediaGate, setPhase02MediaGate] = useState<Phase02MediaGate | null>(null)
  const ideaTextRef = useRef('')
  const directionRef = useRef(1)
  const [slideDir, setSlideDir] = useState(1)

  useRegisterAction('dream:button:refresh', {
    app: 'ux-lab',
    action: 'DREAM_REFRESH_RUNS',
    label: 'Refresh Dream runs',
    description: 'Reload persona-dream video provider run artifacts',
  })
  useRegisterAction('dream:input:search', {
    app: 'ux-lab',
    action: 'DREAM_SEARCH_RUNS',
    label: 'Search Dream runs',
    description: 'Filter persona-dream run artifacts by title, status, or path',
  })
  useRegisterAction('dream:item:run', {
    app: 'ux-lab',
    action: 'DREAM_SELECT_RUN',
    label: 'Select Dream run',
    description: 'Open a persona-dream video provider run artifact',
  })
  useRegisterAction('dream:stage:navigate', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_NAVIGATE',
    label: 'Navigate Dream stage',
    description: 'Jump to a persona-dream pipeline phase panel',
  })
  useRegisterAction('dream:stage:rerun', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_RERUN',
    label: 'Rerun Dream stage',
    description: 'Create a persona-dream stage rerun work order for the project agent',
  })
  useRegisterAction('dream:stage:edit', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_EDIT',
    label: 'Edit Dream stage',
    description: 'Create a persona-dream stage edit work order with human or project-agent repair notes',
  })
  useRegisterAction('dream:stage:ask-agent', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_ASK_AGENT',
    label: 'Ask Dream project agent',
    description: 'Create a project-agent repair work order for the selected Dream stage',
  })
  useRegisterAction('dream:voice:preview', {
    app: 'ux-lab',
    action: 'DREAM_VOICE_PREVIEW',
    label: 'Preview Dream voice',
    description: 'Preview Orpheus/TTS voice evidence when a speaking character voice is ready',
  })
  useRegisterAction('dream:kling:deploy', {
    app: 'ux-lab',
    action: 'DREAM_KLING_DEPLOY',
    label: 'Deploy Dream packet to provider',
    description: 'Submit to the selected video provider only when all upstream preflight gates pass and paid-call authorization is present',
  })
  useRegisterAction('dream:stage:edit-notes', {
    app: 'ux-lab',
    action: 'DREAM_STAGE_EDIT_NOTES',
    label: 'Edit Dream stage notes',
    description: 'Capture repair notes for a persona-dream stage work order',
  })
  useRegisterAction('dream:rail:toggle', {
    app: 'ux-lab',
    action: 'DREAM_RAIL_TOGGLE',
    label: 'Toggle Dream run rail',
    description: 'Collapse or expand the Dream run list rail',
  })
  useRegisterAction('dream:idea:composer', {
    app: 'ux-lab',
    action: 'DREAM_IDEA_COMPOSE',
    label: 'Compose Dream idea',
    description: 'Type a core idea that drives debounced Brave Search and memory recall for the masonry board',
  })
  useRegisterAction('dream:memory:open-media', {
    app: 'ux-lab',
    action: 'DREAM_MEMORY_OPEN_MEDIA',
    label: 'Open memory media',
    description: 'Open a memory image, video, or audio asset in the floating preview inspector',
  })
  useRegisterAction('dream:memory:close-media', {
    app: 'ux-lab',
    action: 'DREAM_MEMORY_CLOSE_MEDIA',
    label: 'Close memory media',
    description: 'Close the floating memory media preview inspector',
  })
  useRegisterAction('dream:memory:link', {
    app: 'ux-lab',
    action: 'DREAM_MEMORY_LINK',
    label: 'Link memory to entity',
    description: 'Associate a memory residue card with a detected story entity',
  })
  useRegisterAction('dream:memory:trace-graph', {
    app: 'ux-lab',
    action: 'DREAM_MEMORY_TRACE_GRAPH',
    label: 'Open memory trace graph',
    description: 'Open the D3 Theory-of-Mind relationship graph for a recalled memory card',
  })

  const loadRuns = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch('/api/projects/dream/runs')
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json() as DreamRunsResponse
      setRunsResponse(data)
      setSelectedId((current) => current || data.runs[0]?.id || '')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setRunsResponse(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadRuns()
  }, [])

  const filteredRuns = useMemo(() => {
    const runs = runsResponse?.runs ?? []
    const needle = query.trim().toLowerCase()
    if (!needle) return runs
    return runs.filter((run) => [
      run.title,
      run.id,
      run.status,
      run.source,
      run.runRoot,
    ].some((value) => value.toLowerCase().includes(needle)))
  }, [query, runsResponse?.runs])

  const selectedRun = useMemo(() => {
    return filteredRuns.find((run) => run.id === selectedId) ?? filteredRuns[0] ?? null
  }, [filteredRuns, selectedId])

  useEffect(() => {
    if (selectedRun && selectedRun.id !== selectedId) setSelectedId(selectedRun.id)
  }, [selectedId, selectedRun])

  useEffect(() => {
    if (!selectedRun) {
      setRunDetail(null)
      return
    }
    const controller = new AbortController()
    setDetailLoading(true)
    setDetailError(null)
    fetch(`/api/projects/dream/run-detail?root=${encodeURIComponent(selectedRun.runRoot)}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return await response.json() as DreamRunDetailResponse
      })
      .then((data) => {
        ideaTextRef.current = data.consumers?.humanIdea?.text ?? ''
        setRunDetail(data)
      })
      .catch((err) => {
        if ((err as Error).name !== 'AbortError') {
          setDetailError(err instanceof Error ? err.message : String(err))
          setRunDetail(null)
        }
      })
      .finally(() => setDetailLoading(false))
    return () => controller.abort()
  }, [selectedRun?.runRoot, detailRefreshNonce])

  useEffect(() => {
    const raw = runDetail?.stages ?? []
    if (raw.length === 0) {
      setSelectedStageId('')
      return
    }
    const canonical = normalizeToCanonicalPhases(raw)
    const hashStageId = activeDreamPhaseFromLocation()
    if (hashStageId && canonical.some((stage) => stage.id === hashStageId)) {
      if (selectedStageId !== hashStageId) setSelectedStageId(hashStageId)
      return
    }
    if (!canonical.some((stage) => stage.id === selectedStageId)) {
      setSelectedStageId(canonical[0].id)
    }
  }, [runDetail?.stages, selectedStageId])

  const resolveLegacyStageId = (canonicalId: string): string => {
    const raw = runDetail?.stages ?? []
    const phase = CANONICAL_PHASES.find(p => p.id === canonicalId)
    if (!phase) return canonicalId
    const matching = raw.find(s => (phase.legacyIds as readonly string[]).includes(s.id))
    return matching?.id ?? canonicalId
  }

  const submitStageAction = async (stageId: string, action: StageAction, noteOverride?: string) => {
    if (!selectedRun) return
    setStageActionStatus((current) => ({ ...current, [stageId]: 'writing work order...' }))
    const requestedBy = action === 'ask-agent' ? 'project_agent' : 'human'
    const backendAction = action === 'edit' ? 'edit' : 'rerun'
    const stageNote = noteOverride ?? stageNotes[stageId] ?? ''
    const notes = action === 'ask-agent'
      ? `[project-agent repair request]\n${stageNote}`.trim()
      : stageNote
    if (noteOverride != null) {
      setStageNotes((current) => ({ ...current, [stageId]: noteOverride }))
    }
    const backendStageId = resolveLegacyStageId(stageId)
    try {
      const response = await fetch('/api/projects/dream/stage-work-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          runRoot: selectedRun.runRoot,
          stageId: backendStageId,
          action: backendAction,
          requestedBy,
          notes,
        }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.error ?? `HTTP ${response.status}`)
      setStageActionStatus((current) => ({
        ...current,
        [stageId]: `work order: ${payload.workOrderPath}`,
      }))
      setDetailRefreshNonce((value) => value + 1)
    } catch (err) {
      setStageActionStatus((current) => ({
        ...current,
        [stageId]: `work order failed: ${err instanceof Error ? err.message : String(err)}`,
      }))
    }
  }

  const navigateToStage = (stageId: string) => {
    const oldIdx = CANONICAL_PHASES.findIndex((p) => p.id === selectedStageId)
    const newIdx = CANONICAL_PHASES.findIndex((p) => p.id === stageId)
    const dir = newIdx >= oldIdx ? 1 : -1
    directionRef.current = dir
    setSlideDir(dir)
    setSelectedStageId(stageId)
    const slug = dreamPhaseHashById[stageId]
    if (slug) {
      const path = window.location.pathname.replace(/\/+$/, '')
      const hashParts = window.location.hash.replace(/^#/, '').split('/').filter(Boolean)
      const nextUrl = path === '/dream'
        ? `/dream#${slug}`
        : hashParts[0] === 'dream' || path === '' || path === '/'
          ? `/#dream/${slug}`
          : `/dream#${slug}`
      if (`${window.location.pathname}${window.location.hash}` !== nextUrl) {
        window.history.replaceState(null, '', nextUrl)
      }
    }
  }

  const pendingIdeaRef = useRef<string | null>(null)

  const handleAutoExtract = async (ideaText: string) => {
    if (!selectedRun) {
      pendingIdeaRef.current = ideaText
      return
    }
    ideaTextRef.current = ideaText
    setProcessingPhase('02')
    setPipelineStatus('ANALYZING')

    try {
      const [searchRes, memoryRes] = await Promise.all([
        fetch('/api/projects/dream/brave-search', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: ideaText }),
        }),
        fetch('/api/memory/recall', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            q: `Embry Kai surf Big Island media contact sheets audio video ${ideaText}`,
            collections: ['persona_memory'],
            tags: ['persona:embry'],
            k: 24,
          }),
        }),
      ])
      const allResults: ResearchMemoryResult[] = []
      const webResults: ResearchMemoryResult[] = []
      if (searchRes.ok) {
        const searchData = await searchRes.json()
        if (searchData.results?.length > 0) webResults.push(...searchData.results)
      }
      if (memoryRes.ok) {
        const memoryData = await memoryRes.json()
        const nodes = Array.isArray(memoryData.items)
          ? memoryData.items as Array<Record<string, unknown>>
          : Array.isArray(memoryData.results)
            ? memoryData.results as Array<Record<string, unknown>>
            : Array.isArray(memoryData.nodes)
              ? memoryData.nodes as Array<Record<string, unknown>>
              : []
        const keys = [...new Set(nodes
          .map((node) => typeof node._key === 'string' ? node._key : extractPersonaMemoryKey({
            id: dreamStringField(node, ['id', 'title', 'name', 'label']),
            label: dreamStringField(node, ['description', 'text', 'retrieval_text', 'content']),
            subtitle: dreamStringField(node, ['snippet', 'summary']),
            imageUrl: dreamStringField(node, ['source_path', 'image_path', 'url', 'path']),
            mediaType: dreamStringField(node, ['media_type', 'asset_type']),
          }))
          .filter((key): key is string => Boolean(key)))]
        const hydratedDocs = keys.length > 0
          ? await memoryByKeysDocuments('persona_memory', keys.slice(0, 24), undefined, [
            '_key',
            'title',
            'name',
            'label',
            'description',
            'media_description',
            'vlm_description',
            'video_description',
            'audio_caption',
            'text_summary',
            'story_prompt_summary',
            'summary',
            'text',
            'retrieval_text',
            'content',
            'source_path',
            'image_path',
            'thumbnail_path',
            'poster_path',
            'keyframe_path',
            'url',
            'asset_url',
            'public_url',
            'path',
            'media_type',
            'mime_type',
            'asset_type',
            'persona_id',
          ]).catch(() => [])
          : []
        const hydratedByKey = new Map(hydratedDocs.map((doc) => [String(doc._key ?? ''), doc]))
        nodes.slice(0, 18).forEach((node, index) => {
          const key = typeof node._key === 'string' ? node._key : keys[index]
          const hydrated = key ? hydratedByKey.get(key) : undefined
          const doc = hydrated ? { ...node, ...hydrated, score: node.score } : node
          const result = dreamMemoryResultFromDocument(doc, index)
          if (result.url || result.snippet || result.title) allResults.push(result)
        })
      }
      const rankedResults = [...allResults, ...webResults]
        .sort((a, b) => dreamMemoryResultPriority(a) - dreamMemoryResultPriority(b))
      if (rankedResults.length > 0) setResearchResults(rankedResults)
      setProcessingPhase(null)
      setPipelineStatus('IDLE')
    } catch {
      setPipelineStatus('ERROR')
      setProcessingPhase(null)
    }
  }

  useEffect(() => {
    if (selectedRun && pendingIdeaRef.current) {
      const idea = pendingIdeaRef.current
      pendingIdeaRef.current = null
      handleAutoExtract(idea)
    }
  }, [selectedRun?.id])

  useEffect(() => {
    let cancelled = false
    loadPhase02MediaGate()
      .then((gate) => {
        if (!cancelled) setPhase02MediaGate(gate)
      })
      .catch(() => {
        if (!cancelled) {
          setPhase02MediaGate({
            status: 'MISSING',
            describedCount: 0,
            requiredCount: phase02RequiredMediaKeys.length + phase02RequiredTextKeys.length,
            personaEdgeCount: 0,
            tomEdgeCount: 0,
          })
        }
      })
    return () => { cancelled = true }
  }, [selectedRun?.id])

  const backendStages = runDetail?.stages ?? []
  const revisionQualified = (runDetail?.revisionQualification as RevisionQualification | undefined)?.state === 'ACTIVE_CONSISTENT'
  const stages = useMemo(() => {
    const normalized = normalizeToCanonicalPhases(backendStages)
    if (!revisionQualified || phase02MediaGate?.status !== 'PASS') return normalized
    return normalized.map((stage) => stage.id === '02'
      ? {
          ...stage,
          status: 'PASS',
          summary: `Live media/story memory gate passed: ${phase02MediaGate.describedCount}/${phase02MediaGate.requiredCount} required assets and text memories described; ${phase02MediaGate.personaEdgeCount} media edges and ${phase02MediaGate.tomEdgeCount} TOM edges found.`,
          failureOrGap: null,
        }
      : stage)
  }, [backendStages, phase02MediaGate, revisionQualified])
  const selectedStage = stages.find((stage) => stage.id === selectedStageId) ?? stages[0] ?? null
  const klingReady = revisionQualified && stages.length > 0 && stages.every((p) => isStagePassed(p)) && !!selectedRun?.paidCallAuthorized

  const pageVariants = {
    initial: (dir: number) => ({ opacity: 0, x: dir > 0 ? 20 : -20 }),
    in: { opacity: 1, x: 0, transition: { duration: 0.2, ease: [0.22, 1, 0.36, 1] } },
    out: (dir: number) => ({ opacity: 0, x: dir > 0 ? -20 : 20, transition: { duration: 0.15 } }),
  }

  return (
    <div
      data-qid="dream:workspace"
      style={{
        ...styles.workspace,
        gridTemplateColumns: railCollapsed ? '56px minmax(0, 1fr) 340px' : '320px minmax(0, 1fr) 340px',
      }}
    >
      <style>{`
        @keyframes dream-phase-fade-up {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes dream-agent-slide {
          from { opacity: 0; transform: translateX(10px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes slide-in-right {
          from { opacity: 0; transform: translateX(20px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes slide-in-left {
          from { opacity: 0; transform: translateX(-20px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes dream-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        @keyframes dream-soft-fade {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        [data-qid="dream:idea:composer"][data-empty="true"]::before {
          content: "What is the intent of this session?";
          color: #334155;
          pointer-events: none;
        }
        [data-qid="dream:idea:composer"]:hover,
        [data-qid="dream:idea:composer"]:focus {
          border-bottom-color: rgba(74, 158, 255, 0.42) !important;
        }
        [data-qid="dream:idea:composer"] + div:hover {
          opacity: 1 !important;
        }
        .idea-edit-affordance {
          opacity: 1;
          transition: color 180ms ease, border-color 180ms ease, background 180ms ease;
        }
        .dream-phase-content {
          will-change: transform, opacity;
          backface-visibility: hidden;
          perspective: 1000px;
        }
        .contextual-inspector {
          box-shadow: -10px 0 20px rgba(0,0,0,0.3);
          background: #111111;
        }
        [data-qid="contact-sheet-grid"] {
          padding: 1rem;
          background: #111111;
          border-radius: 4px;
        }
        .contact-sheet-card:hover .contact-sheet-overlay {
          opacity: 1 !important;
        }
        .memory-link-select, .memory-media-overlay { opacity: 0; transition: opacity 200ms ease, transform 200ms ease, color 160ms ease; }
        .memory-masonry-board {
          column-width: 220px;
          column-gap: 24px;
        }
        @media (max-width: 760px) {
          .memory-masonry-board { column-width: 100%; }
        }
        .memory-masonry-card {
          break-inside: avoid;
          page-break-inside: avoid;
          margin-bottom: 24px;
        }
        .memory-masonry-card:hover .memory-link-select,
        .memory-masonry-card:focus-within .memory-link-select { opacity: 1; }
        .memory-masonry-card:hover {
          transform: translateY(-4px);
        }
        .memory-masonry-card:hover,
        .memory-masonry-card:focus-within {
          border-color: rgba(74, 158, 255, 0.32) !important;
          box-shadow: 0 16px 34px rgba(0, 0, 0, 0.22) !important;
        }
        .memory-masonry-card-media:hover img,
        .memory-masonry-card-media:hover video,
        .memory-masonry-card-media:focus-within img,
        .memory-masonry-card-media:focus-within video {
          transform: scale(1.045);
        }
        .memory-masonry-card:hover .memory-card-shelf,
        .memory-masonry-card:focus-within .memory-card-shelf {
          transform: translateY(0) !important;
        }
        .memory-card-shelf {
          transform: translateY(100%);
        }
        .text-node-well {
          position: relative;
          padding: 12px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          background: #0c0c0c;
        }
        .text-node-content-wrap {
          position: relative;
          max-height: 126px;
          overflow: hidden;
          cursor: pointer;
        }
        .text-node-content {
          font-size: 14px;
          line-height: 1.5;
          color: #e2e8f0;
        }
        .text-node-fade {
          position: absolute;
          bottom: 0;
          left: 0;
          right: 0;
          height: 32px;
          background: linear-gradient(to bottom, transparent, #0c0c0c);
          pointer-events: none;
        }
        .text-node-actions {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          padding: 6px 12px;
          background: rgba(0, 0, 0, 0.75);
          backdrop-filter: blur(4px);
          border-radius: 16px;
          border: 1px solid rgba(255, 255, 255, 0.1);
          display: flex;
          gap: 8px;
          transition: opacity 0.2s;
        }
        .text-node-actions button {
          color: rgba(255, 255, 255, 0.55);
          transition: color 0.15s ease;
        }
        .text-node-actions button:hover {
          color: rgba(255, 255, 255, 0.85) !important;
        }

      `}</style>
      <aside data-qid="dream:rail:runs" style={railCollapsed ? { ...styles.rail, ...styles.railCollapsed } : styles.rail}>
        <div style={railCollapsed ? styles.railCollapsedHeader : styles.railHeader}>
          {railCollapsed ? (
            <button
              type="button"
              data-qid="dream:rail:toggle"
              data-qs-action="DREAM_RAIL_TOGGLE"
              title="Expand Dream run list"
              onClick={() => setRailCollapsed(false)}
              style={styles.iconButton}
            >
              <ChevronRight size={16} />
            </button>
          ) : null}
          {!railCollapsed && (
            <>
          <div style={styles.railTitleRow}>
            <div>
              <div style={styles.eyebrow}>Dream Library</div>
              <h2 style={styles.railTitle}>Persona Dream</h2>
            </div>
            <button
              type="button"
              data-qid="dream:rail:toggle"
              data-qs-action="DREAM_RAIL_TOGGLE"
              title="Collapse Dream run list"
              onClick={() => setRailCollapsed(true)}
              style={styles.iconButton}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              data-qid="dream:button:refresh"
              data-qs-action="DREAM_REFRESH_RUNS"
              title="Refresh Dream runs"
              onClick={() => {
                void loadRuns()
                setDetailRefreshNonce((value) => value + 1)
              }}
              style={styles.iconButton}
            >
              <RefreshCw size={16} style={loading ? styles.spinIcon : undefined} />
            </button>
          </div>
          <label style={styles.searchWrap}>
            <Search size={16} color="#64748b" />
            <input
              data-qid="dream:input:search"
              data-qs-action="DREAM_SEARCH_RUNS"
              title="Search Dream runs"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter runs, status, paths"
              style={styles.searchInput}
            />
          </label>
            </>
          )}
        </div>

        {!railCollapsed && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            {loading && <div style={{ ...styles.stateBox, margin: 12 }}>Loading source artifacts...</div>}
            {!loading && error && <div style={{ ...styles.errorBox, margin: 12 }}>Dream run source unavailable: {error}</div>}
            {!loading && !error && filteredRuns.length === 0 && (
              <div style={{ ...styles.emptyBox, margin: 12 }}>
                No persona-dream runs matched the current filter.
              </div>
            )}
            {!loading && !error && filteredRuns.length > 0 && (
              <>
                <div style={{ padding: '14px 14px 6px' }}>
                  <div style={{ color: '#4a9eff', fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 700, marginBottom: 10 }}>Active Preflight</div>
                  {filteredRuns.filter((r) => r.status === 'RUNNING' || r.status === 'LIVE' || r.status === 'active').length === 0 && (
                    <div style={{ color: '#64748b', fontSize: 13, fontStyle: 'italic', marginBottom: 10 }}>No active runs</div>
                  )}
                  {filteredRuns.filter((r) => r.status === 'RUNNING' || r.status === 'LIVE' || r.status === 'active').map((run) => (
                    <button
                      key={`active-${run.id}`}
                      type="button"
                      data-qid={`dream:item:run:${run.id}`}
                      data-qs-action="DREAM_SELECT_RUN"
                      title={`Open Dream run: ${run.title}`}
                      onClick={() => setSelectedId(run.id)}
                      style={{
                        ...styles.runCard,
                        ...(selectedRun?.id === run.id ? styles.runCardSelected : null),
                        marginBottom: 8,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 14, fontWeight: 700, color: '#e2e8f0' }}>{run.title}</span>
                        <span style={{ color: '#00ff88', fontSize: 11, letterSpacing: '0.06em' }}>● LIVE</span>
                      </div>
                    </button>
                  ))}
                </div>
                <div style={{ flex: 1, overflow: 'auto', padding: '6px 14px 14px' }}>
                  <div style={{ color: '#64748b', fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 10 }}>Archives</div>
                  {filteredRuns.filter((r) => r.status !== 'RUNNING' && r.status !== 'LIVE' && r.status !== 'active').map((run) => (
                    <button
                      key={`archive-${run.id}`}
                      type="button"
                      data-qid={`dream:item:run:${run.id}`}
                      data-qs-action="DREAM_SELECT_RUN"
                      title={`Open Dream run: ${run.title}`}
                      onClick={() => setSelectedId(run.id)}
                      style={{
                        display: 'block',
                        width: '100%',
                        textAlign: 'left',
                        padding: '10px 0',
                        border: 'none',
                        borderBottom: '1px solid rgba(255,255,255,0.06)',
                        background: 'transparent',
                        color: selectedRun?.id === run.id ? '#e2e8f0' : '#64748b',
                        fontSize: 13,
                        cursor: 'pointer',
                      }}
                    >
                      {run.title}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </aside>

      <section data-qid="dream:detail" style={styles.detail}>
        {selectedRun ? (
          <>
	          <PipelineNav
	            activePhaseId={selectedStage?.id ?? ''}
	            onPhaseChange={navigateToStage}
	            klingReady={klingReady}
	            phases={stages}
	          />
          <div style={styles.stageBoard}>
            {detailLoading && <div style={styles.stateBox}>Loading pipeline phase cards...</div>}
            {detailError && <div style={styles.errorBox}>Stage detail unavailable: {detailError}</div>}
            {!detailLoading && !detailError && stages.length === 0 && (
              <div style={styles.emptyBox}>No stage ledger was found for this run. This remains blocked until source stage artifacts exist.</div>
            )}
            {!detailLoading && selectedStage && (
              <AnimatePresence mode="popLayout" custom={slideDir}>
                <motion.div
                  key={selectedStage.id}
                  id={`dream-stage-${selectedStage.id}`}
                  className="dream-phase-content"
                  custom={slideDir}
                  variants={pageVariants as any}
                  initial="initial"
                  animate="in"
                  exit="out"
                  style={styles.stageAnchor}
                >
                  <StageCard
                  run={selectedRun}
                  stage={selectedStage}
                  note={stageNotes[selectedStage.id] ?? ''}
                  actionStatus={stageActionStatus[selectedStage.id]}
                  allStages={stages}
                  researchSeed={researchResults?.map((r) => r.title + ' ' + r.snippet).join(' ')}
                  ideaText={ideaTextRef.current}
                  memoryResults={researchResults}
                  storyboardProjection={runDetail?.consumers?.storyboard}
                  humanIdea={runDetail?.consumers?.humanIdea}
                  revisionQualified={revisionQualified}
                  onTriggerMemories={handleAutoExtract}
                  onNoteChange={(value) => setStageNotes((current) => ({ ...current, [selectedStage.id]: value }))}
                  onSubmitAction={(action, noteOverride) => void submitStageAction(selectedStage.id, action, noteOverride)}
                />
              </motion.div>
            </AnimatePresence>
            )}
          </div>
          </>
        ) : (
          <div style={styles.noReport}>
            <ShieldAlert size={40} color="#fcd34d" />
            <div style={styles.noReportTitle}>Dream project has no source runs</div>
            <p style={styles.noReportCopy}>No placeholder data is shown. Add or generate persona-dream artifacts, then refresh this project.</p>
          </div>
        )}
      </section>
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
        <AgentPane
          selectedRun={selectedRun}
          selectedStage={selectedStage}
          note={selectedStage ? stageNotes[selectedStage.id] ?? '' : ''}
          activePhaseId={selectedStageId}
          research={researchResults}
          ideaSeed={ideaTextRef.current}
          onNoteChange={(value) => {
            if (!selectedStage) return
            setStageNotes((current) => ({ ...current, [selectedStage.id]: value }))
          }}
          onSubmitAction={(action, noteOverride) => {
            if (!selectedStage) return
            void submitStageAction(selectedStage.id, action, noteOverride)
          }}
        />
      </div>
    </div>
  )
}

