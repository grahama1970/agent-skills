import {
  AlertTriangle,
  CheckCircle2,
  Lock,
  RefreshCw,
} from 'lucide-react'

import type {
  Dispatch,
} from '../useCockpit'

import {
  useRegisterAction,
} from '../useRegisterAction'

import type {
  CockpitState,
  IntegrationStatus,
} from '../types'

type SyncLabel =
  | 'SYNCED'
  | 'OUT OF SYNC'
  | 'DISCONNECTED'
  | 'NOT CONFIGURED'

const syncLabel: Record<IntegrationStatus, SyncLabel> = {
  READY: 'SYNCED',
  STALE: 'OUT OF SYNC',
  FAILED: 'DISCONNECTED',
  NOT_CONFIGURED: 'NOT CONFIGURED',
}

const tone: Record<IntegrationStatus, string> = {
  READY: 'border-green-500/70 text-green-300 bg-green-950/40',
  STALE: 'border-amber-500/70 text-amber-300 bg-amber-950/40',
  FAILED: 'border-red-500/70 text-red-300 bg-red-950/40',
  NOT_CONFIGURED: 'border-zinc-700 text-zinc-400 bg-zinc-900/60',
}

function StatusIcon({
  status,
}: {
  status: IntegrationStatus
}) {
  if (status === 'READY') {
    return <CheckCircle2 aria-hidden="true" className="size-3.5 shrink-0" />
  }

  if (status === 'STALE') {
    return <RefreshCw aria-hidden="true" className="size-3.5 shrink-0" />
  }

  if (status === 'FAILED') {
    return <AlertTriangle aria-hidden="true" className="size-3.5 shrink-0" />
  }

  return <Lock aria-hidden="true" className="size-3.5 shrink-0" />
}

function HealthPill({
  id,
  label,
  status,
  onRetry,
}: {
  id: string
  label: string
  status: IntegrationStatus
  onRetry: (id: string) => void
}) {
  const retryable = status !== 'READY'
  const qid = `cockpit:health:status:${id}`

  useRegisterAction({
    element_id: qid,
    app: 'explain-project',
    action: 'SYNC_TARGET_RETRY',
    label: `Retry ${label} sync`,
    description: 'Request a bounded re-sync intent for a non-green cockpit target.',
    params: { target: id },
  })

  return (
    <button
      type="button"
      data-qid={`cockpit:health:status:${id}`}
      data-qs-action="SYNC_TARGET_RETRY"
      data-sync-status={syncLabel[status]}
      className={[
        'inline-flex w-full items-center justify-between gap-2 rounded-md border px-2 py-1.5',
        'font-mono text-xs leading-tight',
        retryable ? 'cursor-pointer' : 'cursor-default',
        tone[status],
      ].join(' ')}
      title={`${label}: ${syncLabel[status]}${retryable ? ' — click to request re-sync' : ''}`}
      onClick={() => {
        if (retryable) onRetry(id)
      }}
    >
      <span className="inline-flex min-w-0 items-center gap-2">
        <StatusIcon status={status} />
        <span className="truncate">{label}</span>
      </span>
    </button>
  )
}

export function IntegrationHealth({
  state,
  dispatch,
}: {
  state: CockpitState
  dispatch: Dispatch
}) {
  function retry(target: string): void {
    window.dispatchEvent(new CustomEvent('cockpit:sync-target-retry', { detail: { target } }))

    if (target === 'source' || target === 'web-ui') {
      void dispatch('source.reveal.request')
    }

    if (target === 'debugger') {
      void dispatch('debugger.prepare.request')
    }
  }
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
        Integration health
      </h2>

      <div className="mt-2 grid gap-1.5">
        <HealthPill
          id="live-evidence"
          label={state.question?.source === 'live_evidence_replay'
            ? 'Live Evidence (replay)'
            : 'Live Evidence intake'}
          status={state.integration_health.live_evidence}
          onRetry={retry}
        />
        <HealthPill
          id="source"
          label="VS Code source"
          status={state.integration_health.source_reveal}
          onRetry={retry}
        />
        <HealthPill
          id="debugger"
          label="Debugger DAP"
          status={state.integration_health.debugger_target}
          onRetry={retry}
        />
        <HealthPill
          id="web-ui"
          label="Web UI / diagram"
          status={state.integration_health.diagram}
          onRetry={retry}
        />
      </div>
    </section>
  )
}
