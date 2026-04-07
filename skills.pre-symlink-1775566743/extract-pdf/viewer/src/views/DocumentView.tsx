import { useEffect, useState } from 'react'
import { NVIS } from '../App'
import { loadExtractionData } from '../loader'
import type { ExtractionResult, Block, Section } from '../types'
import { TaxonomyChipList } from '../components/TaxonomyChip'

// -- Helpers ------------------------------------------------------------------

const BLOCK_TYPE_COLORS: Record<string, string> = {
  Header: NVIS.accent,
  Body: 'rgba(255,255,255,0.65)',
  Boilerplate: NVIS.amber,
  Table: NVIS.green,
  Figure: NVIS.green,
  Caption: NVIS.amber,
  Footnote: 'rgba(255,255,255,0.65)',
}

function badgeStyle(color: string): React.CSSProperties {
  return {
    fontSize: 10,
    paddingLeft: 6,
    paddingRight: 6,
    paddingTop: 2,
    paddingBottom: 2,
    borderRadius: 4,
    fontWeight: 500,
    color,
    backgroundColor: color + '1a', // ~10% opacity hex
    whiteSpace: 'nowrap' as const,
  }
}

function verdictColor(v: string): string {
  if (v === 'Accept') return NVIS.green
  if (v === 'Reject') return NVIS.red
  if (v === 'Escalate') return NVIS.amber
  return 'rgba(255,255,255,0.65)'
}

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}

// -- Sub-components -----------------------------------------------------------

function ProfilePane({ data }: { data: ExtractionResult }) {
  const p = data.profile
  const rows: [string, string | number | undefined][] = [
    ['Domain', p.domain],
    ['Preset', p.preset],
    ['Complexity', p.complexity_score.toFixed(2)],
    ['Pages', p.page_count],
    ['Strategy', p.strategy],
    ['Primary font', p.primary_font],
    ['Font size', p.primary_font_size],
    ['Scanned', p.is_scanned ? 'Yes' : 'No'],
    ['Engine', `${data.engine} ${data.engine_version}`],
  ]

  const taxonomyTags = (data.taxonomy_tags ?? []).map((t) => t.text)

  return (
    <div className="p-4">
      <h2
        className="text-xs font-semibold uppercase tracking-widest mb-4"
        style={{ color: 'white' }}
      >
        Profile
      </h2>
      <div className="flex flex-col gap-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between text-xs">
            <span style={{ color: NVIS.accent }}>{label}</span>
            <span style={{ color: 'rgba(255,255,255,0.7)' }}>
              {value ?? '--'}
            </span>
          </div>
        ))}
      </div>

      {/* Document-level taxonomy tags */}
      {taxonomyTags.length > 0 && (
        <div className="mt-4">
          <h3
            className="text-xs font-semibold uppercase tracking-widest mb-2"
            style={{ color: 'white' }}
          >
            Taxonomy
          </h3>
          <TaxonomyChipList tags={taxonomyTags} />
        </div>
      )}
    </div>
  )
}

function BlockItem({ block }: { block: Block }) {
  const color = BLOCK_TYPE_COLORS[block.block_type] ?? 'rgba(255,255,255,0.5)'
  const blockTags = block.taxonomy_tags ?? []
  return (
    <div
      className="mb-2"
      style={{ borderBottom: `1px solid ${NVIS.border}`, paddingBottom: 8 }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span style={badgeStyle(color)}>{block.block_type}</span>
        <span className="text-[10px]" style={{ color: 'rgba(255,255,255,0.6)' }}>
          p.{block.page}
        </span>
        {block.header_disposition && (
          <span style={badgeStyle(verdictColor(block.header_disposition))}>
            {block.header_disposition}
          </span>
        )}
      </div>
      {blockTags.length > 0 && (
        <div className="mb-1">
          <TaxonomyChipList tags={blockTags} />
        </div>
      )}
      <p className="text-xs leading-relaxed" style={{ color: 'rgba(255,255,255,0.8)' }}>
        {block.text.length > 200 ? block.text.slice(0, 200) + '...' : block.text}
      </p>
    </div>
  )
}

function SectionItem({ section }: { section: Section }) {
  return (
    <div
      className="py-1.5 text-xs"
      style={{
        paddingLeft: section.level * 16,
        borderBottom: `1px solid ${NVIS.border}`,
      }}
    >
      <div className="flex items-center gap-2">
        {section.section_number && (
          <span style={{ color: NVIS.accent, fontWeight: 600 }}>
            {section.section_number}
          </span>
        )}
        <span style={{ color: 'rgba(255,255,255,0.85)' }}>
          {section.title}
        </span>
        <span className="ml-auto" style={{ color: 'rgba(255,255,255,0.6)' }}>
          pp.{section.page_start}
          {section.page_end !== section.page_start && `–${section.page_end}`}
        </span>
      </div>
    </div>
  )
}

function ContentPane({ data }: { data: ExtractionResult }) {
  return (
    <div className="p-4">
      {/* Blocks */}
      <h2
        className="text-xs font-semibold uppercase tracking-widest mb-3"
        style={{ color: 'white' }}
      >
        Blocks ({data.blocks.length})
      </h2>
      {data.blocks.map((b) => (
        <BlockItem key={b.id} block={b} />
      ))}

      {/* Sections */}
      <h2
        className="text-xs font-semibold uppercase tracking-widest mt-6 mb-3"
        style={{ color: 'white' }}
      >
        Sections ({data.sections.length})
      </h2>
      {data.sections.map((s, i) => (
        <SectionItem key={i} section={s} />
      ))}

      {/* Tables */}
      {data.tables.length > 0 && (
        <>
          <h2
            className="text-xs font-semibold uppercase tracking-widest mt-6 mb-3"
            style={{ color: 'white' }}
          >
            Tables ({data.tables.length})
          </h2>
          {data.tables.map((t, i) => (
            <div
              key={i}
              className="mb-2 text-xs flex items-center gap-2"
              style={{ borderBottom: `1px solid ${NVIS.border}`, paddingBottom: 8 }}
            >
              <span style={badgeStyle(NVIS.green)}>Table</span>
              <span style={{ color: 'rgba(255,255,255,0.7)' }}>
                p.{t.page_number} &middot; {t.rows.length} rows &middot; {t.strategy}
              </span>
              {t.score != null && (
                <span className="ml-auto" style={{ color: 'rgba(255,255,255,0.6)' }}>
                  {pct(t.score)}
                </span>
              )}
            </div>
          ))}
        </>
      )}

      {/* Figures */}
      {data.figures.length > 0 && (
        <>
          <h2
            className="text-xs font-semibold uppercase tracking-widest mt-6 mb-3"
            style={{ color: 'white' }}
          >
            Figures ({data.figures.length})
          </h2>
          {data.figures.map((f) => (
            <div
              key={f.figure_id}
              className="mb-2 text-xs flex items-center gap-2"
              style={{ borderBottom: `1px solid ${NVIS.border}`, paddingBottom: 8 }}
            >
              <span style={badgeStyle(NVIS.green)}>Figure</span>
              <span style={{ color: 'rgba(255,255,255,0.7)' }}>
                {f.figure_id} &middot; p.{f.page}
              </span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

function CascadePane({ data }: { data: ExtractionResult }) {
  const decisions = data.cascade_decisions ?? []
  const tags = data.taxonomy_tags ?? []

  // Header disposition summary from blocks
  const dispositions = data.blocks.reduce(
    (acc, b) => {
      if (b.header_disposition) {
        acc[b.header_disposition] = (acc[b.header_disposition] || 0) + 1
      }
      return acc
    },
    {} as Record<string, number>,
  )

  return (
    <div className="p-4">
      {/* Cascade Decisions */}
      <h2
        className="text-xs font-semibold uppercase tracking-widest mb-3"
        style={{ color: 'white' }}
      >
        Cascade Decisions ({decisions.length})
      </h2>
      {decisions.map((d, i) => (
        <div
          key={i}
          className="mb-3"
          style={{ borderBottom: `1px solid ${NVIS.border}`, paddingBottom: 8 }}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium" style={{ color: NVIS.accent }}>
              {d.decision_point}
            </span>
            <span style={badgeStyle(verdictColor(d.predicted))}>
              {d.predicted}
            </span>
            <span className="ml-auto text-xs" style={{ color: 'rgba(255,255,255,0.65)' }}>
              {pct(d.confidence)} &middot; tier {d.tier}
            </span>
          </div>
          {d.features && (
            <div className="flex flex-wrap gap-1 mt-1">
              {Object.entries(d.features).map(([k, v]) => (
                <span
                  key={k}
                  className="text-[10px]"
                  style={{
                    color: 'rgba(255,255,255,0.65)',
                    backgroundColor: 'rgba(255,255,255,0.05)',
                    padding: '1px 5px',
                    borderRadius: 3,
                  }}
                >
                  {k}: {String(v)}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}

      {/* Header Disposition Summary */}
      {Object.keys(dispositions).length > 0 && (
        <>
          <h2
            className="text-xs font-semibold uppercase tracking-widest mt-6 mb-3"
            style={{ color: 'white' }}
          >
            Header Dispositions
          </h2>
          <div className="flex gap-3 mb-4">
            {Object.entries(dispositions).map(([disp, count]) => (
              <div key={disp} className="flex items-center gap-1.5">
                <span style={badgeStyle(verdictColor(disp))}>{disp}</span>
                <span className="text-xs" style={{ color: 'rgba(255,255,255,0.6)' }}>
                  {count}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Taxonomy Tags */}
      {tags.length > 0 && (
        <>
          <h2
            className="text-xs font-semibold uppercase tracking-widest mt-6 mb-3"
            style={{ color: 'white' }}
          >
            Taxonomy Tags ({tags.length})
          </h2>
          <TaxonomyChipList tags={tags.map((t) => t.text)} />
        </>
      )}
    </div>
  )
}

// -- Main export --------------------------------------------------------------

export default function DocumentView() {
  const [data, setData] = useState<ExtractionResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadExtractionData()
      .then((result) => {
        if (result) {
          setData(result)
        } else {
          setError('Failed to load extraction data.')
        }
      })
      .catch((err) => {
        setError(String(err))
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-xs" style={{ color: 'rgba(255,255,255,0.65)' }}>
          Loading...
        </span>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-xs" style={{ color: NVIS.red }}>
          {error ?? 'No data available.'}
        </span>
      </div>
    )
  }

  return (
    <>
      {/* Left pane — 30% */}
      <div
        className="overflow-y-auto"
        style={{
          width: '30%',
          borderRight: `1px solid ${NVIS.border}`,
        }}
      >
        <ProfilePane data={data} />
      </div>

      {/* Center pane — 35% */}
      <div
        className="overflow-y-auto"
        style={{
          width: '35%',
          borderRight: `1px solid ${NVIS.border}`,
        }}
      >
        <ContentPane data={data} />
      </div>

      {/* Right pane — 35% */}
      <div
        className="overflow-y-auto"
        style={{
          width: '35%',
        }}
      >
        <CascadePane data={data} />
      </div>
    </>
  )
}
