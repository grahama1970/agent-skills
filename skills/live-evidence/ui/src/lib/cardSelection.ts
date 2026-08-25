import type { EvidenceCard } from "@/types";

export type CardSelection = {
  cardId: string | null;
  mode: "auto" | "manual";
};

export function visibleCardOrder(cards: EvidenceCard[]): EvidenceCard[] {
  const visible = cards.filter((card) => !card.dismissed);
  const pinned = visible.filter((card) => card.pinned);
  const unpinned = visible.filter((card) => !card.pinned);
  return [...pinned, ...unpinned];
}

export function activeCardForSelection(
  cards: EvidenceCard[],
  selection: CardSelection,
): EvidenceCard | undefined {
  if (selection.mode === "manual" && selection.cardId) {
    const selected = cards.find((card) => card.card_id === selection.cardId);
    if (selected) return selected;
  }
  return cards[0];
}
