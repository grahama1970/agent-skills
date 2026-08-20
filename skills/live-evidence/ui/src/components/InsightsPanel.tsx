import { useEffect, useRef, useState } from "react";

import { useRegisterAction } from "@/hooks/useRegisterAction";

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

type ProvenanceSource = {
  source_id: string;
  label: string;
  lane: string;
  path: string | null;
  line_start: number | null;
  line_end: number | null;
  excerpt: string;
  verification: { state: string; ok: boolean; anchor_line?: string | null } | null;
};
type ProvenanceClause = { clause: string; source_ids: string[]; sourced: boolean; invalidated: boolean };
type ProvenanceCard = { card_id: string; clauses: ProvenanceClause[]; sources: ProvenanceSource[] };

type ActionCandidate = {
  action_id: string;
  kind: string;
  summary: string;
  status: string;
  trigger_event_ids: string[];
};

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
  const [provenance, setProvenance] = useState<ProvenanceCard[]>([]);
  const [pendingActions, setPendingActions] = useState<ActionCandidate[]>([]);
  const [openSource, setOpenSource] = useState<ProvenanceSource | null>(null);

  useRegisterAction({
    element_id: "live-evidence:insights:claim-seek",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_REVIEW_CLAIM_SEEK",
    label: "Seek media to a review claim's clip",
    description: "Seek the retained interview media to the transcript span bound to this claim",
  });
  useRegisterAction({
    element_id: "live-evidence:insights:action-approve",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_ACTION_APPROVE",
    label: "Approve a suggested action",
    description: "Execute one evidence-triggered action after explicit human approval",
  });
  useRegisterAction({
    element_id: "live-evidence:insights:provenance-open-source",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_PROVENANCE_OPEN_SOURCE",
    label: "Open a clause's cited source",
    description: "Show the exact cited file, line range, and verification state for a clause",
  });
  useRegisterAction({
    element_id: "live-evidence:insights:suggestion-dismiss",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_RUBRIC_SUGGESTION_DISMISS",
    label: "Dismiss a rubric follow-up suggestion",
    description: "Journaled, attributable dismissal; never marks the criterion covered",
  });
  const [activeSpan, setActiveSpan] = useState<Span | null>(null);
  const mediaRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const response = await fetch("/api/insights");
        if (response.ok && alive) setInsights(await response.json());
        const provenanceResponse = await fetch("/api/provenance");
        if (provenanceResponse.ok && alive) {
          setProvenance((await provenanceResponse.json()).cards ?? []);
        }
        const actionsResponse = await fetch("/api/actions/pending");
        if (actionsResponse.ok && alive) {
          setPendingActions((await actionsResponse.json()).pending ?? []);
        }
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
  const provenanceCard =
    provenance.find((card) => card.clauses.some((clause) => clause.sourced)) ??
    provenance.find((card) => card.clauses.length > 0) ??
    null;
  if (!review && !rubric && !rehearsal && !provenanceCard && pendingActions.length === 0) return null;

  const approveAction = async (actionId: string) => {
    await fetch(`/api/actions/${actionId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor: "human:hud" }),
    });
  };

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
      {pendingActions.length > 0 && (
        <div data-qid="actions-panel">
          <h3 className="mb-1 font-semibold text-slate-100">Suggested actions (human-approved only)</h3>
          <ul className="grid gap-1 text-xs">
            {pendingActions.map((action) => (
              <li key={action.action_id} data-qid={`action-${action.action_id}`} data-action-kind={action.kind} className="flex items-center gap-2 rounded border border-indigo-700 bg-indigo-950/50 px-2 py-1">
                <span className="rounded bg-black/30 px-1 text-[10px] uppercase">{action.kind.replaceAll("_", " ")}</span>
                <span className="flex-1 text-slate-100">{action.summary}</span>
                <button
                  type="button"
                  data-qid={`approve-${action.action_id}`}
                  data-qs-action="LIVE_EVIDENCE_ACTION_APPROVE"
                  title="Approve and execute this action (journaled, revision-fenced, policy-gated)"
                  onClick={() => void approveAction(action.action_id)}
                  className="rounded bg-indigo-700 px-2 py-0.5 text-indigo-100 hover:bg-indigo-600"
                >
                  Approve
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {provenanceCard && (
        <div data-qid="provenance-panel">
          <h3 className="mb-1 font-semibold text-slate-100">Answer provenance</h3>
          <ul className="grid gap-1 text-xs">
            {provenanceCard.clauses.map((clause, index) => (
              <li
                key={index}
                data-qid={`clause-${index}`}
                data-sourced={String(clause.sourced)}
                data-invalidated={String(clause.invalidated)}
                className={`rounded border px-2 py-1 ${
                  clause.invalidated
                    ? "border-rose-500 bg-rose-950/60 text-rose-100 line-through"
                    : clause.sourced
                      ? "border-emerald-700 bg-emerald-950/40 text-slate-100"
                      : "border-slate-600 bg-slate-800/60 text-slate-400"
                }`}
              >
                <span className="mr-1 rounded bg-black/30 px-1 text-[10px] uppercase">
                  {clause.invalidated ? "invalidated" : clause.sourced ? "sourced" : "unsourced"}
                </span>
                {clause.clause}
                <span className="ml-1">
                  {clause.source_ids.map((sourceId) => {
                    const source = provenanceCard.sources.find((item) => item.source_id === sourceId);
                    if (!source) return null;
                    return (
                      <button
                        key={sourceId}
                        type="button"
                        data-qid={`clause-source-${index}-${sourceId}`}
                        data-qs-action="LIVE_EVIDENCE_PROVENANCE_OPEN_SOURCE"
                        data-file-backed={String(Boolean(source.path))}
                        title={`Open ${source.label} at the exact cited range`}
                        onClick={() => setOpenSource(source)}
                        className="ml-1 rounded bg-sky-900 px-1 text-[10px] text-sky-100 hover:bg-sky-800"
                      >
                        {source.label.split("/").pop()}
                        {source.line_start ? `:${source.line_start}` : ""}
                      </button>
                    );
                  })}
                </span>
              </li>
            ))}
          </ul>
          {openSource && (
            <div data-qid="source-deep-view" className="mt-2 rounded border border-sky-700 bg-slate-950 p-2 text-xs">
              <p className="text-sky-200">
                {openSource.path}
                {openSource.line_start ? `:${openSource.line_start}` : ""}
                {openSource.line_end && openSource.line_end !== openSource.line_start ? `-${openSource.line_end}` : ""}
                {" · "}
                <span data-qid="source-verification-state">
                  {openSource.verification?.state ?? "unknown"}
                </span>
              </p>
              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-slate-300">
                {openSource.verification?.anchor_line ?? openSource.excerpt}
              </pre>
            </div>
          )}
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
