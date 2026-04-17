import { useState, useEffect, useMemo } from 'react'
import { NVIS } from '../App'
import { TaxonomyChip, TaxonomyChipList } from '../components/TaxonomyChip'

// ---------- types local to batch ----------

interface BatchEntry {
  filename: string
  domain: string
  pages: number
  strategy: string
  status: 'success' | 'failed' | 'timeout'
  time_ms: number
  blocks: number
  sections: number
  tables: number
  figures: number
  taxonomy_tags?: string[]
}

interface BatchPayload {
  total: number
  processed: number
  results: BatchEntry[]
}

type SortKey = keyof Pick<BatchEntry, 'filename' | 'domain' | 'pages' | 'strategy' | 'status' | 'time_ms'>
type SortDir = 'asc' | 'desc'
type DomainFilter = 'All' | 'arxiv' | 'defense' | 'nasa' | 'nist' | 'engineering' | 'adversarial'
type StatusFilter = 'All' | 'success' | 'failed' | 'timeout'

const DOMAINS: DomainFilter[] = ['All', 'arxiv', 'defense', 'nasa', 'nist', 'engineering', 'adversarial']
const STATUSES: StatusFilter[] = ['All', 'success', 'failed', 'timeout']

const STATUS_COLOR: Record<string, string> = {
  success: NVIS.green,
  failed: NVIS.red,
  timeout: NVIS.amber,
}

const MUTED = 'rgba(255,255,255,0.65)'

// ---------- component ----------

export default function BatchView() {
  const [payload, setPayload] = useState<BatchPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [domainFilter, setDomainFilter] = useState<DomainFilter>('All')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('All')
  const [sortKey, setSortKey] = useState<SortKey>('filename')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)

  // fetch batch.json
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/batch.json')
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = (await res.json()) as BatchPayload
        if (!cancelled) setPayload(data)
      } catch (err) {
        console.error('[BatchView] failed to load batch.json', err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  // filtered + sorted rows
  const rows = useMemo(() => {
    if (!payload) return []
    let r = payload.results
    if (domainFilter !== 'All') r = r.filter((e) => e.domain === domainFilter)
    if (statusFilter !== 'All') r = r.filter((e) => e.status === statusFilter)
    const sorted = [...r].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
      }
      const an = av as number
      const bn = bv as number
      return sortDir === 'asc' ? an - bn : bn - an
    })
    return sorted
  }, [payload, domainFilter, statusFilter, sortKey, sortDir])

  // summary stats
  const stats = useMemo(() => {
    if (rows.length === 0) return { total: 0, successRate: 0, avgPages: 0, avgTime: 0 }
    const successes = rows.filter((r) => r.status === 'success').length
    const avgPages = rows.reduce((s, r) => s + r.pages, 0) / rows.length
    const avgTime = rows.reduce((s, r) => s + r.time_ms, 0) / rows.length
    return {
      total: rows.length,
      successRate: Math.round((successes / rows.length) * 1000) / 10,
      avgPages: Math.round(avgPages),
      avgTime: Math.round(avgTime),
    }
  }, [rows])

  const selected = selectedIdx !== null ? rows[selectedIdx] ?? null : null

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
    setSelectedIdx(null)
  }

  // column header helper
  function Th({ label, col }: { label: string; col: SortKey }) {
    const active = sortKey === col
    return (
      <th
        onClick={() => toggleSort(col)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSort(col) } }}
        tabIndex={0}
        role="button"
        aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}
        style={{
          cursor: 'pointer',
          textAlign: 'left',
          padding: '6px 8px',
          color: active ? NVIS.accent : MUTED,
          borderBottom: `1px solid ${NVIS.border}`,
          userSelect: 'none',
          whiteSpace: 'nowrap',
          outline: 'none',
        }}
        className="text-xs font-semibold focus-visible:ring-2 focus-visible:ring-[#4a9eff]"
      >
        {label} {active ? (sortDir === 'asc' ? '\u25B2' : '\u25BC') : ''}
      </th>
    )
  }

  // ---------- loading state ----------
  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ height: '100%', color: MUTED }}>
        <span className="text-sm">Loading batch data...</span>
      </div>
    )
  }

  if (!payload) {
    return (
      <div className="flex items-center justify-center" style={{ height: '100%', color: NVIS.red }}>
        <span className="text-sm">Failed to load batch.json</span>
      </div>
    )
  }

  const progressPct = payload.total > 0 ? (payload.processed / payload.total) * 100 : 0

  return (
    <div className="flex flex-col" style={{ height: '100%' }}>
      {/* progress bar header */}
      <div
        className="shrink-0 px-4 py-2"
        style={{ borderBottom: `1px solid ${NVIS.border}` }}
      >
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-semibold" style={{ color: 'white' }}>
            Batch Progress
          </span>
          <span className="text-xs" style={{ color: MUTED }}>
            {payload.processed} / {payload.total}
          </span>
        </div>
        <div role="progressbar" aria-valuenow={Math.round(progressPct)} aria-valuemin={0} aria-valuemax={100} aria-label={`Batch progress: ${payload.processed} of ${payload.total}`} style={{ height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.08)' }}>
          <div
            style={{
              width: `${progressPct}%`,
              height: '100%',
              borderRadius: 2,
              backgroundColor: progressPct >= 100 ? NVIS.green : NVIS.accent,
              transition: 'width 0.3s',
            }}
          />
        </div>
      </div>

      {/* 3 pane body */}
      <div className="flex flex-1 overflow-hidden">
        {/* LEFT pane — filters + stats */}
        <div
          className="overflow-y-auto"
          style={{ width: '30%', borderRight: `1px solid ${NVIS.border}` }}
        >
          <div className="p-4">
            <h2
              className="text-xs font-semibold uppercase tracking-widest mb-3"
              style={{ color: 'white' }}
            >
              Filters
            </h2>

            {/* domain filter */}
            <label className="text-xs block mb-1" style={{ color: MUTED }}>Domain</label>
            <select
              value={domainFilter}
              onChange={(e) => { setDomainFilter(e.target.value as DomainFilter); setSelectedIdx(null) }}
              className="w-full text-xs mb-3 rounded px-2 py-1 focus-visible:ring-2 focus-visible:ring-[#4a9eff]"
              style={{
                backgroundColor: 'rgba(255,255,255,0.06)',
                color: 'white',
                border: `1px solid ${NVIS.border}`,
                outline: 'none',
              }}
            >
              {DOMAINS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>

            {/* status filter */}
            <label className="text-xs block mb-1" style={{ color: MUTED }}>Status</label>
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value as StatusFilter); setSelectedIdx(null) }}
              className="w-full text-xs mb-4 rounded px-2 py-1 focus-visible:ring-2 focus-visible:ring-[#4a9eff]"
              style={{
                backgroundColor: 'rgba(255,255,255,0.06)',
                color: 'white',
                border: `1px solid ${NVIS.border}`,
                outline: 'none',
              }}
            >
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>

            {/* summary stats */}
            <h2
              className="text-xs font-semibold uppercase tracking-widest mb-3"
              style={{ color: 'white' }}
            >
              Summary
            </h2>

            <StatRow label="Total PDFs" value={String(stats.total)} color="white" />
            <StatRow
              label="Success Rate"
              value={`${stats.successRate}%`}
              color={stats.successRate >= 90 ? NVIS.green : stats.successRate >= 70 ? NVIS.amber : NVIS.red}
            />
            <StatRow label="Avg Pages" value={String(stats.avgPages)} color={NVIS.accent} />
            <StatRow label="Avg Time" value={`${stats.avgTime} ms`} color={NVIS.accent} />
          </div>
        </div>

        {/* CENTER pane — sortable table */}
        <div
          className="overflow-y-auto"
          style={{ width: '35%', borderRight: `1px solid ${NVIS.border}` }}
        >
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <Th label="File" col="filename" />
                <Th label="Domain" col="domain" />
                <Th label="Pages" col="pages" />
                <Th label="Strategy" col="strategy" />
                <Th label="Status" col="status" />
                <Th label="Time" col="time_ms" />
                <th
                  style={{
                    textAlign: 'left',
                    padding: '6px 8px',
                    color: MUTED,
                    borderBottom: `1px solid ${NVIS.border}`,
                    whiteSpace: 'nowrap',
                  }}
                  className="text-xs font-semibold"
                >
                  Tags
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const isSelected = selectedIdx === i
                return (
                  <tr
                    key={row.filename + i}
                    onClick={() => setSelectedIdx(i)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedIdx(i) } }}
                    tabIndex={0}
                    role="row"
                    aria-selected={isSelected}
                    style={{
                      cursor: 'pointer',
                      backgroundColor: isSelected
                        ? 'rgba(74,158,255,0.10)'
                        : 'transparent',
                      borderBottom: `1px solid ${NVIS.border}`,
                      outline: 'none',
                    }}
                    className="focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#4a9eff]"
                    onMouseEnter={(e) => {
                      if (!isSelected)
                        (e.currentTarget as HTMLElement).style.backgroundColor =
                          'rgba(255,255,255,0.04)'
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected)
                        (e.currentTarget as HTMLElement).style.backgroundColor = 'transparent'
                    }}
                  >
                    <td className="text-xs px-2 py-1" style={{ color: 'white', maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.filename}
                    </td>
                    <td className="text-xs px-2 py-1" style={{ color: MUTED }}>{row.domain}</td>
                    <td className="text-xs px-2 py-1" style={{ color: MUTED }}>{row.pages}</td>
                    <td className="text-xs px-2 py-1" style={{ color: MUTED, maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.strategy}</td>
                    <td className="text-xs px-2 py-1">
                      <span
                        style={{
                          display: 'inline-block',
                          fontSize: 10,
                          lineHeight: '16px',
                          padding: '0 6px',
                          borderRadius: 3,
                          color: '#141414',
                          fontWeight: 600,
                          backgroundColor: STATUS_COLOR[row.status] ?? MUTED,
                        }}
                      >
                        {row.status}
                      </span>
                    </td>
                    <td className="text-xs px-2 py-1" style={{ color: MUTED, textAlign: 'right' }}>
                      {row.time_ms.toLocaleString()}
                    </td>
                    <td className="text-xs px-2 py-1">
                      {row.taxonomy_tags && row.taxonomy_tags.length > 0 && (
                        <TaxonomyChip tag={row.taxonomy_tags[0]} />
                      )}
                    </td>
                  </tr>
                )
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-xs p-4 text-center" style={{ color: MUTED }}>
                    No results match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* RIGHT pane — detail */}
        <div className="overflow-y-auto" style={{ width: '35%' }}>
          <div className="p-4">
            {selected ? (
              <>
                <h2
                  className="text-xs font-semibold uppercase tracking-widest mb-3"
                  style={{ color: 'white' }}
                >
                  PDF Detail
                </h2>

                <DetailRow label="Filename" value={selected.filename} />
                <DetailRow label="Domain" value={selected.domain} />
                <DetailRow label="Pages" value={String(selected.pages)} />
                <DetailRow label="Strategy" value={selected.strategy} />
                <DetailRow
                  label="Status"
                  value={selected.status}
                  valueColor={STATUS_COLOR[selected.status]}
                />
                <DetailRow label="Time" value={`${selected.time_ms.toLocaleString()} ms`} />

                <div style={{ height: 1, backgroundColor: NVIS.border, margin: '12px 0' }} />

                <h3
                  className="text-xs font-semibold uppercase tracking-widest mb-2"
                  style={{ color: 'white' }}
                >
                  Extraction Counts
                </h3>
                <DetailRow label="Blocks" value={String(selected.blocks)} valueColor={NVIS.accent} />
                <DetailRow label="Sections" value={String(selected.sections)} valueColor={NVIS.accent} />
                <DetailRow label="Tables" value={String(selected.tables)} valueColor={NVIS.accent} />
                <DetailRow label="Figures" value={String(selected.figures)} valueColor={NVIS.accent} />

                <div style={{ height: 1, backgroundColor: NVIS.border, margin: '12px 0' }} />

                <h3
                  className="text-xs font-semibold uppercase tracking-widest mb-2"
                  style={{ color: 'white' }}
                >
                  Cascade Summary
                </h3>
                <DetailRow label="Decision" value={selected.strategy !== 'unknown' ? 'pdf-strategy' : 'n/a'} />
                <DetailRow
                  label="Outcome"
                  value={selected.status === 'success' ? 'Extraction complete' : selected.status === 'timeout' ? 'Timed out (60s limit)' : 'Extraction failed'}
                  valueColor={STATUS_COLOR[selected.status]}
                />

                {/* Taxonomy tags */}
                {selected.taxonomy_tags && selected.taxonomy_tags.length > 0 && (
                  <>
                    <div style={{ height: 1, backgroundColor: NVIS.border, margin: '12px 0' }} />
                    <h3
                      className="text-xs font-semibold uppercase tracking-widest mb-2"
                      style={{ color: 'white' }}
                    >
                      Taxonomy Tags
                    </h3>
                    <TaxonomyChipList tags={selected.taxonomy_tags} />
                  </>
                )}
              </>
            ) : (
              <div
                className="flex items-center justify-center"
                style={{ height: '100%', minHeight: 200, color: MUTED }}
              >
                <span className="text-xs">No PDF selected</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------- small presentational helpers ----------

function StatRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex justify-between items-center mb-2">
      <span className="text-xs" style={{ color: MUTED }}>{label}</span>
      <span className="text-xs font-semibold" style={{ color }}>{value}</span>
    </div>
  )
}

function DetailRow({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div className="flex justify-between items-baseline mb-1">
      <span className="text-xs" style={{ color: MUTED }}>{label}</span>
      <span className="text-xs font-medium" style={{ color: valueColor ?? 'white' }}>{value}</span>
    </div>
  )
}
