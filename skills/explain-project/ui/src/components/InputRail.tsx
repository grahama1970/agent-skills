import {
  useState,
} from 'react'

import type {
  Dispatch,
} from '../useCockpit'

import {
  useFilteredExplainers,
} from '../useCockpit'

import {
  useRegisterAction,
} from '../useRegisterAction'

import {
  ExplainerNavigator,
} from './ExplainerNavigator'

import type {
  CockpitState,
  ExplainerSummary,
} from '../types'

interface Props {
  explainers: ExplainerSummary[]
  state: CockpitState
  dispatch: Dispatch
  importRecord: (
    record: unknown,
  ) => Promise<boolean>
}

function ExplainerButton({
  explainer,
  dispatch,
  selected,
}: {
  explainer: ExplainerSummary
  dispatch: Dispatch
  selected: boolean
}) {
  const id = explainer.feature_id
  const qid = (
    `cockpit:explainer:select:${id}`
  )

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
      data-qid={`cockpit:explainer:select:${id}`}
      data-qs-action="EXPLAINER_SELECT"
      title={`Select ${explainer.title}`}
      aria-current={selected ? 'true' : undefined}
      className={[
        'w-full rounded-lg border p-3 text-left',
        selected
          ? 'border-cyan-300 bg-cyan-950/30 text-zinc-50'
          : 'border-zinc-700 text-zinc-200 hover:border-zinc-400',
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
      <span className="block font-medium">
        {explainer.title}
      </span>

      <span className="text-xs text-zinc-500">
        {explainer.question_family}
        {' · '}
        {explainer.steps}
        {' steps'}
      </span>
    </button>
  )
}

export function InputRail({
  explainers,
  state,
  dispatch,
  importRecord,
}: Props) {
  useRegisterAction({
    element_id: 'cockpit:question:manual-input',
    app: 'explain-project',
    action: 'QUESTION_MANUAL_EDIT',
    label: 'Edit manual interview question',
    description: (
      'Edit a pasted or typed interview question '
      + 'before deterministic routing.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:question:manual-submit',
    app: 'explain-project',
    action: 'QUESTION_MANUAL_SUBMIT',
    label: 'Submit manual interview question',
    description: (
      'Route the current interview question through '
      + 'the deterministic explainer router.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:explainer:search',
    app: 'explain-project',
    action: 'EXPLAINER_SEARCH_SET',
    label: 'Search explainers',
    description: (
      'Filter the in-session explainer catalog without '
      + 'changing cockpit revision.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:explainer:paste-toggle',
    app: 'explain-project',
    action: 'EXPLAINER_IMPORT_TOGGLE',
    label: 'Open explainer paste panel',
    description: (
      'Show or hide the strict session-only '
      + 'explainer import editor.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:explainer:paste-editor',
    app: 'explain-project',
    action: 'EXPLAINER_IMPORT_EDIT',
    label: 'Edit pasted explainer JSON',
    description: (
      'Edit one project.feature_explainer.v1 JSON '
      + 'object before strict server validation.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:explainer:paste-apply',
    app: 'explain-project',
    action: 'EXPLAINER_IMPORT_APPLY',
    label: 'Import pasted explainer',
    description: (
      'Strictly validate and add or replace one '
      + 'in-session explainer record.'
    ),
  })

  const [question, setQuestion] = useState('')
  const [query, setQuery] = useState('')
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pastedJson, setPastedJson] = useState('')

  const filtered = useFilteredExplainers(
    explainers,
    query,
  )

  async function submitQuestion(): Promise<void> {
    const text = question.trim()

    if (!text) return

    await dispatch(
      'question.manual',
      { text },
    )
  }

  async function applyImport(): Promise<void> {
    try {
      const record = JSON.parse(
        pastedJson,
      ) as unknown

      if (await importRecord(record)) {
        setPastedJson('')
        setPasteOpen(false)
      }
    } catch {
      // Malformed JSON never leaves the browser.
      // The server remains authority for valid records.
    }
  }

  return (
    <aside
      className={[
        'space-y-3 overflow-hidden rounded-xl',
        'border border-zinc-800',
        'bg-zinc-900/70 p-3',
      ].join(' ')}
    >
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">
          Question intake
        </h2>
        <p className="mt-1 text-sm text-zinc-400">
          Route the interviewer’s question without changing the proof contract.
        </p>
      </div>

      <div className="flex gap-2">
        <input
          data-qid="cockpit:question:manual-input"
          data-qs-action="QUESTION_MANUAL_EDIT"
          title="Paste or type an interview question"
          className={[
            'min-w-0 flex-1 rounded-lg',
            'bg-zinc-950 p-3 text-base',
            'outline-none ring-cyan-500',
            'focus:ring-2',
          ].join(' ')}
          placeholder="Paste interview question"
          value={question}
          onChange={(event) => {
            setQuestion(
              event.currentTarget.value,
            )
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              void submitQuestion()
            }
          }}
        />

        <button
          type="button"
          data-qid="cockpit:question:manual-submit"
          data-qs-action="QUESTION_MANUAL_SUBMIT"
          title="Route the current interview question"
          className={[
            'rounded-lg border',
            'border-cyan-500 px-3',
            'text-cyan-300',
          ].join(' ')}
          onClick={() => {
            void submitQuestion()
          }}
        >
          Ask
        </button>
      </div>

      <ExplainerNavigator
        explainers={explainers}
        state={state}
        dispatch={dispatch}
      />

      <input
        data-qid="cockpit:explainer:search"
        data-qs-action="EXPLAINER_SEARCH_SET"
        title="Search existing explainers"
        className={[
          'w-full rounded-lg bg-zinc-950',
          'p-2 text-sm outline-none',
          'ring-cyan-500 focus:ring-2',
        ].join(' ')}
        placeholder="Find explainer"
        value={query}
        onChange={(event) => {
          setQuery(
            event.currentTarget.value,
          )
        }}
      />

      <button
        type="button"
        data-qid="cockpit:explainer:paste-toggle"
        data-qs-action="EXPLAINER_IMPORT_TOGGLE"
        title="Paste a session-only explainer"
        className={[
          'w-full rounded-lg bg-cyan-500',
          'px-3 py-2 font-semibold',
          'text-zinc-950',
        ].join(' ')}
        onClick={() => {
          setPasteOpen(
            (open) => !open,
          )
        }}
      >
        Paste explainer
      </button>

      {pasteOpen ? (
        <div className="space-y-2">
          <textarea
            data-qid="cockpit:explainer:paste-editor"
            data-qs-action="EXPLAINER_IMPORT_EDIT"
            title="Paste one project.feature_explainer.v1 JSON object"
            className={[
              'h-40 w-full resize-none rounded-lg',
              'bg-zinc-950 p-2 font-mono text-xs',
              'outline-none ring-cyan-500',
              'focus:ring-2',
            ].join(' ')}
            value={pastedJson}
            onChange={(event) => {
              setPastedJson(
                event.currentTarget.value,
              )
            }}
          />

          <button
            type="button"
            data-qid="cockpit:explainer:paste-apply"
            data-qs-action="EXPLAINER_IMPORT_APPLY"
            title="Validate and import pasted explainer"
            className={[
              'w-full rounded-lg border',
              'border-cyan-500 px-3 py-2',
              'text-cyan-300',
            ].join(' ')}
            onClick={() => {
              void applyImport()
            }}
          >
            Validate + import
          </button>
        </div>
      ) : null}

      <div className="space-y-2 overflow-y-auto pr-1">
        {filtered.map((explainer) => (
          <ExplainerButton
            key={explainer.feature_id}
            explainer={explainer}
            dispatch={dispatch}
            selected={state.selection?.feature_id === explainer.feature_id}
          />
        ))}
      </div>
    </aside>
  )
}
