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
        'flex min-w-0 flex-col justify-between rounded-2xl',
        'border border-cyan-500/30',
        'bg-black p-6 shadow-2xl',
      ].join(' ')}
    >
      <div
        className={[
          'cockpit-stage__meta',
          'flex items-center justify-between gap-3 shrink-0',
        ].join(' ')}
      >
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-cyan-500/40 bg-cyan-950/60 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-cyan-300">
            {state.teleprompter.confidence
              ? `${state.teleprompter.confidence} confidence`
              : 'No confidence'}
          </span>
          <span className="rounded-full border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs font-medium uppercase tracking-wider text-zinc-400">
            {state.teleprompter.verification
              === 'debugger_proof_received'
              ? 'Debugger proof'
              : 'Narrative only'}
          </span>
        </div>
      </div>

      <div className="flex-1 flex flex-col justify-center my-auto py-2 space-y-5">
        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-[0.28em] text-cyan-300">
            Speaker cue
          </p>

          <h1
            className={[
              'max-w-[24ch]',
              'text-3xl font-extrabold tracking-tight leading-[1.12]',
              'text-balance xl:text-4xl text-white',
            ].join(' ')}
          >
            {state.teleprompter.title
              ?? 'Select an explainer'}
          </h1>
        </div>

        <ul
          className={[
            'max-w-[36ch] space-y-3.5',
            'text-[clamp(1.2rem,1.5vw,1.75rem)]',
            'leading-[1.4] text-zinc-100 font-normal',
          ].join(' ')}
        >
          {state.teleprompter.bullets.map(
            (bullet) => (
              <li key={bullet} className="flex items-start gap-3 bg-zinc-950/70 border border-zinc-800/80 rounded-xl p-3.5 shadow-sm">
                <span className="text-cyan-400 font-bold shrink-0 mt-0.5">•</span>
                <span className="text-zinc-100">{bullet}</span>
              </li>
            ),
          )}
        </ul>

        <div
          className={[
            'rounded-xl',
            'border-l-4 border-l-amber-400 border-y border-r border-amber-500/30',
            'bg-amber-950/20 p-3.5',
            'text-sm text-amber-100/90',
          ].join(' ')}
        >
          <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.24em] text-amber-300">
            Proof boundary
          </div>
          {state.teleprompter.proof_boundary
            ?? 'No live proof claimed.'}
        </div>
      </div>

      <div
        className={[
          'flex items-center justify-between shrink-0',
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
            'bg-cyan-950/50 px-5 py-2 min-h-[44px] text-sm font-semibold text-cyan-200',
            'hover:bg-cyan-500 hover:text-zinc-950 transition-all shadow-sm shadow-cyan-950/50',
          ].join(' ')}
          onClick={() => {
            void dispatch('step.next')
          }}
        >
          <span>Next →</span>
        </button>
      </div>
    </section>
  )
}
