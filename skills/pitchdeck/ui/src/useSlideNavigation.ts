import { useCallback, useEffect, useState } from 'react'
import type { UiDeckBundle } from './types'

/** IDs, not ordinals, survive reordering. Resume state is scoped to a deck URL. */
export function useSlideNavigation(deck: UiDeckBundle | null, editing: boolean) {
  const [index, setRawIndex] = useState(0)
  const [notice, setNotice] = useState('')
  const slides = deck ? (editing ? deck.slides : deck.slides.filter(s => !s.hidden)) : []
  const key = `pitchdeck:resume:${location.pathname}:${new URLSearchParams(location.search).get('deck') || './deck.data.json'}:${deck?.deck_id}`
  useEffect(() => {
    if (!deck) return
    const restore = () => {
      let id = ''
      try { id = location.hash.startsWith('#/slide/') ? decodeURIComponent(location.hash.slice(8)) : localStorage.getItem(key) || '' } catch { /* Storage/malformed URL cannot prevent reading. */ }
      const next = slides.findIndex(s => s.id === id)
      setRawIndex(Math.max(next, 0))
      setNotice(id && next < 0 ? 'Saved slide is missing or hidden; showing the first available slide.' : '')
    }
    restore()
    window.addEventListener('popstate', restore)
    window.addEventListener('hashchange', restore)
    return () => { window.removeEventListener('popstate', restore); window.removeEventListener('hashchange', restore) }
  }, [deck, editing, key])
  const setIndex = useCallback((next: number) => {
    const n = Math.max(0, Math.min(slides.length - 1, next))
    const slide = slides[n]
    if (!slide) return
    setRawIndex(n)
    setNotice('')
    const hash = `#/slide/${encodeURIComponent(slide.id)}`
    if (location.hash !== hash) history.pushState(null, '', hash)
    try { localStorage.setItem(key, slide.id) } catch { /* Session navigation still works. */ }
  }, [slides, key])
  return { index, setIndex, notice }
}
