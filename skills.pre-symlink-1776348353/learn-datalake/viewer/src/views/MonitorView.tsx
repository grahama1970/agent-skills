import { useState, useEffect } from 'react'
import { NVIS } from '../theme'
import { checkHealth } from '../api/client'
// Mock data from ../api/mock available but using local MOCK_SERVICES/MOCK_EVENTS for richer detail
import type { MonitorService, MonitorEvent } from '../types'

// --- Mock data (V10 spec: 4-6 service cards + event log) ---

const MOCK_SERVICES: MonitorService[] = [
  {
    name: 'Codebase Health',
    status: 'healthy',
    lastCheck: new Date(Date.now() - 45_000).toISOString(),
    latencyMs: 320,
    errorRate: 0.002,
    details: '0 lint violations, 4491 tests passing',
  },
  {
    name: 'Workstation',
    status: 'healthy',
    lastCheck: new Date(Date.now() - 120_000).toISOString(),
    latencyMs: 85,
    errorRate: 0,
    details: 'NVMe 42% used, 12TB 68% used, GPU idle',
  },
  {
    name: 'Skill Health',
    status: 'degraded',
    lastCheck: new Date(Date.now() - 300_000).toISOString(),
    latencyMs: 1200,
    errorRate: 0.031,
    details: '234/237 skills healthy, 3 stale',
  },
  {
    name: 'Drift Sensors',
    status: 'healthy',
    lastCheck: new Date(Date.now() - 60_000).toISOString(),
    latencyMs: 150,
    errorRate: 0,
    details: 'CUSUM stable, no alarms',
  },
  {
    name: 'GPU Utilization',
    status: 'healthy',
    lastCheck: new Date(Date.now() - 30_000).toISOString(),
    latencyMs: 42,
    errorRate: 0,
    details: 'RTX 4090: 0% util, 24GB free',
  },
  {
    name: 'Disk Space',
    status: 'degraded',
    lastCheck: new Date(Date.now() - 180_000).toISOString(),
    errorRate: 0,
    details: '/mnt/storage12tb at 68% — approaching 75% threshold',
  },
]

const MOCK_EVENTS: MonitorEvent[] = [
  {
    timestamp: new Date(Date.now() - 15_000).toISOString(),
    source: 'monitor-codebase',
    level: 'info',
    message: 'Nightly scan complete: 0 violations found in /extract-pdf',
  },
  {
    timestamp: new Date(Date.now() - 120_000).toISOString(),
    source: 'monitor-skill-health',
    level: 'warn',
    message: '3 skills stale: /create-lut, /ops-nzbgeek, /sync-sites (>7d since last sanity)',
  },
  {
    timestamp: new Date(Date.now() - 300_000).toISOString(),
    source: 'monitor-workstation',
    level: 'info',
    message: 'Disk usage check: NVMe 42%, 12TB 68%, cache clean',
  },
  {
    timestamp: new Date(Date.now() - 600_000).toISOString(),
    source: 'monitor-drift-sensors',
    level: 'info',
    message: 'CUSUM reset on header-verdict stream — 12h stable window',
  },
  {
    timestamp: new Date(Date.now() - 900_000).toISOString(),
    source: 'monitor-ollama',
    level: 'error',
    message: 'Ollama runner hung (1200% CPU), auto-restarted successfully',
  },
  {
    timestamp: new Date(Date.now() - 1200_000).toISOString(),
    source: 'monitor-codebase',
    level: 'info',
    message: 'Incremental scan: /extract-tables 0 violations, /extractor 0 violations',
  },
  {
    timestamp: new Date(Date.now() - 1800_000).toISOString(),
    source: 'monitor-workstation',
    level: 'warn',
    message: '/mnt/storage12tb at 68% — 75% alert threshold approaching',
  },
  {
    timestamp: new Date(Date.now() - 2400_000).toISOString(),
    source: 'monitor-skill-health',
    level: 'info',
    message: 'Nightly skill scan: 234/237 healthy, 3 aspirational gaps flagged',
  },
  {
    timestamp: new Date(Date.now() - 3000_000).toISOString(),
    source: 'monitor-pi',
    level: 'info',
    message: 'D-Bus daemon healthy, scheduler 12/12 jobs succeeded',
  },
  {
    timestamp: new Date(Date.now() - 3600_000).toISOString(),
    source: 'monitor-security',
    level: 'info',
    message: 'T0 scan clean: 0 Semgrep findings, 0 gitleaks, 0 pip-audit vulnerabilities',
  },
  {
    timestamp: new Date(Date.now() - 4200_000).toISOString(),
    source: 'monitor-ollama',
    level: 'warn',
    message: 'Ollama /api/chat latency spike: 4200ms (threshold 3000ms)',
  },
  {
    timestamp: new Date(Date.now() - 5400_000).toISOString(),
    source: 'monitor-codebase',
    level: 'info',
    message: 'Project state assessment: 4 projects healthy, 0 degraded',
  },
  {
    timestamp: new Date(Date.now() - 7200_000).toISOString(),
    source: 'monitor-drift-sensors',
    level: 'error',
    message: 'Page-Hinkley alarm on pdf-strategy stream — drift detected, cascade re-calibrating',
  },
  {
    timestamp: new Date(Date.now() - 9000_000).toISOString(),
    source: 'monitor-workstation',
    level: 'info',
    message: 'Cache cleanup: removed 2.3GB from ~/.cache/huggingface',
  },
  {
    timestamp: new Date(Date.now() - 10800_000).toISOString(),
    source: 'monitor-pi',
    level: 'warn',
    message: 'Scheduler job extract-pdf-nightly took 47m (expected <30m)',
  },
  {
    timestamp: new Date(Date.now() - 14400_000).toISOString(),
    source: 'monitor-security',
    level: 'info',
    message: 'T2 Docker self-hack complete: 0 findings, container destroyed',
  },
  {
    timestamp: new Date(Date.now() - 18000_000).toISOString(),
    source: 'monitor-codebase',
    level: 'info',
    message: 'ast-grep scan: 0 anti-patterns detected across 4 registered projects',
  },
  {
    timestamp: new Date(Date.now() - 21600_000).toISOString(),
    source: 'monitor-skill-health',
    level: 'info',
    message: 'Weekly trend: 2 skills improved (lint fix), 1 skill regressed (/ops-nzbgeek)',
  },
  {
    timestamp: new Date(Date.now() - 28800_000).toISOString(),
    source: 'monitor-ollama',
    level: 'info',
    message: 'Health check OK: qwen3-4b loaded, 890ms p50 latency',
  },
  {
    timestamp: new Date(Date.now() - 36000_000).toISOString(),
    source: 'monitor-workstation',
    level: 'info',
    message: 'SMART check: all drives healthy, 0 reallocated sectors',
  },
]

// --- Status colors (V10 design board spec) ---

const STATUS_DOT_COLORS: Record<MonitorService['status'], string> = {
  healthy: '#00ff88',
  degraded: '#ffaa00',
  down: '#ff4444',
}

const LEVEL_DOT_COLORS: Record<MonitorEvent['level'], string> = {
  info: '#4a9eff',
  warn: '#ffaa00',
  error: '#ff4444',
}

// --- Helpers ---

function formatTimeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

// --- Filter types ---

type LevelFilter = 'All' | 'info' | 'warn' | 'error'

// --- Sub-components ---

function ServiceCard({ service }: { service: MonitorService }) {
  const dotColor = STATUS_DOT_COLORS[service.status]

  return (
    <div
      style={{
        backgroundColor: NVIS.surface,
        border: `1px solid ${NVIS.borderSolid}`,
        borderRadius: 8,
        padding: '16px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      {/* Header: name + status dot */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            fontFamily: 'monospace',
            color: NVIS.white,
          }}
        >
          {service.name}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: dotColor,
              display: 'inline-block',
              boxShadow: `0 0 6px ${dotColor}60`,
            }}
            aria-hidden="true"
          />
          <span
            style={{
              fontSize: 11,
              fontFamily: 'monospace',
              fontWeight: 600,
              color: dotColor,
              textTransform: 'uppercase',
            }}
          >
            {service.status}
          </span>
        </div>
      </div>

      {/* Last check */}
      <div style={{ fontSize: 11, fontFamily: 'monospace', color: NVIS.dim }}>
        Last check: {formatTimeAgo(service.lastCheck)}
      </div>

      {/* Latency + error rate */}
      <div style={{ display: 'flex', gap: 16, fontSize: 11, fontFamily: 'monospace' }}>
        {service.latencyMs !== undefined && (
          <span style={{ color: NVIS.dim }}>
            Latency:{' '}
            <span style={{ color: NVIS.white, fontVariantNumeric: 'tabular-nums' }}>
              {service.latencyMs}ms
            </span>
          </span>
        )}
        {service.errorRate !== undefined && service.errorRate > 0 && (
          <span style={{ color: NVIS.dim }}>
            Errors:{' '}
            <span
              style={{
                color: service.errorRate > 0.01 ? '#ffaa00' : NVIS.white,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {(service.errorRate * 100).toFixed(1)}%
            </span>
          </span>
        )}
      </div>

      {/* Details */}
      {service.details && (
        <div
          style={{
            fontSize: 10,
            fontFamily: 'monospace',
            color: NVIS.dim,
            borderTop: `1px solid ${NVIS.borderSolid}`,
            paddingTop: 8,
            lineHeight: 1.4,
          }}
        >
          {service.details}
        </div>
      )}
    </div>
  )
}

function EventRow({
  event,
  onSourceClick,
}: {
  event: MonitorEvent
  onSourceClick?: (source: string) => void
}) {
  const levelColor = LEVEL_DOT_COLORS[event.level]

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
        padding: '8px 0',
        borderBottom: `1px solid rgba(30,37,45,0.5)`,
        fontSize: 12,
        fontFamily: 'monospace',
      }}
    >
      {/* Timestamp */}
      <span
        style={{
          flexShrink: 0,
          width: 72,
          color: NVIS.dim,
          fontSize: 11,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {formatTimestamp(event.timestamp)}
      </span>

      {/* Level dot */}
      <span
        style={{
          flexShrink: 0,
          width: 8,
          height: 8,
          borderRadius: '50%',
          backgroundColor: levelColor,
          display: 'inline-block',
          marginTop: 3,
        }}
        aria-label={event.level}
      />

      {/* Source */}
      <span
        style={{
          flexShrink: 0,
          width: 160,
          color: NVIS.accent,
          cursor: onSourceClick ? 'pointer' : 'default',
          textDecoration: onSourceClick ? 'none' : 'none',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        onClick={() => onSourceClick?.(event.source)}
        title={event.source}
      >
        {event.source}
      </span>

      {/* Message */}
      <span style={{ flex: 1, color: NVIS.white, lineHeight: 1.4 }}>
        {event.message}
      </span>
    </div>
  )
}

// --- Main Component ---

export default function MonitorView() {
  const [services, setServices] = useState<MonitorService[]>(MOCK_SERVICES)
  const [events, setEvents] = useState<MonitorEvent[]>(MOCK_EVENTS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('All')

  useEffect(() => {
    async function fetchHealth() {
      // Initial data is already set from MOCK_SERVICES/MOCK_EVENTS
      setLoading(false)
      // Try embry-memory health to enrich with live data
      try {
        const health = await checkHealth()
        if (health.status) {
          // Enrich first service card with live health data
          const liveServices: MonitorService[] = MOCK_SERVICES.map((svc) => {
            if (svc.name === 'learn-datalake' || svc.name === 'arangodb') {
              return {
                ...svc,
                status: health.status === 'ok' || health.status === 'healthy' ? 'healthy' as const : 'degraded' as const,
                lastCheck: new Date().toISOString(),
                details: health.collections
                  ? `${health.collections.length} collections, uptime ${Math.round((health.uptime_seconds ?? 0) / 3600)}h`
                  : svc.details,
              }
            }
            return svc
          })
          setServices(liveServices)
          // Prepend a live health event
          const liveEvent: MonitorEvent = {
            timestamp: new Date().toISOString(),
            source: 'embry-memory',
            level: 'info',
            message: `Health check: ${health.status}, version ${health.version ?? 'unknown'}, uptime ${Math.round((health.uptime_seconds ?? 0) / 3600)}h`,
          }
          setEvents([liveEvent, ...MOCK_EVENTS])
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Memory service unreachable')
      }
    }
    fetchHealth()

    // V10.3: Auto-refresh every 60 seconds
    const interval = setInterval(() => {
      fetchHealth()
    }, 60_000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#999', fontFamily: 'monospace', fontSize: 13 }}>
        Loading...
      </div>
    )
  }

  const filteredEvents =
    levelFilter === 'All'
      ? events
      : events.filter((e) => e.level === levelFilter)

  // Counts for filter chips
  const infoCt = events.filter((e) => e.level === 'info').length
  const warnCt = events.filter((e) => e.level === 'warn').length
  const errorCt = events.filter((e) => e.level === 'error').length

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
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 24px',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: 14,
            fontWeight: 600,
            fontFamily: 'monospace',
            color: NVIS.white,
          }}
        >
          System Monitor
        </span>
        <span
          style={{
            fontSize: 11,
            fontFamily: 'monospace',
            color: NVIS.dim,
          }}
        >
          {services.filter((s) => s.status === 'healthy').length}/{services.length} services healthy
        </span>
      </div>

      {/* Status Grid (~60% height) */}
      <div
        style={{
          flex: '0 0 auto',
          padding: '0 24px 16px',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 12,
          }}
        >
          {services.map((svc) => (
            <ServiceCard key={svc.name} service={svc} />
          ))}
        </div>
      </div>

      {/* Event Log (~40% height) */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          padding: '0 24px 24px',
          minHeight: 0,
        }}
      >
        <div
          style={{
            backgroundColor: NVIS.surface,
            border: `1px solid ${NVIS.borderSolid}`,
            borderRadius: 8,
            padding: 20,
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
          }}
        >
          {/* Event log header + filter chips */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 12,
              flexShrink: 0,
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
              Event Log
            </h3>
            <div
              role="radiogroup"
              aria-label="Filter events by level"
              style={{
                display: 'flex',
                gap: 2,
                backgroundColor: NVIS.surface2,
                borderRadius: 4,
                padding: 2,
              }}
            >
              {(
                [
                  { value: 'All' as LevelFilter, label: `All (${events.length})` },
                  { value: 'info' as LevelFilter, label: `Info (${infoCt})` },
                  { value: 'warn' as LevelFilter, label: `Warn (${warnCt})` },
                  { value: 'error' as LevelFilter, label: `Error (${errorCt})` },
                ] as const
              ).map((f) => (
                <button
                  key={f.value}
                  role="radio"
                  aria-checked={levelFilter === f.value}
                  onClick={() => setLevelFilter(f.value)}
                  style={{
                    padding: '2px 10px',
                    fontSize: 10,
                    fontFamily: 'monospace',
                    fontWeight: 500,
                    border: 'none',
                    borderRadius: 3,
                    cursor: 'pointer',
                    backgroundColor:
                      levelFilter === f.value ? 'rgba(74,158,255,0.15)' : 'transparent',
                    color: levelFilter === f.value ? NVIS.accent : NVIS.dim,
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Scrollable event list */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              minHeight: 0,
            }}
          >
            {filteredEvents.length === 0 ? (
              <div
                style={{
                  padding: 20,
                  textAlign: 'center',
                  color: NVIS.dim,
                  fontSize: 12,
                  fontFamily: 'monospace',
                }}
              >
                No events match the selected filter
              </div>
            ) : (
              filteredEvents.map((evt, i) => (
                <EventRow key={`${evt.timestamp}-${i}`} event={evt} />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
