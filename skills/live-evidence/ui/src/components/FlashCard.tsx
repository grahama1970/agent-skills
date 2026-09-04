import {
  AlertTriangle,
  CheckCircle,
  Code2,
  Copy,
  CornerDownRight,
  Database,
  Layers,
  Pin,
  Radio,
  RotateCw,
  Sparkles,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { CodeBlock } from "@/components/CodeBlock";
import { flashCardStatus } from "@/components/QuestionTimeline";
import { useRegisterAction } from "@/hooks/useRegisterAction";
import type { EvidenceCard, EvidenceSource, RetrievalLane } from "@/types";

interface FlashCardProps {
  card: EvidenceCard | null;
  followUps?: EvidenceCard[];
  isFlipped: boolean;
  onFlipToggle: () => void;
  onTogglePin: (cardId: string) => void;
}

interface GlancePoint {
  title: string;
  trigger: string;
}

/**
 * The front face never shows prose. When the solver deck is missing, glance
 * points are DERIVED FROM THE ANSWER ITSELF: headings become titles with their
 * first bullet as trigger; otherwise the first bullets become the points.
 * talking_point (source-excerpt summary text) is banned from the front face -
 * it is not this question's answer (operator, 2026-08-31).
 */
function deriveGlance(answerText: string): GlancePoint[] {
  if (!answerText.trim()) return [];
  const lines = answerText.split("\n");
  const points: GlancePoint[] = [];
  let currentHeading: string | null = null;
  let inCode = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith("```")) { inCode = !inCode; continue; }
    if (inCode) continue;
    if (line.startsWith("## ")) {
      currentHeading = line.replace("## ", "").trim();
      continue;
    }
    if (line.startsWith("- ") || line.startsWith("* ")) {
      const bullet = line.replace(/^[-*]\s+/, "").trim();
      if (!bullet) continue;
      if (currentHeading) {
        points.push({ title: currentHeading, trigger: bullet.slice(0, 90) });
        currentHeading = null;
      } else {
        const words = bullet.split(/\s+/);
        points.push({
          title: words.slice(0, 4).join(" "),
          trigger: bullet.slice(0, 90),
        });
      }
      if (points.length >= 4) break;
    }
  }
  return points;
}

function LaneIcon({ lane }: { lane: RetrievalLane }) {
  if (lane === "code" || lane === "ripgrep") return <Code2 className="size-3.5 text-emerald-400" aria-hidden="true" />;
  if (lane === "memory") return <Database className="size-3.5 text-purple-400" aria-hidden="true" />;
  return <Layers className="size-3.5 text-blue-400" aria-hidden="true" />;
}

function uniqueLanes(sources: EvidenceSource[]): RetrievalLane[] {
  return [...new Set(sources.map((source) => source.lane))];
}

export function FlashCard({ card, followUps = [], isFlipped, onFlipToggle, onTogglePin }: FlashCardProps) {
  const [copied, setCopied] = useState(false);
  const backRef = useRef<HTMLDivElement>(null);
  useRegisterAction({ element_id: "flashcard-controls", app: "live-evidence", action: "operate_flashcard", label: "Operate flashcard", description: "Flip, copy, or pin the active evidence card." });
  const [userScrolledBack, setUserScrolledBack] = useState(false);

  useEffect(() => {
    setCopied(false);
    setUserScrolledBack(false);
  }, [card?.card_id]);

  const status = card ? flashCardStatus(card) : "thinking";
  const isStreaming = status !== "ready";

  const handleBackScroll = () => {
    if (!backRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = backRef.current;
    setUserScrolledBack(scrollHeight - scrollTop - clientHeight >= 30);
  };

  useEffect(() => {
    if (isFlipped && isStreaming && backRef.current && !userScrolledBack) {
      backRef.current.scrollTo({ top: backRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [card?.answer, card?.amendment_text, isFlipped, isStreaming, userScrolledBack]);

  if (!card) {
    return (
      <div className="flex flex-1 select-none flex-col items-center justify-center bg-[#090a0f] p-8 text-slate-500">
        <Sparkles className="mb-3 size-12 animate-pulse text-indigo-500/30" aria-hidden="true" />
        <h3 className="text-xl font-semibold text-slate-300">Awaiting Live Evidence</h3>
        <p className="mt-1 text-sm text-slate-500">Spoken questions will render live flashcards here.</p>
      </div>
    );
  }

  const solverDeck = card.solution_deck ?? [];
  const amendmentPromoted = Boolean(card.amendment_complete && card.amendment_text);
  const answerText = amendmentPromoted ? (card.amendment_text ?? "") : (card.answer ?? "");
  const deckPoints = solverDeck.length > 0 ? solverDeck : deriveGlance(answerText);
  const originalAnswer = card.answer ?? "";
  const question = card.question ?? card.query;

  const handleCopy = () => {
    if (!answerText) return;
    void navigator.clipboard.writeText(answerText);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex h-full flex-1 select-none flex-col overflow-hidden bg-[#090a0f] p-6">
      {/* Ultra-compact single-row action bar (~32px): Copy left, badges + Pin right */}
      <div className="z-10 mb-2 flex h-8 shrink-0 items-center justify-between rounded-t-lg border-b border-slate-800 bg-slate-900/60 px-3 py-1.5">
        {answerText ? (
          <button
            type="button"
            data-qid="flashcard-copy-answer"
            data-qs-action="copy_answer"
            title="Copy answer"
            onClick={handleCopy}
            className="flex h-6 cursor-pointer items-center gap-1.5 rounded border border-slate-700/80 bg-slate-800 px-2 py-1 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-700"
          >
            {copied ? (
              <CheckCircle className="size-3.5 text-emerald-400" aria-hidden="true" />
            ) : (
              <Copy className="size-3.5" aria-hidden="true" />
            )}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>
        ) : <span />}

        <div className="flex items-center gap-2">
          {card.review_verdict === "weak" && !amendmentPromoted ? (
            <span
              className="inline-flex items-center gap-1 rounded-md border border-amber-800/60 bg-amber-950/50 px-2 py-0.5 text-xs font-medium text-amber-400"
              title={(card.review_reasons ?? []).join("; ") || "Reviewer marked this answer weak"}
            >
              <AlertTriangle className="size-3" aria-hidden="true" />
              review: weak{card.amendment_text ? " · amending…" : ""}
            </span>
          ) : null}
          {amendmentPromoted ? (
            <span className="inline-flex items-center gap-1 rounded-md border border-emerald-800/60 bg-emerald-950/50 px-2 py-0.5 text-xs font-medium text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              revised
            </span>
          ) : null}
          <button
            type="button"
            data-qid="flashcard-pin"
            data-qs-action="toggle_pin"
            onClick={() => onTogglePin(card.card_id)}
            className={`cursor-pointer rounded border p-1 transition-colors ${
              card.pinned
                ? "border-amber-500/60 bg-amber-500/20 text-amber-300"
                : "border-slate-700/60 bg-slate-800/60 text-slate-400 hover:bg-slate-800 hover:text-amber-400"
            }`}
            title="Pin card [P]"
          >
            <Pin className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Unified card: question + key points + full solution, no flip */}
      <div className="relative h-full w-full flex-1">
        <div className="flex h-full flex-col overflow-hidden rounded-2xl border-2 border-slate-800/80 bg-[#0e101a] p-4 shadow-2xl">
          {/* Top strip: compact question anchor */}
          <div className="mb-3 flex shrink-0 items-center justify-between gap-3 rounded-r-lg border-l-4 border-emerald-500 bg-slate-800/60 p-3">
            <div className="min-w-0">
              <span className="mb-0.5 block text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                Question
              </span>
              <h2 className="break-words text-sm font-semibold leading-tight text-slate-100">{question}</h2>
            </div>
            {(() => {
              const cx = extractComplexity(answerText);
              return cx.time || cx.space ? (
                <div className="flex shrink-0 gap-2 font-mono text-xs">
                  {cx.time ? (
                    <div className="flex items-center gap-1.5 rounded border border-slate-700 bg-slate-800 px-2.5 py-1">
                      <span className="text-[10px] text-slate-400">TIME:</span>
                      <span className="font-bold text-emerald-400">{cx.time}</span>
                    </div>
                  ) : null}
                  {cx.space ? (
                    <div className="flex items-center gap-1.5 rounded border border-slate-700 bg-slate-800 px-2.5 py-1">
                      <span className="text-[10px] text-slate-400">SPACE:</span>
                      <span className="font-bold text-emerald-400">{cx.space}</span>
                    </div>
                  ) : null}
                </div>
              ) : null;
            })()}
          </div>

          {/* Zero-scroll split view: logic left, code/answer right */}
          <div className="grid min-h-0 flex-1 grid-cols-12 gap-3">
            <div className="col-span-5 flex min-h-0 flex-col overflow-y-auto rounded-lg border border-slate-800 bg-slate-800/30 p-3">
              <span className="mb-2 block shrink-0 text-[10px] font-bold uppercase tracking-wider text-slate-400">Algorithm at a Glance</span>
              {deckPoints.length > 0 ? (
                <div className="space-y-2">
                  {deckPoints.map((point, index) => (
                    <div key={point.title} className="flex items-start gap-2 rounded border border-slate-800/80 bg-slate-900/60 p-2">
                      <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 font-mono text-[10px] font-bold text-emerald-400">{index + 1}</span>
                      <p className="text-xs leading-snug text-slate-300">
                        <strong className="text-slate-100">{point.title}:</strong> {point.trigger}
                      </p>
                    </div>
                  ))}
                </div>
              ) : isStreaming ? (
                <div className="animate-stream-glow rounded-xl border-2 border-indigo-500/60 bg-[#121526] p-3 text-xs text-indigo-200">
                  <span className="flex items-center gap-2 font-bold text-indigo-400">
                    <Radio className="size-4 animate-pulse" aria-hidden="true" /> Solver streaming…
                  </span>
                </div>
              ) : null}
              {followUps.length > 0 ? (
                <div className="mt-2 flex shrink-0 items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-indigo-400">
                  <CornerDownRight className="size-3.5" aria-hidden="true" />
                  {followUps.length} follow-up{followUps.length > 1 ? "s" : ""} at right
                </div>
              ) : null}
            </div>

            <div
              ref={backRef}
              onScroll={handleBackScroll}
              className="col-span-7 min-h-0 scroll-smooth space-y-3 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950 p-3 font-sans text-sm leading-relaxed text-slate-100"
            >
              {answerText ? (
                <FormattedAnswer
                  text={answerText}
                  skipHeadings={[
                    ...(deckPoints.length > 0 ? ["approach", "algorithm"] : []),
                    ...(extractComplexity(answerText).time ? ["complexity"] : []),
                  ]}
                />
              ) : (
                <div className="animate-stream-glow rounded-xl border-2 border-indigo-500/60 bg-[#121526] p-6 font-mono text-base leading-relaxed text-slate-100">
                  Awaiting full solution streaming…
                  <span className="animate-typing-cursor ml-1 inline-block h-5 w-2.5 bg-indigo-400 align-middle" />
                </div>
              )}

              {amendmentPromoted && originalAnswer ? (
                <details className="rounded-xl border border-slate-800/80 bg-[#0b0c13] p-4">
                  <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Original answer (superseded by review)
                  </summary>
                  <div className="mt-2 opacity-70">
                    <FormattedAnswer text={originalAnswer} />
                  </div>
                </details>
              ) : null}

              {card.amendment_text && !card.amendment_complete ? (
                <div className="animate-stream-border rounded-xl border-2 border-indigo-500/50 bg-[#0f111d] p-4">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-indigo-400">
                    Revised answer streaming…
                  </div>
                  <FormattedAnswer text={card.amendment_text} />
                  <span className="animate-typing-cursor ml-1 inline-block h-5 w-2.5 bg-indigo-400 align-middle" />
                </div>
              ) : null}

              {followUps.length > 0 ? (
                <div className="space-y-3 border-t border-slate-800/80 pt-4">
                  {followUps.map((followUp) => (
                    <div key={followUp.card_id} className="rounded-xl border border-indigo-900/40 bg-[#0c0e18] p-4">
                      <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-indigo-400">
                        <CornerDownRight className="size-3.5" aria-hidden="true" />
                        Follow-up
                      </div>
                      <p className="mb-2 text-base font-semibold text-white">{followUp.question ?? followUp.query}</p>
                      {followUp.answer ? (
                        <FormattedAnswer text={followUp.answer} />
                      ) : (
                        <p className="text-sm italic text-slate-500">Answer streaming…</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="mt-4 flex shrink-0 items-center justify-end gap-2 border-t border-slate-800/80 pt-3">
                {uniqueLanes(card.sources).map((lane) => (
                  <span
                    key={lane}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1 font-mono text-xs font-medium text-slate-200"
                  >
                    <LaneIcon lane={lane} />
                    {lane}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Extract Time/Space complexity for the top-strip pills. */
function extractComplexity(text: string): { time?: string; space?: string } {
  const time = /time[^O\n]*\b(O\([^)]+\))/i.exec(text)?.[1];
  const space = /space[^O\n]*\b(O\([^)]+\))/i.exec(text)?.[1];
  return { time, space };
}

function FormattedAnswer({ text, skipHeadings = [] }: { text: string; skipHeadings?: string[] }) {
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeBuffer: string[] = [];
  let detectedLang = "python";
  let skippingSection = false;
  const shouldSkip = (heading: string) =>
    skipHeadings.some((s) => heading.toLowerCase().includes(s.toLowerCase()));

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (line.startsWith("## ")) skippingSection = shouldSkip(line.replace("## ", ""));
    if (skippingSection && !trimmed.startsWith("```") && !inCodeBlock) return;
    if (skippingSection && trimmed.startsWith("```")) skippingSection = false; // never skip code
    if (trimmed.startsWith("```")) {
      if (inCodeBlock) {
        elements.push(<CodeBlock key={`code-${index}`} code={codeBuffer.join("\n")} language={detectedLang} />);
        codeBuffer = [];
        inCodeBlock = false;
      } else {
        detectedLang = trimmed.replace("```", "").trim() || "python";
        inCodeBlock = true;
      }
      return;
    }
    if (inCodeBlock) {
      codeBuffer.push(line);
      return;
    }
    if (line.startsWith("## ")) {
      elements.push(
        <h3
          key={index}
          className="mb-2 mt-6 border-b border-slate-800/80 pb-1.5 text-base font-extrabold uppercase tracking-wider text-indigo-300"
        >
          {line.replace("## ", "")}
        </h3>,
      );
    } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      elements.push(
        <div
          key={index}
          className="my-2 flex items-start gap-3 rounded-xl border border-slate-800/80 bg-[#10121e] p-3.5 text-base font-medium text-slate-100 shadow-sm"
        >
          <span className="mt-0.5 text-lg font-bold leading-none text-indigo-400">•</span>
          <span className="leading-snug">{line.replace(/^\s*[-*]\s+/, "")}</span>
        </div>,
      );
    } else if (trimmed.length > 0) {
      elements.push(
        <p key={index} className="my-2 text-base font-normal leading-relaxed text-slate-200">
          {line}
        </p>,
      );
    }
  });

  return <div className="space-y-1">{elements}</div>;
}
