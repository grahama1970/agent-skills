import { ChevronLeft, ChevronRight, Clock, Database, ExternalLink, FastForward, Minimize2, MessageSquare, Monitor, Pause, Play, Repeat, RotateCcw, ShieldAlert, ShieldCheck, ShieldQuestion, Type, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { SlideBody } from '../layouts/SlideLayouts'
import { CANVAS_HEIGHT, CANVAS_WIDTH, type UiSlide } from '../types'

// Presenter view (user spec, adapted): REAL slide renders (SlideBody scaled)
// for current and next slide, elapsed timer + wall clock, speaker notes with
// adjustable type size, keyboard nav, and optional pop-out window rendered
// through a portal with cloned stylesheets.

function usePresenterTimer() {
  const [elapsed, setElapsed] = useState(0)
  const [running, setRunning] = useState(true)
  const [wallClock, setWallClock] = useState('')
  useEffect(() => {
    const tick = () => setWallClock(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setElapsed((value) => value + 1), 1000)
    return () => clearInterval(id)
  }, [running])
  const pad = (n: number) => String(n).padStart(2, '0')
  const hrs = Math.floor(elapsed / 3600)
  const formatted = `${hrs > 0 ? `${pad(hrs)}:` : ''}${pad(Math.floor((elapsed % 3600) / 60))}:${pad(elapsed % 60)}`
  return { formatted, wallClock, running, toggle: () => setRunning((v) => !v), reset: () => setElapsed(0) }
}

function ScaledSlide({ slide }: { slide: UiSlide }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [scale, setScale] = useState(0.1)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(() => {
      const rect = el.getBoundingClientRect()
      setScale(Math.min(rect.width / CANVAS_WIDTH, rect.height / CANVAS_HEIGHT))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return (
    <div ref={ref} className="relative h-full w-full overflow-hidden">
      <div
        aria-hidden
        className="absolute left-1/2 top-1/2 overflow-hidden rounded-lg bg-slate-950"
        style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: `translate(-50%, -50%) scale(${scale})` }}
      >
        <SlideBody slide={slide} />
      </div>
    </div>
  )
}

function PopoutWindow({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null)
  const windowRef = useRef<Window | null>(null)
  useEffect(() => {
    const external = window.open('', '_blank', 'width=1280,height=720,resizable=yes')
    if (!external) {
      onClose()
      return
    }
    windowRef.current = external
    external.document.title = 'Presenter View — readme-to-pitchdeck'
    for (const sheet of Array.from(document.styleSheets)) {
      try {
        if (sheet.cssRules) {
          const style = external.document.createElement('style')
          style.textContent = Array.from(sheet.cssRules)
            .map((rule) => rule.cssText)
            .join('\n')
          external.document.head.appendChild(style)
        }
      } catch {
        if (sheet.href) {
          const link = external.document.createElement('link')
          link.rel = 'stylesheet'
          link.href = sheet.href
          external.document.head.appendChild(link)
        }
      }
    }
    external.document.body.className = 'bg-slate-950 text-slate-100 m-0 p-0 overflow-hidden'
    const root = external.document.createElement('div')
    root.style.height = '100vh'
    external.document.body.appendChild(root)
    setContainer(root)
    external.addEventListener('beforeunload', onClose)
    return () => {
      external.removeEventListener('beforeunload', onClose)
      external.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  if (!container) return null
  return createPortal(children, container)
}

const INTERVALS = [3, 5, 10, 15, 30]

function useAutoAdvance(total: number, index: number, onNext: () => void, onFirst: () => void) {
  const [playing, setPlaying] = useState(false)
  const [interval, setIntervalSeconds] = useState(5)
  const [loop, setLoop] = useState(true)
  const [progress, setProgress] = useState(0)
  const frame = useRef<number | null>(null)
  const last = useRef<number | null>(null)
  const elapsed = useRef(0)

  useEffect(() => {
    elapsed.current = 0
    setProgress(0)
    last.current = null
  }, [index])

  useEffect(() => {
    if (!playing) {
      if (frame.current) cancelAnimationFrame(frame.current)
      last.current = null
      return
    }
    const target = interval * 1000
    const step = (now: number) => {
      if (last.current !== null) {
        elapsed.current += now - last.current
        setProgress(Math.min((elapsed.current / target) * 100, 100))
        if (elapsed.current >= target) {
          elapsed.current = 0
          setProgress(0)
          if (index < total - 1) onNext()
          else if (loop) onFirst()
          else setPlaying(false)
        }
      }
      last.current = now
      frame.current = requestAnimationFrame(step)
    }
    frame.current = requestAnimationFrame(step)
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current)
    }
  }, [playing, interval, index, total, loop, onNext, onFirst])

  return { playing, interval, loop, progress, setIntervalSeconds, togglePlay: () => setPlaying((v) => !v), toggleLoop: () => setLoop((v) => !v) }
}

const NOTE_SIZES = ['sm', 'base', 'lg', 'xl'] as const
const NOTE_CLASSES: Record<(typeof NOTE_SIZES)[number], string> = {
  sm: 'text-sm leading-relaxed',
  base: 'text-base leading-relaxed',
  lg: 'text-lg leading-relaxed',
  xl: 'text-xl leading-relaxed font-medium',
}

export function PresenterOverlay({
  slides,
  initialIndex,
  onClose,
}: {
  slides: UiSlide[]
  initialIndex: number
  onClose: () => void
}) {
  const [index, setIndex] = useState(Math.min(initialIndex, slides.length - 1))
  const [noteSize, setNoteSize] = useState<(typeof NOTE_SIZES)[number]>('lg')
  const [poppedOut, setPoppedOut] = useState(false)
  const [showEvidence, setShowEvidence] = useState(false)
  const timer = usePresenterTimer()

  const next = useCallback(() => setIndex((value) => Math.min(value + 1, slides.length - 1)), [slides.length])
  const prev = useCallback(() => setIndex((value) => Math.max(value - 1, 0)), [])
  const first = useCallback(() => setIndex(0), [])
  const auto = useAutoAdvance(slides.length, index, next, first)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      } else if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === ' ') {
        event.preventDefault()
        next()
      } else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
        event.preventDefault()
        prev()
      } else if (event.key.toLowerCase() === 'e') {
        setShowEvidence((value) => !value)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, prev, onClose])

  const slide = slides[index]
  const upNext = slides[index + 1]

  const body = (
    <div className="flex h-full w-full select-none flex-col overflow-hidden bg-slate-950 text-slate-100">
      <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900 px-6">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-2 font-mono text-xs font-semibold text-cyan-400">
            <Monitor aria-hidden className="h-4 w-4" /> PRESENTER VIEW{poppedOut ? ' (POPPED OUT)' : ''}
          </span>
          <span className="h-4 w-px bg-slate-800" aria-hidden />
          <span className="font-mono text-xs text-slate-400">
            Slide <strong className="text-slate-100">{index + 1}</strong> of {slides.length}
          </span>
        </div>
        <div className="flex items-center gap-6 rounded-lg border border-slate-800 bg-slate-950 px-4 py-1.5">
          <span className="flex items-center gap-2 font-mono text-sm">
            <Clock aria-hidden className="h-3.5 w-3.5 text-amber-400" />
            <span className="w-16 font-bold text-amber-200">{timer.formatted}</span>
            <button
              type="button"
              data-qid="deck:presenter:timer-toggle"
              data-qs-action="DECK_PRESENTER_TIMER_TOGGLE"
              title={timer.running ? 'Pause timer' : 'Start timer'}
              onClick={timer.toggle}
              className="cursor-pointer rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            >
              {timer.running ? <Pause aria-hidden className="h-3 w-3" /> : <Play aria-hidden className="h-3 w-3" />}
            </button>
            <button
              type="button"
              data-qid="deck:presenter:timer-reset"
              data-qs-action="DECK_PRESENTER_TIMER_RESET"
              title="Reset timer"
              onClick={timer.reset}
              className="cursor-pointer rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            >
              <RotateCcw aria-hidden className="h-3 w-3" />
            </button>
          </span>
          <span className="h-4 w-px bg-slate-800" aria-hidden />
          <span className="font-mono text-xs font-semibold text-slate-200">{timer.wallClock}</span>
        </div>
        <div className="flex flex-col gap-1 rounded-lg border border-slate-800 bg-slate-950 p-1.5 font-mono text-xs">
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-qid="deck:presenter:autoplay"
              data-qs-action="DECK_PRESENTER_AUTOPLAY"
              title={auto.playing ? 'Pause auto-advance' : 'Start auto-advance'}
              aria-pressed={auto.playing}
              onClick={auto.togglePlay}
              className={`flex cursor-pointer items-center gap-1 rounded px-2 py-0.5 font-semibold ${auto.playing ? 'border border-amber-500/40 bg-amber-500/20 text-amber-300' : 'border border-cyan-500/40 bg-cyan-500/20 text-cyan-300'}`}
            >
              {auto.playing ? <Pause aria-hidden className="h-3 w-3" /> : <Play aria-hidden className="h-3 w-3" />}
              Auto
            </button>
            <FastForward aria-hidden className="h-3 w-3 text-slate-500" />
            {INTERVALS.map((seconds) => (
              <button
                key={seconds}
                type="button"
                data-qid={`deck:presenter:interval:${seconds}`}
                data-qs-action="DECK_PRESENTER_INTERVAL"
                title={`Advance every ${seconds} seconds`}
                aria-pressed={auto.interval === seconds}
                onClick={() => auto.setIntervalSeconds(seconds)}
                className={`cursor-pointer rounded px-1.5 py-0.5 text-[10px] ${auto.interval === seconds ? 'border border-slate-600 bg-slate-700 font-bold text-slate-100' : 'text-slate-400 hover:bg-slate-800'}`}
              >
                {seconds}s
              </button>
            ))}
            <button
              type="button"
              data-qid="deck:presenter:loop"
              data-qs-action="DECK_PRESENTER_LOOP"
              title={auto.loop ? 'Loop enabled' : 'Loop disabled'}
              aria-pressed={auto.loop}
              onClick={auto.toggleLoop}
              className={`cursor-pointer rounded p-1 ${auto.loop ? 'border border-emerald-500/30 bg-emerald-500/20 text-emerald-400' : 'text-slate-500 hover:bg-slate-800'}`}
            >
              <Repeat aria-hidden className="h-3 w-3" />
            </button>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-slate-800">
            <div style={{ width: `${auto.playing ? auto.progress : 0}%` }} className="h-full rounded-full bg-cyan-400 transition-[width] duration-75 ease-linear" />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 rounded-md border border-slate-800 bg-slate-950 p-1 text-xs">
            <Type aria-hidden className="mx-1 h-3 w-3 text-slate-500" />
            {NOTE_SIZES.map((size) => (
              <button
                key={size}
                type="button"
                data-qid={`deck:presenter:notesize:${size}`}
                data-qs-action="DECK_PRESENTER_NOTE_SIZE"
                title={`Notes text size ${size}`}
                aria-pressed={noteSize === size}
                onClick={() => setNoteSize(size)}
                className={`cursor-pointer rounded px-2 py-0.5 font-mono text-[10px] uppercase ${
                  noteSize === size ? 'bg-cyan-500/20 font-bold text-cyan-400' : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                {size}
              </button>
            ))}
          </span>
          <button
            type="button"
            data-qid="deck:presenter:evidence"
            data-qs-action="DECK_PRESENTER_EVIDENCE"
            title="Toggle claim evidence drawer (E)"
            aria-pressed={showEvidence}
            onClick={() => setShowEvidence((value) => !value)}
            className={`flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium ${showEvidence ? 'border-cyan-600 bg-cyan-600/20 text-cyan-200' : 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700'}`}
          >
            <Database aria-hidden className="h-3 w-3" /> Evidence
          </button>
          <button
            type="button"
            data-qid="deck:presenter:popout"
            data-qs-action="DECK_PRESENTER_POPOUT"
            title={poppedOut ? 'Embed back into main window' : 'Pop out into a separate window'}
            onClick={() => setPoppedOut((value) => !value)}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
          >
            {poppedOut ? <Minimize2 aria-hidden className="h-3 w-3" /> : <ExternalLink aria-hidden className="h-3 w-3" />}
            {poppedOut ? 'Embed' : 'Pop out'}
          </button>
          <button
            type="button"
            data-qid="deck:presenter:exit"
            data-qs-action="DECK_PRESENTER_EXIT"
            title="Exit presenter view (Esc)"
            onClick={onClose}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-400 hover:bg-rose-500/20"
          >
            <X aria-hidden className="h-3.5 w-3.5" /> Exit
          </button>
        </div>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-12 gap-6 overflow-hidden p-6">
        <div className="col-span-7 flex min-h-0 flex-col gap-4 overflow-hidden">
          <div className="relative min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-800 bg-slate-900 p-3 shadow-2xl">
            <ScaledSlide slide={slide} />
          </div>
          <div className="flex h-32 flex-shrink-0 gap-4">
            <div className="flex w-1/3 flex-col justify-between rounded-xl border border-slate-800 bg-slate-900 p-3">
              <span className="font-mono text-[10px] font-semibold uppercase text-slate-500">Slide controls</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  data-qid="deck:presenter:prev"
                  data-qs-action="DECK_PRESENTER_PREV"
                  title="Previous slide (←)"
                  disabled={index === 0}
                  onClick={prev}
                  className="flex flex-1 cursor-pointer items-center justify-center rounded-lg bg-slate-800 py-3 text-slate-200 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <ChevronLeft aria-hidden className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  data-qid="deck:presenter:next"
                  data-qs-action="DECK_PRESENTER_NEXT"
                  title="Next slide (→ / Space)"
                  disabled={index === slides.length - 1}
                  onClick={next}
                  className="flex flex-1 cursor-pointer items-center justify-center rounded-lg bg-cyan-700 py-3 text-white hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-30"
                >
                  <ChevronRight aria-hidden className="h-5 w-5" />
                </button>
              </div>
            </div>
            <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-slate-800 bg-slate-900 p-3">
              <span className="font-mono text-[10px] font-semibold uppercase text-slate-500">Up next</span>
              {upNext ? (
                <div className="relative mt-1 min-h-0 flex-1 overflow-hidden rounded border border-slate-800/80 bg-slate-950">
                  <ScaledSlide slide={upNext} />
                </div>
              ) : (
                <p className="m-auto text-xs italic text-slate-600">End of presentation deck</p>
              )}
            </div>
          </div>
        </div>
        <div className="col-span-5 flex min-h-0 flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-xl">
          <span className="mb-4 flex items-center gap-2 border-b border-slate-800 pb-3 font-mono text-xs font-semibold uppercase tracking-wider text-slate-300">
            <MessageSquare aria-hidden className="h-4 w-4 text-cyan-400" /> Speaker notes
          </span>
          <div className="min-h-0 flex-1 overflow-y-auto pr-2">
            {slide.notes ? (
              <p className={`m-0 whitespace-pre-wrap text-slate-200 ${NOTE_CLASSES[noteSize]}`}>{slide.notes}</p>
            ) : (
              <p className="m-auto flex h-full items-center justify-center text-xs italic text-slate-600">
                No speaker notes for this slide.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )

  const evidenceDrawer = showEvidence ? (
    <aside
      aria-label="Presenter claim evidence"
      className="fixed bottom-0 right-0 top-14 z-50 flex w-80 flex-col border-l border-slate-800 bg-slate-950 p-4 shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <span className="flex items-center gap-2 font-mono text-xs font-semibold uppercase text-cyan-400">
          <Database aria-hidden className="h-3.5 w-3.5" /> Claim evidence
        </span>
        <button
          type="button"
          data-qid="deck:presenter:evidence-close"
          data-qs-action="DECK_PRESENTER_EVIDENCE_CLOSE"
          title="Close evidence drawer"
          onClick={() => setShowEvidence(false)}
          className="cursor-pointer rounded p-1 text-slate-400 hover:text-slate-100"
        >
          <X aria-hidden className="h-4 w-4" />
        </button>
      </div>
      <p className="m-0 my-2 truncate text-xs font-bold text-slate-200">{slide.title}</p>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {slide.claims.length === 0 ? (
          <p className="text-xs italic text-slate-500">No ledger claims bound to this slide.</p>
        ) : (
          slide.claims.map((claim) => {
            const Icon = claim.status === 'approved' ? ShieldCheck : claim.status === 'candidate' ? ShieldQuestion : ShieldAlert
            const border =
              claim.status === 'approved' ? 'border-emerald-500/30' : claim.status === 'candidate' ? 'border-amber-500/30' : 'border-rose-500/30'
            const text =
              claim.status === 'approved' ? 'text-emerald-300' : claim.status === 'candidate' ? 'text-amber-300' : 'text-rose-300'
            return (
              <div key={claim.id} className={`space-y-1.5 rounded-lg border bg-slate-900 p-3 ${border}`}>
                <span className={`flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase ${text}`}>
                  <Icon aria-hidden className="h-3 w-3" /> {claim.status} · risk {claim.risk}
                </span>
                <p className="m-0 text-xs leading-relaxed text-slate-200">{claim.text}</p>
                {claim.required_qualifier ? (
                  <p className="m-0 text-[11px] leading-snug text-amber-200/90">Qualifier: {claim.required_qualifier}</p>
                ) : null}
                <p className="m-0 font-mono text-[10px] text-slate-500">{claim.id}</p>
              </div>
            )
          })
        )}
        {slide.source_ids.length ? (
          <p className="m-0 flex items-center gap-1 font-mono text-[10px] text-slate-500">
            <ExternalLink aria-hidden className="h-3 w-3" /> sources: {slide.source_ids.join(', ')}
          </p>
        ) : null}
      </div>
    </aside>
  ) : null

  if (poppedOut) {
    return (
      <>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/95 text-sm text-slate-400">
          Presenter view is running in a separate window.
        </div>
        <PopoutWindow onClose={onClose}>{body}</PopoutWindow>
      </>
    )
  }
  return (
    <div className="fixed inset-0 z-50">
      {body}
      {evidenceDrawer}
    </div>
  )
}
