import {
  ClipboardPaste,
  CornerDownLeft,
} from 'lucide-react'

import {
  useState,
} from 'react'

import type {
  Dispatch,
} from '../useCockpit'

import {
  useRegisterAction,
} from '../useRegisterAction'

import {
  DiagramsExplorerPane,
} from './DiagramsExplorerPane'

import {
  ExplainerHistory,
} from './ExplainerHistory'

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
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pastedJson, setPastedJson] = useState('')

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
    }
  }

  return (
    <aside
      className={[
        'flex h-full min-h-0 flex-col gap-2.5 overflow-hidden rounded-xl',
        'border border-zinc-800',
        'bg-zinc-900/70 p-2.5',
      ].join(' ')}
    >
      <div className="flex shrink-0 flex-col gap-1.5">
        <h2 className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
          Question intake
        </h2>
        <p className="text-xs leading-snug text-zinc-400">
          Route the interviewer’s question without changing the proof contract.
        </p>
      </div>

      <div className="flex w-full shrink-0 flex-col gap-1.5">
        <textarea
          data-qid="cockpit:question:manual-input"
          data-qs-action="QUESTION_MANUAL_EDIT"
          title="Paste or type an interview question"
          rows={2}
          className={[
            'w-full resize-none rounded-lg border border-zinc-700',
            'bg-zinc-950 p-2 text-sm leading-snug text-zinc-100 min-h-[72px]',
            'placeholder-zinc-500 outline-none focus:border-cyan-500',
          ].join(' ')}
          placeholder="Paste question (Press / to focus, Enter to route)"
          value={question}
          onChange={(event) => {
            setQuestion(
              event.currentTarget.value,
            )
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
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
            'inline-flex w-full min-h-[38px] items-center justify-center gap-2 rounded-lg border border-cyan-500/80',
            'bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-zinc-100',
            'hover:bg-cyan-500 active:bg-cyan-700 transition-colors',
          ].join(' ')}
          onClick={() => {
            void submitQuestion()
          }}
        >
          <span>Ask Question</span>
          <CornerDownLeft aria-hidden="true" className="size-3.5 opacity-70" />
        </button>
      </div>

      <ExplainerNavigator
        explainers={explainers}
        state={state}
        dispatch={dispatch}
      />

      <ExplainerHistory
        explainers={explainers}
        state={state}
        dispatch={dispatch}
      />

      <DiagramsExplorerPane
        explainers={explainers}
        dispatch={dispatch}
      />

      <button
        type="button"
        data-qid="cockpit:explainer:paste-toggle"
        data-qs-action="EXPLAINER_IMPORT_TOGGLE"
        title="Paste a session-only explainer"
        className={[
          'inline-flex w-full min-h-[38px] shrink-0 items-center justify-center gap-2 rounded-lg bg-cyan-500/20 border border-cyan-500/40',
          'px-3 py-1.5 text-xs font-semibold text-cyan-200',
          'hover:bg-cyan-500 hover:text-zinc-950 transition-all',
        ].join(' ')}
        onClick={() => {
          setPasteOpen(
            (open) => !open,
          )
        }}
      >
        <ClipboardPaste aria-hidden="true" className="size-3.5" />
        <span>Paste explainer</span>
      </button>

      {pasteOpen ? (
        <div className="space-y-2">
          <textarea
            data-qid="cockpit:explainer:paste-editor"
            data-qs-action="EXPLAINER_IMPORT_EDIT"
            title="Paste one project.feature_explainer.v1 JSON object"
            className={[
              'h-32 w-full resize-none rounded-lg border border-zinc-800',
              'bg-zinc-950 p-2 font-mono text-xs text-zinc-200',
              'outline-none focus:border-cyan-500',
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
              'w-full min-h-[44px] rounded-lg border border-cyan-500 px-3 py-1.5',
              'text-xs font-semibold text-cyan-300 hover:bg-cyan-950/50',
            ].join(' ')}
            onClick={() => {
              void applyImport()
            }}
          >
            Validate + import
          </button>
        </div>
      ) : null}

    </aside>
  )
}
