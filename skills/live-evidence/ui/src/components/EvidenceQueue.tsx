import { History } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { EvidenceCard } from "@/types";

export function EvidenceQueue({ cards }: { cards: EvidenceCard[] }) {
  const history = cards.filter((card) => !card.dismissed).slice(1, 4);
  if (history.length === 0) return null;

  return (
    <section className="mt-3" aria-label="Recent evidence cards">
      <div className="mb-2 flex items-center gap-2 px-1 text-[10px] font-semibold uppercase tracking-[0.17em] text-[var(--muted-foreground)]">
        <History aria-hidden="true" className="size-3" />
        Recent cards
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        {history.map((card) => (
          <article
            key={card.card_id}
            className="min-w-0 rounded-xl border border-white/[0.07] bg-white/[0.028] px-3 py-2.5"
          >
            <div className="flex items-center justify-between gap-2">
              <Badge variant="muted">{card.thread}</Badge>
              <span className="text-[10px] text-[var(--muted-foreground)]">
                {Math.round(card.confidence * 100)}%
              </span>
            </div>
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--foreground)]/82">
              {card.talking_point}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
