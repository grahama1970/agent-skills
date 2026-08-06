import { ChevronDown, ChevronUp, Maximize2, MessageSquare, Mic, Minimize2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { UiSlide } from '../types'

// Speaker-notes bottom drawer (user spec, adapted): edits save through the
// validated slide-edit pipeline on blur; live word/char counts; Ctrl+Shift+N
// toggle is bound in App. Height states: collapsed bar / normal / expanded.

export function NotesDrawer({
  slide,
  isOpen,
  onToggleOpen,
  onChanged,
}: {
  slide: UiSlide
  isOpen: boolean
  onToggleOpen: () => void
  onChanged: () => void
}) {
  const [notes, setNotes] = useState(slide.notes)
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [recording, setRecording] = useState(false)

  const record = async () => {
    setRecording(true)
    try {
      const response = await fetch('/api/record-note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slide_id: slide.id }),
      })
      const data = (await response.json()) as { status?: string; transcript?: string; reason?: string; error?: string }
      if (data.status === 'PASS') onChanged()
      else window.alert?.(data.reason ?? data.error ?? 'recording failed')
    } finally {
      setRecording(false)
    }
  }
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setNotes(slide.notes)
    setError(null)
  }, [slide])

  const save = async () => {
    if (notes === slide.notes) return
    setBusy(true)
    setError(null)
    try {
      const response = await fetch('/api/slide-edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slide_id: slide.id, field: 'notes', value: notes }),
      })
      if (!response.ok) {
        const data = (await response.json()) as { error?: string }
        throw new Error(data.error ?? `save failed (${response.status})`)
      }
      onChanged()
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err))
    } finally {
      setBusy(false)
    }
  }

  const wordCount = notes.trim() ? notes.trim().split(/\s+/).length : 0

  return (
    <section
      aria-label="Speaker notes drawer"
      className={`z-30 flex flex-col border-t border-slate-800 bg-slate-950/95 backdrop-blur-md transition-all duration-300 ease-in-out ${
        !isOpen ? 'h-9' : expanded ? 'h-64' : 'h-36'
      }`}
    >
      <button
        type="button"
        data-qid="deck:notes:toggle"
        data-qs-action="DECK_TOGGLE_NOTES"
        title="Toggle speaker notes (Ctrl+Shift+N)"
        aria-expanded={isOpen}
        onClick={onToggleOpen}
        className="flex h-9 flex-shrink-0 cursor-pointer items-center justify-between border-b border-slate-800/80 bg-slate-900/90 px-4 transition-colors hover:bg-slate-900"
      >
        <span className="flex items-center gap-2">
          <MessageSquare aria-hidden className={`h-3.5 w-3.5 ${isOpen ? 'text-cyan-400' : 'text-slate-400'}`} />
          <span className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-300">Speaker notes</span>
          <span className="max-w-56 truncate font-mono text-xs text-slate-500">{slide.title}</span>
        </span>
        <span className="flex items-center gap-3 text-xs text-slate-400">
          <span
            role="button"
            tabIndex={0}
            data-qid="deck:notes:record"
            data-qs-action="DECK_RECORD_NOTE"
            title={recording ? 'Listening — speak now; stops on silence' : 'Record narration into these notes (RealtimeSTT + faster-whisper, local)'}
            onClick={(event) => {
              event.stopPropagation()
              if (!recording) void record()
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !recording) void record()
            }}
            className={`inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 ${recording ? 'animate-pulse bg-rose-500/20 text-rose-300' : 'text-slate-400 hover:text-cyan-300'}`}
          >
            <Mic aria-hidden className="h-3.5 w-3.5" /> {recording ? 'listening…' : 'record'}
          </span>
          {isOpen ? (
            <span className="font-mono text-[11px] text-slate-500">
              {wordCount} words · {notes.length} chars{busy ? ' · validating…' : ''}
            </span>
          ) : null}
          {isOpen ? (
            <span
              role="button"
              tabIndex={0}
              data-qid="deck:notes:expand"
              data-qs-action="DECK_NOTES_EXPAND"
              title={expanded ? 'Collapse height' : 'Expand height'}
              onClick={(event) => {
                event.stopPropagation()
                setExpanded((value) => !value)
              }}
              className="cursor-pointer rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            >
              {expanded ? <Minimize2 aria-hidden className="h-3 w-3" /> : <Maximize2 aria-hidden className="h-3 w-3" />}
            </span>
          ) : null}
          <span className="font-sans text-[10px] text-slate-500">Ctrl+⇧N</span>
          {isOpen ? <ChevronDown aria-hidden className="h-3.5 w-3.5" /> : <ChevronUp aria-hidden className="h-3.5 w-3.5" />}
        </span>
      </button>
      {isOpen ? (
        <div className="flex min-h-0 flex-1 flex-col bg-slate-950/80 p-3">
          <textarea
            data-qid="deck:notes:editor"
            title="Speaker notes for this slide (saved through validation on blur)"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            onBlur={() => void save()}
            placeholder="Type speaker notes for presenter view…"
            className="w-full min-h-0 flex-1 resize-none bg-transparent font-sans text-sm leading-relaxed text-slate-200 outline-none placeholder:text-slate-600"
          />
          {error ? (
            <p role="alert" className="m-0 mt-1 rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-xs text-rose-300">
              Rejected by validation: {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
