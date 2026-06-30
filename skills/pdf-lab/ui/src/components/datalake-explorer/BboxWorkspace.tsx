import { useState, useMemo, useCallback, useEffect } from 'react'
import { NVIS } from './theme'
import type {
  BboxBlock,
} from './types'
import BboxEditor from './BboxEditor'
import RequirementsBlock from './RequirementsBlock'
import PdfCanvas from './PdfCanvas'
import { useRegisterAction } from '../../hooks/useRegisterAction'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export type BlockType = BboxBlock['blockType']

export const BLOCK_TYPE_COLORS: Record<BlockType, string> = {
  table: '#1a99f2',
  header: '#f2731a',
  figure: '#1acc66',
  text: '#999999',
  equation: '#991af2',
  list_item: '#e61a66',
  caption: '#cc801a',
  page_number: '#66cccc',
  boilerplate: '#666666',
}

export const BLOCK_TYPE_LABELS: Record<BlockType, string> = {
  table: 'Table',
  header: 'Header',
  figure: 'Figure',
  text: 'Text',
  equation: 'Equation',
  list_item: 'ListItem',
  caption: 'Caption',
  page_number: 'PageNum',
  boilerplate: 'Boilerplate',
}

const ALL_BLOCK_TYPES: BlockType[] = ['table', 'header', 'figure', 'text', 'equation', 'list_item', 'caption', 'page_number', 'boilerplate']

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1) + '\u2026' : s
}

function confidenceColor(c: number): string {
  if (c >= 0.85) return '#15803d'
  if (c >= 0.60) return '#b45309'
  return '#dc2626'
}

function dispositionIcon(d: string): string {
  if (d === 'accept') return '\u2713'
  if (d === 'reject') return '\u2717'
  return '\u2191' // escalate arrow
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface BboxWorkspaceProps {
  blocks: BboxBlock[]
  sections?: unknown[]
  activeSectionId?: string
  pageCount: number
  currentPage: number
  onPageChange: (page: number) => void
  onBlockUpdate?: (block: BboxBlock) => void
  onBlockDelete?: (blockId: string) => void
  pdfUrl?: string
  entryId?: string
  docKey?: string
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BboxWorkspace({
  blocks,
  sections: _sections,
  activeSectionId,
  pageCount,
  currentPage,
  onPageChange,
  onBlockUpdate,
  onBlockDelete,
  pdfUrl = '/sample.pdf',
  entryId,
  docKey,
}: BboxWorkspaceProps) {
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [dirtyBlockIds, setDirtyBlockIds] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)
  const [typeFilters, setTypeFilters] = useState<Set<BlockType>>(new Set(ALL_BLOCK_TYPES))
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [zoom, setZoom] = useState(1.0)
  const [hoveredBlockIdx, setHoveredBlockIdx] = useState<number | null>(null)

  // Blocks on current page, filtered by type
  const visibleBlocks = useMemo(() => {
    return blocks.filter(
      (b) => b.page === currentPage && typeFilters.has(b.blockType)
    )
  }, [blocks, currentPage, typeFilters])

  // Type counts for filter buttons
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const b of blocks.filter((b) => b.page === currentPage)) {
      counts[b.blockType] = (counts[b.blockType] ?? 0) + 1
    }
    return counts
  }, [blocks, currentPage])

  const selectedBlock = blocks.find((b) => b.id === selectedBlockId) ?? null

  const toggleTypeFilter = useCallback((t: BlockType) => {
    setTypeFilters((prev) => {
      const next = new Set(prev)
      if (next.has(t)) next.delete(t)
      else next.add(t)
      return next
    })
  }, [])

  const handleReclassify = useCallback(
    (blockId: string, newType: BlockType) => {
      const block = blocks.find((b) => b.id === blockId)
      if (block && onBlockUpdate) {
        onBlockUpdate({ ...block, blockType: newType })
        setDirtyBlockIds(prev => new Set(prev).add(blockId))
      }
    },
    [blocks, onBlockUpdate]
  )

  const handleBboxChange = useCallback(
    (blockId: string, bbox: [number, number, number, number]) => {
      const block = blocks.find((b) => b.id === blockId)
      if (block && onBlockUpdate) {
        onBlockUpdate({ ...block, bbox })
        setDirtyBlockIds(prev => new Set(prev).add(blockId))
      }
    },
    [blocks, onBlockUpdate]
  )

  // Check if block is a requirements block (contains SHALL/MUST)
  const isRequirement = (text: string): boolean => {
    return /\b(SHALL|MUST)\b/.test(text)
  }

  // Track reclassify dropdown open state for `t` shortcut in non-edit mode
  const [inspectorTypeDropdown, setInspectorTypeDropdown] = useState(false)

  // S/D keyboard shortcuts: S = select mode (edit off), D = draw/edit mode (edit on)
  // Tab cycles bboxes, `t` opens reclassify dropdown
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
      if (e.key === 's' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        setEditMode(false)
      } else if (e.key === 'd' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault()
        setEditMode(true)
      } else if (e.key === 'Tab' && !e.ctrlKey && !e.metaKey) {
        // Tab cycles through bboxes without closing inspector (4.3)
        if (visibleBlocks.length > 0) {
          e.preventDefault()
          const currentIdx = selectedBlockId
            ? visibleBlocks.findIndex((b) => b.id === selectedBlockId)
            : -1
          const nextIdx = e.shiftKey
            ? (currentIdx <= 0 ? visibleBlocks.length - 1 : currentIdx - 1)
            : (currentIdx + 1) % visibleBlocks.length
          setSelectedBlockId(visibleBlocks[nextIdx].id)
        }
      } else if (e.key === 't' && !e.ctrlKey && !e.metaKey && !editMode && selectedBlockId) {
        // `t` opens reclassify dropdown in inspector (4.4)
        e.preventDefault()
        setInspectorTypeDropdown((p) => !p)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [visibleBlocks, selectedBlockId, editMode])

  async function handleSave() {
    if (!entryId || dirtyBlockIds.size === 0) return
    setSaving(true)
    const dirtyBlocks = blocks.filter(b => dirtyBlockIds.has(b.id))
    try {
      await fetch(`/api/quarantine/${entryId}/bbox-save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ blocks: dirtyBlocks, doc_key: docKey || '' }),
      })
      setDirtyBlockIds(new Set())
    } finally { setSaving(false) }
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); handleSave() } }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [dirtyBlockIds, entryId])

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      {/* ================================================================= */}
      {/* Explorer Panel (280px)                                             */}
      {/* ================================================================= */}
      <div
        style={{
          width: '280px',
          flexShrink: 0,
          backgroundColor: NVIS.surface,
          borderRight: `1px solid ${NVIS.borderSolid}`,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Section scope pill */}
        {activeSectionId && (
          <div
            style={{
              padding: '6px 10px',
              borderBottom: `1px solid ${NVIS.borderSolid}`,
              fontSize: '10px',
              color: NVIS.accent,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              backgroundColor: `${NVIS.accent}08`,
            }}
          >
            \u00A7 {activeSectionId}
          </div>
        )}

        {/* Block list header */}
        <div
          style={{
            padding: '8px 10px',
            borderBottom: `1px solid ${NVIS.borderSolid}`,
            fontSize: '10px',
            color: NVIS.dim,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}
        >
          Content Blocks ({visibleBlocks.length})
        </div>

        {/* Block list */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {visibleBlocks.map((block, bIdx) => {
            const isSelected = block.id === selectedBlockId
            const inSection = !activeSectionId || block.sectionId === activeSectionId
            const color = BLOCK_TYPE_COLORS[block.blockType]
            const isBlockHovered = hoveredBlockIdx === bIdx

            return (
              <div
                key={block.id}
                data-qid={`bbox:block:${block.id}`}
                title={`Block ${block.id}`}
                onClick={() => setSelectedBlockId(block.id)}
                onMouseEnter={() => setHoveredBlockIdx(bIdx)}
                onMouseLeave={() => setHoveredBlockIdx(null)}
                style={{
                  padding: '6px 10px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  opacity: inSection ? 1 : 0.35,
                  borderLeft: isSelected
                    ? '2px solid #7c3aed'
                    : '2px solid transparent',
                  backgroundColor: isSelected
                    ? 'rgba(124, 58, 237, 0.06)'
                    : isBlockHovered
                      ? 'rgba(124, 58, 237, 0.03)'
                      : 'transparent',
                  fontSize: '11px',
                }}
              >
                {/* Type dot */}
                <span
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: color,
                    flexShrink: 0,
                  }}
                />

                {/* Block ID */}
                <span
                  style={{
                    color: NVIS.dim,
                    fontSize: '9px',
                    fontVariantNumeric: 'tabular-nums',
                    flexShrink: 0,
                    minWidth: '36px',
                  }}
                >
                  {block.id}
                </span>

                {/* Text preview */}
                <span
                  style={{
                    flex: 1,
                    color: NVIS.white,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={block.text}
                >
                  {truncate(block.text, 60)}
                </span>

                {/* Confidence */}
                <span
                  style={{
                    fontSize: '10px',
                    fontVariantNumeric: 'tabular-nums',
                    fontWeight: 600,
                    color: confidenceColor(block.confidence),
                    flexShrink: 0,
                  }}
                >
                  {block.confidence.toFixed(2)}
                </span>
              </div>
            )
          })}
          {visibleBlocks.length === 0 && (
            <div
              style={{
                padding: '24px',
                color: NVIS.dim,
                fontSize: '12px',
                textAlign: 'center',
              }}
            >
              No blocks on this page.
            </div>
          )}
        </div>
      </div>

      {/* ================================================================= */}
      {/* Canvas Panel (flex-1)                                              */}
      {/* ================================================================= */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
        }}
      >
        {/* Toolbar */}
        <div
          style={{
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            borderBottom: `1px solid ${NVIS.borderSolid}`,
            backgroundColor: NVIS.surface,
            flexWrap: 'wrap',
          }}
        >
          {/* Edit mode toggle */}
          <button aria-label="Action" data-qid="bbox:el-1" data-qs-action="BBOX_EL_1" title="El 1"
            onClick={() => setEditMode((p) => !p)}
            style={{
              fontFamily: 'monospace',
              fontSize: '10px',
              padding: '3px 10px',
              borderRadius: '3px',
              border: editMode
                ? '1px solid #7c3aed'
                : `1px solid ${NVIS.borderSolid}`,
              backgroundColor: editMode ? 'rgba(124, 58, 237, 0.12)' : NVIS.surface2,
              color: editMode ? '#7c3aed' : NVIS.dim,
              cursor: 'pointer',
              fontWeight: editMode ? 700 : 400,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            {editMode ? 'EDIT MODE' : 'Edit'}
          </button>

          {/* Separator */}
          <div style={{ width: '1px', height: '18px', backgroundColor: NVIS.borderSolid }} />

          {/* Type filter buttons */}
          {ALL_BLOCK_TYPES.map((t) => {
            const active = typeFilters.has(t)
            const color = BLOCK_TYPE_COLORS[t]
            const count = typeCounts[t] ?? 0
            return (
              <button aria-label="Action"
                key={t}
                data-qid={`bbox:filter:${t}`}
                title={`Filter: ${BLOCK_TYPE_LABELS[t]}`}
                onClick={() => toggleTypeFilter(t)}
                style={{
                  fontFamily: 'monospace',
                  fontSize: '9px',
                  padding: '2px 6px',
                  borderRadius: '3px',
                  border: `1px solid ${active ? color : NVIS.borderSolid}`,
                  backgroundColor: active ? `${color}18` : NVIS.surface2,
                  color: active ? color : NVIS.dim,
                  cursor: 'pointer',
                  textTransform: 'uppercase',
                  letterSpacing: '0.03em',
                  opacity: count === 0 ? 0.4 : 1,
                }}
              >
                {BLOCK_TYPE_LABELS[t]}
                <span style={{ fontSize: '8px', marginLeft: '2px', opacity: 0.7 }}>
                  ({count})
                </span>
              </button>
            )
          })}

          {/* Separator */}
          <div style={{ width: '1px', height: '18px', backgroundColor: NVIS.borderSolid }} />

          {/* Zoom controls */}
          <button aria-label="Action" data-qid="bbox:el-2" data-qs-action="BBOX_EL_2" title="El 2"
            onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}
            style={{
              fontFamily: 'monospace',
              fontSize: '10px',
              padding: '2px 6px',
              borderRadius: '3px',
              border: `1px solid ${NVIS.borderSolid}`,
              backgroundColor: NVIS.surface2,
              color: NVIS.white,
              cursor: 'pointer',
            }}
          >
            -
          </button>
          <span
            style={{
              fontFamily: 'monospace',
              fontSize: '9px',
              color: NVIS.dim,
              minWidth: '36px',
              textAlign: 'center',
            }}
          >
            {Math.round(zoom * 100)}%
          </span>
          <button aria-label="Action" data-qid="bbox:el-3" data-qs-action="BBOX_EL_3" title="El 3"
            onClick={() => setZoom((z) => Math.min(4, z + 0.25))}
            style={{
              fontFamily: 'monospace',
              fontSize: '10px',
              padding: '2px 6px',
              borderRadius: '3px',
              border: `1px solid ${NVIS.borderSolid}`,
              backgroundColor: NVIS.surface2,
              color: NVIS.white,
              cursor: 'pointer',
            }}
          >
            +
          </button>

          {/* Save button */}
          {dirtyBlockIds.size > 0 && (
            <button aria-label="Action" data-qid="bbox:save" data-qs-action="BBOX_SAVE" title="Save block changes" onClick={handleSave} disabled={saving} style={{ fontFamily: 'monospace', fontSize: '11px', padding: '2px 8px', borderRadius: '3px', border: 'none', background: '#b45309', color: '#fff', cursor: saving ? 'wait' : 'pointer' }}>
              {saving ? 'Saving...' : `Save ${dirtyBlockIds.size} changes`}
            </button>
          )}

          {/* Spacer */}
          <div style={{ flex: 1 }} />

          {/* Page navigation */}
          <button aria-label="Action"
            data-qid="bbox:page:prev" data-qs-action="BBOX_PREV"
            title="Previous page"
            onClick={() => onPageChange(Math.max(0, currentPage - 1))}
            disabled={currentPage === 0}
            style={{
              fontFamily: 'monospace',
              fontSize: '10px',
              padding: '2px 8px',
              borderRadius: '3px',
              border: `1px solid ${NVIS.borderSolid}`,
              backgroundColor: NVIS.surface2,
              color: currentPage === 0 ? NVIS.dim : NVIS.white,
              cursor: currentPage === 0 ? 'not-allowed' : 'pointer',
              opacity: currentPage === 0 ? 0.4 : 1,
            }}
          >
            Prev
          </button>
          <span
            data-qid="bbox:page:number" data-qs-action="BBOX_NUMBER"
            title="Current page number"
            style={{
              fontSize: '10px',
              color: NVIS.dim,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {currentPage + 1} / {pageCount}
          </span>
          <button aria-label="Action"
            data-qid="bbox:page:next" data-qs-action="BBOX_NEXT"
            title="Next page"
            onClick={() => onPageChange(Math.min(pageCount - 1, currentPage + 1))}
            disabled={currentPage >= pageCount - 1}
            style={{
              fontFamily: 'monospace',
              fontSize: '10px',
              padding: '2px 8px',
              borderRadius: '3px',
              border: `1px solid ${NVIS.borderSolid}`,
              backgroundColor: NVIS.surface2,
              color: currentPage >= pageCount - 1 ? NVIS.dim : NVIS.white,
              cursor: currentPage >= pageCount - 1 ? 'not-allowed' : 'pointer',
              opacity: currentPage >= pageCount - 1 ? 0.4 : 1,
            }}
          >
            Next
          </button>
        </div>

        {/* Canvas area */}
        <div
          style={{
            flex: 1,
            backgroundColor: '#0f1216',
            position: 'relative',
            overflow: 'auto',
          }}
        >
          <PdfCanvas
            pdfUrl={pdfUrl}
            pageNumber={currentPage}
            bboxOverlays={visibleBlocks}
            selectedBlockId={selectedBlockId}
            onBlockClick={setSelectedBlockId}
            zoom={zoom}
            editMode={editMode}
          />
        </div>
      </div>

      {/* ================================================================= */}
      {/* Inspector Panel (300px)                                            */}
      {/* ================================================================= */}
      <div
        style={{
          width: '300px',
          flexShrink: 0,
          backgroundColor: NVIS.surface,
          borderLeft: `1px solid ${NVIS.borderSolid}`,
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
        }}
      >
        {selectedBlock ? (
          <>
            {/* Classification with inline reclassify (4.4) */}
            <InspectorSection title="Classification">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <span
                  style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    backgroundColor: BLOCK_TYPE_COLORS[selectedBlock.blockType],
                    flexShrink: 0,
                  }}
                />
                <span style={{ color: NVIS.white, fontWeight: 600, fontSize: '12px' }}>
                  {BLOCK_TYPE_LABELS[selectedBlock.blockType]}
                </span>
                <span
                  style={{
                    fontSize: '10px',
                    fontVariantNumeric: 'tabular-nums',
                    fontWeight: 600,
                    color: confidenceColor(selectedBlock.confidence),
                    marginLeft: 'auto',
                  }}
                >
                  {selectedBlock.confidence.toFixed(2)}
                </span>
              </div>
              {/* Inline reclassify dropdown (non-edit mode, triggered by `t`) */}
              {!editMode && (
                <div style={{ position: 'relative' }}>
                  <button aria-label="Action" data-qid="bbox:el-4" data-qs-action="BBOX_EL_4" title="El 4"
                    onClick={() => setInspectorTypeDropdown((p) => !p)}
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
                    Reclassify
                    <span style={{ marginLeft: 'auto', fontSize: '9px', color: NVIS.dim }}>t</span>
                  </button>
                  {inspectorTypeDropdown && (
                    <div
                      style={{
                        position: 'absolute',
                        top: '100%',
                        left: 0,
                        right: 0,
                        zIndex: 10,
                        marginTop: '2px',
                        backgroundColor: NVIS.surface2,
                        border: `1px solid ${NVIS.borderSolid}`,
                        borderRadius: '3px',
                        overflow: 'hidden',
                      }}
                    >
                      {ALL_BLOCK_TYPES.map((t, i) => {
                        const isActive = t === selectedBlock.blockType
                        return (
                          <button aria-label="Action" data-qid="bbox:t" data-qs-action="BBOX_T" title="T"
                            key={t}
                            onClick={() => {
                              handleReclassify(selectedBlock.id, t)
                              setInspectorTypeDropdown(false)
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
                            <span style={{ marginLeft: 'auto', fontSize: '9px', color: NVIS.dim }}>{i + 1}</span>
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>
              )}
            </InspectorSection>

            {/* BBox Coordinates */}
            <InspectorSection title="Bounding Box">
              {editMode ? (
                <BboxEditor
                  block={selectedBlock}
                  onReclassify={(newType) => handleReclassify(selectedBlock.id, newType)}
                  onBboxChange={(bbox) => handleBboxChange(selectedBlock.id, bbox)}
                  onDelete={() => onBlockDelete?.(selectedBlock.id)}
                />
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
                  {(['x1', 'y1', 'x2', 'y2'] as const).map((label, i) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ fontSize: '9px', color: NVIS.dim, width: '16px' }}>{label}</span>
                      <span
                        style={{
                          fontSize: '11px',
                          fontVariantNumeric: 'tabular-nums',
                          color: NVIS.white,
                          padding: '2px 6px',
                          backgroundColor: NVIS.surface2,
                          border: `1px solid ${NVIS.borderSolid}`,
                          borderRadius: '2px',
                          flex: 1,
                        }}
                      >
                        {selectedBlock.bbox[i].toFixed(4)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </InspectorSection>

            {/* Extraction Metadata + editable section dropdown (4.7) */}
            <InspectorSection title="Metadata">
              <MetaRow label="Block ID" value={selectedBlock.id} />
              <MetaRow label="Page" value={String(selectedBlock.page + 1)} />
              <MetaRow label="Type" value={selectedBlock.blockType} />
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: '11px',
                  padding: '1px 0',
                }}
              >
                <span style={{ color: NVIS.dim }}>Section</span>
                <select data-qid="bbox:el-6" data-qs-action="BBOX_EL_6" title="El 6"
                  value={selectedBlock.sectionId ?? ''}
                  onChange={(e) => {
                    if (onBlockUpdate) {
                      onBlockUpdate({ ...selectedBlock, sectionId: e.target.value || undefined })
                      setDirtyBlockIds(prev => new Set(prev).add(selectedBlock.id))
                    }
                  }}
                  style={{
                    fontFamily: 'monospace',
                    fontSize: '10px',
                    padding: '2px 4px',
                    borderRadius: '2px',
                    backgroundColor: NVIS.surface2,
                    border: `1px solid ${NVIS.borderSolid}`,
                    color: NVIS.white,
                    cursor: 'pointer',
                    maxWidth: '140px',
                  }}
                >
                  <option value="">None</option>
                  {((_sections ?? []) as { section_number?: string; title?: string }[]).map((s, i) => (
                    <option key={i} value={String(i)}>
                      {s.section_number ?? ''} {truncate(s.title ?? '', 20)}
                    </option>
                  ))}
                </select>
              </div>
            </InspectorSection>

            {/* Cascade Decision Trail */}
            <InspectorSection title="Cascade Trail">
              {(selectedBlock.cascadeTrail?.length ?? 0) > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {selectedBlock.cascadeTrail?.map((step, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '10px',
                        padding: '3px 6px',
                        borderRadius: '3px',
                        backgroundColor: NVIS.surface2,
                        border: `1px solid ${NVIS.borderSolid}`,
                      }}
                    >
                      <span
                        style={{
                          fontSize: '9px',
                          fontWeight: 700,
                          color: NVIS.accent,
                          minWidth: '24px',
                        }}
                      >
                        {step.tier}
                      </span>
                      <span style={{ color: NVIS.dim, flex: 1, fontSize: '9px' }}>
                        {step.tierName}
                      </span>
                      <span style={{ fontSize: '10px' }}>
                        {dispositionIcon(step.disposition)}
                      </span>
                      <span
                        style={{
                          textTransform: 'uppercase',
                          fontSize: '8px',
                          letterSpacing: '0.04em',
                          color:
                            step.disposition === 'accept'
                              ? '#15803d'
                              : step.disposition === 'reject'
                              ? '#dc2626'
                              : '#b45309',
                        }}
                      >
                        {step.disposition}
                      </span>
                      <span
                        style={{
                          fontVariantNumeric: 'tabular-nums',
                          fontWeight: 600,
                          color: confidenceColor(step.confidence),
                        }}
                      >
                        {step.confidence.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <span style={{ color: NVIS.dim, fontSize: '11px' }}>
                  No cascade data
                </span>
              )}
            </InspectorSection>

            {/* Text Preview */}
            <InspectorSection title="Text">
              <div
                data-qid="bbox:block-info" data-qs-action="BBOX_BLOCK_INFO" title="Block Info"
                style={{
                  fontSize: '11px',
                  color: NVIS.white,
                  lineHeight: '1.5',
                  maxHeight: '120px',
                  overflowY: 'auto',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {selectedBlock.text}
              </div>
            </InspectorSection>

            {/* Requirements Block (if applicable) */}
            {isRequirement(selectedBlock.text) && (
              <InspectorSection title="Requirements">
                <RequirementsBlock block={selectedBlock} />
              </InspectorSection>
            )}

            {/* Notes */}
            <InspectorSection title="Notes">
              <textarea
                value={notes[selectedBlock.id] ?? ''}
                onChange={(e) =>
                  setNotes((prev) => ({ ...prev, [selectedBlock.id]: e.target.value }))
                }
                placeholder="Add notes..."
                style={{
                  width: '100%',
                  minHeight: '60px',
                  fontSize: '11px',
                  fontFamily: 'monospace',
                  color: NVIS.white,
                  backgroundColor: NVIS.surface2,
                  border: `1px solid ${NVIS.borderSolid}`,
                  borderRadius: '3px',
                  padding: '6px 8px',
                  resize: 'vertical',
                }}
              />
            </InspectorSection>
          </>
        ) : (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: NVIS.dim,
              fontSize: '12px',
            }}
          >
            Select a block to inspect
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inspector sub-components
// ---------------------------------------------------------------------------

function InspectorSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div
      style={{
        padding: '10px 12px',
        borderBottom: `1px solid ${NVIS.borderSolid}`,
      }}
    >
      <div
        style={{
          fontSize: '9px',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: NVIS.dim,
          marginBottom: '6px',
        }}
      >
        {title}
      </div>
      {children}
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: string }) {

  // QuerySpec action registrations (data-qid → voice/NL/agent control)
  useRegisterAction('bbox:el-1', { app: 'datalake-explorer', action: 'EL_1', label: 'El 1', description: 'El 1 in truncate' })
  useRegisterAction('bbox:el-2', { app: 'datalake-explorer', action: 'EL_2', label: 'El 2', description: 'El 2 in truncate' })
  useRegisterAction('bbox:el-3', { app: 'datalake-explorer', action: 'EL_3', label: 'El 3', description: 'El 3 in truncate' })
  useRegisterAction('bbox:save', { app: 'datalake-explorer', action: 'SAVE', label: 'Save', description: 'Save in truncate' })
  useRegisterAction('bbox:page:prev', { app: 'datalake-explorer', action: 'PAGE_PREV', label: 'Page Prev', description: 'Page Prev in truncate' })
  useRegisterAction('bbox:page:number', { app: 'datalake-explorer', action: 'PAGE_NUMBER', label: 'Page Number', description: 'Page Number in truncate' })
  useRegisterAction('bbox:page:next', { app: 'datalake-explorer', action: 'PAGE_NEXT', label: 'Page Next', description: 'Page Next in truncate' })
  useRegisterAction('bbox:el-4', { app: 'datalake-explorer', action: 'EL_4', label: 'El 4', description: 'El 4 in truncate' })
  useRegisterAction('bbox:t', { app: 'datalake-explorer', action: 'T', label: 'T', description: 'T in truncate' })
  useRegisterAction('bbox:el-6', { app: 'datalake-explorer', action: 'EL_6', label: 'El 6', description: 'El 6 in truncate' })
  useRegisterAction('bbox:block-info', { app: 'datalake-explorer', action: 'BLOCK_INFO', label: 'Block Info', description: 'Block Info in truncate' })

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '11px',
        padding: '1px 0',
      }}
    >
      <span style={{ color: NVIS.dim }}>{label}</span>
      <span style={{ color: NVIS.white, fontVariantNumeric: 'tabular-nums' }}>{value}</span>
    </div>
  )
}
