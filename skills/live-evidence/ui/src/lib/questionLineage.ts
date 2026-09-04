import type { EvidenceCard } from "@/types";

/**
 * The resolver refines a question as more speech arrives, publishing each
 * refinement as a NEW card with a grown thread ("Which · nodes" ->
 * "Which · nodes · parallel · trend" -> "Which · nodes · parallel ·
 * transitions · require"). The timeline must show one entry per evolving
 * question (its latest refinement), not the whole hypothesis history, and it
 * must not show statement/closing-remark cards that make it read like a
 * transcript.
 */

const LINEAGE_WINDOW_MS = 120_000;

const QUESTION_LEADS = new Set([
  "which", "what", "how", "why", "when", "where", "who", "whose",
  "should", "could", "would", "can", "will", "do", "does", "did",
  "is", "are", "was", "were", "have", "has",
]);

const TASK_LEADS = new Set([
  "explain", "describe", "propose", "design", "walk", "implement", "build",
  "compare", "define", "produce", "sketch", "outline", "start", "draft",
  "estimate", "prove", "show", "write", "tell",
]);

function threadTokens(card: EvidenceCard): Set<string> {
  return new Set(
    (card.thread || "")
      .split("·")
      .map((token) => token.trim().toLowerCase())
      .filter((token) => token.length > 0),
  );
}

const LINEAGE_OVERLAP_RATIO = 0.6;

/**
 * ASR hypotheses mutate while a question grows ("Which trend?" corrects to
 * "which transitions require"), so refinement lineage is overlap-based, not
 * strict subset: a smaller card belongs to a richer card's lineage when most
 * of its tokens survive into the richer refinement.
 */
function isRefinedBy(smaller: Set<string>, larger: Set<string>): boolean {
  if (smaller.size === 0 || smaller.size >= larger.size) return false;
  let shared = 0;
  for (const token of smaller) {
    if (larger.has(token)) shared += 1;
  }
  return shared / smaller.size >= LINEAGE_OVERLAP_RATIO;
}

function sameTokens(a: Set<string>, b: Set<string>): boolean {
  if (a.size !== b.size || a.size === 0) return false;
  for (const token of a) {
    if (!b.has(token)) return false;
  }
  return true;
}

/** A card is a legitimate question when its text asks or assigns something. */
export function isLegitimateQuestion(card: EvidenceCard): boolean {
  const text = (card.question ?? card.query ?? "").trim();
  if (!text) return false;
  if (text.includes("?")) return true;
  const words = text.toLowerCase().split(/\s+/);
  if (words.length > 0 && (QUESTION_LEADS.has(words[0]) || TASK_LEADS.has(words[0]))) return true;
  // Scenario prompts bury the ask mid-sentence: "... Start from observability
  // and build a hypothesis matrix." Look for a task verb after punctuation.
  return words.some((word, index) => index > 0 && TASK_LEADS.has(word.replace(/[^a-z]/g, "")) && /[.;:]$/.test(words[index - 1] ?? ""));
}

/**
 * Collapse refinement lineages: drop a card when a newer, richer refinement
 * (its thread tokens are a strict superset) exists within the lineage window.
 * Input order is preserved for survivors (expects newest-first input).
 */
export function collapseRefinements(cards: EvidenceCard[]): EvidenceCard[] {
  const tokenSets = new Map<string, Set<string>>();
  for (const card of cards) tokenSets.set(card.card_id, threadTokens(card));

  return cards.filter((card) => {
    if (card.pinned) return true;
    const own = tokenSets.get(card.card_id) ?? new Set<string>();
    const createdAt = new Date(card.created_at).getTime();
    return !cards.some((other) => {
      if (other.card_id === card.card_id) return false;
      const otherTokens = tokenSets.get(other.card_id) ?? new Set<string>();
      const otherAt = new Date(other.created_at).getTime();
      if (Math.abs(otherAt - createdAt) > LINEAGE_WINDOW_MS) return false;
      if (isRefinedBy(own, otherTokens)) return true;
      // Exact duplicates (ASR repeats): keep only the newest, tie-broken by id.
      if (!sameTokens(own, otherTokens)) return false;
      return otherAt > createdAt || (otherAt === createdAt && other.card_id > card.card_id);
    });
  });
}

/** Timeline view: legitimate questions only, latest refinement per lineage. */
export function timelineCards(cards: EvidenceCard[]): EvidenceCard[] {
  return collapseRefinements(cards.filter((card) => card.pinned || isLegitimateQuestion(card)));
}
