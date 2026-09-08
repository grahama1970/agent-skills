import type {
  Dispatch,
} from '../useCockpit'

import {
  useRegisterAction,
} from '../useRegisterAction'

import type {
  CockpitState,
  ExplainerSummary,
} from '../types'

export function ExplainerNavigator({
  explainers,
  state,
  dispatch,
}: {
  explainers: ExplainerSummary[]
  state: CockpitState
  dispatch: Dispatch
}) {
  useRegisterAction({
    element_id: 'cockpit:explainer:slider',
    app: 'explain-project',
    action: 'EXPLAINER_SLIDER_SET',
    label: 'Jump through explainers',
    description: (
      'Use a PowerPoint-style slide navigator '
      + 'to jump to an explainer by index.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:explainer:page-input',
    app: 'explain-project',
    action: 'EXPLAINER_PAGE_SET',
    label: 'Jump to explainer page',
    description: 'Type an exact explainer index to select it.',
  })

  if (!explainers.length) {
    return null
  }

  const currentIndex = Math.max(
    explainers.findIndex(
      (explainer) => (
        explainer.feature_id
        === state.selection?.feature_id
      ),
    ),
    0,
  )
  const maxIndex = explainers.length - 1

  function selectIndex(index: number): void {
    const explainer = explainers[
      Math.min(Math.max(index, 0), maxIndex)
    ]

    if (!explainer) return

    void dispatch(
      'explainer.select',
      { feature_id: explainer.feature_id },
    )
  }

  return (
    <section className="rounded-lg bg-zinc-950 p-3">
      <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
        <span>Explainer</span>
        <span>
          {currentIndex} / {maxIndex}
        </span>
      </div>

      <input
        type="range"
        min={0}
        max={maxIndex}
        value={currentIndex}
        data-qid="cockpit:explainer:slider"
        data-qs-action="EXPLAINER_SLIDER_SET"
        title="Jump to an explainer by index"
        className="w-full accent-cyan-400"
        onChange={(event) => {
          selectIndex(
            Number(event.currentTarget.value),
          )
        }}
      />

      <input
        type="number"
        min={0}
        max={maxIndex}
        value={currentIndex}
        data-qid="cockpit:explainer:page-input"
        data-qs-action="EXPLAINER_PAGE_SET"
        title="Type an exact explainer index"
        className="mt-2 w-full rounded-lg bg-zinc-900 p-2 text-sm outline-none ring-cyan-500 focus:ring-2"
        onChange={(event) => {
          selectIndex(
            Number(event.currentTarget.value),
          )
        }}
      />
    </section>
  )
}
