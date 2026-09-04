import { useState } from "react";
import { useRegisterAction } from "@/hooks/useRegisterAction";
import type { PendingRequirement } from "@/types";

export function PendingClarification({ requirement }: { requirement: PendingRequirement }) {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useRegisterAction({ element_id: "clarification-answer", app: "live-evidence", action: "EDIT_CLARIFICATION", label: "Clarification answer", description: "Supply missing question context." });
  useRegisterAction({ element_id: "clarification-submit", app: "live-evidence", action: "SUBMIT_CLARIFICATION", label: "Submit clarification", description: "Bind the answer to this question revision." });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!answer.trim()) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/questions/${encodeURIComponent(requirement.question_id)}/clarifications/${encodeURIComponent(requirement.clarification_id ?? "")}/answer`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question_revision: requirement.question_revision, answer: answer.trim() }),
      });
      if (!response.ok) throw new Error(await response.text());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Clarification could not be submitted");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="m-6 shrink-0 rounded-lg border border-amber-600/50 bg-amber-950/20 p-4">
      <p className="mb-2 text-xs font-semibold uppercase text-amber-300">Input needed · answer held</p>
      <label htmlFor="clarification-answer" className="block text-sm text-slate-100">{requirement.text}</label>
      <textarea id="clarification-answer" data-qid="clarification-answer" data-qs-action="EDIT_CLARIFICATION" title="Provide missing input and expected output" value={answer} onChange={(event) => setAnswer(event.target.value)} maxLength={1000} rows={3} required disabled={busy} className="my-3 block w-full rounded border border-slate-600 bg-slate-950 p-2 text-sm text-white" />
      <button type="submit" data-qid="clarification-submit" data-qs-action="SUBMIT_CLARIFICATION" title="Submit clarification for this question" disabled={busy || !answer.trim()} className="rounded border border-amber-600 px-3 py-1.5 text-sm text-amber-100 disabled:opacity-50">{busy ? "Submitting…" : "Provide context"}</button>
      {error ? <p role="alert" className="mt-2 text-sm text-red-300">{error}</p> : null}
    </form>
  );
}
