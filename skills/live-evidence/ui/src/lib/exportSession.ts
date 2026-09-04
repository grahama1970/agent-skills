import type { AppSnapshot, EvidenceCard } from "@/types";

function cardSection(card: EvidenceCard, index: number): string[] {
  const lines: string[] = [];
  const pinTag = card.pinned ? " 📌 [PINNED]" : "";
  lines.push(`### ${index + 1}. ${card.question ?? card.query}${pinTag}`);
  lines.push(`- **Question ID:** \`${card.question_id ?? "unknown"}\` (rev ${card.question_revision ?? 0})`);
  if (card.parent_question_id) lines.push(`- **Follow-up of:** \`${card.parent_question_id}\``);
  if (card.review_verdict) {
    lines.push(`- **Review:** ${card.review_verdict}${card.review_reasons?.length ? ` — ${card.review_reasons.join("; ")}` : ""}`);
  }
  lines.push(`- **Sources:** ${[...new Set(card.sources.map((s) => `${s.lane}:${s.label}`))].join(", ") || "none"}`);
  lines.push("");
  if (card.solution_deck?.length) {
    lines.push("#### Glance Deck");
    for (const point of card.solution_deck) lines.push(`- **${point.title}**: ${point.trigger}`);
    lines.push("");
  }
  const primary = card.amendment_complete && card.amendment_text ? card.amendment_text : card.answer;
  if (primary) {
    lines.push(card.amendment_complete && card.amendment_text ? "#### Answer (revised after review)" : "#### Answer");
    lines.push(primary);
    lines.push("");
    if (card.amendment_complete && card.amendment_text && card.answer) {
      lines.push("<details><summary>Original answer (superseded)</summary>");
      lines.push("");
      lines.push(card.answer);
      lines.push("</details>");
      lines.push("");
    }
  }
  lines.push("---");
  lines.push("");
  return lines;
}

export function generateSessionMarkdown(snapshot: AppSnapshot): string {
  const lines: string[] = [];
  const now = new Date().toISOString().replace("T", " ").substring(0, 19);
  lines.push("# Live Evidence Session Export");
  lines.push(`**Exported At:** ${now} UTC`);
  lines.push(`**Profile:** ${snapshot.session.profile_name}`);
  lines.push(`**Session:** ${snapshot.session.session_id} (${snapshot.session.status})`);
  lines.push(`**Resolved Questions:** ${snapshot.cards.length}`);
  lines.push(`**Transcript Events:** ${snapshot.transcript.length}`);
  lines.push("");
  lines.push("---");
  lines.push("");
  lines.push("## Evidence Cards");
  lines.push("");
  if (snapshot.cards.length === 0) {
    lines.push("*No evidence cards recorded during this session.*");
    lines.push("");
  } else {
    snapshot.cards.forEach((card, index) => lines.push(...cardSection(card, index)));
  }
  lines.push("## Raw Transcript");
  lines.push("");
  lines.push("| Time | Speaker | Kind | Content |");
  lines.push("| :--- | :--- | :--- | :--- |");
  for (const event of snapshot.transcript) {
    if (event.kind !== "final") continue;
    const clean = event.text.replace(/\|/g, "\\|");
    lines.push(`| \`${event.created_at.slice(11, 19)}\` | ${event.speaker} | ${event.kind} | ${clean} |`);
  }
  return lines.join("\n");
}

export function downloadSessionMarkdown(snapshot: AppSnapshot): void {
  const blob = new Blob([generateSessionMarkdown(snapshot)], { type: "text/markdown;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", `live-evidence-session-${stamp}.md`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
