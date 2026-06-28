import { useEffect, useRef, useState } from 'react'
import { useRegisterAction } from '../../hooks/useRegisterAction'
import './SurgicalTriageStaticProof.css'

export function SurgicalTriageStaticProof() {
  useRegisterAction('pdf-lab:static-proof:copy-html-css', {
    app: 'pdf-lab',
    action: 'PDF_LAB_STATIC_PROOF_COPY_HTML_CSS',
    label: 'Copy HTML/CSS',
    description: 'Copy the rendered static surgical triage proof markup',
  })
  useRegisterAction('pdf-lab:static-proof:queue', {
    app: 'pdf-lab',
    action: 'PDF_LAB_STATIC_PROOF_QUEUE',
    label: 'Open ambiguity queue',
    description: 'Open the ambiguity queue in the static surgical triage proof',
  })
  useRegisterAction('pdf-lab:static-proof:gemini-bundle', {
    app: 'pdf-lab',
    action: 'PDF_LAB_STATIC_PROOF_GEMINI_BUNDLE',
    label: 'Gemini Bundle',
    description: 'Generate the Gemini review bundle from the static surgical triage proof',
  })
  useRegisterAction('pdf-lab:static-proof:audit', {
    app: 'pdf-lab',
    action: 'PDF_LAB_STATIC_PROOF_AUDIT',
    label: 'Audit / Repair',
    description: 'Open audit and repair mode from the static surgical triage proof',
  })
  useRegisterAction('pdf-lab:static-proof:reject', {
    app: 'pdf-lab',
    action: 'PDF_LAB_STATIC_PROOF_REJECT',
    label: 'Reject',
    description: 'Reject the active static surgical triage card',
  })
  useRegisterAction('pdf-lab:static-proof:skip', {
    app: 'pdf-lab',
    action: 'PDF_LAB_STATIC_PROOF_SKIP',
    label: 'Skip',
    description: 'Skip the active static surgical triage card',
  })
  useRegisterAction('pdf-lab:static-proof:confirm', {
    app: 'pdf-lab',
    action: 'PDF_LAB_STATIC_PROOF_CONFIRM',
    label: 'Confirm',
    description: 'Confirm the active static surgical triage card',
  })
  useRegisterAction('pdf-lab:static-proof:undo-last-decision', {
    app: 'pdf-lab',
    action: 'PDF_LAB_STATIC_PROOF_UNDO_LAST_DECISION',
    label: 'Undo Last Decision',
    description: 'Undo the last triage decision without leaving the active deck',
  })
  useRegisterAction('pdf-lab:static-proof:intent', {
    app: 'pdf-lab',
    action: 'PDF_LAB_STATIC_PROOF_INTENT',
    label: 'Intent correction',
    description: 'Type an intent correction in the static surgical triage proof',
  })

  const inputRef = useRef<HTMLInputElement>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleCopyHtmlCss = async () => {
    const html = `<!doctype html>\n${document.documentElement.outerHTML}`
    await navigator.clipboard.writeText(html)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1400)
  }

  return (
    <div className="pdf-lab-static-proof" data-qid="pdf-lab:static-proof">
      <header className="pdf-lab-static-proof-header" data-qid="pdf-lab:static-proof:header">
        <div className="pdf-lab-static-proof-header-left">
          <button
            data-qid="pdf-lab:static-proof:queue"
            data-qs-action="PDF_LAB_STATIC_PROOF_QUEUE"
            aria-label="Open ambiguity queue"
            title="Open ambiguity queue"
            type="button"
          >
            <span className="pdf-lab-static-proof-menu">☰</span>
          </button>
          <span>Card 19 / 96</span>
        </div>
        <strong className="pdf-lab-static-proof-title">NIST SP 800-53 Rev. 5 · Surgical Triage</strong>
        <div className="pdf-lab-static-proof-header-actions">
          <button
            className="pdf-lab-static-proof-copy"
            data-copied={copied}
            data-qid="pdf-lab:static-proof:copy-html-css"
            data-qs-action="PDF_LAB_STATIC_PROOF_COPY_HTML_CSS"
            aria-label="Copy HTML and CSS"
            title="Copy the rendered HTML/CSS proof"
            type="button"
            onClick={handleCopyHtmlCss}
          >
            {copied ? 'Copied' : 'Copy HTML/CSS'}
          </button>
          <button
            data-qid="pdf-lab:static-proof:gemini-bundle"
            data-qs-action="PDF_LAB_STATIC_PROOF_GEMINI_BUNDLE"
            aria-label="Generate Gemini review bundle"
            title="Generate Gemini review bundle"
            type="button"
          >
            Gemini Bundle
          </button>
          <button
            data-qid="pdf-lab:static-proof:audit"
            data-qs-action="PDF_LAB_STATIC_PROOF_AUDIT"
            aria-label="Open audit and repair mode"
            title="Open audit and repair mode"
            type="button"
          >
            Audit / Repair
          </button>
        </div>
      </header>

      <main className="pdf-lab-static-proof-stage">
        <section className="pdf-lab-static-proof-page-well" aria-label="Original PDF page with static surgical overlay">
          <img
            className="pdf-lab-static-proof-page"
            src="/artifacts/pdf-lab/pdf-lab-surgical-candidate-429.png"
            alt="Original NIST SP 800-53 page 429 glossary definition-list page"
          />
          <div className="pdf-lab-static-proof-fog" aria-hidden="true">
            <div className="pdf-lab-static-proof-dim pdf-lab-static-proof-fog-top" />
            <div className="pdf-lab-static-proof-dim pdf-lab-static-proof-fog-bottom" />
            <div className="pdf-lab-static-proof-dim pdf-lab-static-proof-fog-left" />
            <div className="pdf-lab-static-proof-dim pdf-lab-static-proof-fog-right" />
            <div
              className="pdf-lab-static-proof-bbox"
              data-qid="pdf-lab:static-proof:active-bbox"
              data-qs-action="PDF_LAB_STATIC_PROOF_ACTIVE_BBOX"
              title="Active p0_t0 definition-list bbox"
            />
          </div>
        </section>

        <div className="pdf-lab-static-proof-dot" aria-hidden="true" />
        <div className="pdf-lab-static-proof-thread" aria-hidden="true" />

        <aside className="pdf-lab-static-proof-hud" aria-label="Decision HUD" data-qid="pdf-lab:static-proof:hud">
          <div className="pdf-lab-static-proof-hud-meta">
            <span>GRAPH › APPX A&nbsp; GLOSSARY</span>
            <span>HIGH SEVERITY</span>
          </div>
          <h1>Is this a definition list?</h1>
          <p>Extraction found columns without headers. Confirming rewrites the node type to Definition List.</p>
          <input
            ref={inputRef}
            className="pdf-lab-static-proof-intent"
            data-qid="pdf-lab:static-proof:intent"
            data-qs-action="PDF_LAB_STATIC_PROOF_INTENT"
            aria-label="Type intent correction"
            title="Type intent correction"
            placeholder="Type intent: table, move box, split..."
          />
          <div className="pdf-lab-static-proof-actions">
            <button
              data-qid="pdf-lab:static-proof:reject"
              data-qs-action="PDF_LAB_STATIC_PROOF_REJECT"
              aria-label="Reject this card"
              title="Reject this card"
              type="button"
            >
              Reject<br />(R)
            </button>
            <button
              data-qid="pdf-lab:static-proof:skip"
              data-qs-action="PDF_LAB_STATIC_PROOF_SKIP"
              aria-label="Skip this card"
              title="Skip this card"
              type="button"
            >
              Skip<br />(S)
            </button>
            <button
              className="pdf-lab-static-proof-confirm"
              data-qid="pdf-lab:static-proof:confirm"
              data-qs-action="PDF_LAB_STATIC_PROOF_CONFIRM"
              aria-label="Confirm this card"
              title="Confirm this card"
              type="button"
            >
              Confirm<br />(A)
            </button>
          </div>
        </aside>
        <div className="pdf-lab-static-proof-star" aria-hidden="true" />
      </main>

      <footer className="pdf-lab-static-proof-footer" data-qid="pdf-lab:static-proof:footer">
        <div className="pdf-lab-static-proof-footer-nav">
          <span>← PREV</span>
          <span>|</span>
          <span>NEXT →</span>
        </div>
        <div className="pdf-lab-static-proof-hotkeys">
          USE <kbd>A</kbd> ACCEPT · <kbd>R</kbd> REJECT · <kbd>S</kbd> SKIP
        </div>
        <div className="pdf-lab-static-proof-footer-right">
          <button
            className="pdf-lab-static-proof-undo"
            data-qid="pdf-lab:static-proof:undo-last-decision"
            data-qs-action="PDF_LAB_STATIC_PROOF_UNDO_LAST_DECISION"
            aria-label="Undo last decision"
            title="Undo the last triage decision"
            type="button"
          >
            Undo Last Decision
          </button>
          <span className="pdf-lab-static-proof-zen">ACTIVE TRIAGE DECK</span>
        </div>
      </footer>
    </div>
  )
}
