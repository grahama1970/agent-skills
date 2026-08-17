import { Archive, Brain, Check, Clipboard, Code2, DatabaseZap, FileText, Pin, Radio, SearchCode, ShieldAlert, X } from "lucide-react";
import { useState } from "react";

import { ClarificationCard } from "@/components/ClarificationCard";
import { SessionControls } from "@/components/SessionControls";
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
>) {
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

      <div className="flex items-center gap-2">
        <span className="hidden font-mono text-[10px] text-slate-500 sm:inline">{transcriptCount} turns</span>
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
                <div className="card-answer-preview">{card.answer || card.talking_point}</div>
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
  const [copied, setCopied] = useState(false);
  const copyQid = card ? `live-evidence:stage:copy:${card.card_id}` : "live-evidence:stage:copy:none";
  const pinQid = card ? `live-evidence:stage:pin:${card.card_id}` : "live-evidence:stage:pin:none";
  const dismissQid = card ? `live-evidence:stage:dismiss:${card.card_id}` : "live-evidence:stage:dismiss:none";

  useRegisterAction({
    element_id: copyQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_STAGE_COPY",
    label: "Copy active insight",
    description: "Copy the active meeting answer and evidence source",
    params: card ? { card_id: card.card_id } : undefined,
  });
  useRegisterAction({
    element_id: pinQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_STAGE_PIN",
    label: "Pin active insight",
    description: "Pin or release the selected live evidence card",
    params: card ? { card_id: card.card_id } : undefined,
  });
  useRegisterAction({
    element_id: dismissQid,
    app: "live-evidence",
    action: "LIVE_EVIDENCE_STAGE_DISMISS",
    label: "Dismiss active insight",
    description: "Dismiss the selected live evidence card",
    params: card ? { card_id: card.card_id } : undefined,
  });

  const copyInsight = async () => {
    if (!card) return;
    try {
      await navigator.clipboard.writeText(
        `Question: ${card.question || card.query}\n\nAnswer: ${card.answer || card.talking_point}\n\nEvidence: ${
          card.evidence || card.proof
        }\n\nSource: ${sourceLabel(card)}\n\nQualifier: ${card.qualifier}`,
      );
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1_500);
    } catch {
      setCopied(false);
    }
  };

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
  const answer = card.answer || card.talking_point;
  const evidence = card.evidence || card.proof;
  const primarySource = card.sources[0];

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

        <section className="hero-answer-card muted-solution" data-type={kind} aria-label="Direct answer">
          <div className="flex items-center justify-between gap-3">
            <h2>Step 2: Core Algorithm & Strategy</h2>
            <div className="stage-actions">
              <button
                data-qid={pinQid}
                data-qs-action="LIVE_EVIDENCE_STAGE_PIN"
                title={card.pinned ? "Unpin card" : "Pin card"}
                type="button"
                disabled={busy}
                onClick={() => onPin(card.card_id)}
                aria-label={card.pinned ? "Unpin card" : "Pin card"}
              >
                <Pin aria-hidden="true" className="size-3.5" />
              </button>
              <button
                data-qid={copyQid}
                data-qs-action="LIVE_EVIDENCE_STAGE_COPY"
                title="Copy active insight"
                type="button"
                onClick={copyInsight}
                aria-label="Copy active insight"
              >
                {copied ? <Check aria-hidden="true" className="size-3.5 text-emerald-300" /> : <Clipboard aria-hidden="true" className="size-3.5" />}
              </button>
              <button
                data-qid={dismissQid}
                data-qs-action="LIVE_EVIDENCE_STAGE_DISMISS"
                title="Dismiss card"
                type="button"
                disabled={busy}
                onClick={() => onDismiss(card.card_id)}
                aria-label="Dismiss card"
              >
                <X aria-hidden="true" className="size-3.5" />
              </button>
            </div>
          </div>
          <p>{answer}</p>
        </section>

        <section className="evidence-section" aria-label="Reasoning and source evidence">
          <div className="evidence-box">
            <h3>
              <ShieldAlert aria-hidden="true" className="size-3.5" />
              Use With Caution
            </h3>
            <p>{card.qualifier}</p>
          </div>
          <div className="evidence-box">
            <h3>
              <DatabaseZap aria-hidden="true" className="size-3.5" />
              Evidence
            </h3>
            <p>{evidence}</p>
          </div>
          <div className="evidence-box source-box">
            <h3>
              <SearchCode aria-hidden="true" className="size-3.5" />
              Source
            </h3>
            <code>{sourceLabel(card)}</code>
            {primarySource?.excerpt ? <pre>{primarySource.excerpt}</pre> : null}
          </div>
          <div className="evidence-box">
            <h3>
              <Code2 aria-hidden="true" className="size-3.5" />
              Confidence
            </h3>
            <p>{Math.round(card.confidence * 100)}% evidence confidence from {card.sources.length} source(s).</p>
          </div>
        </section>
      </div>
    </main>
  );
}

export function LiveMeetingSurface(props: LiveMeetingSurfaceProps) {
  return (
    <div className="meeting-shell">
      <QuietHeader {...props} />
      <div className="app-layout">
        <LiveCardStream cards={props.cards} selectedCardId={props.selectedCardId} onSelectCard={props.onSelectCard} />
        <ActiveInsightStage card={props.activeCard} busy={props.busy} onPin={props.onPin} onDismiss={props.onDismiss} />
      </div>
    </div>
  );
}
