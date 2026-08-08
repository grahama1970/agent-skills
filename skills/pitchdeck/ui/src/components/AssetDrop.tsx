import { ImagePlus } from 'lucide-react'
import { useState, type DragEvent, type ReactNode } from 'react'
import type { UiSlide } from '../types'
// Direct import, never a barrel file (best-practices-react).
import { Button } from './ui/button'

// Drag-and-drop asset attach for the current slide (edit mode). The dropped
// file goes through /api/asset-drop → asset-add: copied into the bundle,
// registered in asset_manifest.yaml with required alt text, bound as the
// slide visual, and validated fail-closed before anything is written.

interface PendingDrop {
  file: File
  slideId: string
}

export function AssetDropZone({
  slide,
  enabled,
  onChanged,
  children,
}: {
  slide: UiSlide
  enabled: boolean
  onChanged: () => void
  children: ReactNode
}) {
  const [dragging, setDragging] = useState(false)
  const [pending, setPending] = useState<PendingDrop | null>(null)
  const [alt, setAlt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!enabled) return <>{children}</>

  const onDrop = (event: DragEvent) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (!file) return
    setPending({ file, slideId: slide.id })
    setAlt('')
    setError(null)
  }

  const upload = async () => {
    if (!pending) return
    setBusy(true)
    setError(null)
    try {
      const buffer = await pending.file.arrayBuffer()
      let binary = ''
      const bytes = new Uint8Array(buffer)
      const chunk = 0x8000
      for (let i = 0; i < bytes.length; i += chunk) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunk))
      }
      const response = await fetch('/api/asset-drop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slide_id: pending.slideId,
          filename: pending.file.name,
          alt,
          data_b64: btoa(binary),
        }),
      })
      const data = (await response.json()) as { error?: string }
      if (!response.ok) throw new Error(data.error ?? `upload failed (${response.status})`)
      setPending(null)
      onChanged()
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="relative flex min-h-0 flex-1"
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      {children}
      {dragging ? (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-2 z-10 flex items-center justify-center rounded-2xl border-2 border-dashed border-cyan-400/80 bg-cyan-500/10"
        >
          <p className="flex items-center gap-2 rounded-xl bg-slate-900/90 px-4 py-2 text-sm text-cyan-200">
            <ImagePlus aria-hidden className="h-4 w-4" /> Drop image or video onto slide {slide.order}
          </p>
        </div>
      ) : null}
      {pending ? (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/70">
          <section
            aria-label="Describe dropped asset"
            className="w-96 rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl"
          >
            <h2 className="m-0 text-sm font-semibold text-slate-200">
              Attach {pending.file.name} to slide {slide.order}
            </h2>
            <label className="mt-3 block text-xs text-slate-400" htmlFor="asset-drop-alt">
              Alt text (required — travels into the manifest and PPTX)
            </label>
            <input
              id="asset-drop-alt"
              data-qid="deck:asset-drop:alt"
              title="Alt text for the dropped asset"
              value={alt}
              onChange={(event) => setAlt(event.target.value)}
              placeholder="What does this show?"
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm text-slate-100"
            />
            {error ? (
              <p role="alert" className="m-0 mt-2 rounded-lg border border-rose-500/50 bg-rose-500/10 p-2 text-xs text-rose-300">
                Rejected: {error}
              </p>
            ) : null}
            <div className="mt-3 flex gap-2">
              <Button
                type="button"
                data-qid="deck:asset-drop:attach"
                data-qs-action="DECK_ASSET_ATTACH"
                title="Attach asset through bundle validation"
                disabled={busy || !alt.trim()}
                onClick={() => void upload()}
                className="cursor-pointer rounded-lg border border-cyan-600 bg-cyan-600/20 px-3 py-1.5 text-sm text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy ? 'Validating…' : 'Attach'}
              </Button>
              <Button
                type="button"
                data-qid="deck:asset-drop:cancel"
                data-qs-action="DECK_ASSET_CANCEL"
                title="Cancel asset attach"
                onClick={() => setPending(null)}
                className="cursor-pointer rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300"
              >
                Cancel
              </Button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}
