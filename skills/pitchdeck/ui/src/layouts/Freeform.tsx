import { useContext, useEffect, useState } from 'react'
import { Rnd } from 'react-rnd'
import { CanonicalDiagram } from '../components/CanonicalDiagram'
import { FloatingToolbar } from '../components/FloatingToolbar'
import { CanvasScaleContext, EditContext } from '../edit'
import { assetUrl, revisionStore } from '../hooks'
import { CANVAS_HEIGHT, CANVAS_WIDTH, type UiElement, type UiSlide } from '../types'

// Freeform layout: elements carry fractional x/y/w/h that map 1:1 onto both
// this 1920x1080 canvas and the PPTX builder's 13.33x7.5in slide, so dragging
// here IS the exported geometry. Drag/resize (react-rnd) posts the new frame
// through /api/slide-edit → apply-edit, which re-validates the whole bundle.

const SNAP_PX = 8
const MARGIN = 40

interface Guide {
  id: string
  type: 'v' | 'h'
  position: number
}

function computeSnap(
  activeId: string,
  x: number,
  y: number,
  w: number,
  h: number,
  siblings: { id: string; x: number; y: number; w: number; h: number }[],
): { x: number; y: number; guides: Guide[] } {
  const guides: Guide[] = []
  let sx = x
  let sy = y
  const candidatesV: { pos: number; anchor: 'left' | 'center' | 'right' }[] = []
  const candidatesH: { pos: number; anchor: 'top' | 'center' | 'bottom' }[] = []
  const staticV = [MARGIN, CANVAS_WIDTH / 2, CANVAS_WIDTH - MARGIN]
  const staticH = [MARGIN, CANVAS_HEIGHT / 2, CANVAS_HEIGHT - MARGIN]
  for (const pos of staticV) {
    candidatesV.push({ pos, anchor: 'left' }, { pos, anchor: 'center' }, { pos, anchor: 'right' })
  }
  for (const pos of staticH) {
    candidatesH.push({ pos, anchor: 'top' }, { pos, anchor: 'center' }, { pos, anchor: 'bottom' })
  }
  for (const sibling of siblings) {
    if (sibling.id === activeId) continue
    for (const pos of [sibling.x, sibling.x + sibling.w / 2, sibling.x + sibling.w]) {
      candidatesV.push({ pos, anchor: 'left' }, { pos, anchor: 'center' }, { pos, anchor: 'right' })
    }
    for (const pos of [sibling.y, sibling.y + sibling.h / 2, sibling.y + sibling.h]) {
      candidatesH.push({ pos, anchor: 'top' }, { pos, anchor: 'center' }, { pos, anchor: 'bottom' })
    }
  }
  for (const { pos, anchor } of candidatesV) {
    const edge = anchor === 'left' ? x : anchor === 'center' ? x + w / 2 : x + w
    if (Math.abs(edge - pos) < SNAP_PX) {
      sx = anchor === 'left' ? pos : anchor === 'center' ? pos - w / 2 : pos - w
      if (!guides.some((g) => g.type === 'v' && Math.abs(g.position - pos) < 2)) {
        guides.push({ id: `v-${pos}`, type: 'v', position: pos })
      }
      break
    }
  }
  for (const { pos, anchor } of candidatesH) {
    const edge = anchor === 'top' ? y : anchor === 'center' ? y + h / 2 : y + h
    if (Math.abs(edge - pos) < SNAP_PX) {
      sy = anchor === 'top' ? pos : anchor === 'center' ? pos - h / 2 : pos - h
      if (!guides.some((g) => g.type === 'h' && Math.abs(g.position - pos) < 2)) {
        guides.push({ id: `h-${pos}`, type: 'h', position: pos })
      }
      break
    }
  }
  return { x: sx, y: sy, guides }
}

function SnapGuideOverlay({ guides }: { guides: Guide[] }) {
  if (!guides.length) return null
  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-0 z-40 h-full w-full overflow-visible"
      viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
    >
      {guides.map((guide) =>
        guide.type === 'v' ? (
          <g key={guide.id}>
            <line x1={guide.position} y1={0} x2={guide.position} y2={CANVAS_HEIGHT} stroke="#22d3ee" strokeWidth={1.5} strokeDasharray="6 6" />
            <circle cx={guide.position} cy={14} r={4} fill="#22d3ee" />
            <circle cx={guide.position} cy={CANVAS_HEIGHT - 14} r={4} fill="#22d3ee" />
          </g>
        ) : (
          <g key={guide.id}>
            <line x1={0} y1={guide.position} x2={CANVAS_WIDTH} y2={guide.position} stroke="#22d3ee" strokeWidth={1.5} strokeDasharray="6 6" />
            <circle cx={14} cy={guide.position} r={4} fill="#22d3ee" />
            <circle cx={CANVAS_WIDTH - 14} cy={guide.position} r={4} fill="#22d3ee" />
          </g>
        ),
      )}
    </svg>
  )
}

async function postFrame(slideId: string, elementId: string, frame: { x: number; y: number; w: number; h: number }) {
  const value = [frame.x, frame.y, frame.w, frame.h].map((v) => v.toFixed(4)).join(',')
  const response = await fetch('/api/slide-edit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slide_id: slideId, field: `element:${elementId}:frame`, value, base_revision: revisionStore.current }),
  })
  if (!response.ok) {
    const data = (await response.json()) as { error?: string }
    throw new Error(data.error ?? `frame update failed (${response.status})`)
  }
}

function ElementContent({ element, responsive = false }: { element: UiElement; responsive?: boolean }) {
  if (element.diagram) return <CanonicalDiagram diagram={element.diagram} responsive={responsive} />
  if (element.type === 'asset' && element.asset) {
    if (element.asset.missing || !element.asset.file) {
      return (
        <div className="flex h-full w-full items-center justify-center rounded-xl border-2 border-dashed border-amber-500/60 bg-amber-500/5 p-4 text-2xl text-amber-300">
          MISSING ASSET: {element.asset.id}
        </div>
      )
    }
    if (element.crop && element.asset.kind !== 'video') {
      const c = element.crop
      return (
        <div className="h-full w-full overflow-hidden rounded-xl">
          <img src={assetUrl(element.asset.file)} alt={element.asset.alt_text} className="max-w-none"
            style={{ width: `${100 / c.w}%`, height: `${100 / c.h}%`, marginLeft: `${-c.x / c.w * 100}%`, marginTop: `${-c.y / c.h * 100}%`, objectFit: 'fill' }} />
        </div>
      )
    }
    return element.asset.kind === 'video' ? (
      <video
        src={assetUrl(element.asset.file)}
        controls
        playsInline
        preload="metadata"
        aria-label={element.asset.alt_text}
        className="h-full w-full rounded-xl object-contain"
      />
    ) : (
      <img src={assetUrl(element.asset.file)} alt={element.asset.alt_text} className="h-full w-full rounded-xl object-contain" />
    )
  }
  return (
    <p
      className="m-0 h-full w-full whitespace-pre-wrap leading-snug"
      style={{
        fontSize: responsive ? `${Math.max(18, Math.min(element.size_pt, element.role === 'title' ? 40 : 28))}px` : `${(element.size_pt / 72) * (CANVAS_HEIGHT / 7.5)}px`, // pt → 144dpi canvas px (WebGPT review P1-11)
        fontWeight: element.bold ? 700 : 400,
        color: 'var(--deck-element-text, ' + (element.color ?? '#3a4550') + ')',  // dark ink on the house white canvas
        fontFamily: element.role === 'title' ? 'var(--deck-heading-font, Arial)' : 'var(--deck-body-font, Arial)',
        textAlign: element.align as 'left' | 'center' | 'right',
      }}
    >
      {element.text}
    </p>
  )
}

export function Freeform({ slide, responsive = false }: { slide: UiSlide; responsive?: boolean }) {
  const { editing, request, selectedElementId: selectedId, selectElement, previewElement } = useContext(EditContext)
  const canvasScale = useContext(CanvasScaleContext)
  const [error, setError] = useState<string | null>(null)
  const [frames, setFrames] = useState<Record<string, { x: number; y: number; w: number; h: number }>>({})
  const [guides, setGuides] = useState<Guide[]>([])
  const { refresh } = useContext(EditContext)
  useEffect(() => { setFrames({}) }, [slide.elements])

  const save = (element: UiElement, frame: { x: number; y: number; w: number; h: number }) => {
    setFrames((prev) => ({ ...prev, [element.id]: frame }))
    postFrame(slide.id, element.id, frame).then(() => refresh?.()).catch((err: Error) => setError(err.message))
  }

  return (
    <div className="freeform-slide relative h-full w-full bg-white text-slate-800">
      {/* house chrome (#1388): the PPTX inherits this from the template; the
          browser draws the same anatomy so review is faithful */}
      <div
        className="freeform-band absolute left-0 top-0 z-0 flex w-full items-center px-10"
        style={{ height: 0.11 * CANVAS_HEIGHT, background: 'var(--deck-header-background, #076889)' }}
      >
        <span className="text-4xl font-semibold" style={{ color: 'var(--deck-header-text, white)', fontFamily: 'var(--deck-heading-font, Arial)' }}>{slide.title}</span>
      </div>
      <div className="freeform-brand absolute bottom-3 left-10 z-0 text-xl font-bold" style={{ color: 'var(--deck-diagram-accent, #076889)' }}>
        grahama.co
      </div>
      <div className="freeform-page absolute bottom-3 right-10 z-0 text-xl text-slate-400">{slide.order}</div>
      {error ? (
        <p role="alert" className="absolute left-4 top-4 z-30 m-0 rounded-lg border border-rose-500/60 bg-rose-500/10 px-3 py-1.5 text-xl text-rose-300">
          Rejected: {error}
        </p>
      ) : null}
      {responsive && slide.footer ? <p className="freeform-footer">{slide.footer}</p> : null}
      <SnapGuideOverlay guides={guides} />
      {slide.elements.map((element) => {
        const proposed = editing && previewElement?.id === element.id ? previewElement : undefined
        const frame = proposed ?? frames[element.id] ?? { x: element.x, y: element.y, w: element.w, h: element.h }
        if (!editing) {
          return (
            <div
              key={element.id}
              data-element-id={element.id}
              className={`freeform-element ${responsive ? '' : 'absolute'} ${element.entrance && element.entrance !== 'none' ? `entrance-${element.entrance}` : ''}`}
              style={{
                left: responsive ? undefined : frame.x * CANVAS_WIDTH,
                top: responsive ? undefined : frame.y * CANVAS_HEIGHT,
                width: responsive ? undefined : frame.w * CANVAS_WIDTH,
                height: responsive ? undefined : frame.h * CANVAS_HEIGHT,
                // Reflow must not enlarge small marks into full-width artwork.
                maxWidth: responsive && element.type === 'asset' ? frame.w * CANVAS_WIDTH : undefined,
                animationDelay: element.entrance_delay_ms ? `${element.entrance_delay_ms}ms` : undefined,
              }}
            >
              <ElementContent element={element} responsive={responsive} />
            </div>
          )
        }
        return (
          <Rnd
            key={element.id}
            bounds="parent"
            scale={canvasScale}
            disableDragging={!!proposed}
            enableResizing={!proposed}
            size={{ width: frame.w * CANVAS_WIDTH, height: frame.h * CANVAS_HEIGHT }}
            position={{ x: frame.x * CANVAS_WIDTH, y: frame.y * CANVAS_HEIGHT }}
            onDrag={(_event, data) => {
              const siblings = slide.elements.map((el) => {
                const f = frames[el.id] ?? { x: el.x, y: el.y, w: el.w, h: el.h }
                return { id: el.id, x: f.x * CANVAS_WIDTH, y: f.y * CANVAS_HEIGHT, w: f.w * CANVAS_WIDTH, h: f.h * CANVAS_HEIGHT }
              })
              const snap = computeSnap(element.id, data.x, data.y, frame.w * CANVAS_WIDTH, frame.h * CANVAS_HEIGHT, siblings)
              setGuides(snap.guides)
            }}
            onDragStop={(_event, data) => {
              const siblings = slide.elements.map((el) => {
                const f = frames[el.id] ?? { x: el.x, y: el.y, w: el.w, h: el.h }
                return { id: el.id, x: f.x * CANVAS_WIDTH, y: f.y * CANVAS_HEIGHT, w: f.w * CANVAS_WIDTH, h: f.h * CANVAS_HEIGHT }
              })
              const snap = computeSnap(element.id, data.x, data.y, frame.w * CANVAS_WIDTH, frame.h * CANVAS_HEIGHT, siblings)
              setGuides([])
              save(element, { ...frame, x: snap.x / CANVAS_WIDTH, y: snap.y / CANVAS_HEIGHT })
            }}
            onResizeStop={(_event, _dir, ref, _delta, position) =>
              save(element, {
                x: position.x / CANVAS_WIDTH,
                y: position.y / CANVAS_HEIGHT,
                w: ref.offsetWidth / CANVAS_WIDTH,
                h: ref.offsetHeight / CANVAS_HEIGHT,
              })
            }
            className={`group border-2 ${selectedId === element.id ? 'border-cyan-500' : 'border-transparent hover:border-cyan-500/60'} ${proposed ? 'border-dashed' : ''}`}
          >
            {selectedId === element.id && !element.diagram && !proposed ? (
              <FloatingToolbar
                slideId={slide.id}
                element={element}
                onChanged={() => refresh?.()}
                onError={setError}
              />
            ) : null}
            <div
              data-qid={`deck:freeform:${slide.id}:${element.id}`}
              data-qs-action="DECK_FREEFORM_ELEMENT"
              title={`Drag or resize ${element.id}; double-click text to edit`}
              className="h-full w-full cursor-move"
              data-selected={selectedId === element.id}
              data-agent-preview={!!proposed}
              role="button"
              tabIndex={0}
              aria-label={`Select ${element.text?.slice(0, 80) || element.asset?.alt_text || element.id}`}
              onClick={() => selectElement?.(element.id)}
              onKeyDown={event => {
                if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); selectElement?.(element.id) }
                if (event.key === 'Escape') { event.stopPropagation(); selectElement?.('') }
              }}
              onDoubleClick={() => {
                if (element.type === 'text' && !element.diagram && !proposed) {
                  request({
                    slideId: slide.id,
                    field: `element:${element.id}:text`,
                    label: `element ${element.id}`,
                    value: element.text ?? '',
                  })
                }
              }}
            >
              <ElementContent element={proposed || element} responsive={responsive} />
            </div>
          </Rnd>
        )
      })}
    </div>
  )
}
