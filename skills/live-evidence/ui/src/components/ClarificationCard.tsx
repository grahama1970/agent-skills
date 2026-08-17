import { CheckCircle2, CircleHelp, Clipboard, Clock3 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useRegisterAction } from "@/hooks/useRegisterAction";
import type { EvidenceCard } from "@/types";

type ClarifyStatus = "unanswered" | "confirmed" | "denied";

interface ClarifyItem {
  id: string;
  label: string;
  question: string;
}

interface ClarificationCardProps {
  card: EvidenceCard;
}

function isParenthesesQuestion(card: EvidenceCard): boolean {
  const text = `${card.question ?? ""} ${card.query} ${card.answer ?? ""}`.toLowerCase();
  return /parenthes|bracket|stack|\(\)/i.test(text);
}

function clarificationItems(card: EvidenceCard): ClarifyItem[] {
  if (isParenthesesQuestion(card)) {
    return [
      {
        id: "input-constraints",
        label: "Input Constraints",
        question: "What are the expected bounds on string length N, and are there memory constraints?",
      },
      {
        id: "character-set",
        label: "Character Set",
        question: "Does the string contain only bracket pairs, or can it include arbitrary alphanumeric characters?",
      },
      {
        id: "return-contract",
        label: "Return Requirements",
        question: "Should we return a boolean, a corrected string, or the invalid indices?",
      },
      {
        id: "edge-cases",
        label: "Edge Cases",
        question: "How should empty strings, unmatched closing brackets, and leftover opening brackets behave?",
      },
    ];
  }
  return [
    {
      id: "input-shape",
      label: "Input Shape",
      question: "What are the input types, bounds, and malformed-input expectations?",
    },
    {
      id: "output-contract",
      label: "Output Contract",
      question: "What exactly should be returned, and are multiple valid outputs acceptable?",
    },
    {
      id: "constraints",
      label: "Constraints",
      question: "What time, memory, ordering, or mutation constraints matter for this solution?",
    },
    {
      id: "examples",
      label: "Examples",
      question: "Can we confirm one normal case and one edge case before implementing?",
    },
  ];
}

function nextStatus(status: ClarifyStatus): ClarifyStatus {
  if (status === "unanswered") return "confirmed";
  if (status === "confirmed") return "denied";
  return "unanswered";
}

function ChecklistItem({
  cardId,
  item,
  index,
  status,
  onToggle,
}: {
  cardId: string;
  item: ClarifyItem;
  index: number;
  status: ClarifyStatus;
  onToggle: (id: string) => void;
}) {
  const qid = `live-evidence:clarify:item:${cardId}:${item.id}`;
  useRegisterAction({
    element_id: qid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CLARIFY_ITEM_TOGGLE",
    label: `Toggle clarification ${index}`,
    description: "Cycle a clarification item between unanswered, confirmed, and alternate contract",
    params: { card_id: cardId, item_id: item.id },
  });

  return (
    <div className="clarify-checklist-item" data-status={status}>
      <button
        data-qid={qid}
        data-qs-action="LIVE_EVIDENCE_CLARIFY_ITEM_TOGGLE"
        title={`Toggle clarification ${index}`}
        type="button"
        className="clarify-hotkey"
        onClick={() => onToggle(item.id)}
        aria-label={`Toggle clarification ${index}`}
      >
        {index}
      </button>
      <div className="clarify-item-copy">
        <span>{item.label}</span>
        <p>{item.question}</p>
      </div>
      <span className="clarify-status">{status.replace("-", " ")}</span>
    </div>
  );
}

export function ClarificationCard({ card }: ClarificationCardProps) {
  const items = useMemo(() => clarificationItems(card), [card]);
  const [seconds, setSeconds] = useState(45);
  const [completed, setCompleted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, ClarifyStatus>>({});
  const copyQid = `live-evidence:clarify:copy:${card.card_id}`;
  const completeQid = `live-evidence:clarify:complete:${card.card_id}`;
  const timerState = completed ? "complete" : seconds <= 0 ? "expired" : seconds <= 10 ? "urgent" : seconds <= 20 ? "warning" : "normal";

  useRegisterAction({
    element_id: copyQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CLARIFY_COPY",
    label: "Copy clarifying questions",
    description: "Copy the active card's clarifying questions",
    params: { card_id: card.card_id },
  });
  useRegisterAction({
    element_id: completeQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CLARIFY_COMPLETE",
    label: "Complete clarification phase",
    description: "Mark the current card as ready to move from clarification to solution",
    params: { card_id: card.card_id },
  });

  useEffect(() => {
    setSeconds(45);
    setCompleted(false);
    setCopied(false);
    setStatuses({});
  }, [card.card_id]);

  useEffect(() => {
    if (completed || seconds <= 0) return;
    const timer = window.setTimeout(() => setSeconds((value) => Math.max(value - 1, 0)), 1_000);
    return () => window.clearTimeout(timer);
  }, [completed, seconds]);

  const toggleItem = (id: string) => {
    setStatuses((current) => ({ ...current, [id]: nextStatus(current[id] ?? "unanswered") }));
  };

  const copyQuestions = async () => {
    await navigator.clipboard.writeText(items.map((item) => `${item.label}: ${item.question}`).join("\n"));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const active = document.activeElement;
      if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement || active instanceof HTMLSelectElement) return;
      if (event.shiftKey && event.key.toLowerCase() === "c") {
        event.preventDefault();
        void copyQuestions();
      }
      if (event.shiftKey && event.code === "Space") {
        event.preventDefault();
        setCompleted(true);
      }
      if (/^[1-4]$/.test(event.key)) {
        const item = items[Number(event.key) - 1];
        if (!item) return;
        event.preventDefault();
        toggleItem(item.id);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [items]);

  return (
    <section className={`hero-clarify-card ${completed ? "phase-completed" : "phase-active"}`} aria-label="Clarifying questions">
      <div className="clarify-header">
        <div className="clarify-title-group">
          <span className="badge-amber">
            <CircleHelp aria-hidden="true" className="size-3.5" />
            Ask Interviewer First
          </span>
          <span className="timer-badge" data-state={timerState}>
            {completed ? <CheckCircle2 aria-hidden="true" className="size-3.5" /> : <Clock3 aria-hidden="true" className="size-3.5" />}
            {completed ? "Clarified" : seconds <= 0 ? "Move to solution" : `Clarify window 0:${String(seconds).padStart(2, "0")}`}
          </span>
        </div>
        <div className="clarify-actions">
          <button
            data-qid={copyQid}
            data-qs-action="LIVE_EVIDENCE_CLARIFY_COPY"
            title="Copy clarifying questions"
            type="button"
            onClick={() => void copyQuestions()}
          >
            {copied ? <CheckCircle2 aria-hidden="true" className="size-3.5" /> : <Clipboard aria-hidden="true" className="size-3.5" />}
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            data-qid={completeQid}
            data-qs-action="LIVE_EVIDENCE_CLARIFY_COMPLETE"
            title="Complete clarification phase"
            type="button"
            onClick={() => setCompleted(true)}
          >
            Done
          </button>
        </div>
      </div>
      <div className="clarify-checklist">
        {items.map((item, index) => (
          <ChecklistItem
            key={item.id}
            cardId={card.card_id}
            item={item}
            index={index + 1}
            status={statuses[item.id] ?? "unanswered"}
            onToggle={toggleItem}
          />
        ))}
      </div>
    </section>
  );
}
