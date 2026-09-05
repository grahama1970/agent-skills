import { useEffect, useRef, useState } from 'react'
import { Check, Eye, Undo2, X } from 'lucide-react'
import { useRegisterAction } from '../hooks'
import type { UiDeckBundle, UiElement } from '../types'
import { Button } from './ui/button'

export type ElementTarget = { slideId: string; elementId: string }
type Selection = { client_id: string; sequence: number; slide_id: string; element_id: string | null; revision: number }
type Proposal = { id: string; summary: string; element: UiElement; publication_review_required: boolean }

/** Extends the existing project chat; no second chat UI or client-authored edit spec. */
export function useSelectedAmendment(deck: UiDeckBundle, target: ElementTarget | undefined, onChanged: (() => void) | undefined, onPreview: ((element?: UiElement) => void) | undefined) {
  const [clientId] = useState(() => crypto.randomUUID())
  const sequence = useRef(0)
  const envelope = useRef<Selection | null>(null)
  const acknowledgment = useRef<Promise<void>>(Promise.resolve())
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [undoId, setUndoId] = useState('')
  const [showPreview, setShowPreview] = useState(true)
  const key = `${deck.deck_id}:${deck.revision}:${target?.slideId}:${target?.elementId}`
  const active = useRef(key)
  active.current = key
  const undoKey = `pitchdeck:agent-undo:${location.search}:${target?.slideId}:${target?.elementId}`
  const selected = deck.slides.find(s => s.id === target?.slideId)?.elements.find(e => e.id === target?.elementId)
  useRegisterAction('deck:agent:apply', { app: 'pitchdeck', action: 'DECK_AGENT_APPLY', label: 'Apply amendment', description: 'Apply the validated proposal to the still-current selection' })
  useRegisterAction('deck:agent:preview', { app: 'pitchdeck', action: 'DECK_AGENT_PREVIEW', label: 'Compare original and proposed', description: 'Toggle the non-mutating on-slide preview' })
  useRegisterAction('deck:agent:dismiss', { app: 'pitchdeck', action: 'DECK_AGENT_DISMISS', label: 'Discard proposal', description: 'Restore original display without changing the document' })
  useRegisterAction('deck:agent:undo', { app: 'pitchdeck', action: 'DECK_AGENT_UNDO', label: 'Undo amendment', description: 'Restore the previous element only if no later document work would be lost' })

  async function post(action: string, body: object) {
    const response = await fetch(`/api/element-agent/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const value = await response.json()
    if (!response.ok) throw new Error(value.error || `Agent request failed (${response.status})`)
    return value
  }
  useEffect(() => {
    const forKey = key
    setProposal(null); setError(''); onPreview?.(undefined)
    try { setUndoId(sessionStorage.getItem(undoKey) || '') } catch { setUndoId('') }
    envelope.current = { client_id: clientId, sequence: ++sequence.current, slide_id: target?.slideId || '', element_id: target?.elementId || null, revision: deck.revision }
    acknowledgment.current = post('selection', { selection: envelope.current }).then(() => undefined)
    void acknowledgment.current.catch(reason => { if (active.current === forKey) setError(String(reason)) })
  }, [key, undoKey, clientId, onPreview])

  const send = async (text: string) => {
    const forKey = key
    setBusy(true); setError(''); setProposal(null); onPreview?.(undefined)
    try {
      const selected = envelope.current
      await acknowledgment.current
      if (active.current !== forKey) return 'Selection changed before sending; select the intended element and ask again.'
      const value = await post('propose', { text, selection: selected })
      if (active.current !== forKey) return 'Selection changed; the old proposal was discarded. Select the intended element and ask again.'
      if (value.status === 'QUESTION') return value.reply as string
      if (value.status !== 'PREVIEW' || !value.element) throw new Error('No validated proposal returned')
      setProposal(value); setShowPreview(true); onPreview?.(value.element)
      return `${value.summary}\n\nPreview only—your document has not changed. Compare with the original, then Apply or discard.${value.publication_review_required ? '\nText changes will require renewed publication review.' : ''}`
    } catch (reason) { setError(String(reason)); return `No changes made: ${String(reason)}` }
    finally { setBusy(false) }
  }
  const commit = async (action: 'apply' | 'undo') => {
    const forKey = key, selected = envelope.current
    setBusy(true); setError('')
    try {
      await acknowledgment.current
      if (active.current !== forKey) throw new Error('Selection changed before confirmation')
      const id = action === 'apply' ? proposal?.id : undoId
      const value = await post(action, { id, selection: selected })
      if (!['APPLIED', 'UNDONE'].includes(value.status)) throw new Error('No committed amendment returned')
      const nextUndo = action === 'apply' ? id! : ''
      setUndoId(nextUndo)
      try { if (nextUndo) sessionStorage.setItem(undoKey, nextUndo); else sessionStorage.removeItem(undoKey) } catch { /* In-memory Undo remains available. */ }
      setProposal(null); onPreview?.(undefined); onChanged?.()
    } catch (reason) { setError(String(reason)) }
    finally { setBusy(false) }
  }
  const card = target ? <section aria-label="Selected element amendment" data-qid="deck:agent:selection" className="mx-2 mb-2 space-y-2 rounded-lg border border-cyan-700 bg-cyan-950/40 p-3 text-xs text-cyan-100">
    <p className="m-0 break-words"><strong>Selected:</strong> {selected?.text?.slice(0, 100) || selected?.asset?.alt_text || 'Slide element'} · revision {deck.revision}</p>
    <p className="m-0 text-cyan-200/80">Tell the project agent what to change. Only this highlighted element is targeted.</p>
    {proposal ? <>
      <p className="m-0 break-words">{proposal.summary}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" title="Compare original and proposed element" data-qid="deck:agent:preview" data-qs-action="DECK_AGENT_PREVIEW" aria-pressed={showPreview} onClick={() => { setShowPreview(v => !v); onPreview?.(showPreview ? undefined : proposal.element) }}><Eye size={14} aria-hidden />{showPreview ? 'Show original' : 'Show proposal'}</Button>
        <Button size="sm" title="Apply to the highlighted element" data-qid="deck:agent:apply" data-qs-action="DECK_AGENT_APPLY" disabled={busy} onClick={() => void commit('apply')}><Check size={14} aria-hidden />Apply</Button>
        <Button size="sm" variant="ghost" title="Discard without changing the document" data-qid="deck:agent:dismiss" data-qs-action="DECK_AGENT_DISMISS" disabled={busy} onClick={() => { setProposal(null); onPreview?.(undefined) }}><X size={14} aria-hidden />Discard</Button>
      </div>
    </> : null}
    {undoId ? <Button size="sm" variant="ghost" title="Undo the last agent amendment; refuses if later work would be lost" data-qid="deck:agent:undo" data-qs-action="DECK_AGENT_UNDO" disabled={busy} onClick={() => void commit('undo')}><Undo2 size={14} aria-hidden />Undo amendment</Button> : null}
    {error ? <p role="alert" className="m-0 break-words text-rose-300">{error}</p> : null}
  </section> : null
  return { send, card, busy }
}
