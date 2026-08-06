'use client';

import { useEffect, useRef, useState } from 'react';

/** The non-linear DAG trace under "An unusual path, on purpose." — draws
 *  once when scrolled into view. A visual metaphor for the copy: the line
 *  branches off baseline through waypoint nodes (composer → Sony → DARPA →
 *  here) and resolves back to alignment. Pure CSS stroke-dashoffset. */
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
      viewBox="0 0 400 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        className="path-line"
        d="M0 12 L60 12 L95 5 L140 19 L190 7 L235 16 L280 12 L400 12"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <circle className="path-node n1" cx="95" cy="5" r="2.2" fill="currentColor" />
      <circle className="path-node n2" cx="140" cy="19" r="2.2" fill="currentColor" />
      <circle className="path-node n3" cx="190" cy="7" r="2.2" fill="currentColor" />
      <circle className="path-node n4" cx="235" cy="16" r="2.2" fill="currentColor" />
    </svg>
  );
}
