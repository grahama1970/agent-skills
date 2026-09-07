import { useState } from 'react'
import { animationTargets, defaultSequence, EFFECTS, phaseFor, FragmentContext, fragmentCount } from '../animations'
import type { AnimationEffect, UiSlide } from '../types'
import { SlideViewport } from './SlideViewport'
import { Button } from './ui/button'

type Catalog = { hashes: string[]; revision: number; can_undo: boolean }
export function AnimationPanel({ slide, onChanged }: { slide: UiSlide; onChanged: () => void }) {
  const [reduceMotion, setReduceMotion] = useState(document.documentElement.dataset.reduceMotion === 'true')
  const [open, setOpen] = useState(false), [draft, setDraft] = useState<AnimationEffect[]>([])
  const [catalog, setCatalog] = useState<Catalog>(), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<string[]>([]), [row, setRow] = useState(0), [preview, setPreview] = useState<number | null>(null), [replay, setReplay] = useState(0)
  const targets = animationTargets(slide), effect = draft[row]
  const q = (s: string) => ({ 'data-qid': `deck:animations:${s}`, 'data-qs-action': 'DECK_ANIMATIONS', title: s.replaceAll('-', ' ') })
  async function begin() {
    setError(''); setBusy(true)
    try { const r = await fetch(`/api/animations?slide_id=${encodeURIComponent(slide.id)}`); const c = await r.json(); if (!r.ok) throw Error(c.error); setCatalog(c); setDraft(defaultSequence(slide)); setRow(0); setSelected([]); setPreview(null); setOpen(true) } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  async function save(action: string) {
    setBusy(true); setError('')
    try { const r = await fetch('/api/animations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, slide_id: slide.id, animations: draft, hashes: catalog?.hashes, revision: catalog?.revision }) }); const v = await r.json(); if (!r.ok) throw Error(v.error); setOpen(false); onChanged() } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  function update(patch: Partial<AnimationEffect>) { setPreview(null); setDraft(d => d.map((a, i) => i === row ? { ...a, ...patch } : a)) }
  function move(delta: number) { const n = row + delta; if (n < 0 || n >= draft.length) return; const d = [...draft]; [d[n], d[row]] = [d[row], d[n]]; setDraft(d); setRow(n); setPreview(null) }
  const previewSlide = { ...slide, reveal: draft.length ? 'step' : 'none', animations: draft }
  return <div className="theme-picker">
    <Button data-qid="deck:animations:menu" data-qs-action="DECK_ANIMATIONS" title="menu" disabled={busy} aria-expanded={open} onClick={() => open ? setOpen(false) : void begin()}>Animations</Button>
    {open ? <section className="animation-panel theme-panel" role="dialog" aria-label="Animations" onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') setOpen(false) }}>
      <h2>Animations · {slide.title}</h2>
      <label><input {...q('reduce-motion')} type="checkbox" checked={reduceMotion} onChange={e => { setReduceMotion(e.target.checked); document.documentElement.dataset.reduceMotion = String(e.target.checked) }} /> Reduce motion for this presentation (manual steps remain)</label>
      <p>One row reveals one concept. Select several targets to keep a claim and qualifier together. Titles, header and background stay static.</p>
      <div className="animation-columns"><div>
        <fieldset><legend>Targets</legend>{targets.map(t => <label key={t.id}><input {...q(`target:${t.id}`)} type="checkbox" checked={selected.includes(t.id)} onChange={e => setSelected(s => e.target.checked ? [...s, t.id] : s.filter(id => id !== t.id))} />{t.label}</label>)}</fieldset>
        <Button data-qid="deck:animations:add" data-qs-action="DECK_ANIMATIONS" title="add" disabled={!selected.length} onClick={() => { setDraft(d => [...d, { id: crypto.randomUUID(), targets: selected, effect: 'appear', phase: 'entrance', direction: 'left', start: 'on-click', duration_ms: 400, delay_ms: 0 }]); setRow(draft.length); setPreview(null) }}>Add effect / group</Button>
        <ol>{draft.map((a, i) => <li key={a.id}><Button data-qid={`deck:animations:row:${i}`} data-qs-action="DECK_ANIMATIONS" title={`row:${i}`} aria-pressed={row === i} onClick={() => { setRow(i); setSelected(a.targets) }}>{i + 1}. {a.effect} · {a.start} · {a.targets.join(', ')}</Button></li>)}</ol>
        <div className="theme-actions"><Button data-qid="deck:animations:up" data-qs-action="DECK_ANIMATIONS" title="up" disabled={row === 0} onClick={() => move(-1)}>↑ Earlier</Button><Button data-qid="deck:animations:down" data-qs-action="DECK_ANIMATIONS" title="down" disabled={row >= draft.length - 1} onClick={() => move(1)}>↓ Later</Button><Button data-qid="deck:animations:remove" data-qs-action="DECK_ANIMATIONS" title="remove" disabled={!effect} onClick={() => { setDraft(d => d.filter((_, i) => i !== row)); setRow(Math.max(0, row - 1)); setPreview(null) }}>Remove</Button></div>
      </div><div>{effect ? <>
        <label>Effect<select {...q('effect')} value={effect.effect} onChange={e => update({ effect: e.target.value, phase: phaseFor(e.target.value) })}>{EFFECTS.map(e => <option key={e}>{e}</option>)}</select></label>
        <label>Kind<select {...q('phase')} value={effect.phase} onChange={e => update({ phase: e.target.value as AnimationEffect['phase'] })}>{(phaseFor(effect.effect) === 'entrance' ? ['entrance', 'exit'] : [phaseFor(effect.effect)]).map(p => <option key={p}>{p}</option>)}</select></label>
        <label>Direction<select {...q('direction')} value={effect.direction} onChange={e => update({ direction: e.target.value })}>{['left','right','up','down','horizontal','vertical','in','out'].map(d => <option key={d}>{d}</option>)}</select></label>
        <label>Start<select {...q('start')} value={effect.start} onChange={e => update({ start: e.target.value as AnimationEffect['start'] })}>{['on-click','with-previous','after-previous'].map(s => <option key={s}>{s}</option>)}</select></label>
        {(['duration_ms','delay_ms'] as const).map(k => <label key={k}>{k.replace('_ms', ' (ms)')}<input {...q(k)} type="number" min="0" max="10000" value={effect[k]} onChange={e => update({ [k]: Number(e.target.value) })} /></label>)}
        {effect.phase === 'emphasis' ? <><label>Amount (0–4; opacity fraction)<input {...q('amount')} type="number" min="0" max="4" step="0.1" value={effect.amount ?? .5} onChange={e => update({ amount: Number(e.target.value) })} /></label><label>Color<input {...q('color')} type="color" value={effect.color ?? '#808080'} onChange={e => update({ color: e.target.value })} /></label></> : null}
        {effect.phase === 'motion' ? (['dx','dy'] as const).map(k => <label key={k}>{k} (slide fraction)<input {...q(k)} type="number" min="-2" max="2" step="0.05" value={effect[k] ?? (k === 'dx' ? .1 : 0)} onChange={e => update({ [k]: Number(e.target.value) })} /></label>) : null}
        <Button data-qid="deck:animations:group" data-qs-action="DECK_ANIMATIONS" title="group" disabled={!selected.length} onClick={() => update({ targets: selected })}>Use selected targets in this group</Button>
      </> : <p>Select targets and Add effect. Multiple rows may target the same object.</p>}
      <p>Color effects require text / shape / connector respectively. Masks use discrete frames. Custom paths, letter animation, audio/video triggers and repeats are not supported.</p></div></div>
      <div className="theme-actions"><Button data-qid="deck:animations:preview" data-qs-action="DECK_ANIMATIONS" title="preview" onClick={() => { setPreview(0); setReplay(n => n + 1) }}>Preview / Replay</Button><Button data-qid="deck:animations:prev" data-qs-action="DECK_ANIMATIONS" title="prev" disabled={preview === null || preview === 0} onClick={() => setPreview(n => Math.max(0, (n ?? 0) - 1))}>Previous build</Button><Button data-qid="deck:animations:next" data-qs-action="DECK_ANIMATIONS" title="next" disabled={preview === null || preview >= fragmentCount(previewSlide)} onClick={() => setPreview(n => (n ?? 0) + 1)}>Next build</Button></div>
      {preview !== null ? <div key={replay} className="animation-preview"><FragmentContext.Provider value={preview}><SlideViewport slide={previewSlide} fixed /></FragmentContext.Provider></div> : null}
      <div className="theme-actions"><Button data-qid="deck:animations:apply" data-qs-action="DECK_ANIMATIONS" title="apply" disabled={busy} onClick={() => void save('apply')}>Apply</Button><Button data-qid="deck:animations:cancel" data-qs-action="DECK_ANIMATIONS" title="cancel" disabled={busy} onClick={() => setOpen(false)}>Cancel</Button><Button data-qid="deck:animations:undo" data-qs-action="DECK_ANIMATIONS" title="undo" disabled={busy || !catalog?.can_undo} onClick={() => void save('undo')}>Undo animations</Button></div>
      {error ? <p role="alert">{error}</p> : null}
    </section> : null}
    {!open && error ? <p role="alert">{error}</p> : null}
  </div>
}
