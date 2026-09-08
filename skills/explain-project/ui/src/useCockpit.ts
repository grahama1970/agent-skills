import { useCallback, useEffect, useState } from 'react'
import type { CockpitState, ExplainerSummary } from './types'

export function useRegisterAction(_qid: string, _action: () => void) {
  // explain-project cockpit contract hook: host shells can replace this no-op.
}

export function useCockpit(initialState: CockpitState, initialExplainers: ExplainerSummary[]) {
  const [state, setState] = useState(initialState)
  const [explainers] = useState(initialExplainers)

  const dispatch = useCallback(async (type: string, payload: Record<string, unknown> = {}) => {
    const res = await fetch('/api/cockpit/event', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ schema: 'explain_project.cockpit_event.v1', event_id: crypto.randomUUID(), type, expected_revision: state.revision, payload }),
    })
    const next = await res.json()
    if (res.ok) setState(next)
  }, [state.revision])

  return { state, explainers, dispatch }
}

export function useCockpitKeys(dispatch: (type: string) => void) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'ArrowRight') { event.preventDefault(); dispatch('step.next') }
      if (event.key === 'ArrowLeft') { event.preventDefault(); dispatch('step.previous') }
    }
    window.addEventListener('keydown', onKeyDown, { capture: true })
    return () => window.removeEventListener('keydown', onKeyDown, { capture: true })
  }, [dispatch])
}

export function useSvgHighlight(activeNodeIds: string[]) {
  return activeNodeIds.join(' ')
}
