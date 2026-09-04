import type { UiDiagram } from '../types'

/** The graph's explicit edges, not node order, define its meaning. Narrow
 * reading uses labeled relationships rather than silently linearizing a DAG. */
export function CanonicalDiagram({ diagram, responsive }: { diagram: UiDiagram; responsive: boolean }) {
  const nodes = new Map(diagram.nodes.map((node) => [node.id, node]))
  if (responsive) {
    return (
      <figure className="canonical-diagram m-0">
        <ul className="m-0 grid list-none gap-3 p-0">
          {diagram.nodes.map((node) => (
            <li key={node.id} className="rounded border border-slate-300 p-4">
              <strong>{node.label}</strong>{node.sublabel ? <p className="m-0 mt-2">{node.sublabel}</p> : null}
            </li>
          ))}
        </ul>
        <ul aria-label="Diagram relationships" className="mt-4 space-y-3 pl-5">
          {diagram.edges.map((edge) => (
            <li key={edge.id}>
              {nodes.get(edge.source)?.label ?? edge.source} {edge.arrowhead === false ? '—' : '→'} {nodes.get(edge.target)?.label ?? edge.target}
              {edge.label ? <>: {edge.label}</> : null}
            </li>
          ))}
        </ul>
      </figure>
    )
  }
  return (
    <div className="flex h-full w-full flex-col" role="group" aria-label="Diagram">
      <div className="relative min-h-0 flex-1">
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1000 600" preserveAspectRatio="none" aria-hidden>
        {diagram.edges.map((edge) => {
          const a = nodes.get(edge.source)?.bbox
          const b = nodes.get(edge.target)?.bbox
          if (!a || !b) return null
          const x1 = (a.x + a.w / 2) * 1000, y1 = (a.y + a.h / 2) * 600
          const x2 = (b.x + b.w / 2) * 1000, y2 = (b.y + b.h / 2) * 600
          return <line key={edge.id} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#076889" strokeWidth="3" strokeDasharray={edge.line_style === 'dashed' ? '8 6' : undefined} />
        })}
      </svg>
      {diagram.nodes.map((node) => (
        <div key={node.id} className="absolute flex flex-col justify-center rounded border-2 border-cyan-800 bg-white p-3 text-center text-2xl"
          style={{ left: `${node.bbox.x * 100}%`, top: `${node.bbox.y * 100}%`, width: `${node.bbox.w * 100}%`, height: `${node.bbox.h * 100}%` }}>
          <strong>{node.label}</strong>{node.sublabel ? <span>{node.sublabel}</span> : null}
        </div>
      ))}
      </div>
      <ul className="m-0 w-full list-none bg-white/95 p-1 text-xl" aria-label="Diagram relationships">
        {diagram.edges.map((edge) => <li key={edge.id}>{nodes.get(edge.source)?.label ?? edge.source} {edge.arrowhead === false ? '—' : '→'} {nodes.get(edge.target)?.label ?? edge.target}{edge.label ? `: ${edge.label}` : ''}</li>)}
      </ul>
    </div>
  )
}
