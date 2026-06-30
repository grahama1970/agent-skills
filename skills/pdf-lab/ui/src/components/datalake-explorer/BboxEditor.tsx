import { useState, useEffect, useCallback } from 'react'
import { NVIS } from './theme'
import type { BboxBlock } from './types'
import { BLOCK_TYPE_COLORS, BLOCK_TYPE_LABELS } from './BboxWorkspace'
import type { BlockType } from './BboxWorkspace'
import { useRegisterAction } from '../../hooks/useRegisterAction'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALL_BLOCK_TYPES: BlockType[] = [
  'table', 'header', 'figure', 'text', 'equation', 'list_item', 'caption',
]

const TYPE_SHORTCUTS: Record<string, BlockType> = {
  '1': 'table',
  '2': 'header',
  '3': 'figure',
  '4': 'text',
  '5': 'equation',
  '6': 'list_item',
  '7': 'caption',
}

/** Write shadow label to cascade log on reclassify (4b.6) */
function logShadowReclassify(block: BboxBlock, newType: BlockType): void {
  const entry = {
    ts: new Date().toISOString(),
    block_id: block.id,
    page: block.page,
    old_type: block.blockType,
    new_type: newType,
    confidence: block.confidence,
    bbox: block.bbox,
    source: 'human-reclassify',
  }
  // Append to cascade shadow log (localStorage-backed for offline)
  try {
    const key = 'cascade_shadow_labels'
    const existing = JSON.parse(localStorage.getItem(key) ?? '[]')
    existing.push(entry)
    localStorage.setItem(key, JSON.stringify(existing))
  } catch { /* quota exceeded — silent */ }
  console.log('[shadow] reclassify:', entry)
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BboxEditorProps {
  block: BboxBlock
  onReclassify: (newType: BlockType) => void
  onBboxChange: (bbox: [number, number, number, number]) => void
  onDelete: () => void
  onSplit?: () => void
  onMerge?: () => void
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BboxEditor({
  block,
  onReclassify,
  onBboxChange,
  onDelete,
  onSplit,
  onMerge,
}: BboxEditorProps) {
  // QuerySpec action registrations
  useRegisterAction('bbox-editor:item-1', { app: 'datalake-explorer', action: 'ITEM_1', label: 'Item 1', description: 'Item 1 in logShadowReclassify' })
  useRegisterAction('bbox:type:select', { app: 'datalake-explorer', action: 'TYPE_SELECT', label: 'Type Select', description: 'Type Select in logShadowReclassify' })
  useRegisterAction('bbox-editor:dyn-2', { app: 'datalake-explorer', action: 'DYN_2', label: 'Dyn 2', description: 'Dyn 2 in logShadowReclassify' })
  useRegisterAction('bbox-editor:type-dropdown-list', { app: 'datalake-explorer', action: 'TYPE_DROPDOWN_LIST', label: 'Type Dropdown List', description: 'Type Dropdown List in logShadowReclassify' })
  const [localBbox, setLocalBbox] = useState<[number, number, number, number]>(block.bbox)
  const [showTypeDropdown, setShowTypeDropdown] = useState(false)
  const [undoStack, setUndoStack] = useState<[number, number, number, number][]>([])

  // Reset local bbox when block changes
  useEffect(() => {
    setLocalBbox(block.bbox)
    setUndoStack([])
  }, [block.id, block.bbox])

  // Keyboard shortcuts
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return

      // Type shortcuts 1-7 — reclassify writes shadow label (4b.6)
      const typeKey = TYPE_SHORTCUTS[e.key]
      if (typeKey) {
        e.preventDefault()
        logShadowReclassify(block, typeKey)
        onReclassify(typeKey)
        setShowTypeDropdown(false)
        return
      }

      // t = toggle reclassify dropdown (4.4)
      if (e.key === 't' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        setShowTypeDropdown((p) => !p)
        return
      }

      // Ctrl+Z = undo
      if (e.key === 'z' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        if (undoStack.length > 0) {
          const prev = undoStack[undoStack.length - 1]
          setUndoStack((s) => s.slice(0, -1))
          setLocalBbox(prev)
          onBboxChange(prev)
        }
        return
      }

      // Enter = apply (4b.5)
      if (e.key === 'Enter') {
        e.preventDefault()
        onBboxChange(localBbox)
        return
      }

      // s = split (4b.5)
      if (e.key === 's' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        if (onSplit) onSplit()
        return
      }

      // m = merge (4b.5)
      if (e.key === 'm' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        if (onMerge) onMerge()
        return
      }

      // Delete/Backspace = delete block
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault()
        onDelete()
        return
      }

      // Arrow keys = nudge
      const nudge = 0.005
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        pushUndo()
        const next: [number, number, number, number] = [
          Math.max(0, localBbox[0] - nudge),
          localBbox[1],
          Math.max(0, localBbox[2] - nudge),
          localBbox[3],
        ]
        setLocalBbox(next)
        onBboxChange(next)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        pushUndo()
        const next: [number, number, number, number] = [
          Math.min(1, localBbox[0] + nudge),
          localBbox[1],
          Math.min(1, localBbox[2] + nudge),
          localBbox[3],
        ]
        setLocalBbox(next)
        onBboxChange(next)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        pushUndo()
        const next: [number, number, number, number] = [
          localBbox[0],
          Math.max(0, localBbox[1] - nudge),
          localBbox[2],
          Math.max(0, localBbox[3] - nudge),
        ]
        setLocalBbox(next)
        onBboxChange(next)
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        pushUndo()
        const next: [number, number, number, number] = [
          localBbox[0],
          Math.min(1, localBbox[1] + nudge),
          localBbox[2],
          Math.min(1, localBbox[3] + nudge),
        ]
        setLocalBbox(next)
        onBboxChange(next)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [localBbox, undoStack, onReclassify, onBboxChange, onDelete])

  function pushUndo() {
    setUndoStack((prev) => [...prev.slice(-19), localBbox])
  }

  const handleCoordChange = useCallback(
    (idx: number, value: string) => {
      const num = parseFloat(value)
      if (isNaN(num)) return
      const clamped = Math.max(0, Math.min(1, num))
      pushUndo()
      const next = [...localBbox] as [number, number, number, number]
      next[idx] = clamped
      setLocalBbox(next)
    },
    [localBbox]
  )

  const handleApply = useCallback(() => {
    onBboxChange(localBbox)
  }, [localBbox, onBboxChange])

  const width = Math.abs(localBbox[2] - localBbox[0])
  const height = Math.abs(localBbox[3] - localBbox[1])

  return (
    <div>
      {/* Coordinate inputs */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', marginBottom: '8px' }}>
        {(['x1', 'y1', 'x2', 'y2'] as const).map((label, i) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ fontSize: '9px', color: NVIS.dim, width: '16px' }}>{label}</span>
            <input
              type="number"
              step="0.001"
              min="0"
              max="1"
              value={localBbox[i].toFixed(4)}
                data-qid="bbox-editor:item-1" data-qs-action="BBOX-EDITOR_ITEM_1"
                title="Item 1"
              onChange={(e) => handleCoordChange(i, e.target.value)}
              style={{
                flex: 1,
                fontSize: '11px',
                fontFamily: 'monospace',
                fontVariantNumeric: 'tabular-nums',
                color: NVIS.white,
                padding: '3px 6px',
                backgroundColor: NVIS.surface2,
                border: `1px solid ${NVIS.borderSolid}`,
                borderRadius: '2px',
                width: '100%',
              }}
            />
          </div>
        ))}
      </div>

      {/* Size readout */}
      <div
        style={{
          fontSize: '9px',
          color: NVIS.dim,
          marginBottom: '8px',
          textAlign: 'center',
        }}
      >
        {(width * 100).toFixed(1)}% x {(height * 100).toFixed(1)}%
      </div>

      {/* Reclassify dropdown */}
      <div style={{ marginBottom: '8px' }}>
        <button aria-label="Action"
          data-qid="bbox:type:select" data-qs-action="BBOX_SELECT"
          title="Reclassify block type"
          onClick={() => setShowTypeDropdown((p) => !p)}
          style={{
            width: '100%',
            fontFamily: 'monospace',
            fontSize: '10px',
            padding: '4px 8px',
            borderRadius: '3px',
            border: `1px solid ${NVIS.borderSolid}`,
            backgroundColor: NVIS.surface2,
            color: NVIS.white,
            cursor: 'pointer',
            textAlign: 'left',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: BLOCK_TYPE_COLORS[block.blockType],
              flexShrink: 0,
            }}
          />
          Reclassify: {BLOCK_TYPE_LABELS[block.blockType]}
          <span style={{ marginLeft: 'auto', fontSize: '9px', color: NVIS.dim }}>
            t
          </span>
        </button>
        {showTypeDropdown && (
          <div
            style={{
              marginTop: '2px',
              backgroundColor: NVIS.surface2,
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: '3px',
              overflow: 'hidden',
            }}
          >
            {ALL_BLOCK_TYPES.map((t, i) => {
              const isActive = t === block.blockType
              return (
                <button aria-label="Action"
                  key={t}
                data-qid="bbox-editor:dyn-2" data-qs-action="BBOX-EDITOR_DYN_2"
                title="Dyn 2"
                  onClick={() => {
                    logShadowReclassify(block, t)
                    onReclassify(t)
                    setShowTypeDropdown(false)
                  }}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '4px 8px',
                    border: 'none',
                    backgroundColor: isActive ? `${BLOCK_TYPE_COLORS[t]}18` : 'transparent',
                    color: NVIS.white,
                    cursor: 'pointer',
                    fontFamily: 'monospace',
                    fontSize: '10px',
                    textAlign: 'left',
                  }}
                >
                  <span
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: BLOCK_TYPE_COLORS[t],
                      flexShrink: 0,
                    }}
                  />
                  <span>{BLOCK_TYPE_LABELS[t]}</span>
                  <span style={{ marginLeft: 'auto', fontSize: '9px', color: NVIS.dim }}>
                    {i + 1}
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div data-qid="bbox-editor:type-dropdown-list" data-qs-action="BBOX-EDITOR_TYPE_DROPDOWN_LIST" title="Type Dropdown List" style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
        <EditorButton label="Apply" color="#15803d" onClick={handleApply} />
        <EditorButton
          label="Split"
          color={NVIS.accent}
          onClick={onSplit ?? (() => console.log('Split:', block.id))}
        />
        <EditorButton
          label="Merge"
          color={NVIS.accent}
          onClick={onMerge ?? (() => console.log('Merge:', block.id))}
        />
        <EditorButton label="Delete" color="#dc2626" onClick={onDelete} qid="bbox:delete" title="Delete block" />
      </div>

      {/* Keyboard shortcut bar */}
      <div
        style={{
          marginTop: '8px',
          padding: '4px 6px',
          backgroundColor: NVIS.surface2,
          borderRadius: '3px',
          border: `1px solid ${NVIS.borderSolid}`,
          fontSize: '8px',
          color: NVIS.dim,
          display: 'flex',
          gap: '6px',
          flexWrap: 'wrap',
          letterSpacing: '0.03em',
        }}
      >
        <span>Enter apply</span>
        <span>S split</span>
        <span>M merge</span>
        <span>1-7 labels</span>
        <span>Ctrl+Z undo</span>
        <span>Del delete</span>
        <span>\u2190\u2191\u2192\u2193 nudge</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-component
// ---------------------------------------------------------------------------

function EditorButton({
  label,
  color,
  onClick,
  qid,
  title: titleProp,
}: {
  label: string
  color: string
  onClick: () => void
  qid?: string
  title?: string
}) {
  return (
    <button aria-label="Action"
      data-qid={qid}
      title={titleProp}
      onClick={onClick}
      style={{
        fontFamily: 'monospace',
        fontSize: '9px',
        padding: '3px 8px',
        borderRadius: '3px',
        border: `1px solid ${color}40`,
        backgroundColor: `${color}14`,
        color,
        cursor: 'pointer',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
      }}
    >
      {label}
    </button>
  )
}
