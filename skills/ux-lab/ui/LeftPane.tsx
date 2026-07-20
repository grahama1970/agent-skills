/**
 * LeftPane — shared collapsible side explorer panel.
 *
 * Ported from pi-mono packages/ux-lab/src/components/common/LeftPane.tsx and
 * kept self-contained for @agent-skills/ux-lab-ui hosts.
 */
import * as React from 'react'
import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react'
import { ArrowDownAZ, ArrowDownWideNarrow, Clock, PanelLeft, PanelLeftClose, PanelLeftOpen, Search } from 'lucide-react'

const EMBRY = {
  bgCard: '#1a1a1a',
  bgPanel: '#111111',
  bgDeep: '#0b1220',
  border: 'rgba(255, 255, 255, 0.13)',
  accent: '#7c3aed',
  white: '#f5f5f5',
  dim: '#94a3b8',
  red: '#ff4444',
  nvisGreenA: '#00CC00',
} as const

const labelStyle = {
  fontSize: 10,
  fontWeight: 700,
  textTransform: 'uppercase' as const,
  letterSpacing: '0.15em',
  color: EMBRY.dim,
} as const

const MONO = '"JetBrains Mono", "SF Mono", monospace'

type ActionDef = {
  app: string
  action: string
  label: string
  description: string
}

function useRegisterAction(_elementId: string, _def: ActionDef): void {
  // Host applications may register qids separately. The shared package keeps
  // data-qid/data-qs-action attributes stable without owning a memory daemon.
}

export type ContextMenuAction = 'rename' | 'delete' | 'copy'

interface ContextMenuProps {
  x: number
  y: number
  visible: boolean
  onAction: (action: ContextMenuAction) => void
  onClose: () => void
}

const menuItemBase: React.CSSProperties = {
  padding: '6px 16px',
  fontSize: 11,
  fontFamily: MONO,
  color: EMBRY.white,
  cursor: 'pointer',
  background: 'transparent',
  border: 'none',
  width: '100%',
  textAlign: 'left',
  transition: 'background 0.1s',
}

const MENU_ITEMS: { action: ContextMenuAction; label: string; color?: string }[] = [
  { action: 'rename', label: 'Rename' },
  { action: 'copy', label: 'Copy' },
  { action: 'delete', label: 'Delete', color: EMBRY.red },
]

export function ContextMenu({ x, y, visible, onAction, onClose }: ContextMenuProps): JSX.Element | null {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!visible) return
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [visible, onClose])

  if (!visible) return null

  return (
    <div
      ref={ref}
      style={{
        position: 'fixed',
        left: x,
        top: y,
        zIndex: 9999,
        background: EMBRY.bgCard,
        border: `1px solid ${EMBRY.border}`,
        borderRadius: 6,
        padding: '4px 0',
        minWidth: 120,
        boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
      }}
    >
      {MENU_ITEMS.map(({ action, label, color }) => {
        const qs =
          action === 'rename'
            ? 'LEFT_PANE_CONTEXT_RENAME'
            : action === 'copy'
              ? 'LEFT_PANE_CONTEXT_COPY'
              : 'LEFT_PANE_CONTEXT_DELETE'
        return (
          <button
            key={action}
            type="button"
            data-qid={`left-pane:context:${action}`}
            data-qs-action={qs}
            title={label}
            style={{ ...menuItemBase, color: color ?? EMBRY.white }}
            onMouseEnter={(event) => {
              event.currentTarget.style.background = 'rgba(255,255,255,0.06)'
            }}
            onMouseLeave={(event) => {
              event.currentTarget.style.background = 'transparent'
            }}
            onClick={() => {
              onAction(action)
              onClose()
            }}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

export function useContextMenu(onContextMenu?: (itemId: string, action: ContextMenuAction) => void): {
  menuProps: ContextMenuProps | null
  triggerContextMenu: (event: React.MouseEvent, itemId: string) => void
} {
  const [menu, setMenu] = useState<{ x: number; y: number; itemId: string } | null>(null)

  const triggerContextMenu = useCallback((event: React.MouseEvent, itemId: string) => {
    event.preventDefault()
    setMenu({ x: event.clientX, y: event.clientY, itemId })
  }, [])

  const close = useCallback(() => setMenu(null), [])

  const menuProps = menu
    ? {
        x: menu.x,
        y: menu.y,
        visible: true,
        onAction: (action: ContextMenuAction) => onContextMenu?.(menu.itemId, action),
        onClose: close,
      }
    : null

  return { menuProps, triggerContextMenu }
}

export type SortMode = 'recent' | 'score' | 'alpha'

const SORT_ICONS: { mode: SortMode; Icon: typeof Clock; title: string }[] = [
  { mode: 'recent', Icon: Clock, title: 'Sort by recent' },
  { mode: 'score', Icon: ArrowDownWideNarrow, title: 'Sort by score' },
  { mode: 'alpha', Icon: ArrowDownAZ, title: 'Sort A-Z' },
]

export interface LeftPaneDockToggleProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label' | 'onClick'> {
  collapsed: boolean
  onToggle: () => void
  qid?: string
  action?: string
  label?: string
  showTitle?: string
  hideTitle?: string
}

export function LeftPaneDockToggle({
  collapsed,
  onToggle,
  qid,
  action,
  label = 'Toggle left pane',
  showTitle = 'Expand left pane',
  hideTitle = 'Collapse left pane',
  style,
  ...buttonProps
}: LeftPaneDockToggleProps): JSX.Element {
  return (
    <button
      {...buttonProps}
      type="button"
      data-qid={qid}
      data-qs-action={action}
      aria-label={label}
      aria-pressed={collapsed}
      title={collapsed ? showTitle : hideTitle}
      onClick={onToggle}
      style={{
        background: 'transparent',
        border: 'none',
        color: collapsed ? EMBRY.nvisGreenA : '#8b949e',
        backgroundColor: collapsed ? 'rgba(0, 204, 0, 0.10)' : 'transparent',
        cursor: 'pointer',
        padding: 6,
        borderRadius: 4,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 0.2s ease',
        minWidth: 32,
        minHeight: 32,
        ...style,
      }}
    >
      {collapsed ? <PanelLeft size={18} strokeWidth={2} aria-hidden="true" /> : <PanelLeftClose size={18} strokeWidth={2} aria-hidden="true" />}
    </button>
  )
}

export type PaneSide = 'left' | 'right'

export interface PaneCollapseButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label' | 'onClick'> {
  side: PaneSide
  collapsed: boolean
  onToggle: () => void
  qid?: string
  action?: string
  label?: string
}

export function PaneCollapseButton({
  side,
  collapsed,
  onToggle,
  qid,
  action,
  label,
  style,
  ...buttonProps
}: PaneCollapseButtonProps): JSX.Element {
  const isLeft = side === 'left'
  const title = label ?? `${collapsed ? 'Expand' : 'Collapse'} ${side} pane`
  const icon = collapsed
    ? isLeft
      ? <PanelLeftOpen size={18} strokeWidth={1.9} aria-hidden="true" />
      : <PanelLeftClose size={18} strokeWidth={1.9} aria-hidden="true" style={{ transform: 'rotate(180deg)' }} />
    : isLeft
      ? <PanelLeftClose size={18} strokeWidth={1.9} aria-hidden="true" />
      : <PanelLeftOpen size={18} strokeWidth={1.9} aria-hidden="true" style={{ transform: 'rotate(180deg)' }} />

  return (
    <button
      {...buttonProps}
      type="button"
      data-qid={qid}
      data-qs-action={action}
      aria-label={title}
      aria-pressed={collapsed}
      title={title}
      onClick={onToggle}
      style={{
        background: 'none',
        border: 'none',
        color: EMBRY.dim,
        cursor: 'pointer',
        padding: 8,
        borderRadius: 6,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'background-color 0.2s, color 0.2s',
        ...style,
      }}
    >
      {icon}
    </button>
  )
}

export interface CollapsiblePaneFrameProps {
  side: PaneSide
  collapsed: boolean
  onCollapsedChange: (collapsed: boolean) => void
  children: React.ReactNode
  width: number | string
  collapsedWidth?: number | string
  qid?: string
  expandQid?: string
  collapseQid?: string
  expandAction?: string
  collapseAction?: string
  backgroundColor?: string
  borderColor?: string
  style?: React.CSSProperties
  collapsedStyle?: React.CSSProperties
}

export function CollapsiblePaneFrame({
  side,
  collapsed,
  onCollapsedChange,
  children,
  width,
  collapsedWidth = 56,
  qid,
  expandQid,
  collapseQid,
  expandAction,
  collapseAction,
  backgroundColor = 'rgba(8,14,24,0.82)',
  borderColor = EMBRY.border,
  style,
  collapsedStyle,
}: CollapsiblePaneFrameProps): JSX.Element {
  const size = collapsed ? collapsedWidth : width
  const borderProp = side === 'left' ? 'borderRight' : 'borderLeft'
  const justify = side === 'left' ? 'center' : 'center'

  return (
    <div
      data-qid={qid}
      data-collapsed={collapsed ? 'true' : 'false'}
      style={{
        width: size,
        display: 'flex',
        flexDirection: 'column',
        backgroundColor,
        flexShrink: 0,
        [borderProp]: `1px solid ${borderColor}`,
        transition: 'width 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        overflow: 'hidden',
        ...style,
      }}
    >
      {collapsed ? (
        <div style={{ padding: '16px 0', display: 'flex', justifyContent: justify, ...collapsedStyle }}>
          <PaneCollapseButton
            side={side}
            collapsed
            onToggle={() => onCollapsedChange(false)}
            qid={expandQid}
            action={expandAction}
          />
        </div>
      ) : (
        <CollapsiblePaneContext.Provider value={{ side, collapseQid, collapseAction, onCollapsedChange }}>
          {children}
        </CollapsiblePaneContext.Provider>
      )}
    </div>
  )
}

const CollapsiblePaneContext = createContext<{
  side: PaneSide
  collapseQid?: string
  collapseAction?: string
  onCollapsedChange: (collapsed: boolean) => void
} | null>(null)

export function useCollapsiblePane(): {
  side: PaneSide
  collapseButton: JSX.Element
  collapse: () => void
} {
  const context = useContext(CollapsiblePaneContext)
  if (!context) {
    throw new Error('useCollapsiblePane must be used inside CollapsiblePaneFrame')
  }
  return {
    side: context.side,
    collapse: () => context.onCollapsedChange(true),
    collapseButton: (
      <PaneCollapseButton
        side={context.side}
        collapsed={false}
        onToggle={() => context.onCollapsedChange(true)}
        qid={context.collapseQid}
        action={context.collapseAction}
        style={{ padding: 4 }}
      />
    ),
  }
}

export interface LeftPaneProps {
  title: string
  children: React.ReactNode
  width?: number
  minWidth?: number
  maxWidth?: number
  resizable?: boolean
  onWidthChange?: (width: number) => void
  resizeQid?: string
  resizeAction?: string
  resizeTitle?: string
  defaultCollapsed?: boolean
  collapsed?: boolean
  onCollapsedChange?: (collapsed: boolean) => void
  searchable?: boolean
  searchTestId?: string
  sortable?: boolean
  sortModes?: SortMode[]
  activeFilter?: string
  onClearFilter?: () => void
  search?: string
  onSearchChange?: React.Dispatch<React.SetStateAction<string>>
  searchPlaceholder?: string
  collapsible?: boolean
  collapsedWidth?: number
  qid?: string
  bodyStyle?: React.CSSProperties
}

export function LeftPane({
  title,
  children,
  width = 260,
  minWidth = 240,
  maxWidth = 520,
  resizable = false,
  onWidthChange,
  resizeQid,
  resizeAction = 'LEFT_PANE_RESIZE',
  resizeTitle = `Resize ${title}`,
  defaultCollapsed = false,
  collapsed: controlledCollapsed,
  onCollapsedChange,
  searchable = false,
  searchTestId,
  sortable = false,
  sortModes,
  activeFilter,
  onClearFilter,
  search: externalSearch,
  onSearchChange,
  searchPlaceholder = 'Filter...',
  collapsible = true,
  collapsedWidth = 32,
  qid,
  bodyStyle,
}: LeftPaneProps): JSX.Element {
  const paneId = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'pane'
  const [internalCollapsed, setInternalCollapsed] = useState(defaultCollapsed)
  const [internalWidth, setInternalWidth] = useState(typeof width === 'number' ? width : minWidth)
  const collapsed = controlledCollapsed ?? internalCollapsed
  const renderedWidth = onWidthChange || typeof width === 'string' ? width : internalWidth
  const setCollapsed = useCallback((next: boolean) => {
    if (controlledCollapsed === undefined) setInternalCollapsed(next)
    onCollapsedChange?.(next)
  }, [controlledCollapsed, onCollapsedChange])
  useEffect(() => {
    if (typeof width === 'number') setInternalWidth(width)
  }, [width])
  const startResize = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (!resizable || collapsed) return
    event.preventDefault()
    const startX = event.clientX
    const rectWidth = event.currentTarget.parentElement?.getBoundingClientRect().width
    const startWidth = typeof width === 'number' ? width : rectWidth ?? internalWidth
    const onMouseMove = (moveEvent: MouseEvent) => {
      const next = Math.max(minWidth, Math.min(maxWidth, Math.round(startWidth + moveEvent.clientX - startX)))
      if (onWidthChange) onWidthChange(next)
      else setInternalWidth(next)
    }
    const onMouseUp = () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [collapsed, internalWidth, maxWidth, minWidth, onWidthChange, resizable, width])
  const [internalSearch, setInternalSearch] = useState('')
  const search = externalSearch ?? internalSearch
  const setSearch = onSearchChange ?? setInternalSearch
  const [sortMode, setSortMode] = useState<SortMode>('recent')
  const modes = sortModes ?? ['recent', 'score', 'alpha']

  useRegisterAction(`left-pane:${paneId}:expand`, {
    app: 'ux-lab',
    action: 'LEFT_PANE_EXPAND',
    label: `Expand ${title}`,
    description: `Expand the ${title} left pane`,
  })
  useRegisterAction(`left-pane:${paneId}:collapse`, {
    app: 'ux-lab',
    action: 'LEFT_PANE_COLLAPSE',
    label: `Collapse ${title}`,
    description: `Collapse the ${title} left pane`,
  })

  if (collapsed) {
    return (
      <div
        data-qid={qid}
        data-collapsed="true"
        style={{
          width: collapsedWidth,
          flexShrink: 0,
          borderRight: `1px solid ${EMBRY.border}`,
          background: EMBRY.bgPanel,
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'center',
          paddingTop: 12,
          overflow: 'hidden',
        }}
      >
        {collapsible ? (
          <button
            type="button"
            data-qid={`left-pane:${paneId}:expand`}
            data-qs-action="LEFT_PANE_EXPAND"
            title={`Expand ${title}`}
            onClick={() => setCollapsed(false)}
            aria-label={`Expand ${title}`}
            style={{ background: 'none', border: 'none', color: EMBRY.dim, cursor: 'pointer', padding: 2 }}
          >
            <PanelLeftOpen size={14} />
          </button>
        ) : null}
      </div>
    )
  }

  return (
    <LeftPaneContext.Provider value={search}>
      <LeftPaneSortContext.Provider value={sortMode}>
        <div
          data-qid={qid}
          data-collapsed="false"
          style={{
            width: renderedWidth,
            flexShrink: 0,
            borderRight: `1px solid ${EMBRY.border}`,
            background: EMBRY.bgPanel,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            position: 'relative',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '12px 16px',
              borderBottom: title || collapsible ? `1px solid ${EMBRY.border}` : undefined,
              flexShrink: 0,
            }}
          >
            {title ? <div style={labelStyle}>{title}</div> : <div />}
            {collapsible ? (
              <button
                type="button"
                data-qid={`left-pane:${paneId}:collapse`}
                data-qs-action="LEFT_PANE_COLLAPSE"
                title={`Collapse ${title}`}
                onClick={() => setCollapsed(true)}
                aria-label={`Collapse ${title}`}
                style={{ background: 'none', border: 'none', color: EMBRY.dim, cursor: 'pointer', padding: 2 }}
              >
                <PanelLeftClose size={14} />
              </button>
            ) : null}
          </div>
          {searchable ? (
            <div style={{ padding: '8px 12px', borderBottom: `1px solid ${EMBRY.border}`, flexShrink: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px', background: EMBRY.bgDeep, borderRadius: 4, border: `1px solid ${EMBRY.border}` }}>
                <Search size={12} color={EMBRY.dim} />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  data-qid={searchTestId}
                  data-qs-action="LEFT_PANE_FILTER_SEARCH"
                  title={`Search ${title}`}
                  placeholder={searchPlaceholder}
                  aria-label={`Search ${title}`}
                  style={{ flex: 1, minHeight: 44, background: 'none', border: 'none', outline: 'none', color: EMBRY.white, fontSize: 11, fontFamily: MONO }}
                />
                {sortable ? (
                  <div style={{ display: 'flex', gap: 2, alignItems: 'center', flexShrink: 0 }}>
                    {SORT_ICONS.filter((sort) => modes.includes(sort.mode)).map((sort) => (
                      <button
                        key={sort.mode}
                        type="button"
                        data-qid={searchTestId ? `${searchTestId}:sort:${sort.mode}` : undefined}
                        data-qs-action={`LEFT_PANE_SORT_${sort.mode.toUpperCase()}`}
                        title={sort.title}
                        onClick={() => setSortMode(sort.mode)}
                        style={{ background: 'none', border: 'none', padding: 2, cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                      >
                        <sort.Icon size={14} color={sortMode === sort.mode ? EMBRY.accent : EMBRY.dim} />
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              {activeFilter ? (
                <button
                  type="button"
                  data-qid={`left-pane:${paneId}:clear-filter`}
                  data-qs-action="LEFT_PANE_CLEAR_FILTER"
                  title={`Clear filter ${activeFilter}`}
                  onClick={onClearFilter}
                  style={{
                    marginTop: 4,
                    background: 'rgba(255,60,60,0.1)',
                    border: `1px solid ${EMBRY.red}`,
                    color: EMBRY.red,
                    padding: '2px 8px',
                    borderRadius: 3,
                    fontSize: 9,
                    fontWeight: 700,
                    cursor: 'pointer',
                    fontFamily: MONO,
                  }}
                >
                  {activeFilter} x
                </button>
              ) : null}
            </div>
          ) : null}
          <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0', ...bodyStyle }}>{children}</div>
          {resizable ? (
            <div
              role="separator"
              aria-orientation="vertical"
              data-qid={resizeQid}
              data-qs-action={resizeAction}
              title={resizeTitle}
              onMouseDown={startResize}
              style={{
                position: 'absolute',
                top: 0,
                right: 0,
                bottom: 0,
                width: 8,
                cursor: 'col-resize',
                background: 'transparent',
              }}
            />
          ) : null}
        </div>
      </LeftPaneSortContext.Provider>
    </LeftPaneContext.Provider>
  )
}

const LeftPaneContext = createContext('')
export function useLeftPaneSearch(): string {
  return useContext(LeftPaneContext)
}

const LeftPaneSortContext = createContext<SortMode>('recent')
export function useLeftPaneSort(): SortMode {
  return useContext(LeftPaneSortContext)
}

export function paneItemStyle(selected: boolean): React.CSSProperties {
  return {
    padding: '8px 16px',
    cursor: 'pointer',
    fontSize: 11,
    fontFamily: MONO,
    color: selected ? EMBRY.accent : EMBRY.dim,
    background: selected ? 'rgba(124,58,237,0.08)' : 'transparent',
    borderLeft: selected ? `3px solid ${EMBRY.accent}` : '3px solid transparent',
    transition: 'all 0.15s',
  }
}

export function LeftPaneSection({ title, children, defaultOpen = true }: { title: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean }): JSX.Element {
  void defaultOpen
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ ...labelStyle, padding: '10px 16px 6px', flexShrink: 0, position: 'sticky', top: 0, background: EMBRY.bgPanel, zIndex: 1 }}>
        {title}
      </div>
      {children}
    </div>
  )
}

export function leftPaneGridTemplateColumns(collapsed: boolean, width: number | string = 300, collapsedWidth = 0): string {
  const openWidth = typeof width === 'number' ? `${width}px` : width
  return `${collapsed ? `${collapsedWidth}px` : openWidth} minmax(0, 1fr)`
}

export default LeftPane
