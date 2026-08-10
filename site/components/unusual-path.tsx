'use client';

import { useEffect, useRef, useState } from 'react';

// A wandering trail, not a chart. It curves, swings across the straight
// "expected" route, and doubles back on itself once (a hook a line chart can
// never make). The past is a solid line; the final approach to "this practice"
// is dotted and hesitant — the present isn't fully drawn yet.
const NODES: { x: number; y: number; label: string }[] = [
  { x: 54, y: 44, label: 'Composer — Adidas, Pepsi, X-Games' },
  { x: 96, y: 98, label: 'Executive producer, Sony' },
  { x: 150, y: 30, label: 'DARPA ARCOS — principal data scientist' },
  { x: 214, y: 102, label: 'AFRL “Hacker” challenge coin' },
  { x: 286, y: 58, label: 'Lean 4 formal methods' },
  { x: 362, y: 26, label: 'This practice' },
];

// Solid trail — the settled past — ending at the Lean 4 node.
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
  'C 250 102, 256 58, 286 58', // → Lean 4 (solid trail ends here)
].join(' ');

// Final approach to "this practice" — dotted, drawn with hesitancy then a
// commit. The present is still being written.
const TRACE_FINAL = 'M 286 58 C 322 58, 340 26, 362 26';

/** The non-linear path under "An unusual path, on purpose." A faint dead-
 *  straight dashed line is the conventional route; the brass trail wanders,
 *  crosses it, and doubles back. The past is solid; the final approach to now
 *  is dotted and hesitant, and the goal dot pulses a focus ring on arrival.
 *  Draws on scroll-in. */
export function UnusualPath() {
  const ref = useRef<SVGSVGElement>(null);
  const [enhanced, setEnhanced] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const el = ref.current;
    if (!el) return;
    setEnhanced(true);
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
      className={`unusual-path-svg${enhanced ? ' is-enhanced' : ''}${visible ? ' is-visible' : ''}`}
      viewBox="0 0 400 128"
      fill="none"
      role="img"
      aria-label="Career path: a winding trail that crosses and doubles back over the conventional straight route through six milestones, with a hesitant final approach to this practice."
    >
      <defs>
        {/* Left-to-right wipe that reveals the dotted final segment. */}
        <clipPath id="unusual-final-clip">
          <rect className="final-clip" x="284" y="4" width="82" height="66" />
        </clipPath>
      </defs>
      {/* The conventional straight route — faint and dashed. */}
      <line className="path-baseline" x1="0" y1="74" x2="400" y2="74" />
      {/* The settled past — solid. */}
      <path
        className="path-line"
        d={TRACE}
        pathLength={1000}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* The hesitant present — dotted, revealed by the wipe. */}
      <path
        className="path-final"
        d={TRACE_FINAL}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        clipPath="url(#unusual-final-clip)"
      />
      {/* Focus ring that expands + glows when the line reaches the goal. */}
      <circle className="goal-ring" cx="362" cy="26" r="3.6" fill="none" stroke="currentColor" />
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
