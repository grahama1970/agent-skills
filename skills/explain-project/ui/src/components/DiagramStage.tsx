import type {
  CockpitState,
} from '../types'

export function DiagramStage({
  state,
}: {
  state: CockpitState
}) {
  const active = new Set(
    state.diagram.active_node_ids,
  )
  const missing = state.diagram.active_node_ids.filter(
    (nodeId) => !state.diagram.node_ids.includes(nodeId),
  )

  const nodes = state.diagram.node_ids.map(
    (nodeId, index) => ({
      nodeId,
      y: 22 + index * 36,
    }),
  )
  const height = Math.max(
    90,
    28 + nodes.length * 36,
  )

  return (
    <section
      data-qid="cockpit:diagram:stage"
      data-revision={state.diagram.revision}
      className="rounded-lg border border-zinc-800 bg-zinc-950 p-3"
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
        Diagram
      </h2>

      <div className="relative mt-2 overflow-hidden rounded border border-zinc-800 bg-zinc-900/90 p-2">
        <svg
          viewBox={`0 0 280 ${height}`}
          role="img"
          aria-label="Current explainer diagram highlights"
          className="cockpit-diagram-preview block w-full"
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
                    r="11"
                    fill="none"
                    stroke="#22d3ee"
                    strokeWidth="1.5"
                    opacity="0.6"
                  />
                ) : null}
                <circle
                  cx="22"
                  cy={y}
                  r="6"
                  fill={isActive ? '#06b6d4' : '#27272a'}
                  stroke={isActive ? '#a5f3fc' : '#52525b'}
                  strokeWidth="2"
                />
                <text
                  x="42"
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

      <p className="mt-2 text-xs font-mono text-cyan-300">
        {state.diagram.active_node_ids.join(' · ')
          || 'No active node'}
      </p>

      {missing.length ? (
        <p
          className="mt-2 text-xs font-mono text-red-400"
          data-diagram-diagnostic="missing-node"
        >
          Missing diagram node: {missing.join(', ')}
        </p>
      ) : null}

      <p className="mt-2 truncate font-mono text-[10px] text-zinc-500" title={state.diagram.rendered_svg_path ?? state.diagram.source_path ?? ''}>
        {state.diagram.rendered_svg_path
          ?? state.diagram.source_path
          ?? 'No diagram'}
      </p>

      <p className="mt-2 text-[11px] font-mono text-zinc-500">
        {state.diagram.highlight_intent
          ? 'Display highlight only; mutation_allowed=false.'
          : 'No highlight intent.'}
      </p>
    </section>
  )
}
