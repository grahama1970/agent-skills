import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  CockpitApiError,
  fetchBootstrap,
  importExplainer,
  postCockpitEvent,
  type EventType,
} from './api'

import type {
  BootstrapResponse,
  CockpitState,
  ExplainerSummary,
} from './types'

export type Dispatch = (
  type: EventType,
  payload?: Record<string, unknown>,
) => Promise<void>

export function useCockpit(
  initialState?: CockpitState,
  initialExplainers: ExplainerSummary[] = [],
) {
  const [state, setState] = useState<CockpitState | null>(
    initialState ?? null,
  )
  const [explainers, setExplainers] = useState(
    initialExplainers,
  )
  const [error, setError] = useState<string | null>(
    null,
  )

  const stateRef = useRef<CockpitState | null>(
    initialState ?? null,
  )
  const queueRef = useRef<Promise<void>>(
    Promise.resolve(),
  )

  const [syncError, setSyncError] = useState<string | null>(null)
  const catalogRevision = useRef(initialState?.revision ?? -1)
  const pendingRefresh = useRef<Promise<void> | null>(null)

  const adoptState = useCallback((next: CockpitState) => {
    // Responses may arrive out of order; a slow poll must not undo an action.
    if (next.revision <= (stateRef.current?.revision ?? -1)) return
    stateRef.current = next
    setState(next)
  }, [])

  const adoptBootstrap = useCallback((bootstrap: BootstrapResponse) => {
    if (bootstrap.state.revision < (stateRef.current?.revision ?? -1)) return
    adoptState(bootstrap.state)
    if (bootstrap.state.revision > catalogRevision.current) {
      catalogRevision.current = bootstrap.state.revision
      setExplainers(bootstrap.explainers)
    }
  }, [adoptState])

  const refresh = useCallback((): Promise<void> => {
    if (pendingRefresh.current) return pendingRefresh.current
    const request = fetchBootstrap()
      .then((bootstrap) => {
        adoptBootstrap(bootstrap)
        setSyncError(null)
      })
      .catch((caught: unknown) => {
        setSyncError(`Cockpit sync interrupted; displayed state may be stale: ${
          caught instanceof Error ? caught.message : String(caught)
        }`)
        throw caught
      })
      .finally(() => { pendingRefresh.current = null })
    pendingRefresh.current = request
    return request
  }, [adoptBootstrap])

  useEffect(() => {
    // Explicit seeded props are for isolated, non-network component previews.
    if (initialState !== undefined) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const refreshQuietly = () => refresh().catch(() => {
      // refresh renders the sync error; never discard it as a successful poll.
    })
    async function poll(): Promise<void> {
      await refreshQuietly()
      // ponytail: 1 Hz snapshots for a local cockpit; SSE if latency/size demands it.
      if (!cancelled) timer = setTimeout(() => { void poll() }, 1000)
    }
    const onFocus = () => { void refreshQuietly() }
    void poll()
    window.addEventListener('focus', onFocus)
    return () => {
      cancelled = true
      clearTimeout(timer)
      window.removeEventListener('focus', onFocus)
    }
  }, [initialState, refresh])

  const dispatch = useCallback<Dispatch>(
    (type, payload = {}) => {
      const queued = queueRef.current.then(
        async () => {
          const current = stateRef.current

          if (current === null) {
            throw new Error(
              'cockpit state is not loaded',
            )
          }

          const next = await postCockpitEvent(
            current,
            type,
            payload,
          )

          adoptState(next)
          setError(null)
        },
      )

      queueRef.current = queued.catch(
        () => undefined,
      )

      return queued.catch(async (caught: unknown) => {
        if (caught instanceof CockpitApiError && caught.status === 409) {
          setError('Cockpit changed elsewhere; action not replayed. Review the current step and try again.')
          await refresh().catch(() => {
            // Keep the sync error visible until a later read succeeds.
          })
          return
        }
        setError(caught instanceof Error ? caught.message : String(caught))
      })
    },
    [adoptState, refresh],
  )

  const importRecord = useCallback(
    (record: unknown): Promise<boolean> => {
      let imported = false

      const queued = queueRef.current.then(
        async () => {
          const bootstrap = await importExplainer(
            record,
          )

          adoptBootstrap(bootstrap)
          setError(null)
          imported = true
        },
      )

      queueRef.current = queued.catch(
        () => undefined,
      )

      return queued
        .then(() => imported)
        .catch((caught) => {
          setError(
            caught instanceof Error
              ? caught.message
              : String(caught),
          )
          return false
        })
    },
    [adoptBootstrap],
  )

  return {
    state,
    explainers,
    dispatch,
    importRecord,
    error: syncError ?? error,
  }
}

function isTypingTarget(
  target: EventTarget | null,
): boolean {
  if (!(target instanceof HTMLElement)) {
    return false
  }

  return (
    target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || target.isContentEditable
  )
}

export function useCockpitKeys(
  dispatch: Dispatch,
): void {
  useEffect(() => {
    function onKeyDown(
      event: KeyboardEvent,
    ): void {
      if (event.key === 'Escape') {
        window.dispatchEvent(new CustomEvent('cockpit:explainer:clear-search'))
      }

      if (isTypingTarget(event.target)) {
        return
      }

      if (event.key === '/') {
        event.preventDefault()
        document
          .querySelector<HTMLElement>('[data-qid="cockpit:question:manual-input"]')
          ?.focus()
      }

      if (event.key === 'ArrowRight' || event.key.toLowerCase() === 'j') {
        event.preventDefault()
        void dispatch('step.next')
      }

      if (event.key === 'ArrowLeft' || event.key.toLowerCase() === 'k') {
        event.preventDefault()
        void dispatch('step.previous')
      }
    }

    window.addEventListener(
      'keydown',
      onKeyDown,
      { capture: true },
    )

    return () => {
      window.removeEventListener(
        'keydown',
        onKeyDown,
        { capture: true },
      )
    }
  }, [dispatch])
}

export function useFilteredExplainers(
  explainers: ExplainerSummary[],
  query: string,
): ExplainerSummary[] {
  return useMemo(() => {
    const needle = query
      .trim()
      .toLowerCase()

    if (!needle) {
      return explainers
    }

    return explainers.filter(
      (explainer) => (
        [
          explainer.feature_id,
          explainer.title,
          explainer.question,
          explainer.question_family,
        ]
          .join(' ')
          .toLowerCase()
          .includes(needle)
      ),
    )
  }, [explainers, query])
}
