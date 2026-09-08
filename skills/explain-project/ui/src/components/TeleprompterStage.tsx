import type {
  Dispatch,
} from '../useCockpit'

import {
  useRegisterAction,
} from '../useRegisterAction'

import type {
  CockpitState,
} from '../types'

export function TeleprompterStage({
  state,
  dispatch,
}: {
  state: CockpitState
  dispatch: Dispatch
}) {
  useRegisterAction({
    element_id: 'cockpit:step:previous',
    app: 'explain-project',
    action: 'STEP_PREVIOUS',
    label: 'Previous explanation step',
    description: (
      'Move left one explainer step through '
      + 'the single reducer only.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:step:next',
    app: 'explain-project',
    action: 'STEP_NEXT',
    label: 'Next explanation step',
    description: (
      'Move right one explainer step through '
      + 'the single reducer only.'
    ),
  })

  return (
    <section
      className={[
        'flex min-w-0 flex-col rounded-2xl',
        'border border-cyan-500/30',
        'bg-black p-8 shadow-2xl',
      ].join(' ')}
    >
      <div
        className={[
          'mb-5 flex items-center justify-between',
          'text-sm uppercase tracking-wider',
          'text-zinc-500',
        ].join(' ')}
      >
        <span>
          {state.teleprompter.confidence
            ? `${state.teleprompter.confidence} confidence`
            : 'No confidence'}
        </span>

        <span>
          {state.teleprompter.verification
            === 'debugger_proof_received'
            ? 'Debugger proof'
            : 'Narrative only'}
        </span>
      </div>

      <h1
        className={[
          'mb-8 max-w-[20ch]',
          'text-5xl font-bold leading-[1.05]',
          'xl:text-6xl',
        ].join(' ')}
      >
        {state.teleprompter.title
          ?? 'Select an explainer'}
      </h1>

      <ul
        className={[
          'max-w-[32ch] flex-1 space-y-5',
          'text-[clamp(2rem,2.45vw,2.7rem)]',
          'leading-[1.13]',
        ].join(' ')}
      >
        {state.teleprompter.bullets.map(
          (bullet) => (
            <li key={bullet}>
              • {bullet}
            </li>
          ),
        )}
      </ul>

      <div
        className={[
          'mt-7 rounded-xl',
          'border border-zinc-800',
          'p-3 text-lg text-zinc-400',
        ].join(' ')}
      >
        {state.teleprompter.proof_boundary
          ?? 'No live proof claimed.'}
      </div>

      <div
        className={[
          'mt-4 flex justify-between',
          'text-xl text-zinc-400',
        ].join(' ')}
      >
        <button
          type="button"
          data-qid="cockpit:step:previous"
          data-qs-action="STEP_PREVIOUS"
          title="Previous step (ArrowLeft)"
          className={[
            'rounded-lg px-3 py-2',
            'hover:bg-zinc-900',
          ].join(' ')}
          onClick={() => {
            void dispatch('step.previous')
          }}
        >
          ← Previous
        </button>

        <button
          type="button"
          data-qid="cockpit:step:next"
          data-qs-action="STEP_NEXT"
          title="Next step (ArrowRight)"
          className={[
            'rounded-lg px-3 py-2',
            'hover:bg-zinc-900',
          ].join(' ')}
          onClick={() => {
            void dispatch('step.next')
          }}
        >
          Next →
        </button>
      </div>
    </section>
  )
}
