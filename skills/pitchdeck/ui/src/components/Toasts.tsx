import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
// Direct import, never a barrel file (best-practices-react).
import { Button } from './ui/button'

// Minimal toast bus (Gemini spec, adapted): toast() dispatches a DOM event so
// any module can raise one without prop drilling; the container renders them
// bottom-right with auto-dismiss. Errors persist longer than info toasts.

export type ToastKind = 'info' | 'error'
interface ToastRecord {
  id: number
  kind: ToastKind
  message: string
}

const EVENT = 'deck:toast'
let nextId = 1

export function toast(message: string, kind: ToastKind = 'info'): void {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { message, kind } }))
}

export function Toasts() {
  const [items, setItems] = useState<ToastRecord[]>([])

  useEffect(() => {
    const onToast = (event: Event) => {
      const { message, kind } = (event as CustomEvent<{ message: string; kind: ToastKind }>).detail
      const id = nextId++
      setItems((prev) => [...prev.slice(-4), { id, kind, message }])
      window.setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), kind === 'error' ? 8000 : 3500)
    }
    window.addEventListener(EVENT, onToast)
    return () => window.removeEventListener(EVENT, onToast)
  }, [])

  if (!items.length) return null
  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[70] flex flex-col gap-2">
      {items.map((item) => (
        <div
          key={item.id}
          role={item.kind === 'error' ? 'alert' : 'status'}
          data-qid={`deck:toast:${item.kind}`}
          className={`pointer-events-auto flex max-w-md items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-xl backdrop-blur ${
            item.kind === 'error'
              ? 'border-rose-500/60 bg-rose-950/90 text-rose-200'
              : 'border-slate-700 bg-slate-900/95 text-slate-200'
          }`}
        >
          <span className="min-w-0 flex-1 break-words">{item.message}</span>
          <Button
            type="button"
            data-qid={`deck:toast:dismiss:${item.id}`}
            data-qs-action="DECK_TOAST_DISMISS"
            title="Dismiss notification"
            onClick={() => setItems((prev) => prev.filter((t) => t.id !== item.id))}
            className="cursor-pointer rounded p-0.5 opacity-70 hover:opacity-100"
          >
            <X aria-hidden className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
    </div>
  )
}
