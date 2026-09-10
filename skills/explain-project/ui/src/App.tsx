import {
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react'

import {
  useEffect,
  useState,
} from 'react'

import {
  EvidenceRail,
} from './components/EvidenceRail'

import {
  CockpitAudioIndicator,
} from './components/CockpitAudioIndicator'

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

import {
  useRegisterAction,
} from './useRegisterAction'

interface Props {
  initialState?: CockpitState
  initialExplainers?: ExplainerSummary[]
}

function statusDotClass(status: string): string {
  if (status === 'READY') return 'bg-green-400 shadow-[0_0_8px_#22c55e]'
  if (status === 'STALE') return 'bg-amber-400 shadow-[0_0_8px_#f59e0b]'
  if (status === 'FAILED') return 'bg-red-400 shadow-[0_0_8px_#ef4444]'
  return 'bg-zinc-500'
}

function masterSync(state: CockpitState): {
  label: string
  className: string
} {
  const statuses = Object.values(state.integration_health)

  if (statuses.every((status) => status === 'READY')) {
    return {
      label: 'ALL SYSTEMS SYNCED',
      className: 'border-green-500/70 bg-green-950/40 text-green-300',
    }
  }

  if (statuses.some((status) => status === 'FAILED')) {
    return {
      label: 'SYNC DISCONNECTED',
      className: 'border-red-500/70 bg-red-950/40 text-red-300',
    }
  }

  if (statuses.some((status) => status === 'STALE')) {
    return {
      label: 'OUT OF SYNC',
      className: 'border-amber-500/70 bg-amber-950/40 text-amber-300',
    }
  }

  return {
    label: 'SYNC NOT CONFIGURED',
    className: 'border-zinc-700 bg-zinc-900/70 text-zinc-400',
  }
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

  const [isEvidenceOpen, setIsEvidenceOpen] = useState(false)

  useRegisterAction({
    element_id: 'cockpit:evidence:toggle',
    app: 'explain-project',
    action: 'EVIDENCE_DRAWER_TOGGLE',
    label: 'Toggle evidence rail',
    description: 'Expand or collapse the mounted evidence/debugger rail without changing reducer state.',
  })

  useCockpitKeys(dispatch)

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      const target = event.target as HTMLElement | null
      if (
        target?.tagName === 'INPUT'
        || target?.tagName === 'TEXTAREA'
        || target?.isContentEditable
      ) {
        return
      }

      if (event.key.toLowerCase() === 'e') {
        event.preventDefault()
        setIsEvidenceOpen((open) => !open)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

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

  const sync = masterSync(state)

  return (
    <main
      data-qid="cockpit:state:root"
      data-revision={state.revision}
      className={[
        'h-screen max-h-screen overflow-hidden',
        'bg-zinc-950 p-3 text-zinc-50',
      ].join(' ')}
    >
      <header
        className={[
          'flex min-h-14 items-center',
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
          <CockpitAudioIndicator />
          <span
            data-qid="cockpit:health:master-sync"
            data-revision={state.revision}
            className={[
              'rounded-full border px-3 py-1 font-bold uppercase tracking-wider',
              sync.className,
            ].join(' ')}
            title="Master sync status across Live Evidence, VS Code, debugger, and web UI targets"
          >
            {sync.label}
          </span>
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
          'cockpit-layout grid h-full min-h-0 overflow-hidden',
          isEvidenceOpen ? 'evidence-expanded' : 'evidence-collapsed',
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

        <div
          data-qid="cockpit:evidence:drawer"
          data-state={isEvidenceOpen ? 'expanded' : 'collapsed'}
          className="relative h-full min-h-0 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950"
        >
          <button
            type="button"
            data-qid="cockpit:evidence:toggle"
            data-qs-action="EVIDENCE_DRAWER_TOGGLE"
            title={isEvidenceOpen ? 'Collapse evidence rail (Press E)' : 'Expand evidence rail (Press E)'}
            aria-label={isEvidenceOpen ? 'Collapse evidence rail' : 'Expand evidence rail'}
            className={[
              'absolute z-10 rounded-lg border border-zinc-700 bg-zinc-900/95',
              'text-xs font-semibold text-zinc-300 hover:border-cyan-500 hover:text-cyan-100',
              isEvidenceOpen
                ? 'right-2 top-2 grid size-9 place-items-center'
                : 'inset-0 flex h-full w-full flex-col items-center justify-between py-4',
            ].join(' ')}
            onClick={() => setIsEvidenceOpen((open) => !open)}
          >
            {isEvidenceOpen ? (
              <PanelRightClose aria-hidden="true" className="size-5" />
            ) : (
              <>
                <PanelRightOpen aria-hidden="true" className="size-4 text-cyan-400" />
                <span className="flex flex-col gap-1" title="Live, DAP, and Web sync status">
                  <span className={`size-2 rounded-full ${statusDotClass(state.integration_health.live_evidence)}`} />
                  <span className={`size-2 rounded-full ${statusDotClass(state.integration_health.debugger_target)}`} />
                  <span className={`size-2 rounded-full ${statusDotClass(state.integration_health.diagram)}`} />
                </span>
                <span className="[writing-mode:vertical-lr] rotate-180 text-[10px] uppercase tracking-widest">
                  Evidence / Debug
                </span>
                <kbd className="rounded border border-zinc-700 bg-zinc-800 px-1 py-0.5 text-[9px]">
                  E
                </kbd>
              </>
            )}
          </button>

          <div
            className={[
              'h-full min-h-0 transition-opacity',
              isEvidenceOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
            ].join(' ')}
            aria-hidden={isEvidenceOpen ? undefined : true}
          >
            <EvidenceRail
              state={state}
              dispatch={dispatch}
            />
          </div>
        </div>
      </section>
    </main>
  )
}
