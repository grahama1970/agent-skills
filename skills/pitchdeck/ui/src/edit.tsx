import { createContext, useContext, type ReactNode } from 'react'
import type { UiElement, UiSlide } from './types'

export interface EditRequest {
  slideId: string
  field: string
  label: string
  value: string
}

interface EditContextValue {
  editing: boolean
  request: (edit: EditRequest) => void
  refresh?: () => void
  selectedElementId?: string
  selectElement?: (id: string) => void
  previewElement?: UiElement
}

export const EditContext = createContext<EditContextValue>({ editing: false, request: () => undefined })
export const CanvasScaleContext = createContext(1)

/** Wraps slide text; in edit mode a click opens the edit panel for that field. */
export function Editable({
  slide,
  field,
  label,
  value,
  children,
}: {
  slide: UiSlide
  field: string
  label: string
  value: string
  children: ReactNode
}) {
  const { editing, request } = useContext(EditContext)
  if (!editing) return <>{children}</>
  return (
    <span
      role="button"
      tabIndex={0}
      data-qid={`deck:edit:${slide.id}:${field}`}
      data-qs-action="DECK_EDIT_FIELD"
      title={`Edit ${label} of slide ${slide.order}`}
      onClick={(event) => {
        event.stopPropagation()
        request({ slideId: slide.id, field, label, value })
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') request({ slideId: slide.id, field, label, value })
      }}
      className="cursor-pointer rounded-md outline-dashed outline-2 outline-offset-4 outline-cyan-500/50 transition-colors hover:bg-cyan-500/10"
    >
      {children}
    </span>
  )
}
