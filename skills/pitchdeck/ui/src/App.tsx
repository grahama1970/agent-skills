import { ChevronLeft, ChevronRight, Columns3, Database, FileCode2, LayoutGrid, LayoutTemplate, Maximize2, MessageSquare, PanelLeft, PanelLeftOpen, PanelRight, PanelRightOpen, Play, ShieldCheck, StickyNote } from 'lucide-react'
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { ClaimReview } from './components/ClaimReview'
import { ChatDrawer } from './components/ChatDrawer'
import { DeckChat } from './components/DeckChat'
import { AssetDropZone } from './components/AssetDrop'
import { EditToolbar, postUndo } from './components/EditChrome'
import { SlideDrawer } from './components/SlideDrawer'
import { ExportMenu } from './components/ExportMenu'
import { NotesDrawer } from './components/NotesDrawer'
import { OverflowBadge } from './components/OverflowBadge'
import { PresenterOverlay } from './components/Presenter'
import { ShortcutsModal } from './components/ShortcutsModal'
import { ResizeHandle } from './components/ResizeHandle'
import { SourcePane } from './components/SourcePane'
import { Toasts, toast } from './components/Toasts'
import { Inspector } from './components/Inspector'
import { EditContext, type EditRequest } from './edit'
import { lintSlide } from './lib/pptxLint'
import { revisionStore, useDeck, useKeyboardNav, usePaneResize, useRegisterAction, useSlideScale } from './hooks'
import { useTopNavShortcuts } from './useTopNavShortcuts'
import { FragmentContext, SlideBody, fragmentCount } from './layouts/SlideLayouts'
import { CANVAS_HEIGHT, CANVAS_WIDTH, type UiDeckBundle, type UiSlide } from './types'

function usePersistentPane(key: string, initial: boolean): [boolean, React.Dispatch<React.SetStateAction<boolean>>] {
  const [value, setValue] = useState<boolean>(() => {
    try {
      const stored = window.localStorage.getItem(key)
      return stored === null ? initial : stored === 'true'
    } catch {
      return initial
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(key, String(value))
    } catch {
      /* storage unavailable — session-only state */
    }
  }, [key, value])
  return [value, setValue]
}

type View = 'present' | 'overview' | 'claims'

function viewFromHash(): View {
  const hash = window.location.hash.replace('#/', '')
  return hash === 'overview' || hash === 'claims' ? hash : 'present'
}

function SlideCanvas({ slide, direction, zoom }: { slide: UiSlide; direction: 'fwd' | 'back'; zoom: string }) {
  const { ref, scale: fitScale } = useSlideScale()
  const scale = zoom === 'fit' ? fitScale : (Number(zoom) / 100) * fitScale
  return (
    <div ref={ref} className="relative min-h-0 flex-1 overflow-hidden">
      <div
        className="absolute left-1/2 top-1/2 overflow-hidden rounded-lg bg-slate-950 shadow-2xl"
        style={{
          width: CANVAS_WIDTH,
          height: CANVAS_HEIGHT,
          transform: `translate(-50%, -50%) scale(${scale})`,
        }}
      >
        <div
          key={slide.id}
          className={`h-full w-full ${slide.transition === 'none' ? '' : `anim-${slide.transition}-${direction}`}`}
          style={{ '--deck-transition': `${slide.transition_duration_ms}ms` } as React.CSSProperties}
        >
          <SlideBody slide={slide} />
        </div>
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
        body: JSON.stringify({ slide_id: edit.slideId, field: edit.field, value, base_revision: revisionStore.current }),
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
  const [chatCollapsed, setChatCollapsed] = usePersistentPane('deck-pane-chat-collapsed', true)
  const [editing, setEditing] = useState(false)
  const [pendingEdit, setPendingEdit] = useState<EditRequest | null>(null)
  const [railCollapsed, setRailCollapsed] = usePersistentPane('deck-pane-rail-collapsed', false)
  const [zoom, setZoom] = useState('fit')
  const [showSource, setShowSource] = usePersistentPane('deck-pane-source', false)
  const [presenting, setPresenting] = useState(false)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [inspectorCollapsed, setInspectorCollapsed] = usePersistentPane('deck-pane-inspector-collapsed', false)
  const [sourceVersion, setSourceVersion] = useState(0)

  useRegisterAction('deck:nav:prev', {
    app: 'pitchdeck',
    action: 'DECK_PREV_SLIDE',
    label: 'Previous slide',
    description: 'Navigate to the previous slide in the presented deck',
  })
  useRegisterAction('deck:nav:next', {
    app: 'pitchdeck',
    action: 'DECK_NEXT_SLIDE',
    label: 'Next slide',
    description: 'Navigate to the next slide in the presented deck',
  })
  useRegisterAction('deck:view:chat', {
    app: 'pitchdeck',
    action: 'DECK_TOGGLE_CHAT',
    label: 'Toggle chat',
    description: 'Show or hide the conversational deck-edit pane (proposals preview via simulate)',
  })
  useRegisterAction('deck:toolbar:undo', {
    app: 'pitchdeck',
    action: 'DECK_UNDO',
    label: 'Undo',
    description: 'Restore the previous committed bundle state (undo of undo = redo)',
  })

  // Theme tokens (typed in DeckMeta.theme_tokens) → CSS vars consumed by the
  // slide layouts, so the browser and PPTX emitters share one accent source.
  useEffect(() => {
    if (!deck?.theme_tokens) return
    const root = document.documentElement.style
    root.setProperty('--deck-accent', deck.theme_tokens.accent)
    root.setProperty('--deck-heading-font', deck.theme_tokens.heading_font)
    root.setProperty('--deck-body-font', deck.theme_tokens.body_font)
  }, [deck])

  const [fragment, setFragment] = useState(0)
  const fragmentTotal = useRef(0)

  // Click-gated builds: forward advance consumes fragments before slides;
  // backward un-reveals before retreating. Only in Present (not editing).
  const go = useCallback(
    (next: number) => {
      if (!editing && fragmentTotal.current > 0) {
        if (next > index && fragment < fragmentTotal.current) {
          setFragment((value) => value + 1)
          return
        }
        if (next < index && fragment > 0) {
          setFragment((value) => value - 1)
          return
        }
      }
      setDirection(next >= index ? 'fwd' : 'back')
      setIndex(next)
      setFragment(0)
    },
    [index, editing, fragment],
  )

  useEffect(() => {
    const onHash = () => setView(viewFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const reloadAll = useCallback(() => {
    reload()
    setSourceVersion((value) => value + 1)
  }, [reload])

  const lastPaneState = useRef({ source: false, rail: true, inspector: true })
  const { widths, startResizing, resetWidth, activeResizer } = usePaneResize()

  const toggleFocusMode = useCallback(() => {
    const anyOpen = showSource || !railCollapsed || !inspectorCollapsed
    if (anyOpen) {
      lastPaneState.current = { source: showSource, rail: !railCollapsed, inspector: !inspectorCollapsed }
      setShowSource(false)
      setRailCollapsed(true)
      setInspectorCollapsed(true)
    } else {
      setShowSource(lastPaneState.current.source)
      setRailCollapsed(!lastPaneState.current.rail)
      setInspectorCollapsed(!lastPaneState.current.inspector)
    }
  }, [showSource, railCollapsed, inspectorCollapsed, setShowSource, setRailCollapsed, setInspectorCollapsed])

  // Shortcut matrix: Ctrl+\ source · Ctrl+B rail · Ctrl+Shift+I inspector · Ctrl+Shift+F focus
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey)) return
      if (event.key === '\\') {
        event.preventDefault()
        setShowSource((value) => !value)
      } else if (event.key.toLowerCase() === 'b' && !event.shiftKey && !event.altKey) {
        event.preventDefault()
        setRailCollapsed((value) => !value)
      } else if (event.key.toLowerCase() === 'i' && event.shiftKey) {
        event.preventDefault()
        setInspectorCollapsed((value) => !value)
      } else if (event.key.toLowerCase() === 'f' && event.shiftKey) {
        event.preventDefault()
        toggleFocusMode()
      } else if (event.key.toLowerCase() === 'n' && event.shiftKey) {
        event.preventDefault()
        setShowNotes((value) => !value)
      } else if (event.key === 'Enter') {
        event.preventDefault()
        setPresenting(true)
      } else if (event.key === '/') {
        event.preventDefault()
        setShowShortcuts((value) => !value)
      } else if (event.key.toLowerCase() === 'z' && !event.shiftKey && !event.altKey) {
        const target = event.target as HTMLElement
        const typing = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
        if (typing || !editing) return // native text undo wins while typing
        event.preventDefault()
        void postUndo().then((failure) => {
          if (failure) toast(`Undo failed: ${failure}`, 'error')
          else {
            toast('Undo applied')
            reloadAll()
          }
        })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleFocusMode, setShowSource, setRailCollapsed, setInspectorCollapsed, editing, reloadAll])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      const typing = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
      if (event.key === '?' && !typing && !event.metaKey && !event.ctrlKey) {
        event.preventDefault()
        setShowShortcuts((value) => !value)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (deck) {
      const navSlidesNow = editing ? deck.slides : deck.slides.filter((s) => !s.hidden)
      const current = navSlidesNow[Math.min(index, navSlidesNow.length - 1)]
      fragmentTotal.current = current ? fragmentCount(current) : 0
    }
  }, [deck, index, editing])

  useKeyboardNav(deck ? (editing ? deck.slides.length : deck.slides.filter((s) => !s.hidden).length) : 0, index, go)


  // Mode architecture (roundtable): Present | Design | Claims | Source as one
  // segmented control — derived from existing state, so deep panes still work.
  const mode: 'present' | 'design' | 'claims' | 'source' =
    view === 'claims' ? 'claims' : editing && showSource ? 'source' : editing ? 'design' : 'present'
  const setMode = (next: typeof mode) => {
    setPendingEdit(null)
    if (next === 'claims') {
      setView('claims')
      return
    }
    setView('present')
    setEditing(next !== 'present')
    setShowSource(next === 'source')
  }

  // Top-nav shortcuts (spec): mod+1..5 best-effort (Chrome reserves Ctrl+1..8),
  // single keys are the reliable tier; mod+j toggles chat. Focus-guarded.
  useTopNavShortcuts(
    {
      'mod+1': () => setMode('present'),
      'mod+2': () => setMode('design'),
      'mod+3': () => setMode('claims'),
      'mod+4': () => setMode('source'),
      'mod+5': () => setView((value) => (value === 'overview' ? 'present' : 'overview')),
      'mod+j': () => setChatCollapsed((value) => !value),
      p: () => setMode('present'),
      d: () => setMode('design'),
      c: () => setMode('claims'),
      s: () => setMode('source'),
      g: () => setView((value) => (value === 'overview' ? 'present' : 'overview')),
    },
    { enabled: !presenting },
  )


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

  const navSlides = editing ? deck.slides : deck.slides.filter((s) => !s.hidden)
  const slide = navSlides[Math.min(index, navSlides.length - 1)] ?? deck.slides[0]
  const navButton =
    'inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 transition-colors hover:border-cyan-500/60 disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <div className="flex h-full flex-col">
      {presenting ? (
        <PresenterOverlay slides={navSlides.filter((s) => !s.hidden)} initialIndex={index} onClose={() => setPresenting(false)} />
      ) : null}
      <ShortcutsModal isOpen={showShortcuts} onClose={() => setShowShortcuts(false)} />
      <Toasts />
      <header className="grid grid-cols-[1fr_auto_1fr] items-center gap-x-4 border-b border-slate-800 px-4 py-1.5">
        <div className="flex min-w-0 items-center gap-3">
          {editing ? (
            <>
              <button
                type="button"
                aria-label="Toggle slide navigator"
                aria-pressed={railCollapsed}
                data-qid="deck:toolbar:rail-toggle"
                data-qs-action="DECK_TOGGLE_RAIL"
                title="Show or hide the slide navigator"
                onClick={() => setRailCollapsed((value) => !value)}
                className={`inline-flex cursor-pointer items-center justify-center rounded-lg border border-transparent p-1.5 hover:border-slate-600 hover:text-cyan-300 ${railCollapsed ? 'text-slate-500' : 'text-cyan-300'}`}
              >
                <PanelLeft aria-hidden className="h-4 w-4" />
              </button>
              <button
                type="button"
                aria-label="Toggle deck source pane"
                aria-pressed={showSource}
                data-qid="deck:toolbar:source-toggle"
                data-qs-action="DECK_TOGGLE_SOURCE"
                title="Show or hide the YAML source pane (Ctrl+\\)"
                onClick={() => setShowSource((value) => !value)}
                className={`inline-flex cursor-pointer items-center justify-center rounded-lg border border-transparent p-1.5 hover:border-slate-600 hover:text-cyan-300 ${showSource ? 'text-cyan-300' : 'text-slate-300'}`}
              >
                <FileCode2 aria-hidden className="h-4 w-4" />
              </button>
              <button
                type="button"
                aria-label="Toggle inspector"
                aria-pressed={!inspectorCollapsed}
                data-qid="deck:toolbar:inspector-toggle"
                data-qs-action="DECK_TOGGLE_INSPECTOR"
                title="Show or hide the slide inspector"
                onClick={() => setInspectorCollapsed((value) => !value)}
                className={`inline-flex cursor-pointer items-center justify-center rounded-lg border border-transparent p-1.5 hover:border-slate-600 hover:text-cyan-300 ${inspectorCollapsed ? 'text-slate-500' : 'text-cyan-300'}`}
              >
                <PanelRight aria-hidden className="h-4 w-4" />
              </button>
              <select
                aria-label="Zoom"
                data-qid="deck:toolbar:zoom"
                data-qs-action="DECK_SET_ZOOM"
                title="Slide zoom"
                value={zoom}
                onChange={(event) => setZoom(event.target.value)}
                className="cursor-pointer rounded-lg border border-slate-700 bg-slate-900 px-1.5 py-1 text-xs text-slate-200"
              >
                <option value="fit">Fit</option>
                <option value="50">50%</option>
                <option value="75">75%</option>
                <option value="100">100%</option>
              </select>
            </>
          ) : null}
          <h1 className="m-0 truncate text-sm font-semibold text-slate-200">{deck.title}</h1>
          <span
            className={`rounded px-1.5 py-0.5 font-mono text-xs ${deck.visibility === 'public' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-rose-500/15 text-rose-300'}`}
          >
            {deck.visibility}
          </span>
          <span className="font-mono text-xs text-slate-500">{deck.validation_readiness}</span>
        </div>
        <div className="flex items-center justify-center">
          {editing ? (
            <EditToolbar
              slide={slide}
              slideCount={deck.slides.length}
              onChanged={reloadAll}
              onPresent={() => {
                setPendingEdit(null)
                setPresenting(true)
              }}
            />
          ) : null}
        </div>
        <nav aria-label="Deck views" className="flex items-center justify-end gap-1">
          <div
            role="radiogroup"
            aria-label="Deck mode"
            className="mr-1 inline-flex overflow-hidden rounded-lg border border-slate-700"
          >
            {(
              [
                ['present', 'Present', 'Read the deck as it will present', Play],
                ['design', 'Design', 'Edit slides — click any text to change it', LayoutTemplate],
                ['claims', 'Claims', 'Review the claim ledger and evidence bindings', ShieldCheck],
                ['source', 'Source', 'Edit the deck manifest YAML directly', Database],
              ] as const
            ).map(([id, label, hint, Icon], modeIndex) => (
              <React.Fragment key={id}>
              {modeIndex === 2 ? <span aria-hidden className="my-1 w-px self-stretch bg-slate-700" /> : null}
              <button
                type="button"
                role="radio"
                aria-checked={mode === id}
                aria-label={label}
                data-qid={`deck:mode:${id}`}
                data-qs-action={`DECK_MODE_${id.toUpperCase()}`}
                title={hint}
                onClick={() => setMode(id)}
                className={`inline-flex cursor-pointer items-center gap-1.5 px-3 py-1.5 text-sm transition-colors ${
                  mode === id ? 'bg-cyan-600/25 text-cyan-200' : 'bg-slate-900 text-slate-300 hover:text-cyan-300'
                }`}
              >
                <Icon aria-hidden className="h-4 w-4" />
                <span className="hidden lg:inline">{label}</span>
              </button>
              </React.Fragment>
            ))}
          </div>
          <button
            type="button"
            data-qid="deck:view:overview"
            data-qs-action="DECK_TOGGLE_OVERVIEW"
            title="Toggle slide overview grid"
            aria-pressed={view === 'overview'}
            onClick={() => setView(view === 'overview' ? 'present' : 'overview')}
            className={navButton}
          >
            <LayoutGrid aria-hidden className="h-4 w-4" /> <span className="hidden lg:inline">Overview</span>
          </button>
          <span aria-hidden className="mx-1 h-5 w-px bg-slate-700" />
          <button
            type="button"
            data-qid="deck:view:chat"
            data-qs-action="DECK_TOGGLE_CHAT"
            title="Toggle the deck chat pane - propose edits conversationally"
            aria-pressed={!chatCollapsed}
            onClick={() => setChatCollapsed((value) => !value)}
            className={`${navButton} ${!chatCollapsed ? 'border-cyan-500/80 text-cyan-200' : ''}`}
          >
            <MessageSquare aria-hidden className="h-4 w-4" /> <span className="hidden lg:inline">Chat</span>
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
            <StickyNote aria-hidden className="h-4 w-4" /> <span className="hidden lg:inline">Notes</span>
          </button>
          <ExportMenu />
        </nav>
      </header>

      {view === 'claims' ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_420px]">
          <ClaimReview deck={deck} onChanged={reloadAll} />
          <aside aria-label="Claim review chat" className="min-h-0 overflow-hidden border-t border-slate-800 lg:border-l lg:border-t-0">
            <DeckChat deck={deck} onChanged={reloadAll} />
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
          <div className="relative flex min-h-0 flex-1">
            {editing && showSource ? (
              <>
                <SourcePane version={sourceVersion} onSaved={reloadAll} onClose={() => setShowSource(false)} width={widths.source} />
                <ResizeHandle pane="source" isDragging={activeResizer === 'source'} onMouseDown={(e) => startResizing('source', e)} onDoubleClick={() => resetWidth('source')} />
              </>
            ) : null}
            {editing && !railCollapsed ? (
              <>
                <SlideDrawer deck={deck} currentIndex={index} onSelect={go} width={widths.rail} onChanged={reloadAll} />
                <ResizeHandle pane="rail" isDragging={activeResizer === 'rail'} onMouseDown={(e) => startResizing('rail', e)} onDoubleClick={() => resetWidth('rail')} />
              </>
            ) : null}
            {editing ? <OverflowBadge warnings={lintSlide(slide)} /> : null}
            {editing && (!showSource || railCollapsed) ? (
              <div className="absolute left-3 top-3 z-30 flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 p-1 backdrop-blur">
                {!showSource ? (
                  <button
                    type="button"
                    aria-label="Expand source pane"
                    data-qid="deck:restore:source"
                    data-qs-action="DECK_RESTORE_SOURCE"
                    title="Expand source pane (Ctrl+\\)"
                    onClick={() => setShowSource(true)}
                    className="cursor-pointer rounded p-1.5 text-slate-300 hover:bg-slate-700"
                  >
                    <PanelLeftOpen aria-hidden className="h-4 w-4" />
                  </button>
                ) : null}
                {railCollapsed ? (
                  <button
                    type="button"
                    aria-label="Expand slide navigation"
                    data-qid="deck:restore:rail"
                    data-qs-action="DECK_RESTORE_RAIL"
                    title="Expand slide navigation (Ctrl+B)"
                    onClick={() => setRailCollapsed(false)}
                    className="cursor-pointer rounded p-1.5 text-slate-300 hover:bg-slate-700"
                  >
                    <Columns3 aria-hidden className="h-4 w-4" />
                  </button>
                ) : null}
              </div>
            ) : null}
            {editing ? (
              <div className="absolute right-3 top-3 z-30 flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 p-1 backdrop-blur">
                <button
                  type="button"
                  aria-label="Toggle focus mode"
                  data-qid="deck:restore:focus"
                  data-qs-action="DECK_FOCUS_MODE"
                  title="Focus mode — collapse or restore all panes (Ctrl+Shift+F)"
                  onClick={toggleFocusMode}
                  className="cursor-pointer rounded p-1.5 text-slate-300 hover:bg-slate-700"
                >
                  <Maximize2 aria-hidden className="h-4 w-4" />
                </button>
                {inspectorCollapsed ? (
                  <button
                    type="button"
                    aria-label="Expand inspector"
                    data-qid="deck:restore:inspector"
                    data-qs-action="DECK_RESTORE_INSPECTOR"
                    title="Expand inspector (Ctrl+Shift+I)"
                    onClick={() => setInspectorCollapsed(false)}
                    className="cursor-pointer rounded p-1.5 text-slate-300 hover:bg-slate-700"
                  >
                    <PanelRightOpen aria-hidden className="h-4 w-4" />
                  </button>
                ) : null}
              </div>
            ) : null}
            <AssetDropZone slide={slide} enabled={editing} onChanged={reloadAll}>
              <EditContext.Provider value={{ editing, request: setPendingEdit, refresh: reloadAll }}>
                <FragmentContext.Provider value={editing ? Infinity : fragment}>
                  <SlideCanvas slide={slide} direction={direction} zoom={editing ? zoom : 'fit'} />
                </FragmentContext.Provider>
              </EditContext.Provider>
            </AssetDropZone>
            {!presenting ? (
              <ChatDrawer collapsed={chatCollapsed} onCollapse={() => setChatCollapsed(true)}>
                <DeckChat deck={deck} onChanged={reloadAll} />
              </ChatDrawer>
            ) : null}
            {editing && !inspectorCollapsed ? (
              <>
                <ResizeHandle pane="inspector" isDragging={activeResizer === 'inspector'} onMouseDown={(e) => startResizing('inspector', e)} onDoubleClick={() => resetWidth('inspector')} />
                <Inspector slide={slide} onChanged={reloadAll} onCollapse={() => setInspectorCollapsed(true)} width={widths.inspector} />
              </>
            ) : null}
          </div>
          {pendingEdit ? (
            <EditPanel edit={pendingEdit} onClose={() => setPendingEdit(null)} onSaved={reloadAll} />
          ) : null}
          <NotesDrawer slide={slide} isOpen={showNotes} onToggleOpen={() => setShowNotes((value) => !value)} onChanged={reloadAll} />
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
              {slide.order} / {navSlides.length} · {slide.id}{slide.hidden ? ' · hidden' : ''}
            </span>
            <button
              type="button"
              data-qid="deck:nav:next"
              data-qs-action="DECK_NEXT_SLIDE"
              title="Next slide"
              disabled={index === navSlides.length - 1}
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
