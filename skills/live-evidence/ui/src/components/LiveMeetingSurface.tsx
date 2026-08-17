import { Archive, Brain, FileText, Maximize2, MessageCircle, Mic, MicOff, Minimize2, Radio } from "lucide-react";
import { useState } from "react";

import { activeClarificationPrompt, ClarificationCard } from "@/components/ClarificationCard";
import { SessionControls } from "@/components/SessionControls";
import { SolutionStage } from "@/components/SolutionStage";
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

function laneTone(state: LaneActivity["state"]): string {
  if (state === "ok") return "bg-emerald-300";
  if (state === "running") return "bg-sky-300 animate-pulse";
  if (state === "degraded" || state === "error") return "bg-amber-300";
  if (state === "disabled") return "bg-slate-600";
  return "bg-slate-400";
}

function liveStatusLabel(session: SessionInfo, connected: boolean): string {
  if (connected && session.status === "listening") return "Listening";
  if (!connected) return "Reconnecting";
  return session.status;
}

function SpeechTeleprompterBar({ prompt }: { prompt: string }) {
  return (
    <div className="teleprompter-bar" data-aoi="AOI_PROMPTER" aria-label="Say aloud prompt">
      <div className="teleprompter-copy">
        <span className="teleprompter-label">
          <MessageCircle aria-hidden="true" className="size-3.5" />
          Say aloud
        </span>
        <span className="teleprompter-prompt">"{prompt}"</span>
      </div>
      <span className="teleprompter-anchor">Glance Anchor</span>
    </div>
  );
}

function QuietHeader({
  connected,
  currentThread,
  lanes,
  session,
  transcriptCount,
  vaultOpen,
  busy,
  onOpenTranscript,
  onToggleVault,
  onStart,
  onPause,
  onStop,
  compactMode,
  onToggleCompact,
}: Pick<
  LiveMeetingSurfaceProps,
  | "connected"
  | "currentThread"
  | "lanes"
  | "session"
  | "transcriptCount"
  | "vaultOpen"
  | "busy"
  | "onOpenTranscript"
  | "onToggleVault"
  | "onStart"
  | "onPause"
  | "onStop"
> & {
  compactMode: boolean;
  onToggleCompact: () => void;
}) {
  const listening = connected && session.status === "listening";

  useRegisterAction({
    element_id: "live-evidence:meeting:open-transcript",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_MEETING_OPEN_TRANSCRIPT",
    label: "Open transcript",
    description: "Open the live transcript drawer for the current meeting session",
  });
  useRegisterAction({
    element_id: "live-evidence:meeting:toggle-vault",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_MEETING_TOGGLE_VAULT",
    label: "Toggle Memory Vault",
    description: "Show or hide the searchable post-call memory vault",
  });
  useRegisterAction({
    element_id: "live-evidence:meeting:toggle-stt",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_MEETING_TOGGLE_STT",
    label: "Toggle local STT session",
    description: "Start or pause the existing consented local STT/evidence session",
  });
  useRegisterAction({
    element_id: "live-evidence:meeting:toggle-compact",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_MEETING_TOGGLE_COMPACT",
    label: "Toggle compact webcam strip mode",
    description: "Switch Live Evidence between full HUD and compact webcam-line-of-sight mode",
  });

  return (
    <header className="hud-header">
      <div className="flex min-w-0 items-center gap-3">
        <div className="live-pill">
          <span className="pulse-dot" />
          {liveStatusLabel(session, connected)}
        </div>
        <div className="hidden min-w-0 items-center gap-2 text-[11px] text-slate-400 md:flex">
          <Radio aria-hidden="true" className="size-3 text-sky-300" />
          <span className="max-w-[20rem] truncate">{currentThread}</span>
        </div>
        <div className="hidden items-center gap-2 text-[11px] text-slate-500 lg:flex" aria-label="Lane health">
          {lanes.slice(0, 4).map((lane) => (
            <span key={lane.lane} className="inline-flex items-center gap-1.5 capitalize" title={`${lane.lane}: ${lane.detail}`}>
              <span className={`size-1.5 rounded-full ${laneTone(lane.state)}`} />
              {lane.lane}
            </span>
          ))}
        </div>
      </div>

      <div className="hud-hotkeys" aria-label="HUD keyboard shortcuts">
        <kbd>Space</kbd> Pin
        <span>|</span>
        <kbd>1-4</kbd> Clarify
        <span>|</span>
        <kbd>Shift+C</kbd> Copy Code
        <span>|</span>
        <kbd>Shift+F</kbd> Compact
      </div>

      <div className="flex items-center gap-2">
        <span className="transcript-count-label hidden font-mono text-[10px] text-slate-500 sm:inline">{transcriptCount} turns</span>
        <button
          type="button"
          data-qid="live-evidence:meeting:toggle-stt"
          data-qs-action="LIVE_EVIDENCE_MEETING_TOGGLE_STT"
          title={listening ? "Pause local STT/evidence session" : "Start local STT/evidence session"}
          className={`stt-status-button ${listening ? "is-listening" : ""}`}
          disabled={busy}
          onClick={listening ? onPause : onStart}
          aria-label={listening ? "Pause local STT evidence session" : "Start local STT evidence session"}
        >
          {listening ? <Mic aria-hidden="true" className="size-3.5" /> : <MicOff aria-hidden="true" className="size-3.5" />}
          <span>{listening ? "STT Active" : "STT Off"}</span>
        </button>
        <button
          type="button"
          data-qid="live-evidence:meeting:open-transcript"
          data-qs-action="LIVE_EVIDENCE_MEETING_OPEN_TRANSCRIPT"
          title="Open transcript"
          className="quiet-icon-button"
          onClick={onOpenTranscript}
          aria-label="Open transcript"
        >
          <FileText aria-hidden="true" className="size-3.5" />
        </button>
        <button
          type="button"
          data-qid="live-evidence:meeting:toggle-vault"
          data-qs-action="LIVE_EVIDENCE_MEETING_TOGGLE_VAULT"
          title={vaultOpen ? "Hide Vault" : "Show Vault"}
          className={`quiet-icon-button ${vaultOpen ? "is-active" : ""}`}
          onClick={onToggleVault}
          aria-label={vaultOpen ? "Hide Vault" : "Show Vault"}
        >
          <Archive aria-hidden="true" className="size-3.5" />
        </button>
        <button
          type="button"
          data-qid="live-evidence:meeting:toggle-compact"
          data-qs-action="LIVE_EVIDENCE_MEETING_TOGGLE_COMPACT"
          title="Toggle compact webcam strip mode"
          className={`quiet-icon-button ${compactMode ? "is-active" : ""}`}
          onClick={onToggleCompact}
          aria-label={compactMode ? "Exit compact webcam strip mode" : "Enter compact webcam strip mode"}
        >
          {compactMode ? <Maximize2 aria-hidden="true" className="size-3.5" /> : <Minimize2 aria-hidden="true" className="size-3.5" />}
        </button>
        <SessionControls status={session.status} busy={busy} onStart={onStart} onPause={onPause} onStop={onStop} />
      </div>
    </header>
  );
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
}: {
  card?: EvidenceCard;
  busy: boolean;
  onPin: (cardId: string) => void;
  onDismiss: (cardId: string) => void;
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

        <ClarificationCard card={card} />
        <SolutionStage card={card} busy={busy} kind={kind} onPin={onPin} onDismiss={onDismiss} />
      </div>
    </main>
  );
}

export function LiveMeetingSurface(props: LiveMeetingSurfaceProps) {
  const [compactMode, setCompactMode] = useState(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("compact") === "1";
  });
  const shimmerKey = props.selectedCardId ?? props.activeCard?.card_id ?? "empty";
  const sayAloudPrompt = props.activeCard ? activeClarificationPrompt(props.activeCard) : "Wait for a stable question before answering.";
  const toggleCompactMode = () => setCompactMode((value) => !value);

  useHUDHotkeys([{ key: "Shift+F", handler: toggleCompactMode }]);

  return (
    <div
      className={`meeting-shell app-hud-root ${compactMode ? "compact-mode" : ""}`}
      data-listening={props.session.status === "listening" ? "true" : "false"}
      data-compact={compactMode ? "true" : "false"}
    >
      <div key={shimmerKey} className="top-shimmer-alert shimmer-active" aria-hidden="true" />
      <QuietHeader {...props} compactMode={compactMode} onToggleCompact={toggleCompactMode} />
      <SpeechTeleprompterBar prompt={sayAloudPrompt} />
      <div className="app-layout">
        <LiveCardStream cards={props.cards} selectedCardId={props.selectedCardId} onSelectCard={props.onSelectCard} />
        <ActiveInsightStage card={props.activeCard} busy={props.busy} onPin={props.onPin} onDismiss={props.onDismiss} />
      </div>
    </div>
  );
}
