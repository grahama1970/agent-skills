import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { NVIS } from '../theme.ts'
import { loadQuarantine } from '../loader.ts'
import { recallDocuments } from '../api/client.ts'
import type {
  QuarantineEntry,
  QuarantineDetail,
  QuarantineBlock,
  Section,
  Table,
  BboxBlock,
  ReextractResult,
} from '../types.ts'
import BboxWorkspace from '../components/BboxWorkspace.tsx'
import SpotReextract from '../components/SpotReextract.tsx'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_BASE =
  (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8004'

type ReasonFilter = 'all' | 'low-confidence' | 'extraction-error' | 'novel-layout' | 'timeout'
type SortMode = 'newest' | 'oldest' | 'worst-score'
type ActionType = 'approve' | 'reject' | 're-extract' | 'interview'
const REASON_COLORS: Record<QuarantineEntry['reason'], { border: string; text: string }> = {
  'low-confidence': { border: '#b45309', text: '#b45309' },
  'extraction-error': { border: '#dc2626', text: '#dc2626' },
  'novel-layout': { border: NVIS.blue, text: NVIS.blue },
  timeout: { border: NVIS.dim, text: NVIS.dim },
}

const REASON_LABELS: Record<QuarantineEntry['reason'], string> = {
  'low-confidence': 'LowConf',
  'extraction-error': 'ExtErr',
  'novel-layout': 'Novel',
  timeout: 'Timeout',
}

const FILTER_CHIPS: { value: ReasonFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'low-confidence', label: 'LowConf' },
  { value: 'extraction-error', label: 'ExtErr' },
  { value: 'novel-layout', label: 'Novel' },
  { value: 'timeout', label: 'Timeout' },
]

const DISPOSITION_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  Accept: {
    bg: 'rgba(21, 128, 61, 0.10)',
    border: 'rgba(21, 128, 61, 0.25)',
    text: '#15803d',
  },
  Reject: {
    bg: 'rgba(220, 38, 38, 0.10)',
    border: 'rgba(220, 38, 38, 0.25)',
    text: '#dc2626',
  },
  Escalate: {
    bg: 'rgba(180, 83, 9, 0.10)',
    border: 'rgba(180, 83, 9, 0.25)',
    text: '#b45309',
  },
}

const RE_EXTRACT_STRATEGIES = [
  { value: 'auto', label: 'Auto' },
  { value: 'tagged', label: 'Tagged PDF' },
  { value: 'visual', label: 'Visual' },
  { value: 'ocr', label: 'OCR' },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function qualityScoreColor(score: number): string {
  if (score >= 0.82) return '#15803d'
  if (score >= 0.70) return '#b45309'
  return '#dc2626'
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 1) + '\u2026' : s
}

function qualityScore(entry: QuarantineEntry): number | null {
  if (!entry.scores) return null
  const vals = Object.values(entry.scores)
  if (vals.length === 0) return null
  return vals.reduce((a, b) => a + b, 0) / vals.length
}

/** Convert QuarantineBlocks to BboxBlocks with mock cascade data */
function toBboxBlocks(blocks: QuarantineBlock[]): BboxBlock[] {
  const typeMap: Record<string, BboxBlock['blockType']> = {
    Header: 'header',
    Body: 'text',
    Boilerplate: 'text',
    Caption: 'caption',
    Footnote: 'text',
    Table: 'table',
    Figure: 'figure',
    Equation: 'equation',
    ListItem: 'list_item',
  }
  return blocks.map((b) => ({
    id: b.id,
    page: b.page,
    bbox: b.bbox,
    blockType: typeMap[b.block_type] ?? 'text',
    text: b.text,
    confidence: b.confidence ?? 0.5,
    sectionId: b.section_idx != null ? String(b.section_idx) : undefined,
    cascadeTrail: [
      {
        tier: 'T0' as const,
        tierName: 'Rust heuristic',
        disposition: (b.header_disposition === 'Accept'
          ? 'accept'
          : b.header_disposition === 'Reject'
          ? 'reject'
          : 'escalate') as 'accept' | 'reject' | 'escalate',
        confidence: b.confidence ?? 0.5,
      },
      {
        tier: 'T0.5' as const,
        tierName: 'RF classifier',
        disposition: (b.confidence != null && b.confidence >= 0.7
          ? 'accept'
          : 'escalate') as 'accept' | 'reject' | 'escalate',
        confidence: Math.min(1, (b.confidence ?? 0.5) + 0.15),
      },
      {
        tier: 'T2' as const,
        tierName: 'Human',
        disposition: 'escalate' as const,
        confidence: 0,
      },
    ],
  }))
}

function parseHash(): { doc?: string; section?: string } {
  const hash = window.location.hash
  if (!hash.startsWith('#quarantine')) return {}
  const params = new URLSearchParams(hash.replace('#quarantine', '').replace('?', ''))
  return {
    doc: params.get('doc') ?? undefined,
    section: params.get('section') ?? undefined,
  }
}

function setHash(doc?: string, section?: string) {
  const parts: string[] = []
  if (doc) parts.push(`doc=${encodeURIComponent(doc)}`)
  if (section) parts.push(`section=${encodeURIComponent(section)}`)
  // Always preserve 'quarantine' in hash so the App tab stays on Quarantine
  window.location.hash = parts.length > 0 ? `quarantine?${parts.join('&')}` : 'quarantine'
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ActionButton({
  label,
  color,
  disabled,
  onClick,
  'aria-label': ariaLabel,
}: {
  label: string
  color: string
  disabled: boolean
  onClick: () => void
  'aria-label'?: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      style={{
        padding: '5px 12px',
        fontSize: '11px',
        fontFamily: 'monospace',
        fontWeight: 600,
        borderRadius: '4px',
        border: `1px solid ${color}30`,
        backgroundColor: `${color}18`,
        color,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
      }}
    >
      {label}
    </button>
  )
}

function DispositionBadge({ disposition, extra }: { disposition?: string; extra?: string }) {
  if (!disposition) return null
  const cfg = DISPOSITION_COLORS[disposition] ?? DISPOSITION_COLORS.Escalate
  return (
    <span
      style={{
        fontSize: '10px',
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        padding: '2px 6px',
        borderRadius: '3px',
        fontWeight: 600,
        backgroundColor: cfg.bg,
        border: `1px solid ${cfg.border}`,
        color: cfg.text,
      }}
    >
      {disposition}{extra ? ` ${extra}` : ''}
    </span>
  )
}


// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Layout presets (L.2) + persistence (L.3)
// ---------------------------------------------------------------------------

type LayoutPreset = 'balanced' | 'review' | 'inspect' | 'wide-content'
const LAYOUT_PRESETS: Record<LayoutPreset, { queue: number; tree: number; label: string }> = {
  balanced:       { queue: 280, tree: 280, label: 'Balanced' },
  review:         { queue: 320, tree: 240, label: 'Review' },
  inspect:        { queue: 200, tree: 200, label: 'Inspect' },
  'wide-content': { queue: 220, tree: 220, label: 'Wide Content' },
}

function loadPreset(): LayoutPreset {
  try {
    const v = localStorage.getItem('quarantine_layout_preset')
    if (v && v in LAYOUT_PRESETS) return v as LayoutPreset
  } catch { /* ignore */ }
  return 'balanced'
}

function savePreset(p: LayoutPreset) {
  try { localStorage.setItem('quarantine_layout_preset', p) } catch { /* ignore */ }
}

export default function QuarantineView() {
  // -- Queue state --
  const [entries, setEntries] = useState<QuarantineEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set())
  const [reasonFilter, setReasonFilter] = useState<ReasonFilter>('all')
  const [search, setSearch] = useState('')
  const [sort] = useState<SortMode>('newest')
  const [actionInFlight, setActionInFlight] = useState<string | null>(null)
  const [hoveredQueueIdx, setHoveredQueueIdx] = useState<number | null>(null)

  // -- Detail state --
  const [detail, setDetail] = useState<QuarantineDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // -- Section tree state --
  const [selectedSectionIdx, setSelectedSectionIdx] = useState<number | null>(null)
  const [collapsedSections, setCollapsedSections] = useState<Set<number>>(new Set())
  const [hoveredSectionIdx, setHoveredSectionIdx] = useState<number | null>(null)

  // -- Detail panel state --
  const [reExtractStrategy, setReExtractStrategy] = useState('auto')

  // -- BBox workspace state --
  const [bboxPage, setBboxPage] = useState(0)
  const [showSpotReextract, setShowSpotReextract] = useState(false)
  const [bboxBlocks, setBboxBlocks] = useState<BboxBlock[]>([])

  // -- Layout state (L.2 + L.3) --
  const [layoutPreset, setLayoutPreset] = useState<LayoutPreset>(loadPreset)
  const [chatOpen, setChatOpen] = useState(false)
  const layoutWidths = LAYOUT_PRESETS[layoutPreset]

  const handlePresetChange = useCallback((p: LayoutPreset) => {
    setLayoutPreset(p)
    savePreset(p)
  }, [])

  // -- Refs --
  const queueRef = useRef<HTMLDivElement>(null)
  const sectionTreeRef = useRef<HTMLDivElement>(null)

  // ---------------------------------------------------------------------------
  // Deep-link on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const { doc } = parseHash()
    if (doc) setSelectedId(doc)
  }, [])

  // ---------------------------------------------------------------------------
  // Fetch entries
  // ---------------------------------------------------------------------------
  const fetchEntries = useCallback(async () => {
    setLoading(true)
    setError(null)
    // Load initial data from loader (real sample data)
    const filter = reasonFilter === 'all' ? undefined : { reason: reasonFilter }
    const data = await loadQuarantine(filter)
    setEntries(data)
    setLoading(false)
    // Try embry-memory to replace with live data
    try {
      const memoryResult = await recallDocuments('quarantine', 'quarantine')
      if (memoryResult.results && memoryResult.results.length > 0) {
        const mapped: QuarantineEntry[] = memoryResult.results.map((r) => {
          const meta = r.metadata as Record<string, unknown>
          return {
            id: r.key,
            filename: (meta.filename as string) ?? r.key,
            path: (meta.path as string) ?? '',
            category: (meta.category as string) ?? 'unknown',
            reason: ((meta.reason as string) ?? 'low-confidence') as QuarantineEntry['reason'],
            timestamp: (meta.timestamp as string) ?? new Date().toISOString(),
            pages: (meta.pages as number) ?? undefined,
            extraction_time_ms: (meta.extraction_time_ms as number) ?? undefined,
            fail_rate: (meta.fail_rate as number) ?? undefined,
            cascade_tier: (meta.cascade_tier as number) ?? undefined,
            scores: (meta.scores as Record<string, number>) ?? undefined,
            error: (meta.error as string) ?? undefined,
          }
        })
        const reasonFilter_ = reasonFilter === 'all' ? undefined : reasonFilter
        const filtered = reasonFilter_ ? mapped.filter((e) => e.reason === reasonFilter_) : mapped
        if (filtered.length > 0) {
          setEntries(filtered)
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Memory service unreachable')
    }
  }, [reasonFilter])

  useEffect(() => {
    fetchEntries()
  }, [fetchEntries])

  // ---------------------------------------------------------------------------
  // Fetch detail when selection changes
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      setSelectedSectionIdx(null)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    fetch(`${API_BASE}/api/quarantine/${encodeURIComponent(selectedId)}/detail`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((data: QuarantineDetail | null) => {
        if (!cancelled) {
          setDetail(data)
          setDetailLoading(false)
          setSelectedSectionIdx(null)
          // Deep-link section
          const { section: sectionNum } = parseHash()
          if (sectionNum && data?.sections) {
            const idx = data.sections.findIndex(
              (s) => s.section_number === sectionNum
            )
            if (idx >= 0) setSelectedSectionIdx(idx)
          }
        }
      })
    return () => {
      cancelled = true
    }
  }, [selectedId])

  // ---------------------------------------------------------------------------
  // Update hash on selection change
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const sectionNum =
      selectedSectionIdx != null && detail?.sections?.[selectedSectionIdx]
        ? detail.sections[selectedSectionIdx].section_number
        : undefined
    setHash(selectedId ?? undefined, sectionNum)
  }, [selectedId, selectedSectionIdx, detail])

  // ---------------------------------------------------------------------------
  // Convert detail blocks to BboxBlocks
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (detail?.blocks) {
      setBboxBlocks(toBboxBlocks(detail.blocks))
      setBboxPage(0)
    } else {
      setBboxBlocks([])
    }
  }, [detail])

  // ---------------------------------------------------------------------------
  // Filter & sort
  // ---------------------------------------------------------------------------
  const filtered = useMemo(() => {
    return entries
      .filter((e) => {
        if (search) {
          const q = search.toLowerCase()
          return (
            e.filename.toLowerCase().includes(q) ||
            e.category.toLowerCase().includes(q)
          )
        }
        return true
      })
      .sort((a, b) => {
        if (sort === 'newest')
          return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        if (sort === 'oldest')
          return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
        return (qualityScore(b) ?? 0) - (qualityScore(a) ?? 0)
      })
  }, [entries, search, sort])

  const selected = filtered.find((e) => e.id === selectedId) ?? null
  const selectedIdx = selected ? filtered.indexOf(selected) : -1

  // Reason counts for filter chips
  const reasonCounts = useMemo(() => {
    const counts: Record<string, number> = { all: entries.length }
    for (const e of entries) {
      counts[e.reason] = (counts[e.reason] ?? 0) + 1
    }
    return counts
  }, [entries])

  // ---------------------------------------------------------------------------
  // Sections for tree: build children map + filter by selected doc
  // ---------------------------------------------------------------------------
  const sections = detail?.sections ?? []
  const sectionChildren = useMemo(() => {
    const map: Record<number, number[]> = {}
    sections.forEach((s, i) => {
      const parent = s.parent_idx ?? -1
      if (!map[parent]) map[parent] = []
      map[parent].push(i)
    })
    return map
  }, [sections])

  const topLevelSections = sectionChildren[-1] ?? []

  // Blocks for selected section
  const sectionBlocks = useMemo<QuarantineBlock[]>(() => {
    if (selectedSectionIdx == null || !detail) return []
    const sec = detail.sections[selectedSectionIdx]
    if (!sec) return []
    // Find blocks assigned to this section (by section_idx) or by page range
    return detail.blocks.filter((b) => {
      if (b.section_idx === selectedSectionIdx) return true
      return b.page >= sec.page_start && b.page <= sec.page_end
    })
  }, [selectedSectionIdx, detail])

  // Tables and figures for selected section
  const sectionTables = useMemo<Table[]>(() => {
    if (selectedSectionIdx == null || !detail) return []
    const sec = detail.sections[selectedSectionIdx]
    if (!sec) return []
    return detail.tables.filter(
      (t) => t.page_number >= sec.page_start && t.page_number <= sec.page_end
    )
  }, [selectedSectionIdx, detail])


  // ---------------------------------------------------------------------------
  // Keyboard navigation
  // ---------------------------------------------------------------------------
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return

      if (e.key === 'j') {
        e.preventDefault()
        const nextIdx = Math.min(filtered.length - 1, selectedIdx + 1)
        if (filtered[nextIdx]) setSelectedId(filtered[nextIdx].id)
      } else if (e.key === 'k') {
        e.preventDefault()
        const prevIdx = Math.max(0, selectedIdx - 1)
        if (filtered[prevIdx]) setSelectedId(filtered[prevIdx].id)
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        // Navigate sections
        if (sections.length > 0) {
          const next =
            selectedSectionIdx == null ? 0 : Math.min(sections.length - 1, selectedSectionIdx + 1)
          setSelectedSectionIdx(next)
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        if (sections.length > 0) {
          const prev =
            selectedSectionIdx == null
              ? sections.length - 1
              : Math.max(0, selectedSectionIdx - 1)
          setSelectedSectionIdx(prev)
        }
      } else if (e.key === 'Enter' && selected && selectedSectionIdx == null && sections.length > 0) {
        e.preventDefault()
        setSelectedSectionIdx(0)
      } else if (e.key === 'Escape') {
        e.preventDefault()
        if (selectedSectionIdx != null) {
          setSelectedSectionIdx(null)
        }
      } else if (e.key === 'a' && !e.ctrlKey && !e.metaKey && selected) {
        e.preventDefault()
        handleAction(selected.id, 'approve')
      } else if (e.key === 'r' && !e.ctrlKey && !e.metaKey && selected) {
        e.preventDefault()
        handleAction(selected.id, 'reject')
      } else if (e.key === 'x' && !e.ctrlKey && !e.metaKey && selected) {
        e.preventDefault()
        if (selectedSectionIdx != null) {
          setShowSpotReextract(true)
        } else {
          handleAction(selected.id, 're-extract')
        }
      } else if (e.key === 'i' && !e.ctrlKey && !e.metaKey && selected) {
        e.preventDefault()
        handleAction(selected.id, 'interview')
      } else if (e.key === ' ' && selected) {
        e.preventDefault()
        toggleChecked(selected.id)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [filtered, selectedIdx, selected, sections, selectedSectionIdx])

  // Scroll queue selection into view
  useEffect(() => {
    if (!selectedId || !queueRef.current) return
    const el = queueRef.current.querySelector(`[data-entry-id="${CSS.escape(selectedId)}"]`)
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedId])

  // Scroll section selection into view
  useEffect(() => {
    if (selectedSectionIdx == null || !sectionTreeRef.current) return
    const el = sectionTreeRef.current.querySelector(
      `[data-section-idx="${selectedSectionIdx}"]`
    )
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedSectionIdx])

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------
  async function handleAction(id: string, action: ActionType) {
    setActionInFlight(action)
    setEntries((prev) => prev.filter((e) => e.id !== id))
    setCheckedIds((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
    if (selectedId === id) setSelectedId(null)
    try {
      const body: Record<string, string> = { action }
      if (action === 're-extract') body.strategy = reExtractStrategy
      await fetch(`${API_BASE}/api/quarantine/${encodeURIComponent(id)}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } catch {
      fetchEntries()
    } finally {
      setActionInFlight(null)
    }
  }

  async function handleBatchApprove() {
    const ids = [...checkedIds]
    if (ids.length === 0) return
    setActionInFlight('approve')
    for (const id of ids) {
      setEntries((prev) => prev.filter((e) => e.id !== id))
      try {
        await fetch(`${API_BASE}/api/quarantine/${encodeURIComponent(id)}/action`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'approve' }),
        })
      } catch {
        // continue
      }
    }
    setCheckedIds(new Set())
    if (selectedId && ids.includes(selectedId)) setSelectedId(null)
    setActionInFlight(null)
    fetchEntries()
  }

  function toggleChecked(id: string) {
    setCheckedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectAllVisible() {
    setCheckedIds(new Set(filtered.map((e) => e.id)))
  }

  function toggleCollapsed(idx: number) {
    setCollapsedSections((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  // ---------------------------------------------------------------------------
  // Section tree rendering (recursive)
  // ---------------------------------------------------------------------------
  function renderSectionNode(idx: number): React.ReactNode {
    const sec = sections[idx]
    if (!sec) return null
    const children = sectionChildren[idx] ?? []
    const hasChildren = children.length > 0
    const isCollapsed = collapsedSections.has(idx)
    const isSelected = selectedSectionIdx === idx
    const indent = 12 + sec.level * 16

    // Count tables/figures in this section's page range
    const tables = detail?.tables.filter(
      (t) => t.page_number >= sec.page_start && t.page_number <= sec.page_end
    ) ?? []
    const figures = detail?.figures.filter(
      (f) => f.page >= sec.page_start && f.page <= sec.page_end
    ) ?? []

    // Determine quality color from disposition
    const dispColor =
      sec.header_disposition === 'Reject'
        ? '#dc2626'
        : sec.header_disposition === 'Escalate'
          ? '#b45309'
          : undefined

    const pageLabel =
      sec.page_start === sec.page_end
        ? `p.${sec.page_start + 1}`
        : `pp.${sec.page_start + 1}-${sec.page_end + 1}`

    const isSectionHovered = hoveredSectionIdx === idx

    return (
      <div key={idx}>
        <div
          data-section-idx={idx}
          role="treeitem"
          aria-selected={isSelected}
          aria-expanded={hasChildren ? !isCollapsed : undefined}
          tabIndex={0}
          onClick={() => setSelectedSectionIdx(idx)}
          onMouseEnter={() => setHoveredSectionIdx(idx)}
          onMouseLeave={() => setHoveredSectionIdx(null)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              setSelectedSectionIdx(idx)
            }
          }}
          style={{
            padding: `4px 12px 4px ${indent}px`,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '6px',
            borderLeft: isSelected
              ? `2px solid ${NVIS.accent}`
              : dispColor
                ? `2px solid ${dispColor}`
                : '2px solid transparent',
            fontSize: '12px',
            lineHeight: '1.4',
            backgroundColor: isSelected
              ? `${NVIS.accent}14`
              : isSectionHovered
                ? 'rgba(74,158,255,0.04)'
                : 'transparent',
          }}
        >
          {/* Toggle */}
          <span
            style={{
              fontSize: '9px',
              color: NVIS.dim,
              width: '12px',
              flexShrink: 0,
              textAlign: 'center',
              marginTop: '2px',
              cursor: hasChildren ? 'pointer' : 'default',
            }}
            onClick={(e) => {
              if (hasChildren) {
                e.stopPropagation()
                toggleCollapsed(idx)
              }
            }}
          >
            {hasChildren ? (isCollapsed ? '\u25B6' : '\u25BC') : '\u00A0'}
          </span>

          {/* Section number */}
          <span
            style={{
              color: NVIS.dim,
              fontSize: '11px',
              flexShrink: 0,
              minWidth: '28px',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {sec.section_number ?? ''}
          </span>

          {/* Title */}
          <span
            style={{
              flex: 1,
              color: NVIS.white,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={sec.display_title || sec.title}
          >
            {truncate(sec.display_title || sec.title, 32)}
          </span>

          {/* Pages */}
          <span
            style={{
              fontSize: '10px',
              color: NVIS.dim,
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
          >
            {pageLabel}
          </span>

          {/* Disposition badge (inline small) */}
          {sec.header_disposition && sec.header_disposition !== 'Accept' && (
            <span
              style={{
                fontSize: '8px',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                padding: '0 3px',
                borderRadius: '2px',
                fontWeight: 600,
                color:
                  sec.header_disposition === 'Reject' ? '#dc2626' : '#b45309',
                backgroundColor:
                  sec.header_disposition === 'Reject'
                    ? 'rgba(220,38,38,0.10)'
                    : 'rgba(180,83,9,0.10)',
              }}
            >
              {sec.header_disposition === 'Reject' ? 'REJ' : 'ESC'}
            </span>
          )}

          {/* Asset badges */}
          {(tables.length > 0 || figures.length > 0) && (
            <span style={{ display: 'flex', gap: '3px', flexShrink: 0, marginLeft: '2px' }}>
              {tables.length > 0 && (
                <span
                  style={{
                    fontSize: '8px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.03em',
                    padding: '1px 4px',
                    borderRadius: '2px',
                    backgroundColor: NVIS.surface2,
                    border: `1px solid rgba(21,128,61,0.2)`,
                    color: '#15803d',
                  }}
                >
                  T{tables.length}
                </span>
              )}
              {figures.length > 0 && (
                <span
                  style={{
                    fontSize: '8px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.03em',
                    padding: '1px 4px',
                    borderRadius: '2px',
                    backgroundColor: NVIS.surface2,
                    border: `1px solid rgba(180,83,9,0.2)`,
                    color: '#b45309',
                  }}
                >
                  F{figures.length}
                </span>
              )}
            </span>
          )}
        </div>

        {/* Children */}
        {hasChildren && !isCollapsed && children.map(renderSectionNode)}
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Selected section data
  // ---------------------------------------------------------------------------
  const selectedSection: Section | null =
    selectedSectionIdx != null ? sections[selectedSectionIdx] ?? null : null
  const parentSection: Section | null =
    selectedSection?.parent_idx != null
      ? sections[selectedSection.parent_idx] ?? null
      : null

  // ---------------------------------------------------------------------------
  // Empty state
  // ---------------------------------------------------------------------------
  if (!loading && entries.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '400px',
          color: NVIS.dim,
          fontFamily: 'monospace',
        }}
      >
        <div style={{ fontSize: '48px', marginBottom: '16px', opacity: 0.3 }}>
          &#10003;
        </div>
        <div style={{ fontSize: '16px', marginBottom: '8px', color: '#15803d' }}>
          Quarantine queue is empty
        </div>
        <div style={{ fontSize: '12px' }}>
          No documents require manual review at this time.
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div
      style={{
        fontFamily: 'monospace',
        fontSize: '13px',
        display: 'flex',
        flexDirection: 'column',
        height: 'calc(100vh - 100px)',
      }}
    >
      {error && (
        <div style={{ background: '#1a0000', border: '1px solid #ff4444', borderRadius: 4, padding: '8px 12px', margin: '8px 0', color: '#ff4444', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
          ✗ {error}
        </div>
      )}
      {/* ── Status bar (top) ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '6px 16px',
          backgroundColor: NVIS.surface,
          borderBottom: `1px solid ${NVIS.borderSolid}`,
          flexShrink: 0,
          fontSize: '11px',
        }}
      >
        <span style={{ color: NVIS.dim }}>
          {filtered.length} doc{filtered.length !== 1 ? 's' : ''}
        </span>
        {checkedIds.size > 0 && (
          <span style={{ color: NVIS.accent }}>
            {checkedIds.size} selected
          </span>
        )}
        {/* Layout presets (L.2) */}
        <div style={{ display: 'flex', gap: '3px', marginLeft: '8px' }}>
          {(Object.keys(LAYOUT_PRESETS) as LayoutPreset[]).map((p) => (
            <button
              key={p}
              onClick={() => handlePresetChange(p)}
              style={{
                fontFamily: 'monospace',
                fontSize: '9px',
                padding: '1px 5px',
                borderRadius: '2px',
                border: layoutPreset === p
                  ? `1px solid ${NVIS.accent}`
                  : `1px solid ${NVIS.borderSolid}`,
                backgroundColor: layoutPreset === p ? `${NVIS.accent}14` : 'transparent',
                color: layoutPreset === p ? NVIS.accent : NVIS.dim,
                cursor: 'pointer',
                textTransform: 'uppercase',
                letterSpacing: '0.03em',
              }}
            >
              {LAYOUT_PRESETS[p].label}
            </button>
          ))}
        </div>

        {/* Chat toggle (L.7) */}
        <button
          onClick={() => setChatOpen((p) => !p)}
          style={{
            fontFamily: 'monospace',
            fontSize: '9px',
            padding: '2px 6px',
            borderRadius: '2px',
            border: chatOpen
              ? `1px solid ${NVIS.accent}`
              : `1px solid ${NVIS.borderSolid}`,
            backgroundColor: chatOpen ? `${NVIS.accent}14` : 'transparent',
            color: chatOpen ? NVIS.accent : NVIS.dim,
            cursor: 'pointer',
            marginLeft: '4px',
          }}
        >
          Chat
        </button>

        <span style={{ marginLeft: 'auto', color: NVIS.dim, opacity: 0.5, fontSize: '10px' }}>
          j/k queue &middot; &uarr;&darr; sections &middot; Enter open &middot; Esc close &middot; a approve &middot; r reject &middot; x re-extract &middot; i interview &middot; Space select
        </span>
      </div>

      {/* ── Three-panel layout ── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* ================================================================= */}
        {/* Panel 1: Document Queue                                           */}
        {/* ================================================================= */}
        <div
          style={{
            width: `${layoutWidths.queue}px`,
            flexShrink: 0,
            backgroundColor: NVIS.surface,
            borderRight: `1px solid ${NVIS.borderSolid}`,
            display: 'flex',
            flexDirection: 'column',
            position: 'relative',
          }}
        >
          {/* Resize handle (L.1: 8px hit area) */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              right: '-4px',
              bottom: 0,
              width: '8px',
              cursor: 'col-resize',
              zIndex: 5,
            }}
            title="Drag to resize"
          />
          {/* Queue header: filter chips + search */}
          <div style={{ padding: '10px 10px 0 10px', flexShrink: 0 }}>
            <div
              style={{
                fontSize: '11px',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: NVIS.dim,
                marginBottom: '6px',
              }}
            >
              Documents
            </div>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: '8px' }}>
              {FILTER_CHIPS.map((chip) => {
                const isActive = chip.value === reasonFilter
                const chipColor =
                  chip.value === 'all'
                    ? NVIS.accent
                    : REASON_COLORS[chip.value as QuarantineEntry['reason']]?.text ?? NVIS.dim
                const count = reasonCounts[chip.value] ?? 0
                return (
                  <button
                    key={chip.value}
                    role="radio"
                    aria-checked={isActive}
                    onClick={() => setReasonFilter(chip.value)}
                    style={{
                      padding: '2px 6px',
                      fontSize: '10px',
                      fontFamily: 'monospace',
                      borderRadius: '3px',
                      border: `1px solid ${isActive ? chipColor : NVIS.borderSolid}`,
                      backgroundColor: isActive ? `${chipColor}18` : NVIS.surface2,
                      color: isActive ? chipColor : NVIS.dim,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                    }}
                  >
                    {chip.label}
                    <span style={{ opacity: 0.7, fontSize: '9px', marginLeft: '2px' }}>
                      ({count})
                    </span>
                  </button>
                )
              })}
            </div>
            <input
              type="text"
              placeholder="Search..."
              aria-label="Search quarantine queue by filename"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                padding: '4px 8px',
                fontSize: '11px',
                fontFamily: 'monospace',
                backgroundColor: NVIS.surface2,
                border: `1px solid ${NVIS.borderSolid}`,
                borderRadius: '3px',
                color: NVIS.white,
                marginBottom: '6px',
              }}
            />
          </div>

          {/* Queue list */}
          <div
            ref={queueRef}
            role="listbox"
            aria-label="Quarantine document queue"
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '0 4px',
            }}
          >
            {loading ? (
              <div style={{ padding: '24px', color: NVIS.dim, textAlign: 'center' }}>
                Loading...
              </div>
            ) : filtered.length === 0 ? (
              <div style={{ padding: '24px', color: NVIS.dim, textAlign: 'center' }}>
                No matches.
              </div>
            ) : (
              filtered.map((entry, qIdx) => {
                const isSelected = entry.id === selectedId
                const isChecked = checkedIds.has(entry.id)
                const rc = REASON_COLORS[entry.reason]
                const score = qualityScore(entry)
                const isHovered = hoveredQueueIdx === qIdx
                return (
                  <div
                    key={entry.id}
                    data-entry-id={entry.id}
                    role="option"
                    aria-selected={isSelected}
                    tabIndex={0}
                    onClick={() => setSelectedId(entry.id)}
                    onMouseEnter={() => setHoveredQueueIdx(qIdx)}
                    onMouseLeave={() => setHoveredQueueIdx(null)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        if (e.key === ' ') toggleChecked(entry.id)
                        else setSelectedId(entry.id)
                      }
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '6px 8px',
                      borderRadius: '0',
                      border: 'none',
                      borderLeft: isSelected
                        ? `2px solid ${NVIS.accent}`
                        : '2px solid transparent',
                      backgroundColor: isSelected
                        ? `${NVIS.accent}0F`
                        : isHovered
                          ? '#161b21'
                          : 'transparent',
                      cursor: 'pointer',
                      marginBottom: '1px',
                      fontSize: '11px',
                    }}
                  >
                    {/* Checkbox */}
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={(e) => {
                        e.stopPropagation()
                        toggleChecked(entry.id)
                      }}
                      aria-label={`Select ${entry.filename}`}
                      style={{
                        flexShrink: 0,
                        accentColor: NVIS.accent,
                        cursor: 'pointer',
                      }}
                    />

                    {/* Filename */}
                    <span
                      style={{
                        flex: 1,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        color: NVIS.white,
                        fontSize: '11px',
                      }}
                      title={entry.filename}
                    >
                      {truncate(entry.filename, 25)}
                    </span>

                    {/* Reason tag */}
                    <span
                      style={{
                        fontSize: '9px',
                        textTransform: 'uppercase',
                        letterSpacing: '0.04em',
                        padding: '1px 4px',
                        borderRadius: '2px',
                        backgroundColor: NVIS.surface2,
                        border: `1px solid ${rc.border}30`,
                        color: rc.text,
                        flexShrink: 0,
                      }}
                    >
                      {REASON_LABELS[entry.reason]}
                    </span>

                    {/* Quality score */}
                    {score != null && (
                      <span
                        style={{
                          fontSize: '11px',
                          fontVariantNumeric: 'tabular-nums',
                          fontWeight: 600,
                          padding: '1px 5px',
                          borderRadius: '3px',
                          color: qualityScoreColor(score),
                          backgroundColor: `${qualityScoreColor(score)}14`,
                          flexShrink: 0,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <span style={{ fontSize: '13px', fontWeight: 700, lineHeight: 1 }}>
                          {score >= 0.82 ? '\u2713' : score >= 0.70 ? '\u26A0' : '\u2717'}
                        </span>
                        {score.toFixed(2)}
                      </span>
                    )}
                  </div>
                )
              })
            )}
          </div>

          {/* Queue footer: batch ops */}
          <div
            style={{
              flexShrink: 0,
              padding: '8px 10px',
              borderTop: `1px solid ${NVIS.borderSolid}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '11px',
            }}
          >
            <button
              onClick={selectAllVisible}
              aria-label="Select all visible documents"
              style={{
                fontSize: '10px',
                fontFamily: 'monospace',
                padding: '3px 8px',
                borderRadius: '3px',
                backgroundColor: NVIS.surface2,
                border: `1px solid ${NVIS.borderSolid}`,
                color: NVIS.dim,
                cursor: 'pointer',
              }}
            >
              Select All
            </button>
            <button
              onClick={handleBatchApprove}
              disabled={checkedIds.size === 0 || actionInFlight !== null}
              aria-label={`Approve ${checkedIds.size} selected documents`}
              style={{
                fontSize: '10px',
                fontFamily: 'monospace',
                padding: '3px 10px',
                borderRadius: '4px',
                backgroundColor: checkedIds.size > 0 ? 'rgba(21,128,61,0.10)' : NVIS.surface2,
                border: `1px solid ${checkedIds.size > 0 ? 'rgba(21,128,61,0.25)' : NVIS.borderSolid}`,
                color: checkedIds.size > 0 ? '#15803d' : NVIS.dim,
                cursor: checkedIds.size === 0 ? 'not-allowed' : 'pointer',
                opacity: checkedIds.size === 0 ? 0.5 : 1,
              }}
            >
              Approve ({checkedIds.size})
            </button>
          </div>
        </div>

        {/* ================================================================= */}
        {/* Panel 2: Section Tree                                             */}
        {/* ================================================================= */}
        <div
          style={{
            width: `${layoutWidths.tree}px`,
            flexShrink: 0,
            backgroundColor: NVIS.bg,
            borderRight: `1px solid ${NVIS.borderSolid}`,
            display: 'flex',
            flexDirection: 'column',
            position: 'relative',
          }}
        >
          {/* Resize handle (L.1: 8px hit area) */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              right: '-4px',
              bottom: 0,
              width: '8px',
              cursor: 'col-resize',
              zIndex: 5,
            }}
            title="Drag to resize"
          />
          {/* Tree header */}
          <div
            style={{
              height: '36px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 12px',
              borderBottom: `1px solid ${NVIS.borderSolid}`,
              flexShrink: 0,
              backgroundColor: NVIS.surface,
            }}
          >
            <span
              style={{
                fontSize: '11px',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                color: NVIS.dim,
              }}
            >
              Section Hierarchy
            </span>
            <span style={{ fontSize: '10px', color: NVIS.dim }}>
              {sections.length} section{sections.length !== 1 ? 's' : ''}
              {detail?.page_count
                ? ` \u00B7 ${detail.page_count} pg${detail.page_count !== 1 ? 's' : ''}`
                : ''}
            </span>
          </div>

          {/* Tree body */}
          <div
            ref={sectionTreeRef}
            role="tree"
            aria-label="Section hierarchy"
            style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}
          >
            {!selected ? (
              <div
                style={{
                  padding: '24px 12px',
                  color: NVIS.dim,
                  fontSize: '12px',
                  textAlign: 'center',
                }}
              >
                Select a document
              </div>
            ) : detailLoading ? (
              <div
                style={{
                  padding: '24px 12px',
                  color: NVIS.dim,
                  fontSize: '12px',
                  textAlign: 'center',
                }}
              >
                Loading sections...
              </div>
            ) : sections.length === 0 ? (
              <div
                style={{
                  padding: '24px 12px',
                  color: NVIS.dim,
                  fontSize: '12px',
                  textAlign: 'center',
                }}
              >
                No sections found.
              </div>
            ) : (
              topLevelSections.map(renderSectionNode)
            )}
          </div>
        </div>

        {/* ================================================================= */}
        {/* Panel 3: Section Detail + Source Strip (flex)                     */}
        {/* ================================================================= */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            backgroundColor: NVIS.bg,
            minWidth: 0,
          }}
        >
          {!selected ? (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                color: NVIS.dim,
                fontSize: '14px',
              }}
            >
              Select a document to review
            </div>
          ) : selectedSection == null ? (
            // Document overview (no section selected)
            <div style={{ padding: '20px', overflowY: 'auto' }}>
              <h2
                style={{
                  margin: 0,
                  fontSize: '16px',
                  color: NVIS.white,
                  fontWeight: 600,
                  marginBottom: '4px',
                }}
              >
                {selected.filename}
              </h2>
              <div style={{ fontSize: '11px', color: NVIS.dim, marginBottom: '16px' }}>
                {selected.path}
              </div>

              {/* Diagnostic cards */}
              <div
                style={{
                  display: 'flex',
                  gap: '10px',
                  marginBottom: '16px',
                  flexWrap: 'wrap',
                }}
              >
                <DiagCard label="Pages" value={String(detail?.page_count ?? selected.pages ?? '--')} />
                <DiagCard
                  label="Sections"
                  value={String(sections.length)}
                />
                <DiagCard
                  label="Tables"
                  value={String(detail?.tables.length ?? '--')}
                />
                <DiagCard
                  label="Figures"
                  value={String(detail?.figures.length ?? '--')}
                />
                <DiagCard
                  label="Cascade Tier"
                  value={selected.cascade_tier != null ? `T${selected.cascade_tier}` : '--'}
                />
              </div>

              {/* Error display */}
              {selected.error && (
                <div
                  style={{
                    color: '#dc2626',
                    marginBottom: '12px',
                    padding: '8px 12px',
                    backgroundColor: 'rgba(220,38,38,0.06)',
                    borderRadius: '4px',
                    border: '1px solid rgba(220,38,38,0.15)',
                    fontSize: '12px',
                  }}
                >
                  {selected.error}
                </div>
              )}

              <div
                style={{
                  color: NVIS.dim,
                  fontSize: '12px',
                  padding: '40px 0',
                  textAlign: 'center',
                }}
              >
                Select a section from the tree to review content.
              </div>
            </div>
          ) : (
            // Section detail view
            <>
              {/* Section header */}
              <div
                style={{
                  flexShrink: 0,
                  padding: '12px 16px',
                  borderBottom: `1px solid ${NVIS.borderSolid}`,
                  backgroundColor: NVIS.surface,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    marginBottom: '6px',
                  }}
                >
                  <span
                    style={{
                      fontSize: '14px',
                      fontWeight: 600,
                      color: NVIS.accent,
                    }}
                  >
                    {selectedSection.section_number ?? ''}
                  </span>
                  <span
                    style={{
                      fontSize: '14px',
                      fontWeight: 600,
                      color: NVIS.white,
                    }}
                  >
                    {selectedSection.display_title || selectedSection.title}
                  </span>
                  <DispositionBadge disposition={selectedSection.header_disposition} />
                </div>

                <div
                  style={{
                    display: 'flex',
                    gap: '16px',
                    fontSize: '11px',
                    color: NVIS.dim,
                    alignItems: 'center',
                  }}
                >
                  <MetaItem label="Level" value={String(selectedSection.level)} />
                  <MetaItem
                    label="Pages"
                    value={
                      selectedSection.page_start === selectedSection.page_end
                        ? String(selectedSection.page_start + 1)
                        : `${selectedSection.page_start + 1}-${selectedSection.page_end + 1}`
                    }
                  />
                  <MetaItem
                    label="Blocks"
                    value={String(sectionBlocks.length)}
                  />
                  {parentSection && (
                    <MetaItem
                      label="Parent"
                      value={`${parentSection.section_number ?? ''} ${truncate(parentSection.title, 20)}`}
                      valueColor={NVIS.accent}
                    />
                  )}
                </div>
              </div>

              {/* BBox Workspace replaces old content+source layout */}
              <BboxWorkspace
                blocks={bboxBlocks}
                sections={sections}
                activeSectionId={selectedSectionIdx != null ? String(selectedSectionIdx) : undefined}
                pageCount={detail?.page_count ?? 1}
                currentPage={bboxPage}
                onPageChange={setBboxPage}
                onBlockUpdate={(updated) => {
                  setBboxBlocks((prev) =>
                    prev.map((b) => (b.id === updated.id ? updated : b))
                  )
                }}
                onBlockDelete={(blockId) => {
                  setBboxBlocks((prev) => prev.filter((b) => b.id !== blockId))
                }}
              />

              {/* SpotReextract dialog */}
              {showSpotReextract && (
                <SpotReextract
                  section={selectedSection ?? undefined}
                  sectionId={selectedSection?.section_number ?? undefined}
                  blockCount={sectionBlocks.length}
                  tableCount={sectionTables.length}
                  onAccept={(_result: ReextractResult) => {
                    setShowSpotReextract(false)
                    // In production: apply the result to update blocks
                  }}
                  onCancel={() => setShowSpotReextract(false)}
                />
              )}

              {/* Actions bar */}
              <div
                style={{
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 14px',
                  borderTop: `1px solid ${NVIS.borderSolid}`,
                  backgroundColor: NVIS.surface,
                  flexWrap: 'wrap',
                }}
              >
                {/* L.5: Approve/Reject are dominant buttons */}
                <button
                  onClick={() => handleAction(selected.id, 'approve')}
                  disabled={actionInFlight !== null}
                  aria-label={`Approve ${selected.filename}`}
                  style={{
                    padding: '6px 18px',
                    fontSize: '12px',
                    fontFamily: 'monospace',
                    fontWeight: 700,
                    borderRadius: '4px',
                    border: '1px solid #15803d',
                    backgroundColor: 'rgba(21, 128, 61, 0.18)',
                    color: '#15803d',
                    cursor: actionInFlight ? 'not-allowed' : 'pointer',
                    opacity: actionInFlight ? 0.5 : 1,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                  }}
                >
                  Approve (a)
                </button>
                <button
                  onClick={() => handleAction(selected.id, 'reject')}
                  disabled={actionInFlight !== null}
                  aria-label={`Reject ${selected.filename}`}
                  style={{
                    padding: '6px 18px',
                    fontSize: '12px',
                    fontFamily: 'monospace',
                    fontWeight: 700,
                    borderRadius: '4px',
                    border: '1px solid #dc2626',
                    backgroundColor: 'rgba(220, 38, 38, 0.18)',
                    color: '#dc2626',
                    cursor: actionInFlight ? 'not-allowed' : 'pointer',
                    opacity: actionInFlight ? 0.5 : 1,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                  }}
                >
                  Reject (r)
                </button>

                {/* Separator */}
                <div
                  style={{
                    width: '1px',
                    height: '22px',
                    backgroundColor: NVIS.borderSolid,
                    margin: '0 4px',
                  }}
                />

                <ActionButton
                  label="Re-extract (x)"
                  aria-label={`Re-extract ${selected.filename}`}
                  color={NVIS.accent}
                  disabled={actionInFlight !== null}
                  onClick={() => handleAction(selected.id, 're-extract')}
                />
                <select
                  value={reExtractStrategy}
                  onChange={(e) => setReExtractStrategy(e.target.value)}
                  aria-label="Re-extraction strategy"
                  style={{
                    fontFamily: 'monospace',
                    fontSize: '10px',
                    padding: '4px 7px',
                    borderRadius: '4px',
                    backgroundColor: NVIS.surface2,
                    border: `1px solid ${NVIS.borderSolid}`,
                    color: NVIS.white,
                    cursor: 'pointer',
                    appearance: 'none' as const,
                  }}
                >
                  {RE_EXTRACT_STRATEGIES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>

                <div
                  style={{
                    width: '1px',
                    height: '22px',
                    backgroundColor: NVIS.borderSolid,
                    margin: '0 4px',
                  }}
                />

                <ActionButton
                  label="Interview (i)"
                  aria-label={`Interview about ${selected.filename}`}
                  color="#b45309"
                  disabled={actionInFlight !== null}
                  onClick={() => handleAction(selected.id, 'interview')}
                />

                {/* Spacer + section scope indicator */}
                <span
                  style={{
                    marginLeft: 'auto',
                    fontSize: '10px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    color: NVIS.dim,
                  }}
                >
                  scope: &sect;{selectedSection.section_number ?? 'doc'}
                </span>
              </div>
            </>
          )}
        </div>

        {/* ================================================================= */}
        {/* Chat Slide-out (L.7: push, not overlay)                           */}
        {/* ================================================================= */}
        {chatOpen && (
          <div
            style={{
              width: '320px',
              flexShrink: 0,
              backgroundColor: NVIS.surface,
              borderLeft: `1px solid ${NVIS.borderSolid}`,
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div
              style={{
                padding: '10px 12px',
                borderBottom: `1px solid ${NVIS.borderSolid}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span
                style={{
                  fontSize: '11px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  color: NVIS.dim,
                }}
              >
                Interview Chat
              </span>
              <button
                onClick={() => setChatOpen(false)}
                style={{
                  fontFamily: 'monospace',
                  fontSize: '10px',
                  padding: '2px 6px',
                  borderRadius: '2px',
                  border: `1px solid ${NVIS.borderSolid}`,
                  backgroundColor: 'transparent',
                  color: NVIS.dim,
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>
            <div style={{ flex: 1, padding: '12px', overflowY: 'auto' }}>
              <div style={{ color: NVIS.dim, fontSize: '12px', textAlign: 'center', marginTop: '40px' }}>
                Chat with /assistant about this document.
              </div>
            </div>
            <div
              style={{
                padding: '8px 12px',
                borderTop: `1px solid ${NVIS.borderSolid}`,
              }}
            >
              <input
                type="text"
                placeholder="Ask about this document..."
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  fontSize: '11px',
                  fontFamily: 'monospace',
                  backgroundColor: NVIS.surface2,
                  border: `1px solid ${NVIS.borderSolid}`,
                  borderRadius: '4px',
                  color: NVIS.white,
                }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Small sub-components
// ---------------------------------------------------------------------------

function DiagCard({
  label,
  value,
  valueColor,
}: {
  label: string
  value: string
  valueColor?: string
}) {
  return (
    <div
      style={{
        padding: '10px 14px',
        backgroundColor: NVIS.surface,
        border: `1px solid ${NVIS.borderSolid}`,
        borderRadius: '6px',
        minWidth: '80px',
      }}
    >
      <div
        style={{
          fontSize: '10px',
          color: NVIS.dim,
          marginBottom: '4px',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: '18px', fontWeight: 700, color: valueColor ?? NVIS.white }}>
        {value}
      </div>
    </div>
  )
}

function MetaItem({
  label,
  value,
  valueColor,
}: {
  label: string
  value: string
  valueColor?: string
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
      <span
        style={{
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          fontSize: '10px',
          color: NVIS.dim,
        }}
      >
        {label}
      </span>
      <span style={{ color: valueColor ?? NVIS.white }}>{value}</span>
    </div>
  )
}
