import { useMemo, useState } from 'react'
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
import {
  CheckCircle2,
  Circle,
  Database,
  FileJson2,
  GitBranch,
  HelpCircle,
  MessageSquare,
  Search,
  Shield,
  XCircle,
  type LucideIcon,
} from 'lucide-react'
import { useRegisterAction } from './_support/useRegisterAction'
import {
  SPARTA_FLOW_NODE_HEIGHT,
  SPARTA_FLOW_NODE_WIDTH,
  SpartaFlowNodeCard,
  SpartaIconEdge,
  layoutDagreFlowElements,
  type SpartaFlowRelationType,
} from './_support/SpartaFlowPrimitives'
import CodeBlockWithCopy from './CodeBlockWithCopy'
import '@xyflow/react/dist/style.css'
import './_support/SupplyChainFlow.css'

export type MemoryPipelineTraceStep = {
  id?: string
  label?: string
  status?: string
  detail?: string
  icon?: string
  data?: unknown
}

export type MemoryPipelineStageKind =
  | 'extract_entities'
  | 'memory_intent'
  | 'memory_recall'
  | 'create_evidence_case'
  | 'memory_answer'
  | 'memory_clarify'
  | 'memory_deflect'
  | 'response'
  | 'unknown'

export type MemoryPipelineNodeData = Record<string, unknown> & {
  label: string
  detail: string
  status: 'passed' | 'running' | 'failed' | 'skipped' | 'pending'
  stageKind: MemoryPipelineStageKind
  flowDirection: 'LR' | 'TB'
  payload: Record<string, unknown>
}

export type MemoryPipelineFlowNode = Node<MemoryPipelineNodeData, 'memoryPipelineNode'>
export type MemoryPipelineFlowEdge = Edge<Record<string, unknown> & {
  label: string
  relationType: SpartaFlowRelationType
}>

export type MemoryPipelineDagModel = {
  nodes: MemoryPipelineFlowNode[]
  edges: MemoryPipelineFlowEdge[]
  contract: {
    renderer: '@xyflow/react'
    layout: 'dagre-lr' | 'dagre-tb'
    source: 'thinkingTrace'
    node_count: number
    edge_count: number
    bounded_node_limit: number
  }
  validation: {
    ok: boolean
    errors: string[]
  }
}

const BOUNDED_NODE_LIMIT = 12
const nodeTypes = { memoryPipelineNode: MemoryPipelineNodeCard }
const edgeTypes = { iconEdge: SpartaIconEdge }
const defaultEdgeOptions = {
  markerEnd: {
    type: MarkerType.ArrowClosed,
    width: 14,
    height: 14,
    color: '#94a3b8',
  },
}

export function MemoryPipelineDag({
  steps,
  receiptId,
  direction = 'LR',
  showInspector = true,
}: {
  steps: MemoryPipelineTraceStep[]
  receiptId?: string
  direction?: 'LR' | 'TB'
  showInspector?: boolean
}): JSX.Element | null {
  const model = useMemo(() => buildMemoryPipelineDagModel(steps, direction), [direction, steps])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const selectedNode = model.nodes.find((node) => node.id === selectedNodeId) ?? model.nodes[0] ?? null
  const isVertical = direction === 'TB'

  useRegisterAction('shared-chat:memory-pipeline-dag:inspect-stage', {
    app: 'shared-chat',
    action: 'SHARED_CHAT_MEMORY_PIPELINE_INSPECT_STAGE',
    label: 'Inspect Memory pipeline stage',
    description: 'Inspect the JSON receipt payload for one Memory pipeline stage',
  })

  if (model.nodes.length === 0) return null

  return (
    <section
      data-qid="shared-chat:memory-pipeline-dag"
      aria-label="Memory pipeline DAG"
      style={{
        display: 'grid',
        gridTemplateColumns: showInspector ? 'minmax(0, 1.05fr) minmax(240px, 0.95fr)' : 'minmax(0, 1fr)',
        gap: 12,
        minWidth: 0,
        height: isVertical ? 560 : 430,
        maxHeight: isVertical ? 560 : 430,
        margin: '0 0 16px',
        border: '1px solid rgba(148, 163, 184, 0.18)',
        borderRadius: 8,
        background: 'rgba(15, 23, 42, 0.22)',
        overflow: 'hidden',
      }}
    >
      <div
        className="supply-chain-flow-canvas"
        data-qid="shared-chat:memory-pipeline-dag:flow"
        data-state={model.validation.ok ? 'ready' : 'invalid'}
        style={{ minHeight: 0, height: '100%', background: '#05070b' }}
      >
        <ReactFlowProvider>
          <ReactFlow<MemoryPipelineFlowNode, MemoryPipelineFlowEdge>
            nodes={model.nodes}
            edges={model.edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            panOnDrag={false}
            zoomOnScroll={false}
            zoomOnPinch
            zoomOnDoubleClick={false}
            fitView
            fitViewOptions={{ padding: 0.08 }}
            minZoom={0.2}
            maxZoom={1.4}
            proOptions={{ hideAttribution: true }}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            aria-label="Read-only Memory pipeline execution DAG"
          >
            <Controls style={{ background: '#111827', border: '1px solid rgba(148,163,184,0.28)' }} />
            <Background color="rgba(148,163,184,0.18)" gap={18} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>

      {showInspector ? (
        <aside
          data-qid="shared-chat:memory-pipeline-dag:inspector"
          style={{
            minWidth: 0,
            minHeight: 0,
            maxHeight: '100%',
            display: 'grid',
            gridTemplateRows: 'auto minmax(0, 1fr)',
            gap: 10,
            padding: 12,
            borderLeft: '1px solid rgba(148, 163, 184, 0.14)',
            background: 'rgba(2, 6, 23, 0.66)',
          }}
        >
          <div style={{ display: 'grid', gap: 5, minWidth: 0 }}>
            <div style={{ color: '#94a3b8', fontSize: 10, fontWeight: 800, letterSpacing: 0, textTransform: 'uppercase' }}>
              Memory pipeline receipt
            </div>
            <div
              data-qid="shared-chat:memory-pipeline-dag:selected-stage"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                minWidth: 0,
              }}
            >
              <strong style={{ color: '#f8fafc', fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {selectedNode?.data.label ?? 'No stage selected'}
              </strong>
              <span style={{ color: statusColor(selectedNode?.data.status ?? 'pending'), fontSize: 10, fontWeight: 900, textTransform: 'uppercase' }}>
                {selectedNode?.data.status ?? 'pending'}
              </span>
            </div>
            {receiptId ? (
              <span
                data-qid="shared-chat:memory-pipeline-dag:receipt-id"
                style={{ color: '#64748b', fontSize: 10, fontFamily: 'var(--font-mono, monospace)' }}
              >
                {receiptId}
              </span>
            ) : null}
          </div>

          {selectedNode ? (
            <div data-qid="shared-chat:memory-pipeline-dag:payload" style={{ minWidth: 0, minHeight: 0, overflow: 'auto' }}>
              <CodeBlockWithCopy language="json">
                {stableJson(selectedNode.data.payload)}
              </CodeBlockWithCopy>
            </div>
          ) : null}
        </aside>
      ) : null}
    </section>
  )
}

export function buildMemoryPipelineDagModel(steps: MemoryPipelineTraceStep[], direction: 'LR' | 'TB' = 'LR'): MemoryPipelineDagModel {
  const visibleSteps = dedupePipelineSteps(steps).slice(0, BOUNDED_NODE_LIMIT)
  const flowNodes: MemoryPipelineFlowNode[] = visibleSteps.map((step, index) => {
    const stageKind = memoryPipelineStageKind(step)
    const status = normalizeStatus(step.status)
    const isVertical = direction === 'TB'
    return {
      id: `memory-pipeline:${index}:${qidToken(step.id ?? step.label ?? `stage-${index + 1}`)}`,
      type: 'memoryPipelineNode',
      position: { x: 0, y: 0 },
      sourcePosition: isVertical ? Position.Bottom : Position.Right,
      targetPosition: isVertical ? Position.Top : Position.Left,
      width: SPARTA_FLOW_NODE_WIDTH,
      height: SPARTA_FLOW_NODE_HEIGHT,
      data: {
        label: stageLabel(stageKind, step),
        detail: step.detail ?? stageDetail(stageKind),
        status,
        stageKind,
        flowDirection: direction,
        payload: {
          schema: 'sparta.memory_pipeline_stage_receipt.v1',
          stage_index: index,
          stage_kind: stageKind,
          source: 'thinkingTrace',
          id: step.id ?? null,
          label: step.label ?? null,
          status: step.status ?? null,
          detail: step.detail ?? null,
          data: step.data ?? null,
        },
      },
    }
  })

  const flowEdges: MemoryPipelineFlowEdge[] = flowNodes.slice(0, -1).map((node, index) => ({
    id: `memory-pipeline-edge:${index}`,
    source: node.id,
    target: flowNodes[index + 1].id,
    sourceHandle: 'out',
    targetHandle: 'in',
    type: 'iconEdge',
    data: { relationType: 'traversal', label: 'then' },
    markerEnd: defaultEdgeOptions.markerEnd,
    style: { stroke: '#94a3b8', strokeWidth: 1.8 },
    labelStyle: { fill: '#cbd5e1', fontSize: 10, fontWeight: 800, letterSpacing: 0, textTransform: 'uppercase' },
    labelBgStyle: { fill: '#0f172a', fillOpacity: 0.94 },
    labelBgPadding: [7, 4],
    labelBgBorderRadius: 4,
  }))

  const layouted = layoutDagreFlowElements(flowNodes, flowEdges, {
    direction,
    nodeWidth: SPARTA_FLOW_NODE_WIDTH,
    nodeHeight: SPARTA_FLOW_NODE_HEIGHT,
    nodesep: direction === 'TB' ? 36 : 48,
    ranksep: direction === 'TB' ? 70 : 126,
    marginx: 44,
    marginy: 44,
  })
  const validation = validateMemoryPipelineDagModel(layouted.nodes, layouted.edges)

  return {
    nodes: layouted.nodes,
    edges: layouted.edges,
    contract: {
      renderer: '@xyflow/react',
      layout: direction === 'TB' ? 'dagre-tb' : 'dagre-lr',
      source: 'thinkingTrace',
      node_count: layouted.nodes.length,
      edge_count: layouted.edges.length,
      bounded_node_limit: BOUNDED_NODE_LIMIT,
    },
    validation,
  }
}

export function validateMemoryPipelineDagModel(
  nodes: MemoryPipelineFlowNode[],
  edges: MemoryPipelineFlowEdge[],
): { ok: boolean; errors: string[] } {
  const errors: string[] = []
  const nodeIds = new Set(nodes.map((node) => node.id))
  if (nodeIds.size !== nodes.length) errors.push('duplicate_node_id')
  for (const edge of edges) {
    if (!nodeIds.has(edge.source)) errors.push(`missing_source:${edge.id}`)
    if (!nodeIds.has(edge.target)) errors.push(`missing_target:${edge.id}`)
    if (edge.sourceHandle !== 'out') errors.push(`missing_source_handle:${edge.id}`)
    if (edge.targetHandle !== 'in') errors.push(`missing_target_handle:${edge.id}`)
  }
  return { ok: errors.length === 0, errors }
}

export function memoryPipelineStageKind(step: MemoryPipelineTraceStep): MemoryPipelineStageKind {
  const key = `${step.id ?? ''} ${step.label ?? ''} ${step.icon ?? ''}`.toLowerCase()
  if (key.includes('extract') || key.includes('entity')) return 'extract_entities'
  if (key.includes('intent') || key.includes('classif')) return 'memory_intent'
  if (key.includes('evidence') || key.includes('answerability') || key.includes('gate')) return 'create_evidence_case'
  if (key.includes('recall') || key.includes('result')) return 'memory_recall'
  if (key.includes('clarif')) return 'memory_clarify'
  if (key.includes('deflect') || key.includes('unsupported')) return 'memory_deflect'
  if (key.includes('answer')) return 'memory_answer'
  if (key.includes('response')) return 'response'
  return 'unknown'
}

function MemoryPipelineNodeCard({ data }: NodeProps<MemoryPipelineFlowNode>): JSX.Element {
  const Icon = iconForStage(data.stageKind)
  const isVertical = data.flowDirection === 'TB'
  return (
    <SpartaFlowNodeCard
      className={`supply-flow-node--service chat-graph-flow-node memory-pipeline-node memory-pipeline-node--${data.status}`}
      qid={`shared-chat:memory-pipeline-dag:node:${qidToken(data.label)}`}
      Icon={Icon}
      eyebrow={eyebrowForStage(data.stageKind)}
      status={<StatusBadge status={data.status} />}
      label={data.label}
      detail={data.detail}
      targetHandleId="in"
      sourceHandleId="out"
      targetPosition={isVertical ? Position.Top : Position.Left}
      sourcePosition={isVertical ? Position.Bottom : Position.Right}
      handleClassName="chat-graph-flow-node__handle"
    />
  )
}

function StatusBadge({ status }: { status: MemoryPipelineNodeData['status'] }): JSX.Element {
  const Icon = status === 'passed' ? CheckCircle2 : status === 'failed' ? XCircle : status === 'running' ? GitBranch : Circle
  return (
    <span
      className="supply-flow-status supply-flow-status--neutral"
      style={{
        color: statusColor(status),
        borderColor: `${statusColor(status)}66`,
        background: `${statusColor(status)}14`,
      }}
    >
      <Icon size={11} strokeWidth={2.2} aria-hidden="true" />
      {status}
    </span>
  )
}

function dedupePipelineSteps(steps: MemoryPipelineTraceStep[]): MemoryPipelineTraceStep[] {
  const latestByKey = new Map<string, MemoryPipelineTraceStep>()
  const anonymous: MemoryPipelineTraceStep[] = []
  for (const step of steps) {
    const key = qidToken(step.id ?? step.label ?? '')
    if (!key || key === 'item') {
      anonymous.push(step)
      continue
    }
    latestByKey.set(key, step)
  }
  return [...latestByKey.values(), ...anonymous]
}

function normalizeStatus(status?: string): MemoryPipelineNodeData['status'] {
  const value = String(status ?? '').toLowerCase()
  if (value === 'completed' || value === 'done' || value === 'passed') return 'passed'
  if (value === 'failed' || value === 'blocked' || value === 'error') return 'failed'
  if (value === 'running') return 'running'
  if (value === 'skipped') return 'skipped'
  return 'pending'
}

function stageLabel(kind: MemoryPipelineStageKind, step: MemoryPipelineTraceStep): string {
  if (kind === 'extract_entities') return '$extract-entities'
  if (kind === 'memory_intent') return '$memory intent'
  if (kind === 'memory_recall') return '$memory recall'
  if (kind === 'create_evidence_case') return '$create-evidence-case'
  if (kind === 'memory_answer') return '$memory answer'
  if (kind === 'memory_clarify') return '$memory clarify'
  if (kind === 'memory_deflect') return '$memory deflect'
  if (kind === 'response') return '$response'
  return step.label ?? step.id ?? '$memory stage'
}

function stageDetail(kind: MemoryPipelineStageKind): string {
  if (kind === 'extract_entities') return 'Grounded entity extraction and unresolved term checks.'
  if (kind === 'memory_intent') return 'Route, recall profile, delivery context, and required artifacts.'
  if (kind === 'memory_recall') return 'Bounded lexical, dense, and graph candidate retrieval.'
  if (kind === 'create_evidence_case') return 'QRA reuse, current-turn answerability, and crosswalk authority.'
  if (kind === 'memory_answer') return 'Clean final answer assembled from admitted evidence.'
  if (kind === 'memory_clarify') return 'Clean clarification when scope or evidence is underspecified.'
  if (kind === 'memory_deflect') return 'Clean fail-closed deflection for unsupported or unsafe turns.'
  return 'Memory pipeline stage receipt.'
}

function eyebrowForStage(kind: MemoryPipelineStageKind): string {
  if (kind === 'extract_entities') return 'ENTITY'
  if (kind === 'memory_intent') return 'ROUTE'
  if (kind === 'memory_recall') return 'RECALL'
  if (kind === 'create_evidence_case') return 'AUTHORITY'
  if (kind === 'memory_answer') return 'ANSWER'
  if (kind === 'memory_clarify') return 'CLARIFY'
  if (kind === 'memory_deflect') return 'DEFLECT'
  return 'STAGE'
}

function iconForStage(kind: MemoryPipelineStageKind): LucideIcon {
  if (kind === 'extract_entities') return Search
  if (kind === 'memory_intent') return GitBranch
  if (kind === 'memory_recall') return Database
  if (kind === 'create_evidence_case') return Shield
  if (kind === 'memory_answer') return MessageSquare
  if (kind === 'memory_clarify') return HelpCircle
  if (kind === 'memory_deflect') return XCircle
  if (kind === 'response') return FileJson2
  return FileJson2
}

function statusColor(status: MemoryPipelineNodeData['status']): string {
  if (status === 'passed') return '#3fb950'
  if (status === 'failed') return '#ff7b72'
  if (status === 'running') return '#58a6ff'
  if (status === 'skipped') return '#94a3b8'
  return '#d29922'
}

function stableJson(value: unknown): string {
  return JSON.stringify(value, (_key, nested) => {
    if (!nested || typeof nested !== 'object' || Array.isArray(nested)) return nested
    return Object.keys(nested as Record<string, unknown>).sort().reduce<Record<string, unknown>>((acc, key) => {
      acc[key] = (nested as Record<string, unknown>)[key]
      return acc
    }, {})
  }, 2)
}

function qidToken(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80) || 'item'
}
