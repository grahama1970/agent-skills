import { useEffect, useState } from 'react'
import { Link, Search } from 'lucide-react'
import { useRegisterAction } from '../hooks'
import type { UiDeckBundle } from '../types'
import { Button } from './ui/button'

export function DeckNavigator({ deck, onSelect }: { deck: UiDeckBundle; onSelect: (id: string) => void }) {
  const [entries, setEntries] = useState<{ url: string; title: string; revision: number; source_available: boolean }[]>([])
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState('')
  useRegisterAction('deck:active:select', { app: 'pitchdeck', action: 'DECK_SELECT', label: 'Active deck', description: 'Choose a validated emitted deck' })
  useRegisterAction('deck:search', { app: 'pitchdeck', action: 'DECK_SEARCH', label: 'Find slide', description: 'Search titles and slide IDs' })
  useRegisterAction('deck:link', { app: 'pitchdeck', action: 'DECK_COPY_LINK', label: 'Copy slide link', description: 'Copy the current stable slide URL' })
  useEffect(() => { fetch('/api/decks').then(r => { if (!r.ok) throw new Error('Deck list unavailable'); return r.json() }).then(setEntries).catch(e => setMessage(String(e))) }, [])
  const active = new URL(new URLSearchParams(location.search).get('deck') || './deck.data.json', location.href).pathname
  const slides = deck.slides.filter(s => !s.hidden)
  return <section aria-label="Deck navigation" className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-800 p-2 text-sm">
    <select title="Active deck — edits and exports use this source" aria-label="Active deck" data-qid="deck:active:select" data-qs-action="DECK_SELECT" value={active}
      className="min-w-0 max-w-full rounded border border-slate-700 bg-slate-900 p-2"
      onChange={e => { const url = new URL(location.href); url.searchParams.set('deck', e.target.value); url.hash = ''; location.assign(url) }}>
      {!entries.some(e => e.url === active) ? <option value={active}>{deck.title}</option> : null}
      {entries.map(e => <option key={e.url} value={e.url}>{e.title} · {e.url}{e.source_available ? '' : ' (source missing — read only)'}</option>)}
    </select>
    <span className="text-xs text-slate-400" title={active}>Revision {deck.revision}</span>
    <label className="flex min-w-0 items-center gap-1"><Search size={16} aria-hidden /><input title="Search slide titles or IDs" aria-label="Find slide" data-qid="deck:search" data-qs-action="DECK_SEARCH"
      className="min-w-0 w-40 rounded border border-slate-700 bg-slate-900 p-2" value={query} onChange={e => setQuery(e.target.value)} placeholder="Find slide…" /></label>
    <Button title="Copy link to this slide" data-qid="deck:link" data-qs-action="DECK_COPY_LINK" variant="ghost" size="icon"
      onClick={() => { void navigator.clipboard.writeText(location.href).then(() => setMessage('Slide link copied'), () => setMessage('Clipboard unavailable; copy the address bar URL.')) }}><Link aria-hidden size={16} /></Button>
    {message ? <span role="status" className="text-xs text-slate-400">{message}</span> : null}
    {query ? <ul className="m-0 flex w-full list-none flex-wrap gap-2 p-0">
      {slides.filter(s => `${s.title} ${s.id}`.toLowerCase().includes(query.toLowerCase())).map(s => <li key={s.id}>
        <Button title={`Go to ${s.title}`} data-qid={`deck:search:${s.id}`} data-qs-action="DECK_GOTO_SLIDE" variant="secondary" onClick={() => { onSelect(s.id); setQuery('') }}>{s.order}. {s.title}</Button>
      </li>)}
    </ul> : null}
  </section>
}
