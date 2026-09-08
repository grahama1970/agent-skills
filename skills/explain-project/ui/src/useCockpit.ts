import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  fetchBootstrap,
  importExplainer,
  postCockpitEvent,
  type EventType,
} from './api'

import type {
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

  useEffect(() => {
    if (stateRef.current !== null) return

    let cancelled = false

    void fetchBootstrap()
      .then((bootstrap) => {
        if (cancelled) return

        stateRef.current = bootstrap.state
        setState(bootstrap.state)
        setExplainers(bootstrap.explainers)
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(
            caught instanceof Error
              ? caught.message
              : String(caught),
          )
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

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

          stateRef.current = next
          setState(next)
        },
      )

      queueRef.current = queued.catch(
        () => undefined,
      )

      return queued.catch((caught) => {
        setError(
          caught instanceof Error
            ? caught.message
            : String(caught),
        )
      })
    },
    [],
  )

  const importRecord = useCallback(
    (record: unknown): Promise<boolean> => {
      let imported = false

      const queued = queueRef.current.then(
        async () => {
          const bootstrap = await importExplainer(
            record,
          )

          stateRef.current = bootstrap.state
          setState(bootstrap.state)
          setExplainers(bootstrap.explainers)

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
    [],
  )

  return {
    state,
    explainers,
    dispatch,
    importRecord,
    error,
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
      if (isTypingTarget(event.target)) {
        return
      }

      if (event.key === 'ArrowRight') {
        event.preventDefault()
        void dispatch('step.next')
      }

      if (event.key === 'ArrowLeft') {
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
