'use client';

import { useEffect, useRef, useState } from 'react';

// A wandering trail, not a chart. It curves, swings across the straight
// "expected" route, and doubles back on itself once (a hook a line chart can
// never make) before ending elevated at this practice. Nodes sit on the trail
// at the six real published milestones; labels are the stops' own words.
const NODES: { x: number; y: number; label: string }[] = [
  { x: 54, y: 44, label: 'Composer — Adidas, Pepsi, X-Games' },
  { x: 96, y: 98, label: 'Executive producer, Sony' },
  { x: 150, y: 30, label: 'DARPA ARCOS — principal data scientist' },
  { x: 214, y: 102, label: 'AFRL “Hacker” challenge coin' },
  { x: 286, y: 58, label: 'Lean 4 formal methods' },
  { x: 362, y: 26, label: 'This practice' },
];

// Hand-authored winding trail through the nodes, with a backward hook after
// the DARPA node so the path visibly crosses and doubles back on itself.
const TRACE = [
  'M0 74',
  'C 22 60, 38 44, 54 44', // → composer
  'C 78 44, 78 98, 96 98', // swing down → Sony
  'C 122 98, 120 22, 150 30', // up → DARPA
  // pronounced doubling-back loop after DARPA: swings right, loops back left
  // across its own upstroke, then advances — a self-crossing a chart can't make
  'C 182 32, 200 60, 172 68',
  'C 140 78, 128 44, 160 42',
  'C 188 40, 200 92, 214 102', // → AFRL
  'C 250 102, 256 58, 286 58', // → Lean 4
  'C 322 58, 340 26, 362 26', // → this practice (the path TERMINATES here)
].join(' ');

/** The non-linear path under "An unusual path, on purpose." A faint dead-
 *  straight dashed line is the conventional route; the brass trail wanders,
 *  crosses it, and doubles back before ending high on its own. Draws on
 *  scroll-in. */
export function UnusualPath() {
  const ref = useRef<SVGSVGElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          io.disconnect();
        }
      },
      { threshold: 0.6 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <svg
      ref={ref}
      className={`unusual-path-svg${visible ? ' is-visible' : ''}`}
      viewBox="0 0 400 128"
      fill="none"
      role="img"
      aria-label="Career path: a winding trail that crosses and doubles back over the conventional straight route through six milestones, ending elevated at this practice."
    >
      {/* The conventional straight route — faint and dashed. */}
      <line className="path-baseline" x1="0" y1="74" x2="400" y2="74" />
      {/* The actual, wandering trail. */}
      <path
        className="path-line"
        d={TRACE}
        pathLength={1000}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {NODES.map((s, i) => (
        <circle
          key={s.label}
          className={`path-node n${i + 1}${i === NODES.length - 1 ? ' is-final' : ''}`}
          cx={s.x}
          cy={s.y}
          r={i === NODES.length - 1 ? 3.6 : 2.6}
          fill="currentColor"
        >
          <title>{s.label}</title>
        </circle>
      ))}
    </svg>
  );
}
