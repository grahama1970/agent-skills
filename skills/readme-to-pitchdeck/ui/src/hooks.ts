import { useCallback, useEffect, useRef, useState } from 'react'
import { CANVAS_HEIGHT, CANVAS_WIDTH, type UiDeckBundle } from './types'

/** Load the emitted deck bundle. Refuses bundles without a seam_validation PASS stamp. */
export function useDeck(): { deck: UiDeckBundle | null; error: string | null } {
  const [deck, setDeck] = useState<UiDeckBundle | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const url = params.get('deck') ?? './deck.data.json'
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`fetch ${url}: ${res.status}`)
        return res.json() as Promise<UiDeckBundle>
      })
      .then((bundle) => {
        if (bundle.seam_validation?.status !== 'PASS') {
          throw new Error('deck bundle is missing its seam_validation PASS stamp; re-run `run.sh emit-ui`')
        }
        setDeck(bundle)
      })
      .catch((err: Error) => setError(err.message))
  }, [])
  return { deck, error }
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
