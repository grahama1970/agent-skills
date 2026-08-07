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
  skillCount?: number;
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

const radiusOf = (t: string) => (t === 'practice' ? 46 : t === 'project' ? 30 : 26);
// The ring the node settles onto — keeps the physics legible instead of a hairball.
const orbitOf = (t: string) => (t === 'practice' ? 0 : t === 'area' ? 234 : 392);

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

  return (
    <figure className="constellation" aria-label="How the practice connects">
      <figcaption className="constellation-cap">
        One practice — technical and creative work, connected by real structure.
        <span className="constellation-hint"> Drag a node.</span>
      </figcaption>
      <div className="constellation-field">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="constellation-svg" role="img">
          <defs>
            {simNodes
              .filter((n) => n.img)
              .map((n) => (
                <clipPath id={`clip-${n.id}`} key={n.id}>
                  <circle cx={n.x} cy={n.y} r={radiusOf(n.type)} />
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
                d={`M ${s.x} ${s.y} Q ${mx} ${my} ${t.x} ${t.y}`}
                className={`c-edge${on ? ' is-on' : ''}`}
              />
            );
          })}

          {simNodes.map((n) => {
            const { x, y } = n;
            const on = connected(n.id);
            const glow = n.lens ? GLOW[n.lens] : '#a99787';
            const r = radiusOf(n.type);

            if (n.type === 'practice') {
              return (
                <g key={n.id} className={`c-node${on ? '' : ' is-dim'}`}>
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
                  <text x={x + 16} y={y + 23} textAnchor="middle" className="c-mark-sub">
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
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
                onPointerDown={startDrag(n)}
                style={{ cursor: 'grab' }}
              >
                {n.type === 'area' && <title>{n.title || n.label}</title>}
                <circle cx={x} cy={y} r={r} className="c-core" />
                {n.img && (
                  <image
                    href={`/projects/${n.img}.webp`}
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
                title={n.question ? `${n.label} — ${n.question}` : `Jump to ${n.label}`}
                aria-label={`${n.label} — ${n.question || ''}`}
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
        {(() => {
          const hn = hover ? byId.get(hover) : null;
          const detail =
            hn && hn.type === 'area'
              ? `${hn.title || hn.label}${hn.skillCount ? ` · ${hn.skillCount} skills` : ''}`
              : hn?.question || '';
          return (
            <div className="constellation-hud" aria-hidden="true">
              {hn ? (
                <>
                  <span className="ch-key">{hn.type}</span>
                  <span className="ch-name">{hn.label}</span>
                  {detail && <span className="ch-detail">{detail}</span>}
                  {hn.visibility && hn.visibility !== 'public' && (
                    <span className="ch-priv">public overview only</span>
                  )}
                </>
              ) : (
                <span className="ch-idle">hover a node to inspect · drag to explore</span>
              )}
            </div>
          );
        })()}
      </div>
      <p className="constellation-legend">
        <span className="cl cl--technical">technical</span>
        <span className="cl cl--hybrid">hybrid</span>
        <span className="cl cl--creative">creative</span>
        <span className="cl-note">dashed ring = private work, public overview only</span>
      </p>
      {/* Text alternative for the graph (d3 a11y): the same structure, read linearly. */}
      <ul className="constellation-sr">
        {NODES.filter((n) => n.type === 'area').map((a) => {
          const projs = EDGES.filter((e) => e.source === a.id).map(
            (e) => byId.get(e.target)?.label,
          );
          return (
            <li key={a.id}>
              {a.label}
              {a.skillCount ? ` (${a.skillCount} skills)` : ''}
              {projs.length ? `: ${projs.join(', ')}` : ''}
            </li>
          );
        })}
      </ul>
    </figure>
  );
}
