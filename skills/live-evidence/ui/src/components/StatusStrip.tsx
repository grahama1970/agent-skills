import { Activity, Clock, Database, Download, Keyboard, Pause, Play, Settings, Terminal, User } from "lucide-react";

import { useRegisterAction } from "@/hooks/useRegisterAction";
import { downloadSessionMarkdown } from "@/lib/exportSession";
import type { AppSnapshot } from "@/types";
import { useEffect, useState } from "react";

import type { SessionInfo } from "@/types";

interface StatusStripProps {
  session: SessionInfo;
  snapshot: AppSnapshot;
  onOpenShortcuts: () => void;
  onOpenDev: () => void;
  transcriptCount?: number;
  connected: boolean;
  busy: boolean;
  transcriptOpen: boolean;
  vaultOpen: boolean;
  onToggleTranscript: () => void;
  onToggleVault: () => void;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onNewSession: () => void;
  onStop: () => void;
}

function formatElapsed(startedAt?: string | null): string {
  if (!startedAt) return "--:--";
  const elapsed = Math.max(0, Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000));
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

export function StatusStrip({
  session,
  snapshot,
  onOpenShortcuts,
  onOpenDev,
  transcriptCount = 0,
  connected,
  busy,
  transcriptOpen,
  vaultOpen,
  onToggleTranscript,
  onToggleVault,
  onStart,
  onPause,
  onResume,
  onNewSession,
}: StatusStripProps) {
  const [, forceTick] = useState(0);
  useRegisterAction({
    element_id: "status-strip-controls",
    app: "live-evidence",
    action: "operate_session_strip",
    label: "Use session strip controls",
    description: "Start, pause, stop, export, or open Live Evidence panels.",
  });
  useEffect(() => {
    const timer = window.setInterval(() => forceTick((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const listening = session.status === "listening";
  const listenerLevel = Number(snapshot.listener?.level ?? 0);
  const hearingAudio = listening && listenerLevel > 8;
  const listenerName = snapshot.listener?.device?.includes("bluez")
    ? "Jabra (Bluetooth)"
    : snapshot.listener?.device?.split(".").slice(-1)[0];

  return (
    <header className="flex h-8 items-center justify-between overflow-hidden border-b border-gray-800/80 bg-[#0d0e15] px-2 text-xs text-gray-400 select-none sm:px-3">
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <div className="flex items-center gap-1.5 font-medium text-gray-200">
          <Activity className="size-3.5 text-indigo-400" aria-hidden="true" />
          <span className="rounded border border-indigo-800/50 bg-indigo-950/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-indigo-300">
            {session.status}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <span
            className={`size-2 rounded-full ${
              listening
                ? "animate-pulse bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
                : connected
                  ? "bg-amber-400"
                  : "bg-red-500"
            }`}
          />
          <span className="capitalize text-gray-300">
            {listening ? "listening" : connected ? session.status : "disconnected"}
          </span>
        </div>

        <div className="hidden min-w-0 items-center gap-1 truncate text-gray-400 md:flex">
          <User className="size-3 shrink-0 text-gray-500" aria-hidden="true" />
          <span className="truncate text-[11px]">{session.profile_name}</span>
        </div>

        <div className="hidden shrink-0 items-center gap-1 font-mono text-[11px] text-gray-400 sm:flex">
          <Clock className="size-3 shrink-0 text-gray-500" aria-hidden="true" />
          <span>{formatElapsed(session.started_at)}</span>
        </div>
        {snapshot.listener?.device ? (
          <div
            className={`flex shrink-0 items-center gap-2 rounded border px-2 py-0.5 font-mono text-[10px] transition-colors ${
              hearingAudio
                ? "border-emerald-500/50 bg-emerald-950/40 text-emerald-200 shadow-[0_0_12px_rgba(16,185,129,0.25)]"
                : "border-amber-700/50 bg-amber-950/20 text-amber-200"
            }`}
            title={`Capturing from ${snapshot.listener.device} (${snapshot.listener.resolve_reason}); level ${listenerLevel}`}
            data-qid="listener-level"
          >
            <span className="hidden max-w-[10rem] truncate lg:inline">{listenerName}</span>
            <span className={`font-semibold tracking-wide ${hearingAudio ? "text-emerald-200" : "text-amber-200"}`}>
              {hearingAudio ? "HEARING" : "SILENT"}
            </span>
            <span className="relative flex size-7 items-center justify-center rounded-full border border-current/50 bg-black/30" aria-label="Input level">
              <span className={`absolute size-full rounded-full ${hearingAudio ? "animate-ping bg-emerald-400/30" : "bg-amber-900/40"}`} />
              {[0, 1, 2].map((i) => {
                const active = listenerLevel > [8, 25, 55][i];
                return (
                  <span
                    key={i}
                    className={`mx-[1px] w-[4px] rounded-full transition-all duration-100 ${active ? "bg-emerald-200 shadow-[0_0_8px_rgba(110,231,183,1)]" : "bg-gray-700"}`}
                    style={{ height: `${active ? 10 + i * 4 + Math.min(10, listenerLevel / 10) : 5 + i * 2}px` }}
                  />
                );
              })}
            </span>
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        <div className="flex items-center gap-0.5 rounded border border-gray-800 bg-[#13151f] p-0.5">
          {/* Play/Pause toggle: listening pauses; paused resumes IN PLACE
              (same session, consent kept); idle/stopped starts. */}
          <button
            type="button"
            data-qid={listening ? "status-pause-session" : "status-start-session"}
            data-qs-action={listening ? "pause_session" : session.status === "paused" ? "resume_session" : "start_session"}
            onClick={listening ? onPause : session.status === "paused" ? onResume : onStart}
            disabled={busy}
            className={`flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-40 ${
              listening ? "text-amber-300 hover:text-amber-200" : "text-emerald-300 hover:text-emerald-200"
            }`}
            title={listening ? "Pause session" : session.status === "paused" ? "Resume session" : "Start session"}
          >
            {listening ? <Pause className="size-3" aria-hidden="true" /> : <Play className="size-3" aria-hidden="true" />}
            {listening ? "Pause" : "Play"}
          </button>
          <button
            type="button"
            data-qid="status-new-session"
            data-qs-action="new_session"
            onClick={onNewSession}
            disabled={busy}
            className="rounded px-2 py-1 text-[11px] font-medium text-slate-400 transition-colors hover:text-slate-200 disabled:opacity-40"
            title="Archive this session and start a new one"
          >
            New
          </button>
        </div>

        <button
          type="button"
          data-qid="status-export-session"
          data-qs-action="export_session"
          onClick={() => downloadSessionMarkdown(snapshot)}
          className="flex cursor-pointer items-center gap-1 rounded border border-slate-700/80 bg-[#161826] px-2 py-0.5 text-[11px] font-medium text-slate-200 transition-colors hover:bg-[#202336]"
          title="Export session to Markdown"
        >
          <Download className="size-3 text-emerald-400" aria-hidden="true" />
          <span className="hidden sm:inline">Export</span>
        </button>

        <button
          type="button"
          data-qid="status-open-dev"
          data-qs-action="open_dev_panel"
          onClick={onOpenDev}
          className="flex cursor-pointer items-center gap-1 rounded border border-gray-800 bg-[#141622] px-2 py-0.5 text-[11px] text-gray-300 transition-colors hover:bg-[#1b1e2e] hover:text-gray-100"
          title="Settings: agent prompts, models, architecture"
        >
          <Settings className="size-3.5 text-indigo-400" aria-hidden="true" />
          <span className="hidden sm:inline">Settings</span>
        </button>

        <button
          type="button"
          data-qid="status-open-shortcuts"
          data-qs-action="open_shortcuts"
          onClick={onOpenShortcuts}
          className="cursor-pointer rounded border border-gray-800 bg-[#141622] p-1 text-gray-400 transition-colors hover:bg-[#1b1e2e] hover:text-gray-100"
          title="Keyboard shortcuts [?]"
        >
          <Keyboard className="size-3.5 text-indigo-400" aria-hidden="true" />
        </button>

        <button
          type="button"
          data-qid="status-toggle-vault"
          data-qs-action="toggle_vault"
          onClick={onToggleVault}
          className={`flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] transition-colors ${
            vaultOpen
              ? "border-indigo-700/60 bg-indigo-950/60 text-indigo-200"
              : "border-gray-800 bg-[#171924] text-gray-300 hover:bg-[#202332]"
          }`}
          title="Toggle Memory Vault"
        >
          <Database className="size-3 text-indigo-400" aria-hidden="true" />
          <span className="hidden sm:inline">Vault</span>
        </button>

        <button
          type="button"
          data-qid="status-toggle-transcript"
          data-qs-action="toggle_transcript"
          onClick={onToggleTranscript}
          className={`flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] transition-colors ${
            transcriptOpen
              ? "border-indigo-700/60 bg-indigo-950/60 text-indigo-200"
              : "border-gray-800 bg-[#171924] text-gray-300 hover:bg-[#202332]"
          }`}
          title="Toggle raw transcript drawer"
        >
          <Terminal className="size-3 text-indigo-400" aria-hidden="true" />
          <span className="hidden sm:inline">STT</span>
          {transcriptCount > 0 ? (
            <span className="rounded-full bg-gray-800 px-1 font-mono text-[9px] text-gray-400">{transcriptCount}</span>
          ) : null}
        </button>
      </div>
    </header>
  );
}
