import { Archive, Eye, EyeOff, FileText, Maximize2, MessageCircle, Mic, MicOff, Minimize2, Radio } from "lucide-react";

import { SessionControls } from "@/components/SessionControls";
import { useRegisterAction } from "@/hooks/useRegisterAction";
import type { LaneActivity, SessionInfo } from "@/types";

interface MeetingHUDHeaderProps {
  connected: boolean;
  currentThread: string;
  lanes: LaneActivity[];
  session: SessionInfo;
  transcriptCount: number;
  vaultOpen: boolean;
  busy: boolean;
  compactMode: boolean;
  peekMode: boolean;
  onOpenTranscript: () => void;
  onToggleVault: () => void;
  onStart: () => void;
  onPause: () => void;
  onStop: () => void;
  onToggleCompact: () => void;
  onTogglePeek: () => void;
}

function laneTone(state: LaneActivity["state"]): string {
  if (state === "ok") return "bg-emerald-300";
  if (state === "running") return "bg-sky-300 animate-pulse";
  if (state === "degraded" || state === "error") return "bg-amber-300";
  if (state === "disabled") return "bg-slate-600";
  return "bg-slate-400";
}

export function sessionModeLabel(session: SessionInfo): string {
  // The active purpose and any disabled assistive capability are surfaced
  // prominently (#1449): the human must always see which authority contract
  // this session runs under, and PRACTICE sessions must be visibly practice.
  const disabled: string[] = [];
  const policy = session.policy;
  if (policy) {
    if (!policy.candidate_answer_generation) disabled.push("no answers");
    if (!policy.external_search) disabled.push("no web");
    if (!policy.debugger_invocation) disabled.push("no debugger");
    if (!policy.voice_output) disabled.push("no voice");
  }
  const mode = session.practice_only ? "REHEARSAL · PRACTICE ONLY" : (session.purpose || "meeting").replace(/_/g, " ").toUpperCase();
  return disabled.length ? `${mode} · ${disabled.join(" · ")}` : mode;
}

function liveStatusLabel(session: SessionInfo, connected: boolean): string {
  if (connected && session.status === "listening") return `Listening · ${sessionModeLabel(session)}`;
  // An armed session exists but consent was never confirmed, so no audio
  // capture is authorized. Saying "Listening" here would misrepresent both what
  // the system is doing and what the human agreed to.
  if (connected && session.status === "armed") return "Armed · consent needed";
  if (!connected) return "Reconnecting";
  return session.status;
}

export function SpeechTeleprompterBar({ prompt }: { prompt: string }) {
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

export function MeetingHUDHeader({
  connected,
  currentThread,
  lanes,
  session,
  transcriptCount,
  vaultOpen,
  busy,
  compactMode,
  peekMode,
  onOpenTranscript,
  onToggleVault,
  onStart,
  onPause,
  onStop,
  onToggleCompact,
  onTogglePeek,
}: MeetingHUDHeaderProps) {
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
  useRegisterAction({
    element_id: "live-evidence:meeting:toggle-definition-peek",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_MEETING_TOGGLE_DEFINITION_PEEK",
    label: "Toggle definition peek",
    description: "Show or hide semantic term definition popovers with Shift+P",
  });

  return (
    <header className="hud-header">
      <div className="flex min-w-0 items-center gap-3">
        <div className="live-pill">
          <span className="pulse-dot" />
          {liveStatusLabel(session, connected)}
        </div>
        <div className="hidden items-center gap-2 rounded-full border border-slate-800 bg-slate-900 px-3 py-1 text-[11px] sm:flex" aria-label="Agent status">
          <div className="flex items-center gap-1.5 border-r border-slate-800 pr-2">
            <span className="relative flex h-2 w-2">
              {listening ? <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" /> : null}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${listening ? "bg-emerald-500" : "bg-slate-600"}`} />
            </span>
            <span className="font-medium text-slate-400">Detector:</span>
            <span className={`font-mono font-semibold ${listening ? "text-emerald-400" : "text-slate-500"}`}>
              {listening ? "LISTENING" : session.status.toUpperCase()}
            </span>
          </div>
          <div className="flex items-center gap-1.5 pl-1">
            <span className="relative flex h-2 w-2">
              {busy ? <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" /> : null}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${busy ? "bg-amber-500" : "bg-slate-600"}`} />
            </span>
            <span className="font-medium text-slate-400">Solver:</span>
            <span className={`font-mono font-semibold ${busy ? "text-amber-400" : "text-slate-500"}`}>
              {busy ? "GENERATING…" : "IDLE"}
            </span>
          </div>
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
        <span>|</span>
        <kbd>Shift+P</kbd> Peek
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
        <button
          type="button"
          data-qid="live-evidence:meeting:toggle-definition-peek"
          data-qs-action="LIVE_EVIDENCE_MEETING_TOGGLE_DEFINITION_PEEK"
          title="Toggle term definition peek"
          className={`quiet-icon-button ${peekMode ? "is-active" : ""}`}
          onClick={onTogglePeek}
          aria-label={peekMode ? "Hide term definition popovers" : "Show term definition popovers"}
        >
          {peekMode ? <EyeOff aria-hidden="true" className="size-3.5" /> : <Eye aria-hidden="true" className="size-3.5" />}
        </button>
        <SessionControls status={session.status} busy={busy} onStart={onStart} onPause={onPause} onStop={onStop} />
      </div>
    </header>
  );
}
