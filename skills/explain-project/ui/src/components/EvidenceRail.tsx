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
        'space-y-3 overflow-y-auto rounded-xl',
        'border border-zinc-800',
        'bg-zinc-900/70 p-3 text-sm',
      ].join(' ')}
    >
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
          Evidence controls
        </h2>
        <p className="mt-1 text-xs text-zinc-400">
          Prepare source and debugger handoffs; execution stays receipt-bound.
        </p>
      </div>

      <IntegrationHealth state={state} />

      <section
        data-qid="cockpit:source:panel"
        data-revision={state.source.revision}
        className="rounded-lg border border-zinc-800 bg-zinc-950 p-3"
      >
        <h2 className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
          Source
        </h2>

        <div className="mt-1 rounded bg-zinc-900 p-2 font-mono text-xs text-cyan-200 break-all select-all border border-zinc-800/80">
          {location
            ? [
                location.file,
                `${location.start_line}-${location.end_line}`,
              ].join(':')
            : 'No source selected'}
        </div>

        <p className="mt-2 text-xs text-zinc-300 leading-relaxed">
          {state.source.explanation}
        </p>

        <button
          type="button"
          data-qid="cockpit:source:reveal"
          data-qs-action="SOURCE_REVEAL_REQUEST"
          title="Prepare a preserve-focus VS Code reveal intent"
          className={[
            'mt-2 w-full rounded border border-zinc-700 bg-zinc-900',
            'py-1.5 px-3 text-xs font-medium text-zinc-200',
            'hover:border-cyan-500/50 hover:bg-zinc-800 transition-all',
          ].join(' ')}
          onClick={() => {
            void dispatch(
              'source.reveal.request',
            )
          }}
        >
          Reveal source
        </button>

        <p className="mt-2 text-[11px] font-mono text-zinc-500">
          {state.source.reveal_intent
            ? (
                `Intent r${state.source.reveal_intent.revision}; `
                + 'execute=false'
              )
            : 'No reveal intent emitted.'}
        </p>
      </section>

      <section
        data-qid="cockpit:debugger:panel"
        data-revision={state.debugger.revision}
        className="rounded-lg border border-zinc-800 bg-zinc-950 p-3"
      >
        <h2 className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
          Debugger target only
        </h2>

        <div className="mt-1 rounded bg-zinc-900 p-2 font-mono text-xs text-cyan-200 break-all select-all border border-zinc-800/80">
          {debuggerTarget
            ? `${debuggerTarget.file}:${debuggerTarget.line}`
            : 'No target'}
        </div>

        <p className="mt-2 text-xs text-zinc-300 leading-relaxed">
          {debuggerTarget?.proves}
        </p>

        {debuggerTarget?.locals.length ? (
          <div className="mt-2 text-[11px] font-mono text-zinc-400 bg-zinc-900/60 p-1.5 rounded border border-zinc-800">
            <span className="text-zinc-500">locals: </span>
            {debuggerTarget.locals.join(', ')}
          </div>
        ) : null}

        <button
          type="button"
          data-qid="cockpit:debugger:prepare"
          data-qs-action="DEBUGGER_PREPARE_TARGET"
          title="Prepare debugger target without running the debugger"
          className={[
            'mt-2 w-full rounded border border-zinc-700 bg-zinc-900',
            'py-1.5 px-3 text-xs font-medium text-zinc-200',
            'hover:border-cyan-500/50 hover:bg-zinc-800 transition-all',
          ].join(' ')}
          onClick={() => {
            void dispatch(
              'debugger.prepare.request',
            )
          }}
        >
          Prepare target
        </button>

        <p className="mt-2 text-[11px] font-mono text-zinc-500">
          {state.debugger.prepare_intent
            ? 'Intent only; execution_allowed=false'
            : state.debugger.status}
        </p>
      </section>

      <DiagramStage state={state} />
    </aside>
  )
}
