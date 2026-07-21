import React, { useCallback, useEffect, useMemo, useState } from 'react'
import './TauLoopView.css'

/** Transparent tau-loop viewer.
 *
 * Renders the evidence chain of one extraction-repair loop run, polled
 * from the read-only artifact API: comparison defect vector, second-pass
 * backlog (fingerprinted bug reports), dry-run ticket projections,
 * per-page repair terminal ledgers, regression verdict, and the tau
 * closure report. Everything shown is a persisted artifact — the view
 * replays identically after the run finishes.
 */

const POLL_MS = 3000

type JsonRecord = Record<string, unknown>

interface LoopRunPayload {
  ok: boolean
  run: string
  runDir: string
  artifacts: {
    comparison?: JsonRecord | null
    backlog?: JsonRecord | null
    human_triage_queue?: JsonRecord | null
    ticket_projection?: JsonRecord | null
    closure_report?: JsonRecord | null
    regression_verdict?: JsonRecord | null
    run_summary?: JsonRecord | null
  }
  terminal_ledgers: Record<string, JsonRecord | null>
  repair_receipts: Record<string, JsonRecord | null>
  page_images: Record<string, string[]>
  page_dirs: string[]
}

function runFileUrl(runId: string, relative: string): string {
  return `/api/pdf-lab/loop-runs/${encodeURIComponent(runId)}/file?path=${encodeURIComponent(relative)}`
}

function useLoopRuns(): { runs: string[]; error: string | null } {
  const [runs, setRuns] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const resp = await fetch('/api/pdf-lab/loop-runs')
        const payload = await resp.json()
        if (cancelled) return
        if (payload.ok) {
          setRuns(payload.runs as string[])
          setError(null)
        } else {
          setError(String(payload.error ?? 'unknown error'))
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      }
    }
    void load()
    const timer = window.setInterval(load, POLL_MS * 4)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])
  return { runs, error }
}

function useLoopRun(runId: string | null): { payload: LoopRunPayload | null; error: string | null } {
  const [payload, setPayload] = useState<LoopRunPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    if (!runId) return
    try {
      const resp = await fetch(`/api/pdf-lab/loop-runs/${encodeURIComponent(runId)}`)
      const body = (await resp.json()) as LoopRunPayload
      if (body.ok) {
        setPayload(body)
        setError(null)
      } else {
        setError(String((body as unknown as JsonRecord).error ?? 'unknown error'))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [runId])
  useEffect(() => {
    setPayload(null)
    if (!runId) return
    void load()
    const timer = window.setInterval(load, POLL_MS)
    return () => window.clearInterval(timer)
  }, [runId, load])
  return { payload, error }
}

function normalizedBbox(value: unknown): [number, number, number, number] | null {
  if (!Array.isArray(value) || value.length !== 4) return null
  const [x0, y0, x1, y1] = value.map(Number)
  if ([x0, y0, x1, y1].some(Number.isNaN)) return null
  if (x1 <= x0 || y1 <= y0 || x1 > 1.5 || y1 > 1.5) return null
  return [x0, y0, x1, y1]
}

function PagePanel({ runId, payload }: { runId: string; payload: LoopRunPayload }) {
  const pagesWithImages = payload.page_dirs.filter((dir) => (payload.page_images[dir] ?? []).length > 0)
  const [selectedPage, setSelectedPage] = useState<string | null>(null)
  const page = selectedPage ?? pagesWithImages[0] ?? null
  if (!page) return <div className="tau-loop-empty">no page renders in this run yet</div>

  const images = payload.page_images[page] ?? []
  const pageNumber = Number(page.replace('page_', ''))
  const backlogEntries = ((payload.artifacts.backlog?.entries ?? []) as JsonRecord[]).filter(
    (entry) => Number(entry.page) === pageNumber,
  )
  const overlays = backlogEntries
    .map((entry) => ({ bbox: normalizedBbox(entry.target_bbox), label: String(entry.kind ?? '') }))
    .filter((item): item is { bbox: [number, number, number, number]; label: string } => item.bbox !== null)

  return (
    <div>
      <div className="tau-loop-meta">
        {pagesWithImages.map((dir) => (
          <button
            key={dir}
            className={dir === page ? 'tau-loop-run tau-loop-run-active' : 'tau-loop-run'}
            onClick={() => setSelectedPage(dir)}
          >
            {dir}
          </button>
        ))}
      </div>
      <div className="tau-loop-page-frame">
        <img src={runFileUrl(runId, images[0])} alt={page} className="tau-loop-page-image" />
        {overlays.map((overlay, index) => (
          <div
            key={index}
            className="tau-loop-bbox"
            title={overlay.label}
            style={{
              left: `${overlay.bbox[0] * 100}%`,
              top: `${overlay.bbox[1] * 100}%`,
              width: `${(overlay.bbox[2] - overlay.bbox[0]) * 100}%`,
              height: `${(overlay.bbox[3] - overlay.bbox[1]) * 100}%`,
            }}
          >
            <span className="tau-loop-bbox-label">{overlay.label}</span>
          </div>
        ))}
      </div>
      {images.length > 1 && (
        <div className="tau-loop-meta">{images.length} renders (annotated variants available in the run directory)</div>
      )}
      {overlays.length === 0 && <div className="tau-loop-meta">no backlog bboxes on this page</div>}
    </div>
  )
}

function DefectVectorTable({ comparison }: { comparison: JsonRecord }) {
  const vector = (comparison.defect_vector ?? {}) as Record<string, number>
  const blockers = (comparison.blockers ?? []) as string[]
  return (
    <div>
      <table className="tau-loop-table">
        <tbody>
          {Object.entries(vector).map(([dimension, count]) => (
            <tr key={dimension} className={count > 0 && dimension !== 'matched_expected' && dimension !== 'waived_extras' ? 'tau-loop-bad' : ''}>
              <td>{dimension}</td>
              <td>{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className={comparison.passed ? 'tau-loop-pass' : 'tau-loop-fail'}>
        {comparison.passed ? 'STRICT VERDICT: PASSED' : `BLOCKED: ${blockers.join(' · ') || 'not passed'}`}
      </div>
    </div>
  )
}

function BacklogPanel({ backlog }: { backlog: JsonRecord }) {
  const entries = (backlog.entries ?? []) as JsonRecord[]
  return (
    <div>
      <div className="tau-loop-meta">
        findings: {String(backlog.finding_count ?? '?')} · backlog entries: {String(backlog.backlog_count ?? '?')}
      </div>
      {entries.map((entry) => (
        <div className="tau-loop-card" key={String(entry.defect_key)}>
          <div className="tau-loop-card-title">
            p{String(entry.page)} · {String(entry.kind)}
            <span className="tau-loop-fingerprint">{String(entry.defect_key).slice(0, 19)}…</span>
          </div>
          <div>{String(entry.reason ?? '')}</div>
          <div className="tau-loop-fix">
            {entry.recommended_engine_fix
              ? `fix: ${String(entry.recommended_engine_fix)}`
              : 'no engine-fix guidance yet'}
          </div>
          <div className="tau-loop-meta">owner: {String(entry.proposed_owner_layer ?? 'unrouted')} · observations: {String(entry.observation_count ?? 1)}</div>
        </div>
      ))}
      {entries.length === 0 && <div className="tau-loop-empty">no backlog entries</div>}
    </div>
  )
}

function TicketsPanel({ projection }: { projection: JsonRecord }) {
  const tickets = (projection.tickets ?? []) as JsonRecord[]
  return (
    <div>
      <div className="tau-loop-meta">
        {String(projection.ticket_count ?? tickets.length)} projected · {projection.dry_run ? 'DRY RUN (not filed)' : 'apply-gated'}
      </div>
      {tickets.map((ticket, index) => (
        <div className="tau-loop-card" key={index}>
          <div className="tau-loop-card-title">{String(ticket.title)}</div>
          <div className="tau-loop-meta">{((ticket.labels ?? []) as string[]).join(' · ')}</div>
          <details>
            <summary>body</summary>
            <pre className="tau-loop-pre">{String(ticket.body ?? '')}</pre>
          </details>
        </div>
      ))}
      {tickets.length === 0 && <div className="tau-loop-empty">no tickets projected</div>}
    </div>
  )
}

function RepairReceiptCard({ runId, pageDir, receipt }: { runId: string; pageDir: string; receipt: JsonRecord }) {
  const status = String(receipt.status ?? '')
  const rolledBack = status.startsWith('rolled_back') || status.startsWith('rejected')
  const patchPath = typeof receipt.patch_path === 'string' ? receipt.patch_path.split('/').pop() : null
  const verify = (receipt.verify ?? null) as JsonRecord | null
  return (
    <div className="tau-loop-card">
      <div className="tau-loop-card-title">
        repair {String(receipt.attempt_id ?? '')}
        <span className="tau-loop-fingerprint">{String(receipt.defect_key ?? '').slice(0, 19)}</span>
      </div>
      <div className={rolledBack ? 'tau-loop-fail' : 'tau-loop-pass'}>{status}</div>
      <div className="tau-loop-meta">preimage: {String(receipt.preimage_sha ?? '').slice(0, 12)}</div>
      {typeof receipt.commit_sha === 'string' && receipt.commit_sha && (
        <div className="tau-loop-meta">
          verified commit {receipt.commit_sha.slice(0, 12)} on {String(receipt.attempt_branch)} · {String(receipt.promotion ?? '')}
        </div>
      )}
      {verify && (
        <div className="tau-loop-meta">
          verify exit={String(verify.exit_code)} · {((receipt.verify_command ?? []) as string[]).join(' ')}
        </div>
      )}
      {receipt.rollback != null && (
        <div className="tau-loop-meta">rollback: {((receipt.rollback as JsonRecord).actions as string[] | undefined)?.join(', ')}</div>
      )}
      {patchPath && (
        <details>
          <summary>patch diff</summary>
          <PatchDiff url={runFileUrl(runId, `${pageDir}/${patchPath}`)} />
        </details>
      )}
    </div>
  )
}

function PatchDiff({ url }: { url: string }) {
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    fetch(url)
      .then((resp) => resp.text())
      .then((body) => {
        if (!cancelled) setText(body)
      })
      .catch(() => {
        if (!cancelled) setText('(patch unavailable)')
      })
    return () => {
      cancelled = true
    }
  }, [url])
  if (text === null) return <div className="tau-loop-empty">loading…</div>
  return (
    <pre className="tau-loop-pre">
      {text.split('\n').map((line, index) => (
        <span
          key={index}
          className={line.startsWith('+') ? 'tau-loop-diff-add' : line.startsWith('-') ? 'tau-loop-diff-del' : undefined}
        >
          {line}
          {'\n'}
        </span>
      ))}
    </pre>
  )
}

function RepairPanel({
  runId,
  ledgers,
  receipts,
  verdict,
}: {
  runId: string
  ledgers: Record<string, JsonRecord | null>
  receipts: Record<string, JsonRecord | null>
  verdict: JsonRecord | null | undefined
}) {
  const entries = Object.entries(ledgers)
  return (
    <div>
      {entries.map(([pageDir, ledger]) => (
        <div className="tau-loop-card" key={pageDir}>
          <div className="tau-loop-card-title">{pageDir}</div>
          {ledger ? (
            <>
              <div className={ledger.terminal_status === 'blocked_substrate' ? 'tau-loop-fail' : 'tau-loop-meta'}>
                {String(ledger.terminal_status)} · {String(ledger.reason)}
              </div>
              {typeof ledger.patch_delegate_blocked_reason === 'string' && (
                <div className="tau-loop-meta">delegate blocked: {ledger.patch_delegate_blocked_reason}</div>
              )}
            </>
          ) : (
            <div className="tau-loop-empty">ledger unreadable</div>
          )}
          {receipts[pageDir] && <RepairReceiptCard runId={runId} pageDir={pageDir} receipt={receipts[pageDir] as JsonRecord} />}
        </div>
      ))}
      {entries.length === 0 && <div className="tau-loop-empty">no repair attempts recorded</div>}
      {verdict && (
        <div className="tau-loop-card">
          <div className="tau-loop-card-title">regression verdict</div>
          <div className={verdict.verdict === 'PASS' ? 'tau-loop-pass' : 'tau-loop-fail'}>{String(verdict.verdict)}</div>
          {((verdict.failures ?? []) as string[]).map((failure) => (
            <div className="tau-loop-meta" key={failure}>{failure}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function ClosurePanel({ report }: { report: JsonRecord }) {
  const blockers = (report.blockers ?? []) as string[]
  return (
    <div>
      <div className={report.closed ? 'tau-loop-pass' : 'tau-loop-fail'}>
        {report.closed ? 'CLOSED' : 'NOT CLOSED'}
      </div>
      {blockers.map((blocker) => (
        <div className="tau-loop-meta" key={blocker}>{blocker}</div>
      ))}
      <div className="tau-loop-meta">goal_hash: {String(report.goal_hash ?? 'n/a')}</div>
      <div className="tau-loop-meta">semantic_truth: {String(report.semantic_truth ?? '')}</div>
    </div>
  )
}

export function TauLoopView() {
  const { runs, error: runsError } = useLoopRuns()
  const [selected, setSelected] = useState<string | null>(null)
  const runId = selected ?? runs[0] ?? null
  const { payload, error } = useLoopRun(runId)
  const artifacts = payload?.artifacts

  const stages = useMemo(
    () => [
      {
        key: 'page',
        title: '0 · Original Page + Findings',
        body: payload && runId ? <PagePanel runId={runId} payload={payload} /> : null,
      },
      {
        key: 'comparison',
        title: '1 · Extraction vs Expected',
        body: artifacts?.comparison ? <DefectVectorTable comparison={artifacts.comparison} /> : null,
      },
      {
        key: 'backlog',
        title: '2 · Second Pass → Bug Reports',
        body: artifacts?.backlog ? <BacklogPanel backlog={artifacts.backlog} /> : null,
      },
      {
        key: 'tickets',
        title: '3 · Ticket Projections',
        body: artifacts?.ticket_projection ? <TicketsPanel projection={artifacts.ticket_projection} /> : null,
      },
      {
        key: 'repair',
        title: '4 · Repair Attempts (receipts + diffs)',
        body:
          payload && runId ? (
            <RepairPanel
              runId={runId}
              ledgers={payload.terminal_ledgers}
              receipts={payload.repair_receipts ?? {}}
              verdict={artifacts?.regression_verdict}
            />
          ) : null,
      },
      {
        key: 'closure',
        title: '5 · Tau Closure Verdict',
        body: artifacts?.closure_report ? <ClosurePanel report={artifacts.closure_report} /> : null,
      },
    ],
    [artifacts, payload, runId],
  )

  return (
    <div className="tau-loop-root">
      <aside className="tau-loop-sidebar">
        <h2>Loop runs</h2>
        {runsError && <div className="tau-loop-fail">{runsError}</div>}
        {runs.map((run) => (
          <button
            key={run}
            className={run === runId ? 'tau-loop-run tau-loop-run-active' : 'tau-loop-run'}
            onClick={() => setSelected(run)}
          >
            {run}
          </button>
        ))}
        {runs.length === 0 && !runsError && <div className="tau-loop-empty">no runs yet</div>}
      </aside>
      <main className="tau-loop-stages">
        {error && <div className="tau-loop-fail">{error}</div>}
        {stages.map((stage) => (
          <section className="tau-loop-stage" key={stage.key}>
            <h3>{stage.title}</h3>
            {stage.body ?? <div className="tau-loop-empty">awaiting artifact…</div>}
          </section>
        ))}
      </main>
    </div>
  )
}
