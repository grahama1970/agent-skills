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
        'bg-zinc-950 p-4 text-zinc-50',
      ].join(' ')}
    >
      <header
        className={[
          'mb-4 flex h-14 items-center',
          'justify-between rounded-xl',
          'border border-zinc-800',
          'bg-zinc-900/80 px-4',
        ].join(' ')}
      >
        <div>
          <div
            className={[
              'text-xs uppercase',
              'tracking-[0.22em] text-cyan-300',
            ].join(' ')}
          >
            Interview cockpit
          </div>
          <div className="text-sm text-zinc-400">
            Answer follow-up questions from source, proof, and safe debugger targets.
          </div>
        </div>

        <div className="text-sm font-semibold text-zinc-300">
          Evidence state: {state.route?.status ?? 'NO_MATCH'} · r{state.revision}
        </div>

        <div className="text-sm text-zinc-400">
          {state.selection
            ? (
                `Step ${state.selection.step_index + 1}`
                + ` / ${state.selection.step_count}`
              )
            : 'No explainer selected'}
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
          'grid h-[calc(100dvh-104px)]',
          'grid-cols-[280px_minmax(0,1fr)_420px]',
          'gap-4',
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
