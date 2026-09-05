import { useEffect, useRef, useState } from 'react'
import { Button } from './ui/button'
import { useRegisterAction } from '../hooks'
import type { UiDeckBundle } from '../types'
export type ThemeTokens = { accent: string; heading_font: string; body_font: string; canvas?: string | null; text?: string; muted?: string; header?: string; header_text?: string; header_opacity?: number; header_image_opacity?: number }
export function applyThemeTokens(tokens: ThemeTokens) {
  const root = document.documentElement
  for (const key of ['accent', 'heading_font', 'body_font', 'canvas', 'text', 'muted', 'header', 'header_text', 'header_opacity', 'header_image_opacity']) {
    const value = tokens[key as keyof ThemeTokens]
    const property = `--deck-${key.replaceAll('_', '-')}`
    if (value == null) root.style.removeProperty(property)
    else root.style.setProperty(property, String(value))
  }
  root.dataset.deckTheme = tokens.canvas ? 'custom' : 'legacy'
}
type Theme = { name: string; tokens: ThemeTokens }
type Catalog = { current: Theme; presets: Theme[]; hashes: string[]; revision: number; can_undo: boolean }
export function ThemePicker({ deck, onChanged }: { deck: UiDeckBundle; onChanged: () => void }) {
  const [catalog, setCatalog] = useState<Catalog>()
  const [draft, setDraft] = useState<Theme>()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const trigger = useRef<HTMLButtonElement>(null)
  useRegisterAction('deck:theme:menu', { app: 'pitchdeck', action: 'DECK_THEME_MENU', label: 'Theme', description: 'Preview and customize the deck theme' })
  useRegisterAction('deck:theme:apply', { app: 'pitchdeck', action: 'DECK_THEME_APPLY', label: 'Apply theme', description: 'Apply only theme metadata' })
  useRegisterAction('deck:theme:cancel', { app: 'pitchdeck', action: 'DECK_THEME_CANCEL', label: 'Cancel theme', description: 'Discard theme preview' })
  useRegisterAction('deck:theme:save', { app: 'pitchdeck', action: 'DECK_THEME_SAVE', label: 'Save theme', description: 'Save a named theme preset' })
  useRegisterAction('deck:theme:undo', { app: 'pitchdeck', action: 'DECK_THEME_UNDO', label: 'Undo theme', description: 'Undo the last theme change if no later work exists' })
  useRegisterAction('deck:theme:preset', { app: 'pitchdeck', action: 'DECK_THEME_PRESET', label: 'Choose theme', description: 'Preview a preset across the deck' })
  useRegisterAction('deck:theme:customize', { app: 'pitchdeck', action: 'DECK_THEME_CUSTOMIZE', label: 'Customize theme', description: 'Change colors, fonts and header transparency' })
  useEffect(() => { setOpen(false); setDraft(undefined); setCatalog(undefined) }, [deck.revision, deck.deck_id])
  const tokens = open && draft ? draft.tokens : deck.theme_tokens
  useEffect(() => {
    applyThemeTokens(tokens)
    return () => applyThemeTokens(deck.theme_tokens)
  }, [tokens, deck.theme_tokens])
  async function load() {
    const response = await fetch('/api/theme'); const value = await response.json()
    if (!response.ok) throw new Error(value.error)
    setCatalog(value); return value as Catalog
  }
  async function begin() {
    setError('')
    try { const c = await load(); setDraft(c.current); setOpen(true) } catch (e) { setError(String(e)) }
  }
  async function action(action: string) {
    setBusy(true); setError('')
    try {
      const r = await fetch('/api/theme', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, theme: draft, hashes: catalog?.hashes, revision: catalog?.revision }) })
      const result = await r.json(); if (!r.ok) throw new Error(result.error)
      if (action === 'save') await load()
      else { setOpen(false); onChanged() }
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  function cancel() { setOpen(false); setDraft(undefined); trigger.current?.focus() }
  function change(key: string, value: string | number) { setDraft(d => d && ({ ...d, name: ['grahama.co', 'Legacy house'].includes(d.name) ? `${d.name} custom` : d.name, tokens: { ...d.tokens, canvas: d.tokens.canvas ?? (deck.slides[0]?.layout === 'freeform' ? '#ffffff' : '#08131f'), [key]: value } })) }
  const attrs = (key: string) => ({ 'data-qid': `deck:theme:${key}`, 'data-qs-action': 'DECK_THEME_CUSTOMIZE', title: key.replaceAll('_', ' ') })
  return <div className="theme-picker">
    <Button ref={trigger} data-qid="deck:theme:menu" data-qs-action="DECK_THEME_MENU" title="Theme: choose and customize" aria-expanded={open} onClick={() => open ? cancel() : void begin()}>
      <span aria-hidden className="theme-swatch" style={{ background: tokens.accent }} />Theme · {open ? draft?.name : deck.theme}
    </Button>
    {open && draft && catalog ? <section className="theme-panel" aria-label="Theme preview" onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); cancel() } }}>
      <label>Theme <select data-qid="deck:theme:preset" data-qs-action="DECK_THEME_PRESET" title="Theme preset" value={draft.name} onChange={e => setDraft([catalog.current, ...catalog.presets].find(p => p.name === e.target.value))}>
        <option value={catalog.current.name}>{catalog.current.name} (current)</option>
        {catalog.presets.filter(p => p.name !== catalog.current.name).map(p => <option key={p.name}>{p.name}</option>)}
        {![catalog.current, ...catalog.presets].some(p => p.name === draft.name) ? <option>{draft.name}</option> : null}
      </select></label>
      <p>Previewing the entire deck. Navigate slides before Apply. Cancel leaves your deck unchanged.</p>
      <details><summary data-qid="deck:theme:customize" data-qs-action="DECK_THEME_CUSTOMIZE" title="Customize colors and fonts">Customize</summary>
        <div className="theme-fields">{(['canvas', 'text', 'accent', 'muted', 'header', 'header_text'] as const).map(key => <label key={key}>{key.replaceAll('_', ' ')}<input {...attrs(key)} type="color" value={draft.tokens[key] || '#ffffff'} onChange={e => change(key, e.target.value)} /></label>)}</div>
        <label>Header background opacity {Math.round((draft.tokens.header_opacity ?? 1) * 100)}%<input {...attrs('header_opacity')} type="range" min="0" max="1" step="0.01" value={draft.tokens.header_opacity ?? 1} onChange={e => change('header_opacity', Number(e.target.value))} /></label>
        <label>Header image opacity {Math.round((draft.tokens.header_image_opacity ?? 0.1) * 100)}%<input {...attrs('header_image_opacity')} type="range" min="0" max="1" step="0.01" value={draft.tokens.header_image_opacity ?? 0.1} onChange={e => change('header_image_opacity', Number(e.target.value))} /></label>
        {(['heading_font', 'body_font'] as const).map(key => <label key={key}>{key === 'heading_font' ? 'Heading font' : 'Body font'}<select {...attrs(key)} value={draft.tokens[key]} onChange={e => change(key, e.target.value)}>{(key === 'heading_font' ? ['Fraunces', 'Arial', 'Calibri', 'Georgia', 'system-ui'] : ['Arial', 'Calibri', 'Georgia', 'system-ui']).map(font => <option key={font}>{font}</option>)}</select></label>)}
        <p>Fraunces is supplied to the browser and PDF renderer. Editable PPTX requests the font, not embeds it; recipients may need the supplied fonts/fraunces TTFs. System sans exports as Arial. Images keep their authored colors.</p>
        <label>Theme name<input {...attrs('name')} value={draft.name} maxLength={60} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>
        <Button data-qid="deck:theme:save" data-qs-action="DECK_THEME_SAVE" title="Save named theme without applying" disabled={busy || !draft.name.trim()} onClick={() => void action('save')}>Save theme</Button>
      </details>
      <div className="theme-actions"><Button data-qid="deck:theme:apply" data-qs-action="DECK_THEME_APPLY" title="Apply theme to deck" disabled={busy} onClick={() => void action('apply')}>Apply</Button><Button data-qid="deck:theme:cancel" data-qs-action="DECK_THEME_CANCEL" title="Cancel theme preview" disabled={busy} onClick={cancel}>Cancel</Button><Button data-qid="deck:theme:undo" data-qs-action="DECK_THEME_UNDO" title="Undo last theme change" disabled={busy || !catalog.can_undo} onClick={() => void action('undo')}>Undo theme</Button></div>
    </section> : null}
    {error ? <p role="alert" className="theme-error">{error}</p> : null}
  </div>
}
