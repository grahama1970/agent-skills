import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
import type { BboxBlock } from './types'
import { useRegisterAction } from '../../hooks/useRegisterAction'

pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'

interface PdfAgentNote {
  id: string
  blockId?: string
  bbox: [number, number, number, number]
  title: string
  body: string
  severity: 'high' | 'medium'
  primaryActionLabel: string
  secondaryActionLabel?: string
}

interface PdfCanvasProps {
  pdfUrl: string
  pageNumber: number
  surgicalFocusBBox?: [number, number, number, number] | null
  surgicalCameraEnabled?: boolean
  bboxOverlays?: BboxBlock[]
  compareOverlays?: BboxBlock[]
  agentNotes?: PdfAgentNote[]
  selectedBlockId?: string | null
  activeTaskBlockId?: string | null
  onBlockClick?: (id: string) => void
  onAgentNoteClick?: (noteId: string, blockId?: string) => void
  onAgentNoteAccept?: (noteId: string, blockId?: string) => void
  onAgentNoteSecondary?: (noteId: string, blockId?: string) => void
  onBlockContextMenu?: (id: string, x: number, y: number) => void
  zoom?: number
  editMode?: boolean
  onBlockBBoxChange?: (id: string, bbox: [number, number, number, number]) => void
  onCanvasClick?: () => void
  onCreateBlock?: (bbox: [number, number, number, number]) => void
  fitMode?: 'manual' | 'page'
  interactionMode?: 'draw-block' | 'select-area'
  selectedAreaBBox?: [number, number, number, number] | null
  selectedAreaBlockIds?: string[]
  onSelectArea?: (bbox: [number, number, number, number], blockIds: string[]) => void
  selectedAreaToolbar?: ReactNode
  autoFrameBBox?: [number, number, number, number] | null
  surgicalFocusBlockId?: string | null
}

const SCALE = 1.6
const GLIDE_DURATION = '600ms'
const GLIDE_TIMING = 'cubic-bezier(0.22, 1, 0.36, 1)'

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function getBlockColor(block: BboxBlock): string {
  if (block.id.startsWith('review:')) return '#a78bfa'
  if (block.flagged || block.confidence < 0.6) return '#ef4444'
  if (block.confidence < 0.9) return '#f59e0b'
  return '#23c7d9'
}

export default function PdfCanvas({
  pdfUrl,
  pageNumber,
  surgicalFocusBBox = null,
  surgicalCameraEnabled = false,
  bboxOverlays = [],
  compareOverlays = [],
  selectedBlockId = null,
  activeTaskBlockId = null,
  onBlockClick,
  onBlockContextMenu,
  onCanvasClick,
  selectedAreaBBox = null,
  selectedAreaToolbar,
  autoFrameBBox = null,
}: PdfCanvasProps) {
  useRegisterAction('pdf:page-wrapper', {
    app: 'datalake-explorer',
    action: 'PDF_PAGE_WRAPPER',
    label: 'Page Wrapper',
    description: 'PDF page wrapper in PdfCanvas',
  })
  useRegisterAction('pdf:canvas', {
    app: 'datalake-explorer',
    action: 'PDF_CANVAS',
    label: 'PDF Canvas',
    description: 'Rendered PDF page canvas in PdfCanvas',
  })
  useRegisterAction('pdf:block', {
    app: 'datalake-explorer',
    action: 'PDF_SELECT_BLOCK',
    label: 'Select Block',
    description: 'Select a reviewed extraction block in PdfCanvas',
  })

  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [page, setPage] = useState<PDFPageProxy | null>(null)
  const [dims, setDims] = useState({ w: 0, h: 0 })
  const [containerDims, setContainerDims] = useState({ w: 0, h: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const safeBboxOverlays = Array.isArray(bboxOverlays) ? bboxOverlays : []
  const safeCompareOverlays = Array.isArray(compareOverlays) ? compareOverlays : []

  useEffect(() => {
    const node = containerRef.current
    if (!node) return

    const update = () => setContainerDims({ w: node.clientWidth, h: node.clientHeight })
    update()
    const observer = new ResizeObserver(update)
    observer.observe(node)
    window.addEventListener('resize', update)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [])

  useEffect(() => {
    if (!pdfUrl) return

    let cancelled = false
    setLoading(true)
    setError(null)
    setPdfDoc(null)
    setPage(null)

    const task = pdfjsLib.getDocument(pdfUrl)
    task.promise
      .then((doc) => {
        if (!cancelled) setPdfDoc(doc)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })

    return () => {
      cancelled = true
      task.destroy()
    }
  }, [pdfUrl])

  useEffect(() => {
    if (!pdfDoc) return

    let cancelled = false
    const pdfPage = pageNumber + 1
    if (pdfPage < 1 || pdfPage > pdfDoc.numPages) {
      setError(`Page ${pdfPage} out of range (1-${pdfDoc.numPages})`)
      setLoading(false)
      return
    }

    pdfDoc.getPage(pdfPage)
      .then((loadedPage) => {
        if (cancelled) return
        setPage(loadedPage)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [pdfDoc, pageNumber])

  useEffect(() => {
    if (!page || !canvasRef.current) return

    const canvas = canvasRef.current
    const canvasContext = canvas.getContext('2d')
    if (!canvasContext) return

    const viewport = page.getViewport({ scale: SCALE })
    canvas.width = viewport.width
    canvas.height = viewport.height
    setDims({ w: viewport.width, h: viewport.height })

    const renderTask = page.render({ canvas, canvasContext, viewport })
    renderTask.promise.catch(() => undefined)
    return () => renderTask.cancel()
  }, [page])

  const focusBBox = surgicalFocusBBox ?? autoFrameBBox

  const cameraStyle = useMemo(() => {
    if (!surgicalCameraEnabled || !focusBBox || dims.w === 0 || dims.h === 0) {
      return {
        position: 'relative' as const,
        transitionProperty: 'transform',
        transitionDuration: '600ms',
        transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)',
      }
    }

    const [x1, y1, x2, y2] = focusBBox
    const viewportWidth = containerRef.current?.clientWidth ?? containerDims.w ?? 1280
    const viewportHeight = containerRef.current?.clientHeight ?? containerDims.h ?? 813
    const focusCenterX = ((x1 + x2) / 2) * dims.w
    const focusCenterY = ((y1 + y2) / 2) * dims.h
    const targetX = viewportWidth * 0.4
    const targetY = viewportHeight * 0.6

    return {
      position: 'absolute' as const,
      left: 0,
      top: 0,
      transform: `translate3d(${targetX - focusCenterX}px, ${targetY - focusCenterY}px, 0)`,
      transitionProperty: 'transform',
      transitionDuration: '600ms',
      transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)',
      willChange: 'transform',
    }
  }, [containerDims.h, containerDims.w, dims.h, dims.w, focusBBox, surgicalCameraEnabled])

  if (!pdfUrl) return <PdfCanvasCenter label="No PDF loaded" />
  if (error) return <PdfCanvasCenter label={error} error />
  if (loading) return <PdfCanvasCenter label="Loading PDF..." loading />

  return (
    <div
      ref={containerRef}
      data-qid="pdf:viewport"
      data-qs-action="PDF_VIEWPORT"
      title="PDF surgical viewport"
      style={{
        width: '100%',
        height: '100%',
        overflow: surgicalCameraEnabled ? 'hidden' : 'auto',
        position: 'relative',
        background: '#000',
        display: surgicalCameraEnabled ? 'block' : 'flex',
        alignItems: surgicalCameraEnabled ? undefined : 'center',
        justifyContent: surgicalCameraEnabled ? undefined : 'center',
      }}
      onClick={onCanvasClick}
    >
      <div
        data-qid="pdf:page-wrapper"
        data-qs-action="PDF_PAGE_WRAPPER"
        title="Page Wrapper"
        style={cameraStyle}
      >
        <canvas
          ref={canvasRef}
          data-qid="pdf:canvas"
          data-qs-action="PDF_CANVAS"
          title="PDF page canvas"
          style={{
            display: 'block',
            boxShadow: '0 0 100px rgba(0,0,0,0.5)',
          }}
        />

        {focusBBox && <RectangularSurgicalMask bbox={focusBBox} />}

        {safeCompareOverlays.map((block) => (
          <BBoxOverlay
            key={`compare:${block.id}`}
            block={block}
            color="#94a3b8"
            dashed
            dimmed
          />
        ))}

        {safeBboxOverlays.map((block) => (
          <BBoxOverlay
            key={block.id}
            block={block}
            color={getBlockColor(block)}
            active={block.id === selectedBlockId || block.id === activeTaskBlockId}
            onBlockClick={onBlockClick}
            onBlockContextMenu={onBlockContextMenu}
          />
        ))}

        {focusBBox && (
          <div
            data-qid="pdf:surgical-focus-bbox"
            data-qs-action="PDF_SURGICAL_FOCUS_BBOX"
            title="Measured active surgical focus bbox"
            aria-hidden
            style={{
              position: 'absolute',
              left: `${focusBBox[0] * 100}%`,
              top: `${focusBBox[1] * 100}%`,
              width: `${(focusBBox[2] - focusBBox[0]) * 100}%`,
              height: `${(focusBBox[3] - focusBBox[1]) * 100}%`,
              border: '2px solid #8b5cf6',
              boxShadow: '0 0 20px rgba(139, 92, 246, 0.4)',
              zIndex: 20,
              pointerEvents: 'none',
              transitionProperty: 'left, top, width, height',
              transitionDuration: '600ms',
              transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)',
            }}
          >
            <div
              data-qid="pdf:surgical-thread-dot"
              data-qs-action="PDF_SURGICAL_THREAD_DOT"
              title="Active thread dot"
              style={{
                position: 'absolute',
                right: -6,
                top: '50%',
                width: 12,
                height: 12,
                borderRadius: '50%',
                background: '#f59e0b',
                transform: 'translateY(-50%)',
                boxShadow: '0 0 10px #f59e0b',
              }}
            />
          </div>
        )}

        {selectedAreaBBox && (
          <div
            data-qid="pdf:selected-area"
            data-qs-action="PDF_SELECTED_AREA"
            title="Selected area"
            style={{
              position: 'absolute',
              left: `${selectedAreaBBox[0] * 100}%`,
              top: `${selectedAreaBBox[1] * 100}%`,
              width: `${(selectedAreaBBox[2] - selectedAreaBBox[0]) * 100}%`,
              height: `${(selectedAreaBBox[3] - selectedAreaBBox[1]) * 100}%`,
              border: '1.5px dashed rgba(245, 158, 11, 0.95)',
              backgroundColor: 'rgba(245, 158, 11, 0.06)',
              zIndex: 25,
              pointerEvents: 'none',
            }}
          />
        )}

        {selectedAreaBBox && selectedAreaToolbar && (
          <div
            data-qid="pdf-lab:contextual-toolbar"
            data-qs-action="PDF_LAB_CONTEXTUAL_TOOLBAR"
            title="Contextual toolbar"
            style={{
              position: 'absolute',
              left: `${selectedAreaBBox[0] * 100}%`,
              top: `${selectedAreaBBox[1] * 100}%`,
              transform: 'translateY(calc(-100% - 8px))',
              zIndex: 30,
              pointerEvents: 'auto',
            }}
          >
            {selectedAreaToolbar}
          </div>
        )}
      </div>
    </div>
  )
}

interface BBoxOverlayProps {
  block: BboxBlock
  color: string
  active?: boolean
  dashed?: boolean
  dimmed?: boolean
  onBlockClick?: (id: string) => void
  onBlockContextMenu?: (id: string, x: number, y: number) => void
}

function BBoxOverlay({
  block,
  color,
  active = false,
  dashed = false,
  dimmed = false,
  onBlockClick,
  onBlockContextMenu,
}: BBoxOverlayProps) {
  const [x1, y1, x2, y2] = block.bbox

  return (
    <button
      data-qid={`pdf:block:${block.id}`}
      data-qs-action="PDF_SELECT_BLOCK"
      title={`${block.blockType} block, ${Math.round(block.confidence * 100)}% confidence`}
      type="button"
      onClick={(event) => {
        event.stopPropagation()
        onBlockClick?.(block.id)
      }}
      onContextMenu={(event) => {
        event.preventDefault()
        event.stopPropagation()
        onBlockContextMenu?.(block.id, event.clientX, event.clientY)
      }}
      style={{
        position: 'absolute',
        left: `${x1 * 100}%`,
        top: `${y1 * 100}%`,
        width: `${(x2 - x1) * 100}%`,
        height: `${(y2 - y1) * 100}%`,
        border: `${active ? 2 : 1.5}px ${dashed ? 'dashed' : 'solid'} ${color}`,
        background: active ? 'rgba(124, 58, 237, 0.1)' : dimmed ? 'rgba(148, 163, 184, 0.04)' : 'transparent',
        opacity: dimmed ? 0.45 : 1,
        padding: 0,
        zIndex: active ? 18 : 12,
        cursor: 'pointer',
        boxSizing: 'border-box',
      }}
    />
  )
}

function RectangularSurgicalMask({ bbox }: { bbox: [number, number, number, number] }) {
  const [x1, y1, x2, y2] = bbox
  const dimStyle = {
    position: 'absolute' as const,
    backgroundColor: 'rgba(0,0,0,0.85)',
    pointerEvents: 'none' as const,
    transitionProperty: 'left, top, right, bottom, width, height',
    transitionDuration: GLIDE_DURATION,
    transitionTimingFunction: GLIDE_TIMING,
  }

  return (
    <div
      data-qid="pdf:surgical-mask"
      data-qs-action="PDF_SURGICAL_MASK"
      title="Surgical rectangular mask"
      aria-hidden
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 10,
        pointerEvents: 'none',
      }}
    >
      <div
        data-qid="pdf:surgical-mask:top"
        style={{
          ...dimStyle,
          left: 0,
          top: 0,
          width: '100%',
          height: `${clamp(y1, 0, 1) * 100}%`,
        }}
      />
      <div
        data-qid="pdf:surgical-mask:bottom"
        style={{
          ...dimStyle,
          left: 0,
          top: `${clamp(y2, 0, 1) * 100}%`,
          width: '100%',
          bottom: 0,
        }}
      />
      <div
        data-qid="pdf:surgical-mask:left"
        style={{
          ...dimStyle,
          left: 0,
          top: `${clamp(y1, 0, 1) * 100}%`,
          width: `${clamp(x1, 0, 1) * 100}%`,
          height: `${clamp(y2 - y1, 0, 1) * 100}%`,
        }}
      />
      <div
        data-qid="pdf:surgical-mask:right"
        style={{
          ...dimStyle,
          left: `${clamp(x2, 0, 1) * 100}%`,
          top: `${clamp(y1, 0, 1) * 100}%`,
          right: 0,
          height: `${clamp(y2 - y1, 0, 1) * 100}%`,
        }}
      />
    </div>
  )
}

function PdfCanvasCenter({ label, error = false, loading = false }: { label: string; error?: boolean; loading?: boolean }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100%',
        backgroundColor: '#0f1216',
        color: error ? '#ff4444' : '#999999',
        fontFamily: 'monospace',
        fontSize: 12,
        textAlign: 'center',
      }}
    >
      {loading && <Spinner />}
      <span style={{ marginTop: loading ? 8 : 0, maxWidth: '80%' }}>{label}</span>
    </div>
  )
}

function Spinner() {
  return (
    <div
      style={{
        width: 24,
        height: 24,
        border: '2px solid transparent',
        borderTop: '2px solid #4a9eff',
        borderRadius: '50%',
        animation: 'pdfcanvas-spin 0.8s linear infinite',
      }}
    >
      <style>{`@keyframes pdfcanvas-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
