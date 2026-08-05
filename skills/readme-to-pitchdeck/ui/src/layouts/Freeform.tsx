import { useContext, useState } from 'react'
import { Rnd } from 'react-rnd'
import { FloatingToolbar } from '../components/FloatingToolbar'
import { EditContext } from '../edit'
import { CANVAS_HEIGHT, CANVAS_WIDTH, type UiElement, type UiSlide } from '../types'

// Freeform layout: elements carry fractional x/y/w/h that map 1:1 onto both
// this 1920x1080 canvas and the PPTX builder's 13.33x7.5in slide, so dragging
// here IS the exported geometry. Drag/resize (react-rnd) posts the new frame
// through /api/slide-edit → apply-edit, which re-validates the whole bundle.

async function postFrame(slideId: string, elementId: string, frame: { x: number; y: number; w: number; h: number }) {
  const value = [frame.x, frame.y, frame.w, frame.h].map((v) => v.toFixed(4)).join(',')
  const response = await fetch('/api/slide-edit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slide_id: slideId, field: `element:${elementId}:frame`, value }),
  })
  if (!response.ok) {
    const data = (await response.json()) as { error?: string }
    throw new Error(data.error ?? `frame update failed (${response.status})`)
  }
}

function ElementContent({ element }: { element: UiElement }) {
  if (element.type === 'asset' && element.asset) {
    if (element.asset.missing || !element.asset.file) {
      return (
        <div className="flex h-full w-full items-center justify-center rounded-xl border-2 border-dashed border-amber-500/60 bg-amber-500/5 p-4 text-2xl text-amber-300">
          MISSING ASSET: {element.asset.id}
        </div>
      )
    }
    return element.asset.kind === 'video' ? (
      <video
        src={element.asset.file}
        controls
        playsInline
        preload="metadata"
        aria-label={element.asset.alt_text}
        className="h-full w-full rounded-xl object-contain"
      />
    ) : (
      <img src={element.asset.file} alt={element.asset.alt_text} className="h-full w-full rounded-xl object-contain" />
    )
  }
  return (
    <p
      className="m-0 h-full w-full whitespace-pre-wrap leading-snug"
      style={{
        fontSize: `${(element.size_pt / 72) * (CANVAS_HEIGHT / 7.5)}px`, // pt → 144dpi canvas px (WebGPT review P1-11)
        fontWeight: element.bold ? 700 : 400,
        color: element.color ?? '#e6edf3',
        textAlign: element.align as 'left' | 'center' | 'right',
      }}
    >
      {element.text}
    </p>
  )
}

export function Freeform({ slide }: { slide: UiSlide }) {
  const { editing, request } = useContext(EditContext)
  const [error, setError] = useState<string | null>(null)
  const [frames, setFrames] = useState<Record<string, { x: number; y: number; w: number; h: number }>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { refresh } = useContext(EditContext)

  const save = (element: UiElement, frame: { x: number; y: number; w: number; h: number }) => {
    setFrames((prev) => ({ ...prev, [element.id]: frame }))
    postFrame(slide.id, element.id, frame).catch((err: Error) => setError(err.message))
  }

  return (
    <div className="relative h-full w-full">
      {error ? (
        <p role="alert" className="absolute left-4 top-4 z-30 m-0 rounded-lg border border-rose-500/60 bg-rose-500/10 px-3 py-1.5 text-xl text-rose-300">
          Rejected: {error}
        </p>
      ) : null}
      {slide.elements.map((element) => {
        const frame = frames[element.id] ?? { x: element.x, y: element.y, w: element.w, h: element.h }
        if (!editing) {
          return (
            <div
              key={element.id}
              className="absolute"
              style={{
                left: frame.x * CANVAS_WIDTH,
                top: frame.y * CANVAS_HEIGHT,
                width: frame.w * CANVAS_WIDTH,
                height: frame.h * CANVAS_HEIGHT,
              }}
            >
              <ElementContent element={element} />
            </div>
          )
        }
        return (
          <Rnd
            key={element.id}
            bounds="parent"
            size={{ width: frame.w * CANVAS_WIDTH, height: frame.h * CANVAS_HEIGHT }}
            position={{ x: frame.x * CANVAS_WIDTH, y: frame.y * CANVAS_HEIGHT }}
            onDragStop={(_event, data) =>
              save(element, { ...frame, x: data.x / CANVAS_WIDTH, y: data.y / CANVAS_HEIGHT })
            }
            onResizeStop={(_event, _dir, ref, _delta, position) =>
              save(element, {
                x: position.x / CANVAS_WIDTH,
                y: position.y / CANVAS_HEIGHT,
                w: ref.offsetWidth / CANVAS_WIDTH,
                h: ref.offsetHeight / CANVAS_HEIGHT,
              })
            }
            className="group border border-dashed border-transparent hover:border-cyan-500/60"
          >
            {selectedId === element.id ? (
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
              onClick={() => setSelectedId(element.id)}
              onDoubleClick={() => {
                if (element.type === 'text') {
                  request({
                    slideId: slide.id,
                    field: `element:${element.id}:text`,
                    label: `element ${element.id}`,
                    value: element.text ?? '',
                  })
                }
              }}
            >
              <ElementContent element={element} />
            </div>
          </Rnd>
        )
      })}
    </div>
  )
}
