import { Copy, MoveLeft, MoveRight, Play, Plus, Trash2, Undo2 } from 'lucide-react'
import { useState } from 'react'
import type { UiDeckBundle, UiSlide } from '../types'

// Keynote-pattern edit chrome: a top toolbar for slide-level actions and a
// left rail for slide navigation. Every mutation posts /api/deck-op, which
// runs the full fail-closed bundle validation before writing anything.

async function postOp(op: string, slideId: string): Promise<string | null> {
  const response = await fetch('/api/deck-op', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ op, slide_id: slideId }),
  })
  if (response.ok) return null
  const data = (await response.json()) as { error?: string }
  return data.error ?? `operation failed (${response.status})`
}

export async function postUndo(): Promise<string | null> {
  const response = await fetch('/api/undo', { method: 'POST' })
  if (response.ok) return null
  const data = (await response.json()) as { error?: string }
  return data.error ?? `undo failed (${response.status})`
}

export function EditToolbar({
  slide,
  slideCount,
  onChanged,
  onPresent,
}: {
  slide: UiSlide
  slideCount: number
  onChanged: () => void
  onPresent: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (op: string) => {
    setBusy(true)
    setError(null)
    const failure = await postOp(op, slide.id)
    setBusy(false)
    if (failure) setError(failure)
    else onChanged()
  }

  const runUndo = async () => {
    setBusy(true)
    setError(null)
    const failure = await postUndo()
    setBusy(false)
    if (failure) setError(failure)
    else onChanged()
  }

  const button =
    'inline-flex cursor-pointer items-center justify-center rounded-lg border border-transparent p-2 text-slate-300 transition-colors hover:border-slate-600 hover:text-cyan-300 disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <div
      role="toolbar"
      aria-label="Slide actions"
      className="flex items-center justify-center gap-0.5"
    >
      <button
        type="button"
        aria-label="Undo last change"
        data-qid="deck:toolbar:undo"
        data-qs-action="DECK_UNDO"
        title="Undo the last committed change (Ctrl+Z)"
        disabled={busy}
        onClick={() => void runUndo()}
        className={button}
      >
        <Undo2 aria-hidden className="h-5 w-5" />
      </button>
      <button
        type="button"
        aria-label="Add slide"
        data-qid="deck:toolbar:add-slide"
        data-qs-action="DECK_ADD_SLIDE"
        title="Add a new slide after this one"
        disabled={busy}
        onClick={() => void run('add_after')}
        className={button}
      >
        <Plus aria-hidden className="h-5 w-5" />
      </button>
      <button
        type="button"
        aria-label="Duplicate slide"
        data-qid="deck:toolbar:duplicate-slide"
        data-qs-action="DECK_DUPLICATE_SLIDE"
        title="Duplicate this slide"
        disabled={busy}
        onClick={() => void run('duplicate')}
        className={button}
      >
        <Copy aria-hidden className="h-5 w-5" />
      </button>
      <button
        type="button"
        aria-label="Move slide earlier"
        data-qid="deck:toolbar:move-left"
        data-qs-action="DECK_MOVE_SLIDE_LEFT"
        title="Move this slide earlier"
        disabled={busy || slide.order === 1}
        onClick={() => void run('move_left')}
        className={button}
      >
        <MoveLeft aria-hidden className="h-5 w-5" />
      </button>
      <button
        type="button"
        aria-label="Move slide later"
        data-qid="deck:toolbar:move-right"
        data-qs-action="DECK_MOVE_SLIDE_RIGHT"
        title="Move this slide later"
        disabled={busy || slide.order === slideCount}
        onClick={() => void run('move_right')}
        className={button}
      >
        <MoveRight aria-hidden className="h-5 w-5" />
      </button>
      <button
        type="button"
        aria-label="Delete slide"
        data-qid="deck:toolbar:delete-slide"
        data-qs-action="DECK_DELETE_SLIDE"
        title="Delete this slide"
        disabled={busy || slideCount === 1}
        onClick={() => void run('delete')}
        className={`${button} hover:border-rose-500/60 hover:text-rose-300`}
      >
        <Trash2 aria-hidden className="h-5 w-5" />
      </button>
      <span className="mx-1 h-5 w-px bg-slate-800" aria-hidden />
      <button
        type="button"
        aria-label="Present"
        data-qid="deck:toolbar:present"
        data-qs-action="DECK_PRESENT"
        title="Exit edit mode and present"
        onClick={onPresent}
        className={`${button} border-cyan-700 text-cyan-200`}
      >
        <Play aria-hidden className="h-5 w-5" />
      </button>
      {busy ? <span className="text-xs text-slate-500">Validating…</span> : null}
      {error ? (
        <span role="alert" className="text-xs text-rose-300">
          Rejected: {error}
        </span>
      ) : null}
    </div>
  )
}

export function SlideRail({
  deck,
  currentIndex,
  onSelect,
  width,
}: {
  deck: UiDeckBundle
  currentIndex: number
  onSelect: (index: number) => void
  width?: number
}) {
  return (
    <nav aria-label="Slides" style={width ? { width, minWidth: width } : undefined} className="w-44 min-w-44 overflow-y-auto bg-slate-900/50 p-2">
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {deck.slides.map((slide, index) => (
          <li key={slide.id}>
            <button
              type="button"
              data-qid={`deck:rail:slide:${slide.id}`}
              data-qs-action="DECK_RAIL_GOTO_SLIDE"
              title={`Go to slide ${slide.order}: ${slide.title}`}
              aria-current={index === currentIndex ? 'true' : undefined}
              onClick={() => onSelect(index)}
              className={`w-full cursor-pointer rounded-lg border p-2 text-left transition-colors ${
                index === currentIndex
                  ? 'border-cyan-500/70 bg-cyan-500/10'
                  : 'border-slate-800 bg-slate-950 hover:border-slate-600'
              }`}
            >
              <span className="font-mono text-[10px] text-slate-500">{slide.order} · {slide.layout}</span>
              <span className="mt-0.5 block truncate text-xs text-slate-200">{slide.title}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}
