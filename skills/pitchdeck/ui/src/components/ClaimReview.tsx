import { ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { TriageQueue } from './TriageQueue'
import type { UiDeckBundle } from '../types'

const STATUS_STYLES: Record<string, string> = {
  approved: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-300',
  qualified: 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300',
  candidate: 'border-amber-500/50 bg-amber-500/10 text-amber-300',
  rejected: 'border-rose-500/50 bg-rose-500/10 text-rose-300',
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'approved' || status === 'qualified') return <ShieldCheck aria-hidden className="h-4 w-4" />
  if (status === 'candidate') return <ShieldQuestion aria-hidden className="h-4 w-4" />
  return <ShieldAlert aria-hidden className="h-4 w-4" />
}

/** Read-only claim-ledger review over the emitted bundle, grouped by slide. */
export function ClaimReview({ deck, onChanged }: { deck: UiDeckBundle; onChanged?: () => void }) {
  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col gap-6 overflow-y-auto px-8 py-10">
      <TriageQueue deck={deck} onChanged={onChanged ?? (() => window.location.reload())} />
      <header className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="m-0 text-2xl font-semibold">Claim review — {deck.title}</h1>
        <p className="m-0 text-sm text-slate-400">
          validation: <span className="font-mono">{deck.validation_readiness}</span>
          {' · '}
          {Object.entries(deck.claim_summary)
            .map(([status, count]) => `${count} ${status}`)
            .join(' · ')}
        </p>
      </header>
      {deck.validation_gaps.length > 0 ? (
        <section
          aria-label="Validation gaps"
          className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 text-sm text-amber-200"
        >
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {deck.validation_gaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {deck.slides.map((slide) => (
        <section key={slide.id} className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <h2 className="m-0 text-base font-medium text-slate-200">
            <span className="mr-2 font-mono text-xs text-slate-500">#{slide.order}</span>
            {slide.title}
          </h2>
          {slide.claims.length === 0 ? (
            <p className="mb-0 mt-3 text-sm text-slate-500">No ledger claims bound to this slide.</p>
          ) : (
            <ul className="m-0 mt-3 flex list-none flex-col gap-2 p-0">
              {slide.claims.map((claim) => (
                <li
                  key={claim.id}
                  className={`flex items-start gap-3 rounded-lg border px-3 py-2 text-sm ${STATUS_STYLES[claim.status] ?? STATUS_STYLES.candidate}`}
                >
                  <StatusIcon status={claim.status} />
                  <div className="min-w-0">
                    <p className="m-0">{claim.text}</p>
                    <p className="m-0 mt-1 font-mono text-xs opacity-70">
                      {claim.id} · {claim.status} · risk:{claim.risk}
                      {claim.required_qualifier ? ` · qualifier: ${claim.required_qualifier}` : ''}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}
