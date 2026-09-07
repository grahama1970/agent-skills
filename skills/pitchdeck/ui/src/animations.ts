import { createContext, useContext, useLayoutEffect, useRef, useState, useCallback } from 'react'
import type { AnimationEffect, UiElement, UiSlide } from './types'

export const FragmentContext = createContext<number>(Infinity)
export const EFFECTS = ['appear', 'fade', 'fly', 'wipe', 'zoom', 'peek', 'split', 'expand', 'stretch', 'rise', 'grow-turn', 'blinds', 'box', 'bars', 'checker', 'strips', 'spin', 'grow-shrink', 'transparency', 'dim', 'pulse', 'font-color', 'fill-color', 'line-color', 'motion-line']
export function phaseFor(effect: string): AnimationEffect['phase'] {
  return effect === 'motion-line' ? 'motion' : ['spin', 'grow-shrink', 'transparency', 'dim', 'pulse', 'font-color', 'fill-color', 'line-color'].includes(effect) ? 'emphasis' : 'entrance'
}
export function animationTargets(slide: UiSlide): { id: string; label: string }[] {
  const walk = (elements: UiElement[]): { id: string; label: string }[] => elements.filter(e => !['title', 'header', 'background', 'footer'].includes(e.role || '')).flatMap(e => [
    { id: e.id, label: e.text?.slice(0, 70) || e.asset?.alt_text || e.id },
    ...walk(e.children || []),
    ...(e.diagram?.nodes.map(n => ({ id: `${e.id}/node/${n.id}`, label: n.label })) || []),
    ...(e.diagram?.edges.map(n => ({ id: `${e.id}/edge/${n.id}`, label: `${n.source} → ${n.target}` })) || []),
  ])
  if (slide.layout === 'freeform') return walk(slide.elements)
  if (slide.layout === 'cover') return []
  const cards = ['three_cards', 'proof_cards', 'roadmap', 'collaboration', 'appendix'].includes(slide.layout)
  const body = cards && slide.visual.items.length ? [] : slide.body.map((label, i) => ({ id: `body:${i}`, label }))
  return [...body, ...slide.visual.items.map((label, i) => ({ id: `visual:${i}`, label })), ...(slide.visual.asset ? [{ id: 'visual', label: slide.visual.asset.alt_text }] : [])]
}
export function defaultSequence(slide: UiSlide): AnimationEffect[] {
  if (slide.animations?.length) return slide.animations
  if (slide.reveal !== 'step' && !slide.elements.some(e => e.fragment_index != null)) return []
  let targets = animationTargets(slide)
  if (slide.layout === 'freeform') targets = targets.filter(t => !t.id.includes('/')).sort((a, b) => {
    const rank = (id: string) => slide.reveal_order?.includes(id) ? slide.reveal_order.indexOf(id) : slide.elements.find(e => e.id === id)?.fragment_index ?? 999
    return rank(a.id) - rank(b.id)
  })
  return targets.map((t, i) => ({ id: `build-${i}`, targets: [t.id], effect: 'appear', phase: 'entrance', direction: 'left', start: 'on-click', duration_ms: 400, delay_ms: 0 }))
}
export function timeline(slide: UiSlide) {
  let step = 0, start = 0, end = 0
  return defaultSequence(slide).map(effect => {
    if (effect.start === 'on-click') { step++; start = effect.delay_ms }
    else start = (effect.start === 'after-previous' ? end : start) + effect.delay_ms
    end = start + effect.duration_ms
    return { effect, step, start, end }
  })
}
export function fragmentCount(slide: UiSlide): number { return Math.max(0, ...timeline(slide).map(e => e.step)) }

/** Shared imperative cursor prevents same-frame key bursts from reading stale React state. */
export function useBuildNavigation(slides: UiSlide[], index: number, setIndex: (n: number) => void, editing = false) {
  const [fragment, setFragment] = useState(0)
  const cursor = useRef({ index, fragment: 0, slide: slides[index] })
  if (cursor.current.index !== index || cursor.current.slide !== slides[index]) cursor.current = { index, fragment: 0, slide: slides[index] }
  const current = cursor.current
  const total = slides[index] ? fragmentCount(slides[index]) : 0
  const jump = useCallback((n: number, end = false) => {
    n = Math.max(0, Math.min(slides.length - 1, n))
    const f = end && slides[n] ? fragmentCount(slides[n]) : 0
    cursor.current = { index: n, fragment: f, slide: slides[n] }; setFragment(f); setIndex(n)
  }, [slides, setIndex])
  const go = useCallback((n: number) => {
    const c = cursor.current, forward = n > index
    const max = slides[c.index] ? fragmentCount(slides[c.index]) : 0
    if (!editing && ((forward && c.fragment < max) || (!forward && n < index && c.fragment > 0))) {
      c.fragment += forward ? 1 : -1; setFragment(c.fragment); return
    }
    const next = c.index + (forward ? 1 : -1)
    if (next >= 0 && next < slides.length) jump(next, !forward && !editing)
  }, [slides, index, editing, jump])
  return { fragment: current.fragment === fragment ? fragment : current.fragment, total, go, jump }
}

function frames(a: AnimationEffect): Keyframe[] {
  const neutral = { opacity: 1, transform: 'none', clipPath: 'inset(0% 0% 0% 0%)' }
  const d = a.direction, horizontal = ['left', 'right', 'horizontal'].includes(d)
  const offset = d === 'right' ? 'translateX(110%)' : d === 'up' ? 'translateY(-110%)' : d === 'down' ? 'translateY(110%)' : 'translateX(-110%)'
  const clip = d === 'right' ? 'inset(0% 0% 0% 100%)' : d === 'up' ? 'inset(0% 0% 100% 0%)' : d === 'down' ? 'inset(100% 0% 0% 0%)' : 'inset(0% 100% 0% 0%)'
  let f: Keyframe[]
  switch (a.effect) {
    case 'appear': f = [{ opacity: 0 }, { opacity: 1 }]; break
    case 'fade': f = [{ opacity: 0 }, { opacity: 1 }]; break
    case 'fly': f = [{ transform: offset }, { transform: 'none' }]; break
    case 'wipe': f = [{ clipPath: clip }, { clipPath: neutral.clipPath }]; break
    case 'peek': f = [{ clipPath: clip, transform: offset }, neutral]; break
    case 'split': f = [{ clipPath: horizontal ? 'inset(0% 50% 0% 50%)' : 'inset(50% 0% 50% 0%)' }, { clipPath: neutral.clipPath }]; break
    case 'zoom': f = [{ transform: d === 'out' ? 'scale(2)' : 'scale(0.05)', opacity: 0 }, neutral]; break
    case 'expand': f = [{ transform: 'scaleX(0)', opacity: 0 }, neutral]; break
    case 'stretch': f = [{ transform: horizontal ? 'scaleX(0)' : 'scaleY(0)' }, { transform: 'none' }]; break
    case 'rise': f = [{ transform: 'translateY(60%)', opacity: 0 }, { transform: 'translateY(-6%)', opacity: 1 }, neutral]; break
    case 'grow-turn': f = [{ transform: 'scale(0) rotate(-90deg)', opacity: 0 }, neutral]; break
    case 'box': f = [{ clipPath: 'inset(50% 50% 50% 50%)' }, { clipPath: neutral.clipPath }]; break
    case 'blinds': case 'bars': case 'checker': case 'strips': {
      // Discrete mask frames, not fade aliases. Deterministic bars are reproducible on reverse.
      const n = 10
      f = Array.from({ length: 21 }, (_, k) => {
        const p = k / 20
        if (a.effect === 'checker') return { maskImage: `conic-gradient(#000 ${p * 360}deg, transparent 0deg)`, maskSize: '40px 40px' }
        if (a.effect === 'strips') return { maskImage: `repeating-linear-gradient(135deg,#000 0px,#000 ${p * 80}px,transparent ${p * 80}px,transparent 80px)` }
        if (a.effect === 'bars') return { maskImage: `linear-gradient(${horizontal ? '90deg' : '0deg'},${Array.from({ length: n }, (_, i) => `${p >= ((i * 7) % n + 1) / n ? '#000' : 'transparent'} ${i * 10}% ${(i + 1) * 10}%`).join(',')})` }
        return { maskImage: `repeating-linear-gradient(${horizontal ? '90deg' : '0deg'},#000 0%,#000 ${p * 10}%,transparent ${p * 10}%,transparent 10%)` }
      }); break
    }
    case 'spin': return [{ transform: 'rotate(0deg)' }, { transform: `rotate(${360 * (a.amount ?? 1)}deg)` }]
    case 'grow-shrink': return [{ transform: 'scale(1)' }, { transform: `scale(${a.amount ?? 1.25})` }]
    case 'pulse': return [{ transform: 'scale(1)' }, { transform: `scale(${1 + (a.amount ?? .1)})` }, { transform: 'scale(1)' }]
    case 'dim': case 'transparency': return [{ opacity: 1 }, { opacity: 1 - Math.min(1, a.amount ?? .5) }]
    case 'font-color': return [{}, { color: a.color || '#808080' }]
    case 'fill-color': return [{}, { backgroundColor: a.color || '#808080' }]
    case 'line-color': return [{}, { borderColor: a.color || '#808080', stroke: a.color || '#808080' }]
    case 'motion-line': return [{ transform: 'translate(0px, 0px)' }, { transform: `translate(${(a.dx ?? .1) * 1920}px, ${(a.dy ?? 0) * 1080}px)` }]
    default: return []
  }
  return a.phase === 'exit' ? [...f].reverse() : f
}

/** One cancellable timeline per rendered slide. Static reading never gets hidden state. */
export function useAnimationTimeline(slide: UiSlide) {
  const revealed = useContext(FragmentContext)
  const ref = useRef<HTMLDivElement>(null)
  const previous = useRef({ id: '', step: 0 })
  useLayoutEffect(() => {
    const root = ref.current
    if (!root || !Number.isFinite(revealed)) return
    const reverse = previous.current.id === slide.id && revealed < previous.current.step
    const fresh = previous.current.id !== slide.id
    previous.current = { id: slide.id, step: revealed }
    const rows = timeline(slide), animations: Animation[] = [], timers: ReturnType<typeof setTimeout>[] = []
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.dataset.reduceMotion === 'true'
    const targets = Array.from(root.querySelectorAll<HTMLElement>('[data-animation-target]'))
    const setHidden = (el: HTMLElement, hidden: boolean) => { el.style.visibility = hidden ? 'hidden' : ''; el.inert = hidden; if (hidden) el.setAttribute('aria-hidden', 'true'); else el.removeAttribute('aria-hidden') }
    for (const el of targets) {
      const rowsFor = rows.filter(r => r.effect.targets.includes(el.dataset.animationTarget!))
      if (!rowsFor.length) continue
      setHidden(el, rowsFor[0].effect.phase === 'entrance')
      for (const row of rowsFor) {
        if (row.step > revealed) continue
        const a = row.effect, active = !reverse && (row.step === revealed) && (row.step > 0 || fresh)
        const delay = active ? row.start : 0, duration = active && !reduced && a.effect !== 'appear' ? a.duration_ms : 0
        const show = () => setHidden(el, false)
        if (a.phase === 'entrance') { if (delay) timers.push(setTimeout(show, delay)); else show() }
        const animation = el.animate(frames(a), { duration, delay, fill: 'both', easing: 'linear' })
        animations.push(animation)
        if (!active) animation.finish()
        if (a.phase === 'exit') {
          const hide = () => setHidden(el, true)
          if (delay + duration) timers.push(setTimeout(hide, delay + duration)); else hide()
        }
      }
    }
    root.dataset.build = String(revealed); root.dataset.buildTotal = String(fragmentCount(slide))
    return () => { timers.forEach(clearTimeout); animations.forEach(a => a.cancel()); targets.forEach(el => setHidden(el, false)) }
  }, [slide, revealed])
  return ref
}
