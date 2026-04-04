import { useEffect, useRef, useState, useCallback } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
import type { BboxBlock } from '../types'
import { BLOCK_TYPE_COLORS } from './BboxWorkspace'

pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PdfCanvasProps {
  pdfUrl: string
  pageNumber: number
  bboxOverlays: BboxBlock[]
  selectedBlockId: string | null
  onBlockClick: (id: string) => void
  zoom: number
  editMode?: boolean
}

const DEFAULT_DPI = 150
const SCALE = DEFAULT_DPI / 72 // pdf.js uses 72 DPI internally

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PdfCanvas({
  pdfUrl,
  pageNumber,
  bboxOverlays,
  selectedBlockId,
  onBlockClick,
  zoom,
  editMode = false,
}: PdfCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const overlayRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null)
  const [page, setPage] = useState<PDFPageProxy | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dims, setDims] = useState({ w: 0, h: 0 })

  // -----------------------------------------------------------------------
  // Load PDF document
  // -----------------------------------------------------------------------
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
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : String(err)
          setError(msg)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
      task.destroy()
    }
  }, [pdfUrl])

  // -----------------------------------------------------------------------
  // Load page when doc or pageNumber changes
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!pdfDoc) return

    let cancelled = false
    // pdfjs pages are 1-indexed; our pageNumber is 0-indexed
    const pdfPage = pageNumber + 1
    if (pdfPage < 1 || pdfPage > pdfDoc.numPages) {
      setError(`Page ${pdfPage} out of range (1-${pdfDoc.numPages})`)
      setLoading(false)
      return
    }

    pdfDoc.getPage(pdfPage).then((p) => {
      if (!cancelled) {
        setPage(p)
        setLoading(false)
      }
    }).catch((err: unknown) => {
      if (!cancelled) {
        const msg = err instanceof Error ? err.message : String(err)
        setError(msg)
        setLoading(false)
      }
    })

    return () => { cancelled = true }
  }, [pdfDoc, pageNumber])

  // -----------------------------------------------------------------------
  // Render page to canvas
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!page || !canvasRef.current) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const viewport = page.getViewport({ scale: SCALE * zoom })
    canvas.width = viewport.width
    canvas.height = viewport.height
    setDims({ w: viewport.width, h: viewport.height })

    let cancelled = false
    const renderTask = page.render({ canvas, canvasContext: ctx, viewport })
    renderTask.promise.catch(() => {
      if (!cancelled) { /* render cancelled, ignore */ }
    })

    return () => {
      cancelled = true
      renderTask.cancel()
    }
  }, [page, zoom])

  // -----------------------------------------------------------------------
  // Draw bbox overlays
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!overlayRef.current || dims.w === 0) return

    const canvas = overlayRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    canvas.width = dims.w
    canvas.height = dims.h
    ctx.clearRect(0, 0, dims.w, dims.h)

    for (const block of bboxOverlays) {
      const [x1, y1, x2, y2] = block.bbox
      const rx = x1 * dims.w
      const ry = y1 * dims.h
      const rw = (x2 - x1) * dims.w
      const rh = (y2 - y1) * dims.h

      const isSelected = block.id === selectedBlockId
      const color = BLOCK_TYPE_COLORS[block.blockType]

      // Fill
      ctx.fillStyle = isSelected ? 'rgba(124, 58, 237, 0.12)' : `${color}18`
      ctx.fillRect(rx, ry, rw, rh)

      // Stroke
      if (isSelected) {
        ctx.strokeStyle = '#7c3aed'
        ctx.lineWidth = 2
      } else {
        ctx.strokeStyle = `${color}99`
        ctx.lineWidth = 1
      }
      ctx.strokeRect(rx, ry, rw, rh)
    }
  }, [bboxOverlays, selectedBlockId, dims])

  // -----------------------------------------------------------------------
  // Click detection on overlay canvas
  // -----------------------------------------------------------------------
  const handleOverlayClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!overlayRef.current || dims.w === 0) return

      const rect = overlayRef.current.getBoundingClientRect()
      const scaleX = dims.w / rect.width
      const scaleY = dims.h / rect.height
      const cx = (e.clientX - rect.left) * scaleX
      const cy = (e.clientY - rect.top) * scaleY

      // Normalized coords
      const nx = cx / dims.w
      const ny = cy / dims.h

      // Find smallest block containing click (most specific match)
      let best: BboxBlock | null = null
      let bestArea = Infinity
      for (const block of bboxOverlays) {
        const [x1, y1, x2, y2] = block.bbox
        if (nx >= x1 && nx <= x2 && ny >= y1 && ny <= y2) {
          const area = (x2 - x1) * (y2 - y1)
          if (area < bestArea) {
            bestArea = area
            best = block
          }
        }
      }

      if (best) {
        onBlockClick(best.id)
      }
    },
    [bboxOverlays, dims, onBlockClick]
  )

  // -----------------------------------------------------------------------
  // Render states
  // -----------------------------------------------------------------------

  if (!pdfUrl) {
    return (
      <div style={centerStyle}>
        <span style={{ color: '#999999', fontFamily: 'monospace', fontSize: '13px' }}>
          No PDF loaded
        </span>
      </div>
    )
  }

  if (error) {
    return (
      <div style={centerStyle}>
        <span style={{ color: '#ff4444', fontFamily: 'monospace', fontSize: '12px', maxWidth: '80%', textAlign: 'center' }}>
          {error}
        </span>
      </div>
    )
  }

  if (loading) {
    return (
      <div style={centerStyle}>
        <Spinner />
        <span style={{ color: '#999999', fontFamily: 'monospace', fontSize: '11px', marginTop: '8px' }}>
          Loading PDF...
        </span>
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        width: '100%',
        height: '100%',
        overflow: 'auto',
        backgroundColor: '#0f1216',
      }}
    >
      <div style={{ position: 'relative', flexShrink: 0, margin: '12px' }}>
        <canvas ref={canvasRef} style={{ display: 'block' }} />
        <canvas
          ref={overlayRef}
          onClick={handleOverlayClick}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            cursor: 'crosshair',
          }}
        />
        {/* 4b.2: 8 resize handles on selected block in edit mode */}
        {editMode && selectedBlockId && (() => {
          const sel = bboxOverlays.find((b) => b.id === selectedBlockId)
          if (!sel || dims.w === 0) return null
          const cw = containerRef.current?.querySelector('canvas')?.clientWidth ?? dims.w
          const ch = containerRef.current?.querySelector('canvas')?.clientHeight ?? dims.h
          const [x1, y1, x2, y2] = sel.bbox
          const left = x1 * cw
          const top_ = y1 * ch
          const right = x2 * cw
          const bottom = y2 * ch
          const mx = (left + right) / 2
          const my = (top_ + bottom) / 2
          const HS = 8 // handle size (4b.2: 8x8px)
          const handles = [
            { x: left, y: top_, cursor: 'nw-resize' },
            { x: mx, y: top_, cursor: 'n-resize' },
            { x: right, y: top_, cursor: 'ne-resize' },
            { x: right, y: my, cursor: 'e-resize' },
            { x: right, y: bottom, cursor: 'se-resize' },
            { x: mx, y: bottom, cursor: 's-resize' },
            { x: left, y: bottom, cursor: 'sw-resize' },
            { x: left, y: my, cursor: 'w-resize' },
          ]
          return handles.map((h, i) => (
            <div
              key={i}
              style={{
                position: 'absolute',
                left: `${h.x - HS / 2}px`,
                top: `${h.y - HS / 2}px`,
                width: `${HS}px`,
                height: `${HS}px`,
                backgroundColor: '#7c3aed',
                border: '1px solid #5b21b6',
                borderRadius: '1px',
                cursor: h.cursor,
                zIndex: 10,
                pointerEvents: 'auto',
              }}
            />
          ))
        })()}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const centerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  width: '100%',
  height: '100%',
  backgroundColor: '#0f1216',
}

function Spinner() {
  return (
    <div
      style={{
        width: '24px',
        height: '24px',
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
