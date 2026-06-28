/**
 * LeftPane — Collapsible side explorer panel with fuzzy search.
 * Used by Library, Results, and PromptLab.
 */
import { useState, useEffect, useCallback, useRef, createContext, useContext } from 'react'
import { PanelLeftClose, PanelLeftOpen, Search, Clock, ArrowDownWideNarrow, ArrowDownAZ } from 'lucide-react'
import { EMBRY, label } from './EmbryStyle'
import { useRegisterAction } from '../../hooks/useRegisterAction'

/* ── Context Menu ──────────────────────────────────────────── */

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
  fontFamily: '"JetBrains Mono", "SF Mono", monospace',
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

export function ContextMenu({ x, y, visible, onAction, onClose }: ContextMenuProps) {
  useRegisterAction('left-pane:context:rename', {
    app: 'ux-lab',
    action: 'LEFT_PANE_CONTEXT_RENAME',
    label: 'Context menu rename',
    description: 'Rename item from left pane context menu',
  })
  useRegisterAction('left-pane:context:copy', {
    app: 'ux-lab',
    action: 'LEFT_PANE_CONTEXT_COPY',
    label: 'Context menu copy',
    description: 'Copy item from left pane context menu',
  })
  useRegisterAction('left-pane:context:delete', {
    app: 'ux-lab',
    action: 'LEFT_PANE_CONTEXT_DELETE',
    label: 'Context menu delete',
    description: 'Delete item from left pane context menu',
  })
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!visible) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [visible, onClose])

  if (!visible) return null

  return (
    <div ref={ref} style={{
      position: 'fixed', left: x, top: y, zIndex: 9999,
      background: EMBRY.bgCard, border: `1px solid ${EMBRY.border}`,
      borderRadius: 6, padding: '4px 0', minWidth: 120,
      boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
    }}>
      {MENU_ITEMS.map(({ action, label: text, color }) => {
        const qs = action === 'rename' ? 'LEFT_PANE_CONTEXT_RENAME' : action === 'copy' ? 'LEFT_PANE_CONTEXT_COPY' : 'LEFT_PANE_CONTEXT_DELETE'
        return (
        <button
          key={action}
          type="button"
          data-qid={`left-pane:context:${action}`}
          data-qs-action={qs}
          title={text}
          style={{ ...menuItemBase, color: color ?? EMBRY.white }}
          onMouseEnter={e => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          onClick={() => { onAction(action); onClose() }}
        >
          {text}
        </button>
        )
      })}
    </div>
  )
}

/** Hook for consumers to wire up context menu on pane items. */
export function useContextMenu(onContextMenu?: (itemId: string, action: ContextMenuAction) => void) {
  const [menu, setMenu] = useState<{ x: number; y: number; itemId: string } | null>(null)

  const triggerContextMenu = useCallback((e: React.MouseEvent, itemId: string) => {
    e.preventDefault()
    setMenu({ x: e.clientX, y: e.clientY, itemId })
  }, [])

  const close = useCallback(() => setMenu(null), [])

  const menuProps: ContextMenuProps | null = menu ? {
    x: menu.x, y: menu.y, visible: true,
    onAction: (action: ContextMenuAction) => onContextMenu?.(menu.itemId, action),
    onClose: close,
  } : null

  return { menuProps, triggerContextMenu }
}

export type SortMode = 'recent' | 'score' | 'alpha'
const MONO = '"JetBrains Mono", "SF Mono", monospace'
const SORT_ICONS: { mode: SortMode; Icon: typeof Clock; title: string }[] = [
  { mode: 'recent', Icon: Clock, title: 'Sort by recent' },
  { mode: 'score', Icon: ArrowDownWideNarrow, title: 'Sort by score' },
  { mode: 'alpha', Icon: ArrowDownAZ, title: 'Sort A-Z' },
]

export function LeftPane({ title, children, width = 260, searchable = false, sortable = false, sortModes, activeFilter, onClearFilter, searchTestId, search: externalSearch, onSearchChange, searchPlaceholder, defaultCollapsed = false, collapsible = true }: {
  title: string
  children: React.ReactNode
  width?: number
  defaultCollapsed?: boolean
  searchable?: boolean
  /** data-qid for the search input */
  searchTestId?: string
  /** Show sort chips below the filter input */
  sortable?: boolean
  /** Custom sort modes (default: recent, score, alpha) */
  sortModes?: SortMode[]
  /** Active filter label shown as a removable chip */
  activeFilter?: string
  /** Called when the filter chip × is clicked */
  onClearFilter?: () => void
  /** Controlled search value (if external) */
  search?: string
  /** Called when search changes (controlled mode) */
  onSearchChange?: React.Dispatch<React.SetStateAction<string>>
  /** Placeholder text for search input */
  searchPlaceholder?: string
  /** Show built-in collapse control (transport room disables — shell has its own) */
  collapsible?: boolean
}) {
  const paneId = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'pane'

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

  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  const [internalSearch, setInternalSearch] = useState('')
  const search = externalSearch ?? internalSearch
  const setSearch = onSearchChange ?? setInternalSearch
  const [sortMode, setSortMode] = useState<SortMode>('recent')
  useRegisterAction('left-pane:expand', {
    app: 'ux-lab',
    action: 'LEFT_PANE_EXPAND',
    label: 'Expand left pane',
    description: 'Expand a collapsed left pane',
  })
  useRegisterAction('left-pane:collapse', {
    app: 'ux-lab',
    action: 'LEFT_PANE_COLLAPSE',
    label: 'Collapse left pane',
    description: 'Collapse a left pane sidebar',
  })
  useRegisterAction('left-pane:clear-filter', {
    app: 'ux-lab',
    action: 'LEFT_PANE_CLEAR_FILTER',
    label: 'Clear left pane filter',
    description: 'Clear active filter chip on left pane',
  })
  useRegisterAction('left-pane:sort-recent', {
    app: 'ux-lab',
    action: 'LEFT_PANE_SORT_RECENT',
    label: 'Sort left pane by recent',
    description: 'Sort left pane items by most recent',
  })
  useRegisterAction('left-pane:sort-score', {
    app: 'ux-lab',
    action: 'LEFT_PANE_SORT_SCORE',
    label: 'Sort left pane by score',
    description: 'Sort left pane items by score',
  })
  useRegisterAction('left-pane:filter-search', {
    app: 'ux-lab',
    action: 'LEFT_PANE_FILTER_SEARCH',
    label: 'Filter left pane list',
    description: 'Filter items in a searchable left pane',
  })

  useRegisterAction('left-pane:sort-alpha', {
    app: 'ux-lab',
    action: 'LEFT_PANE_SORT_ALPHA',
    label: 'Sort left pane A-Z',
    description: 'Sort left pane items alphabetically',
  })

  const modes = sortModes ?? ['recent', 'score', 'alpha']

  if (collapsed) {
    return (
      <div style={{
        width: 32, flexShrink: 0, borderRight: `1px solid ${EMBRY.border}`,
        background: EMBRY.bgPanel, display: 'flex', alignItems: 'flex-start',
        justifyContent: 'center', paddingTop: 12,
      }}>
        <button
          type="button"
          data-qid={`left-pane:${paneId}:expand`}
          data-qs-action="LEFT_PANE_EXPAND"
          title={`Expand ${title}`}
          onClick={() => setCollapsed(false)}
          aria-label={`Expand ${title}`}
          style={{ background: 'none', border: 'none', color: EMBRY.dim, cursor: 'pointer', padding: 2 }}>
          <PanelLeftOpen size={14} />
        </button>
      </div>
    )
  }

  return (
    <LeftPaneContext.Provider value={search}>
      <LeftPaneSortContext.Provider value={sortMode}>
        <div style={{
          width, flexShrink: 0, borderRight: `1px solid ${EMBRY.border}`,
          background: EMBRY.bgPanel, display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '12px 16px', borderBottom: (title || collapsible) ? `1px solid ${EMBRY.border}` : undefined, flexShrink: 0,
          }}>
            {title ? <div style={label}>{title}</div> : <div />}
            {collapsible ? (
              <button
                type="button"
                data-qid={`left-pane:${paneId}:collapse`}
                data-qs-action="LEFT_PANE_COLLAPSE"
                title={`Collapse ${title}`}
                onClick={() => setCollapsed(true)}
                aria-label={`Collapse ${title}`}
                style={{ background: 'none', border: 'none', color: EMBRY.dim, cursor: 'pointer', padding: 2 }}>
                <PanelLeftClose size={14} />
              </button>
            ) : null}
          </div>
          {searchable && (
            <div style={{ padding: '8px 12px', borderBottom: `1px solid ${EMBRY.border}`, flexShrink: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px', background: EMBRY.bgDeep, borderRadius: 4, border: `1px solid ${EMBRY.border}` }}>
                <Search size={12} color={EMBRY.dim} />
                <input value={search} onChange={e => setSearch(e.target.value)}
                  data-qid={searchTestId}
                  data-qs-action="LEFT_PANE_FILTER_SEARCH"
                  title={`Search ${title}`}
                  placeholder="Filter..." aria-label={`Search ${title}`}
                  style={{ flex: 1, minHeight: 44, background: 'none', border: 'none', outline: 'none', color: EMBRY.white, fontSize: 11, fontFamily: MONO }} />
                {sortable && (
                  <div style={{ display: 'flex', gap: 2, alignItems: 'center', flexShrink: 0 }}>
                    {SORT_ICONS.filter(s => modes.includes(s.mode)).map(s => (
                      <button
                        key={s.mode}
                        type="button"
                        data-qid={searchTestId ? `${searchTestId}:sort:${s.mode}` : undefined}
                        data-qs-action={`LEFT_PANE_SORT_${s.mode.toUpperCase()}`}
                        title={s.title}
                        onClick={() => setSortMode(s.mode)}
                        style={{ background: 'none', border: 'none', padding: 2, cursor: 'pointer', display: 'flex', alignItems: 'center' }}
                      >
                        <s.Icon size={14} color={sortMode === s.mode ? EMBRY.accent : EMBRY.dim} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {activeFilter && (
                <button
                  type="button"
                  data-qid={`left-pane:${paneId}:clear-filter`}
                  data-qs-action="LEFT_PANE_CLEAR_FILTER"
                  title={`Clear filter ${activeFilter}`}
                  onClick={onClearFilter}
                  style={{
                  marginTop: 4, background: 'rgba(255,60,60,0.1)', border: `1px solid ${EMBRY.red}`,
                  color: EMBRY.red, padding: '2px 8px', borderRadius: 3, fontSize: 9, fontWeight: 700, cursor: 'pointer',
                  fontFamily: MONO,
                }}>{activeFilter} ✕</button>
              )}
            </div>
          )}
          <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
            {children}
          </div>
        </div>
      </LeftPaneSortContext.Provider>
    </LeftPaneContext.Provider>
  )
}

/** Context so children can read the search term */
const LeftPaneContext = createContext('')
export function useLeftPaneSearch() { return useContext(LeftPaneContext) }

/** Context so children can read the current sort mode */
const LeftPaneSortContext = createContext<SortMode>('recent')
export function useLeftPaneSort() { return useContext(LeftPaneSortContext) }

/** Style for a selectable item inside LeftPane */
export function paneItemStyle(selected: boolean): React.CSSProperties {
  return {
    padding: '8px 16px', cursor: 'pointer', fontSize: 11,
    fontFamily: '"JetBrains Mono", "SF Mono", monospace',
    color: selected ? EMBRY.accent : EMBRY.dim,
    background: selected ? 'rgba(124,58,237,0.08)' : 'transparent',
    borderLeft: selected ? `3px solid ${EMBRY.accent}` : '3px solid transparent',
    transition: 'all 0.15s',
  }
}

/**
 * LeftPaneSection — A pinned section header inside LeftPane.
 * Content below scrolls independently.
 */
export function LeftPaneSection({ title, children, defaultOpen = true }: { title: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean }) {
  // defaultOpen is accepted for API compatibility but currently ignored (always shown)
  void defaultOpen
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ ...label, padding: '10px 16px 6px', flexShrink: 0, position: 'sticky', top: 0, background: EMBRY.bgPanel, zIndex: 1 }}>
        {title}
      </div>
      {children}
    </div>
  )
}
