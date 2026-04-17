import { useState, useEffect, useCallback, useRef } from 'react'
import { NVIS } from '../theme'
import { loadSupervisors, loadSupervisor, loadWorkers } from '../loader'
import { recallDocuments } from '../api/client'
import type { SupervisorState, WorkerState } from '../types'

const REFRESH_MS = 15_000

const PHASES = ['discover', 'extract', 'score', 'debug', 'evaluate', 'summary'] as const
type Phase = (typeof PHASES)[number]

// ── helpers ───────────────────────────────────────────────────

function formatSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

function formatTimeAgo(s: number): string {
  if (s < 60) return `${Math.round(s)}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

function failRateColor(pct: number): string {
  if (pct <= 5) return NVIS.green
  if (pct <= 15) return NVIS.amber
  return NVIS.red
}

function heartbeatColor(seconds: number): string {
  if (seconds <= 60) return NVIS.green
  if (seconds <= 300) return NVIS.amber
  return NVIS.red
}

function stalenessColor(seconds: number): string {
  if (seconds <= 30) return NVIS.green
  if (seconds <= 120) return NVIS.amber
  return NVIS.red
}

function workerStatusColor(status: string): string {
  if (status === 'running') return NVIS.green
  if (status === 'error') return NVIS.red
  return NVIS.dim
}

// ── MetricCard ────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  color,
}: {
  label: string
  value: string
  color?: string
}) {
  return (
    <div
      style={{
        background: NVIS.surface,
        border: `1px solid ${NVIS.borderSolid}`,
        borderRadius: 6,
        padding: '16px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <span
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          color: NVIS.dim,
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 16,
          fontWeight: 600,
          fontVariantNumeric: 'tabular-nums',
          color: color ?? NVIS.white,
        }}
      >
        {value}
      </span>
    </div>
  )
}

// ── PhaseProgress ─────────────────────────────────────────────

function PhaseProgress({ currentPhase }: { currentPhase: string }) {
  const currentIdx = PHASES.indexOf(currentPhase as Phase)

  return (
    <div>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          color: NVIS.dim,
          marginBottom: 16,
        }}
      >
        Phase Progress
      </div>
      <div
        style={{
          background: NVIS.surface,
          border: `1px solid ${NVIS.borderSolid}`,
          borderRadius: 6,
          padding: '28px 48px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            width: '100%',
            maxWidth: 900,
          }}
          role="list"
          aria-label="Pipeline phase progress"
        >
          {PHASES.map((phase, i) => {
            const isComplete = currentIdx > i
            const isActive = currentIdx === i
            const isPending = currentIdx < i

            const dotColor = isComplete ? NVIS.green : isActive ? NVIS.accent : 'transparent'
            const dotBorder = isPending ? `2px solid ${NVIS.dim}` : isActive ? `3px solid ${NVIS.accent}` : 'none'
            const nameColor = isComplete ? NVIS.green : isActive ? NVIS.accent : NVIS.dim
            const lineStyle = isComplete
              ? { background: NVIS.green, opacity: 0.5 }
              : {
                  background: `repeating-linear-gradient(to right, ${NVIS.dim} 0, ${NVIS.dim} 6px, transparent 6px, transparent 12px)`,
                }

            return (
              <div key={phase} style={{ display: 'flex', alignItems: 'center', flex: i < PHASES.length - 1 ? undefined : 'none' }} role="listitem">
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                  <div
                    style={{
                      width: 18,
                      height: 18,
                      borderRadius: '50%',
                      background: dotColor,
                      border: dotBorder,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      position: 'relative',
                      boxShadow: isActive ? `0 0 12px rgba(74,158,255,0.4)` : isComplete ? `0 0 8px rgba(21,128,61,0.3)` : 'none',
                    }}
                    aria-label={`${phase}: ${isComplete ? 'complete' : isActive ? 'active' : 'pending'}`}
                  >
                    {isActive && (
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          background: NVIS.accent,
                          display: 'block',
                        }}
                        aria-hidden="true"
                      />
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 500,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      color: nameColor,
                    }}
                  >
                    {phase}
                  </span>
                </div>
                {i < PHASES.length - 1 && (
                  <div
                    style={{
                      flex: 1,
                      height: 2,
                      minWidth: 40,
                      marginBottom: 28,
                      ...lineStyle,
                    }}
                    aria-hidden="true"
                  />
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── RecentFailures ────────────────────────────────────────────

type ErrorTag = 'timeout' | 'parse_error' | 'encoding_error' | 'ocr_failure' | string

function ErrorBadge({ tag }: { tag: ErrorTag }) {
  let color: string = NVIS.red
  if (tag === 'timeout' || tag === 'ocr_failure') color = NVIS.amber

  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 3,
        fontSize: 11,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.03em',
        color,
        background: `${color}1a`,
        border: `1px solid ${color}40`,
      }}
    >
      {tag}
    </span>
  )
}

function RecentFailures({ files }: { files: string[] }) {
  const thS: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: NVIS.dim,
    textAlign: 'left',
    padding: '12px 20px',
    borderBottom: `1px solid ${NVIS.borderSolid}`,
    background: NVIS.surface2,
  }
  const tdS: React.CSSProperties = {
    padding: '11px 20px',
    borderBottom: `1px solid ${NVIS.borderSolid}`,
    fontSize: 13,
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          color: NVIS.dim,
          marginBottom: 16,
        }}
      >
        Recent Failures
      </div>
      <div
        style={{
          background: NVIS.surface,
          border: `1px solid ${NVIS.borderSolid}`,
          borderRadius: 6,
          overflow: 'hidden',
          flex: 1,
        }}
      >
        <table
          style={{ width: '100%', borderCollapse: 'collapse' }}
          aria-label="Recent extraction failures"
        >
          <thead>
            <tr>
              <th style={{ ...thS, width: '60%' }}>File</th>
              <th style={{ ...thS, width: '40%' }}>Error</th>
            </tr>
          </thead>
          <tbody>
            {files.length === 0 ? (
              <tr>
                <td colSpan={2} style={{ ...tdS, color: NVIS.dim, textAlign: 'center', borderBottom: 'none' }}>
                  No recent failures
                </td>
              </tr>
            ) : (
              files.map((filename, i) => (
                <tr
                  key={i}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#1a2230')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <td style={{ ...tdS, color: NVIS.white, fontWeight: 500 }}>{filename}</td>
                  <td style={{ ...tdS }}>
                    <ErrorBadge tag="timeout" />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── SupervisorSelector ────────────────────────────────────────

function SupervisorSelector({
  supervisors,
  selectedLabel,
  onSelect,
}: {
  supervisors: SupervisorState[]
  selectedLabel: string | null
  onSelect: (label: string) => void
}) {
  if (supervisors.length === 0) {
    return <div style={{ color: NVIS.dim, fontSize: 13 }}>No supervisors found</div>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {supervisors.map((sup) => {
        const isActive = sup.label === selectedLabel
        const hbColor = heartbeatColor(sup.review_heartbeat_age_seconds)
        const statusColor = workerStatusColor(sup.status)

        return (
          <button
            key={sup.label}
            onClick={() => onSelect(sup.label)}
            aria-pressed={isActive}
            style={{
              background: NVIS.surface,
              border: `1px solid ${isActive ? NVIS.accent : NVIS.borderSolid}`,
              borderRadius: 6,
              padding: '12px 16px',
              cursor: 'pointer',
              textAlign: 'left',
              width: '100%',
              fontFamily: 'monospace',
              outline: isActive ? `1px solid ${NVIS.accent}` : 'none',
              outlineOffset: 1,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: isActive ? NVIS.white : NVIS.dim }}>
                {sup.label}
              </span>
              <span
                style={{
                  fontSize: 11,
                  padding: '2px 8px',
                  borderRadius: 10,
                  background: `${statusColor}22`,
                  color: statusColor,
                  fontWeight: 600,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                }}
              >
                <span aria-hidden="true">
                  {statusColor === NVIS.green ? '\u25CF' : statusColor === NVIS.red ? '\u2716' : '\u25CB'}
                </span>
                {sup.status}
              </span>
            </div>
            <div style={{ display: 'flex', gap: 16, fontSize: 11, color: NVIS.dim, marginBottom: 6 }}>
              <span>restarts: <span style={{ color: NVIS.white }}>{sup.restart_count}</span></span>
              <span>runs: <span style={{ color: NVIS.white }}>{sup.run_count}</span></span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
              <span
                style={{ width: 7, height: 7, borderRadius: '50%', background: hbColor, display: 'inline-block' }}
                aria-hidden="true"
              />
              <span style={{ color: hbColor, fontSize: 10, fontWeight: 700 }} aria-hidden="true">
                {hbColor === NVIS.green ? '\u2713' : hbColor === NVIS.amber ? '\u26A0' : '\u2715'}
              </span>
              <span style={{ color: NVIS.dim }}>
                heartbeat{' '}
                <span style={{ color: hbColor }}>
                  {formatTimeAgo(sup.review_heartbeat_age_seconds)}
                </span>
                {sup.review_heartbeat_age_seconds > 300 && ' (stale)'}
              </span>
            </div>
          </button>
        )
      })}
    </div>
  )
}

// ── WorkerTable ───────────────────────────────────────────────

function WorkerTable({ workers }: { workers: WorkerState[] }) {
  const thS: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 500,
    color: NVIS.dim,
    textAlign: 'left',
    padding: '8px 12px',
    borderBottom: `1px solid ${NVIS.borderSolid}`,
  }
  const tdS: React.CSSProperties = {
    padding: '6px 12px',
    fontSize: 12,
    fontFamily: 'monospace',
    borderBottom: `1px solid ${NVIS.borderSolid}`,
  }

  return (
    <div
      style={{
        background: NVIS.surface,
        border: `1px solid ${NVIS.borderSolid}`,
        borderRadius: 6,
        overflow: 'hidden',
      }}
    >
      <table style={{ width: '100%', borderCollapse: 'collapse' }} aria-label="Worker status">
        <thead>
          <tr>
            <th style={thS}>#</th>
            <th style={{ ...thS, textAlign: 'right' }}>Elapsed</th>
            <th style={{ ...thS, textAlign: 'right' }}>Last Output</th>
          </tr>
        </thead>
        <tbody>
          {workers.length === 0 ? (
            <tr>
              <td colSpan={3} style={{ ...tdS, color: NVIS.dim, textAlign: 'center', borderBottom: 'none' }}>
                No workers
              </td>
            </tr>
          ) : (
            workers.map((w, i) => (
              <tr key={i}>
                <td style={{ ...tdS, color: NVIS.dim }}>{w.stats.worker_id ?? i}</td>
                <td style={{ ...tdS, textAlign: 'right', color: NVIS.white }}>
                  {formatSeconds(w.stats.elapsed_seconds)}
                </td>
                <td style={{ ...tdS, textAlign: 'right' }}>
                  <span style={{ color: stalenessColor(w.stats.last_output_age_seconds) }}>
                    {formatSeconds(w.stats.last_output_age_seconds)}
                  </span>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

// ── CountdownBadge ────────────────────────────────────────────

function CountdownBadge({ refreshMs }: { refreshMs: number }) {
  const [remaining, setRemaining] = useState(refreshMs / 1000)
  const startRef = useRef(Date.now())

  useEffect(() => {
    startRef.current = Date.now()
    setRemaining(refreshMs / 1000)
    const id = setInterval(() => {
      const elapsed = (Date.now() - startRef.current) / 1000
      const left = Math.max(0, refreshMs / 1000 - elapsed)
      setRemaining(Math.round(left))
    }, 1000)
    return () => clearInterval(id)
  }, [refreshMs])

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: 32,
        height: 22,
        padding: '0 8px',
        background: NVIS.surface2,
        border: `1px solid ${NVIS.borderSolid}`,
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 600,
        color: NVIS.accent,
        fontVariantNumeric: 'tabular-nums',
      }}
      aria-live="polite"
      aria-label={`Next refresh in ${remaining} seconds`}
    >
      {remaining}s
    </span>
  )
}

// ── main component ────────────────────────────────────────────

export default function SupervisorView() {
  const [supervisors, setSupervisors] = useState<SupervisorState[]>([])
  const [selected, setSelected] = useState<SupervisorState | null>(null)
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null)
  const [workers, setWorkers] = useState<WorkerState[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshTick, setRefreshTick] = useState(0)

  const refresh = useCallback(async () => {
    const [sups, wrks] = await Promise.all([loadSupervisors(), loadWorkers()])
    setSupervisors(sups)
    setWorkers(wrks)
    setSelectedLabel((prev) => prev ?? sups[0]?.label ?? null)
    setLoading(false)
  }, [])

  // Try to enrich with /memory data
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const result = await recallDocuments('extraction pipeline status')
        if (!cancelled && result.results && result.results.length > 0) {
          // Memory data available — could enrich supervisor state here
          console.log('[SupervisorView] /memory returned', result.results.length, 'results')
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Memory service unreachable')
        }
      }
    })()
    return () => { cancelled = true }
  }, [refreshTick])

  // Load detail for selected supervisor
  useEffect(() => {
    if (!selectedLabel) {
      setSelected(null)
      return
    }
    let cancelled = false
    ;(async () => {
      const detail = await loadSupervisor(selectedLabel)
      if (!cancelled) setSelected(detail)
    })()
    return () => {
      cancelled = true
    }
  }, [selectedLabel, refreshTick])

  // Initial load + auto-refresh
  useEffect(() => {
    refresh()
    const id = setInterval(() => {
      refresh()
      setRefreshTick((t) => t + 1)
    }, REFRESH_MS)
    return () => clearInterval(id)
  }, [refresh])

  if (loading) {
    return (
      <div style={{ padding: '24px 32px', color: NVIS.dim, fontSize: 13, fontFamily: 'monospace' }}>
        Loading supervisor data...
      </div>
    )
  }

  const m = selected?.run_metrics
  const phase = m?.phase ?? ''
  const workerCount = m?.worker_aggregate?.worker_count ?? workers.length
  const runningWorkers = workers.filter((w) => w.stats.last_output_age_seconds <= 30).length
  const queueDepth = m?.documents_missing ?? 0
  const failRate = m?.extraction_fail_rate_pct ?? 0
  const recentFailedPdfs = m?.recent_failed_pdfs ?? []
  const qualityGate = m?.quality_gate_action ?? ''

  const pipelineRunning = supervisors.some((s) => s.status === 'running')

  return (
    <div
      style={{
        padding: '24px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: 24,
        fontFamily: 'monospace',
        height: '100%',
        minHeight: 0,
        backgroundColor: NVIS.bg,
        color: NVIS.white,
      }}
    >
      {error && (
        <div style={{ background: '#1a0000', border: '1px solid #ff4444', borderRadius: 4, padding: '8px 12px', margin: '0 0 16px', color: '#ff4444', fontFamily: 'JetBrains Mono, monospace', fontSize: 12, flexShrink: 0 }}>
          ✗ {error}
        </div>
      )}

      {/* Header Row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 14, fontWeight: 600 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: pipelineRunning ? NVIS.green : NVIS.dim,
              display: 'inline-block',
              flexShrink: 0,
            }}
            aria-hidden="true"
          />
          <span style={{ color: NVIS.dim }}>Pipeline Status:</span>
          <span style={{ color: pipelineRunning ? NVIS.green : NVIS.dim }}>
            {pipelineRunning ? 'RUNNING' : 'IDLE'}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: NVIS.dim }}>
          <span>Auto-refresh:</span>
          <CountdownBadge refreshMs={REFRESH_MS} />
        </div>
      </div>

      {/* Top area: supervisors + metrics side by side */}
      <div style={{ display: 'flex', gap: 20, flexShrink: 0 }}>
        {/* Left: supervisor selector */}
        <div style={{ flex: '0 0 30%', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: NVIS.dim, marginBottom: 4 }}>
            Supervisors
          </div>
          <SupervisorSelector
            supervisors={supervisors}
            selectedLabel={selectedLabel}
            onSelect={setSelectedLabel}
          />
        </div>

        {/* Right: metric cards */}
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: NVIS.dim, marginBottom: 12 }}>
            {selected ? `Metrics — ${selected.label}` : 'Metrics'}
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 16,
            }}
          >
            <MetricCard
              label="Phase"
              value={phase || 'unknown'}
              color={NVIS.accent}
            />
            <MetricCard
              label="Workers"
              value={workerCount > 0 ? `${runningWorkers} / ${workerCount}` : '0'}
              color={runningWorkers > 0 ? NVIS.green : NVIS.dim}
            />
            <MetricCard
              label="Fail Rate"
              value={`${failRate.toFixed(1)}%`}
              color={failRateColor(failRate)}
            />
            <MetricCard
              label="Queue"
              value={queueDepth.toLocaleString()}
              color={queueDepth > 100 ? NVIS.amber : queueDepth > 0 ? NVIS.white : NVIS.dim}
            />
            {m && (
              <>
                <MetricCard
                  label="Attempts"
                  value={String(m.extraction_attempts)}
                  color={NVIS.white}
                />
                <MetricCard
                  label="Success"
                  value={String(m.extraction_success_count)}
                  color={NVIS.green}
                />
                <MetricCard
                  label="Failed"
                  value={String(m.extraction_failed_count)}
                  color={m.extraction_failed_count > 0 ? NVIS.red : NVIS.dim}
                />
                <MetricCard
                  label="Throughput/hr"
                  value={m.extraction_throughput_per_hour.toFixed(1)}
                  color={NVIS.accent}
                />
              </>
            )}
          </div>

          {/* Quality gate + retry queue */}
          {m && (
            <div style={{ display: 'flex', gap: 16, marginTop: 16 }}>
              <div
                style={{
                  flex: 1,
                  background: NVIS.surface,
                  border: `1px solid ${NVIS.borderSolid}`,
                  borderRadius: 6,
                  padding: '12px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: NVIS.dim }}>
                  Quality Gate
                </span>
                <span
                  style={{
                    fontSize: 12,
                    padding: '3px 10px',
                    borderRadius: 10,
                    background: qualityGate === 'continue_extracting' ? `${NVIS.green}22` : qualityGate === 'pause_and_debug' ? `${NVIS.amber}22` : `${NVIS.red}22`,
                    color: qualityGate === 'continue_extracting' ? NVIS.green : qualityGate === 'pause_and_debug' ? NVIS.amber : NVIS.red,
                    fontWeight: 600,
                  }}
                >
                  {qualityGate.replace(/_/g, ' ') || 'unknown'}
                </span>
                {m.quality_gate_reason && (
                  <span style={{ fontSize: 12, color: NVIS.dim }}>{m.quality_gate_reason}</span>
                )}
              </div>
              <div
                style={{
                  background: NVIS.surface,
                  border: `1px solid ${NVIS.borderSolid}`,
                  borderRadius: 6,
                  padding: '12px 16px',
                  display: 'flex',
                  gap: 24,
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: NVIS.dim, marginBottom: 4 }}>
                    Retry Queue
                  </div>
                  <div style={{ fontSize: 18, fontWeight: 600, color: NVIS.amber, fontVariantNumeric: 'tabular-nums' }}>
                    {m.memory_retry_queue_count}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: NVIS.dim, marginBottom: 4 }}>
                    Dead Letter
                  </div>
                  <div style={{ fontSize: 18, fontWeight: 600, color: m.memory_retry_dead_letter_count > 0 ? NVIS.red : NVIS.dim, fontVariantNumeric: 'tabular-nums' }}>
                    {m.memory_retry_dead_letter_count}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Phase progress bar */}
      <div style={{ flexShrink: 0 }}>
        <PhaseProgress currentPhase={phase} />
      </div>

      {/* Bottom: workers + recent failures */}
      <div style={{ display: 'flex', gap: 20, flex: 1, minHeight: 0 }}>
        {/* Workers */}
        <div style={{ flex: '0 0 30%', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: NVIS.dim }}>
            Workers ({workerCount})
          </div>
          <WorkerTable workers={workers} />
        </div>

        {/* Recent failures */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <RecentFailures files={recentFailedPdfs} />
        </div>
      </div>
    </div>
  )
}
