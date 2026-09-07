import { useEffect, useRef, useState } from 'react'
import type { UiSlide } from '../types'
import { Button } from './ui/button'
import './teleprompter.css'

type SlideMessage = {
  type: 'slide'
  source: string
  deckTitle: string
  slideId: string
  title: string
  notes: string
  position: number
  total: number
}

function sourceId() {
  try {
    const key = 'pitchdeck:teleprompter-source'
    const saved = sessionStorage.getItem(key)
    if (saved) return saved
    const id = crypto.randomUUID()
    sessionStorage.setItem(key, id)
    return id
  } catch { return crypto.randomUUID() }
}

function isSlideMessage(value: unknown, source: string): value is SlideMessage {
  if (!value || typeof value !== 'object') return false
  const v = value as Record<string, unknown>
  return v.type === 'slide' && v.source === source &&
    ['deckTitle', 'slideId', 'title', 'notes'].every(k => typeof v[k] === 'string') &&
    typeof v.position === 'number' && Number.isInteger(v.position) && v.position > 0 &&
    typeof v.total === 'number' && Number.isInteger(v.total) && v.total >= v.position
}

export function TeleprompterControl({ deckTitle, slide, position, total }: {
  deckTitle: string; slide: UiSlide; position: number; total: number
}) {
  const [source] = useState(sourceId)
  const [error, setError] = useState('')
  const latest = useRef<SlideMessage>({ type: 'slide', source, deckTitle, slideId: slide.id, title: slide.title, notes: slide.notes, position, total })
  const channel = useRef<BroadcastChannel | null>(null)
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return
    const bus = new BroadcastChannel(`pitchdeck:teleprompter:${source}`)
    channel.current = bus
    const send = () => bus.postMessage(latest.current)
    bus.onmessage = event => { if (event.data?.type === 'request' && event.data.source === source) send() }
    const timer = window.setInterval(send, 2000)
    send()
    return () => { clearInterval(timer); channel.current = null; bus.close() }
  }, [source])
  useEffect(() => {
    latest.current = { type: 'slide', source, deckTitle, slideId: slide.id, title: slide.title, notes: slide.notes, position, total }
    channel.current?.postMessage(latest.current)
  }, [source, slide.id, slide.title, slide.notes, deckTitle, position, total])
  const open = () => {
    const url = new URL(location.href)
    url.pathname = '/teleprompter'
    url.search = ''
    url.hash = ''
    url.searchParams.set('source', source)
    const page = window.open(url.href, 'pitchdeck-teleprompter', 'popup,width=1200,height=1000,resizable=yes,scrollbars=yes')
    setError(page ? '' : 'Popup blocked. Allow this site to open the teleprompter window.')
  }
  return <span className="teleprompter-control">
    <Button data-qid="deck:teleprompter:open" data-qs-action="DECK_TELEPROMPTER_OPEN" title="Open the separate speaker teleprompter; reuse its window" disabled={typeof BroadcastChannel === 'undefined'} onClick={open}>Teleprompter</Button>
    {error ? <span role="alert">{error}</span> : null}
  </span>
}

export function TeleprompterPage() {
  const source = new URLSearchParams(location.search).get('source') || ''
  const [slide, setSlide] = useState<SlideMessage | null>(null)
  const [seen, setSeen] = useState(0)
  const [now, setNow] = useState(Date.now())
  const [size, setSize] = useState(64)
  const text = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (!source || typeof BroadcastChannel === 'undefined') return
    const bus = new BroadcastChannel(`pitchdeck:teleprompter:${source}`)
    bus.onmessage = event => {
      if (!isSlideMessage(event.data, source)) return
      setSlide(event.data)
      setSeen(Date.now())
    }
    bus.postMessage({ type: 'request', source })
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => { clearInterval(timer); bus.close() }
  }, [source])
  useEffect(() => { text.current?.scrollTo({ top: 0 }) }, [slide?.slideId])
  useEffect(() => { document.title = `Teleprompter${slide ? ` — ${slide.deckTitle}` : ''}` }, [slide?.deckTitle])
  const connected = seen > 0 && now - seen < 10000
  const bullets = slide?.notes.split(/\r?\n/).map(line => line.trim().replace(/^(?:[-*•]\s+|\d+[.)]\s+)/, '')).filter(Boolean) || []
  return <main className="teleprompter-page" data-qid="teleprompter:page" data-slide-id={slide?.slideId || ''} data-connected={connected}>
    <header className="teleprompter-header">
      <div><span>{slide?.deckTitle || 'Pitchdeck teleprompter'}</span><p role="status">{connected ? `Following slide ${slide?.position} / ${slide?.total}` : slide ? 'Source not responding — showing last received notes' : 'Waiting for the source deck. Open Teleprompter from pitchdeck.'}</p></div>
      <div className="teleprompter-font-controls">
        <Button data-qid="teleprompter:smaller" data-qs-action="TELEPROMPTER_SMALLER" title="Smaller speaking text" disabled={size <= 32} onClick={() => setSize(s => Math.max(32, s - 8))}>A−</Button>
        <output aria-label="Text size">{size}px</output>
        <Button data-qid="teleprompter:larger" data-qs-action="TELEPROMPTER_LARGER" title="Larger speaking text" disabled={size >= 96} onClick={() => setSize(s => Math.min(96, s + 8))}>A+</Button>
      </div>
    </header>
    <div ref={text} className="teleprompter-text" style={{ fontSize: size }}>
      {slide ? <><h1>{slide.title}</h1>{bullets.length ? <ul data-qid="teleprompter:bullets">{bullets.map((bullet, i) => <li key={i}>{bullet}</li>)}</ul> : <p>No speaking points supplied for this slide.</p>}</> : <p>Keep the source deck open on your presentation monitor.</p>}
    </div>
  </main>
}
