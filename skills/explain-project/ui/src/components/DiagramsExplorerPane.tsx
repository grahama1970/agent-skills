import {
  Lightbulb,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
} from 'lucide-react'

import {
  useMemo,
  useState,
} from 'react'

import type {
  Dispatch,
} from '../useCockpit'

import {
  useRegisterAction,
} from '../useRegisterAction'

import type {
  ExplainerSummary,
} from '../types'

interface DiagramEntry {
  source: string
  verified: boolean
  nodes: number
  features: string[]
}

/** Diagrams Explorer pane — ux-lab LeftPane qid pattern
 * (left-pane:{paneId}:*, LEFT_PANE_EXPAND-style actions), cockpit-native.
 *
 * Proposal-safe: the propose control only surfaces the
 * $ops-excalidraw proposal flow; no board mutation happens here.
 */
export function DiagramsExplorerPane({
  explainers,
  dispatch,
}: {
  explainers: ExplainerSummary[]
  dispatch: Dispatch
}) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const [proposeNote, setProposeNote] = useState(false)

  useRegisterAction({
    element_id: 'left-pane:diagrams:expand',
    app: 'explain-project',
    action: 'LEFT_PANE_EXPAND',
    label: 'Toggle Diagrams Explorer pane',
    description: (
      'Collapse or expand the left Diagrams Explorer '
      + '(ux-lab LeftPane pattern).'
    ),
  })

  useRegisterAction({
    element_id: 'left-pane:diagrams:filter',
    app: 'explain-project',
    action: 'LEFT_PANE_DIAGRAM_FILTER',
    label: 'Filter diagrams',
    description: 'Filter the diagrams catalog without changing revision.',
  })

  useRegisterAction({
    element_id: 'left-pane:diagrams:propose',
    app: 'explain-project',
    action: 'LEFT_PANE_DIAGRAM_PROPOSE',
    label: 'Start proposal-safe new diagram flow',
    description: (
      'Surface the $ops-excalidraw proposal flow for a new '
      + 'diagram. Display-only; boards are never mutated here.'
    ),
  })

  const diagrams = useMemo(() => {
    const bySource = new Map<string, DiagramEntry>()
    for (const explainer of explainers) {
      if (!explainer.diagram_source) continue
      const entry = bySource.get(explainer.diagram_source) ?? {
        source: explainer.diagram_source,
        verified: false,
        nodes: 0,
        features: [],
      }
      entry.verified = entry.verified
        || explainer.diagram_verified === true
      entry.nodes = Math.max(
        entry.nodes,
        explainer.diagram_nodes ?? 0,
      )
      entry.features.push(explainer.feature_id)
      bySource.set(explainer.diagram_source, entry)
    }
    const all = [...bySource.values()].sort(
      (a, b) => a.source.localeCompare(b.source),
    )
    if (!filter.trim()) return all
    const needle = filter.trim().toLowerCase()
    return all.filter(
      (entry) => entry.source.toLowerCase().includes(needle)
        || entry.features.some(
          (feature) => feature.toLowerCase().includes(needle),
        ),
    )
  }, [explainers, filter])

  return (
    <section
      data-qid="left-pane:diagrams"
      className="rounded-lg border border-zinc-800 bg-zinc-950 p-2"
    >
      <button
        type="button"
        data-qid="left-pane:diagrams:expand"
        data-qs-action="LEFT_PANE_EXPAND"
        title={open ? 'Collapse Diagrams Explorer' : 'Expand Diagrams Explorer'}
        aria-pressed={open}
        className={[
          'flex w-full items-center justify-between gap-2 rounded px-1 py-1',
          'font-mono text-[11px] font-semibold uppercase tracking-wider',
          open ? 'text-cyan-300' : 'text-zinc-400 hover:text-zinc-200',
        ].join(' ')}
        onClick={() => {
          setOpen((value) => !value)
          if (!open) setProposeNote(false)
        }}
      >
        <span className="inline-flex items-center gap-1.5">
          {open
            ? <PanelLeftClose aria-hidden="true" className="size-3.5" />
            : <PanelLeftOpen aria-hidden="true" className="size-3.5" />}
          Diagrams
          <span className="text-zinc-600">{diagrams.length}</span>
        </span>
      </button>

      {open ? (
        <div className="mt-1.5 space-y-1.5">
          <div className="relative">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-zinc-500"
            />
            <input
              data-qid="left-pane:diagrams:filter"
              data-qs-action="LEFT_PANE_DIAGRAM_FILTER"
              title="Filter diagrams by source or feature"
              type="text"
              className={[
                'w-full rounded border border-zinc-700 bg-zinc-950',
                'py-1 pl-7 pr-2 font-mono text-[11px] text-zinc-100',
                'placeholder-zinc-500 outline-none focus:border-cyan-500',
              ].join(' ')}
              placeholder="Filter diagrams…"
              value={filter}
              onChange={(event) => {
                setFilter(event.currentTarget.value)
              }}
              onKeyDown={(event) => {
                if (event.key === 'Escape') setFilter('')
              }}
            />
          </div>

          <div
            data-qid="left-pane:diagrams:list"
            className="max-h-36 space-y-1 overflow-y-auto"
          >
            {diagrams.map((entry) => {
              const id = entry.features[0]
              return (
                <button
                  key={entry.source}
                  type="button"
                  data-qid={`left-pane:diagrams:item:${id}`}
                  data-qs-action="LEFT_PANE_DIAGRAM_SELECT"
                  title={`Select ${entry.source} (${entry.features.join(', ')})`}
                  className={[
                    'flex w-full flex-col gap-0.5 rounded border p-1.5',
                    'border-zinc-800 bg-zinc-950/60 text-left',
                    'hover:border-cyan-500/60 hover:-translate-y-px',
                    'transition-all',
                  ].join(' ')}
                  onClick={() => {
                    void dispatch(
                      'explainer.select',
                      { feature_id: id },
                    )
                  }}
                >
                  <span className="flex items-center gap-1.5 font-mono text-[10px] text-zinc-400">
                    <Network aria-hidden="true" className="size-3" />
                    {entry.source.split('/').pop()}
                    {entry.verified ? (
                      <span className="text-green-400">✓</span>
                    ) : (
                      <span className="text-amber-400">~</span>
                    )}
                  </span>
                  <span className="truncate font-mono text-[10px] text-zinc-500">
                    {entry.nodes} nodes · {entry.features.length} feature(s)
                  </span>
                </button>
              )
            })}
            {diagrams.length === 0 ? (
              <p className="rounded border border-zinc-800 p-1.5 font-mono text-[10px] text-zinc-500">
                No matching diagrams.
              </p>
            ) : null}
          </div>

          <button
            type="button"
            data-qid="left-pane:diagrams:propose"
            data-qs-action="LEFT_PANE_DIAGRAM_PROPOSE"
            title="Start a proposal-safe new diagram flow through $ops-excalidraw"
            className={[
              'inline-flex w-full items-center justify-center gap-1.5 rounded',
              'border border-purple-500/40 bg-purple-500/10 px-2 py-1',
              'font-mono text-[10px] font-semibold text-purple-300',
              'hover:bg-purple-500/20 transition-colors',
            ].join(' ')}
            onClick={() => {
              setProposeNote(true)
              window.dispatchEvent(
                new CustomEvent('cockpit:diagram-propose', {
                  detail: { pane: 'diagrams' },
                }),
              )
            }}
          >
            <Lightbulb aria-hidden="true" className="size-3" />
            Propose new diagram
          </button>
          {proposeNote ? (
            <p className="rounded border border-purple-500/30 bg-purple-500/5 p-1.5 font-mono text-[10px] text-purple-200">
              Proposal flow is $ops-excalidraw-owned: boards are proposed and
              human-accepted; this pane never mutates a board.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
