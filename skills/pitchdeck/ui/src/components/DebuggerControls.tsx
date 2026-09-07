import { useEffect, useRef, useState } from 'react'
import { Bug, CodeXml, Play, Square, StepForward, Eye } from 'lucide-react'
import { useRegisterAction } from '../hooks'
import { Button } from './ui/button'

interface DebugState {
  status: string
  mapping?: { file: string; line: number; endLine?: number; endColumn?: number; launch?: string; locals?: string[] } | null
  concepts?: { id: string; label: string }[]
  session?: { vscodeSessionId: string; stopSequence: number; status?: string }
  error?: string
  receipt?: { status: string; updatedAt?: string; [key: string]: unknown }
  busy?: boolean
}
export function DebuggerControls({ slideId }: { slideId: string }) {
  const [sync, setSync] = useState(false)
  const [state, setState] = useState<DebugState>({ status: 'not-connected' })
  const [busy, setBusy] = useState(false)
  const [selection, setSelection] = useState({ slideId: '', id: '' })
  const conceptId = selection.slideId === slideId ? selection.id : ''
  const key = `${slideId}:${conceptId}`
  const current = useRef(key)
  current.current = key
  useRegisterAction('deck:debug:sync', { app: 'pitchdeck', action: 'DECK_DEBUG_SYNC', label: 'Sync with VS Code', description: 'Reveal explicitly mapped code when the slide changes; never execute automatically' })
  useRegisterAction('deck:debug:start', { app: 'pitchdeck', action: 'DECK_DEBUG_START', label: 'Run debugger', description: 'Start mapped launch configuration and stop at its breakpoint' })
  useRegisterAction('deck:debug:inspect', { app: 'pitchdeck', action: 'DECK_DEBUG_INSPECT', label: 'Inspect paused locals', description: 'Read the stopped frame through the debugger bridge' })
  useRegisterAction('deck:debug:continue', { app: 'pitchdeck', action: 'DECK_DEBUG_CONTINUE', label: 'Continue', description: 'Explicitly continue the bound debug session' })
  useRegisterAction('deck:debug:stepOver', { app: 'pitchdeck', action: 'DECK_DEBUG_STEP', label: 'Step over', description: 'Step the bound debugger session once' })
  useRegisterAction('deck:debug:terminate', { app: 'pitchdeck', action: 'DECK_DEBUG_STOP', label: 'Stop debugger', description: 'Terminate only the bound debugger session' })
  const act = async (action: string) => {
    const forSelection = key
    setBusy(true)
    try {
      const response = await fetch('/api/debugger', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Pitchdeck-Control': '1' }, body: JSON.stringify({ action, slide_id: slideId, concept_id: conceptId, session_id: state.session?.vscodeSessionId, stop_sequence: state.session?.stopSequence }) })
      const result = await response.json()
      if (current.current === forSelection) setState(previous => ({ ...result, concepts: previous.concepts }))
    } catch (error) { setState({ status: 'unavailable', error: String(error) }) }
    finally { setBusy(false) }
  }
  useEffect(() => {
    let cancelled = false
    const refresh = () => fetch(`/api/debugger?slide=${encodeURIComponent(slideId)}&concept=${encodeURIComponent(conceptId)}`).then(r => r.json()).then(value => { if (!cancelled) setState(value) }).catch(error => { if (!cancelled) setState({ status: 'unavailable', error: String(error) }) })
    void refresh()
    const timer = setInterval(refresh, 2500)
    return () => { cancelled = true; clearInterval(timer) }
  }, [slideId, conceptId])
  useEffect(() => { if (sync) void act('reveal') }, [slideId, conceptId, sync])
  useEffect(() => {
    if (!sync) return
    const select = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return
      const element = event.target.closest('[data-element-id]')
      const id = element?.getAttribute('data-element-id')
      if (id && state.concepts?.some(c => c.id === id)) setSelection({ slideId, id })
    }
    document.addEventListener('click', select)
    return () => document.removeEventListener('click', select)
  }, [sync, slideId, state.concepts])
  const conceptKey = state.concepts?.map(c => c.id).join('|') || ''
  useEffect(() => {
    if (!sync || !conceptKey) return
    const root = Array.from(document.querySelectorAll<HTMLElement>('[data-build]')).find(e => e.closest('[data-qid^="deck:slide:"]')?.getAttribute('data-qid') === `deck:slide:${slideId}`)
    if (!root) return
    const followBuild = () => {
      const visible = Array.from(root.querySelectorAll<HTMLElement>('[data-animation-target]')).filter(e => !e.inert && e.style.visibility !== 'hidden' && e.getAnimations().length && state.concepts?.some(c => c.id === e.dataset.animationTarget))
      const id = visible.at(-1)?.dataset.animationTarget || ''
      setSelection(previous => previous.slideId === slideId && previous.id === id ? previous : { slideId, id })
    }
    const observer = new MutationObserver(followBuild)
    observer.observe(root, { attributes: true, attributeFilter: ['data-build'] })
    return () => observer.disconnect()
  }, [sync, slideId, conceptKey])
  const unavailable = busy || state.busy || !state.mapping
  return <div className="flex max-w-full flex-wrap items-center gap-2 text-sm">
    <Button title="Sync with VS Code — reveal mapped code, without running it" data-qid="deck:debug:sync" data-qs-action="DECK_DEBUG_SYNC" variant={sync ? 'secondary' : 'ghost'} aria-pressed={sync} onClick={() => setSync(v => !v)}><CodeXml size={16} aria-hidden /> Sync VS Code</Button>
    {sync ? <>
      {!!state.concepts?.length && <label className="text-xs text-slate-300">Code for <select aria-label="Code concept" data-qid="deck:debug:concept" value={conceptId} onChange={event => setSelection({ slideId, id: event.target.value })} className="max-w-80 rounded border border-slate-600 bg-slate-900 p-1 text-slate-100"><option value="">Slide overview</option>{state.concepts.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>}
      <span role="status" className="max-w-full break-words text-xs text-slate-400">{state.mapping ? `${state.mapping.file}:${state.mapping.line}–${state.mapping.endLine ?? state.mapping.line}` : 'No slide mapping'} · {busy ? 'requesting…' : `last observed: ${state.status}`}</span>
      {([
        ['start', 'Run debugger at mapped breakpoint', Bug, 'DECK_DEBUG_START'], ['inspect', 'Inspect paused locals', Eye, 'DECK_DEBUG_INSPECT'],
        ['continue', 'Continue execution', Play, 'DECK_DEBUG_CONTINUE'], ['stepOver', 'Step over', StepForward, 'DECK_DEBUG_STEP'], ['terminate', 'Stop bound debugger', Square, 'DECK_DEBUG_STOP'],
      ] as const).map(([action, label, Icon, actionId]) => <Button key={action} title={label} data-qid={`deck:debug:${action}`} data-qs-action={actionId} variant="ghost" size="icon"
        disabled={!!unavailable || (action === 'start' ? !state.mapping?.launch || !!state.session && state.session.status !== 'terminated' : action === 'terminate' ? !state.session || state.session.status === 'terminated' : state.session?.status !== 'paused')} onClick={() => void act(action)}><Icon size={16} aria-hidden /></Button>)}
      {state.error ? <span role="alert" className="w-full break-words text-xs text-rose-300">{state.error}</span> : null}
      {state.receipt && 'stoppedState' in state.receipt ? <details className="w-full"><summary>Paused debugger state</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(state.receipt, null, 2)}</pre></details> : null}
    </> : null}
  </div>
}
