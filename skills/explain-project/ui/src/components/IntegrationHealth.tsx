import type {
  CockpitState,
  IntegrationStatus,
} from '../types'

const tone: Record<IntegrationStatus, string> = {
  READY: 'border-emerald-600/60 text-emerald-300 bg-emerald-950/40',
  STALE: 'border-amber-600/60 text-amber-300 bg-amber-950/40',
  FAILED: 'border-red-600/60 text-red-300 bg-red-950/40',
  NOT_CONFIGURED: 'border-zinc-700 text-zinc-400 bg-zinc-900/60',
}

const dotColor: Record<IntegrationStatus, string> = {
  READY: 'bg-emerald-400',
  STALE: 'bg-amber-400',
  FAILED: 'bg-red-400',
  NOT_CONFIGURED: 'bg-zinc-500',
}

function HealthPill({
  label,
  status,
}: {
  label: string
  status: IntegrationStatus
}) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-xs leading-none',
        tone[status],
      ].join(' ')}
      title={`${label}: ${status}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor[status]}`} />
      <span>{label}: {status}</span>
    </span>
  )
}

export function IntegrationHealth({
  state,
}: {
  state: CockpitState
}) {
  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
        Integration health
      </h2>

      <div className="mt-2 flex flex-wrap gap-1.5">
        <HealthPill
          label={state.question?.source === 'live_evidence_replay'
            ? 'Live Evidence (replay)'
            : 'Live Evidence intake'}
          status={state.integration_health.live_evidence}
        />
        <HealthPill
          label="Source"
          status={state.integration_health.source_reveal}
        />
        <HealthPill
          label="Debugger"
          status={state.integration_health.debugger_target}
        />
        <HealthPill
          label="Diagram"
          status={state.integration_health.diagram}
        />
      </div>
    </section>
  )
}
