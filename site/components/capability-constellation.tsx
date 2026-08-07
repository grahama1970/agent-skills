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
  img?: string;
}
interface GEdge {
  source: string;
  target: string;
  rel: string;
}

const NODES = graph.nodes as GNode[];
const EDGES = graph.edges as GEdge[];

const W = 1120;
const H = 940;
const CX = W / 2;
const CY = H / 2;
const R_AREA = 214;
const R_PROJ = 372;

// Concrete colours (drop-shadow glow needs a real colour, not a CSS var).
const GLOW: Record<string, string> = {
  technical: '#e2ac62',
  creative: '#d1703c',
  hybrid: '#93a289',
};

function polar(deg: number, r: number): [number, number] {
  const a = (deg * Math.PI) / 180;
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)];
}

/**
 * Capability constellation — image-filled glowing nodes on a dark field, in the
 * spirit of the persona-dream graph. Deterministic radial layout (settles
 * instantly, no physics); explicit edges only; projects carry their real
 * concept image, private work a dashed ring. Warm brass/ember/sage palette.
 */
export function CapabilityConstellation() {
  const [hover, setHover] = useState<string | null>(null);

  const pos = useMemo(() => {
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
    const lensRank: Record<string, number> = { technical: 0, hybrid: 1, creative: 2 };
    const ordered = [...areas].sort(
      (a, b) => (lensRank[a.lens!] - lensRank[b.lens!]) || a.id.localeCompare(b.id),
    );
    const n = ordered.length;
    ordered.forEach((a, i) => {
      const angle = -90 + (i / n) * 360;
      p.set(a.id, polar(angle, R_AREA));
      const projs = projByArea.get(a.id) ?? [];
      projs.forEach((pr, j) => {
        const t = projs.length === 1 ? 0 : j / (projs.length - 1) - 0.5;
        p.set(pr.id, polar(angle + t * (360 / n) * 0.92, R_PROJ));
      });
    });
    return p;
  }, []);

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
      </figcaption>
      <div className="constellation-field">
        <svg viewBox={`0 0 ${W} ${H}`} className="constellation-svg" role="img">
          <defs>
            {NODES.filter((n) => n.img).map((n) => {
              const xy = pos.get(n.id);
              if (!xy) return null;
              return (
                <clipPath id={`clip-${n.slug}`} key={n.id}>
                  <circle cx={xy[0]} cy={xy[1]} r={33} />
                </clipPath>
              );
            })}
          </defs>

          {EDGES.map((e) => {
            const s = pos.get(e.source);
            const t = pos.get(e.target);
            if (!s || !t) return null;
            const mx = (s[0] + t[0]) / 2 + (CX - (s[0] + t[0]) / 2) * 0.14;
            const my = (s[1] + t[1]) / 2 + (CY - (s[1] + t[1]) / 2) * 0.14;
            const on = connected(e.source) && connected(e.target);
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
            const on = connected(n.id);
            const glow = n.lens ? GLOW[n.lens] : '#a99787';

            if (n.type === 'practice') {
              return (
                <g key={n.id} className={`c-node${on ? '' : ' is-dim'}`}>
                  <circle cx={x} cy={y} r={52} className="c-core" />
                  <circle
                    cx={x}
                    cy={y}
                    r={52}
                    className="c-ring c-ring--core"
                    style={{ filter: `drop-shadow(0 0 10px rgba(226,172,98,.55))` }}
                  />
                  <text x={x} y={y + 5} textAnchor="middle" className="c-practice">
                    one practice
                  </text>
                </g>
              );
            }

            const isProj = n.type === 'project';
            const r = isProj ? 33 : 24;
            const priv = n.visibility && n.visibility !== 'public';
            const inner = (
              <g
                className={`c-node c-node--${n.type}${on ? '' : ' is-dim'}`}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
              >
                <circle cx={x} cy={y} r={r} className="c-core" />
                {isProj && n.img && (
                  <image
                    href={`/projects/${n.img}.webp`}
                    x={x - r}
                    y={y - r}
                    width={r * 2}
                    height={r * 2}
                    clipPath={`url(#clip-${n.slug})`}
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
              >
                {inner}
              </a>
            ) : (
              <g key={n.id}>{inner}</g>
            );
          })}
        </svg>
      </div>
      <p className="constellation-legend">
        <span className="cl cl--technical">technical</span>
        <span className="cl cl--hybrid">hybrid</span>
        <span className="cl cl--creative">creative</span>
        <span className="cl-note">dashed ring = private work, public overview only</span>
      </p>
    </figure>
  );
}
