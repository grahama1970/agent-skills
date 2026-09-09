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
      y: 24 + index * 42,
    }),
  )
  const height = Math.max(
    80,
    24 + nodes.length * 42,
  )

  return (
    <section data-qid="cockpit:diagram:stage" data-revision={state.diagram.revision} className="h-[300px] rounded-lg bg-zinc-950 p-3">
      <h2 className="font-semibold">
        Diagram
      </h2>

      <svg
        viewBox={`0 0 280 ${height}`}
        role="img"
        aria-label="Current explainer diagram highlights"
        className="cockpit-diagram-preview mt-3 w-full rounded border border-zinc-800 bg-black"
      >
        {nodes.map(({ nodeId, y }) => {
          const isActive = active.has(nodeId)

          return (
            <g
              key={nodeId}
              data-node-id={nodeId}
              data-active={isActive ? 'true' : 'false'}
            >
              <title>{nodeId}</title>
              <circle
                cx="22"
                cy={y}
                r="10"
                className={
                  isActive
                    ? 'fill-cyan-400 stroke-cyan-100'
                    : 'fill-zinc-800 stroke-zinc-600'
                }
                strokeWidth="2"
              />
              <text
                x="44"
                y={y + 5}
                className={
                  isActive
                    ? 'fill-cyan-100 text-[14px]'
                    : 'fill-zinc-400 text-[14px]'
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
