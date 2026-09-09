import type {
  CockpitState,
  IntegrationStatus,
} from '../types'

const tone: Record<IntegrationStatus, string> = {
  READY: 'border-emerald-600 text-emerald-300',
  STALE: 'border-amber-600 text-amber-300',
  FAILED: 'border-red-600 text-red-300',
  NOT_CONFIGURED: 'border-zinc-700 text-zinc-500',
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
        'rounded-full border px-2 py-1 text-[11px]',
        tone[status],
      ].join(' ')}
      title={`${label}: ${status}`}
    >
      {label}: {status}
    </span>
  )
}

export function IntegrationHealth({
  state,
}: {
  state: CockpitState
}) {
  return (
    <section className="rounded-lg bg-zinc-950 p-3">
      <h2 className="font-semibold">
        Integration health
      </h2>

      <div className="mt-2 flex flex-wrap gap-2">
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
