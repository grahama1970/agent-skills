'use client';

import { useEffect, useState } from 'react';

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
  const cur = phases[idx];
  const go = (next: number) =>
    setIdx(Math.min(Math.max(next, 0), phases.length - 1));

  useEffect(() => {
    if (!zoom) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setZoom(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoom]);

  return (
    <div
      className="stepper"
      onKeyDown={(e) => {
        const k = e.key.toLowerCase();
        if (e.key === 'ArrowRight' || k === 'l') {
          e.preventDefault();
          go(idx + 1);
        }
        if (e.key === 'ArrowLeft' || k === 'h') {
          e.preventDefault();
          go(idx - 1);
        }
      }}
    >
      <button
        type="button"
        className="stepper-view"
        style={{
          ['--img' as string]: `url('/dream/${cur.f}.webp')`,
          ['--tint' as string]: cur.t,
        }}
        data-qid="dream:action:zoom"
        data-qs-action="DREAM_ZOOM_FRAME"
        title={`Open phase ${cur.n} frame full-screen`}
        onClick={() => setZoom(true)}
        aria-label={`Phase ${cur.n} — ${cur.c}. Click to view full-screen.`}
      >
        <span className="hud hud-tl">
          [{cur.n}/{String(phases.length).padStart(2, '0')}] {cur.c}
        </span>
        <span className="hud hud-br">
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
      <p className="stepper-hint">
        ← → or H / L to scrub · click frame to zoom · every value in the
        overlay is the file&apos;s real path and size
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
