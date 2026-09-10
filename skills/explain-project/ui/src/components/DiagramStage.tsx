import { useEffect, useState } from 'react'

import type {
  CockpitState,
} from '../types'

export function DiagramStage({
  state,
}: {
  state: CockpitState
}) {
  const [artifact, setArtifact] = useState<
    'loading' | 'shown' | 'missing'
  >('loading')
  const rendered = state.diagram.rendered_svg_path

  useEffect(() => {
    setArtifact(rendered ? 'loading' : 'missing')
  }, [rendered, state.diagram.revision])

  const active = new Set(
    state.diagram.active_node_ids,
  )
  const missing = state.diagram.active_node_ids.filter(
    (nodeId) => !state.diagram.node_ids.includes(nodeId),
  )

  const nodes = state.diagram.node_ids.map(
    (nodeId, index) => ({
      nodeId,
      y: 16 + index * 26,
    }),
  )
  const height = Math.max(
    60,
    20 + nodes.length * 26,
  )

  return (
    <section
      data-qid="cockpit:diagram:stage"
      data-revision={state.diagram.revision}
      className="min-h-0 flex-1 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 p-2.5"
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
        Architecture map
      </h2>

      {rendered && artifact !== 'missing' ? (
        <div className="mt-2 overflow-hidden rounded-md border border-zinc-800 bg-zinc-900/90 p-1.5 flex justify-center">
          <img
            data-qid="cockpit:diagram:artifact"
            src={`/api/cockpit/diagram?rev=${state.diagram.revision}`}
            alt={`Rendered diagram ${rendered}`}
            className="max-h-24 w-auto object-contain rounded bg-white/95 p-1"
            onLoad={() => setArtifact('shown')}
            onError={() => setArtifact('missing')}
          />
        </div>
      ) : null}

      {rendered && artifact === 'missing' ? (
        <p
          className="mt-2 text-xs font-mono text-red-400"
          data-diagram-diagnostic="missing-artifact"
        >
          Rendered artifact unavailable: {rendered}
        </p>
      ) : null}

      <div className="relative mt-2 overflow-hidden rounded border border-zinc-800 bg-zinc-900/90 p-2">
        <svg
          viewBox={`0 0 280 ${height}`}
          role="img"
          aria-label="Current explainer diagram highlights"
          className="cockpit-diagram-preview block w-full max-h-28"
        >
          {nodes.length > 1 ? (
            <line
              x1="22"
              y1={nodes[0].y}
              x2="22"
              y2={nodes[nodes.length - 1].y}
              stroke="#3f3f46"
              strokeWidth="2"
              strokeDasharray="4 2"
            />
          ) : null}

          {nodes.map(({ nodeId, y }) => {
            const isActive = active.has(nodeId)

            return (
              <g
                key={nodeId}
                data-node-id={nodeId}
                data-active={isActive ? 'true' : 'false'}
              >
                <title>{nodeId}</title>
                {isActive ? (
                  <circle
                    cx="22"
                    cy={y}
                    r="9"
                    fill="none"
                    stroke="#22d3ee"
                    strokeWidth="1.5"
                    opacity="0.6"
                  />
                ) : null}
                <circle
                  cx="22"
                  cy={y}
                  r="5"
                  fill={isActive ? '#06b6d4' : '#27272a'}
                  stroke={isActive ? '#a5f3fc' : '#52525b'}
                  strokeWidth="2"
                />
                <text
                  x="38"
                  y={y + 4}
                  fill={isActive ? '#cffafe' : '#a1a1aa'}
                  fontSize="13"
                  fontFamily="monospace"
                  fontWeight={isActive ? 'bold' : 'normal'}
                >
                  {nodeId}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      <div
        data-qid="cockpit:diagram:node-list"
        className="mt-2 max-h-40 space-y-1.5 overflow-y-auto"
      >
        {nodes.length ? nodes.map(({ nodeId }, index) => {
          const isActive = active.has(nodeId)

          return (
            <div
              key={nodeId}
              data-node-id={nodeId}
              data-active={isActive ? 'true' : 'false'}
              className={[
                'min-h-[44px] rounded-lg border px-2.5 py-2 font-mono text-sm',
                'flex items-center justify-between gap-2',
                isActive
                  ? 'border-cyan-500 bg-cyan-950/40 text-cyan-100'
                  : 'border-zinc-800 bg-zinc-950/80 text-zinc-400',
              ].join(' ')}
            >
              <span className="truncate">{nodeId}</span>
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                n{index + 1}
              </span>
            </div>
          )
        }) : (
          <p className="rounded-lg border border-zinc-800 bg-zinc-950/80 p-2.5 font-mono text-sm text-zinc-500">
            No diagram nodes.
          </p>
        )}
      </div>

      <p className="mt-1.5 text-xs font-mono text-cyan-300">
        {state.diagram.active_node_ids.join(' · ')
          || 'No active node'}
      </p>

      {missing.length ? (
        <p
          className="mt-1.5 text-xs font-mono text-red-400"
          data-diagram-diagnostic="missing-node"
        >
          Missing diagram node: {missing.join(', ')}
        </p>
      ) : null}

      <p className="mt-1 truncate font-mono text-[11px] text-zinc-400" title={state.diagram.rendered_svg_path ?? state.diagram.source_path ?? ''}>
        {state.diagram.rendered_svg_path
          ?? state.diagram.source_path
          ?? 'No diagram'}
      </p>

      <p className="mt-1 text-[11px] font-mono text-zinc-400">
        {state.diagram.highlight_intent
          ? 'Display highlight only; mutation_allowed=false.'
          : 'No highlight intent.'}
      </p>
    </section>
  )
}
