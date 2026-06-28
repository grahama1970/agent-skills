import { useRegisterAction } from '../../hooks/useRegisterAction'
import './ParityAuditStaticProof.css'

type RunItem = {
  page: string
  title: string
  preset: string
  parity: string
  misses: string
  cards: string
  status: 'pass' | 'review'
}

const runItems: RunItem[] = [
  { page: '456', title: 'Requirement Matrix', preset: 'control_matrix', parity: '98.4%', misses: '0', cards: '0', status: 'pass' },
  { page: '482', title: 'Traceability Table', preset: 'spec_table', parity: '97.9%', misses: '1', cards: '0', status: 'pass' },
  { page: '429', title: 'Definition List', preset: 'def_list', parity: '91.7%', misses: '3', cards: '3', status: 'review' },
  { page: '027', title: 'Caption Sample', preset: 'table_caption', parity: '96.2%', misses: '0', cards: '0', status: 'pass' },
  { page: '112', title: 'Compliance Block', preset: 'security_ctrl', parity: '99.1%', misses: '0', cards: '0', status: 'pass' },
  { page: '301', title: 'Nested Lists', preset: 'bullet_alpha', parity: '93.8%', misses: '2', cards: '1', status: 'review' },
]

const compareRows = [
  {
    status: 'matched',
    expected: 'definition_list',
    expectedText: '“discretionary access control” term with definition body.',
    emitted: 'definition_list',
    emittedText: 'Term/body pair preserved; normalized text delta only.',
    evidence: 'text ≥ 0.98',
    bbox: '[0.18, .13, .82, .26]',
  },
  {
    status: 'matched',
    expected: 'definition_list',
    expectedText: '“domain” paired with operational environment definition.',
    emitted: 'definition_list',
    emittedText: 'Same semantic node; paragraph wrapped differently.',
    evidence: 'type + bbox',
    bbox: '[0.18, .41, .82, .49]',
  },
  {
    status: 'missing',
    expected: 'definition_list',
    expectedText: 'Expected “dissociability” term and definition as one node.',
    emitted: '—',
    emittedText: 'No single emitted semantic node covers the term/body pair.',
    evidence: 'term anchor',
    bbox: '[0.18, .29, .82, .37]',
  },
  {
    status: 'extra',
    expected: '—',
    expectedText: 'Agent oracle did not expect a separate table object here.',
    emitted: 'table',
    emittedText: 'pdf_oxide emitted a two-column table candidate.',
    evidence: 'cols=2',
    bbox: '[0.17, .27, .83, .51]',
  },
  {
    status: 'ambiguous',
    expected: 'definition_list',
    expectedText: 'Expected semantic type: definition list.',
    emitted: 'table',
    emittedText: 'Emitted semantic type: table; same visual region.',
    evidence: 'type conflict',
    bbox: '[0.17, .27, .83, .51]',
  },
  {
    status: 'matched',
    expected: 'running_footer',
    expectedText: 'Appendix A footer detected outside content region.',
    emitted: 'running_footer',
    emittedText: 'Suppressed from graph; retained as page chrome.',
    evidence: 'chrome',
    bbox: '[0.16, .94, .84, .97]',
  },
]

export function ParityAuditStaticProof() {
  useRegisterAction('pdf-lab:parity-audit:bulk-repair', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PARITY_AUDIT_BULK_REPAIR',
    label: 'Bulk Repair / Re-run',
    description: 'Send systemic extraction defects to preset/core repair and rerun affected candidates',
  })
  useRegisterAction('pdf-lab:parity-audit:promote-passing', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PARITY_AUDIT_PROMOTE_PASSING',
    label: 'Promote 47 Passing Pages',
    description: 'Promote passing candidate pages without human review',
  })
  useRegisterAction('pdf-lab:parity-audit:eject-mismatches', {
    app: 'pdf-lab',
    action: 'PDF_LAB_PARITY_AUDIT_EJECT_MISMATCHES',
    label: 'Eject Mismatches to Triage',
    description: 'Create human triage cards from unresolved below-gate mismatches',
  })

  return (
    <div className="pdf-lab-parity-proof" data-qid="pdf-lab:parity-audit">
      <header className="pdf-lab-parity-header">
        <div className="pdf-lab-parity-brand"><span>PDF</span> LAB <small>/ NIST_SP_800-53r5.pdf / deterministic extraction parity audit</small></div>
        <div className="pdf-lab-parity-actions">
          <button type="button">Copy HTML/CSS</button>
          <button className="pdf-lab-parity-repair" data-qid="pdf-lab:parity-audit:bulk-repair" data-qs-action="PDF_LAB_PARITY_AUDIT_BULK_REPAIR" type="button">Bulk Repair / Re-run</button>
          <button className="pdf-lab-parity-success" data-qid="pdf-lab:parity-audit:promote-passing" data-qs-action="PDF_LAB_PARITY_AUDIT_PROMOTE_PASSING" type="button">Promote 47 Passing Pages</button>
          <button className="pdf-lab-parity-primary" data-qid="pdf-lab:parity-audit:eject-mismatches" data-qs-action="PDF_LAB_PARITY_AUDIT_EJECT_MISMATCHES" type="button">Eject Mismatches to Triage →</button>
        </div>
      </header>

      <section className="pdf-lab-parity-metrics" aria-label="Parity audit metrics">
        <div><span>Candidates Run</span><b>50</b></div>
        <div className="pass"><span>Auto-Pass</span><b>47</b></div>
        <div className="warn"><span>Below Gate</span><b>3</b></div>
        <div><span>Gate</span><b>95.0%</b></div>
        <div className="warn"><span>Selected Page</span><b>429 · 91.7%</b></div>
        <div className="fail"><span>Human Cards</span><b>3</b></div>
      </section>

      <main className="pdf-lab-parity-main">
        <aside className="pdf-lab-parity-run" aria-label="Candidate run status">
          <div className="pdf-lab-parity-pane-head">
            <h2>Candidate Run</h2>
            <p>pdf_oxide extraction and JSON comparison status for pages selected by Initial Sweep.</p>
          </div>
          <div className="pdf-lab-parity-run-list">
            {runItems.map(item => (
              <div className={item.page === '429' ? 'pdf-lab-parity-run-item selected' : 'pdf-lab-parity-run-item'} key={item.page}>
                <div className="pdf-lab-parity-page">{item.page}</div>
                <div>
                  <div className="pdf-lab-parity-run-title">
                    <span>{item.title}</span>
                    <span className={`pdf-lab-parity-pill ${item.status}`}>{item.status === 'pass' ? 'Pass' : 'Review'}</span>
                  </div>
                  <div className="pdf-lab-parity-preset">{item.preset} · extracted + compared</div>
                  <div className="pdf-lab-parity-micro-grid">
                    <div><b>{item.parity}</b>parity</div>
                    <div><b>{item.misses}</b>miss</div>
                    <div><b>{item.cards}</b>cards</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </aside>

        <section className="pdf-lab-parity-compare" aria-label="Parity audit table">
          <div className="pdf-lab-parity-compare-head">
            <div>
              <h1>Page 429 Parity Audit</h1>
              <p>Agent expected nodes are compared against deterministic <code>pdf_oxide</code> output. Only unresolved mismatches become human cards.</p>
            </div>
            <div className="pdf-lab-parity-score"><b>91.7%</b><span>Below 95% gate</span></div>
          </div>
          <div className="pdf-lab-parity-legend">
            <span>matched 22</span><span>missing 2</span><span>extra 1</span><span>human cards 3</span>
          </div>
          <div className="pdf-lab-parity-table-wrap">
            <table>
              <thead>
                <tr><th>Status</th><th>Expected Agent Node</th><th>pdf_oxide Emitted Node</th><th>Evidence</th><th>BBox</th></tr>
              </thead>
              <tbody>
                {compareRows.map((row, index) => (
                  <tr className={row.status} key={`${row.status}-${index}`}>
                    <td><span className={`pdf-lab-parity-status ${row.status}`}>{row.status}</span></td>
                    <td><b>{row.expected}</b><span>{row.expectedText}</span></td>
                    <td><b>{row.emitted}</b><span>{row.emittedText}</span></td>
                    <td><code>{row.evidence}</code></td>
                    <td className="pdf-lab-parity-bbox">{row.bbox}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="pdf-lab-parity-triage" aria-label="Triage output">
          <div className="pdf-lab-parity-pane-head">
            <h2>Triage Output</h2>
            <p>Human cards generated only from unresolved compare failures.</p>
          </div>
          <div className="pdf-lab-parity-card summary"><strong>3 cards</strong><span>Page 429 falls below the 95% parity gate. Passing pages continue automatically.</span></div>
          <div className="pdf-lab-parity-card hot"><small>Card 1 · high · page 429</small><h3>definition_list vs table</h3><p>Same visual region emitted as a table, while the agent expected a definition list.</p></div>
          <div className="pdf-lab-parity-card"><small>Card 2 · medium · page 429</small><h3>Missing term/body node</h3><p>“dissociability” was expected as one definition node but split across candidates.</p></div>
          <div className="pdf-lab-parity-card"><small>Card 3 · medium · page 429</small><h3>Reference parent mismatch</h3><p>IR 8062 reference was detected but not attached to the expected parent.</p></div>
          <div className="pdf-lab-parity-card"><small>Auto-forward · 47 pages</small><h3>No human review required</h3><p>Pages above gate are promoted without entering the ambiguity deck.</p></div>
        </aside>
      </main>
    </div>
  )
}
