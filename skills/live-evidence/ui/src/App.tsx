import { AlertTriangle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { LiveMeetingSurface } from "@/components/LiveMeetingSurface";
import { MemoryVault } from "@/components/MemoryVault";
import { TranscriptDrawer } from "@/components/TranscriptDrawer";
import { useLiveEvidence } from "@/hooks/useLiveEvidence";

export default function App() {
  const { snapshot, connected, error, busy, actions } = useLiveEvidence();
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [vaultOpen, setVaultOpen] = useState(false);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);

  const visibleCards = useMemo(() => {
    return snapshot.cards
      .filter((card) => !card.dismissed)
      .sort((left, right) => {
        if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
        return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
      });
  }, [snapshot.cards]);

  const activeCard = visibleCards.find((card) => card.card_id === selectedCardId) ?? visibleCards[0];

  useEffect(() => {
    if (!activeCard) {
      setSelectedCardId(null);
      return;
    }
    if (!selectedCardId || !visibleCards.some((card) => card.card_id === selectedCardId)) {
      setSelectedCardId(activeCard.card_id);
    }
  }, [activeCard, selectedCardId, visibleCards]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const activeElement = document.activeElement;
      if (
        activeElement instanceof HTMLInputElement ||
        activeElement instanceof HTMLTextAreaElement ||
        activeElement instanceof HTMLSelectElement
      ) {
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "\\") {
        event.preventDefault();
        setTranscriptOpen((value) => !value);
        return;
      }
      if (event.key === "ArrowDown" || event.key === "j") {
        event.preventDefault();
        if (visibleCards.length === 0) return;
        const index = Math.max(visibleCards.findIndex((card) => card.card_id === activeCard?.card_id), 0);
        setSelectedCardId(visibleCards[Math.min(index + 1, visibleCards.length - 1)].card_id);
        return;
      }
      if (event.key === "ArrowUp" || event.key === "k") {
        event.preventDefault();
        if (visibleCards.length === 0) return;
        const index = Math.max(visibleCards.findIndex((card) => card.card_id === activeCard?.card_id), 0);
        setSelectedCardId(visibleCards[Math.max(index - 1, 0)].card_id);
        return;
      }
      if (event.key === " ") {
        event.preventDefault();
        if (activeCard) void actions.pin(activeCard.card_id);
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        document.getElementById("active-insight-stage")?.focus();
        return;
      }
      if (event.key === "Escape" || event.key === "d") {
        event.preventDefault();
        if (activeCard) {
          void actions.dismiss(activeCard.card_id);
          return;
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [actions, activeCard, visibleCards]);

  return (
    <div className="min-h-screen bg-[#090a0f] text-[var(--foreground)]">
      <LiveMeetingSurface
        cards={visibleCards}
        activeCard={activeCard}
        selectedCardId={activeCard?.card_id ?? null}
        connected={connected}
        busy={busy}
        currentThread={snapshot.current_thread}
        lanes={snapshot.lanes}
        session={snapshot.session}
        transcriptCount={snapshot.transcript.length}
        vaultOpen={vaultOpen}
        onSelectCard={setSelectedCardId}
        onPin={(cardId) => void actions.pin(cardId)}
        onDismiss={(cardId) => {
          void actions.dismiss(cardId);
        }}
        onOpenTranscript={() => setTranscriptOpen(true)}
        onToggleVault={() => setVaultOpen((value) => !value)}
        onStart={() => void actions.start()}
        onPause={() => void actions.pause()}
        onStop={() => void actions.stop()}
      />

      {error ? (
        <div
          role="status"
          className="fixed bottom-4 left-1/2 z-[60] flex -translate-x-1/2 items-center gap-2 rounded-lg border border-amber-300/20 bg-amber-300/[0.10] px-3 py-2 text-xs text-amber-100 shadow-2xl shadow-black/40"
        >
          <AlertTriangle aria-hidden="true" className="size-3.5" />
          {error}
        </div>
      ) : null}

      {vaultOpen ? (
        <div className="vault-overlay">
          <div className="vault-panel">
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
        </div>
      ) : null}

      <TranscriptDrawer
        open={transcriptOpen}
        transcript={snapshot.transcript}
        currentThread={snapshot.current_thread}
        onClose={() => setTranscriptOpen(false)}
      />
    </div>
  );
}
