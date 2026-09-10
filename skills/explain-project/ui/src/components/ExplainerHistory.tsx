import {
  Search,
} from 'lucide-react'

import {
  useEffect,
  useState,
} from 'react'

import {
  useFilteredExplainers,
  type Dispatch,
} from '../useCockpit'

import {
  useRegisterAction,
} from '../useRegisterAction'

import type {
  CockpitState,
  ExplainerSummary,
} from '../types'

function ExplainerButton({
  explainer,
  dispatch,
  selected,
  index,
  revision,
}: {
  explainer: ExplainerSummary
  dispatch: Dispatch
  selected: boolean
  index: number
  revision: number
}) {
  const id = explainer.feature_id
  const qid = `cockpit:explainer:item:${id}`

  useRegisterAction({
    element_id: qid,
    app: 'explain-project',
    action: 'EXPLAINER_SELECT',
    label: `Select ${explainer.title}`,
    description: (
      'Select one explainer and project its first '
      + 'synchronized cockpit step.'
    ),
    params: {
      feature_id: explainer.feature_id,
    },
  })

  return (
    <button
      type="button"
      data-qid={`cockpit:explainer:item:${id}`}
      data-qs-action="EXPLAINER_SELECT"
      title={`Load explainer: ${explainer.title}`}
      aria-current={selected ? 'true' : undefined}
      className={[
        'w-full text-left rounded-lg border p-1.5 min-h-[44px] transition-all',
        'flex flex-col gap-0.5',
        selected
          ? 'border-cyan-500 bg-cyan-950/40 text-cyan-100 shadow-sm shadow-cyan-950'
          : 'border-zinc-800 bg-zinc-950/60 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-900',
      ].join(' ')}
      onClick={() => {
        void dispatch(
          'explainer.select',
          {
            feature_id: explainer.feature_id,
          },
        )
      }}
    >
      <span className="flex items-center justify-between gap-2 font-mono text-[11px] uppercase">
        <span className="font-semibold text-cyan-400">#{index + 1}</span>
        <span className="text-zinc-500">r{selected ? revision : 1}</span>
      </span>

      <span className="line-clamp-2 text-sm font-semibold leading-snug">
        {explainer.title || explainer.question}
      </span>

      <span className="flex items-center gap-1.5 text-xs text-zinc-400 font-mono">
        <span>{explainer.question_family}</span>
        <span>·</span>
        <span className="text-cyan-300 font-medium">{explainer.steps} steps</span>
      </span>
    </button>
  )
}

function FamilyPill({
  family,
  active,
  onPick,
}: {
  family: string
  active: boolean
  onPick: (family: string | null) => void
}) {
  const id = family

  useRegisterAction({
    element_id: `cockpit:explainer:family-filter:${id}`,
    app: 'explain-project',
    action: 'EXPLAINER_FAMILY_FILTER_SET',
    label: `Filter explainers by ${family}`,
    description: (
      'Set the explainer filter to one family '
      + 'without changing cockpit revision.'
    ),
    params: { family },
  })

  return (
    <button
      type="button"
      data-qid={`cockpit:explainer:family-filter:${id}`}
      data-qs-action="EXPLAINER_FAMILY_FILTER_SET"
      title={`Show only ${family} explainers`}
      className={[
        'rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold',
        'uppercase tracking-wide transition-colors',
        active
          ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200'
          : 'border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-500',
      ].join(' ')}
      onClick={() => {
        onPick(active ? null : family)
      }}
    >
      {family}
    </button>
  )
}

export function ExplainerHistory({
  explainers,
  state,
  dispatch,
}: {
  explainers: ExplainerSummary[]
  state: CockpitState
  dispatch: Dispatch
}) {
  useRegisterAction({
    element_id: 'cockpit:explainer:search-input',
    app: 'explain-project',
    action: 'EXPLAINER_SEARCH_EDIT',
    label: 'Search explainers',
    description: (
      'Filter the in-session explainer catalog without '
      + 'changing cockpit revision.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:explainer:family-filter:all',
    app: 'explain-project',
    action: 'EXPLAINER_FAMILY_FILTER_SET',
    label: 'Clear explainer family filter',
    description: 'Show all explainers regardless of family.',
  })

  const [query, setQuery] = useState('')

  const filtered = useFilteredExplainers(
    explainers,
    query,
  )

  useEffect(() => {
    const clearSearch = () => setQuery('')
    window.addEventListener('cockpit:explainer:clear-search', clearSearch)
    return () => window.removeEventListener('cockpit:explainer:clear-search', clearSearch)
  }, [])

  const families = Array.from(
    new Set(
      explainers.map(
        (explainer) => explainer.question_family,
      ),
    ),
  ).sort()

  const activeFamily = query.startsWith('family:')
    ? query.slice('family:'.length)
    : null

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1.5 border-t border-zinc-800 pt-2">
      <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-zinc-400">
        <span>Past explainers</span>
        <span className="font-mono text-[11px] text-cyan-400">
          {explainers.length} total
        </span>
      </div>

      <div className="relative">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-zinc-500"
        />
        <input
          data-qid="cockpit:explainer:search-input"
          data-qs-action="EXPLAINER_SEARCH_EDIT"
          title="Search and filter past project explainers"
          type="text"
          className={[
            'w-full rounded-lg border border-zinc-700 bg-zinc-950',
            'py-1.5 pl-8 pr-3 text-sm text-zinc-100 placeholder-zinc-500',
            'outline-none focus:border-cyan-500 min-h-[38px]',
          ].join(' ')}
          placeholder="Filter explainers…"
          value={query}
          onChange={(event) => {
            setQuery(
              event.currentTarget.value,
            )
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setQuery('')
            }
          }}
        />
      </div>

      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          data-qid="cockpit:explainer:family-filter:all"
          data-qs-action="EXPLAINER_FAMILY_FILTER_SET"
          title="Show all explainers"
          className={[
            'rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold',
            'uppercase tracking-wide transition-colors',
            activeFamily === null
              ? 'border-cyan-400 bg-cyan-500/20 text-cyan-200'
              : 'border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-500',
          ].join(' ')}
          onClick={() => setQuery('')}
        >
          all
        </button>
        {families.map((family) => (
          <FamilyPill
            key={family}
            family={family}
            active={activeFamily === family}
            onPick={(next) => {
              setQuery(
                next ? `family:${next}` : '',
              )
            }}
          />
        ))}
      </div>

      <div
        data-qid="cockpit:explainer:history-list"
        className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1"
      >
        {filtered.length > 0 ? filtered.map((explainer, index) => (
          <ExplainerButton
            key={explainer.feature_id}
            explainer={explainer}
            dispatch={dispatch}
            selected={state.selection?.feature_id === explainer.feature_id}
            index={index}
            revision={state.revision}
          />
        )) : (
          <p className="rounded-lg border border-zinc-800 bg-zinc-950/70 p-2.5 text-sm text-zinc-500">
            No matching explainers.
          </p>
        )}
      </div>
    </div>
  )
}
