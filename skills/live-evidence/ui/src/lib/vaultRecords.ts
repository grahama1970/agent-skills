import { compactPath } from "@/lib/utils";
import type { EvidenceCard, EvidenceSource, SessionInfo } from "@/types";

export type VaultType = "all" | "code" | "memory" | "fact";

export interface MemoryRecord {
  id: string;
  type: Exclude<VaultType, "all">;
  project: string;
  question: string;
  answer: string;
  evidence: string;
  title: string;
  content: string;
  sourceText: string;
  sourceExcerpt: string;
  sourceHref?: string;
  tags: string[];
  createdAt: string;
  createdDate: string;
}

export function qidSafe(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-|-$/g, "") || "value";
}

function toDateInput(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString().slice(0, 10);
}

function sourceText(source?: EvidenceSource): string {
  if (!source) return "Source locator pending";
  const locator = source.path ?? source.url ?? source.label;
  const suffix = source.line_start ? `:${source.line_start}` : "";
  return `${source.repository ?? source.lane} / ${compactPath(locator)}${suffix}`;
}

function sourceHref(source?: EvidenceSource): string | undefined {
  if (!source?.url) return undefined;
  return source.url.startsWith("http://") || source.url.startsWith("https://") ? source.url : undefined;
}

function recordType(card: EvidenceCard): MemoryRecord["type"] {
  if (card.lanes.some((lane) => lane === "code" || lane === "ripgrep" || lane === "ask")) return "code";
  if (card.lanes.includes("memory")) return "memory";
  return "fact";
}

export function recordsFrom(cards: EvidenceCard[], session: SessionInfo, currentThread: string): MemoryRecord[] {
  return cards
    .slice()
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
    .map((card) => {
      const primarySource = card.sources[0];
      const tags = Array.from(new Set([...card.lanes, card.status, card.thread].map(qidSafe))).slice(0, 5);
      return {
        id: card.card_id,
        type: recordType(card),
        project: card.thread || session.profile_name || currentThread || "current-session",
        question: card.question || card.query,
        answer: card.answer || card.talking_point,
        evidence: card.evidence || card.proof,
        title: card.question || card.query,
        content: `${card.answer || card.talking_point} ${card.evidence || card.proof} ${card.qualifier}`.trim(),
        sourceText: sourceText(primarySource),
        sourceExcerpt: primarySource?.excerpt ?? "",
        sourceHref: sourceHref(primarySource),
        tags,
        createdAt: new Intl.DateTimeFormat(undefined, {
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
        }).format(new Date(card.created_at)),
        createdDate: toDateInput(card.created_at),
      };
    });
}
