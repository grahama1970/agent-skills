'use client';

import { useLayoutEffect, useRef, useState } from 'react';

interface BridgeGeometry {
  width: number;
  height: number;
  outbound: string;
  inbound: string;
}

/**
 * Measures the real DOM rectangles of the hero's "prove" word
 * ([data-proof-origin]) and the lineage's G0 node ([data-proof-entry]) and
 * draws an SVG wire between them across .hero-grid. One measurement after
 * fonts settle; re-measures only on layout resize. Two finite
 * <animateMotion> tokens: the claim leaves "prove", the receipt returns.
 */
export function HeroProofBridge() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [geometry, setGeometry] = useState<BridgeGeometry | null>(null);
  const [ready, setReady] = useState(false);

  useLayoutEffect(() => {
    const svg = svgRef.current;
    const grid = svg?.closest('.hero-grid') as HTMLElement | null;
    if (!grid) return;
    let disposed = false;

    const measure = () => {
      if (disposed) return;
      const origin = grid.querySelector('[data-proof-origin]') as HTMLElement | null;
      const entry = grid.querySelector('[data-proof-entry]') as SVGGraphicsElement | null;
      const gridRect = grid.getBoundingClientRect();
      if (!origin || !entry || !gridRect.width || !gridRect.height) {
        return;
      }
      // The rail animation still runs at 1024-1199px, but the cross-column
      // bridge is deliberately absent.
      if (window.innerWidth < 1200) {
        setGeometry(null);
        grid.classList.add('proof-ready');
        setReady(true);
        return;
      }
      const originRect = origin.getBoundingClientRect();
      const entryRect = entry.getBoundingClientRect();
      const sx = originRect.right - gridRect.left + 4;
      const sy = originRect.bottom - gridRect.top - 5;
      const ex = entryRect.left - gridRect.left + entryRect.width / 2;
      const ey = entryRect.top - gridRect.top + entryRect.height / 2;
      if (ex <= sx + 32) {
        setGeometry(null);
        grid.classList.add('proof-ready');
        setReady(true);
        return;
      }
      const elbow = sx + (ex - sx) * 0.62;
      const radius = 8;
      const outbound = [
        `M ${sx} ${sy}`,
        `H ${elbow - radius}`,
        `Q ${elbow} ${sy} ${elbow} ${sy + radius}`,
        `V ${ey - radius}`,
        `Q ${elbow} ${ey} ${elbow + radius} ${ey}`,
        `H ${ex}`,
      ].join(' ');
      // Exact reverse geometry, rather than relying on CSS motion-path
      // coordinates outside the local SVG.
      const inbound = [
        `M ${ex} ${ey}`,
        `H ${elbow + radius}`,
        `Q ${elbow} ${ey} ${elbow} ${ey - radius}`,
        `V ${sy + radius}`,
        `Q ${elbow} ${sy} ${elbow - radius} ${sy}`,
        `H ${sx}`,
      ].join(' ');
      setGeometry({
        width: gridRect.width,
        height: gridRect.height,
        outbound,
        inbound,
      });
      grid.classList.add('proof-ready');
      setReady(true);
    };

    const start = async () => {
      await document.fonts?.ready;
      requestAnimationFrame(measure);
    };
    void start();

    const observer = new ResizeObserver(measure);
    observer.observe(grid);
    return () => {
      disposed = true;
      observer.disconnect();
      grid.classList.remove('proof-ready');
    };
  }, []);

  return (
    <svg
      ref={svgRef}
      className={`proof-bridge${ready ? ' is-ready' : ''}`}
      viewBox={geometry ? `0 0 ${geometry.width} ${geometry.height}` : undefined}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {geometry && (
        <>
          <path
            id="hero-proof-outbound"
            className="proof-bridge__wire"
            d={geometry.outbound}
            pathLength="1"
          />
          <path id="hero-proof-inbound" d={geometry.inbound} fill="none" stroke="none" />
          {/* Claim leaves "prove". */}
          <rect
            className="proof-bridge__token proof-bridge__token--out"
            x="-1.5"
            y="-1.5"
            width="3"
            height="3"
          >
            <animateMotion begin="0.8s" dur="0.55s" fill="freeze">
              <mpath href="#hero-proof-outbound" />
            </animateMotion>
            <animate
              attributeName="opacity"
              values="0;1;1;0"
              keyTimes="0;0.08;0.9;1"
              begin="0.8s"
              dur="0.55s"
              fill="freeze"
            />
          </rect>
          {/* Receipt returns after the local lineage has resolved. */}
          <rect
            className="proof-bridge__token proof-bridge__token--return"
            x="-1.75"
            y="-1.75"
            width="3.5"
            height="3.5"
          >
            <animateMotion begin="4.82s" dur="0.38s" fill="freeze">
              <mpath href="#hero-proof-inbound" />
            </animateMotion>
            <animate
              attributeName="opacity"
              values="0;1;1;0"
              keyTimes="0;0.08;0.9;1"
              begin="4.82s"
              dur="0.38s"
              fill="freeze"
            />
          </rect>
        </>
      )}
    </svg>
  );
}
