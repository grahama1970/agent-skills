import { AudioLines, LockKeyhole, Radio } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { SessionControls } from "@/components/SessionControls";
import type { SessionInfo } from "@/types";

interface SessionHeaderProps {
  session: SessionInfo;
  connected: boolean;
  busy: boolean;
  onStart: () => void;
  onPause: () => void;
  onStop: () => void;
}

export function SessionHeader({
  session,
  connected,
  busy,
  onStart,
  onPause,
  onStop,
}: SessionHeaderProps) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.07] px-5 py-4 lg:px-7">
      <div className="flex items-center gap-3.5">
        <div className="grid size-11 place-items-center rounded-2xl border border-[var(--accent)]/25 bg-[var(--accent)]/10 shadow-[0_0_34px_rgba(62,211,194,0.08)]">
          <AudioLines aria-hidden="true" className="size-5 text-[var(--accent)]" />
        </div>
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-base font-semibold tracking-[-0.02em] text-[var(--foreground)]">
              Live Evidence
            </h1>
            <Badge variant={session.status === "listening" ? "default" : "muted"}>
              <Radio aria-hidden="true" className="size-2.5" />
              {session.status}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">
            Listen to the person. Let the system find the proof.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="hidden items-center gap-2 rounded-full border border-white/[0.07] bg-black/15 px-3 py-1.5 text-[11px] text-[var(--muted-foreground)] sm:flex">
          <span className={`size-1.5 rounded-full ${connected ? "bg-emerald-300" : "bg-amber-300"}`} />
          {connected ? "Local stream connected" : "Reconnecting"}
        </div>
        <div className="hidden items-center gap-1.5 text-[11px] text-[var(--muted-foreground)] lg:flex">
          <LockKeyhole aria-hidden="true" className="size-3.5 text-[var(--accent)]" />
          Raw audio is not retained
        </div>
        <SessionControls
          status={session.status}
          busy={busy}
          onStart={onStart}
          onPause={onPause}
          onStop={onStop}
        />
      </div>
    </header>
  );
}
