import { useEffect, useMemo, useRef } from 'react'
import PdfCanvas from '../datalake-explorer/PdfCanvas'
import { ReviewBundleButton } from '../common/ReviewBundleButton'
import { useRegisterAction } from '../../hooks/useRegisterAction'

interface SurgicalTriageTask {
  id: string
  question: string
  reasoning: string
  path: string
  severity: string
  bbox: [number, number, number, number]
}

interface SurgicalTriageViewportProps {
  pdfUrl: string
  pageNumber: number
  taskIndex: number
  taskCount: number
  task: SurgicalTriageTask | null
  intentDraft: string
  onIntentChange: (value: string) => void
  onAccept: () => void
  onReject: () => void
  onSkip: () => void
  onPrevious: () => void
  onNext: () => void
  onOpenAudit: () => void
  onOpenQueue: () => void
}

export function SurgicalTriageViewport(props: SurgicalTriageViewportProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  useRegisterAction('pdf-lab:triage:accept', {
    app: 'pdf-lab',
    action: 'ACCEPT',
    label: 'Confirm (A)',
    description: 'Confirm the active PDF Lab triage card and advance',
  })
  useRegisterAction('pdf-lab:triage:reject', {
    app: 'pdf-lab',
    action: 'REJECT',
    label: 'Reject (R)',
    description: 'Reject the active PDF Lab triage card and advance',
  })
  useRegisterAction('pdf-lab:triage:skip', {
    app: 'pdf-lab',
    action: 'SKIP',
    label: 'Skip (S)',
    description: 'Skip the active PDF Lab triage card',
  })
  useRegisterAction('pdf-lab:triage:intent', {
    app: 'pdf-lab',
    action: 'INTENT',
    label: 'Submit Intent',
    description: 'Submit an intent correction for the active PDF Lab triage card',
  })
  useRegisterAction('pdf-lab:triage:queue', {
    app: 'pdf-lab',
    action: 'OPEN_QUEUE',
    label: 'Open Queue',
    description: 'Open the hidden PDF Lab ambiguity queue',
  })
  useRegisterAction('pdf-lab:triage:audit', {
    app: 'pdf-lab',
    action: 'OPEN_AUDIT',
    label: 'Open Audit',
    description: 'Open full PDF Lab audit and repair mode',
  })
  useRegisterAction('pdf-lab:triage:previous', {
    app: 'pdf-lab',
    action: 'PREVIOUS_CARD',
    label: 'Previous Card',
    description: 'Move to the previous PDF Lab triage card',
  })
  useRegisterAction('pdf-lab:triage:next', {
    app: 'pdf-lab',
    action: 'NEXT_CARD',
    label: 'Next Card',
    description: 'Move to the next PDF Lab triage card',
  })

  const hudPosition = useMemo(() => {
    if (!props.task) return { right: '40px' }
    const [, , x2] = props.task.bbox
    return x2 > 0.75 ? { left: '40px' } : { right: '40px' }
  }, [props.task])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (document.activeElement?.tagName === 'INPUT') return
      const key = event.key.toLowerCase()
      if (key === 'a') props.onAccept()
      if (key === 'r') props.onReject()
      if (key === 's') props.onSkip()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [props.onAccept, props.onReject, props.onSkip])

  useEffect(() => {
    inputRef.current?.focus()
  }, [props.task?.id])

  if (!props.task) return null

  return (
    <div className="pdf-lab-surgical-viewport" data-qid="pdf-lab:triage:root">
      <header className="pdf-lab-surgical-header">
        <div className="surgical-header-left">
          <button aria-label="Action"
            data-qid="pdf-lab:triage:queue"
            data-qs-action="OPEN_QUEUE"
            title="Show ambiguity queue"
            onClick={props.onOpenQueue}
            className="ghost-btn"
          >
            ☰
          </button>
          <span>Card {props.taskIndex + 1} / {props.taskCount}</span>
        </div>
        <div className="surgical-header-title">NIST SP 800-53 Rev. 5 · Surgical Triage</div>
        <div className="surgical-header-actions">
          <ReviewBundleButton
            app="pdf-lab"
            endpoint="/api/pdf-lab/gemini-review-bundle"
            actionId="pdf-lab:triage:gemini-review-bundle"
            action="PDF_LAB_TRIAGE_GEMINI_REVIEW_BUNDLE"
            label="Gemini Bundle"
            className="ghost-btn"
            title="Generate Gemini review bundle"
            description="Generate a Gemini review bundle with context, current code, screenshots, and a five-file zip"
            requestBody={{
              surface: 'pdf-lab',
              route: 'http://localhost:3002/#pdf-lab',
              activeTaskId: props.task.id,
              activePage: props.pageNumber + 1,
              workflowTaskIndex: props.taskIndex,
            }}
          />
          <button aria-label="Action"
            data-qid="pdf-lab:triage:audit"
            data-qs-action="OPEN_AUDIT"
            title="Enter full Audit/Repair mode"
            onClick={props.onOpenAudit}
            className="ghost-btn"
          >
            Audit / Repair
          </button>
        </div>
      </header>

      <main className="pdf-lab-surgical-stage">
        <PdfCanvas
          pdfUrl={props.pdfUrl}
          pageNumber={props.pageNumber}
          surgicalFocusBBox={props.task.bbox}
          surgicalCameraEnabled
        />

        <aside className="pdf-lab-surgical-hud" style={hudPosition}>
          <div className="hud-meta">
            <span className="path">{props.task.path}</span>
            <span className={`severity ${props.task.severity.toLowerCase()}`}>{props.task.severity}</span>
          </div>
          <h2>{props.task.question}</h2>
          <p>{props.task.reasoning}</p>

          <div className="intent-zone">
            <input
              ref={inputRef}
              data-qid="pdf-lab:triage:intent"
              data-qs-action="INTENT"
              title="Type intent: table, move box up, split row"
              className="intent-input"
              value={props.intentDraft}
              onChange={(event) => props.onIntentChange(event.target.value)}
              placeholder="Type intent: table, move box up, split row..."
              autoFocus
            />
          </div>

          <div className="action-triptych">
            <button aria-label="Action"
              data-qid="pdf-lab:triage:reject"
              data-qs-action="REJECT"
              title="Reject this card (R)"
              onClick={props.onReject}
              className="btn-reject"
            >
              Reject (R)
            </button>
            <button aria-label="Action"
              data-qid="pdf-lab:triage:skip"
              data-qs-action="SKIP"
              title="Skip this card (S)"
              onClick={props.onSkip}
              className="btn-skip"
            >
              Skip (S)
            </button>
            <button aria-label="Action"
              data-qid="pdf-lab:triage:accept"
              data-qs-action="ACCEPT"
              title="Confirm this card (A)"
              onClick={props.onAccept}
              className="btn-accept"
            >
              Confirm (A)
            </button>
          </div>
        </aside>
      </main>

      <footer className="pdf-lab-surgical-footer">
        <div className="nav-group">
          <button aria-label="Action"
            data-qid="pdf-lab:triage:previous"
            data-qs-action="PREVIOUS_CARD"
            title="Previous card"
            onClick={props.onPrevious}
          >
            ←
          </button>
          <button aria-label="Action"
            data-qid="pdf-lab:triage:next"
            data-qs-action="NEXT_CARD"
            title="Next card"
            onClick={props.onNext}
          >
            →
          </button>
        </div>
        <div className="hotkeys">USE <kbd>A</kbd> ACCEPT · <kbd>R</kbd> REJECT · <kbd>S</kbd> SKIP</div>
        <div className="status">ZEN MODE ACTIVE</div>
      </footer>
    </div>
  )
}
