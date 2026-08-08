import React, { useCallback, useEffect, useRef, useState } from 'react'
import { PanelBottom, PanelRight, X } from 'lucide-react'
import { useRegisterAction } from '../hooks/useRegisterAction'

const MIN_WIDTH = 420
const MAX_WIDTH = 800
const DEFAULT_WIDTH = 480
const STORAGE_KEY = 'sparta_console_drawer_width'

export type EmbryDrawerDock = 'right' | 'bottom'

interface EmbryDrawerProps {
  isOpen: boolean
  onClose: () => void
  children: React.ReactNode
  dock?: EmbryDrawerDock
  onDockChange?: (dock: EmbryDrawerDock) => void
  title?: string
  qid?: string
}

export default function EmbryDrawer({
  isOpen,
  onClose,
  children,
  dock = 'right',
  onDockChange,
  title = 'Console',
  qid = 'sparta:console:drawer',
}: EmbryDrawerProps): JSX.Element {
  const [width, setWidth] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_WIDTH
    const savedWidth = window.localStorage.getItem(STORAGE_KEY)
    const parsedWidth = savedWidth ? Number.parseInt(savedWidth, 10) : DEFAULT_WIDTH
    return Number.isFinite(parsedWidth) ? Math.min(Math.max(parsedWidth, MIN_WIDTH), MAX_WIDTH) : DEFAULT_WIDTH
  })
  const [isResizing, setIsResizing] = useState(false)
  const widthRef = useRef(width)
  const isBottomDock = dock === 'bottom'

  useRegisterAction(`${qid}:close`, {
    app: 'persona-dream-ux',
    action: 'CLOSE_CHAT',
    label: 'Close Console',
    description: 'Close the Console drawer',
  })
  useRegisterAction(`${qid}:resize-handle`, {
    app: 'persona-dream-ux',
    action: 'RESIZE_CHAT',
    label: 'Resize Console',
    description: 'Resize the Console drawer',
  })

  const handleMouseMove = useCallback((event: MouseEvent) => {
    if (!isResizing || isBottomDock) return
    const rawWidth = document.documentElement.clientWidth - event.clientX
    const nextWidth = Math.min(Math.max(rawWidth, MIN_WIDTH), MAX_WIDTH)
    widthRef.current = nextWidth
    setWidth(nextWidth)
  }, [isBottomDock, isResizing])

  const handleMouseUp = useCallback(() => {
    setIsResizing(false)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, String(widthRef.current))
    }
  }, [])

  useEffect(() => {
    if (!isResizing) return undefined
    const previousUserSelect = document.body.style.userSelect
    const previousCursor = document.body.style.cursor
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.userSelect = previousUserSelect
      document.body.style.cursor = previousCursor
    }
  }, [handleMouseMove, handleMouseUp, isResizing])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  return (
    <>
    {isResizing ? (
      <div
        data-qid={`${qid}:resize-overlay`}
        aria-hidden="true"
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 9999,
          cursor: 'col-resize',
        }}
      />
    ) : null}
    <aside
      id="sparta-chat-slideover"
      data-qid={qid}
      aria-hidden={!isOpen}
      style={{
        width: isBottomDock ? '100%' : isOpen ? width : 0,
        minWidth: isBottomDock ? 0 : isOpen ? MIN_WIDTH : 0,
        maxWidth: isBottomDock ? '100%' : isOpen ? MAX_WIDTH : 0,
        height: isBottomDock ? (isOpen ? '45vh' : 0) : '100%',
        minHeight: isBottomDock ? (isOpen ? 300 : 0) : 0,
        maxHeight: isBottomDock ? '70vh' : undefined,
        opacity: isOpen ? 1 : 0,
        backgroundColor: 'var(--surface-deepest)',
        borderLeft: isBottomDock ? 0 : '1px solid var(--border-default)',
        borderTop: isBottomDock ? '1px solid var(--border-default)' : 0,
        borderRadius: 0,
        boxShadow: isOpen ? isBottomDock ? '0 -8px 24px rgba(0,0,0,0.5)' : '-8px 0 24px rgba(0,0,0,0.5)' : 'none',
        zIndex: 900,
        display: 'flex',
        flexDirection: 'column',
        transform: isOpen ? 'translate(0, 0)' : isBottomDock ? 'translateY(100%)' : 'translateX(100%)',
        transition: isResizing ? 'none' : 'transform 0.3s cubic-bezier(0.165, 0.84, 0.44, 1), opacity 0.2s ease, box-shadow 0.2s ease',
        pointerEvents: isOpen ? 'auto' : 'none',
        overflow: 'hidden',
        flex: isOpen ? isBottomDock ? '0 0 45vh' : `0 0 ${width}px` : '0 0 0px',
        flexShrink: 0,
        position: 'relative',
        willChange: 'transform, opacity',
      }}
    >
        {!isBottomDock ? (
        <div
          data-qid={`${qid}:resize-handle`}
          data-qs-action="RESIZE_CHAT"
          title="Resize Console"
          onMouseDown={(event) => {
            event.preventDefault()
            setIsResizing(true)
          }}
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: -5,
            width: 10,
            cursor: 'col-resize',
            zIndex: 9992,
            display: 'flex',
            justifyContent: 'center',
            opacity: isResizing ? 1 : 0,
            transition: 'opacity 0.2s ease',
          }}
          onMouseEnter={(event) => {
            if (!isResizing) {
              event.currentTarget.style.opacity = '1'
            }
          }}
          onMouseLeave={(event) => {
            if (!isResizing) {
              event.currentTarget.style.opacity = '0'
            }
          }}
        >
          <div
            aria-hidden="true"
            style={{
              width: 2,
              height: '100%',
              backgroundColor: isResizing ? '#3b82f6' : 'rgba(59, 130, 246, 0.5)',
              transition: 'background-color 0.2s ease',
            }}
          />
        </div>
        ) : null}

        <header
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '16px 24px',
            borderBottom: '1px solid #222',
            backgroundColor: '#000',
            borderRadius: 0,
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
            <span style={{ color: '#FFF', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap' }}>
              {title}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            {onDockChange ? (
              <button
                type="button"
                data-qid={`${qid}:dock-toggle`}
                data-qs-action="TOGGLE_CONSOLE_DOCK"
                title={isBottomDock ? 'Dock Console to right' : 'Dock Console to bottom'}
                aria-label={isBottomDock ? 'Dock Console to right' : 'Dock Console to bottom'}
                onClick={() => onDockChange(isBottomDock ? 'right' : 'bottom')}
                style={{
                  background: 'transparent',
                  border: '1px solid rgba(148, 163, 184, 0.18)',
                  color: '#888',
                  cursor: 'pointer',
                  padding: 5,
                  borderRadius: 4,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease',
                }}
              >
                {isBottomDock ? <PanelRight size={14} strokeWidth={1.8} aria-hidden="true" /> : <PanelBottom size={14} strokeWidth={1.8} aria-hidden="true" />}
              </button>
            ) : null}
            <span style={{ color: '#888', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#0070F3', display: 'inline-block' }} />
              Connected
            </span>
          <button
            type="button"
            data-qid={`${qid}:close`}
            data-qs-action="CLOSE_CHAT"
            title="Close drawer (Esc)"
            aria-label="Close Console"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#888',
              cursor: 'pointer',
              padding: 4,
              borderRadius: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.2s ease, color 0.2s ease',
            }}
            onMouseEnter={(event) => {
              event.currentTarget.style.backgroundColor = '#0A0A0A'
              event.currentTarget.style.color = '#EDEDED'
            }}
            onMouseLeave={(event) => {
              event.currentTarget.style.backgroundColor = 'transparent'
              event.currentTarget.style.color = '#888'
            }}
          >
            <X size={14} strokeWidth={1.8} aria-hidden="true" />
          </button>
          </div>
        </header>

        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', borderRadius: 0 }}>
          {children}
        </div>
    </aside>
    </>
  )
}
