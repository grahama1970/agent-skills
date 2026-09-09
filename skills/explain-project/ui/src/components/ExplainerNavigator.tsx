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

  const foundIndex = explainers.findIndex(
    (explainer) => (
      explainer.feature_id
      === state.selection?.feature_id
    ),
  )
  const currentIndex = Math.max(foundIndex, 0)
  const totalCount = explainers.length
  const maxIndex = Math.max(0, totalCount - 1)
  const displayStep = totalCount > 0 ? currentIndex + 1 : 0

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
    <section className="rounded-lg border border-zinc-800 bg-zinc-950/80 p-2.5">
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-semibold uppercase tracking-wider text-cyan-300">
          Explainer Index
        </span>
        <span className="font-mono font-bold text-cyan-400">
          {displayStep} / {totalCount}
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
        className="w-full h-1.5 cursor-pointer accent-cyan-400"
        onChange={(event) => {
          selectIndex(
            Number(event.currentTarget.value),
          )
        }}
      />

      <div className="mt-2 flex items-center gap-2 text-xs">
        <span className="text-zinc-400 font-mono">Jump index:</span>
        <input
          type="number"
          min={1}
          max={totalCount}
          value={displayStep}
          data-qid="cockpit:explainer:page-input"
          data-qs-action="EXPLAINER_PAGE_SET"
          title="Type an exact explainer index"
          className="w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 font-mono text-xs text-zinc-200 outline-none focus:border-cyan-500"
          onChange={(event) => {
            const val = Number(event.currentTarget.value)
            selectIndex(val - 1)
          }}
        />
      </div>
    </section>
  )
}
