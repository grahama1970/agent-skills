/**
 * Deterministic proof for the timeline question-lineage contract:
 * statements never render in the Question Timeline, garbled refinement
 * hypotheses collapse to their latest refinement, and legitimate questions
 * (interrogative, imperative-task, and scenario prompts with a mid-sentence
 * task verb) survive. Fixture texts are taken from a real DriveWealth live
 * session readback (8799 /api/state, 2026-08-31).
 *
 * Run: node --experimental-strip-types scripts/eval_question_lineage.mts
 */

import { writeFileSync } from "node:fs";

// Relative import: type-only imports inside the module are erased by
// --experimental-strip-types, so the "@/types" alias never resolves at runtime.
import {
  collapseRefinements,
  isLegitimateQuestion,
  timelineCards,
} from "../ui/src/lib/questionLineage.ts";

type CardLike = {
  card_id: string;
  created_at: string;
  thread: string;
  question: string | null;
  query: string;
  pinned: boolean;
};

function card(id: string, thread: string, question: string, createdAt: string, pinned = false): CardLike {
  return { card_id: id, created_at: createdAt, thread, question, query: question, pinned };
}

const T0 = "2026-08-31T15:45:00Z";
const T1 = "2026-08-31T15:45:20Z";
const T2 = "2026-08-31T15:45:40Z";

const statementClosing = card("s1", "Thanks · enjoyed · digging", "Thanks I enjoyed digging into this with you both I tried to stay honest throughout", T0);
const statementWrap = card("s2", "covers · areas · explore", "That covers the areas we wanted to explore Neelish and I will compare notes", T0);
const garbledFragment = card("s3", "Permanent · listing · itsa", "Permanent listing is one itsa tat head beo s d be-o-somed, as fast wear-ou", T0);

const refinement1 = card("r1", "Which · nodes", "Which nodes may run?", T0);
const refinement2 = card("r2", "Which · nodes · parallel · trend", "Which nodes may run in parallel? Which trend?", T1);
const refinement3 = card("r3", "Which · nodes · parallel · transitions · require", "Which nodes may run in parallel which transitions require serialization and locking", T2);

const scenarioPrompt = card("q1", "outputs · rise · observability", "At 9:30 on Tuesday morning, bad outputs rise sharply, but service error rate is unchanged. Start from observability and build a hypothesis matrix.", T1);
const imperativeTask = card("q2", "Propose · staged · rollout", "Propose a staged rollout to Customer Service with a kill switch and dashboard", T1);
const pinnedStatement = card("p1", "closing · pinned", "This closing remark was pinned by the human on purpose", T1, true);
const dup1 = card("d1", "mite", "Is a mite?", T0);
const dup2 = card("d2", "mite", "Is a mite?", T1);
const dup3 = card("d3", "mite", "Is a mite?", T2);

const cards = [dup3, refinement3, scenarioPrompt, imperativeTask, dup2, refinement2, refinement1, statementClosing, statementWrap, garbledFragment, pinnedStatement, dup1];

const visible = timelineCards(cards as never);
const visibleIds = visible.map((entry: CardLike) => entry.card_id);

const checks: Record<string, boolean> = {
  statement_closing_filtered: !visibleIds.includes("s1"),
  statement_wrap_filtered: !visibleIds.includes("s2"),
  garbled_fragment_filtered: !visibleIds.includes("s3"),
  lineage_collapsed_to_latest: visibleIds.includes("r3") && !visibleIds.includes("r1") && !visibleIds.includes("r2"),
  scenario_prompt_survives: visibleIds.includes("q1"),
  imperative_task_survives: visibleIds.includes("q2"),
  pinned_always_survives: visibleIds.includes("p1"),
  interrogative_detected: isLegitimateQuestion(refinement1 as never),
  statement_rejected: !isLegitimateQuestion(statementClosing as never),
  collapse_preserves_unrelated: collapseRefinements([scenarioPrompt, imperativeTask] as never).length === 2,
  duplicates_collapse_to_newest: visibleIds.filter((id: string) => id.startsWith("d")).length === 1 && visibleIds.includes("d3"),
};

const failed = Object.entries(checks).filter(([, ok]) => !ok);
const receipt = {
  schema: "live_evidence.question_lineage_eval.v1",
  status: failed.length === 0 ? "PASS" : "FAIL",
  checks,
  visible_ids: visibleIds,
  total_cards: cards.length,
  visible_count: visible.length,
};

writeFileSync("/tmp/live-evidence-question-lineage-eval.json", `${JSON.stringify(receipt, null, 2)}\n`);
console.log(`question-lineage eval: ${receipt.status} (${Object.keys(checks).length - failed.length}/${Object.keys(checks).length} checks)`);
if (failed.length > 0) {
  console.error("failed checks:", failed.map(([name]) => name).join(", "));
  process.exit(1);
}
