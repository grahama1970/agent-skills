import {
  AudioLines,
  Bug,
  CircleSlash,
  Globe,
  TriangleAlert,
} from 'lucide-react'

import {
  useCallback,
  useEffect,
  useState,
} from 'react'

import type {
  LucideIcon,
} from 'lucide-react'

import {
  fetchServices,
} from '../api'

import {
  useRegisterAction,
} from '../useRegisterAction'

import type {
  ServiceStatusKind,
  SkillServiceHealth,
} from '../types'

type ServiceId = SkillServiceHealth['service']

const serviceMeta: Record<
  ServiceId,
  { label: string; icon: LucideIcon }
> = {
  live_evidence: {
    label: 'Live Evidence',
    icon: AudioLines,
  },
  debugger: {
    label: 'Debugger bridge',
    icon: Bug,
  },
  surf: {
    label: 'Surf browser',
    icon: Globe,
  },
}

const statusTone: Record<ServiceStatusKind, string> = {
  ONLINE: 'border-green-500/70 text-green-300 bg-green-950/40',
  DEGRADED: 'border-amber-500/70 text-amber-300 bg-amber-950/40',
  OFFLINE: 'border-red-500/70 text-red-300 bg-red-950/40',
  NOT_CONFIGURED: 'border-zinc-700 text-zinc-400 bg-zinc-900/60',
}

function StatusGlyph({
  status,
}: {
  status: ServiceStatusKind
}) {
  if (status === 'ONLINE') {
    return <span className="size-2 shrink-0 rounded-full bg-green-400 shadow-[0_0_8px_#22c55e]" />
  }
  if (status === 'DEGRADED') {
    return <TriangleAlert aria-hidden="true" className="size-3.5 shrink-0" />
  }
  if (status === 'OFFLINE') {
    return <TriangleAlert aria-hidden="true" className="size-3.5 shrink-0" />
  }
  return <CircleSlash aria-hidden="true" className="size-3.5 shrink-0" />
}

function ServicePill({
  health,
  onBindClick,
  pressed,
}: {
  health: SkillServiceHealth
  onBindClick?: () => void
  pressed?: boolean
}) {
  const meta = serviceMeta[health.service]
  const Icon = meta.icon
  const interactive = onBindClick !== undefined
  const id = health.service

  const className = [
    'flex w-full items-center gap-2 rounded-md border px-2 py-1.5',
    'font-mono text-xs leading-tight',
    interactive
      ? 'cursor-pointer text-left'
      : 'cursor-default',
    statusTone[health.status],
  ].join(' ')

  const title = `${meta.label}: ${health.status} — ${health.detail}`

  if (!interactive) {
    return (
      <div
        data-qid={`cockpit:service:status:${id}`}
        data-service-status={health.status}
        role="status"
        className={className}
        title={title}
      >
        <StatusGlyph status={health.status} />
        <Icon aria-hidden="true" className="size-3.5 shrink-0" />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold uppercase">{meta.label}</span>
          <span className="block truncate text-[10px] opacity-80">{health.detail}</span>
        </span>
      </div>
    )
  }

  return (
    <button
      type="button"
      data-qid={`cockpit:service:status:${id}`}
      data-qs-action="SERVICE_SURF_BIND"
      data-service-status={health.status}
      aria-pressed={pressed}
      title={`${title} — click to bind a tab id`}
      className={className}
      onClick={onBindClick}
    >
      <StatusGlyph status={health.status} />
      <Icon aria-hidden="true" className="size-3.5 shrink-0" />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold uppercase">{meta.label}</span>
        <span className="block truncate text-[10px] opacity-80">{health.detail}</span>
      </span>
    </button>
  )
}

export function ServiceHealth() {
  const [services, setServices] = useState<
    SkillServiceHealth[]
  >([])
  const [boundTabId, setBoundTabId] = useState('')
  const [inputOpen, setInputOpen] = useState(false)
  const [tabInput, setTabInput] = useState('')

  useRegisterAction({
    element_id: 'cockpit:service:status:surf',
    app: 'explain-project',
    action: 'SERVICE_SURF_BIND',
    label: 'Bind surf browser-control tab id',
    description: (
      'Open the tab-id input for $surf browser control '
      + 'liveness binding. Informational probe only.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:service:surf-tab-input',
    app: 'explain-project',
    action: 'SERVICE_SURF_TAB_EDIT',
    label: 'Edit surf tab id',
    description: 'Type the Chrome tab id surf should verify.',
  })

  useRegisterAction({
    element_id: 'cockpit:service:surf-tab-apply',
    app: 'explain-project',
    action: 'SERVICE_SURF_TAB_APPLY',
    label: 'Apply surf tab id',
    description: 'Bind the typed tab id and refresh service probes.',
  })

  const refresh = useCallback(
    async (tabId: string) => {
      try {
        const response = await fetchServices(
          tabId || undefined,
        )
        setServices(response.services)
      } catch {
        setServices([])
      }
    },
    [],
  )

  useEffect(() => {
    void refresh(boundTabId)
    const timer = window.setInterval(() => {
      void refresh(boundTabId)
    }, 10_000)
    return () => window.clearInterval(timer)
  }, [boundTabId, refresh])

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-cyan-300">
        Skill services
      </h2>

      <div className="mt-2 grid gap-1.5">
        {services.map((health) => (
          health.service === 'surf' ? (
            <ServicePill
              key={health.service}
              health={health}
              pressed={inputOpen}
              onBindClick={() => {
                setInputOpen((open) => !open)
              }}
            />
          ) : (
            <ServicePill
              key={health.service}
              health={health}
            />
          )
        ))}

        {services.length === 0 ? (
          <p className="rounded-md border border-zinc-800 bg-zinc-900/60 p-2 text-xs text-zinc-500">
            Service probes unavailable.
          </p>
        ) : null}

        {inputOpen ? (
          <div className="flex gap-1.5">
            <input
              data-qid="cockpit:service:surf-tab-input"
              data-qs-action="SERVICE_SURF_TAB_EDIT"
              title="Chrome tab id for surf browser control"
              type="text"
              inputMode="numeric"
              className={[
                'min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-950',
                'px-2 py-1 font-mono text-xs text-zinc-100',
                'placeholder-zinc-500 outline-none focus:border-cyan-500',
              ].join(' ')}
              placeholder="tab id, e.g. 837435946"
              value={tabInput}
              onChange={(event) => {
                setTabInput(event.currentTarget.value.trim())
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  setBoundTabId(tabInput)
                  setInputOpen(false)
                }
                if (event.key === 'Escape') {
                  setInputOpen(false)
                }
              }}
            />
            <button
              type="button"
              data-qid="cockpit:service:surf-tab-apply"
              data-qs-action="SERVICE_SURF_TAB_APPLY"
              title="Bind this tab id and refresh probes"
              className={[
                'shrink-0 rounded-md border border-cyan-500/60 bg-cyan-950/50',
                'px-2 py-1 font-mono text-xs font-semibold text-cyan-200',
                'hover:bg-cyan-500 hover:text-zinc-950 transition-colors',
              ].join(' ')}
              onClick={() => {
                setBoundTabId(tabInput)
                setInputOpen(false)
              }}
            >
              Bind
            </button>
          </div>
        ) : null}
      </div>
    </section>
  )
}
