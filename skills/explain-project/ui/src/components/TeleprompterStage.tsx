import {
  ChevronLeft,
  ChevronRight,
  Gauge,
  Lightbulb,
  ShieldAlert,
} from 'lucide-react'

import {
  useEffect,
  useRef,
  useState,
} from 'react'

import {
  Kbd,
} from './Kbd'

import type {
  Dispatch,
} from '../useCockpit'

import {
  useRegisterAction,
} from '../useRegisterAction'

import type {
  CockpitState,
} from '../types'

/** Interpolate {{key}} template vars; unbound keys render [key]. */
function interpolateVars(
  text: string,
  vars: Record<string, string>,
): string {
  return text.replace(
    /\{\{(\w+)\}\}/g,
    (_, key: string) => vars[key] ?? `[${key}]`,
  )
}

function paceStatus(wpm: number): {
  label: string
  color: string
} {
  if (wpm > 170) {
    return { label: 'TOO FAST', color: '#ef4444' }
  }
  if (wpm < 110) {
    return { label: 'TOO SLOW', color: '#f59e0b' }
  }
  return { label: 'OPTIMAL PACE', color: '#10b981' }
}

export function TeleprompterStage({
  state,
  dispatch,
}: {
  state: CockpitState
  dispatch: Dispatch
}) {
  useRegisterAction({
    element_id: 'cockpit:step:previous',
    app: 'explain-project',
    action: 'STEP_PREVIOUS',
    label: 'Previous explanation step',
    description: (
      'Move left one explainer step through '
      + 'the single reducer only.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:step:next',
    app: 'explain-project',
    action: 'STEP_NEXT',
    label: 'Next explanation step',
    description: (
      'Move right one explainer step through '
      + 'the single reducer only.'
    ),
  })

  useRegisterAction({
    element_id: 'cockpit:stage:deep-dive',
    app: 'explain-project',
    action: 'STEP_DEEP_DIVE_TOGGLE',
    label: 'Toggle deep-dive drawer for the current step',
    description: (
      'Reveal the drill-down material: source explanation, '
      + 'debugger target, diagram nodes. Read-only.'
    ),
  })

  const activeQuestion = state.question?.text ?? state.route?.question

  // Derived pace: words on this step / dwell time on this step.
  // NOT speech recognition — honest telemetry from step dwell.
  const selection = state.selection
  const stepKey = selection
    ? `${selection.feature_id}:${selection.step_index}`
    : 'none'
  const enteredAt = useRef(Date.now())
  const [dwellMs, setDwellMs] = useState(0)
  useEffect(() => {
    enteredAt.current = Date.now()
    setDwellMs(0)
  }, [stepKey])
  useEffect(() => {
    const timer = window.setInterval(() => {
      setDwellMs(Date.now() - enteredAt.current)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])
  const stepWords = [
    state.teleprompter.title ?? '',
    ...state.teleprompter.bullets,
  ].join(' ').split(/\s+/).filter(Boolean).length
  const minutes = dwellMs / 60_000
  const wpm = minutes >= 0.05
    ? Math.round(stepWords / minutes)
    : 0
  const pace = wpm > 0 ? paceStatus(wpm) : null

  const vars: Record<string, string> = {
    feature: selection?.feature_id ?? '',
    project: 'oai-trial',
    step: state.teleprompter.title ?? '',
  }

  return (
    <section
      data-qid="cockpit:teleprompter:stage"
      data-revision={state.teleprompter.revision}
      className={[
        'cockpit-stage',
        'flex h-full min-w-0 flex-col justify-between overflow-hidden rounded-2xl',
        'border border-cyan-500/30',
        'bg-black p-4 shadow-2xl',
      ].join(' ')}
    >
      <div
        className={[
          'cockpit-stage__meta',
          'flex items-center justify-between gap-3 shrink-0',
        ].join(' ')}
      >
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/40 bg-cyan-950/60 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-cyan-300">
            <Gauge aria-hidden="true" className="size-3" />
            {state.teleprompter.confidence
              ? `${state.teleprompter.confidence} confidence`
              : 'No confidence'}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs font-medium uppercase tracking-wider text-zinc-400">
            <ShieldAlert aria-hidden="true" className="size-3" />
            {state.teleprompter.verification
              === 'debugger_proof_received'
              ? 'Debugger proof'
              : 'Narrative only'}
          </span>
          {pace ? (
            <span
              className="pace-badge"
              style={{ borderColor: pace.color }}
              title={`Derived from step dwell time (not speech recognition): ${stepWords} words over ${Math.round(dwellMs / 1000)}s`}
            >
              <span
                className="pace-dot"
                style={{ background: pace.color }}
              />
              {wpm} WPM • {pace.label}
            </span>
          ) : null}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col justify-center space-y-3 py-2">
        {activeQuestion ? (
          <div
            data-qid="cockpit:stage:active-question"
            data-revision={state.revision}
            className={[
              'shrink-0 rounded-xl border border-cyan-500/30 bg-cyan-950/20',
              'p-2.5 text-cyan-100 shadow-sm shadow-cyan-950/40',
            ].join(' ')}
          >
            <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.22em] text-cyan-300">
              Active interview question
            </div>
            <p className="line-clamp-2 text-sm font-semibold leading-snug text-cyan-50 xl:text-base">
              {activeQuestion}
            </p>
          </div>
        ) : null}

        <div>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-[0.28em] text-cyan-300">
            Speaker cue
          </p>

          <h1
            className={[
              'max-w-[24ch]',
              'text-3xl font-extrabold tracking-tight leading-[1.12]',
              'text-balance xl:text-4xl text-white',
            ].join(' ')}
          >
            {interpolateVars(
              state.teleprompter.title ?? 'Select an explainer',
              vars,
            )}
          </h1>
        </div>

        <ul
          className={[
            'max-w-[36ch] space-y-3.5',
            'text-[clamp(1.05rem,1.35vw,1.55rem)]',
            'leading-[1.4] text-zinc-100 font-normal',
          ].join(' ')}
        >
          {state.teleprompter.bullets.map(
            (bullet) => (
              <li key={bullet} className="flex items-start gap-3 bg-zinc-950/70 border border-zinc-800/80 rounded-xl p-2.5 shadow-sm">
                <span className="text-cyan-400 font-bold shrink-0 mt-0.5">•</span>
                <span className="text-zinc-100">{interpolateVars(bullet, vars)}</span>
              </li>
            ),
          )}
        </ul>

        <div
          className={[
            'rounded-xl',
            'border-l-4 border-l-amber-400 border-y border-r border-amber-500/30',
            'bg-amber-950/20 p-2.5',
            'text-xs text-amber-100/90',
          ].join(' ')}
        >
          <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.24em] text-amber-300">
            Proof boundary
          </div>
          {state.teleprompter.proof_boundary
            ?? 'No live proof claimed.'}
        </div>

        {state.source.location ? (
          <details className="deep-dive-accordion">
            <summary
              data-qid="cockpit:stage:deep-dive"
              data-qs-action="STEP_DEEP_DIVE_TOGGLE"
              title="Reveal drill-down material for this step"
              className="deep-dive-trigger inline-flex items-center gap-2"
            >
              <Lightbulb aria-hidden="true" className="size-3.5" />
              If asked for drill-down: {state.teleprompter.title}
            </summary>
            <div className="deep-dive-content space-y-1">
              <div>
                Source: {state.source.location.file}
                :{state.source.location.start_line}
                -{state.source.location.end_line}
              </div>
              <div>
                {interpolateVars(
                  state.source.explanation ?? '',
                  vars,
                )}
              </div>
              {state.debugger.target ? (
                <div>
                  Debugger: {state.debugger.target.file}
                  :{state.debugger.target.line} — proves:{' '}
                  {state.debugger.target.proves}
                </div>
              ) : null}
              {state.diagram.active_node_ids.length ? (
                <div>
                  Diagram nodes:{' '}
                  {state.diagram.active_node_ids.join(', ')}
                </div>
              ) : null}
            </div>
          </details>
        ) : null}
      </div>

      <div
        className={[
          'flex items-center justify-between shrink-0',
          'pt-2 border-t border-zinc-800/80',
        ].join(' ')}
      >
        <button
          type="button"
          data-qid="cockpit:step:previous"
          data-qs-action="STEP_PREVIOUS"
          title="Previous step (ArrowLeft or K)"
          className={[
            'flex items-center gap-2 rounded-lg border border-zinc-700/80',
            'bg-zinc-900 px-4 py-2 min-h-[44px] text-sm font-semibold text-zinc-300',
            'hover:border-zinc-500 hover:bg-zinc-800 transition-all',
          ].join(' ')}
          onClick={() => {
            void dispatch('step.previous')
          }}
        >
          <ChevronLeft aria-hidden="true" className="size-4" />
          <span>Previous</span>
          <Kbd>← / K</Kbd>
        </button>

        <button
          type="button"
          data-qid="cockpit:step:next"
          data-qs-action="STEP_NEXT"
          title="Next step (ArrowRight or J)"
          className={[
            'flex items-center gap-2 rounded-lg border border-cyan-500/60',
            'bg-cyan-950/50 px-5 py-2 min-h-[44px] text-sm font-semibold text-cyan-200',
            'hover:bg-cyan-500 hover:text-zinc-950 transition-all shadow-sm shadow-cyan-950/50',
          ].join(' ')}
          onClick={() => {
            void dispatch('step.next')
          }}
        >
          <span>Next</span>
          <Kbd>→ / J</Kbd>
          <ChevronRight aria-hidden="true" className="size-4" />
        </button>
      </div>
    </section>
  )
}
