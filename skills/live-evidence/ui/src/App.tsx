import { AlertTriangle, MessageSquareText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AmbientHUD } from "@/components/AmbientHUD";
import { MemoryVault } from "@/components/MemoryVault";
import { SessionControls } from "@/components/SessionControls";
import { TranscriptDrawer } from "@/components/TranscriptDrawer";
import { useLiveEvidence } from "@/hooks/useLiveEvidence";
import { useRegisterAction } from "@/hooks/useRegisterAction";

export default function App() {
  const { snapshot, connected, error, busy, actions } = useLiveEvidence();
  const [hiddenHudCards, setHiddenHudCards] = useState<Set<string>>(new Set());
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  const activeHudCards = useMemo(() => {
    const sorted = snapshot.cards
      .filter((card) => !card.dismissed && !hiddenHudCards.has(card.card_id))
      .sort((left, right) => {
        if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
        return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
      });
    return sorted.slice(0, 2);
  }, [hiddenHudCards, snapshot.cards]);

  useRegisterAction({
    element_id: "live-evidence:transcript:toggle",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_TRANSCRIPT_TOGGLE",
    label: "Toggle transcript drawer",
    description: "Open or close the live transcript drawer during a call",
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "\\") {
        event.preventDefault();
        setTranscriptOpen((value) => !value);
      }
      if (event.key === "Escape") {
        setHiddenHudCards((current) => {
          const next = new Set(current);
          activeHudCards.forEach((card) => next.add(card.card_id));
          return next;
        });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeHudCards]);

  return (
    <div className="min-h-screen bg-[#060b0d] text-[var(--foreground)]">
      <main className="min-h-screen px-4 py-4 sm:px-5 lg:px-7 lg:py-6">
        <div className="mx-auto flex max-w-7xl flex-col gap-4">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] pb-4 pr-0 lg:pr-96">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-base font-semibold text-white">Live Evidence</h1>
                <span className="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-100">
                  {snapshot.session.status}
                </span>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] text-slate-300">
                  {connected ? "stream connected" : "stream reconnecting"}
                </span>
              </div>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">
                Local call companion for surfacing Memory and source evidence while audio is flowing.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                data-qid="live-evidence:transcript:toggle"
                data-qs-action="LIVE_EVIDENCE_TRANSCRIPT_TOGGLE"
                title="Toggle transcript drawer"
                type="button"
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.045] px-3 text-xs text-slate-200 transition hover:border-white/20 hover:bg-white/[0.075] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/35"
                onClick={() => setTranscriptOpen((value) => !value)}
              >
                <MessageSquareText aria-hidden="true" className="size-3.5 text-cyan-300" />
                Transcript
              </button>
              <SessionControls
                status={snapshot.session.status}
                busy={busy}
                onStart={() => void actions.start()}
                onPause={() => void actions.pause()}
                onStop={() => void actions.stop()}
              />
            </div>
          </header>

          {error ? (
            <div
              role="status"
              className="flex items-center gap-2 rounded-lg border border-amber-300/20 bg-amber-300/[0.08] px-3 py-2 text-xs text-amber-100 lg:mr-96"
            >
              <AlertTriangle aria-hidden="true" className="size-3.5" />
              {error}
            </div>
          ) : null}

          <MemoryVault
            cards={snapshot.cards}
            transcript={snapshot.transcript}
            lanes={snapshot.lanes}
            session={snapshot.session}
            currentThread={snapshot.current_thread}
            busy={busy}
            onSearch={(query, lane) => void actions.search(query, lane)}
          />
        </div>
      </main>

      <AmbientHUD
        cards={activeHudCards}
        connected={connected}
        status={snapshot.session.status}
        onDismiss={(cardId) => {
          setHiddenHudCards((current) => new Set(current).add(cardId));
        }}
      />
      <TranscriptDrawer
        open={transcriptOpen}
        transcript={snapshot.transcript}
        currentThread={snapshot.current_thread}
        onClose={() => setTranscriptOpen(false)}
      />
    </div>
  );
}
