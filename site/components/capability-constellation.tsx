'use client';

import { useMemo, useState } from 'react';
import graph from '@/graph.json';

interface GNode {
  id: string;
  type: 'practice' | 'area' | 'project';
  label: string;
  lens?: 'technical' | 'creative' | 'hybrid';
  slug?: string;
  href?: string | null;
  question?: string;
  visibility?: string;
  skillCount?: number;
}
interface GEdge {
  source: string;
  target: string;
  rel: string;
}

const NODES = graph.nodes as GNode[];
const EDGES = graph.edges as GEdge[];

// Deterministic radial layout — technical left, creative right, hybrid top
// (the spec's TECHNICAL | HYBRID | CREATIVE regions). No physics: positions are
// computed once and never move, so it settles instantly and screenshots stably.
const W = 920;
const H = 620;
const CX = W / 2;
const CY = H / 2 + 20;
const R_AREA = 168;
const R_PROJ = 268;
const LENS = {
  technical: { center: 180, spread: 120, color: 'var(--brass)' },
  creative: { center: 0, spread: 90, color: 'var(--ember)' },
  hybrid: { center: 270, spread: 40, color: 'var(--sage)' },
} as const;

function polar(angleDeg: number, r: number): [number, number] {
  const a = (angleDeg * Math.PI) / 180;
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)];
}

export function CapabilityConstellation() {
  const [hover, setHover] = useState<string | null>(null);

  const { pos, projectsByArea } = useMemo(() => {
    const areas = NODES.filter((n) => n.type === 'area');
    const projByArea = new Map<string, GNode[]>();
    for (const e of EDGES) {
      if (e.rel === 'system') {
        const arr = projByArea.get(e.source) ?? [];
        arr.push(NODES.find((n) => n.id === e.target)!);
        projByArea.set(e.source, arr);
      }
    }
    const p = new Map<string, [number, number]>();
    p.set('practice', [CX, CY]);
    // group areas by lens, distribute within each lens sector
    const byLens = new Map<string, GNode[]>();
    for (const a of areas) {
      const arr = byLens.get(a.lens!) ?? [];
      arr.push(a);
      byLens.set(a.lens!, arr);
    }
    for (const [lens, arr] of byLens) {
      const { center, spread } = LENS[lens as keyof typeof LENS];
      arr.forEach((a, i) => {
        const t = arr.length === 1 ? 0.5 : i / (arr.length - 1);
        const angle = center - spread / 2 + t * spread;
        p.set(a.id, polar(angle, R_AREA));
        const projs = projByArea.get(a.id) ?? [];
        projs.forEach((pr, j) => {
          const pt = projs.length === 1 ? 0.5 : j / (projs.length - 1);
          const pa = angle - 12 + pt * 24;
          p.set(pr.id, polar(pa, R_PROJ));
        });
      });
    }
    return { pos: p, projectsByArea: projByArea };
  }, []);

  const active = (id: string) =>
    hover === null ||
    hover === id ||
    EDGES.some(
      (e) =>
        (e.source === hover && e.target === id) ||
        (e.target === hover && e.source === id),
    );

  return (
    <figure className="constellation" aria-label="How the practice connects">
      <figcaption className="constellation-cap">
        One practice — technical and creative work, connected by real structure.
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="constellation-svg" role="img">
        {EDGES.map((e) => {
          const s = pos.get(e.source);
          const t = pos.get(e.target);
          if (!s || !t) return null;
          const mx = (s[0] + t[0]) / 2 + (CX - (s[0] + t[0]) / 2) * 0.12;
          const my = (s[1] + t[1]) / 2 + (CY - (s[1] + t[1]) / 2) * 0.12;
          const on = active(e.source) && active(e.target);
          return (
            <path
              key={`${e.source}-${e.target}`}
              d={`M ${s[0]} ${s[1]} Q ${mx} ${my} ${t[0]} ${t[1]}`}
              className={`c-edge${on ? ' is-on' : ''}`}
            />
          );
        })}
        {NODES.map((n) => {
          const xy = pos.get(n.id);
          if (!xy) return null;
          const [x, y] = xy;
          const color =
            n.lens && n.lens in LENS ? LENS[n.lens as keyof typeof LENS].color : 'var(--muted)';
          const on = active(n.id);
          if (n.type === 'practice') {
            return (
              <text key={n.id} x={x} y={y} className="c-practice" textAnchor="middle">
                {n.label}
              </text>
            );
          }
          const isProj = n.type === 'project';
          const jump =
            isProj && n.slug ? `#project-${n.slug}` : undefined;
          const node = (
            <g
              className={`c-node c-node--${n.type}${on ? '' : ' is-dim'}`}
              onMouseEnter={() => setHover(n.id)}
              onMouseLeave={() => setHover(null)}
            >
              <circle
                cx={x}
                cy={y}
                r={isProj ? 5 : 8}
                style={{ fill: isProj ? color : 'transparent', stroke: color }}
                className={
                  n.visibility && n.visibility !== 'public' ? 'c-dot c-dot--private' : 'c-dot'
                }
              />
              <text
                x={x}
                y={y - (isProj ? 10 : 13)}
                textAnchor="middle"
                className={isProj ? 'c-plabel' : 'c-alabel'}
              >
                {n.label}
                {n.type === 'area' && n.skillCount ? (
                  <tspan className="c-count"> · {n.skillCount}</tspan>
                ) : null}
              </text>
            </g>
          );
          return jump ? (
            <a
              key={n.id}
              href={jump}
              data-qid={`constellation:jump:${n.slug}`}
              data-qs-action="CONSTELLATION_JUMP"
              title={n.question ? `${n.label} — ${n.question}` : `Jump to ${n.label}`}
              aria-label={`${n.label} — ${n.question || ''}`}
            >
              {node}
            </a>
          ) : (
            <g key={n.id}>{node}</g>
          );
        })}
      </svg>
      <p className="constellation-legend">
        <span className="cl cl--technical">technical</span>
        <span className="cl cl--hybrid">hybrid</span>
        <span className="cl cl--creative">creative</span>
        <span className="cl-note">dashed ring = private work, public overview only</span>
      </p>
    </figure>
  );
}
