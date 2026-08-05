import { ChevronLeft, ChevronRight, LayoutGrid, NotebookText, Pencil, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { ClaimReview } from './components/ClaimReview'
import { DeckChat } from './components/DeckChat'
import { EditContext, type EditRequest } from './edit'
import { useDeck, useKeyboardNav, useRegisterAction, useSlideScale } from './hooks'
import { SlideBody } from './layouts/SlideLayouts'
import { CANVAS_HEIGHT, CANVAS_WIDTH, type UiDeckBundle, type UiSlide } from './types'

type View = 'present' | 'overview' | 'claims'

function viewFromHash(): View {
  const hash = window.location.hash.replace('#/', '')
  return hash === 'overview' || hash === 'claims' ? hash : 'present'
}

function SlideCanvas({ slide, direction }: { slide: UiSlide; direction: 'fwd' | 'back' }) {
  const { ref, scale } = useSlideScale()
  return (
    <div ref={ref} className="relative min-h-0 flex-1 overflow-hidden">
      <div
        key={slide.id}
        className={`absolute left-1/2 top-1/2 overflow-hidden rounded-lg bg-slate-950 shadow-2xl ${direction === 'fwd' ? 'slide-enter' : 'slide-enter-back'}`}
        style={{
          width: CANVAS_WIDTH,
          height: CANVAS_HEIGHT,
          transform: `translate(-50%, -50%) scale(${scale})`,
        }}
      >
        <SlideBody slide={slide} />
      </div>
    </div>
  )
}

function Overview({ deck, onSelect }: { deck: UiDeckBundle; onSelect: (index: number) => void }) {
  return (
    <ul className="m-0 grid list-none content-start gap-6 overflow-y-auto p-8 [grid-template-columns:repeat(auto-fill,minmax(280px,1fr))]">
      {deck.slides.map((slide, index) => (
        <li key={slide.id}>
          <button
            type="button"
            data-qid={`deck:overview:slide:${slide.id}`}
            data-qs-action="DECK_GOTO_SLIDE"
            title={`Go to slide ${slide.order}: ${slide.title}`}
            onClick={() => onSelect(index)}
            className="w-full cursor-pointer rounded-xl border border-slate-800 bg-slate-900 p-4 text-left transition-colors hover:border-cyan-500/60"
          >
            <span className="font-mono text-xs text-slate-500">#{slide.order} · {slide.layout}</span>
            <span className="mt-1 block text-sm font-medium text-slate-200">{slide.title}</span>
            <span className="mt-1 block truncate text-xs text-slate-400">{slide.message}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function EditPanel({
  edit,
  onClose,
  onSaved,
}: {
  edit: EditRequest
  onClose: () => void
  onSaved: () => void
}) {
  const [value, setValue] = useState(edit.value)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const response = await fetch('/api/slide-edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slide_id: edit.slideId, field: edit.field, value }),
      })
      const data = (await response.json()) as { error?: string }
      if (!response.ok) throw new Error(data.error ?? `edit failed (${response.status})`)
      onSaved()
      onClose()
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section
      aria-label={`Edit ${edit.label}`}
      className="border-t border-cyan-800/60 bg-slate-900/95 px-6 py-4"
    >
      <p className="m-0 mb-2 text-xs text-slate-400">
        Editing <span className="font-mono text-cyan-300">{edit.slideId}</span> · {edit.label}. Saving re-runs the
        fail-closed bundle validation; a rejected edit changes nothing.
      </p>
      <textarea
        data-qid="deck:edit:panel:value"
        title={`New text for ${edit.label}`}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        rows={3}
        className="w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-sm text-slate-100"
      />
      {error ? (
        <p role="alert" className="m-0 mt-2 rounded-lg border border-rose-500/50 bg-rose-500/10 p-2 text-xs text-rose-300">
          Rejected by validation: {error}
        </p>
      ) : null}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          data-qid="deck:edit:panel:save"
          data-qs-action="DECK_EDIT_SAVE"
          title="Save edit through bundle validation"
          disabled={saving || value === edit.value}
          onClick={() => void save()}
          className="cursor-pointer rounded-lg border border-cyan-600 bg-cyan-600/20 px-3 py-1.5 text-sm text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {saving ? 'Validating…' : 'Save'}
        </button>
        <button
          type="button"
          data-qid="deck:edit:panel:cancel"
          data-qs-action="DECK_EDIT_CANCEL"
          title="Cancel edit"
          onClick={onClose}
          className="cursor-pointer rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300"
        >
          Cancel
        </button>
      </div>
    </section>
  )
}

export function App() {
  const { deck, error, reload } = useDeck()
  const [index, setIndex] = useState(0)
  const [direction, setDirection] = useState<'fwd' | 'back'>('fwd')
  const [view, setView] = useState<View>(viewFromHash)
  const [showNotes, setShowNotes] = useState(false)
  const [editing, setEditing] = useState(false)
  const [pendingEdit, setPendingEdit] = useState<EditRequest | null>(null)

  useRegisterAction('deck:nav:prev', {
    app: 'readme-to-pitchdeck',
    action: 'DECK_PREV_SLIDE',
    label: 'Previous slide',
    description: 'Navigate to the previous slide in the presented deck',
  })
  useRegisterAction('deck:nav:next', {
    app: 'readme-to-pitchdeck',
    action: 'DECK_NEXT_SLIDE',
    label: 'Next slide',
    description: 'Navigate to the next slide in the presented deck',
  })

  const go = useCallback(
    (next: number) => {
      setDirection(next >= index ? 'fwd' : 'back')
      setIndex(next)
    },
    [index],
  )

  useEffect(() => {
    const onHash = () => setView(viewFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useKeyboardNav(deck?.slides.length ?? 0, index, go)

  if (error) {
    return (
      <main className="flex h-full items-center justify-center p-8 text-center">
        <p className="max-w-xl text-rose-300">
          Failed to load deck bundle: {error}. Run{' '}
          <code className="rounded bg-slate-800 px-1">./run.sh emit-ui --bundle-dir &lt;bundle&gt; --output-dir ui/public</code>{' '}
          first.
        </p>
      </main>
    )
  }
  if (!deck) return <main className="flex h-full items-center justify-center text-slate-500">Loading deck…</main>

  const slide = deck.slides[Math.min(index, deck.slides.length - 1)]
  const navButton =
    'inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 transition-colors hover:border-cyan-500/60 disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-slate-800 px-4 py-2">
        <div className="flex min-w-0 items-baseline gap-3">
          <h1 className="m-0 truncate text-sm font-semibold text-slate-200">{deck.title}</h1>
          <span
            className={`rounded px-1.5 py-0.5 font-mono text-xs ${deck.visibility === 'public' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}
          >
            {deck.visibility}
          </span>
          <span className="font-mono text-xs text-slate-500">{deck.validation_readiness}</span>
        </div>
        <nav aria-label="Deck views" className="flex items-center gap-2">
          <button
            type="button"
            data-qid="deck:view:overview"
            data-qs-action="DECK_TOGGLE_OVERVIEW"
            title="Toggle slide overview grid"
            aria-pressed={view === 'overview'}
            onClick={() => setView(view === 'overview' ? 'present' : 'overview')}
            className={navButton}
          >
            <LayoutGrid aria-hidden className="h-4 w-4" /> Overview
          </button>
          <button
            type="button"
            data-qid="deck:view:claims"
            data-qs-action="DECK_TOGGLE_CLAIM_REVIEW"
            title="Toggle claim-ledger review"
            aria-pressed={view === 'claims'}
            onClick={() => setView(view === 'claims' ? 'present' : 'claims')}
            className={navButton}
          >
            <ShieldCheck aria-hidden className="h-4 w-4" /> Claim review
          </button>
          <button
            type="button"
            data-qid="deck:view:edit"
            data-qs-action="DECK_TOGGLE_EDIT_MODE"
            title="Toggle edit mode — click any slide text to change it"
            aria-pressed={editing}
            onClick={() => {
              setEditing((value) => !value)
              setPendingEdit(null)
            }}
            className={`${navButton} ${editing ? 'border-cyan-500/80 text-cyan-200' : ''}`}
          >
            <Pencil aria-hidden className="h-4 w-4" /> Edit
          </button>
          <button
            type="button"
            data-qid="deck:view:notes"
            data-qs-action="DECK_TOGGLE_NOTES"
            title="Toggle speaker notes panel"
            aria-pressed={showNotes}
            onClick={() => setShowNotes((value) => !value)}
            className={navButton}
          >
            <NotebookText aria-hidden className="h-4 w-4" /> Notes
          </button>
        </nav>
      </header>

      {view === 'claims' ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_420px]">
          <ClaimReview deck={deck} />
          <aside aria-label="Claim review chat" className="min-h-0 overflow-hidden border-t border-slate-800 lg:border-l lg:border-t-0">
            <DeckChat deck={deck} />
          </aside>
        </div>
      ) : view === 'overview' ? (
        <Overview
          deck={deck}
          onSelect={(next) => {
            go(next)
            setView('present')
          }}
        />
      ) : (
        <main className="flex min-h-0 flex-1 flex-col">
          <EditContext.Provider value={{ editing, request: setPendingEdit }}>
            <SlideCanvas slide={slide} direction={direction} />
          </EditContext.Provider>
          {pendingEdit ? (
            <EditPanel edit={pendingEdit} onClose={() => setPendingEdit(null)} onSaved={reload} />
          ) : null}
          {showNotes ? (
            <aside aria-label="Speaker notes" className="border-t border-slate-800 px-6 py-3 text-sm text-slate-300">
              {slide.notes || <span className="text-slate-600">No speaker notes for this slide.</span>}
            </aside>
          ) : null}
          <footer className="flex items-center justify-between gap-4 border-t border-slate-800 px-4 py-2">
            <button
              type="button"
              data-qid="deck:nav:prev"
              data-qs-action="DECK_PREV_SLIDE"
              title="Previous slide"
              disabled={index === 0}
              onClick={() => go(index - 1)}
              className={navButton}
            >
              <ChevronLeft aria-hidden className="h-4 w-4" /> Prev
            </button>
            <span className="font-mono text-xs text-slate-500">
              {slide.order} / {deck.slides.length} · {slide.id}
            </span>
            <button
              type="button"
              data-qid="deck:nav:next"
              data-qs-action="DECK_NEXT_SLIDE"
              title="Next slide"
              disabled={index === deck.slides.length - 1}
              onClick={() => go(index + 1)}
              className={navButton}
            >
              Next <ChevronRight aria-hidden className="h-4 w-4" />
            </button>
          </footer>
        </main>
      )}
    </div>
  )
}
