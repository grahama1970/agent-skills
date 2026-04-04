import { useState, useEffect, useMemo } from 'react'
import { NVIS } from '../theme'
import { loadProviders } from '../loader'
import { recallDocuments } from '../api/client'
import type { ProviderInfo } from '../types'

// ── helpers ───────────────────────────────────────────────────

const FAMILY_COLORS: Record<string, string> = {
  document:    '#4a9eff',
  pdf:         '#4a9eff',
  markup:      NVIS.green,
  web:         NVIS.green,
  data:        NVIS.amber,
  spreadsheet: '#b388ff',
  image:       '#00e5ff',
  presentation:'#f97316',
}

function familyColor(family: string): string {
  return FAMILY_COLORS[family] ?? NVIS.dim
}

function formatRate(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`
}

function formatTime(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function rateColor(rate: number): string {
  if (rate >= 0.95) return NVIS.green
  if (rate >= 0.8) return NVIS.amber
  return NVIS.red
}

function rateCellBg(rate: number): string {
  if (rate >= 0.95) return 'rgba(0,255,136,0.06)'
  if (rate >= 0.8) return 'rgba(255,170,0,0.06)'
  return 'rgba(255,68,68,0.06)'
}

// Sort providers: pdf first, then by family, then by extraction count desc
function sortedProviders(providers: ProviderInfo[]): ProviderInfo[] {
  return [...providers].sort((a, b) => {
    if (a.family === 'pdf' && b.family !== 'pdf') return -1
    if (b.family === 'pdf' && a.family !== 'pdf') return 1
    if (a.family !== b.family) return a.family.localeCompare(b.family)
    return b.extraction_count - a.extraction_count
  })
}

// ── sub-components ────────────────────────────────────────────

function FamilyDot({ family }: { family: string }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: familyColor(family),
        display: 'inline-block',
        flexShrink: 0,
      }}
      aria-hidden="true"
    />
  )
}

function ExtBadges({ extensions }: { extensions: string[] }) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {extensions.map((ext) => (
        <span
          key={ext}
          style={{
            display: 'inline-block',
            background: `${NVIS.accent}14`,
            border: `1px solid ${NVIS.accent}26`,
            borderRadius: 3,
            padding: '2px 8px',
            fontSize: 12,
            color: NVIS.accent,
            letterSpacing: '0.02em',
          }}
        >
          .{ext}
        </span>
      ))}
    </div>
  )
}

const thStyle: React.CSSProperties = {
  background: NVIS.surface,
  fontSize: 11,
  fontWeight: 500,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: NVIS.dim,
  textAlign: 'left',
  padding: '12px 20px',
  borderBottom: `1px solid ${NVIS.borderSolid}`,
  whiteSpace: 'nowrap',
}

const tdStyle: React.CSSProperties = {
  padding: '11px 20px',
  borderBottom: `1px solid ${NVIS.borderSolid}`,
  whiteSpace: 'nowrap',
  verticalAlign: 'middle',
  fontSize: 13,
}

function ProvidersTable({
  providers,
}: {
  providers: ProviderInfo[]
}) {
  const sorted = useMemo(() => sortedProviders(providers), [providers])

  // Group by family to alternate row background
  let prevFamily = ''
  let groupToggle = false

  return (
    <table
      style={{
        width: '100%',
        borderCollapse: 'separate',
        borderSpacing: 0,
        border: `1px solid ${NVIS.borderSolid}`,
        borderRadius: 6,
        overflow: 'hidden',
      }}
      aria-label="File type providers"
    >
      <thead>
        <tr>
          <th style={{ ...thStyle, width: 160 }}>Family</th>
          <th style={{ ...thStyle, width: 240 }}>Provider</th>
          <th style={thStyle}>Extensions</th>
          <th style={{ ...thStyle, width: 160, textAlign: 'right' }}>
            Success Rate
          </th>
          <th style={{ ...thStyle, width: 130, textAlign: 'right' }}>
            Avg Time
          </th>
        </tr>
      </thead>
      <tbody>
        {sorted.length === 0 ? (
          <tr>
            <td
              colSpan={5}
              style={{ ...tdStyle, textAlign: 'center', color: NVIS.dim, borderBottom: 'none' }}
            >
              No provider data
            </td>
          </tr>
        ) : (
          sorted.map((p) => {
            const isNewGroup = p.family !== prevFamily
            if (isNewGroup) {
              groupToggle = !groupToggle
              prevFamily = p.family
            }
            const rowBg = groupToggle ? NVIS.surface : NVIS.surface2

            return (
              <tr
                key={p.class_name}
                style={{ background: rowBg }}
                onMouseEnter={(e) => (e.currentTarget.style.background = `${NVIS.accent}0a`)}
                onMouseLeave={(e) => (e.currentTarget.style.background = rowBg)}
              >
                <td style={{ ...tdStyle, borderTop: isNewGroup ? `1px solid ${NVIS.borderSolid}` : undefined }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <FamilyDot family={p.family} />
                    <span style={{ color: NVIS.dim }}>{p.family}</span>
                  </div>
                </td>
                <td
                  style={{
                    ...tdStyle,
                    color: NVIS.white,
                    fontWeight: 500,
                    borderTop: isNewGroup ? `1px solid ${NVIS.borderSolid}` : undefined,
                  }}
                >
                  {p.name}
                </td>
                <td
                  style={{
                    ...tdStyle,
                    borderTop: isNewGroup ? `1px solid ${NVIS.borderSolid}` : undefined,
                  }}
                >
                  <ExtBadges extensions={p.extensions} />
                </td>
                <td
                  style={{
                    ...tdStyle,
                    textAlign: 'right',
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: 16,
                    color: rateColor(p.success_rate),
                    backgroundColor: rateCellBg(p.success_rate),
                    borderTop: isNewGroup ? `1px solid ${NVIS.borderSolid}` : undefined,
                  }}
                >
                  {formatRate(p.success_rate)}
                </td>
                <td
                  style={{
                    ...tdStyle,
                    textAlign: 'right',
                    fontVariantNumeric: 'tabular-nums',
                    color: NVIS.dim,
                    borderTop: isNewGroup ? `1px solid ${NVIS.borderSolid}` : undefined,
                  }}
                >
                  {formatTime(p.avg_time_ms)}
                </td>
              </tr>
            )
          })
        )}
      </tbody>
    </table>
  )
}

function Legend({ providers }: { providers: ProviderInfo[] }) {
  const families = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const p of providers) {
      if (!seen.has(p.family)) {
        seen.add(p.family)
        result.push(p.family)
      }
    }
    return result.sort()
  }, [providers])

  if (families.length === 0) return null

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 28,
        marginTop: 20,
        padding: '14px 20px',
        background: NVIS.surface,
        border: `1px solid ${NVIS.borderSolid}`,
        borderRadius: 6,
        width: 'fit-content',
      }}
      aria-label="Family color legend"
    >
      {families.map((f) => (
        <div
          key={f}
          style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: NVIS.dim }}
        >
          <FamilyDot family={f} />
          <span>{f}</span>
        </div>
      ))}
    </div>
  )
}

// ── main component ────────────────────────────────────────────

export default function ProvidersView() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      const data = await loadProviders()
      if (cancelled) return
      setProviders(data)
      setLoading(false)

      // Try to enrich with /memory data
      try {
        const result = await recallDocuments('file type extraction providers')
        if (!cancelled && result.results && result.results.length > 0) {
          console.log('[ProvidersView] /memory returned', result.results.length, 'results')
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Memory service unreachable')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) {
    return (
      <div style={{ padding: '32px 48px', color: NVIS.dim, fontSize: 13, fontFamily: 'monospace' }}>
        Loading providers...
      </div>
    )
  }

  if (providers.length === 0) {
    return (
      <div style={{ padding: '32px 48px', color: NVIS.dim, fontSize: 13, fontFamily: 'monospace' }}>
        {error && (
          <div style={{ background: '#1a0000', border: '1px solid #ff4444', borderRadius: 4, padding: '8px 12px', margin: '0 0 12px', color: '#ff4444', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
            ✗ {error}
          </div>
        )}
        No provider data available. Ensure the API is running or sample data exists at /sample/providers.json.
      </div>
    )
  }

  return (
    <main
      style={{
        padding: '32px 48px',
        fontFamily: 'monospace',
        backgroundColor: NVIS.bg,
        color: NVIS.white,
        minHeight: '100%',
      }}
    >
      <h1
        style={{
          fontSize: 14,
          fontWeight: 600,
          color: NVIS.white,
          marginBottom: 24,
        }}
      >
        File Type Providers{' '}
        <span style={{ color: NVIS.dim, fontWeight: 400 }}>
          &mdash; {providers.length} registered
        </span>
      </h1>

      {error && (
        <div style={{ background: '#1a0000', border: '1px solid #ff4444', borderRadius: 4, padding: '8px 12px', margin: '0 0 16px', color: '#ff4444', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
          ✗ {error}
        </div>
      )}

      <ProvidersTable providers={providers} />

      <Legend providers={providers} />
    </main>
  )
}
