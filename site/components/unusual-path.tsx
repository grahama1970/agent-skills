'use client';

import { useEffect, useRef, useState } from 'react';

// Waypoints map to the published career TRACK (composer → Sony → DARPA → AFRL →
// Lean 4 → this practice). The real path diverges hard from the flat dashed
// "expected" line and ends elevated at the practice — the divergence itself is
// the point of "an unusual path, on purpose." Labels are the stops' own words.
const STOPS: { x: number; y: number; label: string }[] = [
  { x: 40, y: 60, label: 'Composer — Adidas, Pepsi, X-Games' },
  { x: 100, y: 20, label: 'Executive producer, Sony' },
  { x: 170, y: 80, label: 'DARPA ARCOS — principal data scientist' },
  { x: 220, y: 42, label: 'AFRL “Hacker” challenge coin' },
  { x: 290, y: 66, label: 'Lean 4 formal methods' },
  { x: 362, y: 28, label: 'This practice' },
];
const TRACE = `M0 90 L${STOPS.map((s) => `${s.x} ${s.y}`).join(' L')} L400 28`;

/** The non-linear path under "An unusual path, on purpose." A faint dashed
 *  baseline is the conventional route; the brass trace diverges through the
 *  real milestones and ends high on its own. Draws once on scroll-in. */
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
      viewBox="0 0 400 108"
      fill="none"
      role="img"
      aria-label="Career path: a line diverging from the conventional straight route through six milestones, ending elevated at this practice."
    >
      {/* The conventional path everyone else takes. */}
      <line className="path-baseline" x1="0" y1="90" x2="400" y2="90" />
      {/* The actual, divergent path. */}
      <path className="path-line" d={TRACE} stroke="currentColor" strokeWidth="2" />
      {STOPS.map((s, i) => (
        <circle
          key={s.label}
          className={`path-node n${i + 1}${i === STOPS.length - 1 ? ' is-final' : ''}`}
          cx={s.x}
          cy={s.y}
          r={i === STOPS.length - 1 ? 3.4 : 2.4}
          fill="currentColor"
        >
          <title>{s.label}</title>
        </circle>
      ))}
    </svg>
  );
}
