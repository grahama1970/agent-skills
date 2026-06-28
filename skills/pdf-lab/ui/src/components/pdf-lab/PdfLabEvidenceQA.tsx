import { useEffect, useState, type CSSProperties } from 'react'
import { EMBRY } from '../common/EmbryStyle'

interface NicoQASample {
  sample_id: string
  question: string
  element_id: string
  page: number
  element_type: string
  page_image_uri: string
  crop_uri: string
  json_pointer: string
  selection_reason: string
  verdict: {
    status: string
    uncertainty: string
    warnings: string[]
  }
}

interface NicoQAReport {
  schema_version: string
  run_id: string
  source_pdf: string
  sample_size: number
  seed: number
  policy: string
  samples: NicoQASample[]
}

export function PdfLabEvidenceQA() {
  const [report, setReport] = useState<NicoQAReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/pdf-lab/nico-qa-report')
      .then(async response => {
        const payload = await response.json()
        if (!response.ok) throw new Error(payload.detail ?? payload.error ?? 'Failed to load Nico QA report')
        return payload.report as NicoQAReport
      })
      .then(payload => {
        if (!cancelled) setReport(payload)
      })
      .catch(err => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [])

  const samples = report?.samples ?? []
  const active = samples[0] ?? null

  return (
    <div data-qid="pdf-lab:evidence-qa" style={rootStyle}>
      <header style={headerStyle}>
        <div>
          <div style={eyebrowStyle}>PDF LAB · FINAL QA</div>
          <h1 style={titleStyle}>Nico Evidence QA</h1>
        </div>
        <div style={metricRowStyle}>
          <span style={metricStyle}>{report?.sample_size ?? 0} samples</span>
          <span style={metricStyle}>Seed {report?.seed ?? 53}</span>
          <span style={metricStyle}>Human triage complete</span>
        </div>
      </header>

      {error ? (
        <section style={errorStyle}>Missing real QA artifact: {error}</section>
      ) : !report ? (
        <section style={panelStyle}>Loading real QA report…</section>
      ) : (
        <main style={gridStyle}>
          <aside style={panelStyle}>
            <div style={panelHeaderStyle}>Stratified Samples</div>
            <div style={{ display: 'grid', gap: 8 }}>
              {samples.map(sample => (
                <article key={sample.sample_id} style={sampleRowStyle}>
                  <strong>p{sample.page} · {sample.element_type}</strong>
                  <span style={mutedStyle}>{sample.element_id}</span>
                  <span style={statusStyle}>{sample.verdict.status}</span>
                </article>
              ))}
            </div>
          </aside>

          <section style={panelStyle}>
            <div style={panelHeaderStyle}>Artifact-Grounded Question</div>
            {active && (
              <>
                <h2 style={questionStyle}>{active.question}</h2>
                <p style={mutedStyle}>{report.policy}</p>
                <dl style={detailsStyle}>
                  <dt>JSON pointer</dt><dd>{active.json_pointer}</dd>
                  <dt>Selection</dt><dd>{active.selection_reason}</dd>
                  <dt>Uncertainty</dt><dd>{active.verdict.uncertainty}</dd>
                </dl>
              </>
            )}
          </section>

          <aside style={panelStyle}>
            <div style={panelHeaderStyle}>Source Evidence</div>
            {active && (
              <div style={{ display: 'grid', gap: 12 }}>
                <div style={evidenceImageGroupStyle}>
                  <span style={imageLabelStyle}>Element crop</span>
                  <img alt={`Page ${active.page} evidence crop`} src={active.crop_uri} style={cropImageStyle} />
                </div>
                <div style={evidenceImageGroupStyle}>
                  <span style={imageLabelStyle}>Full page render</span>
                  <img alt={`Page ${active.page} full render`} src={active.page_image_uri} style={pageImageStyle} />
                </div>
                <code style={codeStyle}>{active.crop_uri}</code>
                <code style={codeStyle}>{active.page_image_uri}</code>
              </div>
            )}
          </aside>
        </main>
      )}
    </div>
  )
}

const rootStyle: CSSProperties = {
  minHeight: '100%',
  background: '#05070a',
  color: EMBRY.white,
  display: 'grid',
  gridTemplateRows: '72px minmax(0, 1fr)',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '0 24px',
  borderBottom: `1px solid ${EMBRY.border}`,
  background: '#080b10',
}

const eyebrowStyle: CSSProperties = {
  color: EMBRY.green,
  fontFamily: '"JetBrains Mono", monospace',
  fontSize: 11,
  fontWeight: 900,
  letterSpacing: '0.16em',
}

const titleStyle: CSSProperties = { margin: 0, fontSize: 22 }
const metricRowStyle: CSSProperties = { display: 'flex', gap: 10 }
const metricStyle: CSSProperties = { border: `1px solid ${EMBRY.border}`, borderRadius: 999, padding: '6px 10px', color: EMBRY.muted, fontSize: 12 }
const gridStyle: CSSProperties = { display: 'grid', gridTemplateColumns: '300px minmax(0, 1fr) 380px', gap: 16, padding: 16, minHeight: 0 }
const panelStyle: CSSProperties = { background: '#0d1118', border: `1px solid ${EMBRY.border}`, borderRadius: 12, padding: 16, minHeight: 0, overflow: 'auto' }
const panelHeaderStyle: CSSProperties = { color: EMBRY.muted, fontSize: 11, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 12 }
const sampleRowStyle: CSSProperties = { display: 'grid', gap: 4, padding: 10, border: `1px solid ${EMBRY.border}`, borderRadius: 8, background: '#080b10' }
const mutedStyle: CSSProperties = { color: EMBRY.muted, lineHeight: 1.5 }
const statusStyle: CSSProperties = { color: EMBRY.amber, fontFamily: '"JetBrains Mono", monospace', fontSize: 11, textTransform: 'uppercase' }
const questionStyle: CSSProperties = { fontSize: 24, lineHeight: 1.2, margin: '0 0 12px' }
const detailsStyle: CSSProperties = { display: 'grid', gridTemplateColumns: '120px 1fr', gap: 8, color: EMBRY.muted }
const evidenceImageGroupStyle: CSSProperties = { display: 'grid', gap: 6 }
const imageLabelStyle: CSSProperties = { color: EMBRY.muted, fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase' }
const cropImageStyle: CSSProperties = { width: '100%', minHeight: 96, maxHeight: 160, objectFit: 'contain', background: '#fff', borderRadius: 8 }
const pageImageStyle: CSSProperties = { width: '100%', maxHeight: 320, objectFit: 'contain', background: '#fff', borderRadius: 8 }
const codeStyle: CSSProperties = { color: EMBRY.muted, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 11 }
const errorStyle: CSSProperties = { ...panelStyle, margin: 16, color: EMBRY.red }
