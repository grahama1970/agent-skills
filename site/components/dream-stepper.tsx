'use client';

import { useEffect, useRef, useState } from 'react';

export interface DreamPhase {
  f: string;
  n: string;
  c: string;
  t: string;
  /** Real source dimensions of the frame file. */
  dims: string;
  /** Real origin path within the repo/skill. */
  src: string;
}

/** Step-by-step viewer for the persona-dream pipeline. One real frame at
 *  inspectable size; HUD overlays show only real metadata (phase, source
 *  path, native dimensions). Arrow or H/L keys scrub; click for lightbox. */
export function DreamStepper({ phases }: { phases: DreamPhase[] }) {
  const [idx, setIdx] = useState(0);
  const [zoom, setZoom] = useState(false);
  const scrubLock = useRef(false);
  const cur = phases[idx];
  const go = (next: number) =>
    setIdx(Math.min(Math.max(next, 0), phases.length - 1));

  // Dual-buffer cross-fade: two stacked layers, only one visible. On a phase
  // change the incoming frame is written to the hidden buffer and faded in
  // (CSS opacity, GPU-composited) while the old one fades out — no flash, no
  // hard swap. Preloaded frames (below) make the incoming layer paint instantly.
  const [buffers, setBuffers] = useState<[DreamPhase, DreamPhase | null]>([
    phases[0],
    null,
  ]);
  const [active, setActive] = useState(0);
  // Direction of the last move (+1 forward, -1 back) so the incoming layer
  // drifts a few px from the travel side as it fades — directional cue without
  // a full slide.
  const [dir, setDir] = useState(0);
  const prevIdx = useRef(0);
  const firstRun = useRef(true);
  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      prevIdx.current = idx;
      return;
    }
    setDir(Math.sign(idx - prevIdx.current));
    prevIdx.current = idx;
    const next = active === 0 ? 1 : 0;
    setBuffers((prev) => {
      const copy: [DreamPhase, DreamPhase | null] = [prev[0], prev[1]];
      copy[next] = cur;
      return copy;
    });
    setActive(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);

  // Touch/pointer swipe → drives the cross-fade (not a slide). Direction-lock
  // (horizontal vs vertical) lets vertical page scroll pass through; a fast
  // flick counts even under the distance threshold.
  const drag = useRef<{
    x: number;
    y: number;
    t: number;
    horiz: boolean | null;
  } | null>(null);
  const suppressClick = useRef(false);
  const onPointerDown = (e: React.PointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, t: e.timeStamp, horiz: null };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (d.horiz === null && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
      d.horiz = Math.abs(dx) > Math.abs(dy);
    }
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (!d || !d.horiz) return;
    const dx = e.clientX - d.x;
    const v = dx / Math.max(1, e.timeStamp - d.t); // px per ms
    if (dx < -50 || v < -0.5) {
      suppressClick.current = true;
      go(idx + 1);
    } else if (dx > 50 || v > 0.5) {
      suppressClick.current = true;
      go(idx - 1);
    }
  };

  const stepperRef = useRef<HTMLDivElement>(null);
  // Preload the current frame and its immediate neighbours as you scrub, so a
  // swap never waits on the network.
  useEffect(() => {
    for (const j of [idx - 1, idx, idx + 1]) {
      const p = phases[j];
      if (p) {
        const img = new Image();
        img.src = `/dream/${p.f}.webp`;
      }
    }
  }, [idx, phases]);
  // Preload the remaining frames only once the Dream section nears the
  // viewport — mobile visitors who never scroll this far don't pay for all 11.
  useEffect(() => {
    const el = stepperRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          for (const p of phases) {
            const img = new Image();
            img.src = `/dream/${p.f}.webp`;
          }
          io.disconnect();
        }
      },
      { rootMargin: '600px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [phases]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setZoom(false);
        return;
      }
      const el = document.activeElement as HTMLElement | null;
      const editing =
        !!el &&
        (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) ||
          el.isContentEditable);
      if (editing) return;
      const k = e.key.toLowerCase();
      const isScrub =
        e.key === 'ArrowRight' || e.key === 'ArrowLeft' || k === 'l' || k === 'h';
      // Throttle held-key repeat so rapid scrubbing doesn't stack frame swaps.
      if (isScrub) {
        if (scrubLock.current) return;
        scrubLock.current = true;
        setTimeout(() => {
          scrubLock.current = false;
        }, 120);
      }
      if (e.key === 'ArrowRight' || k === 'l') {
        go(idx + 1);
      } else if (e.key === 'ArrowLeft' || k === 'h') {
        go(idx - 1);
      } else {
        const num = parseInt(e.key, 10);
        if (!Number.isNaN(num)) {
          // Frame 00 (overview) sits at idx 0, so phase N is at idx N; 0 jumps
          // to the last frame.
          const target = num === 0 ? phases.length - 1 : num;
          if (target >= 0 && target < phases.length) setIdx(target);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [idx, phases.length]);

  return (
    <div className="stepper" ref={stepperRef} style={{ ['--dir' as string]: dir }}>
      <button
        type="button"
        className="stepper-view"
        data-qid="dream:action:zoom"
        data-qs-action="DREAM_ZOOM_FRAME"
        title="Zoom this dream frame"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onClick={() => {
          if (suppressClick.current) {
            suppressClick.current = false;
            return;
          }
          setZoom(true);
        }}
        aria-label={`Phase ${cur.n} — ${cur.c}. Click to view full-screen.`}
      >
        {buffers.map((b, i) =>
          b ? (
            <span
              key={i}
              className={`stepper-layer${active === i ? ' is-active' : ''}`}
              style={{
                ['--img' as string]: `url('/dream/${b.f}.webp')`,
                ['--tint' as string]: b.t,
              }}
              aria-hidden="true"
            />
          ) : null,
        )}
        <span className="hud hud-tl" aria-hidden="true">
          [{cur.n}/{String(phases.length).padStart(2, '0')}] {cur.c}
        </span>
        <span className="hud hud-br" aria-hidden="true">
          {cur.src} · {cur.dims}
        </span>
      </button>
      <div className="stepper-controls">
        <button
          type="button"
          data-qid="dream:action:prev"
          data-qs-action="DREAM_PREV_PHASE"
          title="Previous pipeline phase (← or H)"
          onClick={() => go(idx - 1)}
          disabled={idx === 0}
        >
          ← prev
        </button>
        <div className="stepper-thumbs" role="tablist" aria-label="Pipeline phases">
          {phases.map((p, i) => (
            <button
              key={p.f}
              type="button"
              role="tab"
              aria-selected={i === idx}
              data-qid={`dream:thumb:${p.f}`}
              data-qs-action="DREAM_GOTO_PHASE"
              title={`${p.n} — ${p.c}`}
              onClick={() => setIdx(i)}
              className={`stepper-thumb${i === idx ? ' is-current' : ''}`}
              style={{ ['--img' as string]: `url('/dream/${p.f}.webp')` }}
            >
              <span className="sr-only">{p.c}</span>
              <i>{p.n}</i>
            </button>
          ))}
        </div>
        <button
          type="button"
          data-qid="dream:action:next"
          data-qs-action="DREAM_NEXT_PHASE"
          title="Next pipeline phase (→ or L)"
          onClick={() => go(idx + 1)}
          disabled={idx === phases.length - 1}
        >
          next →
        </button>
      </div>
      <p className="stepper-hint stepper-hint--key">
        ← → or H / L to scrub · 1–9 jump to a phase, 0 to the last phase, ← from 01
        for the overview · click frame to zoom · every value in the overlay is
        the file&apos;s real path and size
      </p>
      <p className="stepper-hint stepper-hint--touch">
        Swipe, or tap a thumbnail, to move through the pipeline · tap the large
        frame to expand it · every value in the overlay is the file&apos;s real
        path and size
      </p>
      {zoom && (
        <div
          className="lightbox"
          role="dialog"
          aria-label={`Phase ${cur.n} frame, full size`}
          onClick={() => setZoom(false)}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/dream/${cur.f}.webp`} alt={`Phase ${cur.n} — ${cur.c}`} />
          <button
            type="button"
            data-qid="dream:action:close-zoom"
            data-qs-action="DREAM_CLOSE_ZOOM"
            title="Close full-screen view (Esc)"
            onClick={() => setZoom(false)}
          >
            × close
          </button>
        </div>
      )}
    </div>
  );
}
