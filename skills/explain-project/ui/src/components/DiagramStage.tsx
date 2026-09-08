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

  return (
    <section className="h-[300px] rounded-lg bg-zinc-950 p-3">
      <h2 className="font-semibold">
        Diagram
      </h2>

      <svg
        viewBox="0 0 360 150"
        role="img"
        aria-label="Current explainer diagram highlights"
        className="mt-3 h-32 w-full rounded border border-zinc-800 bg-black"
      >
        {state.diagram.node_ids.map((nodeId, index) => {
          const x = 44 + index * 96
          const isActive = active.has(nodeId)

          return (
            <g
              key={nodeId}
              data-node-id={nodeId}
              data-active={isActive ? 'true' : 'false'}
            >
              <circle
                cx={x}
                cy="58"
                r="25"
                className={
                  isActive
                    ? 'fill-cyan-400 stroke-cyan-100'
                    : 'fill-zinc-800 stroke-zinc-600'
                }
                strokeWidth="3"
              />
              <text
                x={x}
                y="105"
                textAnchor="middle"
                className={
                  isActive
                    ? 'fill-cyan-200 text-[13px]'
                    : 'fill-zinc-500 text-[13px]'
                }
              >
                {nodeId}
              </text>
            </g>
          )
        })}
      </svg>

      <p className="mt-2 text-cyan-300">
        {state.diagram.active_node_ids.join(' · ')
          || 'No active node'}
      </p>

      {missing.length ? (
        <p
          className="mt-2 text-red-300"
          data-diagram-diagnostic="missing-node"
        >
          Missing diagram node: {missing.join(', ')}
        </p>
      ) : null}

      <p className="mt-2 text-zinc-500">
        {state.diagram.rendered_svg_path
          ?? state.diagram.source_path
          ?? 'No diagram'}
      </p>

      <p className="mt-3 text-xs text-zinc-500">
        {state.diagram.highlight_intent
          ? 'Display highlight only; mutation_allowed=false.'
          : 'No highlight intent.'}
      </p>
    </section>
  )
}
