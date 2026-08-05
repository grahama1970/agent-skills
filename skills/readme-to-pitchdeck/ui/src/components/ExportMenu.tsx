import { FileDown, FileText, Globe, MoreHorizontal, Presentation } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

// Keynote-pattern "…" system menu: export the CURRENT validated bundle as
// editable PPTX, rendered PDF, or Marp Markdown via /api/export (each runs
// the real build/render/emit pipeline server-side, gates included).

const FORMATS = [
  { format: 'pptx', label: 'Download PPTX (editable)', icon: Presentation, qid: 'deck:export:pptx', action: 'DECK_EXPORT_PPTX' },
  { format: 'pdf', label: 'Download PDF', icon: FileDown, qid: 'deck:export:pdf', action: 'DECK_EXPORT_PDF' },
  { format: 'html', label: 'Download interactive HTML', icon: Globe, qid: 'deck:export:html', action: 'DECK_EXPORT_HTML' },
  { format: 'md', label: 'Download Marp Markdown', icon: FileText, qid: 'deck:export:md', action: 'DECK_EXPORT_MD' },
] as const

export function ExportMenu() {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onClick)
    return () => window.removeEventListener('mousedown', onClick)
  }, [open])

  const download = async (format: string) => {
    setBusy(format)
    setError(null)
    try {
      const response = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format }),
      })
      const data = (await response.json()) as { url?: string; error?: string }
      if (!response.ok || !data.url) throw new Error(data.error ?? `export failed (${response.status})`)
      const anchor = document.createElement('a')
      anchor.href = data.url
      anchor.download = data.url.split('/').pop() ?? 'deck'
      anchor.click()
      setOpen(false)
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label="Export and more"
        aria-expanded={open}
        data-qid="deck:export:menu"
        data-qs-action="DECK_EXPORT_MENU"
        title="Export the deck (PPTX, PDF, Marp Markdown)"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex cursor-pointer items-center justify-center rounded-lg border border-transparent p-2 text-slate-300 transition-colors hover:border-slate-600 hover:text-cyan-300"
      >
        <MoreHorizontal aria-hidden className="h-5 w-5" />
      </button>
      {open ? (
        <div
          role="menu"
          aria-label="Export options"
          className="absolute right-0 top-full z-20 mt-1 w-64 rounded-xl border border-slate-700 bg-slate-900 p-1.5 shadow-2xl"
        >
          {FORMATS.map(({ format, label, icon: Icon, qid, action }) => (
            <button
              key={format}
              type="button"
              role="menuitem"
              data-qid={qid}
              data-qs-action={action}
              title={label}
              disabled={busy !== null}
              onClick={() => void download(format)}
              className="flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-slate-200 transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Icon aria-hidden className="h-4 w-4 text-cyan-300" />
              {busy === format ? 'Building…' : label}
            </button>
          ))}
          {error ? (
            <p role="alert" className="m-0 px-3 py-2 text-xs text-rose-300">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
