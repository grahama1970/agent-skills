import { useState, useEffect, useMemo } from 'react'
import { NVIS } from '../theme'
import { listDocuments, storeDocument } from '../api/client'
import EvidenceCasePanel from '../components/EvidenceCasePanel'
import type { ThreatCell, ThreatDrillthrough, EvidenceCase } from '../types'

// --- Framework filter ---
type Framework = 'SPARTA' | 'ATT&CK' | 'D3FEND'
const FRAMEWORKS: Framework[] = ['SPARTA', 'ATT&CK', 'D3FEND']
const FRAMEWORK_COLORS: Record<Framework, string> = {
  'SPARTA': '#4a9eff',
  'ATT&CK': '#ff6b6b',
  'D3FEND': '#00ff88',
}

const STATUS_COLORS: Record<ThreatCell['status'], string> = {
  gap: '#ff4444',
  partial: '#ffaa00',
  covered: '#00ff88',
}

function cellBg(status: ThreatCell['status'], alpha: number): string {
  const hex = STATUS_COLORS[status]
  const a = Math.round(alpha * 255).toString(16).padStart(2, '0')
  return `${hex}${a}`
}

// --- Sidebar filter component ---
interface FilterSectionProps {
  title: string
  items: string[]
  selected: Set<string>
  onToggle: (item: string) => void
}

function FilterSection({ title, items, selected, onToggle }: FilterSectionProps) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{
        fontSize: 9,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: NVIS.dim,
        marginBottom: 6,
        padding: '0 12px',
      }}>
        {title}
      </div>
      {items.map((item) => {
        const isChecked = selected.has(item)
        return (
          <label
            key={item}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '3px 12px',
              fontSize: 11,
              color: isChecked ? NVIS.white : NVIS.dim,
              cursor: 'pointer',
            }}
          >
            <input
              type="checkbox"
              checked={isChecked}
              onChange={() => onToggle(item)}
              style={{ accentColor: NVIS.accent }}
            />
            {item}
          </label>
        )
      })}
    </div>
  )
}

// --- Drillthrough panel ---
interface DrillthroughPanelProps {
  data: ThreatDrillthrough
  onClose: () => void
  onCreateEvidence: (cell: ThreatCell) => void
}

function DrillthroughPanel({ data, onClose, onCreateEvidence }: DrillthroughPanelProps) {
  const { cell, evidenceCases, relatedControls, spartaMapping } = data
  const [editingCaseId, setEditingCaseId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  function startEdit(ec: EvidenceCase) {
    setEditingCaseId(ec.id)
    setEditText(ec.claim)
  }

  function commitEdit(ec: EvidenceCase) {
    if (editText.trim() && editText !== ec.claim) {
      // V8.9: write shadow label for the correction
      storeDocument(`shadow:requirement:${ec.id}`, {
        type: 'requirement-edit',
        caseId: ec.id,
        controlId: cell.controlId,
        sector: cell.sector,
        originalText: ec.claim,
        correctedText: editText.trim(),
        timestamp: new Date().toISOString(),
      }).catch(() => { /* best-effort shadow write */ })
      ec.claim = editText.trim()
    }
    setEditingCaseId(null)
  }

  function verdictBadge(verdict: EvidenceCase['verdict']) {
    if (verdict === 'supported') return { label: 'Supported', color: NVIS.green }
    if (verdict === 'refuted') return { label: 'Refuted', color: NVIS.red }
    return { label: 'Insufficient', color: NVIS.amber }
  }

  return (
    <div style={{
      width: 320,
      flexShrink: 0,
      background: NVIS.surface,
      borderLeft: `1px solid ${NVIS.borderSolid}`,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 14px',
        borderBottom: `1px solid ${NVIS.borderSolid}`,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: NVIS.white }}>{cell.controlId}</div>
          <div style={{ fontSize: 11, color: NVIS.dim, marginTop: 2 }}>{cell.controlName}</div>
          <div style={{ fontSize: 10, color: NVIS.dim, marginTop: 2 }}>
            Sector: <span style={{ color: NVIS.accent }}>{cell.sector}</span>
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Close drillthrough"
          style={{
            background: 'none',
            border: 'none',
            color: NVIS.dim,
            fontSize: 16,
            cursor: 'pointer',
            padding: '2px 6px',
            fontFamily: 'monospace',
          }}
        >
          X
        </button>
      </div>

      {/* Coverage summary */}
      <div style={{ padding: '10px 14px', borderBottom: `1px solid ${NVIS.borderSolid}`, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <span style={{
            fontSize: 10,
            fontWeight: 600,
            padding: '2px 8px',
            borderRadius: 3,
            background: `${STATUS_COLORS[cell.status]}1a`,
            border: `1px solid ${STATUS_COLORS[cell.status]}40`,
            color: STATUS_COLORS[cell.status],
            textTransform: 'uppercase',
          }}>
            {cell.status}
          </span>
          <span style={{ fontSize: 11, color: NVIS.dim }}>
            {Math.round(cell.coverageScore * 100)}% coverage
          </span>
        </div>
        <div style={{ fontSize: 10, color: NVIS.dim }}>
          {cell.evidenceCount} evidence item{cell.evidenceCount !== 1 ? 's' : ''}
        </div>
        {spartaMapping && (
          <div style={{ fontSize: 10, color: NVIS.dim, marginTop: 2 }}>
            SPARTA: <span style={{ color: NVIS.cyan }}>{spartaMapping}</span>
          </div>
        )}
      </div>

      {/* Evidence cases */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '10px 14px' }}>
        <div style={{
          fontSize: 9,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: NVIS.dim,
          marginBottom: 8,
        }}>
          Evidence Cases ({evidenceCases.length})
        </div>
        {evidenceCases.map((ec) => {
          const badge = verdictBadge(ec.verdict)
          return (
            <div
              key={ec.id}
              style={{
                padding: '8px 10px',
                marginBottom: 8,
                background: NVIS.surface2,
                borderRadius: 4,
                border: `1px solid ${NVIS.borderSolid}`,
              }}
            >
              {editingCaseId === ec.id ? (
                <input
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onBlur={() => commitEdit(ec)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitEdit(ec)
                    if (e.key === 'Escape') setEditingCaseId(null)
                  }}
                  autoFocus
                  style={{
                    width: '100%',
                    fontSize: 11,
                    color: NVIS.white,
                    background: NVIS.bg,
                    border: `1px solid ${NVIS.accent}`,
                    borderRadius: 3,
                    padding: '4px 6px',
                    marginBottom: 4,
                    fontFamily: 'monospace',
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
              ) : (
                <div
                  style={{ fontSize: 11, color: NVIS.white, marginBottom: 4, lineHeight: 1.4, cursor: 'pointer' }}
                  onClick={() => startEdit(ec)}
                  title="Click to edit"
                >
                  {ec.claim}
                </div>
              )}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{
                  fontSize: 9,
                  padding: '1px 6px',
                  borderRadius: 3,
                  background: `${badge.color}1a`,
                  color: badge.color,
                  fontWeight: 600,
                }}>
                  {badge.label}
                </span>
                <span style={{ fontSize: 9, color: NVIS.dim }}>
                  {Math.round(ec.confidence * 100)}%
                </span>
              </div>
              <div style={{ fontSize: 9, color: NVIS.dim }}>
                {ec.sources.join(' | ')}
              </div>
            </div>
          )
        })}

        {/* Related controls */}
        {relatedControls.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{
              fontSize: 9,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: NVIS.dim,
              marginBottom: 6,
            }}>
              Related Controls
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {relatedControls.map((rc) => (
                <span
                  key={rc}
                  style={{
                    fontSize: 10,
                    padding: '2px 8px',
                    borderRadius: 3,
                    background: `${NVIS.accent}1a`,
                    color: NVIS.accent,
                    border: `1px solid ${NVIS.accent}30`,
                  }}
                >
                  {rc}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        padding: '10px 14px',
        borderTop: `1px solid ${NVIS.borderSolid}`,
        flexShrink: 0,
      }}>
        <button
          onClick={() => onCreateEvidence(cell)}
          style={{
            width: '100%',
            padding: '8px 12px',
            fontSize: 11,
            fontWeight: 600,
            fontFamily: 'monospace',
            background: NVIS.accent,
            border: 'none',
            borderRadius: 4,
            color: '#000',
            cursor: 'pointer',
          }}
        >
          Create Evidence Case
        </button>
      </div>
    </div>
  )
}

// --- Main view ---
export default function ThreatMatrixView() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [coverageInfo, setCoverageInfo] = useState<string | null>(null)
  const [selectedSectors, setSelectedSectors] = useState<Set<string>>(new Set())
  const [selectedFamilies, setSelectedFamilies] = useState<Set<string>>(new Set())
  const [selectedCell, setSelectedCell] = useState<ThreatCell | null>(null)
  const [evidencePanelOpen, setEvidencePanelOpen] = useState(false)
  const [evidencePrefill, setEvidencePrefill] = useState<{ controlId?: string; claim?: string; sources?: string[] }>({})
  const [mode, setMode] = useState<'documents' | 'verified'>('documents')
  const [activeFrameworks, setActiveFrameworks] = useState<Set<Framework>>(new Set(FRAMEWORKS))

  const toggleFramework = (fw: Framework) => {
    setActiveFrameworks((prev) => {
      const next = new Set(prev)
      if (next.has(fw)) { if (next.size > 1) next.delete(fw) } else next.add(fw)
      return next
    })
  }

  // Real data from ArangoDB
  const [cells, setCells] = useState<ThreatCell[]>([])
  const [controlFamilies, setControlFamilies] = useState<string[]>([])
  const [controlNameMap, setControlNameMap] = useState<Record<string, string>>({})
  const [controlFrameworkMap, setControlFrameworkMap] = useState<Record<string, Framework[]>>({})

  useEffect(() => {
    async function fetchFromDatalake() {
      try {
        // Fetch controls and relationships from ArangoDB
        const [controlsResult, relsResult] = await Promise.all([
          listDocuments('sparta_controls', 200),
          listDocuments('sparta_relationships', 500),
        ])

        // Build control name map and framework map from real data
        const nameMap: Record<string, string> = {}
        const fwMap: Record<string, Framework[]> = {}
        const families = new Set<string>()

        for (const doc of controlsResult.documents) {
          const d = doc as unknown as Record<string, unknown>
          const cid = (d.control_id as string) ?? ''
          const name = (d.name as string) ?? cid
          const fw = (d.source_framework as string) ?? 'NIST'
          nameMap[cid] = name
          const family = cid.split('-')[0].split('.')[0]
          if (family) families.add(family)
          // Map source_framework to our Framework type
          const normalizedFw = fw.toLowerCase().includes('sparta') ? 'SPARTA'
            : fw.toLowerCase().includes('att') ? 'ATT&CK'
            : fw.toLowerCase().includes('d3f') ? 'D3FEND'
            : 'SPARTA'
          fwMap[cid] = [...(fwMap[cid] ?? []), normalizedFw as Framework]
        }

        setControlNameMap(nameMap)
        setControlFrameworkMap(fwMap)
        setControlFamilies([...families].sort())

        // Build cells from relationships — each relationship is a requirement→control mapping
        // Group by target_control_id to get coverage per control
        const controlCoverage = new Map<string, { scores: number[]; sources: string[] }>()

        for (const doc of relsResult.documents) {
          const d = doc as unknown as Record<string, unknown>
          const targetId = (d.target_control_id as string) ?? ''
          const sourceId = (d.source_control_id as string) ?? ''
          const score = (d.combined_score as number) ?? 0

          if (!targetId) continue
          const entry = controlCoverage.get(targetId) ?? { scores: [], sources: [] }
          entry.scores.push(score)
          entry.sources.push(sourceId)
          controlCoverage.set(targetId, entry)
        }

        // Build cells — one per control that has any relationships
        const newCells: ThreatCell[] = []
        for (const [controlId, { scores, sources }] of controlCoverage) {
          const avgScore = scores.reduce((a, b) => a + b, 0) / scores.length
          const maxScore = Math.max(...scores)
          const status: ThreatCell['status'] = maxScore >= 0.5 ? 'covered'
            : maxScore >= 0.1 ? 'partial'
            : 'gap'

          // Use source_control_id prefix as "sector" (REC-* groups)
          const sectorPrefix = sources[0]?.split('-')[0] ?? 'REC'

          newCells.push({
            controlId,
            controlName: nameMap[controlId] ?? controlId,
            sector: sectorPrefix,
            coverageScore: Math.round(avgScore * 1000) / 1000,
            evidenceCount: sources.length,
            status,
          })
        }

        setCells(newCells)
        setCoverageInfo(`${controlsResult.total?.toLocaleString() ?? '?'} controls, ${relsResult.total?.toLocaleString() ?? '?'} relationships from /memory`)
        setLoading(false)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Memory service unreachable')
        setLoading(false)
      }
    }
    fetchFromDatalake()
  }, [])

  const toggleSector = (s: string) => {
    setSelectedSectors((prev) => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s); else next.add(s)
      return next
    })
  }

  const toggleFamily = (f: string) => {
    setSelectedFamilies((prev) => {
      const next = new Set(prev)
      if (next.has(f)) next.delete(f); else next.add(f)
      return next
    })
  }

  // Derive unique sectors from real data
  const sectors = useMemo(() => [...new Set(cells.map((c) => c.sector))].sort(), [cells])

  // Initialize selected sets from real data on first load
  useEffect(() => {
    if (sectors.length > 0 && selectedSectors.size === 0) setSelectedSectors(new Set(sectors))
  }, [sectors, selectedSectors.size])
  useEffect(() => {
    if (controlFamilies.length > 0 && selectedFamilies.size === 0) setSelectedFamilies(new Set(controlFamilies))
  }, [controlFamilies, selectedFamilies.size])

  // Derive unique controls and sectors from filtered cells
  const filteredCells = useMemo(() => {
    return cells.filter((c) => {
      const family = c.controlId.split('-')[0].split('.')[0]
      if (!selectedSectors.has(c.sector) || !selectedFamilies.has(family)) return false
      // V8.6: framework filter
      const controlFws = controlFrameworkMap[c.controlId] ?? ['SPARTA']
      if (!controlFws.some((fw) => activeFrameworks.has(fw))) return false
      return true
    })
  }, [selectedSectors, selectedFamilies, activeFrameworks])

  const controlIds = useMemo(() => {
    const ids = [...new Set(filteredCells.map((c) => c.controlId))]
    ids.sort()
    return ids
  }, [filteredCells])

  const activeSectors = useMemo(() => {
    return sectors.filter((s) => selectedSectors.has(s))
  }, [selectedSectors])

  // Build cell lookup
  const cellMap = useMemo(() => {
    const map = new Map<string, ThreatCell>()
    for (const cell of filteredCells) {
      map.set(`${cell.controlId}:${cell.sector}`, cell)
    }
    return map
  }, [filteredCells])

  const handleCellClick = (cell: ThreatCell) => {
    setSelectedCell(cell)
  }

  const handleCreateEvidence = (cell: ThreatCell) => {
    setEvidencePrefill({
      controlId: cell.controlId,
      claim: `${cell.controlName} coverage for ${cell.sector} sector`,
      sources: [],
    })
    setEvidencePanelOpen(true)
  }

  // Drillthrough data synthesized from real relationships
  const drillthroughData: ThreatDrillthrough | null = selectedCell
    ? {
        cell: selectedCell,
        evidenceCases: [],
        relatedControls: controlIds.filter((id) => id !== selectedCell.controlId).slice(0, 5),
        spartaMapping: undefined,
      }
    : null

  // Summary stats
  const totalCells = filteredCells.length
  const gapCount = filteredCells.filter((c) => c.status === 'gap').length
  const partialCount = filteredCells.filter((c) => c.status === 'partial').length
  const coveredCount = filteredCells.filter((c) => c.status === 'covered').length

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#999', fontFamily: 'monospace', fontSize: 13 }}>
        Loading...
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 80px)', minHeight: 0 }}>
      {error && (
        <div style={{ background: '#1a0000', border: '1px solid #ff4444', borderRadius: 4, padding: '8px 12px', margin: '8px 0', color: '#ff4444', fontFamily: 'JetBrains Mono, monospace', fontSize: 12, flexShrink: 0 }}>
          ✗ {error}
        </div>
      )}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      {/* Sidebar */}
      <div style={{
        width: 240,
        flexShrink: 0,
        background: NVIS.surface,
        borderRight: `1px solid ${NVIS.borderSolid}`,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '10px 12px',
          borderBottom: `1px solid ${NVIS.borderSolid}`,
          flexShrink: 0,
        }}>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: NVIS.dim }}>
            Threat Matrix
          </div>
          <div style={{ fontSize: 10, color: NVIS.dim, marginTop: 2 }}>
            SPARTA Coverage Heatmap
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', paddingTop: 8 }}>
          <FilterSection
            title="Sectors"
            items={sectors}
            selected={selectedSectors}
            onToggle={toggleSector}
          />
          <FilterSection
            title="Control Families"
            items={controlFamilies}
            selected={selectedFamilies}
            onToggle={toggleFamily}
          />
        </div>

        {/* Summary */}
        <div style={{
          padding: '10px 12px',
          borderTop: `1px solid ${NVIS.borderSolid}`,
          flexShrink: 0,
          fontSize: 10,
          color: NVIS.dim,
        }}>
          <div style={{ marginBottom: 4 }}>{totalCells} cells visible</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <span style={{ color: '#00ff88' }}>{coveredCount} covered</span>
            <span style={{ color: '#ffaa00' }}>{partialCount} partial</span>
            <span style={{ color: '#ff4444' }}>{gapCount} gap</span>
          </div>
        </div>
      </div>

      {/* Heatmap grid */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        {/* Header bar */}
        <div style={{
          padding: '10px 16px',
          borderBottom: `1px solid ${NVIS.borderSolid}`,
          background: NVIS.surface,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 16,
        }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: NVIS.white }}>Coverage Heatmap</span>

          {/* V8.5: Documents / Verified mode toggle */}
          <div style={{ display: 'flex', gap: 2, background: NVIS.surface2, borderRadius: 4, padding: 2 }}>
            {(['documents', 'verified'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                style={{
                  padding: '3px 10px',
                  fontSize: 10,
                  fontFamily: 'monospace',
                  fontWeight: mode === m ? 600 : 400,
                  border: 'none',
                  borderRadius: 3,
                  cursor: 'pointer',
                  background: mode === m ? `${NVIS.accent}1a` : 'transparent',
                  color: mode === m ? NVIS.accent : NVIS.dim,
                  textTransform: 'capitalize',
                }}
              >
                {m}
              </button>
            ))}
          </div>

          {/* V8.6: Framework filter chips */}
          {FRAMEWORKS.map((fw) => (
            <button
              key={fw}
              onClick={() => toggleFramework(fw)}
              aria-pressed={activeFrameworks.has(fw)}
              style={{
                padding: '3px 10px',
                fontSize: 10,
                fontFamily: 'monospace',
                fontWeight: activeFrameworks.has(fw) ? 600 : 400,
                border: `1px solid ${activeFrameworks.has(fw) ? FRAMEWORK_COLORS[fw] : NVIS.borderSolid}`,
                borderRadius: 12,
                cursor: 'pointer',
                background: activeFrameworks.has(fw) ? `${FRAMEWORK_COLORS[fw]}1a` : 'transparent',
                color: activeFrameworks.has(fw) ? FRAMEWORK_COLORS[fw] : NVIS.dim,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              <span style={{ width: 6, height: 6, borderRadius: 3, background: FRAMEWORK_COLORS[fw], flexShrink: 0 }} />
              {fw}
            </button>
          ))}

          <span style={{ fontSize: 10, color: NVIS.dim }}>
            {controlIds.length} controls x {activeSectors.length} sectors
            {coverageInfo && <> | {coverageInfo}</>}
          </span>
          <div style={{ flex: 1 }} />
          {/* Legend */}
          <div style={{ display: 'flex', gap: 12, fontSize: 9, color: NVIS.dim }}>
            {(['gap', 'partial', 'covered'] as const).map((s) => (
              <span key={s} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: STATUS_COLORS[s], flexShrink: 0 }} />
                {s}
              </span>
            ))}
          </div>
        </div>

        {/* Grid */}
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          <div style={{ minWidth: activeSectors.length * 80 + 120 }}>
            {/* Column headers */}
            <div style={{ display: 'flex', marginBottom: 2 }}>
              <div style={{ width: 120, flexShrink: 0 }} />
              {activeSectors.map((sector) => (
                <div
                  key={sector}
                  style={{
                    width: 80,
                    flexShrink: 0,
                    textAlign: 'center',
                    fontSize: 9,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    color: NVIS.dim,
                    padding: '4px 0',
                  }}
                >
                  {sector}
                </div>
              ))}
            </div>

            {/* Rows */}
            {controlIds.map((controlId) => {
              const controlName = controlNameMap[controlId] ?? controlId
              return (
                <div key={controlId} style={{ display: 'flex', marginBottom: 2 }}>
                  <div
                    style={{
                      width: 120,
                      flexShrink: 0,
                      fontSize: 10,
                      color: NVIS.dim,
                      padding: '6px 8px 6px 0',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={`${controlId}: ${controlName}`}
                  >
                    <span style={{ color: NVIS.accent }}>{controlId}</span>
                    <span style={{ color: NVIS.dim, marginLeft: 4 }}>{controlName}</span>
                  </div>
                  {activeSectors.map((sector) => {
                    const cell = cellMap.get(`${controlId}:${sector}`)
                    if (!cell) {
                      return (
                        <div
                          key={sector}
                          style={{
                            width: 80,
                            height: 32,
                            flexShrink: 0,
                            background: NVIS.surface2,
                            borderRadius: 2,
                            margin: '0 1px',
                          }}
                        />
                      )
                    }
                    const isSelected = selectedCell?.controlId === cell.controlId && selectedCell?.sector === cell.sector
                    return (
                      <button
                        key={sector}
                        onClick={() => handleCellClick(cell)}
                        title={`${cell.controlId} / ${cell.sector}: ${cell.status} (${Math.round(cell.coverageScore * 100)}%)`}
                        style={{
                          width: 80,
                          height: 32,
                          flexShrink: 0,
                          margin: '0 1px',
                          borderRadius: 2,
                          border: isSelected ? `2px solid ${NVIS.accent}` : '2px solid transparent',
                          background: cellBg(cell.status, 0.3 + cell.coverageScore * 0.5),
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontFamily: 'monospace',
                          fontSize: 9,
                          color: NVIS.white,
                          padding: 0,
                        }}
                      >
                        {cell.evidenceCount > 0 && (
                          <span style={{
                            fontSize: 8,
                            padding: '1px 4px',
                            borderRadius: 6,
                            background: 'rgba(0,0,0,0.4)',
                          }}>
                            {mode === 'verified'
                              ? Math.floor(cell.evidenceCount * cell.coverageScore)
                              : cell.evidenceCount}
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Drillthrough panel */}
      {drillthroughData && (
        <DrillthroughPanel
          data={drillthroughData}
          onClose={() => setSelectedCell(null)}
          onCreateEvidence={handleCreateEvidence}
        />
      )}

      {/* Evidence Case Panel */}
      <EvidenceCasePanel
        open={evidencePanelOpen}
        onClose={() => setEvidencePanelOpen(false)}
        prefillContext={evidencePrefill}
      />
      </div>
    </div>
  )
}
