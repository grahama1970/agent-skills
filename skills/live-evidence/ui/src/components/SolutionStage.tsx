import { Check, Clipboard, Code2, DatabaseZap, Pin, SearchCode, ShieldAlert, X } from "lucide-react";
import type { ReactNode } from "react";
import { CardDeckMatrix, ScannableCardStackWithAudio } from "./ScanCard";
import { useMemo, useState } from "react";

import { useHUDHotkeys } from "@/hooks/useHUDHotkeys";
import { useRegisterAction } from "@/hooks/useRegisterAction";
import { compactPath } from "@/lib/utils";
import type { EvidenceCard, EvidenceSource } from "@/types";

interface SolutionStageProps {
  card: EvidenceCard;
  busy: boolean;
  kind: string;
  voiceEnabled?: boolean;
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

/**
 * Only ever surface code the backend actually produced.
 *
 * This previously fell back to a hard-coded Python bracket validator whenever
 * a regex matched /parenthes|bracket|stack/ in the card text. That made the
 * HUD show an authoritative-looking implementation for questions the pipeline
 * had not answered at all, and it made every solution screenshot unfalsifiable
 * -- an agentic eval could assert the solution pane rendered while the backend
 * had returned nothing.
 */
function solutionCode(card: EvidenceCard): { label: string; code: string; sourceBound: boolean } | null {
  const explicit = fencedCode(`${card.answer ?? ""}\n${card.talking_point}\n${card.proof}`);
  if (explicit) {
    return { label: "answer-snippet", code: explicit, sourceBound: card.status === "supported" };
  }
  // The summarizer reduces the card to one extracted sentence, so a fenced
  // block from the solver never survives into answer/talking_point/proof. The
  // full solver response is preserved on the ask-lane source excerpt, which is
  // the only place backend-produced code actually reaches the browser.
  const askSource = card.sources.find((source) => source.lane === "ask");
  const fromAsk = askSource ? fencedCode(askSource.excerpt) : null;
  if (!fromAsk) return null;
  return { label: askSource!.label || "ask-solution", code: fromAsk, sourceBound: card.status === "supported" };
}

/**
 * Show only what the backend said. This previously substituted a fixed
 * stack-algorithm sentence whenever the hard-coded candidate code was present,
 * so the HUD narrated an approach the pipeline never produced.
 */
function takeaway(card: EvidenceCard): string {
  const answer = card.answer || card.talking_point;
  if (answer && answer !== "No source-bound support surfaced yet.") return answer;
  return answer || "No formatted solution is available yet.";
}

/**
 * Reviewer directive (2026-08-27): the center pane must scan as a vertical
 * stack of 2-3 word headers with 2-line bullets, never prose. Parse the
 * answer's numbered/bolded structure; below two items, prose remains.
 */
function scannablePoints(text: string): { header: string; bullet: string }[] {
  const points: { header: string; bullet: string }[] = [];
  const pattern = /(?:^|\s)(\d+)\.\s+\*\*(.+?)\*\*\s*[—:-]?\s*/g;
  const indices: { idx: number; header: string; start: number }[] = [];
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    indices.push({ idx: Number(match[1]), header: match[2], start: pattern.lastIndex });
  }
  for (let i = 0; i < indices.length; i += 1) {
    const end = i + 1 < indices.length ? text.indexOf(`${indices[i + 1].idx}.`, indices[i].start) : text.length;
    const bullet = text
      .slice(indices[i].start, end > 0 ? end : undefined)
      .replace(/\*\*/g, "")
      .trim();
    const trigger = bullet.split(/[.;\u2014]/)[0].split(/\s+/).slice(0, 9).join(" ");
    points.push({ header: `${indices[i].idx}. ${indices[i].header.replace(/\*\*/g, "")}`, bullet: trigger });
  }
  return points;
}

function solutionDeckCards(card: EvidenceCard, answer: string): { title: string; body: string }[] {
  const typed = (card.solution_deck ?? [])
    .map((point) => ({ title: point.title.trim(), body: point.trigger.trim() }))
    .filter((point) => point.title && point.body)
    .slice(0, 4);
  if (typed.length >= 2) return typed;
  return scannablePoints(answer).map((point) => ({ title: point.header, body: point.bullet }));
}

function coreLogicSnippet(text: string): string {
  const lines = text.split("\n");
  const loopStart = lines.findIndex((line) => line.trim().startsWith("for "));
  if (loopStart >= 0) return lines.slice(loopStart).join("\n");
  return lines.slice(0, Math.min(lines.length, 8)).join("\n");
}

function TermBadge({
  className,
  label,
  definition,
}: {
  className: string;
  label: string;
  definition: string;
}) {
  return (
    <span className={`hud-term ${className}`} title={definition}>
      {label}
      <span className="hud-term-popover" role="tooltip">
        {definition}
      </span>
    </span>
  );
}

/**
 * Render the backend answer as-is.
 *
 * This previously replaced the answer with a fixed annotated sentence about
 * stacks and O(N) complexity whenever the card text matched a parentheses
 * regex, so the HUD presented term-badged analysis that no model had produced.
 * Any future term annotation must be driven by resolver output, not by
 * pattern-matching the question text in the browser.
 */
function semanticTakeaway(answer: string): ReactNode {
  return answer;
}

/**
 * Split a staged solver answer into interview-order sections.
 *
 * The Ask prompt requests APPROACH -> PSEUDOCODE -> CODE -> COMPLEXITY ->
 * OPTIMIZATIONS because that is the order a candidate actually speaks: name the
 * data structure, narrate the steps, then write real code, then discuss
 * trade-offs. Rendering the final implementation first leaves nothing to say
 * while typing.
 *
 * Returns null when the answer is unstaged, so older cards and non-code lanes
 * fall through to the existing single-block rendering rather than showing empty
 * headings.
 */
export interface SolutionSections {
  approach?: string;
  pseudocode?: string;
  complexity?: string;
  optimizations: string[];
}

function parseSolutionSections(text: string): SolutionSections | null {
  // Accept ## or ### and stop at the next heading of EITHER depth. The solver
  // mixes them -- observed emitting "## APPROACH" then "### PSEUDOCODE" in one
  // answer -- and a lookahead pinned to "##" swallowed every later section into
  // the first block. Headings may also be inline rather than line-anchored.
  if (!text || !/#{2,3}\s*(APPROACH|PSEUDOCODE|OPTIMIZATIONS)/i.test(text)) return null;
  const grab = (name: string): string | undefined => {
    const match = text.match(
      new RegExp(`#{2,3}\\s*${name}\\b:?\\s*([\\s\\S]*?)(?=#{2,3}\\s*[A-Z]{3,}|$)`, "i"),
    );
    return match?.[1]?.trim() || undefined;
  };
  const stripFence = (value?: string): string | undefined => {
    if (!value) return undefined;
    const fenced = value.match(/```(?:[a-zA-Z0-9_-]+)?\s*\n?([\s\S]*?)```/);
    return (fenced?.[1] ?? value).trim() || undefined;
  };
  const optimizationsRaw = grab("OPTIMIZATIONS") ?? "";
  const optimizations = optimizationsRaw
    .split("\n")
    .map((line) => line.replace(/^\s*[-*\d.)]+\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 4);
  const sections: SolutionSections = {
    approach: grab("APPROACH"),
    pseudocode: stripFence(grab("PSEUDOCODE")),
    complexity: grab("COMPLEXITY"),
    optimizations,
  };
  const hasAny =
    sections.approach || sections.pseudocode || sections.complexity || optimizations.length > 0;
  return hasAny ? sections : null;
}

function askAnswerText(card: EvidenceCard): string {
  // The summarizer reduces the card to one extracted sentence, so staged
  // sections survive only on the ask-lane source excerpt.
  const askSource = card.sources.find((source) => source.lane === "ask");
  return askSource?.excerpt ?? "";
}

export function SolutionStage({ card, busy, kind, onPin, onDismiss, voiceEnabled = false }: SolutionStageProps) {
  const [copiedInsight, setCopiedInsight] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);
  const [expandedCode, setExpandedCode] = useState(false);
  const primarySource = card.sources[0];
  const code = useMemo(() => solutionCode(card), [card]);
  const sections = useMemo(() => parseSolutionSections(askAnswerText(card)), [card]);
  const answer = takeaway(card);
  const displayedCode = code ? (expandedCode ? code.code : coreLogicSnippet(code.code)) : null;
  const deckCards = useMemo(() => solutionDeckCards(card, answer), [card, answer]);
  const copyQid = `live-evidence:solution:copy:${card.card_id}`;
  const copyCodeQid = `live-evidence:solution:copy-code:${card.card_id}`;
  const foldCodeQid = `live-evidence:solution:toggle-code-fold:${card.card_id}`;
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
    element_id: foldCodeQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SOLUTION_TOGGLE_CODE_FOLD",
    label: "Toggle code glance mode",
    description: "Switch the selected solution code between glance mode and full implementation",
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

  useHUDHotkeys([{ key: "Shift+E", handler: () => code && setExpandedCode((value) => !value) }]);

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

      {deckCards.length >= 2 ? (
        <div data-aoi="AOI_SOLUTION">
          {voiceEnabled ? (
            <ScannableCardStackWithAudio cards={deckCards} />
          ) : (
            <CardDeckMatrix cards={deckCards} />
          )}
        </div>
      ) : (
        <div className="takeaway-box" data-aoi="AOI_SOLUTION">{semanticTakeaway(answer)}</div>
      )}
      {sections ? (
        <div className="solution-stages" data-aoi="AOI_SOLUTION_STAGES">
          {sections.approach ? (
            <section className="solution-stage-block" data-stage="approach">
              <p className="solution-stage-label">Approach · say this first</p>
              <p className="solution-stage-body">{sections.approach}</p>
            </section>
          ) : null}
          {sections.pseudocode ? (
            <section className="solution-stage-block" data-stage="pseudocode">
              <p className="solution-stage-label">Pseudocode · narrate while you type</p>
              <pre className="solution-stage-pre">{sections.pseudocode}</pre>
            </section>
          ) : null}
          {sections.complexity ? (
            <section className="solution-stage-block" data-stage="complexity">
              <p className="solution-stage-label">Complexity</p>
              <p className="solution-stage-body">{sections.complexity}</p>
            </section>
          ) : null}
          {sections.optimizations.length > 0 ? (
            <section className="solution-stage-block" data-stage="optimizations">
              <p className="solution-stage-label">Likely follow-ups · be ready</p>
              <ul className="solution-stage-list">
                {sections.optimizations.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      ) : null}

      <div className="code-block-container">
        <div className="code-bar">
          <div className="code-bar-label">
            <span>{code?.label ?? "solution-code unavailable"}</span>
            <span>{expandedCode ? "Full Class" : "Glance Mode"}</span>
          </div>
          <div className="code-bar-actions">
            <button data-qid={foldCodeQid} data-qs-action="LIVE_EVIDENCE_SOLUTION_TOGGLE_CODE_FOLD" title="Toggle code glance mode" type="button" disabled={!code} onClick={() => setExpandedCode((value) => !value)}>
              {expandedCode ? "Fold" : "Expand"}
            </button>
            <button data-qid={copyCodeQid} data-qs-action="LIVE_EVIDENCE_SOLUTION_COPY_CODE" title="Copy solution code" type="button" disabled={!code} onClick={() => void copyCode()}>
              {copiedCode ? "Copied" : "Copy Code"}
            </button>
          </div>
        </div>
        {displayedCode ? <pre><code>{displayedCode}</code></pre> : <div className="code-empty">No source-bound code block is available yet.</div>}
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
