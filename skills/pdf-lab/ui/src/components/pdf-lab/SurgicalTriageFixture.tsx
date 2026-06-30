import { useEffect, useRef } from 'react'
import { useRegisterAction } from '../../hooks/useRegisterAction'

export function SurgicalTriageFixture() {
  const inputRef = useRef<HTMLInputElement>(null)

  useRegisterAction('pdf-lab:surgical-fixture:queue', {
    app: 'pdf-lab',
    action: 'PDF_LAB_SURGICAL_FIXTURE_QUEUE',
    label: 'Open ambiguity queue',
    description: 'Open the ambiguity queue in the surgical fixture',
  })
  useRegisterAction('pdf-lab:surgical-fixture:gemini-bundle', {
    app: 'pdf-lab',
    action: 'PDF_LAB_SURGICAL_FIXTURE_GEMINI_BUNDLE',
    label: 'Gemini Bundle',
    description: 'Generate the Gemini review bundle from the surgical fixture',
  })
  useRegisterAction('pdf-lab:surgical-fixture:audit', {
    app: 'pdf-lab',
    action: 'PDF_LAB_SURGICAL_FIXTURE_AUDIT',
    label: 'Audit / Repair',
    description: 'Open audit and repair mode from the surgical fixture',
  })
  useRegisterAction('pdf-lab:surgical-fixture:reject', {
    app: 'pdf-lab',
    action: 'PDF_LAB_SURGICAL_FIXTURE_REJECT',
    label: 'Reject',
    description: 'Reject the active clean-room fixture triage card',
  })
  useRegisterAction('pdf-lab:surgical-fixture:skip', {
    app: 'pdf-lab',
    action: 'PDF_LAB_SURGICAL_FIXTURE_SKIP',
    label: 'Skip',
    description: 'Skip the active clean-room fixture triage card',
  })
  useRegisterAction('pdf-lab:surgical-fixture:confirm', {
    app: 'pdf-lab',
    action: 'PDF_LAB_SURGICAL_FIXTURE_CONFIRM',
    label: 'Confirm',
    description: 'Confirm the active clean-room fixture triage card',
  })
  useRegisterAction('pdf-lab:surgical-fixture:intent', {
    app: 'pdf-lab',
    action: 'PDF_LAB_SURGICAL_FIXTURE_INTENT',
    label: 'Intent correction',
    description: 'Type an intent correction in the clean-room fixture',
  })

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  return (
    <div className="surgical-fixture" data-qid="pdf-lab:surgical-fixture">
      <header className="surgical-fixture-header" data-qid="pdf-lab:surgical-fixture:header">
        <div className="surgical-fixture-header-left">
          <button aria-label="Action"
            className="surgical-fixture-icon"
            data-qid="pdf-lab:surgical-fixture:queue"
            data-qs-action="PDF_LAB_SURGICAL_FIXTURE_QUEUE"
            title="Open ambiguity queue"
            type="button"
          >
            ☰
          </button>
          <span className="surgical-fixture-progress">Card 19 / 96</span>
        </div>
        <strong className="surgical-fixture-title">NIST SP 800-53 Rev. 5 · Surgical Triage</strong>
        <div className="surgical-fixture-actions">
          <button aria-label="Action"
            className="surgical-fixture-ghost"
            data-qid="pdf-lab:surgical-fixture:gemini-bundle"
            data-qs-action="PDF_LAB_SURGICAL_FIXTURE_GEMINI_BUNDLE"
            title="Generate Gemini review bundle"
            type="button"
          >
            Gemini Bundle
          </button>
          <button aria-label="Action"
            className="surgical-fixture-ghost"
            data-qid="pdf-lab:surgical-fixture:audit"
            data-qs-action="PDF_LAB_SURGICAL_FIXTURE_AUDIT"
            title="Open audit and repair mode"
            type="button"
          >
            Audit / Repair
          </button>
        </div>
      </header>

      <main className="surgical-fixture-stage">
        <section className="surgical-fixture-pdf" data-qid="pdf-lab:surgical-fixture:pdf-canvas">
          <div className="surgical-fixture-page">
            <div className="fixture-running-header">
              <span>NIST SP 800-53, Rev. 5</span>
              <span>Security and Privacy Controls for Information Systems and Organizations</span>
            </div>
            <article className="fixture-document">
              <p className="fixture-sentinel">Appendix A · Glossary / Definition List</p>
              <h1>CONTROL BASELINES</h1>
              <p>
                The control baselines that have previously been included in NIST Special Publication 800-53
                have been relocated to <a>NIST Special Publication 800-53B</a>. SP 800-53B contains security
                and privacy control baselines for federal information systems and organizations.
              </p>
              <p>
                It provides guidance for tailoring control baselines and for developing overlays to support
                the security and privacy requirements of stakeholders and their organizations.
              </p>
              <div
                className="fixture-active-bbox"
                data-qid="pdf-lab:surgical-fixture:active-bbox"
                data-qs-action="PDF_LAB_SURGICAL_FIXTURE_ACTIVE_BBOX"
                title="Active evidence bbox"
              >
                <div className="fixture-term-row"><b>discretionary access control</b><span>An access control policy that is enforced over subjects and objects.</span></div>
                <div className="fixture-term-row"><b>disassociability</b><span>Processing personally identifiable information without association to individuals.</span></div>
                <div className="fixture-term-row"><b>domain</b><span>An environment that includes systems and entities with authority to access resources.</span></div>
                <span className="fixture-thread-dot" />
              </div>
            </article>
          </div>
          <div className="surgical-fixture-mask" data-qid="pdf-lab:surgical-fixture:mask" />
          <div className="fixture-thread-line" data-qid="pdf-lab:surgical-fixture:thread" />
        </section>

        <aside className="surgical-fixture-hud" data-qid="pdf-lab:surgical-fixture:hud">
          <div className="fixture-hud-meta">
            <span>NIST › APPX A › GLOSSARY</span>
            <span>HIGH</span>
          </div>
          <h2>Is this a definition list?</h2>
          <p>
            pdf_oxide emitted a table object. The agent found term/definition rows without a table header.
            Confirming rewrites the node as a definition list.
          </p>
          <input
            ref={inputRef}
            data-qid="pdf-lab:surgical-fixture:intent"
            data-qs-action="PDF_LAB_SURGICAL_FIXTURE_INTENT"
            title="Type intent correction"
            placeholder="Type intent correction: table, move box up, split row 2…"
          />
          <div className="fixture-triptych">
            <button aria-label="Action"
              data-qid="pdf-lab:surgical-fixture:reject"
              data-qs-action="PDF_LAB_SURGICAL_FIXTURE_REJECT"
              title="Reject this card"
              type="button"
            >
              Reject (R)
            </button>
            <button aria-label="Action"
              data-qid="pdf-lab:surgical-fixture:skip"
              data-qs-action="PDF_LAB_SURGICAL_FIXTURE_SKIP"
              title="Skip this card"
              type="button"
            >
              Skip (S)
            </button>
            <button aria-label="Action"
              data-qid="pdf-lab:surgical-fixture:confirm"
              data-qs-action="PDF_LAB_SURGICAL_FIXTURE_CONFIRM"
              title="Confirm this card"
              type="button"
            >
              Confirm (A)
            </button>
          </div>
        </aside>
      </main>

      <footer className="surgical-fixture-footer" data-qid="pdf-lab:surgical-fixture:footer">
        <span>Use <kbd>A</kbd> Accept · <kbd>R</kbd> Reject · <kbd>S</kbd> Skip · <kbd>Enter</kbd> Submit Intent</span>
      </footer>
    </div>
  )
}
