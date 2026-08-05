import { PanelRightClose, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { revisionStore } from '../hooks'
import type { UiSlide } from '../types'
import { VisualLayoutPicker } from './VisualLayoutPicker'

// Keynote-pattern selection-scoped inspector: properties of the CURRENT slide,
// every change routed through /api/slide-edit → apply-edit → full fail-closed
// bundle validation. No free-form styling: fonts/colors stay theme decisions.

async function postEdit(slideId: string, field: string, value: string): Promise<string | null> {
  const response = await fetch('/api/slide-edit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slide_id: slideId, field, value, base_revision: revisionStore.current }),
  })
  if (response.ok) return null
  const data = (await response.json()) as { error?: string }
  return data.error ?? `edit failed (${response.status})`
}

export function Inspector({ slide, onChanged, onCollapse, width }: { slide: UiSlide; onChanged: () => void; onCollapse?: () => void; width?: number }) {
  const [footer, setFooter] = useState(slide.footer ?? '')
  const [notes, setNotes] = useState(slide.notes)
  const [newBullet, setNewBullet] = useState('')
  const [busyField, setBusyField] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setFooter(slide.footer ?? '')
    setNotes(slide.notes)
    setError(null)
  }, [slide])

  const apply = async (field: string, value: string) => {
    setBusyField(field)
    setError(null)
    const failure = await postEdit(slide.id, field, value)
    setBusyField(null)
    if (failure) setError(failure)
    else onChanged()
  }

  const label = 'block text-xs font-medium text-slate-400'
  const input = 'mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm text-slate-100'

  return (
    <aside
      aria-label="Slide inspector"
      style={width ? { width, minWidth: width } : undefined}
      className="absolute inset-y-0 right-0 z-10 flex w-80 flex-col gap-5 overflow-y-auto border-l border-slate-800 bg-slate-900/95 p-4 shadow-2xl backdrop-blur lg:static lg:z-auto lg:min-w-80 lg:border-l-0 lg:bg-slate-900/70 lg:shadow-none"
    >
      <header className="flex items-start justify-between gap-2">
        <div>
          <h2 className="m-0 text-sm font-semibold text-slate-200">Slide {slide.order}</h2>
          <p className="m-0 mt-0.5 font-mono text-xs text-slate-500">{slide.id}</p>
        </div>
        {onCollapse ? (
          <button
            type="button"
            aria-label="Collapse inspector"
            data-qid="deck:inspector:collapse"
            data-qs-action="DECK_INSPECTOR_COLLAPSE"
            title="Collapse the inspector"
            onClick={onCollapse}
            className="cursor-pointer rounded-md border border-transparent p-1 text-slate-400 hover:border-slate-600 hover:text-cyan-300"
          >
            <PanelRightClose aria-hidden className="h-4 w-4" />
          </button>
        ) : null}
      </header>

      {error ? (
        <p role="alert" className="m-0 rounded-lg border border-rose-500/50 bg-rose-500/10 p-2 text-xs text-rose-300">
          Rejected by validation: {error}
        </p>
      ) : null}

      <section>
        <VisualLayoutPicker
          currentLayout={slide.layout}
          disabled={busyField === 'layout'}
          onSelectLayout={(layoutId) => void apply('layout', layoutId)}
        />
      </section>

      {slide.layout === 'freeform' ? (
        <section>
          <button
            type="button"
            data-qid="deck:inspector:add-textbox"
            data-qs-action="DECK_ADD_TEXTBOX"
            title="Add a text box to this freeform slide"
            disabled={busyField !== null}
            onClick={() => void apply('element:add:text', 'New text')}
            className="w-full cursor-pointer rounded-lg border border-cyan-700 bg-cyan-600/10 px-3 py-2 text-sm text-cyan-200 hover:border-cyan-500 disabled:opacity-40"
          >
            + Add text box
          </button>
        </section>
      ) : null}

      <section>
        <label className={label} htmlFor="inspector-transition">
          Transition
        </label>
        <select
          id="inspector-transition"
          data-qid="deck:inspector:transition"
          data-qs-action="DECK_INSPECTOR_SET_TRANSITION"
          title="Slide entrance transition (browser deck)"
          value={slide.transition}
          disabled={busyField === 'transition'}
          onChange={(event) => void apply('transition', event.target.value)}
          className={input}
        >
          {['slide', 'slide_up', 'fade', 'zoom', 'flip', 'wipe', 'none'].map((name) => (
            <option key={name} value={name}>
              {name.replace('_', ' ')}
            </option>
          ))}
        </select>
        {slide.transition !== 'none' ? (
          <div className="mt-2">
            <span className="flex items-center justify-between text-[11px] font-mono text-slate-400">
              Duration <strong className="text-slate-200">{slide.transition_duration_ms}ms</strong>
            </span>
            <input
              type="range"
              min={200}
              max={1200}
              step={50}
              data-qid="deck:inspector:transition-duration"
              data-qs-action="DECK_INSPECTOR_SET_TRANSITION_DURATION"
              title="Transition duration in milliseconds"
              defaultValue={slide.transition_duration_ms}
              onMouseUp={(event) => void apply('transition_duration', (event.target as HTMLInputElement).value)}
              onTouchEnd={(event) => void apply('transition_duration', (event.target as HTMLInputElement).value)}
              className="h-1 w-full cursor-pointer accent-cyan-500"
            />
          </div>
        ) : null}
      </section>

      <section>
        <label className={label} htmlFor="inspector-reveal">
          Content reveal
        </label>
        <select
          id="inspector-reveal"
          data-qid="deck:inspector:reveal"
          data-qs-action="DECK_INSPECTOR_SET_REVEAL"
          title="Bullet and card entrance animation"
          value={slide.reveal}
          disabled={busyField === 'reveal'}
          onChange={(event) => void apply('reveal', event.target.value)}
          className={input}
        >
          {['stagger_up', 'stagger_fade', 'none'].map((name) => (
            <option key={name} value={name}>
              {name.replace('_', ' ')}
            </option>
          ))}
        </select>
      </section>

      {slide.visual.asset ? (
        <section>
          <label className={label} htmlFor="inspector-visual-position">
            Visual position
          </label>
          <select
            id="inspector-visual-position"
            data-qid="deck:inspector:visual-position"
            data-qs-action="DECK_INSPECTOR_SET_VISUAL_POSITION"
            title="Where the image or video sits on the slide"
            value={slide.visual.position}
            disabled={busyField === 'visual:position'}
            onChange={(event) => void apply('visual:position', event.target.value)}
            className={input}
          >
            <option value="right">right</option>
            <option value="left">left</option>
            <option value="full">full</option>
          </select>
        </section>
      ) : null}

      <section>
        <label className={label} htmlFor="inspector-footer">
          Footer
        </label>
        <input
          id="inspector-footer"
          data-qid="deck:inspector:footer"
          data-qs-action="DECK_INSPECTOR_SET_FOOTER"
          title="Edit slide footer (empty removes it)"
          value={footer}
          disabled={busyField === 'footer'}
          onChange={(event) => setFooter(event.target.value)}
          onBlur={() => footer !== (slide.footer ?? '') && void apply('footer', footer)}
          className={input}
          placeholder="No footer"
        />
      </section>

      <section>
        <label className={label} htmlFor="inspector-notes">
          Speaker notes
        </label>
        <textarea
          id="inspector-notes"
          data-qid="deck:inspector:notes"
          data-qs-action="DECK_INSPECTOR_SET_NOTES"
          title="Edit speaker notes"
          rows={4}
          value={notes}
          disabled={busyField === 'notes'}
          onChange={(event) => setNotes(event.target.value)}
          onBlur={() => notes !== slide.notes && void apply('notes', notes)}
          className={input}
        />
      </section>

      <section>
        <span className={label}>Bullets</span>
        <ul className="m-0 mt-1 flex list-none flex-col gap-1.5 p-0">
          {slide.body.map((line, index) => (
            <li key={`${index}-${line}`} className="flex items-center gap-1.5">
              <span className="min-w-0 flex-1 truncate rounded-lg border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs text-slate-300">
                {line}
              </span>
              <button
                type="button"
                data-qid={`deck:inspector:bullet-del:${index}`}
                data-qs-action="DECK_INSPECTOR_DELETE_BULLET"
                title={`Delete bullet ${index + 1}`}
                disabled={busyField !== null}
                onClick={() => void apply(`body:del.${index}`, '')}
                className="cursor-pointer rounded-md border border-slate-700 p-1.5 text-slate-400 hover:border-rose-500/60 hover:text-rose-300 disabled:opacity-40"
              >
                <Trash2 aria-hidden className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex items-center gap-1.5">
          <input
            data-qid="deck:inspector:bullet-new"
            title="New bullet text"
            value={newBullet}
            onChange={(event) => setNewBullet(event.target.value)}
            placeholder="Add a bullet…"
            className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-100"
          />
          <button
            type="button"
            data-qid="deck:inspector:bullet-add"
            data-qs-action="DECK_INSPECTOR_ADD_BULLET"
            title="Add bullet to this slide"
            disabled={!newBullet.trim() || busyField !== null}
            onClick={() => {
              void apply('body:add', newBullet.trim())
              setNewBullet('')
            }}
            className="cursor-pointer rounded-md border border-slate-700 p-1.5 text-slate-300 hover:border-cyan-500/60 disabled:opacity-40"
          >
            <Plus aria-hidden className="h-3.5 w-3.5" />
          </button>
        </div>
      </section>

      <p className="m-0 mt-auto text-[11px] leading-snug text-slate-600">
        Every change re-runs the fail-closed bundle validation; rejected edits change nothing. Fonts and colors are
        theme decisions — tune them in the exported PPTX or the theme layer, not per element.
      </p>
    </aside>
  )
}
