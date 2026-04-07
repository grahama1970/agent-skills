import { useState } from 'react'
import { NVIS } from '../App'
import { TaxonomyChipList } from '../components/TaxonomyChip'

interface ComparisonData {
  filename: string
  ratio: number
  oxide_blocks: number
  pymupdf_blocks: number
  oxide_sections: number
  pymupdf_sections: number
  oxide_lines: string[]
  pymupdf_lines: string[]
  missing_blocks: string[]
  extra_blocks: string[]
  disposition_changes: { text: string; old: string; new: string }[]
  taxonomy_tags?: string[]
}

const SAMPLE_COMPARISONS: ComparisonData[] = [
  {
    filename: 'NIST_SP_800-53r5.pdf',
    ratio: 0.968,
    oxide_blocks: 1205,
    pymupdf_blocks: 1180,
    oxide_sections: 48,
    pymupdf_sections: 45,
    oxide_lines: [
      'NIST Special Publication 800-53',
      'Revision 5',
      '',
      'Security and Privacy Controls',
      'for Information Systems and Organizations',
    ],
    pymupdf_lines: [
      'NIST Special Publication 800-53',
      'Revision 5',
      'Security and Privacy Controls',
      'for Information Systems and Organizations',
      '',
    ],
    missing_blocks: ['Footer: Page ii'],
    extra_blocks: ['Header: Table of Contents', 'Body: Appendix J summary'],
    disposition_changes: [
      { text: 'APPENDIX A', old: 'Reject', new: 'Accept' },
      { text: 'References', old: 'Escalate', new: 'Accept' },
    ],
    taxonomy_tags: ['heart:compliance', 'heart:trust', 'mind:technical'],
  },
  {
    filename: 'arxiv_2401.12345.pdf',
    ratio: 0.991,
    oxide_blocks: 87,
    pymupdf_blocks: 85,
    oxide_sections: 6,
    pymupdf_sections: 6,
    oxide_lines: ['Abstract', 'We present a novel approach...'],
    pymupdf_lines: ['Abstract', 'We present a novel approach...'],
    missing_blocks: [],
    extra_blocks: ['Figure: Fig. 3 caption'],
    disposition_changes: [],
    taxonomy_tags: ['mind:analytical', 'mind:process'],
  },
]

type DiffLineKind = 'match' | 'added' | 'removed'

interface DiffLine {
  kind: DiffLineKind
  oxideLineNo?: number
  pymupdfLineNo?: number
  text: string
}

function computeDiff(oxideLines: string[], pymupdfLines: string[]): DiffLine[] {
  const result: DiffLine[] = []
  let oi = 0
  let pi = 0

  while (oi < oxideLines.length && pi < pymupdfLines.length) {
    if (oxideLines[oi] === pymupdfLines[pi]) {
      result.push({ kind: 'match', oxideLineNo: oi + 1, pymupdfLineNo: pi + 1, text: oxideLines[oi] })
      oi++
      pi++
    } else {
      // Look ahead to find a match
      let foundOxide = -1
      let foundPymupdf = -1
      for (let k = 1; k <= 5; k++) {
        if (foundPymupdf < 0 && pi + k < pymupdfLines.length && oxideLines[oi] === pymupdfLines[pi + k]) {
          foundPymupdf = pi + k
        }
        if (foundOxide < 0 && oi + k < oxideLines.length && oxideLines[oi + k] === pymupdfLines[pi]) {
          foundOxide = oi + k
        }
      }

      if (foundPymupdf >= 0 && (foundOxide < 0 || (foundPymupdf - pi) <= (foundOxide - oi))) {
        // Lines in pymupdf before the match are "removed" (in pymupdf but not oxide)
        for (let j = pi; j < foundPymupdf; j++) {
          result.push({ kind: 'removed', pymupdfLineNo: j + 1, text: pymupdfLines[j] })
        }
        pi = foundPymupdf
      } else if (foundOxide >= 0) {
        // Lines in oxide before the match are "added" (in oxide but not pymupdf)
        for (let j = oi; j < foundOxide; j++) {
          result.push({ kind: 'added', oxideLineNo: j + 1, text: oxideLines[j] })
        }
        oi = foundOxide
      } else {
        // No nearby match — emit both as change
        result.push({ kind: 'removed', pymupdfLineNo: pi + 1, text: pymupdfLines[pi] })
        result.push({ kind: 'added', oxideLineNo: oi + 1, text: oxideLines[oi] })
        oi++
        pi++
      }
    }
  }

  // Remaining oxide lines
  while (oi < oxideLines.length) {
    result.push({ kind: 'added', oxideLineNo: oi + 1, text: oxideLines[oi] })
    oi++
  }

  // Remaining pymupdf lines
  while (pi < pymupdfLines.length) {
    result.push({ kind: 'removed', pymupdfLineNo: pi + 1, text: pymupdfLines[pi] })
    pi++
  }

  return result
}

function qualityVerdict(ratio: number): { label: string; color: string } {
  if (ratio >= 0.98) return { label: 'Excellent', color: NVIS.green }
  if (ratio >= 0.95) return { label: 'Good', color: NVIS.accent }
  if (ratio >= 0.90) return { label: 'Acceptable', color: NVIS.amber }
  return { label: 'Needs Review', color: NVIS.red }
}

function DeltaBadge({ value }: { value: number }) {
  const color = value > 0 ? NVIS.green : value < 0 ? NVIS.red : 'rgba(255,255,255,0.65)'
  const prefix = value > 0 ? '+' : ''
  return (
    <span style={{ color, fontVariantNumeric: 'tabular-nums' }}>
      {prefix}{value}
    </span>
  )
}

export default function CompareView() {
  const [selectedIdx, setSelectedIdx] = useState(0)
  const selected = SAMPLE_COMPARISONS[selectedIdx]
  const diffLines = computeDiff(selected.oxide_lines, selected.pymupdf_lines)
  const verdict = qualityVerdict(selected.ratio)

  const dimText: React.CSSProperties = { color: 'rgba(255,255,255,0.65)' }
  const gutterStyle: React.CSSProperties = {
    ...dimText,
    width: 32,
    textAlign: 'right',
    paddingRight: 8,
    userSelect: 'none',
    flexShrink: 0,
  }

  return (
    <div className="flex flex-1 overflow-hidden" style={{ height: '100%' }}>
      {/* Left pane — PDF selector + metrics */}
      <div
        className="overflow-y-auto"
        style={{ width: '30%', borderRight: `1px solid ${NVIS.border}` }}
      >
        <div className="p-4">
          <h2
            className="text-xs font-semibold uppercase tracking-widest mb-3"
            style={{ color: 'white' }}
          >
            Quality Comparison
          </h2>

          <div className="flex flex-col gap-1">
            {SAMPLE_COMPARISONS.map((comp, idx) => {
              const isSelected = idx === selectedIdx
              const blockDelta = comp.oxide_blocks - comp.pymupdf_blocks
              const sectionDelta = comp.oxide_sections - comp.pymupdf_sections

              return (
                <button
                  key={comp.filename}
                  onClick={() => setSelectedIdx(idx)}
                  className="text-left rounded px-3 py-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#4a9eff]"
                  style={{
                    backgroundColor: isSelected ? 'rgba(74,158,255,0.10)' : 'transparent',
                    border: isSelected
                      ? `1px solid rgba(74,158,255,0.25)`
                      : '1px solid transparent',
                    cursor: 'pointer',
                  }}
                >
                  <div
                    className="text-xs font-medium truncate"
                    style={{ color: isSelected ? NVIS.accent : 'rgba(255,255,255,0.8)' }}
                  >
                    {comp.filename}
                  </div>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-xs" style={dimText}>
                      Match:{' '}
                      <span style={{ color: qualityVerdict(comp.ratio).color }}>
                        {(comp.ratio * 100).toFixed(1)}%
                      </span>
                    </span>
                    <span className="text-xs" style={dimText}>
                      Blocks: <DeltaBadge value={blockDelta} />
                    </span>
                    <span className="text-xs" style={dimText}>
                      Sections: <DeltaBadge value={sectionDelta} />
                    </span>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Summary metrics for selected */}
          <div
            className="mt-4 rounded p-3"
            style={{ border: `1px solid ${NVIS.border}`, backgroundColor: 'rgba(255,255,255,0.03)' }}
          >
            <div className="text-xs font-semibold mb-2" style={{ color: 'white' }}>
              {selected.filename}
            </div>
            <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-xs">
              <div style={dimText}>SequenceMatcher</div>
              <div style={{ color: verdict.color }}>{(selected.ratio * 100).toFixed(1)}%</div>

              <div style={dimText}>Block count (oxide)</div>
              <div style={{ color: 'white' }}>{selected.oxide_blocks}</div>

              <div style={dimText}>Block count (pymupdf)</div>
              <div style={{ color: 'white' }}>{selected.pymupdf_blocks}</div>

              <div style={dimText}>Block delta</div>
              <div><DeltaBadge value={selected.oxide_blocks - selected.pymupdf_blocks} /></div>

              <div style={dimText}>Section count (oxide)</div>
              <div style={{ color: 'white' }}>{selected.oxide_sections}</div>

              <div style={dimText}>Section count (pymupdf)</div>
              <div style={{ color: 'white' }}>{selected.pymupdf_sections}</div>

              <div style={dimText}>Section delta</div>
              <div><DeltaBadge value={selected.oxide_sections - selected.pymupdf_sections} /></div>
            </div>
          </div>
        </div>
      </div>

      {/* Center pane — Side-by-side text diff */}
      <div
        className="overflow-y-auto"
        style={{ width: '35%', borderRight: `1px solid ${NVIS.border}` }}
      >
        <div className="p-4">
          {/* Column headers */}
          <div className="flex gap-4 mb-3">
            <h2
              className="text-xs font-semibold uppercase tracking-widest flex-1"
              style={{ color: NVIS.accent }}
            >
              pdf_oxide
            </h2>
            <h2
              className="text-xs font-semibold uppercase tracking-widest flex-1"
              style={{ color: 'rgba(255,255,255,0.65)' }}
            >
              PyMuPDF
            </h2>
          </div>

          {/* Diff lines */}
          <div
            className="rounded overflow-hidden"
            style={{
              border: `1px solid ${NVIS.border}`,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              fontSize: 11,
              lineHeight: '20px',
            }}
          >
            {diffLines.map((line, i) => {
              let bg = 'transparent'
              if (line.kind === 'added') bg = 'rgba(0,255,136,0.08)'
              if (line.kind === 'removed') bg = 'rgba(255,68,68,0.08)'

              return (
                <div
                  key={i}
                  className="flex"
                  style={{ backgroundColor: bg, minHeight: 20 }}
                >
                  {/* Oxide gutter */}
                  <div style={gutterStyle}>
                    {line.oxideLineNo ?? ''}
                  </div>
                  {/* Pymupdf gutter */}
                  <div style={gutterStyle}>
                    {line.pymupdfLineNo ?? ''}
                  </div>
                  {/* Marker */}
                  <div
                    style={{
                      width: 16,
                      textAlign: 'center',
                      flexShrink: 0,
                      color: line.kind === 'added'
                        ? NVIS.green
                        : line.kind === 'removed'
                          ? NVIS.red
                          : 'rgba(255,255,255,0.2)',
                    }}
                  >
                    {line.kind === 'added' ? '+' : line.kind === 'removed' ? '-' : ' '}
                  </div>
                  {/* Text content */}
                  <div
                    className="flex-1 px-2 truncate"
                    style={{
                      color: line.kind === 'match' ? 'rgba(255,255,255,0.7)' : 'white',
                    }}
                  >
                    {line.text || '\u00A0'}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Right pane — Structural diff */}
      <div className="overflow-y-auto" style={{ width: '35%' }}>
        <div className="p-4">
          <h2
            className="text-xs font-semibold uppercase tracking-widest mb-3"
            style={{ color: 'white' }}
          >
            Structural Diff
          </h2>

          {/* Quality verdict badge */}
          <div className="mb-4">
            <span
              className="inline-block rounded px-2 py-1 text-xs font-semibold"
              style={{
                color: verdict.color,
                backgroundColor: verdict.color + '18',
                border: `1px solid ${verdict.color}40`,
              }}
            >
              {verdict.label} — {(selected.ratio * 100).toFixed(1)}%
            </span>
          </div>

          {/* Taxonomy tags */}
          {selected.taxonomy_tags && selected.taxonomy_tags.length > 0 && (
            <div className="mb-4">
              <h3
                className="text-xs font-semibold mb-2"
                style={{ color: 'rgba(255,255,255,0.7)' }}
              >
                Taxonomy Tags
              </h3>
              <TaxonomyChipList tags={selected.taxonomy_tags} />
            </div>
          )}

          {/* Missing blocks */}
          <div className="mb-4">
            <h3
              className="text-xs font-semibold mb-2"
              style={{ color: 'rgba(255,255,255,0.7)' }}
            >
              Missing blocks
              <span style={dimText}> (in PyMuPDF, not in pdf_oxide)</span>
            </h3>
            {selected.missing_blocks.length === 0 ? (
              <div className="text-xs" style={dimText}>None</div>
            ) : (
              <ul className="flex flex-col gap-1">
                {selected.missing_blocks.map((block, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs">
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: '50%',
                        backgroundColor: NVIS.red,
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ color: 'rgba(255,255,255,0.8)' }}>{block}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Extra blocks */}
          <div className="mb-4">
            <h3
              className="text-xs font-semibold mb-2"
              style={{ color: 'rgba(255,255,255,0.7)' }}
            >
              Extra blocks
              <span style={dimText}> (in pdf_oxide, not in PyMuPDF)</span>
            </h3>
            {selected.extra_blocks.length === 0 ? (
              <div className="text-xs" style={dimText}>None</div>
            ) : (
              <ul className="flex flex-col gap-1">
                {selected.extra_blocks.map((block, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs">
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: '50%',
                        backgroundColor: NVIS.green,
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ color: 'rgba(255,255,255,0.8)' }}>{block}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Header disposition changes */}
          {selected.disposition_changes.length > 0 && (
            <div className="mb-4">
              <h3
                className="text-xs font-semibold mb-2"
                style={{ color: 'rgba(255,255,255,0.7)' }}
              >
                Header Disposition Changes
              </h3>
              <div
                className="rounded overflow-hidden"
                style={{ border: `1px solid ${NVIS.border}` }}
              >
                {/* Table header */}
                <div
                  className="flex text-xs font-semibold px-3 py-1"
                  style={{
                    backgroundColor: 'rgba(255,255,255,0.04)',
                    borderBottom: `1px solid ${NVIS.border}`,
                    color: 'rgba(255,255,255,0.65)',
                  }}
                >
                  <div style={{ flex: 2 }}>Text</div>
                  <div style={{ flex: 1 }}>Old</div>
                  <div style={{ flex: 1 }}>New</div>
                </div>
                {/* Table rows */}
                {selected.disposition_changes.map((change, i) => (
                  <div
                    key={i}
                    className="flex text-xs px-3 py-1"
                    style={{
                      borderBottom:
                        i < selected.disposition_changes.length - 1
                          ? `1px solid ${NVIS.border}`
                          : undefined,
                    }}
                  >
                    <div style={{ flex: 2, color: 'white' }}>{change.text}</div>
                    <div style={{ flex: 1, color: NVIS.red }}>{change.old}</div>
                    <div style={{ flex: 1, color: NVIS.green }}>{change.new}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {selected.disposition_changes.length === 0 && (
            <div className="mb-4">
              <h3
                className="text-xs font-semibold mb-2"
                style={{ color: 'rgba(255,255,255,0.7)' }}
              >
                Header Disposition Changes
              </h3>
              <div className="text-xs" style={dimText}>None</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
