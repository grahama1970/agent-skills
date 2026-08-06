import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  defaultDropAnimationSideEffects,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
  type DropAnimation,
} from '@dnd-kit/core'
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { AlertTriangle, ChevronsLeft, ChevronsRight, Copy, Eye, EyeOff, GripVertical, Plus, ShieldQuestion, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { revisionStore } from '../hooks'
import { SlideBody } from '../layouts/SlideLayouts'
import { CANVAS_HEIGHT, CANVAS_WIDTH, type UiDeckBundle, type UiSlide } from '../types'

// Slide navigation drawer (user spec, adapted): dnd-kit sortable thumbnails
// with DragOverlay, hover quick actions, and derived status badges. All
// mutations go through the validated pipeline (deck-op / slide-edit) and the
// mini previews are REAL scaled slide renders, not wireframe approximations.
// Status is DERIVED from ledger data (never stored): REVIEW = candidate
// claims present; GAPS = missing asset. No stored "VERIFIED" state exists.

type DerivedStatus = 'REVIEW' | 'GAPS' | null

function deriveStatus(slide: UiSlide): DerivedStatus {
  if (slide.claims.some((claim) => claim.status === 'candidate')) return 'REVIEW'
  if (slide.visual.asset?.missing) return 'GAPS'
  return null
}

const BADGES: Record<Exclude<DerivedStatus, null>, { label: string; className: string; icon: typeof AlertTriangle }> = {
  REVIEW: { label: 'REVIEW', className: 'border-rose-500/30 bg-rose-500/10 text-rose-400', icon: ShieldQuestion },
  GAPS: { label: 'GAPS', className: 'border-amber-500/30 bg-amber-500/10 text-amber-400', icon: AlertTriangle },
}

const THUMB_W = 112

function MiniPreview({ slide }: { slide: UiSlide }) {
  const scale = THUMB_W / CANVAS_WIDTH
  return (
    <div className="pointer-events-none relative h-full w-full select-none overflow-hidden">
      <div
        aria-hidden
        style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: `scale(${scale})`, transformOrigin: 'top left' }}
        className="absolute left-0 top-0 bg-slate-950"
      >
        <SlideBody slide={slide} />
      </div>
    </div>
  )
}

interface ThumbnailProps {
  slide: UiSlide
  index: number
  isActive: boolean
  busy: boolean
  onSelect: () => void
  onDuplicate: (id: string) => void
  onDelete: (id: string) => void
  onToggleHide: (slide: UiSlide) => void
  dragHandleProps?: Record<string, unknown>
}

export function SlideThumbnail({
  slide,
  index,
  isActive,
  busy,
  onSelect,
  onDuplicate,
  onDelete,
  onToggleHide,
  dragHandleProps,
}: ThumbnailProps) {
  const status = deriveStatus(slide)
  const badge = status ? BADGES[status] : null
  const HideIcon = slide.hidden ? Eye : EyeOff
  return (
    <div
      data-qid={`deck:rail:slide:${slide.id}`}
      data-qs-action="DECK_RAIL_GOTO_SLIDE"
      title={`Go to slide ${slide.order}: ${slide.title}`}
      onClick={onSelect}
      className={`group relative flex cursor-pointer items-center gap-2 rounded-lg border p-1.5 transition-all ${
        isActive
          ? 'border-cyan-500/80 bg-cyan-500/10 ring-1 ring-cyan-500/30'
          : 'border-slate-800/80 bg-slate-900/60 hover:border-slate-700 hover:bg-slate-900'
      } ${slide.hidden ? 'opacity-40' : 'opacity-100'}`}
    >
      <span
        {...dragHandleProps}
        data-qid={`deck:rail:drag:${slide.id}`}
        data-qs-action="DECK_DRAG_SLIDE"
        title={`Drag to reorder slide ${slide.order}`}
        onClick={(event) => event.stopPropagation()}
        className="cursor-grab touch-none rounded p-1 text-slate-600 hover:bg-slate-800/60 active:cursor-grabbing group-hover:text-slate-400"
      >
        <GripVertical aria-hidden className="h-3.5 w-3.5" />
      </span>
      <span className="w-4 text-center font-mono text-[11px] font-medium text-slate-500">{index + 1}</span>
      <div className="relative aspect-video w-28 flex-shrink-0 overflow-hidden rounded border border-slate-800 bg-slate-950 shadow-inner">
        <MiniPreview slide={slide} />
        {badge ? (
          <span
            className={`absolute right-1 top-1 flex items-center gap-1 rounded border px-1 py-0.5 font-mono text-[8px] font-semibold backdrop-blur-md ${badge.className}`}
          >
            <badge.icon aria-hidden className="h-2.5 w-2.5" />
            {badge.label}
          </span>
        ) : null}
      </div>
      <div className="min-w-0 flex-1 pr-1">
        <p className="m-0 truncate text-xs font-medium text-slate-200 group-hover:text-slate-100">{slide.title}</p>
        <p className="m-0 text-[10px] capitalize text-slate-500">{slide.layout.replace('_', ' ')}</p>
      </div>
      <div className="absolute right-2 flex items-center gap-1 rounded border border-slate-700/80 bg-slate-900/95 p-1 opacity-0 shadow-lg backdrop-blur transition-opacity group-hover:opacity-100">
        <button
          type="button"
          data-qid={`deck:rail:hide:${slide.id}`}
          data-qs-action="DECK_TOGGLE_SLIDE_HIDDEN"
          title={slide.hidden ? 'Unhide slide (included in exports)' : 'Hide slide (excluded from exports)'}
          disabled={busy}
          onClick={(event) => {
            event.stopPropagation()
            onToggleHide(slide)
          }}
          className="cursor-pointer rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:opacity-40"
        >
          <HideIcon aria-hidden className="h-3 w-3" />
        </button>
        <button
          type="button"
          data-qid={`deck:rail:duplicate:${slide.id}`}
          data-qs-action="DECK_DUPLICATE_SLIDE"
          title="Duplicate slide"
          disabled={busy}
          onClick={(event) => {
            event.stopPropagation()
            onDuplicate(slide.id)
          }}
          className="cursor-pointer rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:opacity-40"
        >
          <Copy aria-hidden className="h-3 w-3" />
        </button>
        <button
          type="button"
          data-qid={`deck:rail:delete:${slide.id}`}
          data-qs-action="DECK_DELETE_SLIDE"
          title="Delete slide"
          disabled={busy}
          onClick={(event) => {
            event.stopPropagation()
            onDelete(slide.id)
          }}
          className="cursor-pointer rounded p-1 text-slate-400 hover:bg-rose-500/20 hover:text-rose-400 disabled:opacity-40"
        >
          <Trash2 aria-hidden className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}

function SortableThumbnail(props: ThumbnailProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: props.slide.id })
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, zIndex: isDragging ? 50 : 'auto', opacity: isDragging ? 0.4 : 1 }}
    >
      <SlideThumbnail {...props} dragHandleProps={{ ...attributes, ...listeners }} />
    </div>
  )
}

const dropAnimation: DropAnimation = {
  sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: '0.4' } } }),
  duration: 200,
  easing: 'cubic-bezier(0.18, 0.67, 0.6, 1.22)',
}

async function postOp(body: Record<string, unknown>, endpoint: string): Promise<string | null> {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...body, base_revision: revisionStore.current }),
  })
  if (response.ok) return null
  const data = (await response.json()) as { error?: string }
  return data.error ?? `operation failed (${response.status})`
}

export function SlideDrawer({
  deck,
  currentIndex,
  width,
  onSelect,
  onChanged,
  collapsed = false,
  onToggleCollapsed,
}: {
  deck: UiDeckBundle
  currentIndex: number
  width?: number
  collapsed?: boolean
  onToggleCollapsed?: () => void
  onSelect: (index: number) => void
  onChanged: () => void
}) {
  const [draggedId, setDraggedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const run = async (body: Record<string, unknown>, endpoint = '/api/deck-op') => {
    setBusy(true)
    setError(null)
    const failure = await postOp(body, endpoint)
    setBusy(false)
    if (failure) setError(failure)
    else onChanged()
  }

  const onDragEnd = (event: DragEndEvent) => {
    setDraggedId(null)
    const { active, over } = event
    if (!over || active.id === over.id) return
    const target = deck.slides.find((slide) => slide.id === over.id)
    if (!target) return
    void run({ op: 'move_to', slide_id: active.id, target_order: target.order })
  }

  const activeSlide = deck.slides[currentIndex]
  const draggedSlide = deck.slides.find((slide) => slide.id === draggedId) ?? null

  // Collapsed: 48px icon-only strip — numbers stay clickable so navigation
  // never requires re-expanding; the strip's own chevron restores the pane.
  if (collapsed) {
    return (
      <nav
        aria-label="Slides (collapsed)"
        data-qid="deck:rail:strip"
        className="flex select-none flex-col border-r border-slate-800 bg-slate-900/50"
        style={{ width: 48, minWidth: 48, transition: 'width 200ms cubic-bezier(0.16, 1, 0.3, 1)' }}
      >
        <div className="min-h-0 flex-1 overflow-y-auto py-2">
          {deck.slides.map((s, i) => (
            <button
              key={s.id}
              type="button"
              data-qid={`deck:rail:strip:${s.id}`}
              data-qs-action="DECK_GOTO_SLIDE"
              title={`Go to slide ${s.order}: ${s.title}`}
              aria-current={i === currentIndex}
              onClick={() => onSelect(i)}
              className={`mx-auto mb-1 flex h-8 w-8 cursor-pointer items-center justify-center rounded font-mono text-xs ${
                i === currentIndex ? 'bg-cyan-500/15 font-bold text-cyan-300 ring-1 ring-cyan-500/40' : 'text-slate-500 hover:bg-slate-800 hover:text-slate-300'
              }`}
            >
              {s.order}
            </button>
          ))}
        </div>
        {onToggleCollapsed ? (
          <div className="border-t border-slate-800 p-1.5">
            <button
              type="button"
              data-qid="deck:rail:expand"
              data-qs-action="DECK_RAIL_EXPAND"
              aria-label="Expand slide navigation"
              title="Expand slide navigation (Ctrl+B)"
              onClick={onToggleCollapsed}
              className="flex w-full cursor-pointer items-center justify-center rounded py-1 text-slate-500 transition hover:bg-slate-800 hover:text-slate-300"
            >
              <ChevronsRight aria-hidden className="h-4 w-4" />
            </button>
          </div>
        ) : null}
      </nav>
    )
  }

  return (
    <nav
      aria-label="Slides"
      style={{ ...(width ? { width, minWidth: width } : {}), transition: 'width 250ms cubic-bezier(0.16, 1, 0.3, 1)' }}
      className="flex w-64 min-w-64 select-none flex-col bg-slate-900/50"
    >
      <div className="flex items-center justify-between border-b border-slate-800 p-2.5">
        <span className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Slides
          <span className="rounded-full border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
            {deck.slides.length}
          </span>
        </span>
        <button
          type="button"
          data-qid="deck:rail:add-slide"
          data-qs-action="DECK_ADD_SLIDE"
          title="Add a slide after the current one"
          disabled={busy}
          onClick={() => void run({ op: 'add_after', slide_id: activeSlide.id })}
          className="flex cursor-pointer items-center gap-1 rounded bg-cyan-700 px-2 py-1 text-xs font-medium text-white transition-colors hover:bg-cyan-600 disabled:opacity-40"
        >
          <Plus aria-hidden className="h-3.5 w-3.5" /> Add
        </button>
      </div>
      {error ? (
        <p role="alert" className="m-2 rounded-lg border border-rose-500/40 bg-rose-500/10 p-2 text-xs text-rose-300">
          Rejected: {error}
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={(event: DragStartEvent) => setDraggedId(String(event.active.id))}
          onDragCancel={() => setDraggedId(null)}
          onDragEnd={onDragEnd}
        >
          <SortableContext items={deck.slides.map((slide) => slide.id)} strategy={verticalListSortingStrategy}>
            <div className="space-y-2">
              {deck.slides.map((slide, index) => (
                <SortableThumbnail
                  key={slide.id}
                  slide={slide}
                  index={index}
                  isActive={index === currentIndex}
                  busy={busy}
                  onSelect={() => onSelect(index)}
                  onDuplicate={(id) => void run({ op: 'duplicate', slide_id: id })}
                  onDelete={(id) => void run({ op: 'delete', slide_id: id })}
                  onToggleHide={(target) =>
                    void run(
                      { slide_id: target.id, field: 'hidden', value: target.hidden ? 'false' : 'true' },
                      '/api/slide-edit',
                    )
                  }
                />
              ))}
            </div>
          </SortableContext>
          <DragOverlay dropAnimation={dropAnimation}>
            {draggedSlide ? (
              <div className="rotate-1 scale-105 transform cursor-grabbing rounded-lg bg-slate-900 shadow-2xl shadow-cyan-950/80 ring-2 ring-cyan-500">
                <SlideThumbnail
                  slide={draggedSlide}
                  index={deck.slides.findIndex((slide) => slide.id === draggedId)}
                  isActive={false}
                  busy
                  onSelect={() => undefined}
                  onDuplicate={() => undefined}
                  onDelete={() => undefined}
                  onToggleHide={() => undefined}
                />
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      </div>
      {onToggleCollapsed ? (
        <div className="border-t border-slate-800 p-1.5">
          <button
            type="button"
            data-qid="deck:rail:collapse"
            data-qs-action="DECK_RAIL_COLLAPSE"
            aria-label="Collapse slide navigation"
            title="Collapse to icon rail (Ctrl+B)"
            onClick={onToggleCollapsed}
            className="flex w-full cursor-pointer items-center justify-center gap-1 rounded py-1 text-xs text-slate-500 transition hover:bg-slate-800 hover:text-slate-300"
          >
            <ChevronsLeft aria-hidden className="h-3.5 w-3.5" /> Collapse
          </button>
        </div>
      ) : null}
    </nav>
  )
}
