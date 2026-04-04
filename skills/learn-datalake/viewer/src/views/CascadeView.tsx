import { useState, useEffect, useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { NVIS } from '../theme'
import { loadCascade, loadCascadeEscalations } from '../loader'
import { recallDocuments } from '../api/client'
import type { CascadeDecisionPoint, CascadeEscalation } from '../types'

// --- Constants ---

const DECISION_POINTS = ['header-verdict', 'pdf-profile', 'pdf-strategy'] as const

const DISPOSITION_COLORS: Record<string, string> = {
  Accept: NVIS.green,
  Reject: NVIS.red,
  Escalate: NVIS.amber,
}

const TIER_LABELS: Record<string, string> = {
  'Tier 0': 'Heuristic',
  'Tier 0.5': 'Classifier',
  'Tier 2': 'LLM',
}

const BIN_OPTIONS = [
  { value: 5, label: '5' },
  { value: 10, label: '10' },
  { value: 20, label: '20' },
] as const

type BinCount = 5 | 10 | 20

type DispositionFilter = 'All' | 'Accept' | 'Reject' | 'Escalate'

// --- Helpers ---

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatDate(iso: string): string {
  if (!iso) return '--'
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatFeatures(features: Record<string, number | boolean | string>): string {
  return Object.entries(features)
    .map(([k, v]) => {
      if (typeof v === 'boolean') return `${k}: ${v}`
      if (typeof v === 'number') return `${k}: ${v.toFixed(v % 1 === 0 ? 0 : 1)}`
      return `${k}: ${v}`
    })
    .join(', ')
}

/** Rebin 5-bin confidence distribution into n bins */
function rebinConfidence(dist: number[], bins: BinCount): { bin: string; count: number; pct: number }[] {
  const total = dist.reduce((a, b) => a + b, 0)
  if (bins === 5) {
    const labels = ['0.0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0']
    return labels.map((bin, i) => ({
      bin,
      count: dist[i] ?? 0,
      pct: total > 0 ? ((dist[i] ?? 0) / total) * 100 : 0,
    }))
  }
  // For 10 or 20 bins, we interpolate from the 5 source bins
  // Since source data is 5 bins, we subdivide each evenly
  const subdiv = bins / 5
  const result: { bin: string; count: number; pct: number }[] = []
  const step = 1.0 / bins
  for (let i = 0; i < bins; i++) {
    const srcIdx = Math.floor(i / subdiv)
    const count = Math.round((dist[srcIdx] ?? 0) / subdiv)
    const lo = (i * step).toFixed(2)
    const hi = ((i + 1) * step).toFixed(2)
    result.push({
      bin: `${lo}-${hi}`,
      count,
      pct: total > 0 ? (count / total) * 100 : 0,
    })
  }
  return result
}

// --- Sub-components ---

function StatusBadge({ status }: { status: 'Early' | 'Learning' | 'Ready' }) {
  const styles: Record<string, { bg: string; text: string; border: string; icon: string }> = {
    Early: { bg: 'rgba(153,153,153,0.15)', text: NVIS.dim, border: NVIS.dim, icon: '[*]' },
    Learning: { bg: 'rgba(180,83,9,0.15)', text: NVIS.amber, border: NVIS.amber, icon: '[~]' },
    Ready: { bg: 'rgba(21,128,61,0.15)', text: NVIS.green, border: NVIS.green, icon: '[+]' },
  }
  const s = styles[status]
  return (
    <span
      role="status"
      aria-label={`Promotion status: ${status}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 12,
        fontFamily: 'monospace',
        fontWeight: 600,
        backgroundColor: s.bg,
        color: s.text,
        border: `1px solid ${s.border}`,
      }}
    >
      <span aria-hidden="true">{s.icon}</span>
      {status}
    </span>
  )
}

function HorizontalBar({
  value,
  max,
  color,
  label,
  count,
}: {
  value: number
  max: number
  color: string
  label: string
  count: string
}) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
      <span
        style={{
          width: 52,
          textAlign: 'right',
          fontSize: 11,
          fontFamily: 'monospace',
          color: NVIS.dim,
          flexShrink: 0,
        }}
      >
        {label}
      </span>
      <div
        style={{
          flex: 1,
          height: 18,
          backgroundColor: 'rgba(255,255,255,0.05)',
          borderRadius: 3,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            backgroundColor: color,
            borderRadius: 3,
            minWidth: value > 0 ? 2 : 0,
          }}
        />
      </div>
      <span
        style={{
          width: 50,
          fontSize: 11,
          fontFamily: 'monospace',
          color: NVIS.white,
          flexShrink: 0,
        }}
      >
        {count}
      </span>
    </div>
  )
}

// --- Custom Tooltip ---

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function HistogramTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ value: number }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  const entry = payload[0]
  return (
    <div
      style={{
        backgroundColor: NVIS.surface2,
        border: `1px solid ${NVIS.borderSolid}`,
        borderRadius: 4,
        padding: '6px 10px',
        fontFamily: 'monospace',
        fontSize: 11,
      }}
    >
      <div style={{ color: NVIS.dim }}>{label}</div>
      <div style={{ color: NVIS.accent, fontWeight: 600 }}>
        {entry.value.toLocaleString()}
      </div>
    </div>
  )
}

// --- Main Component ---

export default function CascadeView() {
  const [points, setPoints] = useState<CascadeDecisionPoint[]>([])
  const [escalations, setEscalations] = useState<CascadeEscalation[]>([])
  const [selectedPoint, setSelectedPoint] = useState<string>('header-verdict')
  const [binCount, setBinCount] = useState<BinCount>(5)
  const [dispositionFilter, setDispositionFilter] = useState<DispositionFilter>('All')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchCascade() {
      // Load initial data from loader (real sample data)
      const data = await loadCascade()
      setPoints(data)
      setLoading(false)
      // Try embry-memory to replace with live data
      try {
        const memoryResult = await recallDocuments('cascade shadow header-verdict')
        if (memoryResult.results && memoryResult.results.length > 0) {
          const mapped = memoryResult.results.map((r) => r.metadata as unknown as CascadeDecisionPoint).filter((p) => p && p.name)
          if (mapped.length > 0) {
            setPoints(mapped)
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Memory service unreachable')
      }
    }
    fetchCascade()
  }, [])

  useEffect(() => {
    loadCascadeEscalations(selectedPoint, 20).then(setEscalations)
  }, [selectedPoint])

  const active = useMemo(
    () => points.find((p) => p.name === selectedPoint),
    [points, selectedPoint],
  )

  const confidenceData = useMemo(() => {
    if (!active) return []
    return rebinConfidence(active.confidence_distribution, binCount)
  }, [active, binCount])

  const filteredEscalations = useMemo(() => {
    if (dispositionFilter === 'All') return escalations
    return escalations.filter((e) => e.rust_guess === dispositionFilter)
  }, [escalations, dispositionFilter])

  // Tier counts from data or derive from disposition
  const tierCounts = useMemo(() => {
    if (!active) return []
    if (active.tier_counts) {
      return Object.entries(active.tier_counts).map(([tier, count]) => ({
        tier,
        label: TIER_LABELS[tier] ?? tier,
        count,
      }))
    }
    // Fallback: estimate from disposition counts
    const total = active.total_samples
    const escalateCount = active.disposition_counts['Escalate'] ?? 0
    const resolvedCount = total - escalateCount
    return [
      { tier: 'Tier 0', label: 'Heuristic', count: Math.round(resolvedCount * 0.7) },
      { tier: 'Tier 0.5', label: 'Classifier', count: Math.round(resolvedCount * 0.3) },
      { tier: 'Tier 2', label: 'LLM', count: escalateCount },
    ]
  }, [active])

  // Disposition chart data
  const dispositionData = useMemo(() => {
    if (!active) return []
    return Object.entries(active.disposition_counts).map(([name, value]) => ({
      name,
      value,
    }))
  }, [active])

  const totalDisp = useMemo(
    () => dispositionData.reduce((sum, d) => sum + d.value, 0),
    [dispositionData],
  )

  // Promotion progress
  const progressPct = active
    ? active.samples_vs_threshold.threshold > 0
      ? Math.min(100, (active.samples_vs_threshold.current / active.samples_vs_threshold.threshold) * 100)
      : 0
    : 0

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          color: NVIS.dim,
          fontFamily: 'monospace',
          fontSize: 13,
        }}
      >
        Loading cascade data...
      </div>
    )
  }

  if (!active) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          color: NVIS.dim,
          fontFamily: 'monospace',
          fontSize: 13,
        }}
      >
        No cascade decision points available.
      </div>
    )
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: NVIS.bg,
        overflow: 'hidden',
      }}
    >
      {error && (
        <div style={{ background: '#1a0000', border: '1px solid #ff4444', borderRadius: 4, padding: '8px 12px', margin: '8px 0', color: '#ff4444', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
          ✗ {error}
        </div>
      )}
      {/* Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 24px',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2
            style={{
              fontSize: 14,
              fontWeight: 600,
              fontFamily: 'monospace',
              color: NVIS.white,
              margin: 0,
            }}
          >
            Cascade Decisions
          </h2>
          <StatusBadge status={active.promotion_status} />
        </div>
        <span
          style={{
            fontSize: 12,
            fontFamily: 'monospace',
            color: NVIS.dim,
          }}
        >
          {active.total_samples.toLocaleString()} shadow entries
        </span>
      </div>

      {/* Decision Point Selector */}
      <div
        role="tablist"
        aria-label="Cascade decision points"
        style={{
          display: 'flex',
          gap: 6,
          padding: '0 24px 12px',
          flexShrink: 0,
        }}
      >
        {DECISION_POINTS.map((dp) => {
          const isActive = dp === selectedPoint
          return (
            <button
              key={dp}
              role="tab"
              aria-selected={isActive}
              aria-controls={`panel-${dp}`}
              onClick={() => setSelectedPoint(dp)}
              style={{
                padding: '6px 16px',
                borderRadius: 6,
                fontSize: 12,
                fontFamily: 'monospace',
                fontWeight: 500,
                cursor: 'pointer',
                border: isActive
                  ? `1px solid ${NVIS.accent}`
                  : `1px solid ${NVIS.borderSolid}`,
                backgroundColor: isActive
                  ? 'rgba(74,158,255,0.12)'
                  : 'transparent',
                color: isActive ? NVIS.accent : NVIS.dim,
              }}
            >
              {dp}
            </button>
          )
        })}
      </div>

      {/* Main Content */}
      <div
        id={`panel-${selectedPoint}`}
        role="tabpanel"
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          padding: '0 24px 24px',
          overflow: 'auto',
          minHeight: 0,
        }}
      >
        {/* Top Row: Disposition + Confidence + Promotion */}
        <div style={{ display: 'flex', gap: 16, flexShrink: 0 }}>
          {/* Disposition Summary */}
          <div
            style={{
              flex: '1 1 33%',
              backgroundColor: NVIS.surface,
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: 8,
              padding: 20,
            }}
          >
            <h3
              style={{
                fontSize: 12,
                fontWeight: 600,
                fontFamily: 'monospace',
                color: NVIS.white,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 14,
              }}
            >
              Disposition Summary
            </h3>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={dispositionData} margin={{ top: 16, right: 8, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={NVIS.borderSolid} />
                <XAxis
                  dataKey="name"
                  tick={{ fill: NVIS.dim, fontSize: 11, fontFamily: 'monospace' }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: NVIS.dim, fontSize: 11, fontFamily: 'monospace' }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v: number) => formatCount(v)}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: NVIS.surface2,
                    border: `1px solid ${NVIS.borderSolid}`,
                    borderRadius: 4,
                    color: NVIS.white,
                    fontFamily: 'monospace',
                    fontSize: 11,
                  }}
                  formatter={(value: number) => [value.toLocaleString(), 'Count']}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} label={{ position: 'top', fill: NVIS.white, fontSize: 11, fontFamily: 'monospace', formatter: (v: number) => formatCount(v) }}>
                  {dispositionData.map((entry) => (
                    <Cell key={entry.name} fill={DISPOSITION_COLORS[entry.name] ?? NVIS.accent} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            {/* Class balance bar */}
            <div style={{ marginTop: 12 }}>
              <div
                style={{
                  display: 'flex',
                  height: 14,
                  borderRadius: 3,
                  overflow: 'hidden',
                  backgroundColor: 'rgba(255,255,255,0.05)',
                }}
              >
                {totalDisp > 0 &&
                  dispositionData.map((d) => (
                    <div
                      key={d.name}
                      style={{
                        width: `${(d.value / totalDisp) * 100}%`,
                        height: '100%',
                        backgroundColor: DISPOSITION_COLORS[d.name] ?? NVIS.accent,
                      }}
                    />
                  ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', gap: 16, marginTop: 6 }}>
                {dispositionData.map((d) => (
                  <span
                    key={d.name}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      fontSize: 11,
                      fontFamily: 'monospace',
                      color: NVIS.dim,
                    }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: 2,
                        backgroundColor: DISPOSITION_COLORS[d.name] ?? NVIS.accent,
                        display: 'inline-block',
                      }}
                    />
                    {d.name}{' '}
                    <span style={{ color: NVIS.white }}>
                      {totalDisp > 0 ? ((d.value / totalDisp) * 100).toFixed(1) : '0.0'}%
                    </span>
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Confidence Histogram */}
          <div
            style={{
              flex: '1 1 40%',
              backgroundColor: NVIS.surface,
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: 8,
              padding: 20,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 14,
              }}
            >
              <h3
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  fontFamily: 'monospace',
                  color: NVIS.white,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  margin: 0,
                }}
              >
                Confidence Distribution
              </h3>
              <div
                role="radiogroup"
                aria-label="Histogram bin count"
                style={{ display: 'flex', gap: 2, backgroundColor: NVIS.surface2, borderRadius: 4, padding: 2 }}
              >
                {BIN_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    role="radio"
                    aria-checked={binCount === opt.value}
                    onClick={() => setBinCount(opt.value)}
                    style={{
                      padding: '2px 10px',
                      fontSize: 10,
                      fontFamily: 'monospace',
                      fontWeight: 500,
                      border: 'none',
                      borderRadius: 3,
                      cursor: 'pointer',
                      backgroundColor: binCount === opt.value ? 'rgba(74,158,255,0.15)' : 'transparent',
                      color: binCount === opt.value ? NVIS.accent : NVIS.dim,
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* CSS horizontal bars with threshold lines */}
            <div style={{ position: 'relative' }}>
              {confidenceData.map((d) => (
                <HorizontalBar
                  key={d.bin}
                  value={d.count}
                  max={Math.max(...confidenceData.map((c) => c.count), 1)}
                  color={NVIS.accent}
                  label={d.bin}
                  count={`${d.pct.toFixed(0)}%`}
                />
              ))}
              {/* Threshold labels */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  marginTop: 8,
                  fontSize: 10,
                  fontFamily: 'monospace',
                }}
              >
                <span style={{ color: NVIS.red }}>Reject &lt;=0.15</span>
                <span style={{ color: NVIS.green }}>Accept &gt;=0.85</span>
              </div>
            </div>
          </div>

          {/* Promotion & Tier Breakdown */}
          <div
            style={{
              flex: '1 1 27%',
              backgroundColor: NVIS.surface,
              border: `1px solid ${NVIS.borderSolid}`,
              borderRadius: 8,
              padding: 20,
            }}
          >
            <h3
              style={{
                fontSize: 12,
                fontWeight: 600,
                fontFamily: 'monospace',
                color: NVIS.white,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: 14,
              }}
            >
              Promotion Readiness
            </h3>

            {/* Agreement Rate */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontFamily: 'monospace', color: NVIS.dim, marginBottom: 2 }}>
                Agreement Rate
              </div>
              <div
                style={{
                  fontSize: 24,
                  fontWeight: 700,
                  fontFamily: 'monospace',
                  color:
                    active.agreement_rate >= 0.9
                      ? NVIS.green
                      : active.agreement_rate >= 0.7
                        ? NVIS.amber
                        : NVIS.red,
                }}
              >
                {(active.agreement_rate * 100).toFixed(1)}%
              </div>
            </div>

            {/* Wilson Lower Bound */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontFamily: 'monospace', color: NVIS.dim, marginBottom: 2 }}>
                Wilson Lower Bound (99% CI)
              </div>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 600,
                  fontFamily: 'monospace',
                  color: active.wilson_lower_bound >= 0.85 ? NVIS.green : active.wilson_lower_bound >= 0.7 ? NVIS.amber : NVIS.dim,
                }}
              >
                {active.wilson_lower_bound.toFixed(4)}
              </div>
            </div>

            {/* Samples Progress */}
            <div style={{ marginBottom: 16 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: 11,
                  fontFamily: 'monospace',
                  color: NVIS.dim,
                  marginBottom: 4,
                }}
              >
                <span>Samples: {formatCount(active.samples_vs_threshold.current)}</span>
                <span>threshold: {formatCount(active.samples_vs_threshold.threshold)}</span>
              </div>
              <div
                role="progressbar"
                aria-valuenow={progressPct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Sample collection progress"
                style={{
                  height: 10,
                  backgroundColor: 'rgba(255,255,255,0.05)',
                  borderRadius: 3,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${progressPct}%`,
                    height: '100%',
                    backgroundColor: progressPct >= 100 ? NVIS.green : progressPct >= 50 ? NVIS.amber : NVIS.dim,
                    borderRadius: 3,
                  }}
                />
              </div>
            </div>

            {/* Tier Breakdown */}
            <div style={{ borderTop: `1px solid ${NVIS.borderSolid}`, paddingTop: 12 }}>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  fontFamily: 'monospace',
                  color: NVIS.dim,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  marginBottom: 8,
                }}
              >
                Tier Breakdown
              </div>
              {tierCounts.map((t) => (
                <div
                  key={t.tier}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '4px 0',
                  }}
                >
                  <span style={{ fontSize: 12, fontFamily: 'monospace', color: NVIS.white }}>
                    {t.tier}{' '}
                    <span style={{ color: NVIS.dim, fontSize: 10 }}>({t.label})</span>
                  </span>
                  <span style={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 600, color: NVIS.white }}>
                    {formatCount(t.count)}
                  </span>
                </div>
              ))}
            </div>

            {/* Date Range */}
            <div style={{ borderTop: `1px solid ${NVIS.borderSolid}`, paddingTop: 12, marginTop: 12 }}>
              <div
                style={{
                  fontSize: 10,
                  fontFamily: 'monospace',
                  color: NVIS.dim,
                }}
              >
                {formatDate(active.date_range.start)} — {formatDate(active.date_range.end)}
              </div>
              <div
                style={{
                  fontSize: 10,
                  fontFamily: 'monospace',
                  color: NVIS.dim,
                  marginTop: 2,
                }}
              >
                Shadow: {formatBytes(active.shadow_file_size_bytes)}
              </div>
            </div>
          </div>
        </div>

        {/* Bottom: Recent Escalations Table */}
        <div
          style={{
            backgroundColor: NVIS.surface,
            border: `1px solid ${NVIS.borderSolid}`,
            borderRadius: 8,
            padding: 20,
            flex: 1,
            minHeight: 200,
            overflow: 'auto',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 14,
            }}
          >
            <h3
              style={{
                fontSize: 12,
                fontWeight: 600,
                fontFamily: 'monospace',
                color: NVIS.white,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                margin: 0,
              }}
            >
              Recent Escalations
            </h3>
            <div
              role="radiogroup"
              aria-label="Filter by disposition"
              style={{ display: 'flex', gap: 2, backgroundColor: NVIS.surface2, borderRadius: 4, padding: 2 }}
            >
              {(['All', 'Accept', 'Reject', 'Escalate'] as const).map((f) => (
                <button
                  key={f}
                  role="radio"
                  aria-checked={dispositionFilter === f}
                  onClick={() => setDispositionFilter(f)}
                  style={{
                    padding: '2px 10px',
                    fontSize: 10,
                    fontFamily: 'monospace',
                    fontWeight: 500,
                    border: 'none',
                    borderRadius: 3,
                    cursor: 'pointer',
                    backgroundColor: dispositionFilter === f ? 'rgba(74,158,255,0.15)' : 'transparent',
                    color: dispositionFilter === f ? NVIS.accent : NVIS.dim,
                  }}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          <table
            role="table"
            aria-label="Recent cascade escalations"
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontFamily: 'monospace',
              fontSize: 12,
            }}
          >
            <thead>
              <tr>
                <th
                  scope="col"
                  style={{
                    textAlign: 'left',
                    padding: '6px 12px 6px 0',
                    fontSize: 11,
                    fontWeight: 600,
                    color: NVIS.dim,
                    borderBottom: `1px solid ${NVIS.borderSolid}`,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  File
                </th>
                <th
                  scope="col"
                  style={{
                    textAlign: 'left',
                    padding: '6px 12px',
                    fontSize: 11,
                    fontWeight: 600,
                    color: NVIS.dim,
                    borderBottom: `1px solid ${NVIS.borderSolid}`,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Confidence
                </th>
                <th
                  scope="col"
                  style={{
                    textAlign: 'left',
                    padding: '6px 12px',
                    fontSize: 11,
                    fontWeight: 600,
                    color: NVIS.dim,
                    borderBottom: `1px solid ${NVIS.borderSolid}`,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Rust Guess
                </th>
                <th
                  scope="col"
                  style={{
                    textAlign: 'left',
                    padding: '6px 0 6px 12px',
                    fontSize: 11,
                    fontWeight: 600,
                    color: NVIS.dim,
                    borderBottom: `1px solid ${NVIS.borderSolid}`,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Features
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredEscalations.length === 0 ? (
                <tr>
                  <td
                    colSpan={4}
                    style={{
                      padding: '20px 0',
                      textAlign: 'center',
                      color: NVIS.dim,
                      fontSize: 12,
                    }}
                  >
                    {escalations.length === 0
                      ? 'No escalation data available'
                      : 'No entries match the selected filter'}
                  </td>
                </tr>
              ) : (
                filteredEscalations.map((esc, i) => {
                  const disagree =
                    esc.classifier_disposition &&
                    esc.classifier_disposition !== esc.rust_guess
                  return (
                    <tr
                      key={`${esc.filename}-${i}`}
                      style={{
                        cursor: esc.doc_id ? 'pointer' : 'default',
                        backgroundColor: disagree
                          ? 'rgba(180,83,9,0.04)'
                          : 'transparent',
                      }}
                      onClick={() => {
                        if (esc.doc_id) {
                          // Navigate to quarantine view with doc ID
                          window.location.hash = `#quarantine/${esc.doc_id}`
                        }
                      }}
                      title={
                        esc.doc_id
                          ? 'Click to view in Quarantine'
                          : undefined
                      }
                    >
                      <td
                        style={{
                          padding: '8px 12px 8px 0',
                          color: NVIS.accent,
                          borderBottom: `1px solid rgba(30,37,45,0.5)`,
                          maxWidth: 220,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {esc.filename}
                      </td>
                      <td
                        style={{
                          padding: '8px 12px',
                          color:
                            esc.confidence >= 0.85
                              ? NVIS.green
                              : esc.confidence <= 0.15
                                ? NVIS.red
                                : NVIS.white,
                          borderBottom: `1px solid rgba(30,37,45,0.5)`,
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {esc.confidence.toFixed(2)}
                      </td>
                      <td
                        style={{
                          padding: '8px 12px',
                          color: DISPOSITION_COLORS[esc.rust_guess] ?? NVIS.white,
                          borderBottom: `1px solid rgba(30,37,45,0.5)`,
                          fontWeight: 500,
                        }}
                      >
                        {esc.rust_guess}
                      </td>
                      <td
                        style={{
                          padding: '8px 0 8px 12px',
                          color: NVIS.dim,
                          borderBottom: `1px solid rgba(30,37,45,0.5)`,
                          fontSize: 10,
                          maxWidth: 400,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={formatFeatures(esc.features)}
                      >
                        {formatFeatures(esc.features)}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
