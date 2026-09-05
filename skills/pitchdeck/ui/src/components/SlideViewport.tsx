import { useEffect } from 'react'
import { useRegisterAction, useSlideScale } from '../hooks'
import { SlideBody } from '../layouts/SlideLayouts'
import { CanvasScaleContext } from '../edit'
import { CANVAS_HEIGHT, CANVAS_WIDTH, type UiSlide } from '../types'

/** Reading reflows below 1100 CSS px of AVAILABLE slide space. Design and
 * thumbnails retain the export coordinate system; resizing never writes data. */
export function SlideViewport({ slide, direction = 'fwd', zoom = 'fit', fixed = false, qidPrefix = 'deck:slide' }: {
  slide: UiSlide
  direction?: 'fwd' | 'back'
  zoom?: string
  fixed?: boolean
  qidPrefix?: 'deck:slide' | 'deck:presenter:slide'
}) {
  useRegisterAction(`${qidPrefix}:${slide.id}`, { app: 'pitchdeck', action: 'DECK_FOCUS_SLIDE', label: 'Slide content', description: 'Focus the slide reading region for keyboard scrolling' })
  const { ref, scale: fitScale, width } = useSlideScale()
  const responsive = !fixed && width > 0 && width < 1100
  const scale = zoom === 'fit' ? fitScale : (Number(zoom) / 100) * fitScale
  useEffect(() => { ref.current?.scrollTo(0, 0) }, [slide.id, ref])
  return (
    <div ref={ref} className={`slide-viewport relative min-h-0 min-w-0 flex-1 ${responsive ? 'overflow-y-auto' : 'overflow-hidden'}`}
      data-layout={responsive ? 'responsive' : 'canvas'} data-slide-id={slide.id}
      data-qid={`${qidPrefix}:${slide.id}`} data-qs-action="DECK_FOCUS_SLIDE" title="Slide content — scroll to read the complete slide"
      role="region" aria-label={`Slide ${slide.order}: ${slide.title}`} tabIndex={0}>
      <div className={responsive ? 'responsive-slide bg-slate-950' : 'absolute left-1/2 top-1/2 overflow-hidden rounded-lg bg-slate-950 shadow-2xl'}
        style={responsive ? undefined : { width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: `translate(-50%, -50%) scale(${scale})` }}>
        <div key={slide.id} className={`${responsive ? '' : 'h-full w-full'} ${slide.transition === 'none' ? '' : `anim-${slide.transition}-${direction}`}`}
          style={{ '--deck-transition': `${slide.transition_duration_ms}ms` } as React.CSSProperties}>
          <CanvasScaleContext.Provider value={responsive ? 1 : scale}>
            <SlideBody slide={slide} responsive={responsive} />
          </CanvasScaleContext.Provider>
        </div>
      </div>
    </div>
  )
}
