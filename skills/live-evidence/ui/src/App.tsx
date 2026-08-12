import { AlertTriangle } from "lucide-react";

import { CurrentThread } from "@/components/CurrentThread";
import { EmptyEvidence } from "@/components/EmptyEvidence";
import { EvidenceCardView } from "@/components/EvidenceCardView";
import { EvidenceQueue } from "@/components/EvidenceQueue";
import { ManualSearch } from "@/components/ManualSearch";
import { RetrievalRail } from "@/components/RetrievalRail";
import { SessionHeader } from "@/components/SessionHeader";
import { TranscriptPanel } from "@/components/TranscriptPanel";
import { useLiveEvidence } from "@/hooks/useLiveEvidence";

export default function App() {
  const { snapshot, connected, error, busy, actions } = useLiveEvidence();
  const visibleCards = snapshot.cards.filter((card) => !card.dismissed);
  const currentCard = visibleCards.find((card) => card.pinned) ?? visibleCards[0];

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_18%_0%,rgba(62,211,194,0.08),transparent_32%),radial-gradient(circle_at_90%_100%,rgba(212,168,83,0.055),transparent_30%)]" />
      <div className="relative flex min-h-screen flex-col">
        <SessionHeader
          session={snapshot.session}
          connected={connected}
          busy={busy}
          onStart={() => void actions.start()}
          onPause={() => void actions.pause()}
          onStop={() => void actions.stop()}
        />

        {error ? (
          <div
            role="status"
            className="mx-5 mt-3 flex items-center gap-2 rounded-xl border border-amber-300/15 bg-amber-300/[0.055] px-3 py-2 text-xs text-amber-100 lg:mx-7"
          >
            <AlertTriangle aria-hidden="true" className="size-3.5" />
            {error}
          </div>
        ) : null}

        <main className="grid min-h-0 flex-1 gap-3 p-3 sm:p-4 lg:grid-cols-[minmax(230px,0.72fr)_minmax(500px,1.72fr)_minmax(260px,0.82fr)] lg:p-5 xl:gap-4 xl:p-6">
          <aside className="flex min-h-[420px] flex-col gap-3 lg:min-h-0" aria-label="Conversation context">
            <CurrentThread thread={snapshot.current_thread} />
            <TranscriptPanel transcript={snapshot.transcript} />
          </aside>

          <section className="flex min-h-[480px] min-w-0 flex-col lg:min-h-0" aria-label="Current evidence">
            {currentCard ? (
              <EvidenceCardView
                card={currentCard}
                busy={busy}
                onPin={(cardId) => void actions.pin(cardId)}
                onDismiss={(cardId) => void actions.dismiss(cardId)}
              />
            ) : (
              <EmptyEvidence />
            )}
            <EvidenceQueue cards={visibleCards} />
          </section>

          <aside className="flex min-h-0 flex-col gap-3" aria-label="Retrieval controls and health">
            <RetrievalRail lanes={snapshot.lanes} />
            <ManualSearch busy={busy} onSearch={(query, lane) => void actions.search(query, lane)} />
            <div className="rounded-xl border border-white/[0.06] bg-black/10 px-3 py-2.5 text-[10px] leading-4 text-[var(--muted-foreground)]">
              <span className="font-semibold text-[var(--foreground)]/80">Boundary:</span> evidence cards restore context; they do not authorize disclosure or prove a model-generated claim.
            </div>
          </aside>
        </main>
      </div>
    </div>
  );
}
