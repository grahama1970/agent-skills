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
      data-qid="cockpit:teleprompter:stage"
      data-revision={state.teleprompter.revision}
      className={[
        'cockpit-stage',
        'flex min-w-0 flex-col rounded-2xl',
        'border border-cyan-500/30',
        'bg-black p-8 shadow-2xl justify-between',
      ].join(' ')}
    >
      <div>
        <div
          className={[
            'cockpit-stage__meta',
            'mb-4 flex items-center justify-between gap-3',
          ].join(' ')}
        >
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-cyan-500/30 bg-cyan-950/50 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-cyan-300">
              {state.teleprompter.confidence
                ? `${state.teleprompter.confidence} confidence`
                : 'No confidence'}
            </span>
            <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs font-medium uppercase tracking-wider text-zinc-400">
              {state.teleprompter.verification
                === 'debugger_proof_received'
                ? 'Debugger proof'
                : 'Narrative only'}
            </span>
          </div>
        </div>

        <p className="mb-2 text-xs uppercase tracking-[0.28em] text-cyan-300 font-semibold">
          Speaker cue
        </p>

        <h1
          className={[
            'mb-6 max-w-[22ch]',
            'text-4xl font-bold leading-[1.08]',
            'text-balance xl:text-5xl text-white',
          ].join(' ')}
        >
          {state.teleprompter.title
            ?? 'Select an explainer'}
        </h1>

        <ul
          className={[
            'max-w-[32ch] space-y-4',
            'text-[clamp(1.5rem,2vw,2.25rem)]',
            'leading-[1.25] text-zinc-100',
          ].join(' ')}
        >
          {state.teleprompter.bullets.map(
            (bullet) => (
              <li key={bullet} className="flex items-start gap-2">
                <span className="text-cyan-400 font-bold shrink-0">•</span>
                <span>{bullet}</span>
              </li>
            ),
          )}
        </ul>
      </div>

      <div>
        <div
          className={[
            'mt-6 rounded-xl',
            'border border-amber-400/40',
            'bg-amber-950/20 p-4',
            'text-sm text-amber-100',
          ].join(' ')}
        >
          <div className="mb-1 text-xs font-bold uppercase tracking-[0.24em] text-amber-300">
            Proof boundary
          </div>
          {state.teleprompter.proof_boundary
            ?? 'No live proof claimed.'}
        </div>

        <div
          className={[
            'mt-5 flex items-center justify-between',
            'pt-3 border-t border-zinc-800/80',
          ].join(' ')}
        >
          <button
            type="button"
            data-qid="cockpit:step:previous"
            data-qs-action="STEP_PREVIOUS"
            title="Previous step (ArrowLeft)"
            className={[
              'flex items-center gap-2 rounded-lg border border-zinc-700/80',
              'bg-zinc-900 px-4 py-2 min-h-[44px] text-sm font-semibold text-zinc-300',
              'hover:border-zinc-500 hover:bg-zinc-800 transition-all',
            ].join(' ')}
            onClick={() => {
              void dispatch('step.previous')
            }}
          >
            <span>← Previous</span>
          </button>

          <button
            type="button"
            data-qid="cockpit:step:next"
            data-qs-action="STEP_NEXT"
            title="Next step (ArrowRight)"
            className={[
              'flex items-center gap-2 rounded-lg border border-cyan-500/60',
              'bg-cyan-950/40 px-5 py-2 min-h-[44px] text-sm font-semibold text-cyan-200',
              'hover:bg-cyan-500 hover:text-zinc-950 transition-all shadow-sm',
            ].join(' ')}
            onClick={() => {
              void dispatch('step.next')
            }}
          >
            <span>Next →</span>
          </button>
        </div>
      </div>
    </section>
  )
}
