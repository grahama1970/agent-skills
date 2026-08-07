/**
 * TraceGraphOverlay, extracted from DreamWorkspace.tsx.
 */
import React, { type CSSProperties, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import * as d3 from 'd3'
import { highlightWithGlossary, type GlossaryTerm } from '../highlightEntities'
import type {ContactSheetDecision, ContactSheetDisplayAsset, ContactSheetRequirementAsset, CrewPersonaOption, CrewRole, DreamArtifact, DreamRun, DreamRunDetailResponse, DreamRunsResponse, DreamStage, HumanIdeaProjection, LinkedStoryAsset, LoadedVideoArtifact, MediaLockFrame, MemoryConnectionSignal, Phase02MediaGate, ResearchMemoryResult, RevisionQualification, ScriptCoverageStatus, SimulationLinkDatum, SimulationNodeDatum, StageAction, StatusTone, StoryMatrixRow, StoryPromptPayload, StoryWriterOption, StoryboardConsumerProjection, StoryboardFrameProjection, StoryboardPanelProjection, TraceAnchorRect, TraceGraph, TraceGraphLink, TraceGraphNode, TraceNodeKind, ZipFileEntry, ZoomTransform} from '../types'
import {endpointParts, graphKindFromDocument, graphLabelFromDocument, graphNodeFromEndpoint, graphThumbFromDocument, memoryEdgeDocuments, memoryListByEndpoint, memoryRecallDocuments} from '../lib/graph'
import { buildLiveMemoryTraceGraph, dreamMemoryResultFromDocument, dreamMemoryResultPriority, extractKnownMemoryFieldText, extractPersonaMemoryKey, humanMemoryCaption, linkedStoryAssetFromMemoryResult, memoryConnectionPalette, memoryConnectionSignals, mergeMemoryTomGraph, personaMemoryThumbCache, readableMemoryText, readableMemoryValue, stripLeadingMemoryFieldLabels } from '../lib/memory'
import { PipelineErrorBoundary, clampNumber, styles, useElementSize } from '../lib/react'
import { isExecutionReceiptArtifact, nodeKindColor, relationshipColor, statusLabel, statusTone, toneStyles } from '../lib/status'
import { isDisplayableTraceEdge, relaxTraceNodeOverlaps } from '../lib/trace'
import { nvis } from '../styles'
import { CircleDot, FileText, Film, GitBranch, Image, MapPin, Package, UserRound, Volume2, X } from 'lucide-react'

export function TraceGraphOverlay({
  graph,
  ideaText,
  anchorRect,
  onClose,
}: {
  graph: TraceGraph
  ideaText: string
  anchorRect?: TraceAnchorRect | null
  onClose: () => void
}) {
  const [hopLimit, setHopLimit] = useState<1 | 2 | 3 | 99>(2)
  const [liveGraph, setLiveGraph] = useState(graph)
  const [memoryStatus, setMemoryStatus] = useState<'idle' | 'loading' | 'loaded' | 'miss' | 'error'>('idle')
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState(graph.rootId)
  const [activeRootNode, setActiveRootNode] = useState<TraceGraphNode>(graph.nodes.find((node) => node.id === graph.rootId) ?? graph.nodes[0])
  const [wrapRef, size] = useElementSize<HTMLDivElement>()
  const svgRef = useRef<SVGSVGElement | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [zoomTransform, setZoomTransform] = useState<ZoomTransform>(d3.zoomIdentity)
  const [layoutPulse, setLayoutPulse] = useState(0)
  const [showTraceLinks, setShowTraceLinks] = useState(false)
  const [playingAudioNodeId, setPlayingAudioNodeId] = useState<string | null>(null)
  const [videoNode, setVideoNode] = useState<TraceGraphNode | null>(null)
  void ideaText

  useEffect(() => {
    setLiveGraph(graph)
    setSelectedNodeId(graph.rootId)
    setActiveRootNode(graph.nodes.find((node) => node.id === graph.rootId) ?? graph.nodes[0])
    setVideoNode(null)
    setPlayingAudioNodeId(null)
    audioRef.current?.pause()
  }, [graph])

  const activeBaseGraph = useMemo<TraceGraph>(() => {
    const root = activeRootNode ?? graph.nodes.find((node) => node.id === graph.rootId) ?? graph.nodes[0]
    return {
      ...graph,
      rootId: root.id,
      memoryEndpoint: root.id,
      title: root.label,
      source: graph.source,
      nodes: [{ ...root, hop: 0 }],
      links: [],
    }
  }, [activeRootNode, graph])

  useEffect(() => {
    let cancelled = false
    async function loadMemoryNeighborhood() {
      const rootEndpoint = activeBaseGraph.memoryEndpoint ?? activeBaseGraph.rootId
      if (!endpointParts(rootEndpoint)) {
        setMemoryStatus('miss')
        setLiveGraph(activeBaseGraph)
        return
      }
      setMemoryStatus('loading')
      setLiveGraph(activeBaseGraph)
      try {
        const edgeCollections = ['persona_memory_edges', 'tom_edges', 'persona_memory_entity_edges', 'persona_entity_edges']
        const firstHopBatches = await Promise.all(edgeCollections.flatMap((collection) => [
          memoryEdgeDocuments(collection, rootEndpoint, '_from').catch(() => []),
          memoryEdgeDocuments(collection, rootEndpoint, '_to').catch(() => []),
        ]))
        const firstHopRows = firstHopBatches.flat()
        const firstHopEndpoints = Array.from(new Set(firstHopRows.flatMap((edge) => [String(edge._from || ''), String(edge._to || '')]).filter(Boolean)))
          .filter((endpoint: any) => endpoint !== rootEndpoint)
          .slice(0, 8)
        const secondHopCollections = ['persona_memory_edges', 'tom_edges', 'persona_memory_entity_edges']
        const secondHopBatches = await Promise.all(firstHopEndpoints.flatMap((endpoint) => secondHopCollections.flatMap((collection) => [
          memoryEdgeDocuments(collection, endpoint, '_from').catch(() => []),
          memoryEdgeDocuments(collection, endpoint, '_to').catch(() => []),
        ])))
        const recallMediaBatches = await Promise.all(firstHopEndpoints.map((endpoint) => {
          const key = endpointParts(endpoint)?.key ?? endpoint
          return memoryRecallDocuments(
            `media_to_story_memory tom_media_grounding surf ritual Kai Embry audio video image ${key} ${activeBaseGraph.title}`,
            ['persona_memory_edges', 'tom_edges'],
            18,
          ).catch(() => [])
        }))
        const rowById = new Map<string, Record<string, unknown>>()
        ;[...firstHopRows, ...secondHopBatches.flat(), ...recallMediaBatches.flat()].filter((edge: any) => isDisplayableTraceEdge(edge, rootEndpoint)).forEach((edge, index) => {
          const from = String(edge._from || '')
          const to = String(edge._to || '')
          if (!from || !to) return
          const edgeKey = String(edge._id || edge._key || `${from}->${to}:${edge.relationship_type || edge.tom_state_type || index}`)
          rowById.set(edgeKey, edge)
        })
        const rows = Array.from(rowById.values()).slice(0, 22)
        const endpoints = Array.from(new Set([rootEndpoint, ...rows.flatMap((edge) => [String(edge._from || ''), String(edge._to || '')]).filter(Boolean)]))
        const hydrated = await Promise.all(endpoints.map(async (endpoint) => [endpoint, await memoryListByEndpoint(endpoint).catch(() => null)] as const))
        const docsByEndpoint = new Map<string, Record<string, unknown> | null>(hydrated)
        if (cancelled) return
        setLiveGraph(buildLiveMemoryTraceGraph(activeBaseGraph, rows, docsByEndpoint))
        setMemoryStatus(rows.length > 0 ? 'loaded' : 'miss')
      } catch {
        if (!cancelled) {
          setLiveGraph(activeBaseGraph)
          setMemoryStatus('error')
        }
      }
    }
    void loadMemoryNeighborhood()
    return () => { cancelled = true }
  }, [activeBaseGraph])

  useEffect(() => {
    const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const selection = d3.select(svg)
    const zoom = d3.zoom()
      .scaleExtent([0.45, 2.4])
      .on('zoom', (event: any) => setZoomTransform(event.transform))
    selection.call(zoom)
    selection.on('dblclick.zoom', null)
    return () => {
      selection.on('.zoom', null)
    }
  }, [])

  const filteredGraph = useMemo(() => {
    if (hopLimit === 99) return liveGraph
    const nodes = liveGraph.nodes.filter((node: any) => node.hop <= hopLimit)
    const nodeIds = new Set(nodes.map((node) => node.id))
    const links = liveGraph.links.filter((link: any) => link.hop <= hopLimit && nodeIds.has(link.source) && nodeIds.has(link.target))
    return { ...liveGraph, nodes, links }
  }, [liveGraph, hopLimit])

  useEffect(() => {
    let frame = 0
    let cancelled = false
    setLayoutPulse(0)
    setShowTraceLinks(false)
    const tick = () => {
      if (cancelled) return
      frame += 1
      setLayoutPulse(frame)
      if (frame < 64) window.setTimeout(tick, 34)
    }
    const edgeTimer = window.setTimeout(() => {
      if (!cancelled) setShowTraceLinks(true)
    }, 2600)
    tick()
    return () => {
      cancelled = true
      window.clearTimeout(edgeTimer)
    }
  }, [filteredGraph.rootId, filteredGraph.nodes.length, filteredGraph.links.length, hopLimit])

  const layout = useMemo(() => {
    const width = size.width
    const height = size.height
    const nodes = filteredGraph.nodes.map((node) => ({ ...node }))
    const links = filteredGraph.links.map((link) => ({ ...link }))
    nodes.forEach((node, index) => {
      const angle = (-Math.PI / 2) + index * ((Math.PI * 2) / Math.max(1, nodes.length))
      const ring = node.id === filteredGraph.rootId ? 0 : index % 2 === 0 ? 0.28 : 0.38
      const radius = Math.min(width, height) * ring
      ;(node as TraceGraphNode & SimulationNodeDatum).x = width * 0.5 + Math.cos(angle) * radius
      ;(node as TraceGraphNode & SimulationNodeDatum).y = height * 0.5 + Math.sin(angle) * radius
      if (node.id === filteredGraph.rootId) {
        ;(node as TraceGraphNode & SimulationNodeDatum).fx = width * 0.5
        ;(node as TraceGraphNode & SimulationNodeDatum).fy = height * 0.5
      }
    })
    const simulation = d3.forceSimulation(nodes as Array<TraceGraphNode & SimulationNodeDatum>)
      .force('link', d3.forceLink(links as Array<TraceGraphLink & SimulationLinkDatum<TraceGraphNode & SimulationNodeDatum>>).id((node: any) => node.id).distance((link: any) => 122 + link.hop * 42).strength(0.32))
      .force('charge', d3.forceManyBody().strength(-420))
      .force('center', d3.forceCenter(width * 0.5, height * 0.5))
      .force('x', d3.forceX(width * 0.5).strength(0.035))
      .force('y', d3.forceY(height * 0.5).strength(0.035))
      .force('collision', d3.forceCollide().radius((node: any) => node.radius + 32).iterations(4).strength(1))
      .stop()
    for (let i = 0; i < Math.min(140, 6 + layoutPulse * 2); i += 1) simulation.tick()
    simulation.stop()
    const extents = nodes.reduce(
      (acc, node) => {
        const x = (node as TraceGraphNode & SimulationNodeDatum).x ?? width * 0.5
        const y = (node as TraceGraphNode & SimulationNodeDatum).y ?? height * 0.5
        const pad = node.radius + 44
        return {
          minX: Math.min(acc.minX, x - pad),
          maxX: Math.max(acc.maxX, x + pad),
          minY: Math.min(acc.minY, y - pad),
          maxY: Math.max(acc.maxY, y + pad),
        }
      },
      { minX: Number.POSITIVE_INFINITY, maxX: Number.NEGATIVE_INFINITY, minY: Number.POSITIVE_INFINITY, maxY: Number.NEGATIVE_INFINITY }
    )
    const shiftX = width * 0.5 - (extents.minX + extents.maxX) / 2
    const shiftY = height * 0.5 - (extents.minY + extents.maxY) / 2
    relaxTraceNodeOverlaps(nodes as Array<TraceGraphNode & SimulationNodeDatum>, width, height)
    nodes.forEach((node) => {
      const datum = node as TraceGraphNode & SimulationNodeDatum
      const pad = node.radius + 58
      datum.x = clampNumber((datum.x ?? width * 0.5) + shiftX, pad, width - pad)
      datum.y = clampNumber((datum.y ?? height * 0.5) + shiftY, pad, height - pad)
    })
    relaxTraceNodeOverlaps(nodes as Array<TraceGraphNode & SimulationNodeDatum>, width, height)
    nodes.forEach((node) => {
      const datum = node as TraceGraphNode & SimulationNodeDatum
      const pad = node.radius + 58
      datum.x = clampNumber(datum.x ?? width * 0.5, pad, width - pad)
      datum.y = clampNumber(datum.y ?? height * 0.5, pad, height - pad)
    })
    return { nodes: nodes as Array<TraceGraphNode & SimulationNodeDatum>, links: links as Array<TraceGraphLink & SimulationLinkDatum<TraceGraphNode & SimulationNodeDatum>> }
  }, [filteredGraph, size, layoutPulse])

  const hopLabel = hopLimit === 99 ? 'All hops' : `${hopLimit}-Hop`
  const cycleHopLimit = () => {
    setHopLimit((current) => current === 1 ? 2 : current === 2 ? 3 : current === 3 ? 99 : 1)
  }
  const viewportWidth = typeof window === 'undefined' ? 1440 : window.innerWidth
  const viewportHeight = typeof window === 'undefined' ? 900 : window.innerHeight
  const region = anchorRect ?? { left: 240, top: 104, width: viewportWidth - 560, height: viewportHeight - 128 }
  const panelWidth = Math.min(760, Math.max(560, Math.min(region.width, 720)), viewportWidth - 48)
  const panelHeight = Math.min(560, Math.max(430, Math.min(region.height + 120, viewportHeight * 0.64)), viewportHeight - 48)
  const panelLeft = clampNumber(region.left + (region.width - panelWidth) / 2, 24, viewportWidth - panelWidth - 24)
  const panelTop = clampNumber(region.top + Math.min(28, region.height * 0.08), 72, viewportHeight - panelHeight - 24)
  const currentNode = filteredGraph.nodes.find((node) => node.id === (hoveredNodeId ?? selectedNodeId)) ?? filteredGraph.nodes.find((node) => node.id === filteredGraph.rootId) ?? filteredGraph.nodes[0]
  const currentNodeText = currentNode ? (currentNode.source_ref || currentNode.label) : graph.title

  const handleNodeClick = (node: TraceGraphNode) => {
    setSelectedNodeId(node.id)
    setHoveredNodeId(null)
    if (node.kind === 'audio' && node.mediaUrl) {
      if (!audioRef.current) audioRef.current = new Audio()
      const audio = audioRef.current
      if (playingAudioNodeId === node.id && !audio.paused) {
        audio.pause()
        setPlayingAudioNodeId(null)
        return
      }
      audio.src = node.mediaUrl
      audio.onended = () => setPlayingAudioNodeId(null)
      void audio.play().then(() => setPlayingAudioNodeId(node.id)).catch(() => setPlayingAudioNodeId(null))
      return
    }
    if (node.kind === 'video' && node.mediaUrl) {
      setVideoNode(node)
      return
    }
    setActiveRootNode({ ...node, hop: 0 })
    setHopLimit(1)
  }

  return createPortal(
    <div data-qid="dream:memory:trace-graph-overlay" role="dialog" aria-modal="false" aria-label="Memory relationship trace graph" style={nvis.traceOverlayBackdrop} onClick={onClose}>
      <motion.div
        onClick={(event: any) => event.stopPropagation()}
        initial={{ opacity: 0, scale: 0.94, y: 18 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 360, damping: 26, mass: 0.75 }}
        style={{ ...nvis.traceOverlayPanel, left: panelLeft, top: panelTop, width: panelWidth, height: panelHeight }}
      >
        <div style={nvis.traceHeader}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
            <CircleDot size={16} style={{ color: '#4a9eff', flexShrink: 0 }} />
            <span style={nvis.traceTitle}>{currentNodeText}</span>
          </div>
          <div style={nvis.traceToolbar}>
            <button
              type="button"
              data-qid="dream:trace:hop-cycle"
              data-qs-action="DREAM_TRACE_SET_HOP"
              title={`Showing assets up to ${hopLimit === 99 ? 'all' : hopLimit} connection${hopLimit === 1 ? '' : 's'} away. Click to change hop depth.`}
              onClick={cycleHopLimit}
              style={nvis.traceHopCycle}
            >
              <GitBranch size={14} />
              <span>{hopLimit === 99 ? 'Related (all)' : `Related (${hopLimit}°)`}</span>
            </button>
          </div>
          <div style={nvis.traceIconBar}>
            <button type="button" data-qid="dream:trace:close" data-qs-action="DREAM_TRACE_CLOSE" title="Close relationship graph" onClick={onClose} style={nvis.traceIconButton}><X size={18} /></button>
          </div>
        </div>
        <div style={nvis.traceBody}>
          <div ref={wrapRef} style={nvis.traceGraphCanvas}>
            <svg ref={svgRef} data-qid="dream:trace:graph-svg" width="100%" height="100%" viewBox={`0 0 ${size.width} ${size.height}`} role="img" aria-label="Persisted memory relationship graph" style={nvis.traceSvg}>
              <defs>
                <filter id="trace-glow" x="-40%" y="-40%" width="180%" height="180%">
                  <feGaussianBlur stdDeviation="4" result="coloredBlur" />
                  <feMerge>
                    <feMergeNode in="coloredBlur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              <g transform={zoomTransform.toString()}>
              <g data-trace-layer="edges">
              {showTraceLinks && layout.links.map((link) => {
                const source = link.source as TraceGraphNode & SimulationNodeDatum
                const target = link.target as TraceGraphNode & SimulationNodeDatum
                const sx = source.x ?? 0
                const sy = source.y ?? 0
                const tx = target.x ?? 0
                const ty = target.y ?? 0
                const dx = tx - sx
                const dy = ty - sy
                const duplicateIndex = filteredGraph.links.filter((other: any) => other.source === link.source && other.target === link.target).findIndex((other) => other.id === link.id)
                const normal = duplicateIndex <= 0 ? 0 : (duplicateIndex % 2 === 0 ? 1 : -1) * (duplicateIndex * 12)
                const c1x = sx + dx * 0.42 - dy * 0.08 + normal
                const c1y = sy + dy * 0.24 + dx * 0.08
                const c2x = tx - dx * 0.42 - dy * 0.08 + normal
                const c2y = ty - dy * 0.24 + dx * 0.08
                const curve = `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${tx} ${ty}`
                return (
                  <g key={link.id}>
                    <motion.path
                      data-trace-edge="true"
                      d={curve}
                      fill="none"
                      stroke={nodeKindColor('memory')}
                      strokeOpacity={0.42}
                      strokeWidth={1.15}
                      strokeDasharray={link.hop >= 3 ? '4 5' : undefined}
                      initial={{ pathLength: 0, opacity: 0 }}
                      animate={{ pathLength: 1, opacity: 1 }}
                      transition={{ type: 'spring', stiffness: 220, damping: 26, delay: 0.42 + 0.08 * link.hop }}
                    />
                  </g>
                )
              })}
              </g>
              <g data-trace-layer="nodes">
              {layout.nodes.map((node) => {
                const showNodeLabel = false
                return (
                  <motion.g
                    key={node.id}
                    onMouseEnter={() => setHoveredNodeId(node.id)}
                    onMouseLeave={() => setHoveredNodeId((current) => current === node.id ? null : current)}
                    onClick={() => handleNodeClick(node)}
                    initial={{ opacity: 0, x: size.width * 0.48, y: size.height * 0.52, scale: node.id === filteredGraph.rootId ? 0.9 : 0.58 }}
                    animate={{ opacity: 1, x: node.x ?? 0, y: node.y ?? 0, scale: 1 }}
                    transition={{ type: 'spring', stiffness: 300, damping: 22, mass: 0.7, delay: 0.035 * node.hop }}
                    data-trace-node-kind={node.kind}
                  >
                    <circle r={Math.max(26, node.radius + 16)} fill="transparent" pointerEvents="all" />
                    <circle r={node.radius + 8} fill={node.color} opacity={0.14} filter="url(#trace-glow)" />
                    {node.id === selectedNodeId && (
                      <motion.circle
                        r={node.radius + 13}
                        fill="none"
                        stroke="#f8fafc"
                        strokeWidth={2}
                        strokeOpacity={0.86}
                        initial={{ scale: 0.92, opacity: 0 }}
                        animate={{ scale: [1, 1.08, 1], opacity: [0.72, 1, 0.72] }}
                        transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
                      />
                    )}
                    <circle r={node.radius} fill="rgba(10,15,25,0.94)" stroke={node.color} strokeWidth={node.id === filteredGraph.rootId ? 4 : 2.5} />
                    <foreignObject x={-node.radius + 6} y={-node.radius + 6} width={(node.radius - 6) * 2} height={(node.radius - 6) * 2}>
                      {(node.kind === 'media' || node.kind === 'video') && node.thumbnailUrl ? (
                        <div style={nvis.traceNodeMediaPanel}>
                          <img src={node.thumbnailUrl} alt="" style={nvis.traceNodeMediaImage} />
                          <span style={nvis.traceNodeIconOverlay}>
                            {node.kind === 'video' ? <Film size={13} /> : <Image size={13} />}
                          </span>
                        </div>
                      ) : (
                        <div style={nvis.traceNodeGlyphPanel}>
                          {node.kind === 'audio' ? <Volume2 size={playingAudioNodeId === node.id ? 18 : 16} /> : node.kind === 'video' ? <Film size={16} /> : node.kind === 'media' ? <Image size={16} /> : node.kind === 'person' ? <UserRound size={16} /> : node.kind === 'place' ? <MapPin size={16} /> : node.kind === 'object' ? <Package size={16} /> : <FileText size={16} />}
                        </div>
                      )}
                    </foreignObject>
                    {showNodeLabel && (
                      <foreignObject x={-92} y={node.radius + 12} width={184} height={42} style={{ overflow: 'visible' }}>
                        <div style={nvis.traceNodeLabelBox}>
                          <div style={nvis.traceNodeLabelText}>{node.label}</div>
                          <div style={nvis.traceNodeKindText}>{node.kind.replace('_', ' ')}</div>
                        </div>
                      </foreignObject>
                    )}
                  </motion.g>
                )
              })}
              </g>
              </g>
            </svg>
            {currentNode && currentNode.kind === 'memory' && (
              <div data-qid="dream:trace:node-preview" style={nvis.traceTextPreviewFloating}>
                <div style={nvis.traceTextPreviewMeta}>Text memory</div>
                <div>{currentNodeText.slice(0, 260)}</div>
              </div>
            )}
            {videoNode?.mediaUrl && (
              <div data-qid="dream:trace:video-player" style={nvis.traceVideoPlayer}>
                <div style={nvis.traceVideoHeader}>
                  <span>{videoNode.label}</span>
                  <button type="button" title="Close video" onClick={() => setVideoNode(null)} style={nvis.traceVideoClose}><X size={14} /></button>
                </div>
                <video src={videoNode.mediaUrl} controls autoPlay style={nvis.traceVideoElement} />
              </div>
            )}
          </div>
        </div>
        <table style={nvis.traceHiddenTable}>
          <caption>Memory trace graph nodes and links</caption>
          <tbody>
            {filteredGraph.nodes.map((node) => (
              <tr key={node.id}><th>{node.label}</th><td>{node.kind}</td><td>{node.tom_state_type || ''}</td><td>{node.tom_tags?.join(', ') || ''}</td></tr>
            ))}
          </tbody>
        </table>
      </motion.div>
    </div>,
    document.body
  )
}
