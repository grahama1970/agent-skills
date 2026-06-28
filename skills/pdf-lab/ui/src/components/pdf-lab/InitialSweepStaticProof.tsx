import { useState } from 'react'
import { useRegisterAction } from '../../hooks/useRegisterAction'
import './InitialSweepStaticProof.css'

type CandidatePage = {
  page: string
  image: string
  alt: string
  elements: string[]
  preset: string
  reason: string
  nextStep: string
}

const elementFamilies = [
  ['Tables', '12'],
  ['Figures', '4'],
  ['Section Headers', '50+'],
  ['Running Headers', '2'],
  ['Running Footers', '2'],
  ['Requirements', '18'],
  ['Lists', '22'],
  ['Definition Lists', '8'],
  ['Captions', '15'],
  ['Compliance Blocks', '9'],
]

const candidatePages: CandidatePage[] = [
  {
    page: '456',
    image: '/artifacts/pdf-lab/pdf-lab-initial-sweep-page-456.png',
    alt: 'NIST page 456 requirement matrix candidate',
    elements: ['Table', 'Requirement'],
    preset: 'control_matrix',
    reason: '42 anchors; grid-aligned',
    nextStep: 'Extract Page',
  },
  {
    page: '482',
    image: '/artifacts/pdf-lab/pdf-lab-initial-sweep-page-482.png',
    alt: 'NIST page 482 table candidate',
    elements: ['Table'],
    preset: 'spec_table',
    reason: 'Rev. 5 header schema',
    nextStep: 'Extract Page',
  },
  {
    page: '429',
    image: '/artifacts/pdf-lab/pdf-lab-initial-sweep-page-429.png',
    alt: 'NIST page 429 definition list candidate',
    elements: ['Definition List'],
    preset: 'def_list',
    reason: 'Indentation anchor found',
    nextStep: 'Compare JSON',
  },
  {
    page: '027',
    image: '/artifacts/pdf-lab/pdf-lab-initial-sweep-page-027.png',
    alt: 'NIST page 27 caption candidate',
    elements: ['Captions'],
    preset: 'table_caption',
    reason: 'Table [N] bold prefix',
    nextStep: 'Extract Sample',
  },
  {
    page: '112',
    image: '/artifacts/pdf-lab/pdf-lab-initial-sweep-page-456.png',
    alt: 'NIST page 112 compliance block proxy thumbnail',
    elements: ['Compliance Block'],
    preset: 'security_ctrl',
    reason: 'AC-1 policy header',
    nextStep: 'Extract Page',
  },
  {
    page: '301',
    image: '/artifacts/pdf-lab/pdf-lab-initial-sweep-page-429.png',
    alt: 'NIST page 301 list and requirement proxy thumbnail',
    elements: ['List', 'Requirement'],
    preset: 'bullet_alpha',
    reason: 'Nested alpha-list recursion',
    nextStep: 'Compare JSON',
  },
]

export function InitialSweepStaticProof() {
  const [selectedPage, setSelectedPage] = useState(candidatePages[0])
  const [copied, setCopied] = useState(false)

  useRegisterAction('pdf-lab:initial-sweep:copy-html-css', {
    app: 'pdf-lab',
    action: 'PDF_LAB_INITIAL_SWEEP_COPY_HTML_CSS',
    label: 'Copy HTML/CSS',
    description: 'Copy the rendered Initial Sweep mockup markup',
  })
  useRegisterAction('pdf-lab:initial-sweep:execute-extraction', {
    app: 'pdf-lab',
    action: 'PDF_LAB_INITIAL_SWEEP_EXECUTE_EXTRACTION',
    label: 'Commit Sweep to Run',
    description: 'Commit the agent-selected sweep plan to the deterministic extraction run',
  })
  useRegisterAction('pdf-lab:initial-sweep:add-page', {
    app: 'pdf-lab',
    action: 'PDF_LAB_INITIAL_SWEEP_ADD_PAGE',
    label: 'Add Page to Candidates',
    description: 'Manually add a known edge-case page to the candidate extraction queue',
  })
  useRegisterAction('pdf-lab:initial-sweep:run-candidates', {
    app: 'pdf-lab',
    action: 'PDF_LAB_INITIAL_SWEEP_RUN_CANDIDATES',
    label: 'Run pdf_oxide on candidates',
    description: 'Run pdf_oxide extraction on the 50 selected candidate pages',
  })
  useRegisterAction('pdf-lab:initial-sweep:select-page', {
    app: 'pdf-lab',
    action: 'PDF_LAB_INITIAL_SWEEP_SELECT_PAGE',
    label: 'Select candidate page',
    description: 'Select a candidate page and update the evidence pane',
  })
  useRegisterAction('pdf-lab:initial-sweep:extract-page', {
    app: 'pdf-lab',
    action: 'PDF_LAB_INITIAL_SWEEP_EXTRACT_PAGE',
    label: 'Extract selected page',
    description: 'Extract the selected candidate page with pdf_oxide',
  })

  const handleCopyHtmlCss = async () => {
    const html = `<!doctype html>\n${document.documentElement.outerHTML}`
    await navigator.clipboard.writeText(html)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  return (
    <div className="pdf-lab-initial-sweep-proof" data-qid="pdf-lab:initial-sweep">
      <header className="pdf-lab-initial-sweep-header">
        <div className="pdf-lab-initial-sweep-brand">
          <span>PDF</span> LAB <small>/ NIST_SP_800-53r5.pdf</small>
        </div>
        <div className="pdf-lab-initial-sweep-actions">
          <button
            data-copied={copied}
            data-qid="pdf-lab:initial-sweep:copy-html-css"
            data-qs-action="PDF_LAB_INITIAL_SWEEP_COPY_HTML_CSS"
            title="Copy the rendered Initial Sweep HTML/CSS"
            type="button"
            onClick={handleCopyHtmlCss}
          >
            {copied ? 'Copied' : 'Copy HTML/CSS'}
          </button>
          <button
            className="pdf-lab-initial-sweep-primary"
            data-qid="pdf-lab:initial-sweep:execute-extraction"
            data-qs-action="PDF_LAB_INITIAL_SWEEP_EXECUTE_EXTRACTION"
            title="Commit the agent-selected sweep plan to the deterministic extraction run"
            type="button"
          >
            Commit Sweep to Run -&gt;
          </button>
        </div>
      </header>

      <section className="pdf-lab-initial-sweep-metrics" aria-label="Sweep metrics">
        <div><span>Pages</span><b>492</b></div>
        <div><span>Presets Fired</span><b>136</b></div>
        <div><span>Candidates</span><b>50</b></div>
        <div><span>Expected Nodes</span><b>4,115</b></div>
        <div><span>Prior Comparison</span><b>99.2%</b></div>
      </section>

      <main className="pdf-lab-initial-sweep-main">
        <aside className="pdf-lab-initial-sweep-elements" aria-label="Elements found by sweep">
          <div className="pdf-lab-initial-sweep-pane-title">Elements</div>
          <div className="pdf-lab-initial-sweep-source">
            /mnt/storage12tb/extractor_corpus/source/standards/NIST_SP_800-53r5.pdf
          </div>
          {elementFamilies.map(([label, count], index) => (
            <div className={index === 0 ? 'pdf-lab-initial-sweep-family active' : 'pdf-lab-initial-sweep-family'} key={label}>
              <span>{label}</span>
              <b>{count}</b>
            </div>
          ))}
        </aside>

        <section className="pdf-lab-initial-sweep-candidates" aria-label="Candidate pages">
          <div className="pdf-lab-initial-sweep-candidate-head">
            <div>
              <h2>Candidate Pages</h2>
              <p>Agent-selected pages containing pdf_oxide-supported elements. Run deterministic extraction next, then compare JSON.</p>
            </div>
            <div className="pdf-lab-initial-sweep-candidate-actions">
              <button
                className="pdf-lab-initial-sweep-secondary"
                data-qid="pdf-lab:initial-sweep:add-page"
                data-qs-action="PDF_LAB_INITIAL_SWEEP_ADD_PAGE"
                title="Manually add a known edge-case page to the candidate extraction queue"
                type="button"
              >
                Add Page to Candidates
              </button>
              <button
                className="pdf-lab-initial-sweep-primary"
                data-qid="pdf-lab:initial-sweep:run-candidates"
                data-qs-action="PDF_LAB_INITIAL_SWEEP_RUN_CANDIDATES"
                title="Run pdf_oxide extraction on all selected candidate pages"
                type="button"
              >
                Run pdf_oxide on 50 Candidates -&gt;
              </button>
            </div>
          </div>

          <div className="pdf-lab-initial-sweep-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Page</th>
                  <th>Page View</th>
                  <th>Found Elements</th>
                  <th>pdf_oxide Presets</th>
                  <th>Why This Page</th>
                  <th>Next Step</th>
                </tr>
              </thead>
              <tbody>
                {candidatePages.map(candidate => (
                  <tr
                    className={selectedPage.page === candidate.page ? 'selected' : undefined}
                    key={candidate.page}
                    onClick={() => setSelectedPage(candidate)}
                  >
                    <td><span className="pdf-lab-initial-sweep-page">{candidate.page}</span></td>
                    <td>
                      <button
                        className="pdf-lab-initial-sweep-thumb"
                        data-qid={`pdf-lab:initial-sweep:select-page:${candidate.page}`}
                        data-qs-action="PDF_LAB_INITIAL_SWEEP_SELECT_PAGE"
                        title={`Select page ${candidate.page}`}
                        type="button"
                        onClick={() => setSelectedPage(candidate)}
                      >
                        <img src={candidate.image} alt={candidate.alt} />
                      </button>
                    </td>
                    <td>
                      <div className="pdf-lab-initial-sweep-tags">
                        {candidate.elements.map(element => <span key={element}>{element}</span>)}
                      </div>
                    </td>
                    <td className="pdf-lab-initial-sweep-preset">{candidate.preset}</td>
                    <td className="pdf-lab-initial-sweep-why">{candidate.reason}</td>
                    <td className="pdf-lab-initial-sweep-next">{candidate.nextStep}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="pdf-lab-initial-sweep-evidence" aria-label="Selected page evidence">
          <div className="pdf-lab-initial-sweep-evidence-head">
            <h3>Evidence</h3>
            <p>Page {selectedPage.page} - selected candidate page with detected supported element highlighted.</p>
          </div>
          <div className="pdf-lab-initial-sweep-preview">
            <div className="pdf-lab-initial-sweep-page-preview">
              <img src={selectedPage.image} alt={selectedPage.alt} />
              <div className="pdf-lab-initial-sweep-highlight">
                <div>{selectedPage.elements[0] === 'Table' ? 'Requirement Matrix' : selectedPage.elements[0]}</div>
              </div>
            </div>
          </div>
          <div className="pdf-lab-initial-sweep-meta">
            <div><b>Matched Preset</b><code>{selectedPage.preset}</code></div>
            <div><b>Target Family</b><span>{selectedPage.elements.join(', ')}</span></div>
            <p>Agent detected candidate anchors for deterministic extraction. This page enters the proofing queue before JSON comparison.</p>
            <button
              className="pdf-lab-initial-sweep-primary"
              data-qid="pdf-lab:initial-sweep:extract-page"
              data-qs-action="PDF_LAB_INITIAL_SWEEP_EXTRACT_PAGE"
              title={`Extract page ${selectedPage.page}`}
              type="button"
            >
              Extract Page {selectedPage.page} -&gt;
            </button>
          </div>
        </aside>
      </main>
    </div>
  )
}
