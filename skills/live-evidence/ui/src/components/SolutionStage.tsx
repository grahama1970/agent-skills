import { Check, Clipboard, Code2, DatabaseZap, Pin, SearchCode, ShieldAlert, X } from "lucide-react";
import { useMemo, useState } from "react";

import { useRegisterAction } from "@/hooks/useRegisterAction";
import { compactPath } from "@/lib/utils";
import type { EvidenceCard, EvidenceSource } from "@/types";

interface SolutionStageProps {
  card: EvidenceCard;
  busy: boolean;
  kind: string;
  onPin: (cardId: string) => void;
  onDismiss: (cardId: string) => void;
}

function sourceLabel(source?: EvidenceSource): string {
  if (!source) return "Source pending";
  const locator = source.path ?? source.url ?? source.label;
  const suffix = source.line_start ? `:${source.line_start}` : "";
  return `${source.repository ?? source.lane} / ${compactPath(locator)}${suffix}`;
}

function fencedCode(text: string): string | null {
  const match = text.match(/```(?:[a-zA-Z0-9_-]+)?\n([\s\S]*?)```/);
  return match?.[1]?.trim() || null;
}

function isParenthesesQuestion(card: EvidenceCard): boolean {
  return `${card.question ?? ""} ${card.query} ${card.answer ?? ""}`.toLowerCase().match(/parenthes|bracket|stack|\(\)/) !== null;
}

function solutionCode(card: EvidenceCard): { label: string; code: string; sourceBound: boolean } | null {
  const explicit = fencedCode(`${card.answer ?? ""}\n${card.talking_point}\n${card.proof}`);
  if (explicit) {
    return { label: "answer-snippet", code: explicit, sourceBound: card.status === "supported" };
  }
  if (!isParenthesesQuestion(card)) return null;
  return {
    label: "candidate_valid_parentheses.py",
    sourceBound: false,
    code: `class Solution:
    def isValid(self, s: str) -> bool:
        stack: list[str] = []
        pairs = {")": "(", "]": "[", "}": "{"}

        for char in s:
            if char in pairs.values():
                stack.append(char)
            elif char in pairs:
                if not stack or stack.pop() != pairs[char]:
                    return False

        return not stack`,
  };
}

function takeaway(card: EvidenceCard, hasCandidateCode: boolean): string {
  const answer = card.answer || card.talking_point;
  if (answer && answer !== "No source-bound support surfaced yet.") return answer;
  if (hasCandidateCode) {
    return "Use a stack after confirming the contract: push opening brackets, pop on matching closes, reject mismatches immediately, and reject leftover openings at the end.";
  }
  return answer || "No formatted solution is available yet.";
}

export function SolutionStage({ card, busy, kind, onPin, onDismiss }: SolutionStageProps) {
  const [copiedInsight, setCopiedInsight] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);
  const primarySource = card.sources[0];
  const code = useMemo(() => solutionCode(card), [card]);
  const answer = takeaway(card, Boolean(code));
  const copyQid = `live-evidence:solution:copy:${card.card_id}`;
  const copyCodeQid = `live-evidence:solution:copy-code:${card.card_id}`;
  const pinQid = `live-evidence:solution:pin:${card.card_id}`;
  const dismissQid = `live-evidence:solution:dismiss:${card.card_id}`;
  const diagnosticsQid = `live-evidence:solution:diagnostics:${card.card_id}`;

  useRegisterAction({
    element_id: copyQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SOLUTION_COPY",
    label: "Copy formatted solution",
    description: "Copy the active formatted solution takeaway and diagnostics summary",
    params: { card_id: card.card_id },
  });
  useRegisterAction({
    element_id: copyCodeQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SOLUTION_COPY_CODE",
    label: "Copy solution code",
    description: "Copy the active solution code block when one is available",
    params: { card_id: card.card_id },
  });
  useRegisterAction({
    element_id: pinQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SOLUTION_PIN",
    label: "Pin active solution",
    description: "Pin or release the selected live evidence solution card",
    params: { card_id: card.card_id },
  });
  useRegisterAction({
    element_id: dismissQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SOLUTION_DISMISS",
    label: "Dismiss active solution",
    description: "Dismiss the selected live evidence solution card",
    params: { card_id: card.card_id },
  });
  useRegisterAction({
    element_id: diagnosticsQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SOLUTION_DIAGNOSTICS_TOGGLE",
    label: "Toggle solution diagnostics",
    description: "Show or hide the source confidence and retrieval diagnostics for the selected solution card",
    params: { card_id: card.card_id },
  });

  const copyInsight = async () => {
    await navigator.clipboard.writeText(
      `Question: ${card.question || card.query}\n\nTakeaway: ${answer}\n\nDiagnostics: ${card.qualifier}\nEvidence: ${card.evidence || card.proof}\nSource: ${sourceLabel(primarySource)}`,
    );
    setCopiedInsight(true);
    window.setTimeout(() => setCopiedInsight(false), 1_500);
  };

  const copyCode = async () => {
    if (!code) return;
    await navigator.clipboard.writeText(code.code);
    setCopiedCode(true);
    window.setTimeout(() => setCopiedCode(false), 1_500);
  };

  return (
    <section className="solution-pane" data-type={kind} aria-label="Formatted answer and code">
      <div className="solution-header">
        <div>
          <span className="solution-title">Step 2: Formatted Answer & Code</span>
          <p>{code?.sourceBound ? "Source-bound implementation" : "Candidate implementation, verify after clarification"}</p>
        </div>
        <div className="stage-actions">
          <button data-qid={pinQid} data-qs-action="LIVE_EVIDENCE_SOLUTION_PIN" title={card.pinned ? "Unpin card" : "Pin card"} type="button" disabled={busy} onClick={() => onPin(card.card_id)} aria-label={card.pinned ? "Unpin card" : "Pin card"}>
            <Pin aria-hidden="true" className="size-3.5" />
          </button>
          <button data-qid={copyQid} data-qs-action="LIVE_EVIDENCE_SOLUTION_COPY" title="Copy formatted solution" type="button" onClick={() => void copyInsight()} aria-label="Copy formatted solution">
            {copiedInsight ? <Check aria-hidden="true" className="size-3.5 text-emerald-300" /> : <Clipboard aria-hidden="true" className="size-3.5" />}
          </button>
          <button data-qid={dismissQid} data-qs-action="LIVE_EVIDENCE_SOLUTION_DISMISS" title="Dismiss card" type="button" disabled={busy} onClick={() => onDismiss(card.card_id)} aria-label="Dismiss card">
            <X aria-hidden="true" className="size-3.5" />
          </button>
        </div>
      </div>

      <div className="takeaway-box">{answer}</div>

      <div className="code-block-container">
        <div className="code-bar">
          <span>{code?.label ?? "solution-code unavailable"}</span>
          <button data-qid={copyCodeQid} data-qs-action="LIVE_EVIDENCE_SOLUTION_COPY_CODE" title="Copy solution code" type="button" disabled={!code} onClick={() => void copyCode()}>
            {copiedCode ? "Copied" : "Copy Code"}
          </button>
        </div>
        {code ? <pre><code>{code.code}</code></pre> : <div className="code-empty">No source-bound code block is available yet.</div>}
      </div>

      <details className="diag-drawer">
        <summary
          data-qid={diagnosticsQid}
          data-qs-action="LIVE_EVIDENCE_SOLUTION_DIAGNOSTICS_TOGGLE"
          title="Toggle solution diagnostics"
        >
          System Diagnostics & Source Confidence ({Math.round(card.confidence * 100)}%)
        </summary>
        <div className="diag-content">
          <div className="diag-box">
            <h3><ShieldAlert aria-hidden="true" className="size-3.5" /> Use With Caution</h3>
            <p>{card.qualifier}</p>
          </div>
          <div className="diag-box">
            <h3><DatabaseZap aria-hidden="true" className="size-3.5" /> Evidence</h3>
            <p>{card.evidence || card.proof}</p>
          </div>
          <div className="diag-box diag-source">
            <h3><SearchCode aria-hidden="true" className="size-3.5" /> Source</h3>
            <code>{sourceLabel(primarySource)}</code>
            {primarySource?.excerpt ? <pre>{primarySource.excerpt}</pre> : null}
          </div>
          <div className="diag-box">
            <h3><Code2 aria-hidden="true" className="size-3.5" /> Confidence</h3>
            <p>{Math.round(card.confidence * 100)}% evidence confidence from {card.sources.length} source(s).</p>
          </div>
        </div>
      </details>
    </section>
  );
}
