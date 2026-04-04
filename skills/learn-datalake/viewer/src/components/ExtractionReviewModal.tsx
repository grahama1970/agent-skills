import { useState, useEffect, useCallback } from 'react'
import PdfCanvas from './PdfCanvas'
import { NVIS } from '../theme'
import type { BboxBlock, CascadeStep } from '../types'

const CORPUS_SOURCE = '/mnt/storage12tb/extractor_corpus/source/'
const FIXTURES_DIR = '/mnt/storage12tb/extractor_corpus/fixtures/generated/'

interface ExtractionReviewModalProps {
  filename: string
  originalPath: string
  resultsDir?: string
  pageCount: number
  reasons: string[]
  debugPatterns: string[]
  s00Estimated: number
  s04Actual: number
  onClose: () => void
  onReExtract?: () => void
  onAccept?: () => void
}

type ModalMode = 'review' | 'compare' | 'generating'

function pdfUrl(originalPath: string): string {
  if (originalPath.startsWith(CORPUS_SOURCE)) {
    return '/corpus-pdf/' + originalPath.slice(CORPUS_SOURCE.length)
  }
  return '/corpus-pdf/' + originalPath
}

export default function ExtractionReviewModal({
  filename, originalPath, resultsDir, pageCount, reasons, debugPatterns,
  s00Estimated, s04Actual, onClose, onReExtract, onAccept,
}: ExtractionReviewModalProps) {
  const [mode, setMode] = useState<ModalMode>('review')
  const [currentPage, setCurrentPage] = useState(0)
  const [blocks, setBlocks] = useState<BboxBlock[]>([])
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1.0)
  const [loading, setLoading] = useState(true)

  // Fixture state
  const [fixtureSpec, setFixtureSpec] = useState<FixtureSpec | null>(null)
  const [fixtureBlocks, setFixtureBlocks] = useState<BboxBlock[]>([])
  const [generatingStatus, setGeneratingStatus] = useState('')
  const [fixturePdfUrl, setFixturePdfUrl] = useState<string | null>(null)
  const [fixtureStatus, setFixtureStatus] = useState<'loading' | 'found' | 'none'>('loading')

  // Load extraction results
  useEffect(() => {
    if (!resultsDir) { setLoading(false); return }
    fetch(`/corpus-pdf/../results/${resultsDir}/02_marker_extractor/json_output/02_blocks.json`)
      .then((r) => r.ok ? r.json() : null)
      .catch(() => null)
      .then((data) => {
        if (data?.blocks) {
          const parsed: BboxBlock[] = data.blocks
            .filter((b: Record<string, unknown>) => b.page === currentPage || b.page_number === currentPage)
            .map((b: Record<string, unknown>, i: number) => ({
              id: `block-${i}`,
              page: (b.page as number) ?? (b.page_number as number) ?? 0,
              bbox: normalizeBbox(b.bbox as number[]),
              blockType: mapBlockType(b.block_type as string ?? b.type as string ?? 'text'),
              text: ((b.text as string) ?? '').slice(0, 200),
              confidence: (b.confidence as number) ?? 1.0,
              cascadeTrail: [] as CascadeStep[],
            }))
          setBlocks(parsed)
        }
        setLoading(false)
      })
  }, [resultsDir, currentPage])

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
    if (e.key === 'ArrowRight' && currentPage < pageCount - 1) setCurrentPage((p) => p + 1)
    if (e.key === 'ArrowLeft' && currentPage > 0) setCurrentPage((p) => p - 1)
  }, [onClose, currentPage, pageCount])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  // Look up fixture from pattern/fix registries
  useEffect(() => {
    setFixtureStatus('loading')
    const patternP = fetch('/pattern_registry.json').then((r) => r.ok ? r.json() : null).catch(() => null)
    const fixP = fetch('/corpus-metadata/fix_registry.json').then((r) => r.ok ? r.json() : null).catch(() => null)
    Promise.all([patternP, fixP]).then(([patData, fixData]) => {
      // Find which patterns this file belongs to
      const filePatterns: string[] = []
      if (patData?.patterns) {
        for (const [pat, info] of Object.entries(patData.patterns) as [string, { files?: string[] }][]) {
          if (info.files?.includes(filename)) filePatterns.push(pat)
        }
      }
      // Also include debugPatterns passed from parent
      for (const dp of debugPatterns) {
        if (!filePatterns.includes(dp)) filePatterns.push(dp)
      }
      // Check fix_registry for any pattern with a generated fixture
      let hasFixture = false
      if (fixData?.patterns) {
        for (const pat of filePatterns) {
          const fix = fixData.patterns[pat] as Record<string, unknown> | undefined
          if (fix?.fixture_generated) { hasFixture = true; break }
        }
      }
      if (!hasFixture) { setFixtureStatus('none'); return }
      // Convention: fixture PDF is {stem}_fixture.pdf in /corpus-fixture/
      const stem = filename.replace(/\.pdf$/i, '')
      const fUrl = `/corpus-fixture/${stem}_fixture.pdf`
      // Verify fixture PDF actually exists
      fetch(fUrl, { method: 'HEAD' }).then((r) => {
        if (r.ok) {
          setFixturePdfUrl(fUrl)
          setFixtureStatus('found')
        } else { setFixtureStatus('none') }
      }).catch(() => setFixtureStatus('none'))
    })
  }, [filename, debugPatterns])

  // Load ground truth bboxes when fixture is found and page changes
  useEffect(() => {
    if (fixtureStatus !== 'found') { setFixtureBlocks([]); return }
    const stem = filename.replace(/\.pdf$/i, '')
    const gtUrl = `/corpus-fixture/${stem}_fixture_ground_truth.json`
    fetch(gtUrl)
      .then((r) => r.ok ? r.json() : null)
      .catch(() => null)
      .then((gt) => {
        if (!gt) { setFixtureBlocks([]); return }
        const parsed: BboxBlock[] = []
        let idx = 0
        // Ground truth sections → header blocks
        for (const s of (gt.sections ?? []) as Record<string, unknown>[]) {
          if ((s.page_start as number) === currentPage || (s.page as number) === currentPage) {
            parsed.push({
              id: `gt-section-${idx++}`, page: currentPage,
              bbox: normalizeBbox(s.bbox as number[]),
              blockType: 'header', text: ((s.title as string) ?? '').slice(0, 200),
              confidence: 1.0, cascadeTrail: [],
            })
          }
        }
        // Ground truth blocks
        for (const b of (gt.blocks ?? []) as Record<string, unknown>[]) {
          const pg = (b.page as number) ?? (b.page_number as number) ?? 0
          if (pg === currentPage) {
            parsed.push({
              id: `gt-block-${idx++}`, page: currentPage,
              bbox: normalizeBbox(b.bbox as number[]),
              blockType: mapBlockType((b.block_type as string) ?? (b.type as string) ?? 'text'),
              text: ((b.text as string) ?? '').slice(0, 200),
              confidence: 1.0, cascadeTrail: [],
            })
          }
        }
        // Ground truth tables
        for (const t of (gt.tables ?? []) as Record<string, unknown>[]) {
          const pg = (t.page_number as number) ?? (t.page as number) ?? 0
          if (pg === currentPage) {
            parsed.push({
              id: `gt-table-${idx++}`, page: currentPage,
              bbox: normalizeBbox(t.bbox as number[]),
              blockType: 'table', text: `Table (${((t.rows as unknown[])?.length ?? 0)} rows)`,
              confidence: 1.0, cascadeTrail: [],
            })
          }
        }
        // Ground truth figures
        for (const f of (gt.figures ?? []) as Record<string, unknown>[]) {
          const pg = (f.page as number) ?? (f.page_number as number) ?? 0
          if (pg === currentPage) {
            parsed.push({
              id: `gt-figure-${idx++}`, page: currentPage,
              bbox: normalizeBbox(f.bbox as number[]),
              blockType: 'figure', text: ((f.context_above as string) ?? 'Figure').slice(0, 200),
              confidence: 1.0, cascadeTrail: [],
            })
          }
        }
        setFixtureBlocks(parsed)
      })
  }, [fixtureStatus, filename, currentPage])

  // Build fixture spec from failure analysis
  function buildFixtureSpec(): FixtureSpec {
    const tricks: string[] = []
    for (const p of debugPatterns) {
      if (p.includes('underestimate')) tricks.push('toc-entries', 'multi-column')
      if (p.includes('overestimate')) tricks.push('key-value-pairs', 'numbered-list')
      if (p.includes('table')) tricks.push('false-tables', 'malformed-tables')
    }
    return {
      sourceFile: filename,
      sourcePath: originalPath,
      patterns: debugPatterns,
      tricks: [...new Set(tricks)],
      groundTruth: {
        expectedSections: s04Actual || s00Estimated,
        notes: `Reproduces failure pattern from ${filename}: ${reasons.join('; ')}`,
      },
      generatedPath: null,
    }
  }

  async function handleGenerateFixture() {
    const spec = buildFixtureSpec()
    setFixtureSpec(spec)
    setMode('generating')
    setGeneratingStatus('Analyzing failure pattern...')

    // Step 1: Screenshot TOC pages for reference
    setGeneratingStatus('Capturing TOC pages via /pdf-screenshot...')
    await sleep(500) // UI feedback

    // Step 2: Generate fixture spec JSON (agent will use this to call /fixture-tricky)
    setGeneratingStatus('Building fixture specification...')
    const specJson = JSON.stringify({
      command: 'generate',
      tricks: spec.tricks,
      output: `${FIXTURES_DIR}${filename.replace('.pdf', '_fixture.pdf')}`,
      ground_truth: spec.groundTruth,
      source_analysis: {
        filename: spec.sourceFile,
        patterns: spec.patterns,
        s00_estimated: s00Estimated,
        s04_actual: s04Actual,
      },
    }, null, 2)

    // Store spec for the agent to pick up
    try {
      await fetch('/memory/learn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          collection: 'lessons',
          document: {
            problem: `Fixture spec for ${filename}: ${debugPatterns.join(', ')}`,
            solution: specJson,
            scope: 'pdf-lab',
            tags: ['fixture-spec', 'pdf-lab', ...debugPatterns],
          },
        }),
      })
      setGeneratingStatus('Fixture spec stored in /memory. Agent will generate synthetic PDF.')
    } catch {
      setGeneratingStatus('Failed to store spec — check /memory daemon')
    }

    // For now, show the spec — the agent picks it up and runs /fixture-tricky
    setMode('compare')
  }

  const url = pdfUrl(originalPath)

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.9)',
      display: 'flex', flexDirection: 'column', fontFamily: "'JetBrains Mono', monospace",
    }}>
      {/* Top bar */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '8px 16px', borderBottom: `1px solid ${NVIS.border}`, flexShrink: 0,
        background: '#0f1216',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: NVIS.white }}>{filename}</span>
          <span style={{ fontSize: 10, color: NVIS.dim }}>Page {currentPage + 1} / {pageCount}</span>
          {/* Mode tabs */}
          <div style={{ display: 'flex', gap: 4, marginLeft: 12 }}>
            {(['review', 'compare'] as ModalMode[]).map((m) => (
              <span key={m} onClick={() => setMode(m)} style={{
                fontSize: 9, padding: '2px 8px', borderRadius: 3, cursor: 'pointer',
                color: mode === m ? '#0f1216' : NVIS.dim,
                background: mode === m ? NVIS.accent : 'transparent',
                border: `1px solid ${mode === m ? NVIS.accent : NVIS.border}`,
              }}>
                {m === 'review' ? 'Review' : 'Compare Synthetic'}
              </span>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={handleGenerateFixture} style={btnStyle(NVIS.accent)}>Generate Fixture</button>
          {onReExtract && <button onClick={onReExtract} style={btnStyle(NVIS.amber)}>Re-extract</button>}
          {onAccept && <button onClick={onAccept} style={btnStyle(NVIS.green)}>Accept as-is</button>}
          <button onClick={onClose} style={btnStyle(NVIS.dim)}>Close (Esc)</button>
        </div>
      </div>

      {/* Agent directives */}
      {reasons.length > 0 && (
        <div style={{ padding: '6px 16px', background: 'rgba(255,68,68,0.06)', borderBottom: `1px solid ${NVIS.border}`, flexShrink: 0 }}>
          <span style={{ fontSize: 9, color: NVIS.dim, textTransform: 'uppercase', marginRight: 8 }}>Agent Directive:</span>
          {reasons.map((r, i) => (
            <span key={i} style={{ fontSize: 10, color: NVIS.red, fontWeight: 600, marginRight: 12 }}>{r}</span>
          ))}
        </div>
      )}

      {/* Generating status */}
      {mode === 'generating' && (
        <div style={{ padding: '12px 16px', background: 'rgba(74,158,255,0.06)', borderBottom: `1px solid ${NVIS.border}`, flexShrink: 0 }}>
          <span style={{ fontSize: 10, color: NVIS.accent }}>{generatingStatus}</span>
        </div>
      )}

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {mode === 'review' && (
          <>
            {/* Single PDF view */}
            <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
              {loading ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: NVIS.dim, fontSize: 11 }}>
                  Loading extraction data...
                </div>
              ) : (
                <PdfCanvas pdfUrl={url} pageNumber={currentPage} bboxOverlays={blocks}
                  selectedBlockId={selectedBlock} onBlockClick={setSelectedBlock} zoom={zoom} />
              )}
            </div>
            {/* Block list */}
            <BlockListSidebar blocks={blocks} selectedBlock={selectedBlock}
              onSelect={setSelectedBlock} currentPage={currentPage} loading={loading} resultsDir={resultsDir} />
          </>
        )}

        {mode === 'compare' && (
          <>
            {/* Left: Real PDF */}
            <div style={{ flex: 1, borderRight: `2px solid ${NVIS.red}`, position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 4, left: 8, fontSize: 9, color: NVIS.red, fontWeight: 700, zIndex: 2, background: 'rgba(0,0,0,0.7)', padding: '2px 6px', borderRadius: 2 }}>
                REAL — {filename}
              </div>
              <PdfCanvas pdfUrl={url} pageNumber={currentPage} bboxOverlays={blocks}
                selectedBlockId={selectedBlock} onBlockClick={setSelectedBlock} zoom={zoom} />
            </div>

            {/* Right: Fixture PDF with ground truth (or placeholder) */}
            <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 4, left: 8, fontSize: 9, color: NVIS.green, fontWeight: 700, zIndex: 2, background: 'rgba(0,0,0,0.7)', padding: '2px 6px', borderRadius: 2 }}>
                {fixturePdfUrl ? 'FIXTURE — Ground Truth' : 'SYNTHETIC — Ground Truth'}
              </div>
              {fixturePdfUrl ? (
                <PdfCanvas pdfUrl={fixturePdfUrl} pageNumber={currentPage}
                  bboxOverlays={fixtureBlocks} selectedBlockId={selectedBlock}
                  onBlockClick={setSelectedBlock} zoom={zoom} />
              ) : fixtureSpec?.generatedPath ? (
                <PdfCanvas pdfUrl={pdfUrl(fixtureSpec.generatedPath)} pageNumber={currentPage}
                  bboxOverlays={fixtureBlocks} selectedBlockId={selectedBlock}
                  onBlockClick={setSelectedBlock} zoom={zoom} />
              ) : (
                <NoFixturePlaceholder fixtureStatus={fixtureStatus} fixtureSpec={fixtureSpec}
                  onGenerate={handleGenerateFixture} />
              )}
            </div>
          </>
        )}
      </div>

      {/* Page nav overlay */}
      <div style={{
        position: 'absolute', bottom: 12, left: '50%', transform: 'translateX(-50%)',
        display: 'flex', gap: 8, alignItems: 'center', padding: '4px 12px',
        background: 'rgba(15,18,22,0.9)', borderRadius: 4, border: `1px solid ${NVIS.border}`,
        zIndex: 10,
      }}>
        <span onClick={() => currentPage > 0 && setCurrentPage(currentPage - 1)}
          style={{ color: currentPage > 0 ? NVIS.accent : NVIS.dim, cursor: 'pointer', fontSize: 11 }}>← Prev</span>
        <span style={{ color: NVIS.white, fontSize: 10 }}>{currentPage + 1} / {pageCount}</span>
        <span onClick={() => currentPage < pageCount - 1 && setCurrentPage(currentPage + 1)}
          style={{ color: currentPage < pageCount - 1 ? NVIS.accent : NVIS.dim, cursor: 'pointer', fontSize: 11 }}>Next →</span>
        <span style={{ color: NVIS.dim, fontSize: 9, marginLeft: 8 }}>|</span>
        <span onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
          style={{ color: NVIS.accent, cursor: 'pointer', fontSize: 11 }}>−</span>
        <span style={{ color: NVIS.dim, fontSize: 9 }}>{(zoom * 100).toFixed(0)}%</span>
        <span onClick={() => setZoom((z) => Math.min(3, z + 0.25))}
          style={{ color: NVIS.accent, cursor: 'pointer', fontSize: 11 }}>+</span>
      </div>
    </div>
  )
}

// --- Block list sidebar ---

function BlockListSidebar({ blocks, selectedBlock, onSelect, currentPage, loading, resultsDir }: {
  blocks: BboxBlock[]; selectedBlock: string | null; onSelect: (id: string | null) => void;
  currentPage: number; loading: boolean; resultsDir?: string;
}) {
  return (
    <div style={{ width: 320, flexShrink: 0, borderLeft: `1px solid ${NVIS.border}`, overflow: 'auto', background: '#0f1216', padding: 8 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: NVIS.dim, marginBottom: 6 }}>
        Blocks on page {currentPage + 1} ({blocks.length})
      </div>
      {blocks.length === 0 && !loading && (
        <div style={{ fontSize: 9, color: NVIS.dim, padding: 8 }}>
          No extraction data available.{!resultsDir && ' (No results directory)'}
        </div>
      )}
      {blocks.map((block) => (
        <div key={block.id}
          onClick={() => onSelect(block.id === selectedBlock ? null : block.id)}
          style={{
            padding: '4px 6px', marginBottom: 2, fontSize: 9, cursor: 'pointer', borderRadius: 2,
            borderLeft: `3px solid ${BLOCK_COLORS[block.blockType] ?? NVIS.dim}`,
            background: block.id === selectedBlock ? 'rgba(74,158,255,0.1)' : 'transparent',
          }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: BLOCK_COLORS[block.blockType] ?? NVIS.dim, fontWeight: 600 }}>{block.blockType}</span>
            <span style={{ color: NVIS.dim }}>{(block.confidence * 100).toFixed(0)}%</span>
          </div>
          <div style={{ color: NVIS.white, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {block.text || '(empty)'}
          </div>
        </div>
      ))}
    </div>
  )
}

// --- No-fixture placeholder ---

function NoFixturePlaceholder({ fixtureStatus, fixtureSpec, onGenerate }: {
  fixtureStatus: 'loading' | 'found' | 'none'; fixtureSpec: FixtureSpec | null; onGenerate: () => void;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', padding: 24 }}>
      {fixtureStatus === 'loading' ? (
        <div style={{ fontSize: 11, color: NVIS.dim }}>Checking for fixture...</div>
      ) : (
        <>
          <div style={{ fontSize: 12, color: NVIS.dim, marginBottom: 12 }}>
            No fixture generated for this pattern.
          </div>
          <div style={{ fontSize: 10, color: NVIS.amber, marginBottom: 16 }}>
            Use heal-fixture to create one, or generate a spec below.
          </div>
          {fixtureSpec ? (
            <div style={{ background: '#0f1216', border: `1px solid ${NVIS.border}`, borderRadius: 4, padding: 12, maxWidth: 400, fontSize: 9, color: NVIS.dim }}>
              <div style={{ fontSize: 10, color: NVIS.accent, fontWeight: 600, marginBottom: 6 }}>Fixture Specification</div>
              <div style={{ marginBottom: 4 }}>
                <span style={{ color: NVIS.dim }}>Patterns: </span>
                <span style={{ color: NVIS.amber }}>{fixtureSpec.patterns.join(', ')}</span>
              </div>
              <div style={{ marginBottom: 4 }}>
                <span style={{ color: NVIS.dim }}>Tricks: </span>
                <span style={{ color: NVIS.white }}>{fixtureSpec.tricks.join(', ')}</span>
              </div>
              <div style={{ marginBottom: 4 }}>
                <span style={{ color: NVIS.dim }}>Expected sections: </span>
                <span style={{ color: NVIS.green }}>{fixtureSpec.groundTruth.expectedSections}</span>
              </div>
              <div style={{ fontSize: 8, color: NVIS.dim, marginTop: 8 }}>
                Spec stored in /memory. The project agent will run /fixture-tricky to generate the synthetic PDF,
                then /pdf-lab convergence loop to tune extraction parameters.
              </div>
            </div>
          ) : (
            <button onClick={onGenerate} style={btnStyle(NVIS.accent)}>Generate Fixture</button>
          )}
        </>
      )}
    </div>
  )
}

// --- Types ---

interface FixtureSpec {
  sourceFile: string
  sourcePath: string
  patterns: string[]
  tricks: string[]
  groundTruth: {
    expectedSections: number
    notes: string
  }
  generatedPath: string | null
}

// --- Helpers ---

const BLOCK_COLORS: Record<string, string> = {
  header: '#4a9eff', text: '#888', table: '#00ff88', figure: '#ffaa00',
  equation: '#ff4444', list_item: '#9966ff', caption: '#66cccc',
}

function btnStyle(color: string): React.CSSProperties {
  return {
    fontSize: 10, padding: '3px 10px', borderRadius: 3, cursor: 'pointer',
    background: 'transparent', border: `1px solid ${color}`, color,
    fontFamily: "'JetBrains Mono', monospace",
  }
}

function normalizeBbox(bbox: number[] | undefined): [number, number, number, number] {
  if (!bbox || bbox.length < 4) return [0, 0, 0, 0]
  const [x1, y1, x2, y2] = bbox
  if (x1 > 1 || y1 > 1 || x2 > 1 || y2 > 1) return [x1 / 612, y1 / 792, x2 / 612, y2 / 792]
  return [x1, y1, x2, y2]
}

function mapBlockType(t: string): BboxBlock['blockType'] {
  const map: Record<string, BboxBlock['blockType']> = {
    header: 'header', title: 'header', heading: 'header',
    text: 'text', body: 'text', paragraph: 'text',
    table: 'table', figure: 'figure', image: 'figure',
    equation: 'equation', formula: 'equation', math: 'equation',
    list: 'list_item', list_item: 'list_item', caption: 'caption',
  }
  return map[t.toLowerCase()] ?? 'text'
}

function sleep(ms: number): Promise<void> { return new Promise((r) => setTimeout(r, ms)) }
