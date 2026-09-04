import { CheckCircle2, ChevronDown, ChevronRight, Clock, Layers, Loader2, MessageSquare, Pin } from "lucide-react";
import { useMemo, useState } from "react";

import { useRegisterAction } from "@/hooks/useRegisterAction";
import type { EvidenceCard } from "@/types";

export type FlashCardStatus = "thinking" | "streaming" | "ready";

export function flashCardStatus(card: EvidenceCard): FlashCardStatus {
  if (card.answer && card.answer.trim()) return "ready";
  if (card.solution_deck && card.solution_deck.length > 0) return "streaming";
  return "thinking";
}

interface QuestionTimelineProps {
  cards: EvidenceCard[];
  selectedCardId: string | null;
  onSelectCard: (cardId: string) => void;
}

interface Thread {
  key: string;
  root: EvidenceCard;
  /** All restatement passes of the root (root included), newest text wins. */
  passes: EvidenceCard[];
  /** Follow-up cards linked via parent_question_id. */
  followUps: EvidenceCard[];
}

/** Cluster key mirroring the backend's fallback_question_key: first 6 significant words. */
function clusterKey(card: EvidenceCard): string {
  const text = (card.question ?? card.query ?? "").toLowerCase();
  return text
    .replace(/[^a-z0-9 ]/g, " ")
    .split(/\s+/)
    .filter((word) => word.length > 2)
    .slice(0, 6)
    .join(" ");
}

/**
 * Group cards into threads: restatement passes cluster under one root
 * (dedupe badge shows the pass count), and follow-ups nest under the
 * thread owning their parent_question_id. Newest thread first.
 */
function buildThreads(cards: EvidenceCard[]): Thread[] {
  const byQuestionId = new Map<string, Thread>();
  const byKey = new Map<string, Thread>();
  const threads: Thread[] = [];
  const sorted = [...cards].sort((a, b) => a.created_at.localeCompare(b.created_at));

  for (const card of sorted) {
    const parentId = card.parent_question_id;
    if (parentId && byQuestionId.has(parentId)) {
      byQuestionId.get(parentId)!.followUps.push(card);
      continue;
    }
    const key = clusterKey(card);
    const existing = byKey.get(key);
    if (existing && key) {
      existing.passes.push(card);
      existing.root = card; // newest restatement is the representative
    } else {
      const thread: Thread = { key: key || card.card_id, root: card, passes: [card], followUps: [] };
      threads.push(thread);
      if (key) byKey.set(key, thread);
    }
    if (card.question_id) byQuestionId.set(card.question_id, byKey.get(key) ?? threads[threads.length - 1]);
  }
  return threads.reverse();
}

const STATUS_CHIP: Record<FlashCardStatus, { label: string; className: string; spinning: boolean }> = {
  thinking: { label: "Thinking", className: "border-purple-800/50 bg-purple-950/40 text-purple-300", spinning: true },
  streaming: { label: "Streaming", className: "border-blue-800/50 bg-blue-950/40 text-blue-300", spinning: true },
  ready: { label: "Ready", className: "border-emerald-800/50 bg-emerald-950/40 text-emerald-300", spinning: false },
};

function timeOf(createdAt: string): string {
  const date = new Date(createdAt);
  return `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}:${date
    .getSeconds()
    .toString()
    .padStart(2, "0")}`;
}

export function QuestionTimeline({ cards, selectedCardId, onSelectCard }: QuestionTimelineProps) {
  useRegisterAction({
    element_id: "question-timeline-select",
    app: "live-evidence",
    action: "select_timeline_card",
    label: "Select timeline card",
    description: "Select a question topic or follow-up from the threaded timeline.",
  });
  const threads = useMemo(() => buildThreads(cards), [cards]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const activeKey = threads[0]?.key;

  return (
    <aside className="flex h-full w-[280px] min-w-[280px] flex-col overflow-hidden border-r border-gray-800/60 bg-[#0c0d14] select-none">
      <div className="flex items-center justify-between border-b border-gray-800/50 p-2.5 text-xs font-semibold text-gray-400">
        <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider">
          <Layers className="size-3.5 text-emerald-400" aria-hidden="true" />
          Question Topics
        </span>
        <span className="font-mono text-[10px] text-gray-500">
          {threads.length} topics · {cards.length} events
        </span>
      </div>

      <div className="flex-1 space-y-1.5 overflow-y-auto p-2">
        {threads.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-2 text-xs text-gray-600">
            <MessageSquare className="size-6 opacity-40" aria-hidden="true" />
            <span>Listening for questions…</span>
          </div>
        ) : (
          threads.map((thread) => {
            const card = thread.root;
            const isActive = thread.key === activeKey;
            const containsSelection =
              card.card_id === selectedCardId ||
              thread.passes.some((c) => c.card_id === selectedCardId) ||
              thread.followUps.some((c) => c.card_id === selectedCardId);
            const isExpanded = expanded[thread.key] ?? (containsSelection && thread.followUps.length > 0);
            const status = flashCardStatus(card);
            const chip = STATUS_CHIP[status];
            const passCount = thread.passes.length;

            return (
              <div
                key={thread.key}
                className={`rounded-lg border transition-all ${
                  containsSelection
                    ? "border-emerald-500/50 bg-[#141c2e] shadow-sm shadow-emerald-950/20"
                    : isActive
                      ? "border-gray-700 bg-[#11131c]/80"
                      : "border-gray-800/60 bg-[#11131c]/50 opacity-80 hover:opacity-100 hover:border-gray-700"
                }`}
              >
                <button
                  type="button"
                  data-qid={`question-timeline-card-${card.card_id}`}
                  data-qs-action="select_timeline_card"
                  title="Select question topic"
                  onClick={() => onSelectCard(card.card_id)}
                  className="w-full cursor-pointer p-2.5 text-left"
                >
                  <div className="mb-1.5 flex items-center justify-between gap-1.5">
                    <span
                      className={`relative inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${chip.className}`}
                    >
                      {chip.spinning ? (
                        <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                      ) : (
                        <CheckCircle2 className="size-3" aria-hidden="true" />
                      )}
                      {isActive && status === "ready" ? "Active" : chip.label}
                    </span>
                    <span className="flex items-center gap-1">
                      {card.pinned ? <Pin className="size-3 fill-amber-400 text-amber-400" aria-hidden="true" /> : null}
                      {passCount > 1 ? (
                        <span
                          className="rounded border border-gray-700/60 bg-gray-800 px-1.5 py-0.5 font-mono text-[10px] text-gray-400"
                          title={`${passCount} deduplicated transcription passes`}
                        >
                          {passCount}x
                        </span>
                      ) : null}
                      <span className="flex items-center gap-0.5 font-mono text-[10px] text-gray-500">
                        <Clock className="size-2.5" aria-hidden="true" />
                        {timeOf(card.created_at)}
                      </span>
                      {thread.followUps.length > 0 ? (
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(event) => {
                            event.stopPropagation();
                            setExpanded((prev) => ({ ...prev, [thread.key]: !isExpanded }));
                          }}
                          className="rounded p-0.5 text-gray-400 hover:bg-gray-800/60 hover:text-gray-200"
                        >
                          {isExpanded ? (
                            <ChevronDown className="size-3.5" aria-hidden="true" />
                          ) : (
                            <ChevronRight className="size-3.5" aria-hidden="true" />
                          )}
                        </span>
                      ) : null}
                    </span>
                  </div>
                  <p className="line-clamp-2 text-xs font-medium leading-snug text-gray-200">
                    {card.question ?? card.query}
                  </p>
                </button>

                {isExpanded && thread.followUps.length > 0 ? (
                  <div className="space-y-1 rounded-b-lg border-t border-gray-800/60 bg-[#0c101a] p-1.5">
                    <div className="flex items-center justify-between px-1 text-[10px] font-medium uppercase tracking-wider text-gray-500">
                      <span>Follow-ups</span>
                      <span>{thread.followUps.length}</span>
                    </div>
                    {thread.followUps.map((followUp) => (
                      <button
                        key={followUp.card_id}
                        type="button"
                        data-qid={`question-timeline-card-${followUp.card_id}`}
                        data-qs-action="select_timeline_card"
                        title="Select follow-up question"
                        onClick={() => onSelectCard(followUp.card_id)}
                        className={`flex w-full cursor-pointer items-start gap-2 rounded border p-1.5 text-left transition-colors ${
                          followUp.card_id === selectedCardId
                            ? "border-emerald-600/50 bg-[#161e30]"
                            : "border-transparent hover:border-gray-800 hover:bg-[#161e30]"
                        }`}
                      >
                        <MessageSquare className="mt-0.5 size-3 shrink-0 text-emerald-400/70" aria-hidden="true" />
                        <span className="min-w-0 flex-1">
                          <span className="mb-0.5 block font-mono text-[10px] text-gray-500">{timeOf(followUp.created_at)}</span>
                          <span className="block text-[11px] leading-tight text-gray-300">
                            {followUp.question ?? followUp.query}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
