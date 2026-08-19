import { useEffect, useRef, useState } from "react";

// Reviewer surfaces for #1451 (evidence-linked review dossier), #1452 (rubric
// coverage + follow-up), #1453 (rehearsal turn state). Everything rendered
// here is a readback of backend-published artifacts; nothing is invented in
// the browser, and dismissing a suggestion journals an attributable action
// without touching coverage evidence.

type Span = {
  span_id: string;
  event_ids: string[];
  start_s: number;
  end_s: number;
};

type Claim = {
  claim_id: string;
  text: string;
  disposition: string;
  span_ids: string[];
};

type Review = {
  review_id: string;
  media_locator: string;
  questions: { question_id: string; question_revision: number; text: string }[];
  answer_spans: Span[];
  review_claims: Claim[];
};

type Coverage = { criterion_id: string; state: string };
type Suggestion = { criterion_id: string; question_text: string; why_this_is_still_open: string };
type Rubric = { coverage: Coverage[]; suggestions: Suggestion[] };
type RehearsalTurn = { turn_id: string; question_text: string; audio_status: string; question_revision: number };
type Insights = { review?: Review; rubric?: Rubric; rehearsal?: { turns: RehearsalTurn[] } };

const DISPOSITION_STYLE: Record<string, string> = {
  supported_by_interview: "bg-emerald-900/60 border-emerald-500 text-emerald-100",
  supported_by_authorized_artifact: "bg-emerald-900/60 border-emerald-400 text-emerald-100",
  candidate_assertion_unverified: "bg-amber-900/60 border-amber-500 text-amber-100",
  contradicted: "bg-rose-900/60 border-rose-500 text-rose-100",
  insufficient_evidence: "bg-slate-800 border-slate-500 text-slate-200",
};

const COVERAGE_STYLE: Record<string, string> = {
  covered: "bg-emerald-800 text-emerald-100",
  partially_covered: "bg-amber-800 text-amber-100",
  untested: "bg-slate-700 text-slate-200",
  contradicted: "bg-rose-800 text-rose-100",
  not_applicable: "bg-slate-800 text-slate-400",
};

export function InsightsPanel() {
  const [insights, setInsights] = useState<Insights>({});
  const [activeSpan, setActiveSpan] = useState<Span | null>(null);
  const mediaRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const response = await fetch("/api/insights");
        if (response.ok && alive) setInsights(await response.json());
      } catch {
        /* server-side artifact readback only; nothing to invent on failure */
      }
    };
    void poll();
    const timer = setInterval(poll, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const { review, rubric, rehearsal } = insights;
  if (!review && !rubric && !rehearsal) return null;

  const seekClaim = (claim: Claim) => {
    if (!review) return;
    const span = review.answer_spans.find((candidate) => claim.span_ids.includes(candidate.span_id));
    if (!span) return;
    setActiveSpan(span);
    const media = mediaRef.current;
    if (media) {
      const apply = () => {
        media.currentTime = span.start_s;
      };
      if (media.readyState >= 1) {
        apply();
      } else {
        media.addEventListener("loadedmetadata", apply, { once: true });
        media.load();
      }
    }
  };

  const dismiss = async (criterionId: string) => {
    await fetch("/api/insights/rubric/dismiss", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ criterion_id: criterionId, actor: "reviewer:ui" }),
    });
  };

  return (
    <section data-qid="insights-panel" className="mt-3 grid gap-3 rounded-lg border border-slate-700 bg-slate-900/70 p-3 text-sm">
      {review && (
        <div data-qid="review-dossier">
          <h3 className="mb-1 font-semibold text-slate-100">Review dossier</h3>
          <audio data-qid="review-media" ref={mediaRef} src="/api/insights/media" controls className="mb-2 h-8 w-full" />
          <ul className="grid gap-1">
            {review.review_claims.map((claim) => (
              <li key={claim.claim_id}>
                <button
                  type="button"
                  data-qid={`insight-claim-${claim.claim_id}`}
                  data-qs-action="LIVE_EVIDENCE_REVIEW_CLAIM_SEEK"
                  data-disposition={claim.disposition}
                  title={`Seek media to the supporting clip (${claim.disposition})`}
                  onClick={() => seekClaim(claim)}
                  className={`w-full rounded border px-2 py-1 text-left ${DISPOSITION_STYLE[claim.disposition] ?? "border-slate-600"}`}
                >
                  <span className="mr-2 rounded bg-black/30 px-1 text-[10px] uppercase tracking-wide">
                    {claim.disposition.replaceAll("_", " ")}
                  </span>
                  {claim.text}
                </button>
              </li>
            ))}
          </ul>
          {activeSpan && (
            <p data-qid="active-span" className="mt-1 text-xs text-slate-300">
              Clip {activeSpan.start_s.toFixed(1)}s–{activeSpan.end_s.toFixed(1)}s · events {activeSpan.event_ids.join(", ")}
            </p>
          )}
        </div>
      )}
      {rubric && (
        <div data-qid="rubric-coverage">
          <h3 className="mb-1 font-semibold text-slate-100">Rubric coverage</h3>
          <div className="flex flex-wrap gap-1">
            {rubric.coverage.map((entry) => (
              <span
                key={entry.criterion_id}
                data-qid={`coverage-${entry.criterion_id}`}
                data-coverage-state={entry.state}
                className={`rounded px-2 py-0.5 text-xs ${COVERAGE_STYLE[entry.state] ?? "bg-slate-700"}`}
              >
                {entry.criterion_id}: {entry.state.replaceAll("_", " ")}
              </span>
            ))}
          </div>
          {rubric.suggestions.map((suggestion) => (
            <div key={suggestion.criterion_id} data-qid={`suggestion-${suggestion.criterion_id}`} className="mt-2 rounded border border-sky-700 bg-sky-950/60 p-2">
              <p className="text-slate-100">Suggested next question: {suggestion.question_text}</p>
              <p className="text-xs text-slate-400">{suggestion.why_this_is_still_open}</p>
              <button
                type="button"
                data-qs-action="LIVE_EVIDENCE_RUBRIC_SUGGESTION_DISMISS"
                data-qid={`dismiss-${suggestion.criterion_id}`}
                title="Dismiss this suggestion (journaled; does not mark the criterion covered)"
                onClick={() => void dismiss(suggestion.criterion_id)}
                className="mt-1 rounded bg-slate-700 px-2 py-0.5 text-xs hover:bg-slate-600"
              >
                Dismiss
              </button>
            </div>
          ))}
        </div>
      )}
      {rehearsal && (
        <div data-qid="rehearsal-state">
          <h3 className="mb-1 font-semibold text-slate-100">Rehearsal turns (practice only)</h3>
          <ul className="grid gap-1 text-xs">
            {rehearsal.turns.map((turn) => (
              <li key={turn.turn_id} data-qid={`turn-${turn.turn_id}`} data-audio-status={turn.audio_status} className="rounded border border-slate-700 px-2 py-1">
                rev {turn.question_revision} · {turn.audio_status} · {turn.question_text}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
