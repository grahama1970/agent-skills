import type { CockpitState, ExplainerSummary } from './types'
import { useCockpit, useCockpitKeys, useRegisterAction, useSvgHighlight } from './useCockpit'

export function CockpitApp({ initialState, initialExplainers }: { initialState: CockpitState; initialExplainers: ExplainerSummary[] }) {
  const { state, explainers, dispatch } = useCockpit(initialState, initialExplainers)
  useCockpitKeys((type) => void dispatch(type))
  useRegisterAction('cockpit-step-next', () => void dispatch('step.next'))
  useRegisterAction('cockpit-step-previous', () => void dispatch('step.previous'))
  useRegisterAction('cockpit-reveal-source', () => void dispatch('source.reveal.request'))
  useRegisterAction('cockpit-prepare-debugger', () => void dispatch('debugger.prepare.request'))

  return (
    <main className="h-dvh overflow-hidden bg-zinc-950 p-4 text-zinc-50" data-qid="explain-project-cockpit">
      <header className="mb-4 flex h-14 items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900/80 px-4">
        <div className="text-sm uppercase tracking-wide text-zinc-400">{state.route?.status ?? 'NO_MATCH'}</div>
        <div className="text-lg font-semibold">Revision {state.revision}</div>
        <div className="text-lg">{state.selection ? `${state.selection.step_index + 1} / ${state.selection.step_count}` : 'No explainer'}</div>
      </header>
      <section className="grid h-[calc(100dvh-104px)] grid-cols-[280px_minmax(0,1fr)_440px] gap-4">
        <InputRail explainers={explainers} dispatch={dispatch} />
        <TeleprompterStage state={state} dispatch={dispatch} />
        <EvidenceRail state={state} dispatch={dispatch} />
      </section>
    </main>
  )
}

function InputRail({ explainers, dispatch }: { explainers: ExplainerSummary[]; dispatch: (type: string, payload?: Record<string, unknown>) => Promise<void> }) {
  return (
    <aside className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/70 p-3">
      <input data-qid="question-input" data-qs-action="question.manual" title="Paste interview question" className="w-full rounded-lg bg-zinc-950 p-3 text-base" placeholder="Paste question" onKeyDown={(e) => { if (e.key === 'Enter') void dispatch('question.manual', { text: e.currentTarget.value }) }} />
      <button data-qid="paste-explainer" data-qs-action="explainer.import" title="Paste a session-only explainer" className="w-full rounded-lg bg-cyan-500 px-3 py-2 font-semibold text-zinc-950">Paste explainer</button>
      <div className="space-y-2">
        {explainers.map((ex) => <button key={ex.feature_id} data-qid={`explainer-${ex.feature_id}`} data-qs-action="explainer.select" title={`Select ${ex.title}`} className="w-full rounded-lg border border-zinc-700 p-2 text-left text-sm" onClick={() => void dispatch('explainer.select', { feature_id: ex.feature_id })}>{ex.title}</button>)}
      </div>
    </aside>
  )
}

function TeleprompterStage({ state, dispatch }: { state: CockpitState; dispatch: (type: string) => Promise<void> }) {
  return (
    <section className="rounded-2xl border border-cyan-500/30 bg-black p-8 shadow-2xl">
      <h1 className="mb-8 max-w-[18ch] text-5xl font-bold leading-tight">{state.teleprompter.title ?? 'Select an explainer'}</h1>
      <ul className="max-w-[30ch] space-y-5 text-[40px] leading-[1.14]">
        {state.teleprompter.bullets.map((b) => <li key={b}>• {b}</li>)}
      </ul>
      <div className="mt-8 rounded-xl border border-zinc-800 p-3 text-lg text-zinc-400">{state.teleprompter.proof_boundary ?? 'No live proof claimed.'}</div>
      <div className="mt-4 flex justify-between text-xl text-zinc-500">
        <button data-qid="step-prev" data-qs-action="step.previous" title="Previous step" onClick={() => void dispatch('step.previous')}>← Previous</button>
        <button data-qid="step-next" data-qs-action="step.next" title="Next step" onClick={() => void dispatch('step.next')}>Next →</button>
      </div>
    </section>
  )
}

function EvidenceRail({ state, dispatch }: { state: CockpitState; dispatch: (type: string) => Promise<void> }) {
  const activeNodes = useSvgHighlight(state.diagram.active_node_ids)
  return (
    <aside className="space-y-3 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/70 p-3 text-sm">
      <section className="rounded-lg bg-zinc-950 p-3">
        <h2 className="font-semibold">Source</h2>
        <p>{state.source.location ? `${state.source.location.file}:${state.source.location.start_line}-${state.source.location.end_line}` : 'No source selected'}</p>
        <p className="text-zinc-400">{state.source.explanation}</p>
        <button data-qid="reveal-source" data-qs-action="source.reveal.request" title="Reveal source through debugger bridge" className="mt-2 rounded bg-zinc-800 px-2 py-1" onClick={() => void dispatch('source.reveal.request')}>Reveal source</button>
      </section>
      <section className="rounded-lg bg-zinc-950 p-3">
        <h2 className="font-semibold">Debugger target only</h2>
        <p>{state.debugger.target ? `${state.debugger.target.file}:${state.debugger.target.line}` : 'No target'}</p>
        <p className="text-zinc-400">{state.debugger.target?.proves}</p>
        <button data-qid="prepare-debugger" data-qs-action="debugger.prepare.request" title="Prepare debugger target without running" className="mt-2 rounded bg-zinc-800 px-2 py-1" onClick={() => void dispatch('debugger.prepare.request')}>Prepare target</button>
      </section>
      <section className="h-[360px] rounded-lg bg-zinc-950 p-3">
        <h2 className="font-semibold">Diagram</h2>
        <p data-qid="active-svg-nodes" title="Active SVG nodes" className="text-cyan-300">{activeNodes || 'No active node'}</p>
        <p className="text-zinc-500">SVG highlight only; no Excalidraw mutation from navigation.</p>
      </section>
    </aside>
  )
}
