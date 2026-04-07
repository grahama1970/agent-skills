import { useState } from 'react'
import { NVIS } from '../theme'
import type { MonitorStripEvent } from '../types'

// --- Sample data ---
const SAMPLE_EVENTS: MonitorStripEvent[] = [
  {
    id: 'ev-1', timestamp: '02:20 AM', status: 'warn',
    source: 'monitor-drift-sensors',
    message: 'CUSUM alert: header-verdict agreement dropped 91.2% → 88.7% on nist preset (last 48h)',
  },
  {
    id: 'ev-2', timestamp: '02:17 AM', status: 'pass',
    source: 'monitor-skills',
    message: '/extract-pdf: sanity PASS, 4491 tests, cascade 3/3 healthy, shadow 540K entries',
  },
  {
    id: 'ev-3', timestamp: '02:15 AM', status: 'pass',
    source: 'monitor-codebase',
    message: 'pdf_oxide: 0 lint issues, 0 type errors, 4491 tests pass, no regressions vs main',
  },
  {
    id: 'ev-4', timestamp: '02:10 AM', status: 'info',
    source: 'monitor-skill-health',
    message: 'header-verdict classifier: F1=0.9979, 529K shadow entries, promoted to Tier 0.5',
  },
  {
    id: 'ev-5', timestamp: 'Yesterday', status: 'fail',
    source: 'monitor-drift-sensors',
    message: 'Page-Hinkley: pdf-strategy accuracy anomaly on engineering preset (p=0.03), auto-resolved',
  },
  {
    id: 'ev-6', timestamp: 'Yesterday', status: 'pass',
    source: 'monitor-codebase',
    message: 'Full corpus benchmark: 97.5% parity, 4.5x speed improvement validated',
  },
  {
    id: 'ev-7', timestamp: '2d ago', status: 'info',
    source: 'monitor-skills',
    message: '/learn-datalake: nightly run complete, 2,819 PDFs seeded, 540,618 shadow entries',
  },
]

type MonitorStatus = 'pass' | 'warn' | 'fail'

interface MonitorChipData {
  name: string
  status: MonitorStatus
  time: string
}

const MONITOR_CHIPS: MonitorChipData[] = [
  { name: 'monitor-codebase', status: 'pass', time: '02:15' },
  { name: 'monitor-skills', status: 'pass', time: '02:17' },
  { name: 'drift-sensors', status: 'warn', time: '02:20' },
]

const DOT_COLOR: Record<MonitorStatus | 'info', string> = {
  pass: '#15803d',
  warn: '#b45309',
  fail: '#dc2626',
  info: NVIS.accent,
}

const STATUS_ICON: Record<MonitorStatus | 'info', string> = {
  pass: '\u2713',  // ✓
  warn: '\u26A0',  // ⚠
  fail: '\u2715',  // ✕
  info: '\u2139',  // ℹ
}

interface MonitorChipProps {
  chip: MonitorChipData
}

function MonitorChip({ chip }: MonitorChipProps) {
  const icon = STATUS_ICON[chip.status]
  const dotColor = DOT_COLOR[chip.status]
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 6, fontSize: 11,
        color: NVIS.dim, padding: '2px 8px', borderRadius: 3,
        background: '#161b21', whiteSpace: 'nowrap',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
          background: dotColor,
        }}
      />
      <span
        aria-label={chip.status}
        style={{ color: dotColor, fontSize: 10, fontWeight: 700, flexShrink: 0 }}
      >
        {icon}
      </span>
      <span style={{ color: NVIS.dim }}>{chip.name}</span>
      <span style={{ color: NVIS.dim, fontSize: 10 }}>{chip.time}</span>
    </div>
  )
}

function CascadeChip() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: NVIS.dim, padding: '2px 8px', borderRadius: 3, background: '#161b21', whiteSpace: 'nowrap' }}>
      <span style={{ color: '#999' }}>cascade</span>
      <span style={{ color: '#15803d', fontSize: 12 }}>↑</span>
      <span>91.2%</span>
    </div>
  )
}

function ShadowChip() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: NVIS.dim, padding: '2px 8px', borderRadius: 3, background: '#161b21', whiteSpace: 'nowrap' }}>
      <span style={{ color: '#999' }}>shadow</span>
      <span>540K entries</span>
    </div>
  )
}

interface MonitorStripProps {
  /** Passed by App so the event source link can navigate to a view */
  onNavigate?: (source: string) => void
}

export default function MonitorStrip({ onNavigate }: MonitorStripProps) {
  const [expanded, setExpanded] = useState(false)

  const chipRow = (
    <>
      {MONITOR_CHIPS.map((c) => <MonitorChip key={c.name} chip={c} />)}
      <CascadeChip />
      <ShadowChip />
    </>
  )

  if (!expanded) {
    return (
      <div
        role="complementary"
        aria-label="Monitor status strip"
        style={{
          height: 32, background: '#0a0d10', borderTop: `1px solid ${NVIS.borderSolid}`,
          display: 'flex', alignItems: 'center', padding: '0 12px', gap: 16, flexShrink: 0,
        }}
      >
        <button
          aria-label="Expand monitor strip"
          aria-expanded={false}
          onClick={() => setExpanded(true)}
          style={{
            width: 16, height: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#999', cursor: 'pointer', fontSize: 10, flexShrink: 0,
            background: 'none', border: 'none', padding: 0, fontFamily: 'monospace',
          }}
        >
          &#9658;
        </button>
        {chipRow}
        <div style={{ flex: 1 }} />
        <span style={{ color: NVIS.dim, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          last nightly: 5h ago
        </span>
      </div>
    )
  }

  return (
    <div
      role="complementary"
      aria-label="Monitor status strip"
      style={{ background: '#0a0d10', borderTop: `1px solid ${NVIS.borderSolid}`, flexShrink: 0 }}
    >
      {/* Header row */}
      <div style={{
        height: 32, display: 'flex', alignItems: 'center', padding: '0 12px', gap: 16,
        borderBottom: '1px solid #161b21',
      }}>
        <button
          aria-label="Collapse monitor strip"
          aria-expanded={true}
          onClick={() => setExpanded(false)}
          style={{
            width: 16, height: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: NVIS.accent, cursor: 'pointer', fontSize: 10, flexShrink: 0,
            background: 'none', border: 'none', padding: 0, fontFamily: 'monospace',
          }}
        >
          &#9660;
        </button>
        {chipRow}
        <div style={{ flex: 1 }} />
        <span style={{ color: NVIS.dim, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
          last nightly: 5h ago
        </span>
      </div>

      {/* Event log */}
      <div
        role="log"
        aria-label="Monitor event log"
        aria-live="polite"
        style={{ padding: '8px 12px', maxHeight: 168, overflowY: 'auto' }}
      >
        {SAMPLE_EVENTS.map((ev) => {
          const dotColor = DOT_COLOR[ev.status as keyof typeof DOT_COLOR] ?? NVIS.dim
          const statusIcon = STATUS_ICON[ev.status as keyof typeof STATUS_ICON] ?? ''
          return (
            <div
              key={ev.id}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 10,
                padding: '4px 0', fontSize: 11,
                borderBottom: '1px solid #111418',
              }}
            >
              <span style={{ color: NVIS.dim, fontSize: 10, minWidth: 72, flexShrink: 0, paddingTop: 1 }}>
                {ev.timestamp}
              </span>
              <span
                aria-hidden="true"
                style={{
                  width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                  marginTop: 5, background: dotColor,
                }}
              />
              <span
                aria-label={ev.status}
                style={{ color: dotColor, fontSize: 10, fontWeight: 700, flexShrink: 0, paddingTop: 1, minWidth: 10 }}
              >
                {statusIcon}
              </span>
              <button
                aria-label={`Navigate to ${ev.source}`}
                onClick={() => onNavigate?.(ev.source)}
                style={{
                  color: NVIS.accent, minWidth: 140, flexShrink: 0,
                  background: 'none', border: 'none', padding: 0,
                  fontFamily: 'monospace', fontSize: 11, cursor: 'pointer',
                  textAlign: 'left',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.textDecoration = 'underline' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.textDecoration = 'none' }}
              >
                {ev.source}
              </button>
              <span style={{ color: NVIS.dim, flex: 1 }}>{ev.message}</span>
              <button
                aria-label={`View full report for ${ev.source}`}
                style={{
                  color: NVIS.dim, fontSize: 10, cursor: 'pointer', whiteSpace: 'nowrap',
                  flexShrink: 0, background: 'none', border: 'none', padding: 0,
                  fontFamily: 'monospace',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = NVIS.accent }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = NVIS.dim }}
              >
                → full report
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
