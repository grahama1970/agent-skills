import { useState } from 'react'
import { NVIS } from '../App'
import { TaxonomyChipList } from '../components/TaxonomyChip'

// --- Sample data -----------------------------------------------------------

interface DecisionPointData {
  total: number
  firstDate: string
  lastDate: string
  dispositions: { Accept: number; Reject: number; Escalate: number }
  confidences: [number, number, number, number, number] // 5 bins
  agreementRate: number
  samples: number
}

const SAMPLE_CASCADE_DATA: Record<string, DecisionPointData> = {
  'header-verdict': {
    total: 529340,
    firstDate: '2026-03-10',
    lastDate: '2026-03-11',
    dispositions: { Accept: 123870, Reject: 330850, Escalate: 74620 },
    confidences: [2100, 8400, 22300, 156200, 340340],
    agreementRate: 0.923,
    samples: 529340,
  },
  'pdf-profile': {
    total: 5639,
    firstDate: '2026-03-10',
    lastDate: '2026-03-11',
    dispositions: { Accept: 5639, Reject: 0, Escalate: 0 },
    confidences: [0, 0, 120, 1800, 3719],
    agreementRate: 0.97,
    samples: 5639,
  },
  'pdf-strategy': {
    total: 5639,
    firstDate: '2026-03-10',
    lastDate: '2026-03-11',
    dispositions: { Accept: 4200, Reject: 800, Escalate: 639 },
    confidences: [50, 200, 500, 2100, 2789],
    agreementRate: 0.91,
    samples: 5639,
  },
}

const DECISION_POINTS = ['header-verdict', 'pdf-profile', 'pdf-strategy'] as const

const TAXONOMY_TAGS = [
  'mind:technical',
  'mind:process',
  'mind:analytical',
  'heart:trust',
  'heart:safety',
  'heart:compliance',
]

// --- Helpers ----------------------------------------------------------------

function wilsonLowerBound(p: number, n: number): number {
  if (n === 0) return 0
  const z = 2.576 // 99% CI
  return p - z * Math.sqrt((p * (1 - p)) / n)
}

function promotionStatus(
  wilson: number,
  n: number,
): { label: string; color: string } {
  if (n < 50) return { label: 'Early', color: NVIS.amber }
  if (wilson < 0.85 || n < 200) return { label: 'Learning', color: NVIS.accent }
  return { label: 'Ready', color: NVIS.green }
}

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

// --- Sub-components ---------------------------------------------------------

function HorizontalBar({
  value,
  max,
  color,
  label,
}: {
  value: number
  max: number
  color: string
  label: string
}) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="flex items-center gap-2 mb-2">
      <span
        className="text-xs shrink-0"
        style={{ color: 'rgba(255,255,255,0.6)', width: 60, textAlign: 'right' }}
      >
        {label}
      </span>
      <div className="flex-1" style={{ height: 18, backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: 3 }}>
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            backgroundColor: color,
            borderRadius: 3,
            minWidth: value > 0 ? 2 : 0,
            transition: 'width 0.3s ease',
          }}
        />
      </div>
      <span className="text-xs shrink-0" style={{ color: 'rgba(255,255,255,0.65)', width: 50 }}>
        {formatCount(value)}
      </span>
    </div>
  )
}

// --- Main component ---------------------------------------------------------

export default function CascadeView() {
  const [selected, setSelected] = useState<string>('header-verdict')
  const data = SAMPLE_CASCADE_DATA[selected]

  const wilson = wilsonLowerBound(data.agreementRate, data.samples)
  const status = promotionStatus(wilson, data.samples)

  // Disposition max for bar scaling
  const dispMax = Math.max(
    data.dispositions.Accept,
    data.dispositions.Reject,
    data.dispositions.Escalate,
    1,
  )

  // Confidence bin max
  const confMax = Math.max(...data.confidences, 1)

  // Class balance totals
  const dispTotal =
    data.dispositions.Accept + data.dispositions.Reject + data.dispositions.Escalate

  const samplesProgress = Math.min(data.samples / 200, 1.0)

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* ── Left pane (30%) ── Decision point selector + stats ── */}
      <div
        className="overflow-y-auto"
        style={{ width: '30%', borderRight: `1px solid ${NVIS.border}` }}
      >
        <div className="p-4">
          <h2
            className="text-xs font-semibold uppercase tracking-widest mb-3"
            style={{ color: 'white' }}
          >
            Decision Points
          </h2>

          {DECISION_POINTS.map((dp) => {
            const d = SAMPLE_CASCADE_DATA[dp]
            const isActive = dp === selected
            return (
              <button
                key={dp}
                onClick={() => setSelected(dp)}
                className="w-full text-left rounded px-3 py-3 mb-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#4a9eff]"
                style={{
                  backgroundColor: isActive
                    ? `rgba(74,158,255,0.10)`
                    : 'transparent',
                  border: isActive
                    ? `1px solid rgba(74,158,255,0.25)`
                    : `1px solid transparent`,
                  cursor: 'pointer',
                }}
              >
                <div
                  className="text-sm font-medium"
                  style={{ color: isActive ? NVIS.accent : 'rgba(255,255,255,0.7)' }}
                >
                  {dp}
                </div>
                <div
                  className="text-2xl font-bold mt-1"
                  style={{ color: 'white' }}
                >
                  {formatCount(d.total)}
                </div>
                <div
                  className="text-xs mt-1"
                  style={{ color: 'rgba(255,255,255,0.6)' }}
                >
                  {d.firstDate} — {d.lastDate}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Center pane (35%) ── Distribution visualizations ── */}
      <div
        className="overflow-y-auto"
        style={{ width: '35%', borderRight: `1px solid ${NVIS.border}` }}
      >
        <div className="p-4">
          {/* Disposition histogram */}
          <h2
            className="text-xs font-semibold uppercase tracking-widest mb-3"
            style={{ color: 'white' }}
          >
            Disposition
          </h2>
          <HorizontalBar value={data.dispositions.Accept} max={dispMax} color={NVIS.green} label="Accept" />
          <HorizontalBar value={data.dispositions.Reject} max={dispMax} color={NVIS.red} label="Reject" />
          <HorizontalBar value={data.dispositions.Escalate} max={dispMax} color={NVIS.amber} label="Escalate" />

          {/* Confidence distribution */}
          <h2
            className="text-xs font-semibold uppercase tracking-widest mb-3 mt-6"
            style={{ color: 'white' }}
          >
            Confidence Distribution
          </h2>
          {(['0–0.2', '0.2–0.4', '0.4–0.6', '0.6–0.8', '0.8–1.0'] as const).map(
            (label, i) => (
              <HorizontalBar
                key={label}
                value={data.confidences[i]}
                max={confMax}
                color={NVIS.accent}
                label={label}
              />
            ),
          )}

          {/* Class balance stacked bar */}
          <h2
            className="text-xs font-semibold uppercase tracking-widest mb-3 mt-6"
            style={{ color: 'white' }}
          >
            Class Balance
          </h2>
          <div
            className="flex overflow-hidden"
            style={{ height: 22, borderRadius: 3, backgroundColor: 'rgba(255,255,255,0.05)' }}
          >
            {dispTotal > 0 && (
              <>
                <div
                  style={{
                    width: `${(data.dispositions.Accept / dispTotal) * 100}%`,
                    backgroundColor: NVIS.green,
                    height: '100%',
                    transition: 'width 0.3s ease',
                  }}
                />
                <div
                  style={{
                    width: `${(data.dispositions.Reject / dispTotal) * 100}%`,
                    backgroundColor: NVIS.red,
                    height: '100%',
                    transition: 'width 0.3s ease',
                  }}
                />
                <div
                  style={{
                    width: `${(data.dispositions.Escalate / dispTotal) * 100}%`,
                    backgroundColor: NVIS.amber,
                    height: '100%',
                    transition: 'width 0.3s ease',
                  }}
                />
              </>
            )}
          </div>
          <div className="flex justify-between mt-1">
            {(
              [
                ['Accept', NVIS.green],
                ['Reject', NVIS.red],
                ['Escalate', NVIS.amber],
              ] as const
            ).map(([lbl, clr]) => (
              <span key={lbl} className="text-xs flex items-center gap-1">
                <span
                  style={{
                    display: 'inline-block',
                    width: 8,
                    height: 8,
                    borderRadius: 2,
                    backgroundColor: clr,
                  }}
                />
                <span style={{ color: 'rgba(255,255,255,0.65)' }}>{lbl}</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* ── Right pane (35%) ── Promotion metrics ── */}
      <div className="overflow-y-auto" style={{ width: '35%' }}>
        <div className="p-4">
          <h2
            className="text-xs font-semibold uppercase tracking-widest mb-3"
            style={{ color: 'white' }}
          >
            Promotion Metrics
          </h2>

          {/* Promotion status badge */}
          <div className="flex items-center gap-2 mb-4">
            <span
              className="text-xs font-semibold px-2 py-1 rounded"
              style={{
                color: status.color,
                backgroundColor: `${status.color}1a`,
                border: `1px solid ${status.color}40`,
              }}
            >
              {status.label}
            </span>
          </div>

          {/* Agreement rate */}
          <div className="mb-4">
            <div className="text-xs" style={{ color: 'rgba(255,255,255,0.65)' }}>
              Agreement Rate
            </div>
            <div className="text-3xl font-bold" style={{ color: 'white' }}>
              {(data.agreementRate * 100).toFixed(1)}%
            </div>
          </div>

          {/* Wilson score */}
          <div className="mb-4">
            <div className="text-xs" style={{ color: 'rgba(255,255,255,0.65)' }}>
              Wilson Lower Bound (99% CI)
            </div>
            <div className="text-xl font-semibold" style={{ color: NVIS.accent }}>
              {wilson.toFixed(4)}
            </div>
          </div>

          {/* Samples progress */}
          <div className="mb-4">
            <div className="flex justify-between text-xs mb-1">
              <span style={{ color: 'rgba(255,255,255,0.65)' }}>
                Samples: {formatCount(data.samples)}
              </span>
              <span style={{ color: 'rgba(255,255,255,0.6)' }}>
                threshold: 200
              </span>
            </div>
            <div
              style={{
                height: 14,
                backgroundColor: 'rgba(255,255,255,0.05)',
                borderRadius: 3,
                position: 'relative',
              }}
            >
              {/* Filled portion */}
              <div
                style={{
                  width: `${samplesProgress * 100}%`,
                  height: '100%',
                  backgroundColor: status.color,
                  borderRadius: 3,
                  transition: 'width 0.3s ease',
                }}
              />
              {/* Threshold line at 200 (only visible when total > 200) */}
              {data.samples > 200 && (
                <div
                  style={{
                    position: 'absolute',
                    left: `${(200 / data.samples) * samplesProgress * 100}%`,
                    top: 0,
                    bottom: 0,
                    width: 2,
                    backgroundColor: 'rgba(255,255,255,0.65)',
                  }}
                />
              )}
            </div>
          </div>

          {/* Taxonomy tags */}
          <div className="mt-6">
            <div
              className="text-xs font-semibold uppercase tracking-widest mb-2"
              style={{ color: 'white' }}
            >
              Taxonomy
            </div>
            <TaxonomyChipList tags={TAXONOMY_TAGS} />
          </div>
        </div>
      </div>
    </div>
  )
}
