import { useCallback, useEffect, useRef, useState } from 'react'
import { CANVAS_HEIGHT, CANVAS_WIDTH, type UiDeckBundle } from './types'

export const revisionStore = { current: 0 }

/** Load the emitted deck bundle. Refuses bundles without a seam_validation PASS stamp. */
export function useDeck(): { deck: UiDeckBundle | null; error: string | null; reload: () => void } {
  const [deck, setDeck] = useState<UiDeckBundle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const url = params.get('deck') ?? './deck.data.json'
    fetch(`${url}${url.includes('?') ? '&' : '?'}v=${version}`, { cache: 'no-store' })
      .then((res) => {
        if (!res.ok) throw new Error(`fetch ${url}: ${res.status}`)
        return res.json() as Promise<UiDeckBundle>
      })
      .then((bundle) => {
        if (bundle.seam_validation?.status !== 'PASS') {
          throw new Error('deck bundle is missing its seam_validation PASS stamp; re-run `run.sh emit-ui`')
        }
        revisionStore.current = bundle.revision ?? 0
        setDeck(bundle)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
  }, [version])
  const reload = useCallback(() => setVersion((value) => value + 1), [])
  return { deck, error, reload }
}

/** Scale a fixed 1920x1080 canvas to fit its container (open-slide convention). */
export function useSlideScale(): { ref: React.RefObject<HTMLDivElement | null>; scale: number } {
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
  return { ref, scale }
}

/** Arrow/space/home/end keyboard navigation. */
export function useKeyboardNav(count: number, index: number, setIndex: (next: number) => void): void {
  const clamp = useCallback(
    (value: number) => Math.max(0, Math.min(count - 1, value)),
    [count],
  )
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      switch (event.key) {
        case 'ArrowRight':
        case 'ArrowDown':
        case ' ':
        case 'PageDown':
          setIndex(clamp(index + 1))
          break
        case 'ArrowLeft':
        case 'ArrowUp':
        case 'PageUp':
          setIndex(clamp(index - 1))
          break
        case 'Home':
          setIndex(0)
          break
        case 'End':
          setIndex(count - 1)
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [clamp, count, index, setIndex])
}

interface ActionSpec {
  app: string
  action: string
  label: string
  description: string
}

/**
 * Local copy of the action-registry hook (best-practices-react write-time contract).
 * Registers to the endpoint named by VITE_ACTION_REGISTRY_URL when configured;
 * otherwise records to an in-page registry only. Fail-silent by design — the deck
 * must render without the workstation memory daemon.
 */
const registered = new Set<string>()
export function useRegisterAction(qid: string, spec: ActionSpec): void {
  useEffect(() => {
    if (registered.has(qid)) return
    registered.add(qid)
    ;(window as unknown as { __appActions?: Record<string, ActionSpec> }).__appActions = {
      ...(window as unknown as { __appActions?: Record<string, ActionSpec> }).__appActions,
      [qid]: spec,
    }
    const endpoint = import.meta.env.VITE_ACTION_REGISTRY_URL as string | undefined
    if (!endpoint) return
    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document: { _key: qid.replace(/[^a-zA-Z0-9_-]/g, '_'), qid, ...spec }, collection: 'app_actions' }),
    }).catch(() => undefined)
  }, [qid, spec])
}


type ResizablePane = 'source' | 'rail' | 'inspector'

const PANE_CONSTRAINTS: Record<ResizablePane, { min: number; max: number; initial: number }> = {
  source: { min: 260, max: 650, initial: 400 },
  rail: { min: 110, max: 320, initial: 130 },
  inspector: { min: 240, max: 480, initial: 320 },
}

/** Persisted, clamped pane widths with window-level drag listeners. */
export function usePaneResize() {
  const [widths, setWidths] = useState<Record<ResizablePane, number>>(() => {
    const load = (pane: ResizablePane) => {
      try {
        const stored = Number(window.localStorage.getItem(`deck-pane-width-${pane}`))
        const { min, max, initial } = PANE_CONSTRAINTS[pane]
        return Number.isFinite(stored) && stored >= min && stored <= max ? stored : initial
      } catch {
        return PANE_CONSTRAINTS[pane].initial
      }
    }
    return { source: load('source'), rail: load('rail'), inspector: load('inspector') }
  })
  const [activeResizer, setActiveResizer] = useState<ResizablePane | null>(null)
  const startX = useRef(0)
  const startWidth = useRef(0)

  const startResizing = useCallback(
    (pane: ResizablePane, event: React.MouseEvent) => {
      event.preventDefault()
      setActiveResizer(pane)
      startX.current = event.clientX
      startWidth.current = widths[pane]
    },
    [widths],
  )

  useEffect(() => {
    if (!activeResizer) return
    const onMove = (event: MouseEvent) => {
      const delta = event.clientX - startX.current
      const signed = activeResizer === 'inspector' ? -delta : delta
      const { min, max } = PANE_CONSTRAINTS[activeResizer]
      const next = Math.min(Math.max(startWidth.current + signed, min), max)
      setWidths((prev) => ({ ...prev, [activeResizer]: next }))
    }
    const onUp = () => setActiveResizer(null)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [activeResizer])

  useEffect(() => {
    try {
      for (const [pane, width] of Object.entries(widths)) {
        window.localStorage.setItem(`deck-pane-width-${pane}`, String(width))
      }
    } catch {
      /* storage unavailable */
    }
  }, [widths])

  const resetWidth = useCallback((pane?: ResizablePane) => {
    setWidths((prev) => {
      if (!pane) {
        return {
          source: PANE_CONSTRAINTS.source.initial,
          rail: PANE_CONSTRAINTS.rail.initial,
          inspector: PANE_CONSTRAINTS.inspector.initial,
        }
      }
      return { ...prev, [pane]: PANE_CONSTRAINTS[pane].initial }
    })
  }, [])

  return { widths, startResizing, resetWidth, activeResizer }
}
