import { AlertTriangle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { DevPanel } from "@/components/DevPanel";
import { FlashCard } from "@/components/FlashCard";
import { PendingClarification } from "@/components/PendingClarification";
import { KeyboardShortcutsModal } from "@/components/KeyboardShortcutsModal";
import { MemoryVault } from "@/components/MemoryVault";
import { QuestionTimeline } from "@/components/QuestionTimeline";
import { StatusStrip } from "@/components/StatusStrip";
import { TranscriptDrawer } from "@/components/TranscriptDrawer";
import { useHUDHotkeys } from "@/hooks/useHUDHotkeys";
import { useLiveEvidence } from "@/hooks/useLiveEvidence";
import { activeCardForSelection, visibleCardOrder, type CardSelection } from "@/lib/cardSelection";

export default function App() {
  const { snapshot, connected, error, busy, actions } = useLiveEvidence();
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [vaultOpen, setVaultOpen] = useState(false);
  const [isFlipped, setIsFlipped] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [devOpen, setDevOpen] = useState(false);
  const [selection, setSelection] = useState<CardSelection>({ cardId: null, mode: "auto" });

  // Scanner-owned question identity (3-agent architecture) makes timeline
  // dedupe/legitimacy by construction; the former timelineCards() UI band-aid
  // over-filtered scanner-approved questions and is retired.
  // Follow-ups render inside their parent's flashcard, never as separate
  // timeline entries the human has to hunt for.
  const { visibleCards, followUpsByParent } = useMemo(() => {
    const ordered = visibleCardOrder(snapshot.cards);
    const parents = ordered.filter((card) => !card.parent_question_id);
    const byParent = new Map<string, typeof ordered>();
    for (const card of ordered) {
      if (!card.parent_question_id) continue;
      const bucket = byParent.get(card.parent_question_id) ?? [];
      bucket.push(card);
      byParent.set(card.parent_question_id, bucket);
    }
    return { visibleCards: parents, followUpsByParent: byParent };
  }, [snapshot.cards]);

  const activeCard = activeCardForSelection(visibleCards, selection);
  const pending = snapshot.pending_requirements?.find((item) => item.blocking && item.status === "unresolved" && item.clarification_id);

  useEffect(() => {
    if (!activeCard) {
      if (selection.mode !== "auto" || selection.cardId !== null) {
        setSelection({ cardId: null, mode: "auto" });
      }
      return;
    }
    if (
      selection.mode === "manual" &&
      selection.cardId &&
      !visibleCards.some((card) => card.card_id === selection.cardId)
    ) {
      setSelection({ cardId: null, mode: "auto" });
    }
  }, [activeCard, selection, visibleCards]);

  const selectRelativeCard = (direction: 1 | -1) => {
    if (visibleCards.length === 0) return;
    const index = Math.max(visibleCards.findIndex((card) => card.card_id === activeCard?.card_id), 0);
    const nextIndex = direction > 0 ? Math.min(index + 1, visibleCards.length - 1) : Math.max(index - 1, 0);
    setSelection({ cardId: visibleCards[nextIndex].card_id, mode: "manual" });
    setIsFlipped(false);
  };

  useHUDHotkeys([
    { key: "?", handler: () => setShortcutsOpen((value) => !value) },
    { key: "Cmd+\\", handler: () => setTranscriptOpen((value) => !value) },
    { key: "Ctrl+\\", handler: () => setTranscriptOpen((value) => !value) },
    { key: "ArrowDown", handler: () => selectRelativeCard(1) },
    { key: "j", handler: () => selectRelativeCard(1) },
    { key: "ArrowUp", handler: () => selectRelativeCard(-1) },
    { key: "k", handler: () => selectRelativeCard(-1) },
    { key: "Space", handler: () => activeCard && setIsFlipped((value) => !value) },
    { key: "p", handler: () => activeCard && void actions.pin(activeCard.card_id) },
    { key: "Escape", handler: () => activeCard && void actions.dismiss(activeCard.card_id) },
    { key: "d", handler: () => activeCard && void actions.dismiss(activeCard.card_id) },
  ]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[#090a0f] text-[var(--foreground)]">
      <StatusStrip
        session={snapshot.session}
        snapshot={snapshot}
        onOpenShortcuts={() => setShortcutsOpen(true)}
        onOpenDev={() => setDevOpen(true)}
        transcriptCount={snapshot.transcript.length}
        connected={connected}
        busy={busy}
        transcriptOpen={transcriptOpen}
        vaultOpen={vaultOpen}
        onToggleTranscript={() => setTranscriptOpen((value) => !value)}
        onToggleVault={() => setVaultOpen((value) => !value)}
        onStart={() => void actions.start()}
        onPause={() => void actions.pause()}
        onResume={() => void actions.resume()}
        onNewSession={() => void actions.newSession()}
        onStop={() => void actions.stop()}
      />

      <div className="relative flex flex-1 overflow-hidden">
        <QuestionTimeline
          cards={visibleCards}
          selectedCardId={activeCard?.card_id ?? null}
          onSelectCard={(cardId) => {
            setSelection({ cardId, mode: "manual" });
            setIsFlipped(false);
          }}
        />

        <main className="flex flex-1 flex-col overflow-hidden bg-[#090a0f]">
          {pending ? <PendingClarification key={`${snapshot.session.session_id}:${pending.requirement_id}`} requirement={pending} /> : null}
          <FlashCard
            card={activeCard ?? null}
            followUps={activeCard?.question_id ? (followUpsByParent.get(activeCard.question_id) ?? []) : []}
            isFlipped={isFlipped}
            onFlipToggle={() => setIsFlipped((value) => !value)}
            onTogglePin={(cardId) => void actions.pin(cardId)}
          />
        </main>
      </div>

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

      <KeyboardShortcutsModal isOpen={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />

      <DevPanel isOpen={devOpen} onClose={() => setDevOpen(false)} />

      <TranscriptDrawer
        open={transcriptOpen}
        transcript={snapshot.transcript}
        currentThread={snapshot.current_thread}
        onClose={() => setTranscriptOpen(false)}
      />
    </div>
  );
}
