/**
 * ContextMenu — Shared right-click context menu for LeftPane items and graph nodes.
 * Used by Binary Explorer (binaries, graph nodes), Testing (manifests), Prompt Lab (prompts).
 *
 * Supports: keyboard shortcuts, section separators, section headers, disabled items.
 *
 * Binary analysis presets: buildBinaryNodeMenuItems() returns IDA/Ghidra-style node items.
 */
/* eslint-disable react-refresh/only-export-components */
import { useEffect, useRef } from 'react'
import { EMBRY } from './EmbryStyle'

// ── Binary node context menu ──────────────────────────────────────────────────

export interface BinaryNodeInfo {
  address: string
  name?: string
  hasXrefs?: boolean
  canExpand?: boolean
  canCollapse?: boolean
}

export interface BinaryNodeActions {
  onRename?: () => void
  onAnnotate?: () => void
  onShowXrefs?: () => void
  onCopyAddress?: () => void
  onExpandNeighbors?: () => void
  onCollapseNode?: () => void
  onSetBreakpoint?: () => void
  onFollowCall?: () => void
}

/**
 * Returns IDA/Ghidra-style context menu items for a binary graph node.
 * Pass the result as `items` to <ContextMenu />.
 */
export function buildBinaryNodeMenuItems(
  node: BinaryNodeInfo,
  actions: BinaryNodeActions,
): ContextMenuItem[] {
  const items: ContextMenuItem[] = [
    // Navigation section
    { label: 'Navigation', header: true, onClick: () => {} },
    {
      label: 'Follow Call / Jump',
      shortcut: 'Enter',
      disabled: !actions.onFollowCall,
      onClick: actions.onFollowCall ?? (() => {}),
    },
    {
      label: 'Show Cross-References',
      shortcut: 'X',
      disabled: !actions.onShowXrefs && !node.hasXrefs,
      onClick: actions.onShowXrefs ?? (() => {}),
    },
    { separator: true, onClick: () => {} },

    // Graph section
    { label: 'Graph', header: true, onClick: () => {} },
    {
      label: 'Expand Neighbors',
      shortcut: 'E',
      disabled: !actions.onExpandNeighbors || node.canExpand === false,
      onClick: actions.onExpandNeighbors ?? (() => {}),
    },
    {
      label: 'Collapse Node',
      shortcut: 'Backspace',
      disabled: !actions.onCollapseNode || node.canCollapse === false,
      onClick: actions.onCollapseNode ?? (() => {}),
    },
    { separator: true, onClick: () => {} },

    // Annotation section
    { label: 'Annotation', header: true, onClick: () => {} },
    {
      label: 'Rename…',
      shortcut: 'N',
      disabled: !actions.onRename,
      onClick: actions.onRename ?? (() => {}),
    },
    {
      label: 'Add Comment / Annotation…',
      shortcut: ';',
      disabled: !actions.onAnnotate,
      onClick: actions.onAnnotate ?? (() => {}),
    },
    { separator: true, onClick: () => {} },

    // Clipboard section
    { label: 'Clipboard', header: true, onClick: () => {} },
    {
      label: `Copy Address  (${node.address})`,
      shortcut: 'Ctrl+C',
      disabled: !actions.onCopyAddress,
      onClick: actions.onCopyAddress ?? (() => {}),
    },
    { separator: true, onClick: () => {} },

    // Debug section
    {
      label: 'Toggle Breakpoint',
      shortcut: 'F2',
      disabled: !actions.onSetBreakpoint,
      onClick: actions.onSetBreakpoint ?? (() => {}),
    },
  ]
  return items
}

export interface ContextMenuItem {
  label?: string
  icon?: React.ReactNode
  /** Keyboard shortcut label shown right-aligned (e.g. "N", "Ctrl+C", ";") */
  shortcut?: string
  /** Render as a horizontal divider (label/icon/onClick ignored) */
  separator?: boolean
  /** Render as a non-interactive section header */
  header?: boolean
  danger?: boolean
  disabled?: boolean
  onClick?: () => void
  /** Test automation identifier */
  'data-qid'?: string
  /** QuerySpec action identifier */
  'data-qs-action'?: string
}

interface ContextMenuProps {
  x: number
  y: number
  items: ContextMenuItem[]
  /** Optional title shown at the top of the menu */
  title?: string
  onClose: () => void
}

export function ContextMenu({ x, y, items, title, onClose }: ContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const escHandler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', handler)
    document.addEventListener('keydown', escHandler)
    return () => {
      document.removeEventListener('mousedown', handler)
      document.removeEventListener('keydown', escHandler)
    }
  }, [onClose])

  // Adjust position to stay in viewport
  const menuWidth = 220
  const itemCount = items.filter(i => !i.separator && !i.header).length
  const sepCount = items.filter(i => i.separator).length
  const headerCount = items.filter(i => i.header).length
  const titleHeight = title ? 28 : 0
  const menuHeight = titleHeight + itemCount * 28 + sepCount * 9 + headerCount * 22 + 8
  const adjustedX = x + menuWidth > window.innerWidth ? x - menuWidth : x
  const adjustedY = y + menuHeight > window.innerHeight ? y - menuHeight : y

  return (
    <div
      ref={ref}
      onContextMenu={e => e.preventDefault()}
      style={{
        position: 'fixed', left: adjustedX, top: adjustedY, zIndex: 99999,
        background: '#0a0a0a', border: `1px solid ${EMBRY.border}`,
        borderRadius: 4, padding: '4px 0', minWidth: menuWidth,
        boxShadow: '0 8px 32px rgba(0,0,0,0.8)',
        userSelect: 'none',
      }}
    >
      {title && (
        <div style={{
          padding: '5px 12px', fontSize: 9, fontWeight: 700,
          color: EMBRY.dim, borderBottom: `1px solid ${EMBRY.border}`,
          marginBottom: 4, letterSpacing: '0.08em',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {title.toUpperCase()}
        </div>
      )}
      {items.map((item, i) => {
        if (item.separator) {
          return <div key={i} style={{ height: 1, background: EMBRY.border, margin: '4px 0' }} />
        }
        if (item.header) {
          return (
            <div key={i} style={{
              padding: '4px 12px', fontSize: 8, fontWeight: 700,
              color: EMBRY.dim, textTransform: 'uppercase', letterSpacing: '0.1em',
              marginTop: 2,
            }}>
              {item.label}
            </div>
          )
        }
        return (
          <div
            key={i}
            data-qid={item['data-qid']}
            data-qs-action={item['data-qs-action']}
            title={item.label}
            onClick={() => {
              if (item.disabled) return
              item.onClick?.()
              onClose()
            }}
            style={{
              padding: '5px 12px', fontSize: 11, cursor: item.disabled ? 'default' : 'pointer',
              color: item.disabled ? EMBRY.dim : item.danger ? '#ff4444' : EMBRY.white,
              display: 'flex', alignItems: 'center', gap: 8,
              transition: 'background 0.1s',
              opacity: item.disabled ? 0.45 : 1,
            }}
            onMouseEnter={e => { if (!item.disabled) e.currentTarget.style.background = '#1a1a1a' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
          >
            <span style={{ width: 14, display: 'flex', alignItems: 'center', flexShrink: 0 }}>
              {item.icon}
            </span>
            <span style={{ flex: 1 }}>{item.label}</span>
            {item.shortcut && (
              <span style={{
                fontSize: 9, color: EMBRY.dim, fontFamily: 'monospace',
                background: '#1a1a1a', borderRadius: 2,
                padding: '1px 5px', border: `1px solid ${EMBRY.border}`,
                letterSpacing: '0.05em', flexShrink: 0,
              }}>
                {item.shortcut}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
