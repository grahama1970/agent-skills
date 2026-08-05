import { ImageOff } from 'lucide-react'
import { Editable } from '../edit'
import { Freeform } from './Freeform'
import type { UiSlide, UiVisual } from '../types'

/** Layout components for the 10 SlideLayout values in the deck manifest schema. */

function Visual({ visual }: { visual: UiVisual }) {
  if (visual.type === 'none') return null
  if ((visual.type === 'image' || visual.type === 'screenshot') && visual.asset) {
    if (visual.asset.missing || !visual.asset.file) {
      return (
        <figure className="flex h-full w-full flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed border-amber-500/60 bg-amber-500/5 text-amber-300">
          <ImageOff aria-hidden className="h-16 w-16" />
          <figcaption className="text-3xl font-semibold">MISSING ASSET: {visual.asset.id}</figcaption>
          <p className="max-w-xl px-8 text-center text-2xl text-amber-200/80">{visual.asset.alt_text}</p>
        </figure>
      )
    }
    return (
      <figure className="flex h-full w-full flex-col gap-3">
        {visual.asset.kind === 'video' ? (
          <video
            src={visual.asset.file}
            controls
            playsInline
            preload="metadata"
            aria-label={visual.asset.alt_text}
            className="min-h-0 w-full flex-1 rounded-2xl object-contain shadow-2xl"
          />
        ) : (
          <img
            src={visual.asset.file}
            alt={visual.asset.alt_text}
            className="min-h-0 w-full flex-1 rounded-2xl object-contain shadow-2xl"
          />
        )}
        {visual.caption ? (
          <figcaption className="text-center text-2xl text-slate-400">{visual.caption}</figcaption>
        ) : null}
      </figure>
    )
  }
  if (visual.type === 'native_diagram') {
    return (
      <div className="flex h-full w-full items-center justify-center gap-6">
        {visual.items.map((item, i) => (
          <div key={item} className="flex items-center gap-6">
            {i > 0 ? <span aria-hidden className="text-5xl text-cyan-400">→</span> : null}
            <div className="rounded-2xl border border-cyan-500/40 bg-cyan-500/10 px-8 py-6 text-center text-3xl font-medium">
              {item}
            </div>
          </div>
        ))}
      </div>
    )
  }
  if (visual.type === 'cards') {
    return (
      <ul className="grid h-full w-full list-none grid-cols-2 content-center gap-6 p-0">
        {visual.items.map((item) => (
          <li key={item} className="rounded-2xl border border-slate-700 bg-slate-800/60 p-8 text-3xl">
            {item}
          </li>
        ))}
      </ul>
    )
  }
  return null
}

function BodyList({ slide, size = 'text-4xl' }: { slide: UiSlide; size?: string }) {
  if (!slide.body.length) return null
  return (
    <ul className={`m-0 flex list-none flex-col gap-5 p-0 ${size} leading-snug text-slate-200 ${slide.reveal !== 'none' ? `reveal-${slide.reveal}` : ''}`}>
      {slide.body.map((line, index) => (
        <li key={line} style={{ '--i': index } as React.CSSProperties} className="flex gap-4">
          <span aria-hidden className="mt-1 text-cyan-400">▸</span>
          <span>
            <Editable slide={slide} field={`body:${index}`} label={`bullet ${index + 1}`} value={line}>
              {line}
            </Editable>
          </span>
        </li>
      ))}
    </ul>
  )
}

function Footer({ slide }: { slide: UiSlide }) {
  if (!slide.footer) return null
  return <p className="absolute bottom-10 left-24 right-24 m-0 text-2xl text-slate-500">{slide.footer}</p>
}

export function Cover({ slide }: { slide: UiSlide }) {
  return (
    <div className="relative flex h-full flex-col justify-center gap-8 bg-gradient-to-br from-slate-950 via-slate-900 to-cyan-950 px-32">
      <h1 className="m-0 text-8xl font-bold tracking-tight text-white"><Editable slide={slide} field="title" label="title" value={slide.title}>{slide.title}</Editable></h1>
      <p className="m-0 max-w-5xl text-5xl leading-tight text-cyan-200"><Editable slide={slide} field="message" label="message" value={slide.message}>{slide.message}</Editable></p>
      <Footer slide={slide} />
    </div>
  )
}

export function Statement({ slide }: { slide: UiSlide }) {
  return (
    <div className="relative flex h-full flex-col items-center justify-center gap-10 px-40 text-center">
      <h2 className="m-0 text-6xl font-semibold text-white"><Editable slide={slide} field="title" label="title" value={slide.title}>{slide.title}</Editable></h2>
      <p className="m-0 max-w-6xl text-5xl leading-snug text-cyan-100"><Editable slide={slide} field="message" label="message" value={slide.message}>{slide.message}</Editable></p>
      <BodyList slide={slide} size="text-3xl" />
      <Footer slide={slide} />
    </div>
  )
}

export function Split({ slide }: { slide: UiSlide }) {
  return (
    <div className="relative flex h-full flex-col gap-10 px-24 py-20">
      <header>
        <h2 className="m-0 text-6xl font-semibold text-white"><Editable slide={slide} field="title" label="title" value={slide.title}>{slide.title}</Editable></h2>
        <p className="mt-4 text-4xl text-cyan-200"><Editable slide={slide} field="message" label="message" value={slide.message}>{slide.message}</Editable></p>
      </header>
      <div className="grid min-h-0 flex-1 grid-cols-2 items-center gap-16">
        {slide.visual.position === 'left' ? (
          <>
            <Visual visual={slide.visual} />
            <BodyList slide={slide} />
          </>
        ) : (
          <>
            <BodyList slide={slide} />
            <Visual visual={slide.visual} />
          </>
        )}
      </div>
      <Footer slide={slide} />
    </div>
  )
}

export function Screenshot({ slide }: { slide: UiSlide }) {
  return (
    <div className="relative flex h-full flex-col gap-8 px-24 py-16">
      <header className="flex items-baseline justify-between gap-8">
        <h2 className="m-0 text-5xl font-semibold text-white"><Editable slide={slide} field="title" label="title" value={slide.title}>{slide.title}</Editable></h2>
        <p className="m-0 max-w-2xl text-right text-3xl text-cyan-200"><Editable slide={slide} field="message" label="message" value={slide.message}>{slide.message}</Editable></p>
      </header>
      <div className="min-h-0 flex-1">
        <Visual visual={slide.visual} />
      </div>
      <Footer slide={slide} />
    </div>
  )
}

export function CardGrid({ slide }: { slide: UiSlide }) {
  const cards = slide.visual.items.length ? slide.visual.items : slide.body
  return (
    <div className="relative flex h-full flex-col gap-12 px-24 py-20">
      <header>
        <h2 className="m-0 text-6xl font-semibold text-white"><Editable slide={slide} field="title" label="title" value={slide.title}>{slide.title}</Editable></h2>
        <p className="mt-4 text-4xl text-cyan-200"><Editable slide={slide} field="message" label="message" value={slide.message}>{slide.message}</Editable></p>
      </header>
      <ul className={`m-0 grid min-h-0 flex-1 list-none content-start gap-8 p-0 [grid-template-columns:repeat(auto-fit,minmax(480px,1fr))] ${slide.reveal !== 'none' ? `reveal-${slide.reveal}` : ''}`}>
        {cards.map((card, cardIndex) => (
          <li key={card} style={{ '--i': cardIndex } as React.CSSProperties} className="rounded-2xl border border-slate-700 bg-slate-800/60 p-10 text-3xl leading-snug">
            {card}
          </li>
        ))}
      </ul>
      <Footer slide={slide} />
    </div>
  )
}

export function Flow({ slide }: { slide: UiSlide }) {
  return (
    <div className="relative flex h-full flex-col gap-12 px-24 py-20">
      <header>
        <h2 className="m-0 text-6xl font-semibold text-white"><Editable slide={slide} field="title" label="title" value={slide.title}>{slide.title}</Editable></h2>
        <p className="mt-4 text-4xl text-cyan-200"><Editable slide={slide} field="message" label="message" value={slide.message}>{slide.message}</Editable></p>
      </header>
      <div className="min-h-0 flex-1">
        {slide.visual.type !== 'none' ? (
          <Visual visual={slide.visual} />
        ) : (
          <Visual visual={{ ...slide.visual, type: 'native_diagram', items: slide.body }} />
        )}
      </div>
      <Footer slide={slide} />
    </div>
  )
}

const LAYOUTS: Record<string, (props: { slide: UiSlide }) => React.ReactNode> = {
  freeform: Freeform,
  cover: Cover,
  statement: Statement,
  split: Split,
  screenshot: Screenshot,
  flow: Flow,
  three_cards: CardGrid,
  proof_cards: CardGrid,
  roadmap: CardGrid,
  collaboration: CardGrid,
  appendix: CardGrid,
}

export function SlideBody({ slide }: { slide: UiSlide }) {
  const Layout = LAYOUTS[slide.layout] ?? Split
  return <Layout slide={slide} />
}
