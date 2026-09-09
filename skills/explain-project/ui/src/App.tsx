import {
  EvidenceRail,
} from './components/EvidenceRail'

import {
  InputRail,
} from './components/InputRail'

import {
  TeleprompterStage,
} from './components/TeleprompterStage'

import type {
  CockpitState,
  ExplainerSummary,
} from './types'

import {
  useCockpit,
  useCockpitKeys,
} from './useCockpit'

interface Props {
  initialState?: CockpitState
  initialExplainers?: ExplainerSummary[]
}

export function CockpitApp({
  initialState,
  initialExplainers = [],
}: Props = {}) {
  const {
    state,
    explainers,
    dispatch,
    importRecord,
    error,
  } = useCockpit(
    initialState,
    initialExplainers,
  )

  useCockpitKeys(dispatch)

  if (state === null) {
    return (
      <main
        className={[
          'grid h-dvh place-items-center',
          'bg-zinc-950 text-zinc-300',
        ].join(' ')}
      >
        <p>
          {error ?? 'Loading cockpit…'}
        </p>
      </main>
    )
  }

  return (
    <main
      data-qid="cockpit:state:root"
      data-revision={state.revision}
      className={[
        'h-dvh overflow-hidden',
        'bg-zinc-950 p-3.5 text-zinc-50',
      ].join(' ')}
    >
      <header
        className={[
          'mb-2.5 flex h-12 items-center',
          'justify-between rounded-xl',
          'border border-zinc-800',
          'bg-zinc-900/80 px-4',
        ].join(' ')}
      >
        <div className="flex items-center gap-3">
          <div
            className={[
              'text-xs font-bold uppercase',
              'tracking-[0.22em] text-cyan-300',
            ].join(' ')}
          >
            Interview Cockpit
          </div>
          <span className="text-zinc-700">|</span>
          <div className="text-xs text-zinc-400 truncate max-w-md">
            Answer follow-up questions from source, proof, and safe debugger targets.
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <span className="text-zinc-300 font-semibold">
            Evidence: <span className="text-cyan-300">{state.route?.status ?? 'NO_MATCH'}</span> · r{state.revision}
          </span>
          <span className="text-zinc-600">•</span>
          <span className="text-zinc-400">
            {state.selection
              ? (
                  `Step ${state.selection.step_index + 1}`
                  + ` / ${state.selection.step_count}`
                )
              : 'No explainer selected'}
          </span>
        </div>
      </header>

      {error ? (
        <div
          role="alert"
          data-qid="cockpit:state:error"
          className={[
            'mb-2 rounded-lg border',
            'border-red-700 bg-red-950/70',
            'px-3 py-2 text-sm text-red-200',
          ].join(' ')}
        >
          {error}
        </div>
      ) : null}

      <section
        className={[
          'grid h-[calc(100dvh-74px)]',
          'grid-cols-[290px_minmax(0,1fr)_390px]',
          'gap-3.5 overflow-hidden',
        ].join(' ')}
      >
        <InputRail
          explainers={explainers}
          state={state}
          dispatch={dispatch}
          importRecord={importRecord}
        />

        <TeleprompterStage
          state={state}
          dispatch={dispatch}
        />

        <EvidenceRail
          state={state}
          dispatch={dispatch}
        />
      </section>
    </main>
  )
}
