import { AlertTriangle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { InsightsPanel } from "@/components/InsightsPanel";
import { LiveMeetingSurface } from "@/components/LiveMeetingSurface";
import { MemoryVault } from "@/components/MemoryVault";
import { TranscriptDrawer } from "@/components/TranscriptDrawer";
import { useHUDHotkeys } from "@/hooks/useHUDHotkeys";
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

  const selectRelativeCard = (direction: 1 | -1) => {
    if (visibleCards.length === 0) return;
    const index = Math.max(visibleCards.findIndex((card) => card.card_id === activeCard?.card_id), 0);
    const nextIndex = direction > 0 ? Math.min(index + 1, visibleCards.length - 1) : Math.max(index - 1, 0);
    setSelectedCardId(visibleCards[nextIndex].card_id);
  };

  useHUDHotkeys([
    { key: "Cmd+\\", handler: () => setTranscriptOpen((value) => !value) },
    { key: "Ctrl+\\", handler: () => setTranscriptOpen((value) => !value) },
    { key: "ArrowDown", handler: () => selectRelativeCard(1) },
    { key: "j", handler: () => selectRelativeCard(1) },
    { key: "ArrowUp", handler: () => selectRelativeCard(-1) },
    { key: "k", handler: () => selectRelativeCard(-1) },
    { key: "Space", handler: () => activeCard && void actions.pin(activeCard.card_id) },
    { key: "Enter", handler: () => document.getElementById("active-insight-stage")?.focus() },
    { key: "Escape", handler: () => activeCard && void actions.dismiss(activeCard.card_id) },
    { key: "d", handler: () => activeCard && void actions.dismiss(activeCard.card_id) },
    {
      key: "Shift+C",
      handler: () => {
        const button = document.querySelector<HTMLButtonElement>('[data-qs-action="LIVE_EVIDENCE_SOLUTION_COPY_CODE"]:not(:disabled)');
        button?.click();
      },
    },
  ]);

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

      <InsightsPanel />

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
