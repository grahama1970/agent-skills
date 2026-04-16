import { useState, useEffect, useMemo, lazy, Suspense } from 'react'
import { BarChart, Bar, Cell, ResponsiveContainer } from 'recharts'
import { listDocuments, recallDocuments } from '../api/client'
import { NVIS } from '../theme'

const ExtractionReviewModal = lazy(() => import('../components/ExtractionReviewModal'))

interface CollectionRow {
  name: string
  label: string
  total: number
  error: string | null
}

interface ManifestEntry {
  filename: string
  original_path: string
  path?: string
  category: string
  page_count: number
  file_size_mb: number
  quality_signal: string
  s00_preset: string
  s00_estimated_sections: number
  s04_actual_sections?: number
  s00_s04_ratio?: number
  s00_s04_label?: string
  duration_sec: number
  status: string
  debug_patterns: string[]
  lessons_stored: boolean
  error?: string
  results_dir?: string
  processing_started?: string
  processing_finished?: string
}

interface ScoreBucket { range: string; count: number; color: string }
type Severity = 'fail' | 'warn' | 'pass' | 'retry'
type SortKey = 'filename' | 'category' | 'page_count' | 'status' | 'quality_signal' | 'duration_sec' | 's00_s04_ratio' | 'reason'
type SortDir = 'asc' | 'desc'
const COLLECTIONS = [
  { name: 'lessons', label: 'Lessons' },
  { name: 'sparta_controls', label: 'Controls' },
  { name: 'sparta_qra', label: 'QRAs' },
  { name: 'sparta_relationships', label: 'Relationships' },
  { name: 'sparta_urls', label: 'URLs' },
  { name: 'sparta_url_knowledge', label: 'URL Knowledge' },
]

function cleanError(raw: string): string {
  const joined = raw.split('\n').filter((l) => !l.includes('ryptographyDeprecation') && !l.includes('from cryptography')).join(' ').trim()
  const m = joined.match(/ERROR\s+\|\s+.*?\|\s+(.+)/)
  return (m ? m[1].trim() : joined).slice(0, 200)
}

function failureReasons(e: ManifestEntry): string[] {
  const r: string[] = []
  if (e.error) {
    const c = cleanError(e.error)
    if (c.includes('Timeout')) r.push(`Timeout (${e.duration_sec}s on ${e.page_count}p)`)
    else if (c.includes('preflight failed')) r.push('SciLLM rate limited (429)')
    else if (c.includes('429')) r.push('Rate limited (429)')
    else r.push(c.slice(0, 80))
  } else if (e.status === 'failed' || e.status === 'error') r.push('Extraction failed (no error captured)')
  else if (e.status === 'timeout') r.push(`Timeout (${e.duration_sec}s)`)
  if (e.debug_patterns?.length > 0) for (const p of e.debug_patterns) r.push(p.replace(/_/g, ' '))
  if (e.quality_signal === 'REVIEW_REQUIRED' && !r.length) r.push('Review required')
  if (e.s00_s04_label && !e.debug_patterns?.some((p) => p.includes('estimate'))) {
    const est = e.s00_estimated_sections ?? 0, act = e.s04_actual_sections ?? 0
    if (e.s00_s04_label === 'S00_OVERESTIMATE') r.push(`S00 overestimated: predicted ${est}, got ${act}`)
    else if (e.s00_s04_label === 'S00_UNDERESTIMATE') r.push(`S00 underestimated: predicted ${est}, got ${act}`)
  }
  return r
}
function failureReason(e: ManifestEntry): string { return failureReasons(e).join(' · ') }
function isRetryable(e: ManifestEntry): boolean {
  if (!e.error) return false
  const err = e.error.toLowerCase()
  return err.includes('timeout') || err.includes('429') || err.includes('preflight failed') || err.includes('rate limit') || err.includes('502')
}function severityOf(e: ManifestEntry): Severity {
  if (e.status !== 'completed' && isRetryable(e)) return 'retry'
  if (e.status === 'failed' || e.status === 'error' || e.status === 'timeout') return 'fail'
  if (e.quality_signal === 'REVIEW_REQUIRED' || (e.debug_patterns?.length > 0)) return 'warn'
  return 'pass'
}
function severityColor(s: Severity): string {
  if (s === 'fail') return NVIS.red
  if (s === 'warn') return NVIS.amber
  if (s === 'retry') return '#666' // dim — not Nico's problem
  return NVIS.green
}

export default function CorpusView() {
  const [rows, setRows] = useState<CollectionRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [manifest, setManifest] = useState<ManifestEntry[]>([])
  const [scoreBuckets, setScoreBuckets] = useState<ScoreBucket[]>([])
  const [avgGrounding, setAvgGrounding] = useState(0)

  // Filters
  const [severityFilter, setSeverityFilter] = useState<Set<Severity>>(new Set(['fail', 'warn']))
  const [sectorFilter, setSectorFilter] = useState<Set<string>>(new Set())

  // Sort
  const [sortKey, setSortKey] = useState<SortKey>('status')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  // Detail pane
  const [selected, setSelected] = useState<ManifestEntry | null>(null)

  // Collection drill-down
  const [expandedCollection, setExpandedCollection] = useState<string | null>(null)
  const [collectionDocs, setCollectionDocs] = useState<Record<string, unknown>[]>([])
  const [collectionLoading, setCollectionLoading] = useState(false)
  const [collectionPage, setCollectionPage] = useState(0)
  const [reviewEntry, setReviewEntry] = useState<ManifestEntry | null>(null)

  useEffect(() => {
    async function fetchAll() {
      const results = await Promise.allSettled(
        COLLECTIONS.map(async (col) => {
          const result = await listDocuments(col.name, 1)
          return { name: col.name, label: col.label, total: result.total ?? 0, error: null } satisfies CollectionRow
        }),
      )
      setRows(results.map((r, i) =>
        r.status === 'fulfilled' ? r.value : { name: COLLECTIONS[i].name, label: COLLECTIONS[i].label, total: 0, error: String(r.reason) }
      ))

      try {
        const qraResult = await listDocuments('sparta_qra', 200)
        let totalScored = 0, sumGrounding = 0
        const nicoB = { fail: 0, warn: 0, needsHelp: 0, pass: 0 }
        for (const doc of qraResult.documents) {
          const d = doc as unknown as Record<string, unknown>
          const gs = d.grounding_score as number | undefined
          if (gs !== undefined && gs !== null) {
            sumGrounding += gs; totalScored++
            if (gs >= 0.82) nicoB.pass++
            else if (gs >= 0.70) nicoB.needsHelp++
            else if (gs >= 0.60) nicoB.warn++
            else nicoB.fail++
          }
        }
        if (totalScored > 0) {
          setAvgGrounding(sumGrounding / totalScored)
          setScoreBuckets([
            { range: 'Fail', count: nicoB.fail, color: '#ff4444' },
            { range: 'Warn', count: nicoB.warn, color: '#ff4444' },
            { range: 'Help', count: nicoB.needsHelp, color: '#ffaa00' },
            { range: 'Pass', count: nicoB.pass, color: '#00ff88' },
          ])
        }
      } catch { /* optional */ }

      try {
        const res = await fetch('/manifest.jsonl')
        if (res.ok) {
          const text = await res.text()
          const entries: ManifestEntry[] = text.trim().split('\n')
            .map((line) => { try { return JSON.parse(line) } catch { return null } })
            .filter((e): e is ManifestEntry => e !== null)
            .map((e) => {
              // Derive filename from path if missing
              if (!e.filename && (e.original_path || e.path)) {
                const p = e.original_path || e.path || ''
                e.filename = p.split('/').pop() ?? ''
              }
              return e
            })
          setManifest(entries)
        }
      } catch { /* optional */ }

      setLoading(false)
    }
    fetchAll().catch((e) => { setError(e instanceof Error ? e.message : 'Load failed'); setLoading(false) })
  }, [])

  async function loadCollectionDocs(name: string, page: number) {
    setCollectionLoading(true)
    try {
      const result = await listDocuments(name, 20, page * 20)
      setCollectionDocs(result.documents as unknown as Record<string, unknown>[])
    } catch { setCollectionDocs([]) }
    setCollectionLoading(false)
  }

  // Computed counts
  const counts = useMemo(() => {
    const c = { fail: 0, warn: 0, pass: 0, retry: 0 }
    for (const e of manifest) c[severityOf(e)]++
    return c
  }, [manifest])

  const allSectors = useMemo(() => [...new Set(manifest.map((e) => e.category))].sort(), [manifest])

  // Filtered + sorted rows
  const tableRows = useMemo(() => {
    let filtered = manifest.filter((e) => severityFilter.has(severityOf(e)))
    if (sectorFilter.size > 0) filtered = filtered.filter((e) => sectorFilter.has(e.category))

    const cmp = (a: ManifestEntry, b: ManifestEntry): number => {
      const dir = sortDir === 'asc' ? 1 : -1
      switch (sortKey) {
        case 'filename': return dir * a.filename.localeCompare(b.filename)
        case 'category': return dir * a.category.localeCompare(b.category)
        case 'page_count': return dir * (a.page_count - b.page_count)
        case 'duration_sec': return dir * (a.duration_sec - b.duration_sec)
        case 'quality_signal': return dir * (a.quality_signal ?? '').localeCompare(b.quality_signal ?? '')
        case 's00_s04_ratio': return dir * ((a.s00_s04_ratio ?? 99) - (b.s00_s04_ratio ?? 99))
        case 'reason': return dir * failureReason(a).localeCompare(failureReason(b))
        case 'status': {
          const order: Record<Severity, number> = { fail: 0, warn: 1, retry: 2, pass: 3 }
          return dir * (order[severityOf(a)] - order[severityOf(b)])
        }
        default: return 0
      }
    }
    return [...filtered].sort(cmp)
  }, [manifest, severityFilter, sectorFilter, sortKey, sortDir])

  const toggleSeverity = (s: Severity) => {
    const next = new Set(severityFilter)
    if (next.has(s)) next.delete(s); else next.add(s)
    setSeverityFilter(next)
  }
  const toggleSector = (s: string) => {
    const next = new Set(sectorFilter)
    if (next.has(s)) next.delete(s); else next.add(s)
    setSectorFilter(next)
  }
  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  const totalDocs = rows.reduce((s, r) => s + r.total, 0)

  if (loading) return <div style={{ padding: 24, color: NVIS.dim }}>Loading corpus data...</div>

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', fontFamily: "'JetBrains Mono', monospace", color: NVIS.white, overflow: 'hidden' }}>
      {error && <div style={{ padding: '6px 12px', background: '#1a0000', border: `1px solid ${NVIS.red}`, fontSize: 11, color: NVIS.red }}>✗ {error}</div>}

      {/* === TOP STRIP: Aggregate metrics === */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 16px', borderBottom: `1px solid ${NVIS.border}`, flexShrink: 0 }}>
        <span style={{ fontSize: 14, fontWeight: 700 }}>Corpus</span>
        <span style={{ color: NVIS.dim, fontSize: 10 }}>{totalDocs.toLocaleString()} docs · {manifest.length} files</span>
        <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
          <MetricChip label="Fail" count={counts.fail} color={NVIS.red} />
          <MetricChip label="Warn" count={counts.warn} color={NVIS.amber} />
          <MetricChip label="Pass" count={counts.pass} color={NVIS.green} />
          {counts.retry > 0 && <MetricChip label="Auto-retry" count={counts.retry} color="#666" />}
        </div>
        <div style={{ flex: 1 }} />
        {avgGrounding > 0 && <span style={{ fontSize: 10, color: avgGrounding >= 0.82 ? NVIS.green : avgGrounding >= 0.70 ? NVIS.amber : NVIS.red }}>
          Grounding: {(avgGrounding * 100).toFixed(1)}%
        </span>}
        {scoreBuckets.length > 0 && (
          <div style={{ width: 100, height: 24 }}>
            <ResponsiveContainer width="100%" height={24}>
              <BarChart data={scoreBuckets} barSize={10}>
                <Bar dataKey="count" radius={[2, 2, 0, 0]}>{scoreBuckets.map((b, i) => <Cell key={i} fill={b.color} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* === FILTER BAR === */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px', borderBottom: `1px solid ${NVIS.border}`, flexShrink: 0, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 9, color: NVIS.dim, textTransform: 'uppercase', marginRight: 4 }}>Severity</span>
        {(['fail', 'warn', 'pass'] as Severity[]).map((s) => (
          <FilterChip key={s} label={s.toUpperCase()} active={severityFilter.has(s)} color={severityColor(s)} onClick={() => toggleSeverity(s)} />
        ))}
        {counts.retry > 0 && (
          <FilterChip label={`RETRY (${counts.retry})`} active={severityFilter.has('retry')} color="#666" onClick={() => toggleSeverity('retry')} />
        )}
        <span style={{ fontSize: 9, color: NVIS.dim, textTransform: 'uppercase', marginLeft: 12, marginRight: 4 }}>Sector</span>
        {allSectors.map((s) => (
          <FilterChip key={s} label={s} active={sectorFilter.has(s)} color={NVIS.accent} onClick={() => toggleSector(s)} />
        ))}
        {sectorFilter.size > 0 && (
          <span style={{ fontSize: 9, color: NVIS.accent, cursor: 'pointer', marginLeft: 4 }} onClick={() => setSectorFilter(new Set())}>clear</span>
        )}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 9, color: NVIS.dim }}>{tableRows.length} shown</span>
      </div>

      {/* === MAIN: Table + Detail Pane === */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* TABLE */}
        <div style={{ flex: 1, overflow: 'auto', minWidth: 0 }}>
          {/* Table header */}
          <div style={{ display: 'grid', gridTemplateColumns: '280px 55px 45px 65px 55px 45px 1fr', gap: 4, padding: '4px 12px', fontSize: 9, color: NVIS.dim, borderBottom: `1px solid ${NVIS.border}`, position: 'sticky', top: 0, background: '#0f1216', zIndex: 1 }}>
            <SortHeader label="Filename" sortKey="filename" current={sortKey} dir={sortDir} onClick={handleSort} />
            <SortHeader label="Status" sortKey="status" current={sortKey} dir={sortDir} onClick={handleSort} />
            <SortHeader label="Pages" sortKey="page_count" current={sortKey} dir={sortDir} onClick={handleSort} />
            <SortHeader label="Quality" sortKey="quality_signal" current={sortKey} dir={sortDir} onClick={handleSort} />
            <SortHeader label="S00/S04" sortKey="s00_s04_ratio" current={sortKey} dir={sortDir} onClick={handleSort} />
            <SortHeader label="Time" sortKey="duration_sec" current={sortKey} dir={sortDir} onClick={handleSort} />
            <SortHeader label="Reason" sortKey="reason" current={sortKey} dir={sortDir} onClick={handleSort} />
          </div>

          {/* Table rows */}
          {tableRows.map((entry) => {
            const sev = severityOf(entry)
            const isSelected = selected?.filename === entry.filename
            return (
              <div
                key={entry.filename}
                onClick={() => setSelected(entry)}
                style={{
                  display: 'grid', gridTemplateColumns: '280px 55px 45px 65px 55px 45px 1fr', gap: 4,
                  padding: '3px 12px', fontSize: 10, cursor: 'pointer',
                  borderBottom: `1px solid rgba(255,255,255,0.03)`,
                  borderLeft: isSelected ? `3px solid ${NVIS.accent}` : '3px solid transparent',
                  background: isSelected ? 'rgba(74,158,255,0.08)' : sev === 'fail' ? 'rgba(255,68,68,0.04)' : sev === 'warn' ? 'rgba(255,170,0,0.02)' : 'transparent',
                }}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: NVIS.white }}>{entry.filename}</span>
                <span style={{ color: severityColor(sev), fontWeight: 600, fontSize: 9 }}>
                  {sev === 'fail' ? '✗ FAIL' : sev === 'warn' ? '⚠ WARN' : '✓ PASS'}
                </span>
                <span style={{ color: NVIS.dim }}>{entry.page_count}</span>
                <span style={{ color: entry.quality_signal === 'GOOD' ? NVIS.green : entry.quality_signal === 'REASONABLE' ? NVIS.amber : NVIS.red, fontSize: 9 }}>
                  {entry.quality_signal}
                </span>
                <span style={{ color: (entry.s00_s04_ratio ?? 1) < 0.5 || (entry.s00_s04_ratio ?? 1) > 2 ? NVIS.red : NVIS.dim, fontSize: 9 }}>
                  {entry.s00_s04_ratio?.toFixed(2) ?? '—'}
                </span>
                <span style={{ color: entry.duration_sec > 300 ? NVIS.red : NVIS.dim }}>{entry.duration_sec}s</span>
                <span style={{ color: sev === 'fail' ? NVIS.red : sev === 'warn' ? NVIS.amber : NVIS.dim, fontSize: 9, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {failureReason(entry)}
                </span>
              </div>
            )
          })}

          {/* Sectors summary below the table */}
          <div style={{ borderTop: `1px solid ${NVIS.border}`, marginTop: 8 }}>
            <div style={{ padding: '8px 12px', fontSize: 10, fontWeight: 700, color: NVIS.dim }}>
              Knowledge Graph — {totalDocs.toLocaleString()} documents
            </div>
            {rows.map((row) => {
              const isExpanded = expandedCollection === row.name
              return (
                <div key={row.name}>
                  <div
                    onClick={() => {
                      if (isExpanded) { setExpandedCollection(null); setCollectionDocs([]) }
                      else { setExpandedCollection(row.name); setCollectionPage(0); loadCollectionDocs(row.name, 0) }
                    }}
                    style={{
                      display: 'flex', justifyContent: 'space-between', padding: '4px 12px',
                      cursor: 'pointer', fontSize: 10, borderBottom: `1px solid ${NVIS.border}`,
                      background: isExpanded ? 'rgba(74,158,255,0.04)' : 'transparent',
                    }}
                  >
                    <span style={{ color: NVIS.accent }}>{isExpanded ? '▾' : '▸'} {row.label}</span>
                    <span style={{ color: row.error ? NVIS.red : NVIS.dim }}>
                      {row.error ? `✗ ${row.error}` : row.total.toLocaleString()}
                    </span>
                  </div>
                  {isExpanded && (
                    <div style={{ background: 'rgba(0,0,0,0.15)', padding: '6px 12px 6px 28px' }}>
                      {collectionLoading ? (
                        <div style={{ color: NVIS.dim, fontSize: 10, padding: 4 }}>Loading...</div>
                      ) : collectionDocs.length === 0 ? (
                        <div style={{ color: NVIS.dim, fontSize: 10, padding: 4 }}>No documents</div>
                      ) : (
                        <>
                          {collectionDocs.map((doc, i) => {
                            const key = (doc._key as string) ?? `doc-${i}`
                            return (
                              <div key={key} style={{ padding: '2px 0', fontSize: 10, borderBottom: `1px solid rgba(255,255,255,0.03)` }}>
                                <span style={{ color: NVIS.dim, marginRight: 8, fontSize: 9 }}>{key}</span>
                                {collectionDisplayFields(row.name, doc)}
                              </div>
                            )
                          })}
                          <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 10 }}>
                            {collectionPage > 0 && (
                              <span style={{ color: NVIS.accent, cursor: 'pointer' }} onClick={(ev) => {
                                ev.stopPropagation(); const p = collectionPage - 1; setCollectionPage(p); loadCollectionDocs(row.name, p)
                              }}>← Prev</span>
                            )}
                            <span style={{ color: NVIS.dim }}>Page {collectionPage + 1}</span>
                            {collectionDocs.length >= 20 && (
                              <span style={{ color: NVIS.accent, cursor: 'pointer' }} onClick={(ev) => {
                                ev.stopPropagation(); const p = collectionPage + 1; setCollectionPage(p); loadCollectionDocs(row.name, p)
                              }}>Next →</span>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* DETAIL PANE */}
        {selected && <DetailPane entry={selected} onClose={() => setSelected(null)} onReview={(e) => setReviewEntry(e)} />}
      </div>

      {/* EXTRACTION REVIEW MODAL */}
      {reviewEntry && (
        <Suspense fallback={<div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: NVIS.dim, zIndex: 1000 }}>Loading viewer...</div>}>
        <ExtractionReviewModal
          filename={reviewEntry.filename}
          originalPath={reviewEntry.original_path}
          resultsDir={reviewEntry.results_dir}
          pageCount={reviewEntry.page_count}
          reasons={failureReasons(reviewEntry)}
          debugPatterns={reviewEntry.debug_patterns ?? []}
          s00Estimated={reviewEntry.s00_estimated_sections ?? 0}
          s04Actual={reviewEntry.s04_actual_sections ?? 0}
          onClose={() => setReviewEntry(null)}
          onAccept={() => setReviewEntry(null)}
        />
        </Suspense>
      )}
    </div>
  )
}

type FixtureStatus = 'generated' | 'pending' | 'none'

interface PatternInfo {
  count: number
  files: string[]
  first_seen: string
  has_fixture: boolean
  fixture_status: FixtureStatus
  convergence_score: number | null
  convergence_rounds: number | null
  fix_applied_count: number | null
  fix_pending_review: boolean
}

function DetailPane({ entry, onClose, onReview }: { entry: ManifestEntry; onClose: () => void; onReview: (e: ManifestEntry) => void }) {
  const [evidence, setEvidence] = useState<{ key: string; problem: string; scope?: string }[]>([])
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [paneError, setPaneError] = useState<string | null>(null)
  const [patternDiag, setPatternDiag] = useState<Record<string, PatternInfo>>({})

  // Load pattern registry + fix registry for diagnosis with fixture status
  useEffect(() => {
    const patternP = fetch('/pattern_registry.json').then((r) => r.ok ? r.json() : null).catch(() => null)
    const fixP = fetch('/corpus-metadata/fix_registry.json').then((r) => r.ok ? r.json() : null).catch(() => null)
    Promise.all([patternP, fixP]).then(([patData, fixData]) => {
      if (!patData?.patterns) return
      const fixes: Record<string, { fixture_status: FixtureStatus; convergence_score: number | null; convergence_rounds: number | null; fix_applied_count: number | null; fix_pending_review: boolean }> = {}
      if (fixData?.patterns) {
        for (const [key, val] of Object.entries(fixData.patterns) as [string, Record<string, unknown>][]) {
          fixes[key] = {
            fixture_status: (val.fixture_generated ? 'generated' : val.fixture_pending ? 'pending' : 'none') as FixtureStatus,
            convergence_score: (val.convergence_score as number) ?? null,
            convergence_rounds: (val.convergence_rounds as number) ?? null,
            fix_applied_count: (val.fix_applied_count as number) ?? null,
            fix_pending_review: (val.fix_pending_review as boolean) ?? false,
          }
        }
      }
      const diag: Record<string, PatternInfo> = {}
      const addPattern = (pat: string) => {
        const p = patData.patterns[pat]
        if (!p || diag[pat]) return
        const fix = fixes[pat]
        diag[pat] = {
          count: p.count,
          files: p.files ?? [],
          first_seen: p.first_seen ?? '',
          has_fixture: fix?.fixture_status === 'generated',
          fixture_status: fix?.fixture_status ?? 'none',
          convergence_score: fix?.convergence_score ?? null,
          convergence_rounds: fix?.convergence_rounds ?? null,
          fix_applied_count: fix?.fix_applied_count ?? null,
          fix_pending_review: fix?.fix_pending_review ?? false,
        }
      }
      for (const pat of (entry.debug_patterns ?? [])) addPattern(pat)
      if (entry.s00_s04_label) addPattern(entry.s00_s04_label.toLowerCase())
      setPatternDiag(diag)
    })
  }, [entry.filename, entry.debug_patterns, entry.s00_s04_label])

  if (paneError) {
    return (
      <div style={{ width: 380, flexShrink: 0, borderLeft: `1px solid ${NVIS.border}`, padding: 12, background: NVIS.surface }}>
        <div style={{ color: NVIS.red, fontSize: 10 }}>Error: {paneError}</div>
        <span onClick={onClose} style={{ color: NVIS.dim, fontSize: 10, cursor: 'pointer' }}>Close</span>
      </div>
    )
  }

  // Fetch related lessons from /memory when entry changes
  useEffect(() => {
    setEvidence([])
    setEvidenceLoading(true)
    const basename = entry.filename.replace(/\.[^.]+$/, '')
    recallDocuments(basename)
      .then((result) => {
        const items = (result.results ?? []).slice(0, 8).map((r: Record<string, unknown>) => ({
          key: (r.key as string) ?? '',
          problem: ((r.metadata as Record<string, unknown>)?.problem as string) ?? (r.content as string) ?? '',
          scope: ((r.metadata as Record<string, unknown>)?.scope as string) ?? undefined,
        }))
        setEvidence(items)
      })
      .catch((err) => { setEvidence([]); setPaneError(err instanceof Error ? err.message : String(err)) })
      .finally(() => setEvidenceLoading(false))
  }, [entry.filename])

  const sev = severityOf(entry)
  const reasons = failureReasons(entry)
  const est = entry.s00_estimated_sections ?? 0
  const actual = entry.s04_actual_sections ?? 0
  const maxSections = Math.max(est, actual, 1)

  return (
    <div style={{ width: 380, flexShrink: 0, borderLeft: `1px solid ${NVIS.border}`, overflow: 'auto', padding: 12, background: NVIS.surface }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.filename}</span>
        <span style={{ fontSize: 10, color: NVIS.dim, cursor: 'pointer', flexShrink: 0, marginLeft: 8 }} onClick={onClose}>✕</span>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 3, color: '#0f1216', background: severityColor(sev) }}>
          {sev.toUpperCase()}
        </span>
        <span
          onClick={() => onReview(entry)}
          style={{ fontSize: 9, color: NVIS.accent, padding: '2px 8px', border: `1px solid ${NVIS.accent}`, borderRadius: 3, cursor: 'pointer' }}>
          Review Extraction
        </span>
        {sev === 'retry' && (
          <span style={{ fontSize: 9, color: '#888', padding: '2px 8px', border: '1px solid #444', borderRadius: 3 }}>
            Queued for auto-retry
          </span>
        )}
        {sev === 'warn' && (
          <span style={{ fontSize: 9, color: NVIS.green, padding: '2px 8px', border: `1px solid ${NVIS.green}`, borderRadius: 3, cursor: 'pointer' }}>
            Accept as-is
          </span>
        )}
      </div>

      {/* Failure reasons */}
      {reasons.length > 0 && (
        <div style={{ padding: '6px 8px', background: sev === 'retry' ? 'rgba(100,100,100,0.08)' : 'rgba(255,68,68,0.08)', border: `1px solid ${sev === 'retry' ? 'rgba(100,100,100,0.2)' : 'rgba(255,68,68,0.2)'}`, borderRadius: 3, marginBottom: 10 }}>
          {reasons.map((r, i) => (
            <div key={i} style={{ fontSize: 10, color: sev === 'retry' ? '#888' : NVIS.red, fontWeight: 600, padding: '1px 0' }}>
              {r}
            </div>
          ))}
        </div>
      )}

      {/* Prediction vs Actual */}
      {(est > 0 || actual > 0) && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 9, color: NVIS.dim, textTransform: 'uppercase', marginBottom: 4 }}>Prediction vs Actual</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {[{ label: 'S00 predicted', val: est, color: NVIS.accent }, { label: 'S04 actual', val: actual, color: actual > 0 ? NVIS.green : NVIS.red }].map(({ label, val, color }) => (
              <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 9, color: NVIS.dim, width: 70 }}>{label}</span>
                <div style={{ flex: 1, height: 10, background: '#1a1a1a', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ width: `${(val / maxSections) * 100}%`, height: '100%', background: color, borderRadius: 2 }} />
                </div>
                <span style={{ fontSize: 10, fontWeight: 600, width: 30, textAlign: 'right' }}>{val || '\u2014'}</span>
              </div>
            ))}
            {est > 0 && actual > 0 && (() => {
              const r = entry.s00_s04_ratio ?? 1
              const lbl = r < 0.5 ? 'S00 severely overestimated' : r > 2 ? 'S00 severely underestimated' : r < 0.8 ? 'S00 overestimated' : r > 1.2 ? 'S00 underestimated' : 'Good match'
              return <div style={{ fontSize: 9, color: r < 0.5 || r > 2 ? NVIS.red : NVIS.dim, marginTop: 2 }}>Ratio: {r.toFixed(2)} — {lbl}</div>
            })()}
          </div>
        </div>
      )}

      {/* pdf-lab diagnosis — pattern matching + fixture status */}
      {Object.keys(patternDiag).length > 0 && (
        <div style={{ marginBottom: 10, padding: '6px 8px', background: 'rgba(74,158,255,0.06)', border: `1px solid rgba(74,158,255,0.2)`, borderRadius: 3 }}>
          <div style={{ fontSize: 9, color: NVIS.accent, textTransform: 'uppercase', marginBottom: 4, fontWeight: 600 }}>
            /pdf-lab Diagnosis
          </div>
          {Object.entries(patternDiag).map(([pat, info]) => (
            <div key={pat} style={{ marginBottom: 6, padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                <span style={{ fontSize: 10, color: NVIS.amber, fontWeight: 600 }}>{pat.replace(/_/g, ' ')}</span>
                <span style={{ color: NVIS.dim, fontSize: 9 }}>{info.count} files</span>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, alignItems: 'center' }}>
                <FixtureBadge status={info.fixture_status} />
                {info.convergence_score !== null ? (() => {
                  const c = info.convergence_score >= 0.9 ? NVIS.green700 : info.convergence_score >= 0.7 ? NVIS.amber700 : NVIS.red600
                  return <span style={{ fontSize: 10, fontFamily: 'monospace', padding: '1px 6px', borderRadius: 3, color: c, background: `${c}15`, border: `1px solid ${c}30` }}>
                    Score: {info.convergence_score.toFixed(2)}{info.convergence_rounds !== null ? ` (${info.convergence_rounds} rounds)` : ''}
                  </span>
                })() : info.fixture_status !== 'none' && <span style={{ fontSize: 9, color: NVIS.dim, fontFamily: 'monospace' }}>Not started</span>}
              </div>
              <div style={{ fontSize: 9, color: NVIS.dim, marginTop: 2, fontFamily: 'monospace' }}>
                {info.fix_applied_count !== null && info.fix_applied_count > 0
                  ? <span style={{ color: NVIS.green700 }}>Applied to {info.fix_applied_count} files</span>
                  : info.fix_pending_review ? <span style={{ color: NVIS.amber700 }}>Pending Nico review</span>
                  : info.fixture_status === 'none' ? <span>No fixture generated</span>
                  : <span>Fix not yet applied</span>}
              </div>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
            <span style={{ fontSize: 9, color: NVIS.accent, padding: '2px 8px', border: `1px solid ${NVIS.accent}`, borderRadius: 3, cursor: 'pointer' }}>
              Generate Fixture
            </span>
            <span style={{ fontSize: 9, color: NVIS.green, padding: '2px 8px', border: `1px solid ${NVIS.green}`, borderRadius: 3, cursor: 'pointer' }}>
              Run Convergence
            </span>
          </div>
        </div>
      )}

      {/* Error output (for infra errors) */}
      {entry.error && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 9, color: NVIS.dim, textTransform: 'uppercase', marginBottom: 3 }}>Error Output</div>
          <div style={{ fontSize: 9, color: '#888', fontFamily: 'monospace', padding: '4px 6px', background: '#0f1216', borderRadius: 3, wordBreak: 'break-all', maxHeight: 60, overflow: 'auto' }}>
            {cleanError(entry.error)}
          </div>
        </div>
      )}

      {/* Metadata */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px', fontSize: 10, marginBottom: 10 }}>
        <span style={{ color: NVIS.dim }}>Sector</span><span>{entry.category}</span>
        <span style={{ color: NVIS.dim }}>Pages</span><span>{entry.page_count}</span>
        <span style={{ color: NVIS.dim }}>Size</span><span>{entry.file_size_mb.toFixed(1)} MB</span>
        <span style={{ color: NVIS.dim }}>Duration</span>
        <span style={{ color: entry.duration_sec > 300 ? NVIS.red : NVIS.white }}>{entry.duration_sec}s</span>
        <span style={{ color: NVIS.dim }}>Status</span>
        <span style={{ color: entry.status === 'completed' ? NVIS.green : NVIS.red }}>{entry.status}</span>
        <span style={{ color: NVIS.dim }}>Quality</span>
        <span style={{ color: entry.quality_signal === 'GOOD' ? NVIS.green : entry.quality_signal === 'REASONABLE' ? NVIS.amber : NVIS.red }}>
          {entry.quality_signal || '—'}
        </span>
        <span style={{ color: NVIS.dim }}>Preset</span><span>{entry.s00_preset ?? '—'}</span>
        <span style={{ color: NVIS.dim }}>Lessons</span>
        <span style={{ color: entry.lessons_stored ? NVIS.green : NVIS.red }}>{entry.lessons_stored ? 'Yes' : 'No'}</span>
      </div>

      {/* Evidence from /memory — what was actually extracted */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 9, color: NVIS.dim, textTransform: 'uppercase', marginBottom: 4 }}>
          Extracted Content (from /memory)
        </div>
        {evidenceLoading ? (
          <div style={{ fontSize: 9, color: NVIS.dim, padding: 4 }}>Searching...</div>
        ) : evidence.length === 0 ? (
          <div style={{ fontSize: 9, color: NVIS.red, padding: 4 }}>No lessons found in /memory for this file</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {evidence.map((e, i) => (
              <div key={i} style={{ fontSize: 9, padding: '3px 6px', background: '#0f1216', borderRadius: 2, borderLeft: `2px solid ${NVIS.accent}` }}>
                <span style={{ color: NVIS.white }}>{e.problem.slice(0, 100)}{e.problem.length > 100 ? '...' : ''}</span>
                {e.scope && <span style={{ color: NVIS.dim, marginLeft: 6 }}>[{e.scope}]</span>}
              </div>
            ))}
            {evidence.length >= 8 && <div style={{ fontSize: 9, color: NVIS.dim }}>... more in /memory</div>}
          </div>
        )}
      </div>

      {/* Path */}
      <div style={{ fontSize: 9, color: NVIS.dim, marginBottom: 3 }}>Path</div>
      <div style={{ fontSize: 8, color: NVIS.dim, fontFamily: 'monospace', padding: '3px 6px', background: '#0f1216', borderRadius: 3, wordBreak: 'break-all' }}>
        {entry.original_path}
      </div>
    </div>
  )
}

const FIXTURE_BADGE_CONFIG: Record<FixtureStatus, { color: string; icon: string; label: string }> = {
  generated: { color: NVIS.green700, icon: '\u2714', label: 'Generated' },
  pending: { color: NVIS.amber700, icon: '\u29D6', label: 'Pending' },
  none: { color: NVIS.red600, icon: '\u2716', label: 'None' },
}

function FixtureBadge({ status }: { status: FixtureStatus }) {
  const cfg = FIXTURE_BADGE_CONFIG[status]
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        fontSize: 10,
        fontFamily: 'monospace',
        padding: '1px 6px',
        borderRadius: 3,
        color: cfg.color,
        backgroundColor: `${cfg.color}15`,
        border: `1px solid ${cfg.color}30`,
      }}
    >
      <span style={{ fontSize: 9 }}>{cfg.icon}</span>
      {cfg.label}
    </span>
  )
}

function MetricChip({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, padding: '1px 8px', borderRadius: 3, background: `${color}18`, border: `1px solid ${color}40` }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
      <span style={{ color }}>{count}</span>
      <span style={{ color: NVIS.dim, fontSize: 9 }}>{label}</span>
    </span>
  )
}

function FilterChip({ label, active, color, onClick }: { label: string; active: boolean; color: string; onClick: () => void }) {
  return (
    <span
      onClick={onClick}
      style={{
        fontSize: 9, cursor: 'pointer', padding: '1px 6px', borderRadius: 2,
        color: active ? '#0f1216' : color,
        background: active ? color : 'transparent',
        border: `1px solid ${active ? color : NVIS.border}`,
        fontWeight: active ? 700 : 400,
      }}
    >
      {label}
    </span>
  )
}

function SortHeader({ label, sortKey: key, current, dir, onClick }: {
  label: string; sortKey: SortKey; current: SortKey; dir: SortDir; onClick: (k: SortKey) => void
}) {
  const isActive = current === key
  return (
    <span
      onClick={() => onClick(key)}
      style={{ cursor: 'pointer', color: isActive ? NVIS.white : NVIS.dim, fontWeight: isActive ? 600 : 400 }}
    >
      {label}{isActive ? (dir === 'asc' ? ' ↑' : ' ↓') : ''}
    </span>
  )
}

function collectionDisplayFields(collection: string, doc: Record<string, unknown>): React.ReactNode {
  const str = (key: string): string => (doc[key] as string) ?? ''
  const num = (key: string): number | undefined => doc[key] as number | undefined

  switch (collection) {
    case 'sparta_controls': {
      const desc = str('description')
      const isPlaceholder = !desc || desc.toLowerCase().includes('placeholder') || desc.toLowerCase().includes('{{ insert')
      return <span>
        <span style={{ color: NVIS.amber, fontSize: 9, marginRight: 6 }}>{str('source_framework')}</span>
        <span style={{ color: NVIS.accent }}>{str('control_id')}</span>
        <span style={{ color: NVIS.white, marginLeft: 8 }}>{str('name').slice(0, 50)}</span>
        {isPlaceholder
          ? <span style={{ color: '#0f1216', background: NVIS.amber, fontSize: 8, padding: '0 4px', borderRadius: 2, marginLeft: 8, fontWeight: 700 }}>PLACEHOLDER</span>
          : <span style={{ color: NVIS.dim, marginLeft: 8, fontSize: 9 }}>{desc.slice(0, 60)}{desc.length > 60 ? '...' : ''}</span>
        }
      </span>
    }
    case 'sparta_qra': {
      const gs = num('grounding_score')
      const gsColor = gs !== undefined ? (gs >= 0.82 ? NVIS.green : gs >= 0.70 ? NVIS.amber : NVIS.red) : NVIS.dim
      return <span>
        {gs !== undefined && <span style={{ color: gsColor, marginRight: 8 }}>{(gs * 100).toFixed(0)}%</span>}
        <span style={{ color: NVIS.white }}>{(str('question') || str('problem')).slice(0, 80)}</span>
        {str('evidence_grade') && <span style={{ color: NVIS.dim, marginLeft: 8, fontSize: 9 }}>Grade {str('evidence_grade')}</span>}
      </span>
    }
    case 'sparta_relationships':
      return <span><span style={{ color: NVIS.accent }}>{str('source_control_id')}</span><span style={{ color: NVIS.dim, margin: '0 6px' }}>{'\u2192'}</span><span style={{ color: NVIS.green }}>{str('target_control_id')}</span>{num('combined_score') !== undefined && <span style={{ color: NVIS.dim, marginLeft: 8, fontSize: 9 }}>score: {num('combined_score')!.toFixed(2)}</span>}</span>
    case 'sparta_urls':
      return <span><span style={{ color: NVIS.accent }}>{str('url').slice(0, 80)}</span>{str('domain') && <span style={{ color: NVIS.dim, marginLeft: 8, fontSize: 9 }}>{str('domain')}</span>}</span>
    case 'sparta_url_knowledge':
      return <span><span style={{ color: NVIS.white }}>{str('topic').slice(0, 60)}</span>{str('control_id') && <span style={{ color: NVIS.accent, marginLeft: 8, fontSize: 9 }}>{str('control_id')}</span>}{str('source_framework') && <span style={{ color: NVIS.amber, marginLeft: 8, fontSize: 9 }}>{str('source_framework')}</span>}</span>
    case 'lessons':
      return <span><span style={{ color: NVIS.white }}>{str('problem').slice(0, 80)}</span>{str('scope') && <span style={{ color: NVIS.dim, marginLeft: 8, fontSize: 9 }}>{str('scope')}</span>}</span>
    default:
      return <span style={{ color: NVIS.dim }}>{JSON.stringify(doc).slice(0, 100)}</span>
  }
}
