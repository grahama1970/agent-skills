'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceRadial,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
} from 'd3-force';
import graph from '@/graph.json';

interface GNode {
  id: string;
  type: 'practice' | 'area' | 'project';
  label: string;
  title?: string;
  lens?: 'technical' | 'creative' | 'hybrid';
  slug?: string;
  href?: string | null;
  question?: string;
  visibility?: string;
  evidenceAccess?: string;
  skillCount?: number;
  taxonomy?: string;
  abstract?: string;
  hasSanityCheck?: boolean;
  img?: string;
}
interface GEdge {
  source: string;
  target: string;
  rel: string;
}
// Mutable simulation node: d3-force writes x/y/vx/vy/fx/fy onto it in place.
type SimNode = GNode & {
  x: number;
  y: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
};
type SimEdge = { source: SimNode; target: SimNode; rel: string };
type InspectorData = {
  title: string;
  lens: string;
  taxonomy: string;
  abstract: string;
  status?: string;
};
type InspectorState = {
  data: InspectorData;
  left: number;
  top: number;
};

const NODES = graph.nodes as GNode[];
const EDGES = graph.edges as GEdge[];

const W = 1120;
const H = 940;
const CX = W / 2;
const CY = H / 2;

// Concrete colours (drop-shadow glow needs a real colour, not a CSS var).
const GLOW: Record<string, string> = {
  technical: '#e2ac62',
  creative: '#d1703c',
  hybrid: '#93a289',
};
const LENS_LABEL: Record<string, string> = {
  technical: '▲ technical',
  creative: '● creative',
  hybrid: '◆ hybrid',
};

function getInspectorData(node: GNode): InspectorData {
  if (node.type === 'practice') {
    return {
      title: node.label,
      lens: LENS_LABEL[node.lens ?? 'hybrid'] ?? '◆ hybrid',
      taxonomy: 'practice hub',
      abstract: 'Central practice node connecting the research areas and public project routes.',
      status: 'overview',
    };
  }
  if (node.type === 'area') {
    const skillCount = node.skillCount ?? 0;
    return {
      title: node.title || node.label,
      lens: LENS_LABEL[node.lens ?? 'technical'] ?? '▲ technical',
      taxonomy: 'research area',
      abstract: `Category group containing ${skillCount} active ${skillCount === 1 ? 'skill contract' : 'skill contracts'}.`,
      status: node.skillCount ? `${node.skillCount} ${node.skillCount === 1 ? 'skill' : 'skills'}` : 'category',
    };
  }
  return {
    title: node.label,
    lens: LENS_LABEL[node.lens ?? 'technical'] ?? '▲ technical',
    taxonomy:
      node.taxonomy ||
      (node.evidenceAccess === 'abstract' ? 'public overview' : 'skill contract'),
    abstract:
      node.abstract ||
      node.question ||
      'Executable skill contract registered in the public inventory.',
    status:
      node.hasSanityCheck === true
        ? 'sanity checked'
        : node.visibility && node.visibility !== 'public'
          ? 'public overview only'
          : 'source linked',
  };
}

// Redundant, colourblind-safe cue for lens: technical=triangle, creative=circle,
// hybrid=diamond — so the technical/creative distinction never rests on the two
// adjacent warm hues alone (best-practices-d3: don't rely on colour alone).
function LensMark({ x, y, lens, color }: { x: number; y: number; lens?: string; color: string }) {
  const s = 4;
  if (lens === 'technical')
    return <polygon points={`${x},${y - s} ${x - s},${y + s} ${x + s},${y + s}`} fill={color} className="c-lensmark" />;
  if (lens === 'hybrid')
    return <rect x={x - s + 0.8} y={y - s + 0.8} width={(s - 0.8) * 2} height={(s - 0.8) * 2} transform={`rotate(45 ${x} ${y})`} fill={color} className="c-lensmark" />;
  return <circle cx={x} cy={y} r={s - 0.6} fill={color} className="c-lensmark" />; // creative
}

const radiusOf = (t: string) => (t === 'practice' ? 46 : t === 'project' ? 30 : 26);
// The ring the node settles onto — keeps the physics legible instead of a hairball.
const orbitOf = (t: string) => (t === 'practice' ? 0 : t === 'area' ? 234 : 392);
// Node and Chromium can differ at the final decimal for trig-derived SVG values.
// Round rendered coordinates so SSR markup and hydrated client props match.
const coord = (n: number) => Number(n.toFixed(3));

// Per-character width (px) of each node's label, used to reserve enough space in
// the collision force that LABELS never overlap — not just the circles.
const charPxOf = (t: string) => (t === 'area' ? 8.4 : 6.9);

// Half-width of a node's footprint (label OR circle, whichever is wider) plus a
// gap. This is the collision radius, so the simulation spreads nodes until no
// two labels touch.
function footprintOf(n: { type: string; label: string; skillCount?: number }): number {
  const r = radiusOf(n.type);
  if (n.type === 'practice') return r + 20;
  const chars = n.label.length + (n.type === 'area' && n.skillCount ? 4 : 0);
  const halfLabel = (chars * charPxOf(n.type)) / 2;
  return Math.max(r, halfLabel) + 14;
}

/**
 * Capability constellation — a live d3-force graph in the spirit of the
 * persona-dream node graph: charge repulsion so nodes push apart, collision so
 * they never overlap, and draggable nodes that re-settle. The practice hub is
 * pinned at centre; a light radial force biases areas to an inner ring and
 * projects to an outer one so the structure stays readable. Image-filled
 * glowing ovals; private work a dashed ring. Warm brass/ember/sage palette.
 */
export function CapabilityConstellation() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [inspector, setInspector] = useState<InspectorState | null>(null);
  const [, force] = useState(0); // bump to re-render from mutated sim positions
  const drag = useRef<{ id: string } | null>(null);
  const moved = useRef(false); // distinguishes a drag from a click on project nodes

  // Stable simulation nodes/edges (built once; d3 mutates them across ticks).
  const { simNodes, simEdges, byId } = useMemo(() => {
    const nodes: SimNode[] = NODES.map((n) => {
      const orbit = orbitOf(n.type);
      // Seed on the target ring so the first frame is already close to settled.
      const a = (NODES.indexOf(n) / NODES.length) * Math.PI * 2;
      return {
        ...n,
        x: CX + orbit * Math.cos(a),
        y: CY + orbit * Math.sin(a),
        fx: n.type === 'practice' ? CX : null,
        fy: n.type === 'practice' ? CY : null,
      };
    });
    const map = new Map(nodes.map((n) => [n.id, n]));
    const edges: SimEdge[] = EDGES.map((e) => ({
      source: map.get(e.source)!,
      target: map.get(e.target)!,
      rel: e.rel,
    }));
    return { simNodes: nodes, simEdges: edges, byId: map };
  }, []);

  useEffect(() => {
    const sim: Simulation<SimNode, SimEdge> = forceSimulation(simNodes)
      .force(
        'link',
        forceLink<SimNode, SimEdge>(simEdges)
          .id((d) => d.id)
          .distance((e) => (e.rel === 'area' ? 150 : 96))
          .strength(0.5),
      )
      .force('charge', forceManyBody().strength(-620)) // repulsion (persona-dream uses -200)
      // Collide by label footprint so text never overlaps, not just the circles.
      .force('collide', forceCollide<SimNode>((d) => footprintOf(d)).strength(1).iterations(4))
      .force('radial', forceRadial<SimNode>((d) => orbitOf(d.type), CX, CY).strength(0.2))
      .force('x', forceX(CX).strength(0.02))
      .force('y', forceY(CY).strength(0.02))
      .force('center', forceCenter(CX, CY).strength(0.02));

    // Reduced motion: settle synchronously and render once — no animation,
    // honouring the site's exhibits-not-theater posture for that audience.
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      sim.stop();
      for (let i = 0; i < 320; i += 1) sim.tick();
      force((t) => t + 1);
    } else {
      sim.on('tick', () => force((t) => t + 1));
    }
    return () => {
      sim.stop();
    };
  }, [simNodes, simEdges]);

  // Convert a pointer event to viewBox coordinates for dragging.
  const toLocal = (clientX: number, clientY: number): [number, number] => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const m = svg.getScreenCTM();
    if (!m) return [CX, CY];
    const p = pt.matrixTransform(m.inverse());
    return [p.x, p.y];
  };

  useEffect(() => {
    const move = (ev: PointerEvent) => {
      const d = drag.current;
      if (!d) return;
      ev.preventDefault();
      const node = byId.get(d.id);
      if (!node) return;
      const [x, y] = toLocal(ev.clientX, ev.clientY);
      node.fx = x;
      node.fy = y;
      moved.current = true; // a real drag — suppress the click-through navigation
      force((t) => t + 1);
    };
    const up = () => {
      const d = drag.current;
      if (d) {
        const node = byId.get(d.id);
        // Release everything except the pinned hub.
        if (node && node.type !== 'practice') {
          node.fx = null;
          node.fy = null;
        }
      }
      drag.current = null;
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, [byId]);

  const startDrag = (n: SimNode) => (ev: React.PointerEvent) => {
    if (n.type === 'practice') return; // hub stays put
    ev.preventDefault();
    drag.current = { id: n.id };
    moved.current = false;
    n.fx = n.x;
    n.fy = n.y;
  };

  const connected = (id: string) =>
    hover === null ||
    hover === id ||
    EDGES.some(
      (e) =>
        (e.source === hover && e.target === id) || (e.target === hover && e.source === id),
    );

  const positionInspector = (clientX: number, clientY: number, data: InspectorData) => {
    const width = 310;
    const height = 168;
    let left = clientX + 16;
    let top = clientY + 16;
    if (typeof window !== 'undefined') {
      if (left + width > window.innerWidth) left = clientX - width - 16;
      if (top + height > window.innerHeight) top = clientY - height - 16;
    }
    setInspector({ data, left: Math.max(12, left), top: Math.max(12, top) });
  };

  const inspectAtPointer = (n: SimNode) => (ev: React.MouseEvent | React.FocusEvent) => {
    setHover(n.id);
    const data = getInspectorData(n);
    if ('clientX' in ev && ev.clientX && ev.clientY) {
      positionInspector(ev.clientX, ev.clientY, data);
      return;
    }
    const svg = svgRef.current;
    const rect = svg?.getBoundingClientRect();
    if (!rect) {
      setInspector({ data, left: 16, top: 16 });
      return;
    }
    const left = rect.left + (n.x / W) * rect.width + 16;
    const top = rect.top + (n.y / H) * rect.height + 16;
    positionInspector(left, top, data);
  };

  const moveInspector = (n: SimNode) => (ev: React.MouseEvent) => {
    if (!inspector) return;
    positionInspector(ev.clientX, ev.clientY, getInspectorData(n));
  };

  const hideInspector = () => {
    setHover(null);
    setInspector(null);
  };

  return (
    <figure className="constellation" aria-label="How the practice connects">
      <figcaption className="constellation-cap">
        Public repo map — skill contracts, project routes, and evidence access.
        <span className="constellation-hint"> Drag a node.</span>
      </figcaption>
      <div className="constellation-field">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="constellation-svg" role="img">
          <defs>
            {simNodes
              .filter((n) => n.img)
              .map((n) => (
                <clipPath id={`clip-${n.id}`} key={n.id}>
                  <circle cx={coord(n.x)} cy={coord(n.y)} r={radiusOf(n.type)} />
                </clipPath>
              ))}
          </defs>

          {simEdges.map((e) => {
            const s = e.source;
            const t = e.target;
            const mx = (s.x + t.x) / 2 + (CX - (s.x + t.x) / 2) * 0.14;
            const my = (s.y + t.y) / 2 + (CY - (s.y + t.y) / 2) * 0.14;
            const on = connected(e.source.id) && connected(e.target.id);
            return (
              <path
                key={`${e.source.id}-${e.target.id}`}
                d={`M ${coord(s.x)} ${coord(s.y)} Q ${coord(mx)} ${coord(my)} ${coord(t.x)} ${coord(t.y)}`}
                className={`c-edge${on ? ' is-on' : ''}`}
              />
            );
          })}

          {simNodes.map((n) => {
            const x = coord(n.x);
            const y = coord(n.y);
            const on = connected(n.id);
            const glow = n.lens ? GLOW[n.lens] : '#a99787';
            const r = radiusOf(n.type);

            if (n.type === 'practice') {
              return (
                <g
                  key={n.id}
                  className={`c-node${on ? '' : ' is-dim'}`}
                  data-qid={`constellation:node:${n.id}`}
                  data-qs-action="CONSTELLATION_NODE"
                  tabIndex={0}
                  onMouseEnter={inspectAtPointer(n)}
                  onMouseMove={moveInspector(n)}
                  onMouseLeave={hideInspector}
                  onFocus={inspectAtPointer(n)}
                  onBlur={hideInspector}
                  style={{ cursor: 'default' }}
                >
                  <circle cx={x} cy={y} r={r} className="c-core" />
                  <circle
                    cx={x}
                    cy={y}
                    r={r}
                    className="c-ring c-ring--core"
                    style={{ filter: `drop-shadow(0 0 10px rgba(226,172,98,.55))` }}
                  />
                  {/* G꜀ monogram — G (the visual mass) locked to the exact node
                      centre; c hangs off it as an external subscript so it never
                      pulls G off-centre. */}
                  <text x={x} y={y + 15} textAnchor="middle" className="c-mark">
                    G
                  </text>
                  <text x={x + 21} y={y + 23} textAnchor="middle" className="c-mark-sub">
                    c
                  </text>
                </g>
              );
            }

            const isProj = n.type === 'project';
            const priv = n.visibility && n.visibility !== 'public';
            const inner = (
              <g
                className={`c-node c-node--${n.type}${on ? '' : ' is-dim'}`}
                data-qid={`constellation:node:${n.id}`}
                data-qs-action="CONSTELLATION_NODE"
                tabIndex={0}
                onMouseEnter={inspectAtPointer(n)}
                onMouseMove={moveInspector(n)}
                onMouseLeave={hideInspector}
                onFocus={inspectAtPointer(n)}
                onBlur={hideInspector}
                onPointerDown={startDrag(n)}
                style={{ cursor: 'grab' }}
              >
                <circle cx={x} cy={y} r={r} className="c-core" />
                {n.img && (
                  <image
                    href={`/projects/thumbs/${n.img}.webp`}
                    x={x - r}
                    y={y - r}
                    width={r * 2}
                    height={r * 2}
                    clipPath={`url(#clip-${n.id})`}
                    preserveAspectRatio="xMidYMid slice"
                    className="c-img"
                  />
                )}
                <circle
                  cx={x}
                  cy={y}
                  r={r}
                  className={`c-ring${priv ? ' c-ring--private' : ''}`}
                  style={{ stroke: glow, filter: `drop-shadow(0 0 7px ${glow}aa)` }}
                />
                <LensMark x={x} y={y - r - 6} lens={n.lens} color={glow} />
                <text
                  x={x}
                  y={y + r + (isProj ? 17 : 15)}
                  textAnchor="middle"
                  className={isProj ? 'c-plabel' : 'c-alabel'}
                >
                  {n.label}
                  {n.type === 'area' && n.skillCount ? (
                    <tspan className="c-count"> · {n.skillCount}</tspan>
                  ) : null}
                </text>
                {priv && (
                  <text x={x} y={y + r + 30} textAnchor="middle" className="c-priv">
                    public overview
                  </text>
                )}
              </g>
            );
            return isProj && n.slug ? (
              <a
                key={n.id}
                href={`#project-${n.slug}`}
                data-qid={`constellation:jump:${n.slug}`}
                data-qs-action="CONSTELLATION_JUMP"
                aria-label={n.question ? `${n.label} — ${n.question}` : `Jump to ${n.label}`}
                onClick={(e) => {
                  if (moved.current) e.preventDefault(); // was a drag, not a click
                }}
              >
                {inner}
              </a>
            ) : (
              <g key={n.id}>{inner}</g>
            );
          })}
        </svg>
        <div
          id="graph-inspector-card"
          className={`inspector-card${inspector ? '' : ' is-hidden'}`}
          aria-live="polite"
          style={inspector ? { left: inspector.left, top: inspector.top } : undefined}
        >
          {inspector ? (
            <>
              <div className="inspector-card__head">
                <span className="inspector-card__title">{inspector.data.title}</span>
                <span className="inspector-card__lens">{inspector.data.lens}</span>
              </div>
              <p className="inspector-card__taxonomy">{inspector.data.taxonomy}</p>
              <p className="inspector-card__abstract">{inspector.data.abstract}</p>
              {inspector.data.status && <span className="status-badge">{inspector.data.status}</span>}
            </>
          ) : null}
        </div>
      </div>
      <p className="constellation-legend">
        <span className="cl cl--technical">▲ technical</span>
        <span className="cl cl--hybrid">◆ hybrid</span>
        <span className="cl cl--creative">● creative</span>
        <span className="cl-note">dashed ring = private work, public overview only</span>
      </p>
      {/* Text alternative for the graph (d3 a11y): a navigable equivalent — the
          same areas and projects, with real jump links so keyboard / screen-
          reader users reach every project the sighted graph links to. */}
      <nav className="constellation-sr" aria-label="Practice map, as a list">
        <ul>
          {NODES.filter((n) => n.type === 'area').map((a) => {
            const projs = EDGES.filter((e) => e.source === a.id)
              .map((e) => byId.get(e.target))
              .filter(Boolean);
            return (
              <li key={a.id}>
                {a.label}
                {a.skillCount ? ` (${a.skillCount} ${a.skillCount === 1 ? 'skill' : 'skills'})` : ''}
                {projs.length ? (
                  <ul>
                    {projs.map((p) => (
                      <li key={p!.id}>
                        {p!.slug ? (
                          <a
                            href={`#project-${p!.slug}`}
                            data-qid={`constellation:srjump:${p!.slug}`}
                            data-qs-action="CONSTELLATION_SR_JUMP"
                            title={`Jump to ${p!.label}`}
                          >
                            {p!.label}
                          </a>
                        ) : (
                          p!.label
                        )}
                        {p!.lens ? ` — ${p!.lens}` : ''}
                        {p!.visibility && p!.visibility !== 'public'
                          ? ' (public overview only)'
                          : ''}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      </nav>
    </figure>
  );
}
