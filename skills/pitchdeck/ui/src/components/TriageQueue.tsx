import { useEffect, useMemo, useState } from 'react'
import { Check, ShieldAlert, X } from 'lucide-react'
import { toast } from './Toasts'
import type { UiDeckBundle } from '../types'
// Direct import, never a barrel file (best-practices-react).
import { Button } from './ui/button'

// Writable claim triage (#1227): risk-ordered keyboard queue with the claim
// beside its verbatim evidence spans. Decisions post /api/claim-decide — the
// sanctioned ledger write path (full bundle validation + replayable audit
// log). High-risk and numeric claims can never be batch-decided; here every
// decision is individual by construction.

const RISK_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2, mandatory_non_claim: 3 }

interface TriageClaim {
  id: string
  text: string
  risk: string
  kind: string
  required_qualifier?: string | null
  evidence_spans: { source_id: string; text: string }[]
  slides: string[]
}

function candidateQueue(deck: UiDeckBundle): TriageClaim[] {
  const map = new Map<string, TriageClaim>()
  for (const slide of deck.slides) {
    for (const claim of slide.claims) {
      if (claim.status !== 'candidate') continue
      const existing = map.get(claim.id)
      if (existing) existing.slides.push(String(slide.order))
      else
        map.set(claim.id, {
          id: claim.id,
          text: claim.text,
          risk: claim.risk,
          kind: claim.kind,
          required_qualifier: claim.required_qualifier,
          evidence_spans: (claim as { evidence_spans?: TriageClaim['evidence_spans'] }).evidence_spans ?? [],
          slides: [String(slide.order)],
        })
    }
  }
  return [...map.values()].sort((a, b) => {
    const risk = (RISK_ORDER[a.risk] ?? 9) - (RISK_ORDER[b.risk] ?? 9)
    if (risk !== 0) return risk
    return Number(/\d/.test(b.text)) - Number(/\d/.test(a.text))
  })
}

export function TriageQueue({ deck, onChanged }: { deck: UiDeckBundle; onChanged: () => void }) {
  const queue = useMemo(() => candidateQueue(deck), [deck])
  const [index, setIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [reviewer, setReviewer] = useState(() => window.localStorage.getItem('deck-reviewer') ?? '')
  const current = queue[Math.min(index, queue.length - 1)]

  useEffect(() => {
    window.localStorage.setItem('deck-reviewer', reviewer)
  }, [reviewer])

  const decide = async (decision: 'approve' | 'reject') => {
    if (!current || busy) return
    if (!reviewer.trim()) {
      toast('Enter your reviewer name first — approvals carry provenance.', 'error')
      return
    }
    setBusy(true)
    const response = await fetch('/api/claim-decide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ claim_id: current.id, decision, decided_by: reviewer.trim() }),
    })
    setBusy(false)
    if (!response.ok) {
      const data = (await response.json()) as { error?: string }
      toast(`Decision rejected: ${data.error ?? response.status}`, 'error')
      return
    }
    toast(`${decision === 'approve' ? 'Approved' : 'Rejected'} ${current.id}`)
    onChanged()
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return
      if (event.key === 'j') setIndex((value) => Math.min(queue.length - 1, value + 1))
      else if (event.key === 'k') setIndex((value) => Math.max(0, value - 1))
      else if (event.key === 'a') void decide('approve')
      else if (event.key === 'r') void decide('reject')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue.length, current?.id, reviewer, busy])

  if (!queue.length) {
    return (
      <p className="m-0 rounded-lg border border-emerald-700/50 bg-emerald-500/10 p-3 text-sm text-emerald-300">
        No candidate claims — the review queue is clear.
      </p>
    )
  }

  return (
    <section aria-label="Claim triage queue" data-qid="deck:triage:queue" className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
      <header className="mb-3 flex items-center gap-3">
        <h3 className="m-0 text-sm font-semibold text-slate-200">
          Triage {index + 1} / {queue.length}
        </h3>
        <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${current.risk === 'high' ? 'bg-rose-500/20 text-rose-300' : 'bg-slate-700 text-slate-300'}`}>
          {current.risk}
        </span>
        {/\d/.test(current.text) ? (
          <span title="Contains numbers — individual decision required" className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-1.5 py-0.5 font-mono text-[10px] text-amber-300">
            <ShieldAlert aria-hidden className="h-3 w-3" /> numeric
          </span>
        ) : null}
        <input
          data-qid="deck:triage:reviewer"
          title="Your reviewer identity — recorded as approval provenance"
          placeholder="reviewer name"
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
          className="ml-auto w-40 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
        />
      </header>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="m-0 mb-1 font-mono text-[10px] uppercase text-slate-500">Claim · {current.id} · slides {current.slides.join(', ')}</p>
          <p className="m-0 text-sm leading-relaxed text-slate-100">{current.text}</p>
          {current.required_qualifier ? (
            <p className="m-0 mt-2 text-xs text-amber-300">Required qualifier: {current.required_qualifier}</p>
          ) : null}
        </div>
        <div>
          <p className="m-0 mb-1 font-mono text-[10px] uppercase text-slate-500">Evidence spans ({current.evidence_spans.length})</p>
          {current.evidence_spans.length ? (
            current.evidence_spans.map((span, spanIndex) => (
              <blockquote key={`${span.source_id}-${spanIndex}`} className="m-0 mb-2 border-l-2 border-cyan-600 pl-2 text-xs text-slate-300">
                {span.text}
                <footer className="mt-0.5 font-mono text-[10px] text-slate-500">{span.source_id}</footer>
              </blockquote>
            ))
          ) : (
            <p className="m-0 text-xs text-rose-300">No spans — rendering this claim will not publish (RENDERING_UNBOUND).</p>
          )}
        </div>
      </div>
      <footer className="mt-3 flex items-center gap-2">
        <Button
          type="button"
          data-qid="deck:triage:approve"
          data-qs-action="DECK_TRIAGE_APPROVE"
          title="Approve this claim with your provenance (A)"
          disabled={busy}
          onClick={() => void decide('approve')}
          className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-emerald-600 bg-emerald-600/20 px-3 py-1.5 text-sm text-emerald-200 disabled:opacity-40"
        >
          <Check aria-hidden className="h-4 w-4" /> Approve (a)
        </Button>
        <Button
          type="button"
          data-qid="deck:triage:reject"
          data-qs-action="DECK_TRIAGE_REJECT"
          title="Reject this claim (R)"
          disabled={busy}
          onClick={() => void decide('reject')}
          className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-rose-600 bg-rose-600/20 px-3 py-1.5 text-sm text-rose-200 disabled:opacity-40"
        >
          <X aria-hidden className="h-4 w-4" /> Reject (r)
        </Button>
        <span className="ml-auto text-xs text-slate-500">j/k navigate · a approve · r reject — every decision re-validates the bundle</span>
      </footer>
    </section>
  )
}
