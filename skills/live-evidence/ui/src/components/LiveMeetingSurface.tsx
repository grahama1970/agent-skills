import { Brain, Radio } from "lucide-react";
import { useState } from "react";

import { activeClarificationPrompt, ClarificationCard } from "@/components/ClarificationCard";
import { MeetingHUDHeader, SpeechTeleprompterBar } from "@/components/MeetingHUDHeader";
import { SolutionStage } from "@/components/SolutionStage";
import { useDefinitionPeek } from "@/hooks/useDefinitionPeek";
import { useHUDHotkeys } from "@/hooks/useHUDHotkeys";
import { useRegisterAction } from "@/hooks/useRegisterAction";
import { compactPath } from "@/lib/utils";
import type { EvidenceCard, LaneActivity, SessionInfo } from "@/types";

type CardKind = "code" | "fact" | "memory" | "urgent";

interface LiveMeetingSurfaceProps {
  cards: EvidenceCard[];
  activeCard?: EvidenceCard;
  selectedCardId?: string | null;
  connected: boolean;
  busy: boolean;
  currentThread: string;
  lanes: LaneActivity[];
  session: SessionInfo;
  transcriptCount: number;
  vaultOpen: boolean;
  onSelectCard: (cardId: string) => void;
  onPin: (cardId: string) => void;
  onDismiss: (cardId: string) => void;
  onOpenTranscript: () => void;
  onToggleVault: () => void;
  onStart: () => void;
  onPause: () => void;
  onStop: () => void;
}

function cardKind(card: EvidenceCard): CardKind {
  if (card.status === "insufficient") return "urgent";
  if (card.lanes.some((lane) => lane === "ask" || lane === "code" || lane === "ripgrep")) return "code";
  if (card.lanes.includes("memory")) return "memory";
  return "fact";
}

function sourceLabel(card?: EvidenceCard): string {
  const source = card?.sources[0];
  if (!source) return "Source pending";
  const locator = source.path ?? source.url ?? source.label;
  const suffix = source.line_start ? `:${source.line_start}` : "";
  return `${source.repository ?? source.lane} / ${compactPath(locator)}${suffix}`;
}

function previewText(card: EvidenceCard): string {
  const raw = card.answer || card.talking_point;
  if (raw === "No source-bound support surfaced yet.") {
    return card.status === "insufficient" ? "Pending source-bound evidence" : "Clarify before relying on this card";
  }
  return raw;
}

function lineageLabel(card: EvidenceCard): string {
  const parts: string[] = [];
  if (card.question_id) {
    parts.push(`q:${card.question_id.slice(0, 8)}`);
  }
  if (card.question_revision && card.question_revision > 0) {
    parts.push(`rev ${card.question_revision}`);
  }
  if (card.frame_refs?.length) {
    parts.push(`${card.frame_refs.length} frame${card.frame_refs.length === 1 ? "" : "s"}`);
  }
  return parts.join(" · ");
}

function LiveCardStream({
  cards,
  selectedCardId,
  onSelectCard,
}: Pick<LiveMeetingSurfaceProps, "cards" | "selectedCardId" | "onSelectCard">) {
  useRegisterAction({
    element_id: "live-evidence:card-stream:select",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_CARD_SELECT",
    label: "Select evidence card",
    description: "Select a live evidence flashcard and open it in the detail stage",
  });

  return (
    <aside className="card-stream" aria-label="Live evidence card stream">
      <div className="stream-heading">
        <span>Live Cards</span>
        <span>{cards.length}</span>
      </div>
      <div className="space-y-2" role="listbox" aria-label="Current evidence cards">
        {cards.length === 0 ? (
          <div className="empty-stream">
            <Brain aria-hidden="true" className="size-5 text-slate-500" />
            <p>Waiting for the first useful question.</p>
            <span>Cards appear here when transcript windows produce evidence.</span>
          </div>
        ) : (
          cards.map((card, index) => {
            const active = card.card_id === selectedCardId;
            const kind = cardKind(card);
            return (
              <button
                key={card.card_id}
                type="button"
                data-qid={`live-evidence:card-stream:select:${card.card_id}`}
                data-qs-action="LIVE_EVIDENCE_CARD_SELECT"
                title="Select evidence card"
                className={`flashcard entering ${active ? "active" : ""} ${card.pinned ? "pinned" : ""}`}
                data-type={kind}
                role="option"
                aria-selected={active}
                onClick={() => onSelectCard(card.card_id)}
              >
                <div className="card-top">
                  <span>#{kind}</span>
                  <span>{index === 0 ? "Now" : `${index + 1}`}</span>
                </div>
                <div className="card-question-preview">{card.question || card.query}</div>
                <div className="card-answer-preview">{previewText(card)}</div>
                {lineageLabel(card) ? (
                  <div className="mt-2 truncate font-mono text-[10px] text-slate-500" title={lineageLabel(card)}>
                    {lineageLabel(card)}
                  </div>
                ) : null}
                <div className="mt-2 flex items-center justify-between gap-2 text-[10px] text-slate-500">
                  <span className="truncate">{sourceLabel(card)}</span>
                  <span>{Math.round(card.confidence * 100)}%</span>
                </div>
                {!card.pinned ? <div className="timer-progress-bar" /> : null}
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}

function ActiveInsightStage({
  card,
  busy,
  onPin,
  onDismiss,
  voiceEnabled = false,
}: {
  card?: EvidenceCard;
  busy: boolean;
  onPin: (cardId: string) => void;
  onDismiss: (cardId: string) => void;
  voiceEnabled?: boolean;
}) {
  if (!card) {
    return (
      <main id="active-insight-stage" className="main-stage" tabIndex={-1}>
        <div className="stage-content">
          <div className="empty-stage">
            <Radio aria-hidden="true" className="size-8 text-slate-500" />
            <h2>Listening for a usable question</h2>
            <p>When Live Evidence finds a source-bound answer, the newest card opens here for a fast glance.</p>
          </div>
        </div>
      </main>
    );
  }

  const kind = cardKind(card);
  const question = card.question || card.query;
  const lineage = lineageLabel(card);

  return (
    <main id="active-insight-stage" className="main-stage" tabIndex={-1}>
      <div className="stage-content">
        <div className="topic-breadcrumbs">
          <span className="tag">#{kind}</span>
          {card.lanes.slice(0, 3).map((lane) => (
            <span key={lane} className="tag">
              #{lane}
            </span>
          ))}
          {card.pinned ? <span className="tag tag-pinned">Pinned</span> : null}
        </div>

        <div className="question-anchor">"{question}"</div>
        {lineage ? (
          <div className="mt-3 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">
            <span>{lineage}</span>
            <span>card:{card.card_id.slice(0, 8)}</span>
          </div>
        ) : null}

        <ClarificationCard card={card} />
        <SolutionStage card={card} busy={busy} kind={kind} onPin={onPin} onDismiss={onDismiss} voiceEnabled={voiceEnabled} />
      </div>
    </main>
  );
}

export function LiveMeetingSurface(props: LiveMeetingSurfaceProps) {
  const [compactMode, setCompactMode] = useState(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("compact") === "1";
  });
  const { isPeeking, toggleDefinitionPeek } = useDefinitionPeek();
  const shimmerKey = props.selectedCardId ?? props.activeCard?.card_id ?? "empty";
  const sayAloudPrompt = props.activeCard ? activeClarificationPrompt(props.activeCard) : "Wait for a stable question before answering.";
  const toggleCompactMode = () => setCompactMode((value) => !value);

  useHUDHotkeys([{ key: "Shift+F", handler: toggleCompactMode }]);

  return (
    <div
      className={`meeting-shell app-hud-root ${compactMode ? "compact-mode" : ""} ${isPeeking ? "peek-mode" : ""}`}
      data-listening={props.session.status === "listening" ? "true" : "false"}
      data-compact={compactMode ? "true" : "false"}
      data-peek={isPeeking ? "true" : "false"}
    >
      <div key={shimmerKey} className="top-shimmer-alert shimmer-active" aria-hidden="true" />
      <MeetingHUDHeader
        {...props}
        compactMode={compactMode}
        peekMode={isPeeking}
        onToggleCompact={toggleCompactMode}
        onTogglePeek={toggleDefinitionPeek}
      />
      <SpeechTeleprompterBar prompt={sayAloudPrompt} />
      <div className="app-layout">
        <LiveCardStream cards={props.cards} selectedCardId={props.selectedCardId} onSelectCard={props.onSelectCard} />
        <ActiveInsightStage card={props.activeCard} busy={props.busy} onPin={props.onPin} onDismiss={props.onDismiss} voiceEnabled={props.session?.policy?.voice_output === true} />
      </div>
    </div>
  );
}
