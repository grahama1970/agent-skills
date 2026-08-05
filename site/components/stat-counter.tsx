'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * Counts up to `value` when scrolled into view. Renders the final value
 * for SSR/no-JS/reduced-motion, so the real number is always present.
 */
export function StatCounter({ value, label }: { value: number; label: string }) {
  const ref = useRef<HTMLElement>(null);
  const [display, setDisplay] = useState(value);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        io.disconnect();
        const start = performance.now();
        const dur = 1100;
        const tick = (now: number) => {
          const p = Math.min(1, (now - start) / dur);
          setDisplay(Math.round(value * (1 - Math.pow(1 - p, 3))));
          if (p < 1) requestAnimationFrame(tick);
        };
        setDisplay(0);
        requestAnimationFrame(tick);
      },
      { threshold: 0.6 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [value]);

  return (
    <div className="border-t-2 border-accent pt-3">
      <b
        ref={ref}
        className="block font-mono text-3xl font-semibold tabular-nums"
        aria-label={String(value)}
      >
        {display}
      </b>
      <span className="text-[13px] text-mute">{label}</span>
    </div>
  );
}
