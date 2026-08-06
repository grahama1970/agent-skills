import { Mic } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { UiSlide } from '../types'

// Speaker-notes panel for the RIGHT side sheet (3-pane spec: auxiliary tools —
// Chat & Notes — anchor exclusively to the right; the old bottom drawer
// invaded the canvas row). Edits save through the validated slide-edit
// pipeline on blur; narration records via RealtimeSTT + faster-whisper
// (local, no keys) and is APPENDED to notes by the compiler path.

export function NotesPanel({ slide, onChanged }: { slide: UiSlide; onChanged: () => void }) {
  const [notes, setNotes] = useState(slide.notes)
  const [busy, setBusy] = useState(false)
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setNotes(slide.notes)
    setError(null)
  }, [slide])

  const record = async () => {
    setRecording(true)
    try {
      const response = await fetch('/api/record-note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slide_id: slide.id }),
      })
      const data = (await response.json()) as { status?: string; reason?: string; error?: string }
      if (data.status === 'PASS') onChanged()
      else setError(data.reason ?? data.error ?? 'recording failed')
    } finally {
      setRecording(false)
    }
  }

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
    <section aria-label="Speaker notes" className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-800/80 px-3 py-2">
        <span className="max-w-44 truncate font-mono text-xs text-slate-500" title={slide.title}>
          {slide.title}
        </span>
        <span className="flex items-center gap-3 text-xs text-slate-400">
          <span
            role="button"
            tabIndex={0}
            data-qid="deck:notes:record"
            data-qs-action="DECK_RECORD_NOTE"
            title={recording ? 'Listening — speak now; stops on silence' : 'Record narration into these notes (RealtimeSTT + faster-whisper, local)'}
            onClick={() => {
              if (!recording) void record()
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !recording) void record()
            }}
            className={`inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-0.5 ${recording ? 'animate-pulse bg-rose-500/20 text-rose-300' : 'text-slate-400 hover:text-cyan-300'}`}
          >
            <Mic aria-hidden className="h-3.5 w-3.5" /> {recording ? 'listening…' : 'record'}
          </span>
          <span className="font-mono text-[11px] text-slate-500">
            {wordCount} words{busy ? ' · validating…' : ''}
          </span>
        </span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col p-3">
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
    </section>
  )
}
