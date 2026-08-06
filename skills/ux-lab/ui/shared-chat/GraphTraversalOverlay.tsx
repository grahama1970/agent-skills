import { useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { Database, Loader2, Search, Shield, XCircle } from 'lucide-react'
import { useRegisterAction } from './_support/useRegisterAction'
import {
  SPARTA_FLOW_NODE_HEIGHT,
  SPARTA_FLOW_NODE_WIDTH,
  SpartaFlowNodeCard,
  type SpartaFlowRelationType,
  SpartaIconEdge,
  layoutDagreFlowElements,
} from './_support/SpartaFlowPrimitives'
import '@xyflow/react/dist/style.css'
import './_support/SupplyChainFlow.css'

export type TraceEntity = {
  label: string
  value: string
  type: string
}

export type GraphTraversalRequest = {
  phaseTitle: string
  entities: TraceEntity[]
}

export type GraphTraversalNode = {
  id: string
  label: string
  type: string
  evidence?: string
}

export type GraphTraversalLink = {
  source: string
  target: string
  label: string
}

export type GraphTraversalData = {
  nodes: GraphTraversalNode[]
  links: GraphTraversalLink[]
  receipt?: Record<string, unknown>
}

type GraphTraversalNodeKind = 'entity' | 'evidence' | 'control'
type GraphTraversalNodeStatus = 'source-backed' | 'request-only'

type GraphTraversalFlowNodeData = Record<string, unknown> & {
  label: string
  detail: string
  nodeKind: GraphTraversalNodeKind
  status: GraphTraversalNodeStatus
}

type GraphTraversalEdgeData = Record<string, unknown> & {
  label: string
  relationType: SpartaFlowRelationType
}

export type GraphTraversalFlowNode = Node<GraphTraversalFlowNodeData, 'graphTraversalNode'>
export type GraphTraversalFlowEdge = Edge<GraphTraversalEdgeData>

export type GraphTraversalFlowModel = {
  nodes: GraphTraversalFlowNode[]
  edges: GraphTraversalFlowEdge[]
  contract: {
    renderer: '@xyflow/react'
    layout: 'dagre-lr'
    node_count: number
    edge_count: number
    bounded_node_limit: number
  }
  validation: {
    ok: boolean
    errors: string[]
  }
}

const FLOW_NODE_WIDTH = SPARTA_FLOW_NODE_WIDTH
const FLOW_NODE_HEIGHT = SPARTA_FLOW_NODE_HEIGHT
const BOUNDED_NODE_LIMIT = 18

const graphTraversalNodeTypes = {
  graphTraversalNode: GraphTraversalNodeCard,
}

const graphTraversalEdgeTypes = {
  iconEdge: SpartaIconEdge,
}

const defaultEdgeOptions = {
  markerEnd: {
    type: MarkerType.ArrowClosed,
    width: 14,
    height: 14,
    color: '#94a3b8',
  },
}

export function GraphTraversalOverlay({
  request,
  onClose,
}: {
  request: GraphTraversalRequest
  onClose: () => void
}): JSX.Element {
  useRegisterAction('shared-chat:graph-traversal:close', {
    app: 'sparta-explorer',
    action: 'SHARED_CHAT_GRAPH_TRAVERSAL_CLOSE',
    label: 'Close Graph Traversal',
    description: 'Close the SPARTA chat Memory graph traversal overlay',
  })
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading')
  const [data, setData] = useState<GraphTraversalData>({ nodes: [], links: [] })
  const [error, setError] = useState<string | null>(null)
  const [inspectedNodeId, setInspectedNodeId] = useState<string | null>(null)

  // HUD takeover contract (grahama1970/sparta#44): ESC closes and the page
  // behind cannot scroll while the overlay is open — including the loading and
  // failed states, which is why both effects mount unconditionally.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setState('loading')
    setError(null)
    fetch('/api/sparta/chat/graph-traversal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entities: request.entities, phase_title: request.phaseTitle }),
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(String(payload?.error ?? payload?.detail ?? `HTTP ${response.status}`))
        return payload as GraphTraversalData
      })
      .then((payload) => {
        if (cancelled) return
        setData(payload)
        setState('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
        setState('failed')
      })
    return () => {
      cancelled = true
    }
  }, [request])

  const graphData = useMemo(() => graphDataWithRequestFallback(data, request.entities), [data, request.entities])
  const flowModel = useMemo(() => buildGraphTraversalFlowModel(graphData), [graphData])

  const inspectedNode = graphData.nodes.find((node) => node.id === inspectedNodeId) ?? graphData.nodes[0] ?? null
  const inspectedEdges = inspectedNode
    ? data.links.filter((link) => link.source === inspectedNode.id || link.target === inspectedNode.id)
    : []

  return (
    <div
      // Blurred, dimmed backdrop over the console; z-index stays 220 (design-tokens.css)
      // — Tailwind z-50 would regress under the drawer stack.
      className="chat-graph-overlay"
      data-qid="shared-chat:graph-traversal:overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Graph traversal overlay"
      onMouseDown={(event) => {
        // Backdrop click routes through the same close handler the registered
        // SHARED_CHAT_GRAPH_TRAVERSAL_CLOSE action drives.
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div className="chat-graph-overlay__panel" data-qid="shared-chat:graph-traversal:panel">
      <div className="chat-graph-overlay__header">
        <div>
          <div className="chat-graph-overlay__eyebrow">React Flow Graph Traversal</div>
          <h2>Memory path for {request.entities[0]?.value ?? request.phaseTitle}</h2>
        </div>
        <div className="chat-graph-overlay__header-hud">
          <span className="chat-graph-overlay__seed-chip" data-qid="shared-chat:graph-traversal:seed-chip" title="Traversal seed entity">
            SEED&nbsp;{request.entities[0]?.value ?? request.phaseTitle}
          </span>
          <span className="chat-graph-overlay__esc-hint" aria-hidden="true">PRESS ESC TO CLOSE</span>
          <button
            type="button"
            onClick={onClose}
            data-qid="shared-chat:graph-traversal:close"
            data-qs-action="SHARED_CHAT_GRAPH_TRAVERSAL_CLOSE"
            title="Close graph traversal"
            aria-label="Close graph traversal"
          >
            <XCircle size={18} strokeWidth={1.9} />
          </button>
        </div>
      </div>

      <div className="chat-graph-overlay__body">
        <div className="chat-graph-overlay__canvas supply-chain-flow-canvas" data-state={state} data-qid="shared-chat:graph-traversal:flow">
          {state === 'loading' ? (
            <div className="chat-graph-overlay__loading">
              <Loader2 size={18} className="chat-thinking-trace__running-spinner" />
              Loading bounded traversal
            </div>
          ) : null}
          {state === 'failed' ? (
            <div className="chat-graph-overlay__error">
              Graph traversal unavailable: {error}
            </div>
          ) : null}
          {state === 'ready' ? (
            <>
              <ReactFlowProvider>
                <ReactFlow<GraphTraversalFlowNode, GraphTraversalFlowEdge>
                  nodes={flowModel.nodes}
                  edges={flowModel.edges}
                  nodeTypes={graphTraversalNodeTypes}
                  edgeTypes={graphTraversalEdgeTypes}
                  defaultEdgeOptions={defaultEdgeOptions}
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={false}
                  panOnDrag={false}
                  zoomOnScroll={false}
                  zoomOnPinch
                  zoomOnDoubleClick={false}
                  fitView
                  fitViewOptions={{ padding: 0.22 }}
                  minZoom={0.65}
                  maxZoom={1.6}
                  proOptions={{ hideAttribution: true }}
                  aria-label="Read-only bounded Memory graph traversal"
                >
                  <Controls style={{ background: '#111827', border: '1px solid rgba(148,163,184,0.28)' }} />
                  <Background color="rgba(148,163,184,0.22)" gap={18} />
                </ReactFlow>
              </ReactFlowProvider>
              <GraphTraversalA11yTable nodes={flowModel.nodes} edges={flowModel.edges} />
            </>
          ) : null}
        </div>
        <aside className="chat-graph-overlay__inspector">
          {inspectedNode ? (
            <section data-qid="shared-chat:graph-traversal:node-inspector">
              <div className="chat-graph-overlay__eyebrow">Node Inspection</div>
              <div className="chat-graph-overlay__inspected-node">
                <strong>{inspectedNode.label}</strong>
                <span>{readableNodeType(inspectedNode)}</span>
              </div>
              <div className="chat-graph-overlay__eyebrow chat-graph-overlay__eyebrow--spaced">Known Relationships</div>
              <ul className="chat-graph-overlay__edge-ledger" data-qid="shared-chat:graph-traversal:edge-ledger">
                {inspectedEdges.length === 0 ? (
                  <li className="chat-graph-overlay__edge-row chat-graph-overlay__edge-row--empty">No source-backed links for this node.</li>
                ) : (
                  inspectedEdges.map((link, index) => {
                    const outbound = link.source === inspectedNode.id
                    const otherId = outbound ? link.target : link.source
                    const other = graphData.nodes.find((node) => node.id === otherId)
                    const severity = /not[_ -]?satisfied|missing|fail/i.test(link.label)
                      ? 'critical'
                      : /inconclusive|pending|partial/i.test(link.label)
                        ? 'warning'
                        : 'neutral'
                    return (
                      <li key={`${link.source}:${link.target}:${index}`} className={`chat-graph-overlay__edge-row chat-graph-overlay__edge-row--${severity}`}>
                        <span className="chat-graph-overlay__edge-verb">{outbound ? 'enables' : 'requires'}</span>
                        <span className="chat-graph-overlay__edge-label">{link.label}</span>
                        <button
                          type="button"
                          className="chat-graph-overlay__edge-target"
                          data-qid={`shared-chat:graph-traversal:edge-target:${index}`}
                          data-qs-action="SHARED_CHAT_GRAPH_TRAVERSAL_INSPECT_NODE"
                          title={`Inspect ${other?.label ?? otherId}`}
                          onClick={() => setInspectedNodeId(otherId)}
                        >
                          {other?.label ?? otherId}
                        </button>
                      </li>
                    )
                  })
                )}
              </ul>
              <div className="chat-graph-overlay__eyebrow chat-graph-overlay__eyebrow--spaced">Evidence State</div>
              <div className="chat-graph-overlay__evidence-state" data-qid="shared-chat:graph-traversal:evidence-state">
                <div><span>Provenance</span><strong>{inspectedNode.id.startsWith('request:') ? 'REQUEST ONLY' : 'SOURCE BACKED'}</strong></div>
                <div><span>Evidence</span><strong>{inspectedNode.evidence ?? 'None recorded'}</strong></div>
              </div>
            </section>
          ) : null}
          <div className="chat-graph-overlay__eyebrow chat-graph-overlay__eyebrow--spaced">Traversal Receipt</div>
          <pre>{JSON.stringify(data.receipt ?? {
            state,
            entity_count: request.entities.length,
            renderer: flowModel.contract.renderer,
            source: 'pending_bounded_memory_recall',
          }, null, 2)}</pre>
          <div className="chat-graph-overlay__eyebrow chat-graph-overlay__eyebrow--spaced">Graph Contract</div>
          <pre>{JSON.stringify(flowModel.contract, null, 2)}</pre>
          {!flowModel.validation.ok ? (
            <>
              <div className="chat-graph-overlay__eyebrow chat-graph-overlay__eyebrow--spaced">Validation Errors</div>
              <pre>{JSON.stringify(flowModel.validation.errors, null, 2)}</pre>
            </>
          ) : null}
        </aside>
      </div>
      </div>
    </div>
  )
}

export function buildGraphTraversalFlowModel(data: GraphTraversalData): GraphTraversalFlowModel {
  const boundedNodes = data.nodes.slice(0, BOUNDED_NODE_LIMIT)
  const includedIds = new Set(boundedNodes.map((node) => node.id))
  const flowNodes: GraphTraversalFlowNode[] = boundedNodes.map((node) => ({
    id: node.id,
    type: 'graphTraversalNode',
    position: { x: 0, y: 0 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    width: FLOW_NODE_WIDTH,
    height: FLOW_NODE_HEIGHT,
    data: {
      label: node.label,
      detail: node.evidence ?? readableNodeType(node),
      nodeKind: kindForNode(node),
      status: node.id.startsWith('request:') ? 'request-only' : 'source-backed',
    },
  }))

  const flowEdges: GraphTraversalFlowEdge[] = data.links
    .filter((link) => includedIds.has(link.source) && includedIds.has(link.target))
    .map((link, index) => ({
      id: `graph-traversal-edge:${link.source}:${link.target}:${index}`,
      source: link.source,
      target: link.target,
      sourceHandle: 'out',
      targetHandle: 'in',
      type: 'iconEdge',
      data: { relationType: 'traversal', label: link.label },
      markerEnd: defaultEdgeOptions.markerEnd,
      style: { stroke: '#94a3b8', strokeWidth: 1.8 },
      labelStyle: { fill: '#cbd5e1', fontSize: 10, fontWeight: 800, letterSpacing: '0.04em', textTransform: 'uppercase' },
      labelBgStyle: { fill: '#0f172a', fillOpacity: 0.92 },
      labelBgPadding: [7, 4],
      labelBgBorderRadius: 4,
    }))

  const layouted = layoutDagreFlowElements(flowNodes, flowEdges, {
    direction: 'LR',
    nodeWidth: FLOW_NODE_WIDTH,
    nodeHeight: FLOW_NODE_HEIGHT,
    nodesep: 54,
    ranksep: 132,
    marginx: 44,
    marginy: 44,
  })
  const validation = validateGraphTraversalFlowModel(layouted.nodes, layouted.edges)

  return {
    nodes: layouted.nodes,
    edges: layouted.edges,
    contract: {
      renderer: '@xyflow/react',
      layout: 'dagre-lr',
      node_count: layouted.nodes.length,
      edge_count: layouted.edges.length,
      bounded_node_limit: BOUNDED_NODE_LIMIT,
    },
    validation,
  }
}

export function validateGraphTraversalFlowModel(
  nodes: GraphTraversalFlowNode[],
  edges: GraphTraversalFlowEdge[],
): { ok: boolean; errors: string[] } {
  const errors: string[] = []
  const nodeIds = new Set<string>()
  for (const node of nodes) {
    if (nodeIds.has(node.id)) errors.push(`duplicate_node:${node.id}`)
    nodeIds.add(node.id)
  }
  const edgeIds = new Set<string>()
  for (const edge of edges) {
    if (edgeIds.has(edge.id)) errors.push(`duplicate_edge:${edge.id}`)
    edgeIds.add(edge.id)
    if (!nodeIds.has(edge.source)) errors.push(`missing_source:${edge.id}:${edge.source}`)
    if (!nodeIds.has(edge.target)) errors.push(`missing_target:${edge.id}:${edge.target}`)
    if (edge.sourceHandle !== 'out') errors.push(`missing_source_handle:${edge.id}`)
    if (edge.targetHandle !== 'in') errors.push(`missing_target_handle:${edge.id}`)
  }
  if (hasDirectedCycle(nodes.map((node) => node.id), edges.map((edge) => [edge.source, edge.target]))) {
    errors.push('outer_graph_cycle')
  }
  return { ok: errors.length === 0, errors }
}

function GraphTraversalNodeCard({ data }: NodeProps<GraphTraversalFlowNode>): JSX.Element {
  const Icon = data.nodeKind === 'control' ? Shield : data.nodeKind === 'evidence' ? Database : Search
  const supplyClass = data.nodeKind === 'control'
    ? 'supply-flow-node--mission'
    : data.nodeKind === 'evidence'
      ? 'supply-flow-node--vendor tier-2'
      : 'supply-flow-node--service'
  const statusText = data.status === 'request-only' ? 'REQUEST' : 'SOURCE'

  return (
    <SpartaFlowNodeCard
      className={`${supplyClass} chat-graph-flow-node chat-graph-flow-node--${data.nodeKind}`}
      qid={`shared-chat:graph-node:${qidToken(data.label)}`}
      Icon={Icon}
      eyebrow={nodeKindLabel(data.nodeKind)}
      statusText={statusText}
      statusClass={data.status === 'request-only' ? 'supply-flow-status--investigating' : 'supply-flow-status--neutral'}
      label={data.label}
      detail={data.detail}
      targetHandleId="in"
      sourceHandleId="out"
      targetPosition={Position.Left}
      sourcePosition={Position.Right}
      handleClassName="chat-graph-flow-node__handle"
    />
  )
}

function GraphTraversalA11yTable({
  nodes,
  edges,
}: {
  nodes: GraphTraversalFlowNode[]
  edges: GraphTraversalFlowEdge[]
}): JSX.Element {
  return (
    <table className="chat-graph-overlay__a11y-table">
      <caption>Bounded Memory graph traversal nodes and links</caption>
      <thead>
        <tr>
          <th scope="col">Node</th>
          <th scope="col">Type</th>
          <th scope="col">Outgoing links</th>
        </tr>
      </thead>
      <tbody>
        {nodes.map((node) => (
          <tr key={node.id}>
            <td>{node.data.label}</td>
            <td>{node.data.nodeKind}</td>
            <td>{edges.filter((edge) => edge.source === node.id).map((edge) => `${edge.data?.label ?? edge.label} ${nodeLabel(edge.target, nodes)}`).join('; ') || 'None'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function graphDataWithRequestFallback(data: GraphTraversalData, entities: TraceEntity[]): GraphTraversalData {
  if (data.nodes.length > 0) return data
  return {
    nodes: entities.map((entity) => ({
      id: `request:${entity.value}`,
      label: entity.value,
      type: normalizeEntityType(entity.type),
      evidence: 'Request entity only; bounded traversal has not returned source nodes.',
    })),
    links: [],
    receipt: data.receipt,
  }
}

function kindForNode(node: GraphTraversalNode): GraphTraversalNodeKind {
  const inferredType = entityTypeFromValue(node.label)
  if (node.id.startsWith('entity:') || node.id.startsWith('request:') || ['cwe', 'cve', 'ip', 'hash'].includes(inferredType)) return 'entity'
  const type = normalizeEntityType(node.type)
  if (type === 'control' || /^rd-\d/i.test(node.label) || node.id.startsWith('control:')) return 'control'
  if (type === 'qra' || type === 'evidence') return 'evidence'
  return 'entity'
}

function readableNodeType(node: GraphTraversalNode): string {
  const type = normalizeEntityType(node.type)
  if (type === 'qra') return 'Bounded Memory evidence'
  if (type === 'control') return 'SPARTA control or requirement'
  if (type === 'cwe') return 'Extracted weakness entity'
  if (type === 'cve') return 'Extracted vulnerability entity'
  return 'Graph traversal node'
}

function nodeKindLabel(kind: GraphTraversalNodeKind): string {
  if (kind === 'control') return 'SPARTA CONTROL'
  if (kind === 'evidence') return 'MEMORY EVIDENCE'
  return 'EXTRACTED ENTITY'
}

function nodeLabel(id: string, nodes: GraphTraversalFlowNode[]): string {
  return nodes.find((node) => node.id === id)?.data.label ?? id
}

function hasDirectedCycle(nodeIds: string[], edgePairs: Array<[string, string]>): boolean {
  const incoming = new Map(nodeIds.map((id) => [id, 0]))
  const outgoing = new Map(nodeIds.map((id) => [id, [] as string[]]))
  for (const [source, target] of edgePairs) {
    if (!incoming.has(source) || !incoming.has(target)) continue
    incoming.set(target, (incoming.get(target) ?? 0) + 1)
    outgoing.get(source)?.push(target)
  }
  const queue = [...incoming.entries()].filter(([, count]) => count === 0).map(([id]) => id)
  let visited = 0
  while (queue.length > 0) {
    const id = queue.shift()
    if (!id) continue
    visited += 1
    for (const target of outgoing.get(id) ?? []) {
      const next = (incoming.get(target) ?? 0) - 1
      incoming.set(target, next)
      if (next === 0) queue.push(target)
    }
  }
  return visited !== nodeIds.length
}

function normalizeEntityType(type: string): string {
  const normalized = type.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  if (normalized === 'ipv4' || normalized === 'ip-address' || normalized === 'network') return 'ip'
  if (normalized === 'sha256' || normalized === 'sha1' || normalized === 'md5' || normalized === 'file-hash') return 'hash'
  if (normalized === 'vulnerability' || normalized === 'weakness' || normalized === 'cwe-id') return 'cwe'
  if (normalized === 'identity' || normalized === 'username' || normalized === 'account') return 'user'
  return normalized || 'entity'
}

function entityTypeFromValue(value: string): string {
  if (/^CWE-\d+$/i.test(value)) return 'cwe'
  if (/^CVE-\d{4}-\d{4,7}$/i.test(value)) return 'cve'
  if (/^(?:\d{1,3}\.){3}\d{1,3}$/.test(value)) return 'ip'
  if (/^[a-fA-F0-9]{32,64}$/.test(value)) return 'hash'
  return 'entity'
}

function qidToken(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'node'
}
