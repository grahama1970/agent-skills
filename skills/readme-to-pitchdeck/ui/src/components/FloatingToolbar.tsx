import { AArrowDown, AArrowUp, AlignCenter, AlignLeft, AlignRight, Bold, Trash2 } from 'lucide-react'
import { revisionStore } from '../hooks'
import type { UiElement } from '../types'

// Phase 2 (Gemini spec) adapted: contextual toolbar for the selected freeform
// element, wired to REAL manifest ops (element:<id>:bold|size|align, del) —
// every action re-validates the bundle server-side. No unwired style variants.

async function postElementEdit(slideId: string, field: string, value: string): Promise<string | null> {
  const response = await fetch('/api/slide-edit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slide_id: slideId, field, value, base_revision: revisionStore.current }),
  })
  if (response.ok) return null
  const data = (await response.json()) as { error?: string }
  return data.error ?? `edit failed (${response.status})`
}

export function FloatingToolbar({
  slideId,
  element,
  onChanged,
  onError,
}: {
  slideId: string
  element: UiElement
  onChanged: () => void
  onError: (message: string) => void
}) {
  const act = async (field: string, value: string) => {
    const failure = await postElementEdit(slideId, field, value)
    if (failure) onError(failure)
    else onChanged()
  }
  const button =
    'inline-flex cursor-pointer items-center justify-center rounded p-1.5 text-slate-200 transition-colors hover:bg-slate-700 disabled:opacity-40'
  const isText = element.type === 'text'

  return (
    <div
      role="toolbar"
      aria-label={`Element ${element.id} actions`}
      className="absolute left-1/2 top-0 z-40 flex -translate-x-1/2 -translate-y-[110%] items-center gap-0.5 rounded-lg border border-slate-700 bg-slate-800/95 px-1.5 py-1 text-xs shadow-2xl backdrop-blur-md"
      onMouseDown={(event) => event.stopPropagation()}
    >
      {isText ? (
        <>
          <button
            type="button"
            data-qid={`deck:eltoolbar:bold:${element.id}`}
            data-qs-action="DECK_ELEMENT_BOLD"
            title={element.bold ? 'Remove bold' : 'Make bold'}
            aria-pressed={element.bold}
            onClick={() => void act(`element:${element.id}:bold`, element.bold ? 'false' : 'true')}
            className={`${button} ${element.bold ? 'bg-slate-700 text-cyan-300' : ''}`}
          >
            <Bold aria-hidden className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            data-qid={`deck:eltoolbar:size-up:${element.id}`}
            data-qs-action="DECK_ELEMENT_SIZE_UP"
            title="Increase text size"
            onClick={() => void act(`element:${element.id}:size`, String(Math.min(96, element.size_pt + 2)))}
            className={button}
          >
            <AArrowUp aria-hidden className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            data-qid={`deck:eltoolbar:size-down:${element.id}`}
            data-qs-action="DECK_ELEMENT_SIZE_DOWN"
            title="Decrease text size"
            onClick={() => void act(`element:${element.id}:size`, String(Math.max(8, element.size_pt - 2)))}
            className={button}
          >
            <AArrowDown aria-hidden className="h-3.5 w-3.5" />
          </button>
          <span aria-hidden className="mx-0.5 h-4 w-px bg-slate-700" />
          {(
            [
              ['left', AlignLeft],
              ['center', AlignCenter],
              ['right', AlignRight],
            ] as const
          ).map(([align, Icon]) => (
            <button
              key={align}
              type="button"
              data-qid={`deck:eltoolbar:align-${align}:${element.id}`}
              data-qs-action="DECK_ELEMENT_ALIGN"
              title={`Align ${align}`}
              aria-pressed={element.align === align}
              onClick={() => void act(`element:${element.id}:align`, align)}
              className={`${button} ${element.align === align ? 'bg-slate-700 text-cyan-300' : ''}`}
            >
              <Icon aria-hidden className="h-3.5 w-3.5" />
            </button>
          ))}
          <span aria-hidden className="mx-0.5 h-4 w-px bg-slate-700" />
        </>
      ) : null}
      <button
        type="button"
        data-qid={`deck:eltoolbar:delete:${element.id}`}
        data-qs-action="DECK_ELEMENT_DELETE"
        title="Delete element"
        onClick={() => void act(`element:del:${element.id}`, '')}
        className={`${button} text-rose-400 hover:bg-rose-500/20`}
      >
        <Trash2 aria-hidden className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
