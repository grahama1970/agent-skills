import type {
  Dispatch,
} from '../useCockpit'

import {
  useRegisterAction,
} from '../useRegisterAction'

import {
  DiagramStage,
} from './DiagramStage'

import {
  IntegrationHealth,
} from './IntegrationHealth'

import type {
  CockpitState,
} from '../types'

export function EvidenceRail({
  state,
  dispatch,
}: {
  state: CockpitState
  dispatch: Dispatch
}) {
  useRegisterAction({
    element_id: 'cockpit:source:reveal',
    app: 'explain-project',
    action: 'SOURCE_REVEAL_REQUEST',
    label: 'Prepare source reveal',
    description: (
      'Emit a debugger-owned VS Code source-reveal '
      + 'intent with preserve-focus semantics.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:debugger:prepare',
    app: 'explain-project',
    action: 'DEBUGGER_PREPARE_TARGET',
    label: 'Prepare debugger target',
    description: (
      'Emit a breakpoint target intent; this action '
      + 'cannot run, continue, or step the debugger.'
    ),
  })

  const location = state.source.location
  const debuggerTarget = state.debugger.target

  return (
    <aside
      className={[
        'space-y-3 overflow-hidden rounded-xl',
        'border border-zinc-800',
        'bg-zinc-900/70 p-3 text-sm',
      ].join(' ')}
    >
      <IntegrationHealth state={state} />

      <section className="rounded-lg bg-zinc-950 p-3">
        <h2 className="font-semibold">
          Source
        </h2>

        <p>
          {location
            ? [
                location.file,
                `${location.start_line}-${location.end_line}`,
              ].join(':')
            : 'No source selected'}
        </p>

        <p className="mt-1 text-zinc-400">
          {state.source.explanation}
        </p>

        <button
          type="button"
          data-qid="cockpit:source:reveal"
          data-qs-action="SOURCE_REVEAL_REQUEST"
          title="Prepare a preserve-focus VS Code reveal intent"
          className={[
            'mt-2 rounded bg-zinc-800',
            'px-2 py-1 hover:bg-zinc-700',
          ].join(' ')}
          onClick={() => {
            void dispatch(
              'source.reveal.request',
            )
          }}
        >
          Reveal source
        </button>

        <p className="mt-2 text-xs text-zinc-500">
          {state.source.reveal_intent
            ? (
                `Intent r${state.source.reveal_intent.revision}; `
                + 'execute=false'
              )
            : 'No reveal intent emitted.'}
        </p>
      </section>

      <section className="rounded-lg bg-zinc-950 p-3">
        <h2 className="font-semibold">
          Debugger target only
        </h2>

        <p>
          {debuggerTarget
            ? `${debuggerTarget.file}:${debuggerTarget.line}`
            : 'No target'}
        </p>

        <p className="mt-1 text-zinc-400">
          {debuggerTarget?.proves}
        </p>

        {debuggerTarget?.locals.length ? (
          <p className="mt-2 text-xs text-zinc-500">
            locals:
            {' '}
            {debuggerTarget.locals.join(', ')}
          </p>
        ) : null}

        <button
          type="button"
          data-qid="cockpit:debugger:prepare"
          data-qs-action="DEBUGGER_PREPARE_TARGET"
          title="Prepare debugger target without running the debugger"
          className={[
            'mt-2 rounded bg-zinc-800',
            'px-2 py-1 hover:bg-zinc-700',
          ].join(' ')}
          onClick={() => {
            void dispatch(
              'debugger.prepare.request',
            )
          }}
        >
          Prepare target
        </button>

        <p className="mt-2 text-xs text-zinc-500">
          {state.debugger.prepare_intent
            ? 'Intent only; execution_allowed=false'
            : state.debugger.status}
        </p>
      </section>

      <DiagramStage state={state} />
    </aside>
  )
}
