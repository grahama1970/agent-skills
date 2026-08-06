'use client';

import { useState } from 'react';

export interface DreamPhase {
  f: string;
  n: string;
  c: string;
  t: string;
}

/** Step-by-step viewer for the persona-dream pipeline: one real frame at
 *  inspectable size, thumbnail rail below, arrow keys when focused. */
export function DreamStepper({ phases }: { phases: DreamPhase[] }) {
  const [idx, setIdx] = useState(0);
  const cur = phases[idx];
  const go = (next: number) =>
    setIdx(Math.min(Math.max(next, 0), phases.length - 1));

  return (
    <div
      className="stepper"
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight') {
          e.preventDefault();
          go(idx + 1);
        }
        if (e.key === 'ArrowLeft') {
          e.preventDefault();
          go(idx - 1);
        }
      }}
    >
      <figure
        className="stepper-view"
        style={{
          ['--img' as string]: `url('/dream/${cur.f}.webp')`,
          ['--tint' as string]: cur.t,
        }}
        role="img"
        aria-label={`Phase ${cur.n} — ${cur.c}`}
      >
        <figcaption>
          <b>
            {cur.n} / {String(phases.length).padStart(2, '0')}
          </b>{' '}
          {cur.c}
        </figcaption>
      </figure>
      <div className="stepper-controls">
        <button
          type="button"
          data-qid="dream:action:prev"
          data-qs-action="DREAM_PREV_PHASE"
          title="Previous pipeline phase"
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
          title="Next pipeline phase"
          onClick={() => go(idx + 1)}
          disabled={idx === phases.length - 1}
        >
          next →
        </button>
      </div>
    </div>
  );
}
