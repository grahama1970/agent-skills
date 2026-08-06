import dagre from 'dagre'
import type React from 'react'
import { motion } from 'framer-motion'
import {
  BaseEdge,
  EdgeLabelRenderer,
  Handle,
  Position,
  getSmoothStepPath,
  type Edge,
  type EdgeProps,
  type Node,
} from '@xyflow/react'
import { Crosshair, Link2, ShieldAlert, type LucideIcon } from 'lucide-react'

export const SPARTA_FLOW_NODE_WIDTH = 230
export const SPARTA_FLOW_NODE_HEIGHT = 132

export type SpartaFlowDirection = 'LR' | 'TB'
export type SpartaFlowRelationType = 'supplier' | 'provider' | 'mission' | 'traversal'

export type SpartaFlowNodeCardProps = {
  className?: string
  qid: string
  Icon: LucideIcon
  eyebrow: string
  status?: React.ReactNode
  statusText?: string
  statusClass?: string
  label: string
  detail: string
  targetHandleId?: string
  sourceHandleId?: string
  targetPosition?: Position
  sourcePosition?: Position
  handleClassName?: string
  onFocus?: () => void
  onBlur?: () => void
  onMouseEnter?: () => void
  onMouseLeave?: () => void
  children?: React.ReactNode
}

export type DagreLayoutOptions = {
  direction?: SpartaFlowDirection
  nodeWidth?: number
  nodeHeight?: number
  nodesep?: number
  ranksep?: number
  marginx?: number
  marginy?: number
}

type SpartaFlowEdgeData = {
  relationType?: SpartaFlowRelationType
  label?: string
}

export function SpartaFlowStatusBadge({
  text,
  className,
}: {
  text: string
  className?: string
}) {
  return <span className={`supply-flow-status ${className ?? ''}`}>{text}</span>
}

export function SpartaFlowNodeCard({
  className,
  qid,
  Icon,
  eyebrow,
  status,
  statusText,
  statusClass,
  label,
  detail,
  targetHandleId,
  sourceHandleId,
  targetPosition = Position.Left,
  sourcePosition = Position.Right,
  handleClassName = '',
  onFocus,
  onBlur,
  onMouseEnter,
  onMouseLeave,
  children,
}: SpartaFlowNodeCardProps) {
  return (
    <motion.button
      type="button"
      className={`supply-flow-node ${className ?? ''}`}
      data-qid={qid}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, ease: [0.19, 1, 0.22, 1] }}
      onFocus={onFocus}
      onBlur={onBlur}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {targetHandleId ? (
        <Handle id={targetHandleId} type="target" position={targetPosition} className={`supply-flow-handle ${handleClassName}`} />
      ) : null}
      <div className="supply-flow-node__header">
        <Icon size={15} className="supply-flow-node__icon" aria-hidden="true" />
        <span className="supply-flow-node__eyebrow">{eyebrow}</span>
        {status ?? (statusText ? <SpartaFlowStatusBadge text={statusText} className={statusClass} /> : null)}
      </div>
      <div className="supply-flow-node__label">{label}</div>
      <div className="supply-flow-node__detail">{detail}</div>
      {children}
      {sourceHandleId ? (
        <Handle id={sourceHandleId} type="source" position={sourcePosition} className={`supply-flow-handle ${handleClassName}`} />
      ) : null}
    </motion.button>
  )
}

export function SpartaIconEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })
  const edgeData = (data ?? {}) as SpartaFlowEdgeData
  const relationType = edgeData.relationType ?? 'supplier'
  const EdgeIcon = relationType === 'mission'
    ? Crosshair
    : relationType === 'provider'
      ? ShieldAlert
      : Link2
  const title = edgeData.label ?? (
    relationType === 'mission'
      ? 'Mission dependency'
      : relationType === 'provider'
        ? 'Common-service provider'
        : relationType === 'traversal'
          ? 'Memory traversal'
          : 'Supplier dependency'
  )

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      <EdgeLabelRenderer>
        <div
          className={`supply-chain-edge-badge supply-chain-edge-badge--${relationType} nodrag nopan`}
          title={title}
          aria-label={title}
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          }}
        >
          <EdgeIcon size={12} strokeWidth={2.4} aria-hidden="true" />
          {edgeData.label ? <span className="supply-chain-edge-badge__label">{edgeData.label}</span> : null}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

export function layoutDagreFlowElements<TNode extends Node, TEdge extends Edge>(
  flowNodes: TNode[],
  flowEdges: TEdge[],
  options: DagreLayoutOptions = {},
): { nodes: TNode[]; edges: TEdge[] } {
  const {
    direction = 'LR',
    nodeWidth = SPARTA_FLOW_NODE_WIDTH,
    nodeHeight = SPARTA_FLOW_NODE_HEIGHT,
    nodesep = 42,
    ranksep = 118,
    marginx = 40,
    marginy = 40,
  } = options
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))
  dagreGraph.setGraph({ rankdir: direction, nodesep, ranksep, marginx, marginy })
  for (const node of flowNodes) {
    dagreGraph.setNode(node.id, { width: node.width ?? nodeWidth, height: node.height ?? nodeHeight })
  }
  for (const edge of flowEdges) {
    dagreGraph.setEdge(edge.source, edge.target)
  }
  dagre.layout(dagreGraph)
  const isHorizontal = direction === 'LR'
  return {
    nodes: flowNodes.map((node) => {
      const layoutNode = dagreGraph.node(node.id)
      const width = node.width ?? nodeWidth
      const height = node.height ?? nodeHeight
      return {
        ...node,
        targetPosition: isHorizontal ? Position.Left : Position.Top,
        sourcePosition: isHorizontal ? Position.Right : Position.Bottom,
        position: {
          x: layoutNode.x - width / 2,
          y: layoutNode.y - height / 2,
        },
      }
    }),
    edges: flowEdges,
  }
}
