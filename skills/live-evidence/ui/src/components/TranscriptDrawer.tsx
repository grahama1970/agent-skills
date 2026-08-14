import { MessageSquareText, X } from "lucide-react";

import { useRegisterAction } from "@/hooks/useRegisterAction";
import { formatClock } from "@/lib/utils";
import type { TranscriptEvent } from "@/types";

interface TranscriptDrawerProps {
  open: boolean;
  transcript: TranscriptEvent[];
  currentThread: string;
  onClose: () => void;
}

export function TranscriptDrawer({ open, transcript, currentThread, onClose }: TranscriptDrawerProps) {
  useRegisterAction({
    element_id: "live-evidence:transcript:close",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_TRANSCRIPT_CLOSE",
    label: "Close transcript drawer",
    description: "Close the transcript drawer and return to the Vault surface",
  });

  const visible = transcript.slice(-60).reverse();

  return (
    <aside
      className={`fixed bottom-4 left-4 z-40 flex max-h-[76vh] w-[min(34rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border border-white/10 bg-[#071012]/95 shadow-2xl shadow-black/40 backdrop-blur-xl transition duration-150 ${
        open ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-2 opacity-0"
      }`}
      aria-label="Live transcript drawer"
      aria-hidden={!open}
    >
      <div className="flex items-start justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <MessageSquareText aria-hidden="true" className="size-4 text-cyan-300" />
            <h2 className="text-sm font-semibold text-white">Transcript</h2>
          </div>
          <p className="mt-1 truncate text-xs text-slate-400">{currentThread}</p>
        </div>
        <button
          data-qid="live-evidence:transcript:close"
          data-qs-action="LIVE_EVIDENCE_TRANSCRIPT_CLOSE"
          title="Close transcript drawer"
          type="button"
          className="grid size-11 shrink-0 place-items-center rounded-lg text-slate-400 transition hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/35"
          onClick={onClose}
          aria-label="Close transcript drawer"
          tabIndex={open ? 0 : -1}
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3" aria-live="polite">
        {visible.length === 0 ? (
          <div className="grid min-h-44 place-items-center px-6 text-center text-xs leading-5 text-slate-400">
            No transcript events have arrived from the local listener.
          </div>
        ) : (
          visible.map((event) => (
            <article
              key={event.event_id}
              className={`mb-2 rounded-lg border px-3 py-2 ${
                event.speaker === "interviewer"
                  ? "border-white/10 bg-white/[0.04]"
                  : "border-cyan-300/15 bg-cyan-300/[0.055]"
              } ${event.kind === "interim" ? "opacity-60" : "opacity-100"}`}
            >
              <div className="flex items-center justify-between gap-2 text-[10px] uppercase text-slate-500">
                <span>{event.speaker === "graham" ? "You" : event.speaker}</span>
                <span>{formatClock(event.created_at)}</span>
              </div>
              <p className="mt-1.5 text-xs leading-5 text-slate-200">{event.text}</p>
            </article>
          ))
        )}
      </div>
    </aside>
  );
}
