import { CheckCircle2, Circle, CircleHelp, Clipboard, Clock3, PencilLine, Target, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useHUDHotkeys } from "@/hooks/useHUDHotkeys";
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
        label: "Bounds on N?",
        question: "What are the expected bounds on string length N, and are there memory constraints?",
      },
      {
        id: "character-set",
        label: "Character Set?",
        question: "Does the string contain only bracket pairs, or can it include arbitrary alphanumeric characters?",
      },
      {
        id: "return-contract",
        label: "Return Type?",
        question: "Should we return a boolean, a corrected string, or the invalid indices?",
      },
      {
        id: "edge-cases",
        label: "Empty Strings?",
        question: "How should empty strings, unmatched closing brackets, and leftover opening brackets behave?",
      },
    ];
  }
  return [
    {
      id: "input-shape",
      label: "Input Shape?",
      question: "What are the input types, bounds, and malformed-input expectations?",
    },
    {
      id: "output-contract",
      label: "Output Type?",
      question: "What exactly should be returned, and are multiple valid outputs acceptable?",
    },
    {
      id: "constraints",
      label: "Constraints?",
      question: "What time, memory, ordering, or mutation constraints matter for this solution?",
    },
    {
      id: "examples",
      label: "Examples?",
      question: "Can we confirm one normal case and one edge case before implementing?",
    },
  ];
}

export function activeClarificationPrompt(card: EvidenceCard): string {
  return clarificationItems(card)[0]?.question ?? "Confirm the problem contract before answering.";
}

function nextStatus(status: ClarifyStatus): ClarifyStatus {
  if (status === "unanswered") return "confirmed";
  if (status === "confirmed") return "denied";
  return "unanswered";
}

function statusLabel(status: ClarifyStatus, activeNext: boolean): string {
  if (activeNext) return "Active Step";
  if (status === "confirmed") return "Confirmed";
  if (status === "denied") return "Alt Contract";
  return "Unanswered";
}

function StatusIcon({ status, activeNext }: { status: ClarifyStatus; activeNext: boolean }) {
  if (activeNext) return <Target aria-hidden="true" className="size-4 text-amber-300" />;
  if (status === "confirmed") return <CheckCircle2 aria-hidden="true" className="size-4 text-emerald-300" />;
  if (status === "denied") return <XCircle aria-hidden="true" className="size-4 text-rose-300" />;
  return <Circle aria-hidden="true" className="size-4 text-slate-600" />;
}

function ChecklistItem({
  cardId,
  item,
  index,
  status,
  note,
  activeNext,
  activeEditing,
  onToggle,
  onEdit,
}: {
  cardId: string;
  item: ClarifyItem;
  index: number;
  status: ClarifyStatus;
  note: string;
  activeNext: boolean;
  activeEditing: boolean;
  onToggle: (id: string) => void;
  onEdit: (id: string) => void;
}) {
  const qid = `live-evidence:clarify:item:${cardId}:${item.id}`;
  const editQid = `live-evidence:clarify:edit-note:${cardId}:${item.id}`;
  const noteQid = `live-evidence:clarify:note:${cardId}:${item.id}`;
  const answer = note.trim();
  useRegisterAction({
    element_id: qid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CLARIFY_ITEM_TOGGLE",
    label: `Toggle clarification ${index}`,
    description: "Cycle a clarification item between unanswered, confirmed, and alternate contract",
    params: { card_id: cardId, item_id: item.id },
  });
  useRegisterAction({
    element_id: editQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CLARIFY_NOTE_EDIT",
    label: `Edit clarification note ${index}`,
    description: "Open the manual clarification note editor for one item",
    params: { card_id: cardId, item_id: item.id },
  });
  useRegisterAction({
    element_id: noteQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CLARIFY_NOTE_UPDATE",
    label: `Update clarification note ${index}`,
    description: "Capture the interviewer's answer or operator note for a clarification item",
    params: { card_id: cardId, item_id: item.id },
  });

  return (
    <article
      title={`${activeNext ? "Active next step: " : ""}${item.question}`}
      className={`clarify-anchor-card ${activeNext ? "active-next-action" : ""}`}
      data-status={status}
      data-active-next={activeNext ? "true" : "false"}
      aria-label={`Clarification ${index}: ${item.label}`}
    >
      <span className="clarify-anchor-copy">
        <span className="anchor-title">
          {index}. {item.label}
        </span>
        <span className="anchor-subtext">{item.question}</span>
        <span className="clarify-answer-chip" data-state={answer ? "answered" : "pending"}>
          {answer || "Listening for answer"}
        </span>
      </span>
      <span className="clarify-card-actions">
        <button
          data-qid={editQid}
          data-qs-action="LIVE_EVIDENCE_CLARIFY_NOTE_EDIT"
          type="button"
          title={`Edit answer note for ${item.label}`}
          className={`clarify-edit-button ${activeEditing ? "is-active" : ""}`}
          onClick={() => onEdit(item.id)}
          aria-label={`Edit answer note for ${item.label}`}
          aria-pressed={activeEditing}
        >
          <PencilLine aria-hidden="true" className="size-3.5" />
        </button>
        <button
          data-qid={qid}
          data-qs-action="LIVE_EVIDENCE_CLARIFY_ITEM_TOGGLE"
          type="button"
          title={`Cycle clarification status for ${item.label}`}
          className="clarify-status-icon"
          onClick={() => onToggle(item.id)}
          aria-label={`Cycle clarification ${index}: ${statusLabel(status, activeNext)}`}
          aria-pressed={status !== "unanswered"}
        >
          <StatusIcon status={status} activeNext={activeNext} />
        </button>
      </span>
    </article>
  );
}

export function ClarificationCard({ card }: ClarificationCardProps) {
  const items = useMemo(() => clarificationItems(card), [card]);
  const [seconds, setSeconds] = useState(45);
  const [completed, setCompleted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [statuses, setStatuses] = useState<Record<string, ClarifyStatus>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const copyQid = `live-evidence:clarify:copy:${card.card_id}`;
  const completeQid = `live-evidence:clarify:complete:${card.card_id}`;
  const closeNoteQid = `live-evidence:clarify:note-editor-close:${card.card_id}`;
  const timerState = completed ? "complete" : seconds <= 0 ? "expired" : seconds <= 10 ? "urgent" : seconds <= 20 ? "warning" : "normal";
  const activeNextId = useMemo(() => items.find((item) => (statuses[item.id] ?? "unanswered") === "unanswered")?.id ?? null, [items, statuses]);
  const editingItem = items.find((item) => item.id === editingNoteId);

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
  useRegisterAction({
    element_id: closeNoteQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CLARIFY_NOTE_EDITOR_CLOSE",
    label: "Close clarification note editor",
    description: "Close the manual clarification note editor and return to the compact grid",
    params: { card_id: card.card_id },
  });

  useEffect(() => {
    setSeconds(45);
    setCompleted(false);
    setCopied(false);
    setStatuses({});
    setNotes({});
    setEditingNoteId(null);
  }, [card.card_id]);

  useEffect(() => {
    if (completed || seconds <= 0) return;
    const timer = window.setTimeout(() => setSeconds((value) => Math.max(value - 1, 0)), 1_000);
    return () => window.clearTimeout(timer);
  }, [completed, seconds]);

  const toggleItem = (id: string) => {
    setStatuses((current) => ({ ...current, [id]: nextStatus(current[id] ?? "unanswered") }));
  };

  const updateNote = (id: string, value: string) => {
    setNotes((current) => ({ ...current, [id]: value }));
  };

  const editNote = (id: string) => {
    setEditingNoteId((current) => (current === id ? null : id));
  };

  const copyQuestions = async () => {
    await navigator.clipboard.writeText(
      items
        .map((item) => {
          const answer = notes[item.id]?.trim();
          return `${item.label}: ${item.question}${answer ? `\nAnswer: ${answer}` : ""}`;
        })
        .join("\n\n"),
    );
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  };

  useHUDHotkeys([
    { key: "Shift+Space", handler: () => setCompleted(true) },
    { key: "1", handler: () => items[0] && toggleItem(items[0].id) },
    { key: "2", handler: () => items[1] && toggleItem(items[1].id) },
    { key: "3", handler: () => items[2] && toggleItem(items[2].id) },
    { key: "4", handler: () => items[3] && toggleItem(items[3].id) },
  ]);

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
      <div className="clarify-grid">
        {items.map((item, index) => (
          <ChecklistItem
            key={item.id}
            cardId={card.card_id}
            item={item}
            index={index + 1}
            status={statuses[item.id] ?? "unanswered"}
            note={notes[item.id] ?? ""}
            activeNext={item.id === activeNextId}
            activeEditing={item.id === editingNoteId}
            onToggle={toggleItem}
            onEdit={editNote}
          />
        ))}
      </div>
      {editingItem ? (
        <div className="clarify-note-editor">
          <label htmlFor={`clarify-note-editor-${card.card_id}-${editingItem.id}`}>Manual note: {editingItem.label}</label>
          <div className="clarify-note-editor-row">
            <input
              id={`clarify-note-editor-${card.card_id}-${editingItem.id}`}
              data-qid={`live-evidence:clarify:note:${card.card_id}:${editingItem.id}`}
              data-qs-action="LIVE_EVIDENCE_CLARIFY_NOTE_UPDATE"
              title={`Answer note for ${editingItem.label}`}
              value={notes[editingItem.id] ?? ""}
              onChange={(event) => updateNote(editingItem.id, event.target.value)}
              placeholder="Only type here when the call allows it."
              aria-label={`Answer note for ${editingItem.label}`}
            />
            <button
              data-qid={closeNoteQid}
              data-qs-action="LIVE_EVIDENCE_CLARIFY_NOTE_EDITOR_CLOSE"
              title="Close clarification note editor"
              type="button"
              onClick={() => setEditingNoteId(null)}
            >
              Close
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
