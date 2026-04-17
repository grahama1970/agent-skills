import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'
import type { SimulationNodeDatum, SimulationLinkDatum } from 'd3-force'
import { NVIS } from '../theme'
import { MOCK_LEMMA_NODES, MOCK_LEMMA_EDGES } from '../api/mock'
import { recallDocuments } from '../api/client'
import EvidenceCasePanel from '../components/EvidenceCasePanel'
import type { LemmaNode, LemmaEdge, ProofStatus } from '../types'

// --- Layout modes (V9.7) ---
type LayoutMode = 'force' | 'radial' | 'hierarchy'

// --- Provenance steps (V9.10) ---
const PROVENANCE_STEPS = ['source', 'mapping', 'flag', 'evidence', 'proof'] as const

// --- Types for simulation ---
interface SimNode extends SimulationNodeDatum {
  id: string
  data: LemmaNode
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  data: LemmaEdge
}

// --- Colors ---
const PROOF_COLORS: Record<ProofStatus, string> = {
  proven: '#00ff88',
  unproven: '#ffaa00',
  partial: '#4a9eff',
  axiom: '#999999',
}

const PROOF_LABELS: Record<ProofStatus, string> = {
  proven: 'Proven',
  unproven: 'Unproven',
  partial: 'Partial',
  axiom: 'Axiom',
}

// --- Filter chips ---
interface FilterChipProps {
  label: string
  color: string
  active: boolean
  onToggle: () => void
}

function FilterChip({ label, color, active, onToggle }: FilterChipProps) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      onClick={onToggle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      aria-pressed={active}
      style={{
        padding: '4px 10px',
        fontSize: 10,
        fontWeight: active ? 600 : 400,
        fontFamily: 'monospace',
        border: `1px solid ${active || hovered ? color : NVIS.borderSolid}`,
        borderRadius: 12,
        background: active ? `${color}1a` : hovered ? `${color}0d` : 'transparent',
        color: active || hovered ? color : NVIS.dim,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        transition: 'border-color 0.1s, background 0.1s, color 0.1s',
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: 3, background: color, flexShrink: 0 }} />
      {label}
    </button>
  )
}

// --- Detail panel ---
interface DetailPanelProps {
  node: LemmaNode
  onClose: () => void
  onCreateEvidence: (node: LemmaNode) => void
}

function DetailPanel({ node, onClose, onCreateEvidence }: DetailPanelProps) {
  const statusColor = PROOF_COLORS[node.proofStatus]

  return (
    <div style={{
      width: 360,
      flexShrink: 0,
      background: NVIS.surface,
      borderLeft: `1px solid ${NVIS.borderSolid}`,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 14px',
        borderBottom: `1px solid ${NVIS.borderSolid}`,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: NVIS.white }}>{node.label}</div>
          <div style={{ fontSize: 10, color: NVIS.dim, marginTop: 2 }}>ID: {node.id}</div>
        </div>
        <button
          onClick={onClose}
          aria-label="Close detail panel"
          style={{
            background: 'none',
            border: 'none',
            color: NVIS.dim,
            fontSize: 16,
            cursor: 'pointer',
            padding: '2px 6px',
            fontFamily: 'monospace',
          }}
        >
          X
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
        {/* Status badge */}
        <div style={{ marginBottom: 14 }}>
          <span style={{
            fontSize: 10,
            fontWeight: 600,
            padding: '3px 10px',
            borderRadius: 3,
            background: `${statusColor}1a`,
            border: `1px solid ${statusColor}40`,
            color: statusColor,
            textTransform: 'uppercase',
          }}>
            {PROOF_LABELS[node.proofStatus]}
          </span>
        </div>

        {/* Metrics */}
        <div style={{ display: 'flex', gap: 16, marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: NVIS.dim, marginBottom: 2 }}>
              Impact Score
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: NVIS.white }}>
              {node.impactScore.toFixed(2)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: NVIS.dim, marginBottom: 2 }}>
              Dependencies
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: NVIS.white }}>
              {node.dependencyCount}
            </div>
          </div>
        </div>

        {/* Lean4 snippet */}
        {node.lean4Snippet && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: NVIS.dim, marginBottom: 4 }}>
              Lean4 Snippet
            </div>
            <pre style={{
              padding: '10px 12px',
              background: NVIS.surface2,
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: 4,
              fontSize: 10,
              color: NVIS.white,
              fontFamily: 'monospace',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              margin: 0,
              lineHeight: 1.5,
            }}>
              {node.lean4Snippet}
            </pre>
          </div>
        )}

        {/* Linked requirements */}
        {node.requirementIds.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: NVIS.dim, marginBottom: 6 }}>
              Linked Requirements
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {node.requirementIds.map((rid) => (
                <span
                  key={rid}
                  style={{
                    fontSize: 10,
                    padding: '2px 8px',
                    borderRadius: 3,
                    background: `${NVIS.accent}1a`,
                    color: NVIS.accent,
                    border: `1px solid ${NVIS.accent}30`,
                  }}
                >
                  {rid}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* V9.10: Provenance chain stepper */}
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: NVIS.dim, marginBottom: 8 }}>
            Provenance Chain
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
            {PROVENANCE_STEPS.map((step, i) => {
              // Color by completion: proven=all green, partial=first 3 green, unproven=first 2, axiom=just source
              const completedCount = node.proofStatus === 'proven' ? 5
                : node.proofStatus === 'partial' ? 3
                : node.proofStatus === 'axiom' ? 1
                : 2
              const dotColor = i < completedCount ? '#00ff88' : NVIS.dim
              return (
                <div key={step} style={{ display: 'flex', alignItems: 'center' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                    <div style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      background: i < completedCount ? dotColor : 'transparent',
                      border: `2px solid ${dotColor}`,
                    }} />
                    <span style={{ fontSize: 7, color: dotColor, textTransform: 'capitalize' }}>{step}</span>
                  </div>
                  {i < PROVENANCE_STEPS.length - 1 && (
                    <div style={{
                      width: 24,
                      height: 2,
                      background: i < completedCount - 1 ? '#00ff88' : NVIS.borderSolid,
                      margin: '0 2px',
                      marginBottom: 12,
                    }} />
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{
        padding: '10px 14px',
        borderTop: `1px solid ${NVIS.borderSolid}`,
        flexShrink: 0,
      }}>
        <button
          onClick={() => onCreateEvidence(node)}
          style={{
            width: '100%',
            padding: '8px 12px',
            fontSize: 11,
            fontWeight: 600,
            fontFamily: 'monospace',
            background: NVIS.accent,
            border: 'none',
            borderRadius: 4,
            color: '#000',
            cursor: 'pointer',
          }}
        >
          Create Evidence Case
        </button>
      </div>
    </div>
  )
}

// --- Main view ---
export default function LemmaGraphView() {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [activeFilters, setActiveFilters] = useState<Set<ProofStatus>>(
    new Set(['proven', 'unproven', 'partial', 'axiom'])
  )
  const [zoom, setZoom] = useState(1)
  const [nodePositions, setNodePositions] = useState<Map<string, { x: number; y: number }>>(new Map())
  const [evidencePanelOpen, setEvidencePanelOpen] = useState(false)
  const [evidencePrefill, setEvidencePrefill] = useState<{ controlId?: string; claim?: string; sources?: string[] }>({})
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const simulationRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null)
  const dragRef = useRef<{ nodeId: string; active: boolean } | null>(null)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('force')
  const [whatIfActive, setWhatIfActive] = useState(false)
  const [failedNodes, setFailedNodes] = useState<Set<string>>(new Set())
  const [cascadedNodes, setCascadedNodes] = useState<Set<string>>(new Set())
  const [memoryError, setMemoryError] = useState<string | null>(null)
  const [memoryNodes, setMemoryNodes] = useState<LemmaNode[]>([])

  // V9.14: /memory wiring
  useEffect(() => {
    recallDocuments('formal verification lemma proof')
      .then((result) => {
        const extra: LemmaNode[] = (result.results ?? [])
          .filter((r) => r.metadata?.id && r.metadata?.label)
          .map((r) => ({
            id: r.metadata.id as string,
            label: r.metadata.label as string,
            proofStatus: (r.metadata.proofStatus as ProofStatus) ?? 'unproven',
            dependencyCount: (r.metadata.dependencyCount as number) ?? 0,
            impactScore: (r.metadata.impactScore as number) ?? 0.5,
            lean4Snippet: r.metadata.lean4Snippet as string | undefined,
            requirementIds: (r.metadata.requirementIds as string[]) ?? [],
          }))
        setMemoryNodes(extra)
      })
      .catch((e) => {
        setMemoryError(e instanceof Error ? e.message : 'Memory service unreachable')
      })
  }, [])

  // Merge mock + memory nodes, then filter
  const allNodes = useMemo(() => {
    const mockIds = new Set(MOCK_LEMMA_NODES.map((n) => n.id))
    const extra = memoryNodes.filter((n) => !mockIds.has(n.id))
    return [...MOCK_LEMMA_NODES, ...extra]
  }, [memoryNodes])

  const filteredNodes = useMemo(
    () => allNodes.filter((n) => activeFilters.has(n.proofStatus)),
    [activeFilters, allNodes],
  )

  const filteredNodeIds = useMemo(
    () => new Set(filteredNodes.map((n) => n.id)),
    [filteredNodes],
  )

  const filteredEdges = useMemo(
    () => MOCK_LEMMA_EDGES.filter((e) => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target)),
    [filteredNodeIds],
  )

  const selectedNode = useMemo(
    () => allNodes.find((n) => n.id === selectedNodeId) ?? null,
    [selectedNodeId, allNodes],
  )

  const toggleFilter = (status: ProofStatus) => {
    setActiveFilters((prev) => {
      const next = new Set(prev)
      if (next.has(status)) {
        if (next.size > 1) next.delete(status) // keep at least one
      } else {
        next.add(status)
      }
      return next
    })
  }

  // Measure container
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        })
      }
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  // Run simulation (only in force mode)
  useEffect(() => {
    if (layoutMode !== 'force') return
    const simNodes: SimNode[] = filteredNodes.map((n) => {
      const existing = nodePositions.get(n.id)
      return {
        id: n.id,
        data: n,
        x: existing?.x ?? dimensions.width / 2 + (Math.random() - 0.5) * 200,
        y: existing?.y ?? dimensions.height / 2 + (Math.random() - 0.5) * 200,
      }
    })

    const simLinks: SimLink[] = filteredEdges.map((e) => ({
      source: e.source,
      target: e.target,
      data: e,
    }))

    const sim = forceSimulation<SimNode>(simNodes)
      .force('link', forceLink<SimNode, SimLink>(simLinks).id((d) => d.id).distance(120).strength(0.4))
      .force('charge', forceManyBody().strength(-300))
      .force('center', forceCenter(dimensions.width / 2, dimensions.height / 2))
      .force('collide', forceCollide(40))
      .alpha(0.8)
      .on('tick', () => {
        const positions = new Map<string, { x: number; y: number }>()
        for (const node of simNodes) {
          positions.set(node.id, { x: node.x ?? 0, y: node.y ?? 0 })
        }
        setNodePositions(new Map(positions))
      })

    simulationRef.current = sim

    return () => {
      sim.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredNodes, filteredEdges, dimensions.width, dimensions.height, layoutMode])

  const handleCreateEvidence = (node: LemmaNode) => {
    setEvidencePrefill({
      controlId: node.requirementIds[0],
      claim: `${node.label} proof status: ${node.proofStatus}`,
      sources: node.requirementIds,
    })
    setEvidencePanelOpen(true)
  }

  const resetLayout = useCallback(() => {
    if (simulationRef.current) {
      simulationRef.current.alpha(1).restart()
    }
  }, [])

  // V9.6: What-If BFS cascade
  const handleWhatIfClick = useCallback((nodeId: string) => {
    if (!whatIfActive) return
    const newFailed = new Set(failedNodes)
    if (newFailed.has(nodeId)) {
      newFailed.delete(nodeId)
    } else {
      newFailed.add(nodeId)
    }
    // BFS to find all dependent nodes
    const cascaded = new Set<string>()
    const queue = [...newFailed]
    const visited = new Set<string>(newFailed)
    while (queue.length > 0) {
      const current = queue.shift()!
      for (const edge of filteredEdges) {
        if (edge.source === current && !visited.has(edge.target)) {
          visited.add(edge.target)
          cascaded.add(edge.target)
          queue.push(edge.target)
        }
      }
    }
    setFailedNodes(newFailed)
    setCascadedNodes(cascaded)
  }, [whatIfActive, failedNodes, filteredEdges])

  // V9.7: Apply radial/hierarchy layout
  useEffect(() => {
    if (layoutMode === 'force') return // handled by simulation
    const positions = new Map<string, { x: number; y: number }>()
    const cx = dimensions.width / 2
    const cy = dimensions.height / 2

    if (layoutMode === 'radial') {
      // Group by proof status, concentric circles
      const statusOrder: ProofStatus[] = ['proven', 'partial', 'unproven', 'axiom']
      const groups = new Map<ProofStatus, LemmaNode[]>()
      for (const n of filteredNodes) {
        if (!groups.has(n.proofStatus)) groups.set(n.proofStatus, [])
        groups.get(n.proofStatus)!.push(n)
      }
      let ring = 0
      for (const status of statusOrder) {
        const nodes = groups.get(status) ?? []
        if (nodes.length === 0) continue
        const radius = 80 + ring * 100
        nodes.forEach((n, i) => {
          const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2
          positions.set(n.id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) })
        })
        ring++
      }
    } else if (layoutMode === 'hierarchy') {
      // Compute depth from edges (BFS from roots)
      const inDegree = new Map<string, number>()
      for (const n of filteredNodes) inDegree.set(n.id, 0)
      for (const e of filteredEdges) inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1)
      const depth = new Map<string, number>()
      const queue: string[] = []
      for (const [id, deg] of inDegree) { if (deg === 0) { depth.set(id, 0); queue.push(id) } }
      while (queue.length > 0) {
        const cur = queue.shift()!
        for (const e of filteredEdges) {
          if (e.source === cur && !depth.has(e.target)) {
            depth.set(e.target, (depth.get(cur) ?? 0) + 1)
            queue.push(e.target)
          }
        }
      }
      // Assign remaining unvisited nodes
      for (const n of filteredNodes) { if (!depth.has(n.id)) depth.set(n.id, 0) }
      const byDepth = new Map<number, LemmaNode[]>()
      for (const n of filteredNodes) {
        const d = depth.get(n.id) ?? 0
        if (!byDepth.has(d)) byDepth.set(d, [])
        byDepth.get(d)!.push(n)
      }
      const spacing = 120
      for (const [d, nodes] of byDepth) {
        const y = 60 + d * spacing
        const totalW = (nodes.length - 1) * 100
        const startX = cx - totalW / 2
        nodes.forEach((n, i) => {
          positions.set(n.id, { x: startX + i * 100, y })
        })
      }
    }
    if (positions.size > 0) {
      if (simulationRef.current) simulationRef.current.stop()
      setNodePositions(positions)
    }
  }, [layoutMode, filteredNodes, filteredEdges, dimensions.width, dimensions.height])

  // --- Drag handlers ---
  const handleMouseDown = useCallback((nodeId: string, e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { nodeId, active: true }
    if (simulationRef.current) {
      simulationRef.current.alphaTarget(0.3).restart()
    }
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragRef.current?.active || !svgRef.current) return
    const svg = svgRef.current
    const rect = svg.getBoundingClientRect()
    const x = (e.clientX - rect.left) / zoom
    const y = (e.clientY - rect.top) / zoom
    const nodeId = dragRef.current.nodeId

    if (simulationRef.current) {
      const simNodes = simulationRef.current.nodes()
      const node = simNodes.find((n) => n.id === nodeId)
      if (node) {
        node.fx = x
        node.fy = y
      }
    }
  }, [zoom])

  const handleMouseUp = useCallback(() => {
    if (!dragRef.current?.active) return
    const nodeId = dragRef.current.nodeId
    dragRef.current = null

    if (simulationRef.current) {
      simulationRef.current.alphaTarget(0)
      const simNodes = simulationRef.current.nodes()
      const node = simNodes.find((n) => n.id === nodeId)
      if (node) {
        node.fx = null
        node.fy = null
      }
    }
  }, [])

  // Node radius based on impact score
  const nodeRadius = (n: LemmaNode) => 12 + n.impactScore * 18

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 80px)', minHeight: 0 }}>
      {/* V9.15: Error banner */}
      {memoryError && (
        <div style={{
          background: '#1a0000',
          border: '1px solid #ff4444',
          borderRadius: 4,
          padding: '8px 12px',
          margin: '8px 16px 0',
          color: '#ff4444',
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 12,
          flexShrink: 0,
        }}>
          Memory: {memoryError}
        </div>
      )}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      {/* Graph area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        {/* Toolbar */}
        <div style={{
          padding: '8px 16px',
          borderBottom: `1px solid ${NVIS.borderSolid}`,
          background: NVIS.surface,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: NVIS.white, marginRight: 8 }}>
            Lemma Graph
          </span>

          {/* Filter chips */}
          {(Object.keys(PROOF_COLORS) as ProofStatus[]).map((status) => (
            <FilterChip
              key={status}
              label={PROOF_LABELS[status]}
              color={PROOF_COLORS[status]}
              active={activeFilters.has(status)}
              onToggle={() => toggleFilter(status)}
            />
          ))}

          {/* V9.7: Layout mode toggle */}
          <div style={{ display: 'flex', gap: 2, background: NVIS.surface2, borderRadius: 4, padding: 2, marginLeft: 8 }}>
            {(['force', 'radial', 'hierarchy'] as LayoutMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setLayoutMode(m)}
                style={{
                  padding: '3px 10px',
                  fontSize: 10,
                  fontFamily: 'monospace',
                  fontWeight: layoutMode === m ? 600 : 400,
                  border: 'none',
                  borderRadius: 3,
                  cursor: 'pointer',
                  background: layoutMode === m ? `${NVIS.accent}1a` : 'transparent',
                  color: layoutMode === m ? NVIS.accent : NVIS.dim,
                  textTransform: 'capitalize',
                }}
              >
                {m}
              </button>
            ))}
          </div>

          {/* V9.9: What-If toggle */}
          <button
            onClick={() => {
              setWhatIfActive((prev) => !prev)
              if (whatIfActive) { setFailedNodes(new Set()); setCascadedNodes(new Set()) }
            }}
            style={{
              padding: '3px 10px',
              fontSize: 10,
              fontFamily: 'monospace',
              fontWeight: whatIfActive ? 600 : 400,
              border: `1px solid ${whatIfActive ? NVIS.red : NVIS.borderSolid}`,
              borderRadius: 12,
              cursor: 'pointer',
              background: whatIfActive ? `${NVIS.red}1a` : 'transparent',
              color: whatIfActive ? NVIS.red : NVIS.dim,
              marginLeft: 4,
            }}
          >
            What-If
          </button>

          <div style={{ flex: 1 }} />

          {/* Zoom controls */}
          <button
            onClick={() => setZoom((z) => Math.min(z + 0.2, 3))}
            aria-label="Zoom in"
            style={{
              padding: '4px 10px',
              fontSize: 13,
              fontFamily: 'monospace',
              background: NVIS.surface2,
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: 4,
              color: NVIS.dim,
              cursor: 'pointer',
            }}
          >
            +
          </button>
          <button
            onClick={() => setZoom((z) => Math.max(z - 0.2, 0.2))}
            aria-label="Zoom out"
            style={{
              padding: '4px 10px',
              fontSize: 13,
              fontFamily: 'monospace',
              background: NVIS.surface2,
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: 4,
              color: NVIS.dim,
              cursor: 'pointer',
            }}
          >
            -
          </button>
          <span style={{ fontSize: 10, color: NVIS.dim, minWidth: 36, textAlign: 'center' }}>
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={resetLayout}
            style={{
              padding: '4px 10px',
              fontSize: 10,
              fontFamily: 'monospace',
              background: NVIS.surface2,
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: 4,
              color: NVIS.dim,
              cursor: 'pointer',
            }}
          >
            Reset Layout
          </button>
        </div>

        {/* SVG graph */}
        <div
          ref={containerRef}
          style={{ flex: 1, overflow: 'hidden', background: NVIS.bg }}
        >
          <svg
            ref={svgRef}
            width={dimensions.width}
            height={dimensions.height}
            style={{ cursor: dragRef.current?.active ? 'grabbing' : 'default' }}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
          >
            <g transform={`scale(${zoom})`}>
              {/* Arrow marker defs */}
              <defs>
                {(Object.keys(PROOF_COLORS) as ProofStatus[]).map((status) => (
                  <marker
                    key={status}
                    id={`arrow-${status}`}
                    viewBox="0 0 10 10"
                    refX={10}
                    refY={5}
                    markerWidth={6}
                    markerHeight={6}
                    orient="auto"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" fill={`${PROOF_COLORS[status]}80`} />
                  </marker>
                ))}
                <marker
                  id="arrow-default"
                  viewBox="0 0 10 10"
                  refX={10}
                  refY={5}
                  markerWidth={6}
                  markerHeight={6}
                  orient="auto"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill={`${NVIS.dim}60`} />
                </marker>
              </defs>

              {/* Edges */}
              {filteredEdges.map((edge, idx) => {
                const sourcePos = nodePositions.get(edge.source)
                const targetPos = nodePositions.get(edge.target)
                if (!sourcePos || !targetPos) return null

                const targetNode = filteredNodes.find((n) => n.id === edge.target)
                const r = targetNode ? nodeRadius(targetNode) : 20

                // Shorten line to stop at node boundary
                const dx = targetPos.x - sourcePos.x
                const dy = targetPos.y - sourcePos.y
                const dist = Math.sqrt(dx * dx + dy * dy)
                const offsetX = dist > 0 ? (dx / dist) * (r + 4) : 0
                const offsetY = dist > 0 ? (dy / dist) * (r + 4) : 0

                const strokeColor = edge.relation === 'contradicts' ? `${NVIS.red}50` : `${NVIS.dim}30`
                const dashArray = edge.relation === 'contradicts' ? '4,4' : undefined

                return (
                  <line
                    key={idx}
                    x1={sourcePos.x}
                    y1={sourcePos.y}
                    x2={targetPos.x - offsetX}
                    y2={targetPos.y - offsetY}
                    stroke={strokeColor}
                    strokeWidth={1 + edge.strength}
                    strokeDasharray={dashArray}
                    markerEnd="url(#arrow-default)"
                  />
                )
              })}

              {/* Nodes */}
              {filteredNodes.map((node) => {
                const pos = nodePositions.get(node.id)
                if (!pos) return null
                const r = nodeRadius(node)
                const color = PROOF_COLORS[node.proofStatus]
                const isSelected = node.id === selectedNodeId

                // V9.9: What-if coloring
                const isFailed = failedNodes.has(node.id)
                const isCascaded = cascadedNodes.has(node.id)
                const displayColor = isFailed ? '#ff4444' : isCascaded ? '#ffaa00' : color

                return (
                  <g
                    key={node.id}
                    transform={`translate(${pos.x}, ${pos.y})`}
                    style={{ cursor: whatIfActive ? 'crosshair' : 'grab' }}
                    onMouseDown={(e) => handleMouseDown(node.id, e)}
                    onClick={() => {
                      if (whatIfActive) { handleWhatIfClick(node.id) }
                      else { setSelectedNodeId(node.id === selectedNodeId ? null : node.id) }
                    }}
                  >
                    {/* Selection ring */}
                    {isSelected && (
                      <circle
                        r={r + 4}
                        fill="none"
                        stroke={NVIS.accent}
                        strokeWidth={2}
                      />
                    )}
                    {/* Node circle */}
                    <circle
                      r={r}
                      fill={`${displayColor}30`}
                      stroke={displayColor}
                      strokeWidth={isSelected ? 2 : 1.5}
                    />
                    {/* Label */}
                    <text
                      y={r + 14}
                      textAnchor="middle"
                      fill={NVIS.white}
                      fontSize={9}
                      fontFamily="monospace"
                      style={{ pointerEvents: 'none' }}
                    >
                      {node.label}
                    </text>
                    {/* Impact score */}
                    <text
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill={color}
                      fontSize={10}
                      fontWeight={700}
                      fontFamily="monospace"
                      style={{ pointerEvents: 'none' }}
                    >
                      {node.impactScore.toFixed(2)}
                    </text>
                  </g>
                )
              })}
            </g>
          </svg>
        </div>

        {/* Status bar */}
        <div style={{
          height: 28,
          background: NVIS.surface,
          borderTop: `1px solid ${NVIS.borderSolid}`,
          display: 'flex',
          alignItems: 'center',
          padding: '0 16px',
          flexShrink: 0,
          fontSize: 11,
          color: NVIS.dim,
          gap: 0,
        }}
          role="status"
          aria-live="polite"
        >
          <span>{filteredNodes.length} nodes</span>
          <span style={{ margin: '0 10px', color: NVIS.borderSolid }}>|</span>
          <span>{filteredEdges.length} edges</span>
          <span style={{ margin: '0 10px', color: NVIS.borderSolid }}>|</span>
          <span>
            {filteredNodes.filter((n) => n.proofStatus === 'proven').length} proven
            {' / '}
            {filteredNodes.filter((n) => n.proofStatus === 'unproven').length} unproven
          </span>
          {selectedNode && (
            <>
              <span style={{ margin: '0 10px', color: NVIS.borderSolid }}>|</span>
              <span>
                Selected: <span style={{ color: NVIS.accent }}>{selectedNode.label}</span>
              </span>
            </>
          )}
        </div>
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <DetailPanel
          node={selectedNode}
          onClose={() => setSelectedNodeId(null)}
          onCreateEvidence={handleCreateEvidence}
        />
      )}

      {/* Evidence Case Panel */}
      <EvidenceCasePanel
        open={evidencePanelOpen}
        onClose={() => setEvidencePanelOpen(false)}
        prefillContext={evidencePrefill}
      />
      </div>
    </div>
  )
}
