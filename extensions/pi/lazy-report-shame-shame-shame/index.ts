// Humorous final-report guard for lazy failure reporting disguised as progress.
// Global Pi extension. Reload Pi with /reload after editing.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beginGuardTurn, claimGuardFollowUp } from "../_shared/guard-pipeline-shared.ts";

const EXTENSION_DIR = dirname(fileURLToPath(import.meta.url));
// JSON-first checker (2026-09-01): regex/prose classification is banned.
// status-json-check.mjs validates a pi.agent_status.v1 block via pydantic.
const REPORT_CHECK = join(EXTENSION_DIR, "status-json-check.mjs");
const SHAME_AUDIO = process.env.LAZY_REPORT_SHAME_AUDIO || join(EXTENSION_DIR, "shame.wav");
const TRAINING_JSONL = process.env.LAZY_REPORT_SHAME_TRAINING_JSONL || "/mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl";
const PENDING_REVIEW_PACKET = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || "/mnt/storage12tb/skills/shame/training/pending-review-packet.json";
const CONFIGURED_MEMORY_URL = process.env.MEMORY_SERVICE_URL || process.env.MEMORY_API_URL || "";
const MEMORY_URL = (CONFIGURED_MEMORY_URL.startsWith("unix://") ? "http://127.0.0.1:8601" : (CONFIGURED_MEMORY_URL || "http://127.0.0.1:8601")).replace(/\/+$/, "");
const MEMORY_COLLECTION = process.env.SHAME_MEMORY_COLLECTION || "shame_training_examples";
const MEMORY_SEARCH_COLLECTION = process.env.SHAME_MEMORY_SEARCH_COLLECTION || "project_knowledge";
const MEMORY_ENABLED = !/^(0|false|off|no)$/i.test(process.env.LAZY_REPORT_SHAME_MEMORY_ENABLED || "1");
const AUDIO_COOLDOWN_MS = 10_000;
const MAX_REJECTED_EXCERPT_CHARS = 8_000;
const CONTINUATION_GUARD_FILE = process.env.LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE || "/mnt/storage12tb/skills/shame/continuation-guard/current.json";

const HOLD_LABELS = new Set([
  "agent-active",
  "agent-blocked",
  "maintainer-active",
  "maintainer-blocked",
  "needs-human",
  "next:human",
  "status:deferred",
]);

type CheckDecision = "pass" | "reject" | "error" | "unknown";
type HumanVerdict = "allow" | "reject" | "warn" | "needs_review";

type ContinuationTicket = {
  ref?: string;
  url?: string;
  number?: number | string;
  state?: string;
  labels?: Array<string | { name?: string }>;
  target?: string;
  next_command?: string;
  blocked_by?: string;
};

type ContinuationGate = {
  id?: string;
  status?: string;
  next_command?: string;
  proof?: string;
};

type ContinuationState = {
  schema?: string;
  active?: boolean;
  target?: string;
  tickets?: ContinuationTicket[];
  gates?: ContinuationGate[];
  obvious_next_steps?: string[];
  next_command?: string;
};

const LEGACY_LABELS: Record<string, { verdict: HumanVerdict; reasons: string[] }> = {
  false_positive: { verdict: "allow", reasons: ["false_positive"] },
  false_negative: { verdict: "reject", reasons: ["false_negative"] },
  good_status_report: { verdict: "allow", reasons: ["good_status_report"] },
  commit_laundering: { verdict: "reject", reasons: ["commit_laundering"] },
  jargon_no_status: { verdict: "reject", reasons: ["jargon_no_status"] },
};

type CheckResult = {
  schema: "lazy_report_shame.report_check.v2";
  checker_version: string;
  decision: CheckDecision;
  reason_codes: string[];
  features: Record<string, unknown>;
  footer_failures: string[];
  diagnostics: string;
};

type Candidate = {
  user_text: string;
  assistant_entry_id: string;
  assistant_text: string;
  response_sha256: string;
  machine_decision: CheckDecision;
  machine_reason_codes: string[];
  checker_version: string;
  force_status: boolean;
  session_file?: string;
  session_id?: string;
  turn_id: string;
};

function contentToText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part: any) => {
      if (!part) return "";
      if (part.type === "text" && typeof part.text === "string") return part.text;
      if (typeof part.content === "string") return part.content;
      return "";
    })
    .join("\n");
}

function appendText(content: unknown, text: string): unknown {
  if (typeof content === "string") return `${content.trimEnd()}\n\n${text}`;
  if (!Array.isArray(content)) return text;
  return [...content, { type: "text", text: `\n\n${text}` }];
}

function activatesGuard(text: string): boolean {
  return /\$unlazy\b|\/unlazy\b|\$shame\b|\/shame\b|\bacceptance ledger\b/i.test(text);
}

function activatesShameSelfCorrection(text: string): boolean {
  return /\$shame\b|\/shame\b/i.test(text);
}

function sha256(value: string): string {
  return "sha256:" + createHash("sha256").update(value).digest("hex");
}

function truncateForRetry(text: string): string {
  if (text.length <= MAX_REJECTED_EXCERPT_CHARS) return text;
  return text.slice(0, MAX_REJECTED_EXCERPT_CHARS) + `\n\n[truncated by lazy-report-shame-shame-shame at ${MAX_REJECTED_EXCERPT_CHARS} chars]`;
}

function parseCheckerPayload(stdout: string, stderr: string, status: number | null): CheckResult {
  let payload: any = null;
  try { payload = JSON.parse(String(stdout || "{}")); } catch { payload = null; }
  if (payload?.schema === "lazy_report_shame.report_check.v2") {
    return {
      schema: payload.schema,
      checker_version: String(payload.checker_version || "unknown"),
      decision: ["pass", "reject", "error"].includes(payload.decision) ? payload.decision : "error",
      reason_codes: Array.isArray(payload.reason_codes) ? payload.reason_codes.map(String) : [],
      features: payload.features && typeof payload.features === "object" ? payload.features : {},
      footer_failures: Array.isArray(payload.footer_failures) ? payload.footer_failures.map(String) : [],
      diagnostics: String(stderr || stdout || "").trim(),
    };
  }
  return {
    schema: "lazy_report_shame.report_check.v2",
    checker_version: "unknown",
    decision: "error",
    reason_codes: ["checker_output_unparseable"],
    features: { exit_status: status },
    footer_failures: [],
    diagnostics: String(stderr || stdout || "report-check failed without diagnostics").trim(),
  };
}

function checkReport(text: string, forceStatus: boolean, mutatingTurn: boolean, strictStatus = false, userText = ""): CheckResult {
  const result = spawnSync("node", [REPORT_CHECK], {
    input: text,
    encoding: "utf8",
    timeout: 5000,
    env: {
      ...process.env,
      LRSSS_FORCE_STATUS: forceStatus ? "1" : "0",
      LRSSS_STRICT_STATUS: strictStatus ? "1" : "0",
      LRSSS_MUTATING_TURN: mutatingTurn ? "1" : "0",
      LRSSS_USER_TEXT: userText,
    },
  });
  if (result.error) {
    return {
      schema: "lazy_report_shame.report_check.v2",
      checker_version: "unknown",
      decision: "error",
      reason_codes: ["checker_spawn_error"],
      features: {},
      footer_failures: [],
      diagnostics: String(result.error.message || result.error),
    };
  }
  return parseCheckerPayload(String(result.stdout || ""), String(result.stderr || ""), result.status);
}

function loadContinuationState(): ContinuationState | null {
  if (!CONTINUATION_GUARD_FILE) return null;
  if (!existsSync(CONTINUATION_GUARD_FILE)) return null;
  try {
    const parsed = JSON.parse(readFileSync(CONTINUATION_GUARD_FILE, "utf8"));
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as ContinuationState;
  } catch {
    return null;
  }
}

function activeContinuationState(): ContinuationState | null {
  const state = loadContinuationState();
  if (!state || state.active === false) return null;
  return state;
}

function labelNames(ticket: ContinuationTicket): Set<string> {
  const result = new Set<string>();
  for (const raw of ticket.labels || []) {
    const value = typeof raw === "string" ? raw : raw?.name;
    if (value) result.add(String(value).toLowerCase());
  }
  return result;
}

function ticketRef(ticket: ContinuationTicket): string {
  if (ticket.ref) return ticket.ref;
  if (ticket.url) return ticket.url;
  if (ticket.number !== undefined) return `#${ticket.number}`;
  return ticket.target || "unknown-ticket";
}

function isClosedState(value: unknown): boolean {
  return /^(closed|done|complete|completed|merged)$/i.test(String(value || ""));
}

function actionableOpenTickets(state: ContinuationState): ContinuationTicket[] {
  return (state.tickets || []).filter((ticket) => {
    if (isClosedState(ticket.state)) return false;
    const labels = labelNames(ticket);
    if (!labels.has("agent-work")) return false;
    if ([...labels].some((label) => HOLD_LABELS.has(label))) return false;
    if (ticket.blocked_by) return false;
    return true;
  });
}

function unresolvedGates(state: ContinuationState): ContinuationGate[] {
  return (state.gates || []).filter((gate) => !/^(pass|passed|ok|complete|completed|closed)$/i.test(String(gate.status || "")));
}

// JSON-first (2026-09-01): a completion claim is state === "done" in the
// validated pi.agent_status.v1 object. No prose regex.
function completionClaim(statusState: string | undefined): boolean {
  return statusState === "done";
}

function evaluateContinuationGuard(statusState: string | undefined): CheckResult | null {
  const state = activeContinuationState();
  if (!state) return null;
  const tickets = actionableOpenTickets(state);
  const gates = unresolvedGates(state);
  const steps = Array.isArray(state.obvious_next_steps) ? state.obvious_next_steps.filter(Boolean) : [];
  if (!tickets.length && !gates.length && !steps.length && !state.next_command) return null;
  if (!completionClaim(statusState)) return null;

  const nextAction = state.next_command
    || tickets.find((ticket) => ticket.next_command)?.next_command
    || gates.find((gate) => gate.next_command)?.next_command
    || steps[0]
    || "Continue the active goal until the unresolved ticket/gate is closed or explicitly blocked.";
  const failures = [];
  if (tickets.length) failures.push("open_relevant_agent_work_ticket");
  if (gates.length) failures.push("unresolved_acceptance_gate");
  if (steps.length || state.next_command) failures.push("obvious_next_step_not_enacted");
  return {
    schema: "lazy_report_shame.report_check.v2",
    checker_version: "continuation-guard-v1",
    decision: "reject",
    reason_codes: ["continuation_guard_unresolved_work"],
    features: {
      continuation_guard_file: CONTINUATION_GUARD_FILE,
      target: state.target || null,
      open_ticket_refs: tickets.map(ticketRef),
      unresolved_gates: gates.map((gate) => gate.id || "unnamed-gate"),
      next_action: nextAction,
    },
    footer_failures: failures,
    diagnostics: `Continuation guard blocked final answer. Next action: ${nextAction}`,
  };
}

function playShameAudio(lastPlayedAt: { value: number }): void {
  if (/^(0|false|off|no)$/i.test(process.env.LAZY_REPORT_SHAME_AUDIO_ENABLED || "1")) return;
  const now = Date.now();
  if (now - lastPlayedAt.value < AUDIO_COOLDOWN_MS) return;
  lastPlayedAt.value = now;
  if (existsSync(SHAME_AUDIO)) {
    spawnSync("sh", ["-c", "(command -v pw-play >/dev/null && nohup pw-play \"$1\" >/dev/null 2>&1 &) || (command -v ffplay >/dev/null && nohup ffplay -nodisp -autoexit \"$1\" >/dev/null 2>&1 &) || (command -v aplay >/dev/null && nohup aplay \"$1\" >/dev/null 2>&1 &)", "sh", SHAME_AUDIO], { timeout: 1000 });
    return;
  }
  spawnSync("sh", ["-c", "(command -v canberra-gtk-play >/dev/null && nohup canberra-gtk-play -i bell >/dev/null 2>&1 &) || printf '\\a'"] , { timeout: 1000 });
}

function candidateExcerpt(candidate: Candidate): string {
  return candidate.assistant_text.replace(/\s+/g, " ").trim().slice(0, 320) || "(no text extracted)";
}

function makeReviewPacket(candidate: Candidate, check: CheckResult, retried: boolean) {
  return {
    schema: "lazy_report_shame.review_packet.v1",
    created_at: new Date().toISOString(),
    candidate_hash: candidate.response_sha256,
    turn_id: candidate.turn_id,
    assistant_entry_id: candidate.assistant_entry_id,
    session_file: candidate.session_file,
    session_id: candidate.session_id,
    machine: {
      decision: check.decision,
      reason_codes: check.reason_codes,
      footer_failures: check.footer_failures,
      checker_version: check.checker_version,
      retried,
    },
    candidate,
    rejected_excerpt: candidateExcerpt(candidate),
    human_commands: [
      "/shame show",
      "/shame reject commit_laundering -- no final Status Report",
      "/shame allow normal_answer -- this was acceptable",
      "/shame warn jargon_no_status -- needs clearer proof",
    ],
    correction_contract: {
      instruction: "Agent rewrites the answer plainly; human labels the raw rejected candidate after reviewing the correction.",
      required_footer: ["Status Report", "- Changed:", "- Verified:", "- Proof:", "- Not done:"],
    },
  };
}

function writePendingReviewPacket(candidate: Candidate, check: CheckResult, retried: boolean): string {
  mkdirSync(dirname(PENDING_REVIEW_PACKET), { recursive: true });
  writeFileSync(PENDING_REVIEW_PACKET, JSON.stringify(makeReviewPacket(candidate, check, retried), null, 2) + "\n", "utf8");
  return PENDING_REVIEW_PACKET;
}

function loadPendingCandidate(): Candidate | null {
  if (!existsSync(PENDING_REVIEW_PACKET)) return null;
  try {
    const packet = JSON.parse(readFileSync(PENDING_REVIEW_PACKET, "utf8"));
    const candidate = packet?.candidate;
    if (!candidate || typeof candidate.assistant_text !== "string" || typeof candidate.response_sha256 !== "string") return null;
    return {
      user_text: String(candidate.user_text || ""),
      assistant_entry_id: String(candidate.assistant_entry_id || "unknown"),
      assistant_text: candidate.assistant_text,
      response_sha256: candidate.response_sha256,
      machine_decision: ["pass", "reject", "error"].includes(candidate.machine_decision) ? candidate.machine_decision : "unknown" as CheckDecision,
      machine_reason_codes: Array.isArray(candidate.machine_reason_codes) ? candidate.machine_reason_codes.map(String) : [],
      checker_version: String(candidate.checker_version || "unknown"),
      force_status: Boolean(candidate.force_status),
      session_file: typeof candidate.session_file === "string" ? candidate.session_file : undefined,
      session_id: typeof candidate.session_id === "string" ? candidate.session_id : undefined,
      turn_id: String(candidate.turn_id || sha256(`${candidate.user_text || ""}\n---\n${candidate.assistant_text}`)),
    };
  } catch {
    return null;
  }
}

function rejectionNotice(candidate: Candidate, check: CheckResult, retried: boolean, reviewPacketPath: string): string {
  const excerpt = candidateExcerpt(candidate);
  const disposition = retried
    ? "The bad answer was hidden. One automatic retry was already used for this turn, so no second automatic retry was queued."
    : "The bad answer was hidden and one rewrite request was queued.";
  const footerFailures = check.footer_failures.length ? check.footer_failures.join(", ") : "none";
  return `🦥 REJECTED_BY_SLOTH_COURT

The last answer was rejected because it did not give a plain status report.

Machine check
- Candidate: ${candidate.response_sha256}
- Checker: ${check.checker_version}
- Reasons: ${check.reason_codes.join(", ") || "none"}
- Footer failures: ${footerFailures}
${check.diagnostics ? `- Diagnostics: ${check.diagnostics}\n` : ""}
Rejected excerpt:
${excerpt ? `> ${excerpt}` : "> (no text extracted)"}

Correction workflow
- ${disposition}
- The review packet was saved for human approval and survives extension reloads.
- The rewrite must give the corrected answer, not more gate JSON.
- After the corrected answer, use \`/shame review\` for an interactive label picker or label directly with \`/shame reject|allow|warn <reason> -- <note>\`.
- Use \`/shame show\` to inspect the raw candidate that will be labeled.

Status Report
- Changed: The bad status answer was replaced with a correction workflow instead of standing as the final answer.
- Verified: report-check.mjs returned ${check.decision}; checker ${check.checker_version}; footer failures: ${footerFailures}.
- Proof: ${reviewPacketPath}; rejected candidate ${candidate.response_sha256}; excerpt shown above.
- Not done: ${check.reason_codes.includes("continuation_guard_unresolved_work") ? (String(check.features?.next_action || "Continue the active goal until unresolved work is closed or blocked.")) : "Human review can label the raw candidate with /shame reject|allow|warn after the corrected answer."}`;
}

function retryPrompt(candidate: Candidate, check: CheckResult, reviewPacketPath: string): string {
  const excerpt = truncateForRetry(candidate.assistant_text.trim());
  const footerFailures = check.footer_failures.length ? check.footer_failures.join(", ") : "none";
  return `UNLAZY_FORCED_RETRY

Your previous answer was rejected by lazy-report-shame-shame-shame because it looked like a delivery/status report but did not end with a clear report title and plain-English bullet summary.

Machine check
- Candidate: ${candidate.response_sha256}
- Checker: ${check.checker_version}
- Reasons: ${check.reason_codes.join(", ") || "none"}
- Footer failures: ${footerFailures}
${check.diagnostics ? `- Diagnostics: ${check.diagnostics}\n` : ""}- Review packet: ${reviewPacketPath}

Rejected response:
${excerpt ? `> ${excerpt.replace(/\n/g, "\n> ")}` : "> (no text extracted)"}

Rewrite the answer now. Preserve only supported facts. Do not invent commands, results, receipts, or proof. Use “Not verified” or “Missing” when evidence does not exist. Do not answer with another gate failure unless a gate command actually failed and you have the receipt.

Collaborative correction flow:
- Give the corrected answer first.
- End with the exact Status Report footer below.
- The human can inspect the raw rejected candidate with \`/shame show\`.
- The human can label that candidate with \`/shame review\` or \`/shame reject|allow|warn <reason> -- <note>\`.

Status Report
- Changed: plain-English user-visible/project-visible change, not a commit/SHA/branch by itself.
- Verified: exact command/readback and observed result, or Not verified: exact reason.
- Proof: concrete path, URL, issue/PR number, commit, or Missing: exact reason.
- Not done: none, or exact unfinished item and next concrete step.`;
}

function parseShameArgs(args: string): { action: "capture" | "show" | "undo" | "review"; verdict: HumanVerdict; reasons: string[]; note: string; error?: string } {
  const trimmed = String(args || "").trim();
  if (!trimmed) return { action: "capture", verdict: "needs_review", reasons: [], note: "" };
  if (/^show\b/i.test(trimmed)) return { action: "show", verdict: "needs_review", reasons: [], note: "" };
  if (/^review\b/i.test(trimmed)) return { action: "review", verdict: "needs_review", reasons: [], note: trimmed.replace(/^review\s*/i, "") };
  if (/^undo\b/i.test(trimmed)) return { action: "undo", verdict: "needs_review", reasons: [], note: trimmed.replace(/^undo\s*/i, "") };

  const [beforeNote, ...afterNote] = trimmed.split(/\s+--\s+/);
  const tokens = beforeNote.trim().split(/\s+/).filter(Boolean);
  const rawHead = (tokens.shift() || "needs_review").toLowerCase().replace(/-/g, "_");
  const allowedVerdicts = new Set<HumanVerdict>(["allow", "reject", "warn", "needs_review"]);
  if (rawHead in LEGACY_LABELS) {
    const mapped = LEGACY_LABELS[rawHead];
    return {
      action: "capture",
      verdict: mapped.verdict,
      reasons: mapped.reasons,
      note: afterNote.join(" -- ").trim() || tokens.join(" "),
    };
  }
  const verdict = rawHead as HumanVerdict;
  if (!allowedVerdicts.has(verdict)) {
    return { action: "capture", verdict: "needs_review", reasons: [], note: "", error: `unknown verdict '${verdict}'. Use: allow, reject, warn, needs_review, or a legacy label such as false_positive` };
  }
  const reasons = tokens.map((token) => token.toLowerCase().replace(/-/g, "_")).filter(Boolean);
  return { action: "capture", verdict, reasons, note: afterNote.join(" -- ").trim() };
}

function getLastAssistantEntry(ctx: any): { id: string; text: string } | null {
  const sessionManager = ctx?.sessionManager;
  const entries = typeof sessionManager?.getBranch === "function"
    ? sessionManager.getBranch()
    : (typeof sessionManager?.getEntries === "function" ? sessionManager.getEntries() : []);
  for (let i = entries.length - 1; i >= 0; i -= 1) {
    const entry = entries[i];
    const message = entry?.message;
    if (entry?.type === "message" && message?.role === "assistant") {
      const text = contentToText(message.content);
      if (text.trim()) return { id: String(entry.id || message.id || "unknown"), text };
    }
  }
  return null;
}

function appendTrainingExample(example: Record<string, unknown>, outPath: string): void {
  mkdirSync(dirname(outPath), { recursive: true });
  appendFileSync(outPath, JSON.stringify(example) + "\n", "utf8");
}

async function postMemoryJson(path: string, body: Record<string, unknown>): Promise<any> {
  const response = await fetch(`${MEMORY_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-caller-skill": "shame" },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data: any = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}: ${text.slice(0, 500)}`);
  return data;
}

async function storeTrainingExampleInMemory(example: Record<string, unknown>): Promise<{ collection: string; key: string; read_back_count: number; search_collection: string; search_key: string; search_read_back_count: number; recall_found: boolean }> {
  const key = String(example._key || "");
  if (!key) throw new Error("training example is missing _key");
  await postMemoryJson("/store", { collection: MEMORY_COLLECTION, document: example });
  const readBack = await postMemoryJson("/recall/by-keys", {
    collection: MEMORY_COLLECTION,
    keys: [key],
    key_field: "_key",
    return_fields: ["_key", "schema", "human_verdict", "human_reasons", "response_sha256", "retrieval_text"],
  });
  const count = Array.isArray(readBack?.documents) ? readBack.documents.length : 0;
  if (count !== 1) throw new Error(`memory read-back failed for ${MEMORY_COLLECTION}/${key}`);

  const searchKey = `shame_search_${key.replace(/^shame_/, "").slice(0, 64)}`.slice(0, 254);
  const searchDoc = {
    _key: searchKey,
    doc_type: "shame_training_example",
    kind: "agent_status_shame_training_search_doc",
    problem: `Human-labeled agent status example: ${example.human_verdict} ${(((example.human_reasons as string[]) || []).join(", ") || "no_reason")}`,
    solution: example.retrieval_text,
    project: "agent-skills",
    scope: "agent-skills",
    section: "shame_training_examples",
    source_collection: MEMORY_COLLECTION,
    source_key: key,
    response_sha256: example.response_sha256,
    human_verdict: example.human_verdict,
    human_reasons: example.human_reasons,
    classifier_label: example.classifier_label,
    tags: ["project_knowledge", "project:agent-skills", ...((example.tags as string[]) || [])],
    retrieval_text: example.retrieval_text,
  };
  await postMemoryJson("/store", { collection: MEMORY_SEARCH_COLLECTION, document: searchDoc });
  const searchReadBack = await postMemoryJson("/recall/by-keys", {
    collection: MEMORY_SEARCH_COLLECTION,
    keys: [searchKey],
    key_field: "_key",
    return_fields: ["_key", "kind", "source_collection", "source_key", "retrieval_text", "tags"],
  });
  const searchCount = Array.isArray(searchReadBack?.documents) ? searchReadBack.documents.length : 0;
  if (searchCount !== 1) throw new Error(`memory search-doc read-back failed for ${MEMORY_SEARCH_COLLECTION}/${searchKey}`);
  const recallBody = {
    q: `${example.human_verdict} ${((example.human_reasons as string[]) || []).join(" ")} ${example.note || ""} ${example.assistant_text || ""}`.slice(0, 500),
    scope: "agent-skills",
    collections: [MEMORY_SEARCH_COLLECTION],
    tags: ["shame"],
    k: 10,
    threshold: 0.0,
  };
  let recallFound = false;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const recall = await postMemoryJson("/recall", recallBody);
    const items = Array.isArray(recall?.items) ? recall.items : [];
    recallFound = items.some((item: any) => item?._key === searchKey);
    if (recallFound) break;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  if (!recallFound) throw new Error(`memory recall did not return searchable shame doc ${MEMORY_SEARCH_COLLECTION}/${searchKey}`);
  return { collection: MEMORY_COLLECTION, key, read_back_count: count, search_collection: MEMORY_SEARCH_COLLECTION, search_key: searchKey, search_read_back_count: searchCount, recall_found: recallFound };
}

function removeTrainingExample(exampleId: string, outPath: string): boolean {
  if (!existsSync(outPath)) return false;
  const lines = readFileSync(outPath, "utf8").split(/\n/);
  const kept = lines.filter((line) => {
    if (!line.trim()) return false;
    try { return JSON.parse(line).example_id !== exampleId; } catch { return true; }
  });
  const removed = kept.length !== lines.filter((line) => line.trim()).length;
  if (removed) writeFileSync(outPath, kept.join("\n") + (kept.length ? "\n" : ""), "utf8");
  return removed;
}

function makeCandidate(ctx: any, userText: string, assistantEntryId: string, assistantText: string, check: CheckResult, forceStatus: boolean): Candidate {
  return {
    user_text: userText,
    assistant_entry_id: assistantEntryId,
    assistant_text: assistantText,
    response_sha256: sha256(assistantText),
    machine_decision: check.decision,
    machine_reason_codes: check.reason_codes,
    checker_version: check.checker_version,
    force_status: forceStatus,
    session_file: typeof ctx?.sessionManager?.getSessionFile === "function" ? ctx.sessionManager.getSessionFile() : undefined,
    session_id: typeof ctx?.sessionManager?.getSessionId === "function" ? ctx.sessionManager.getSessionId() : undefined,
    turn_id: sha256(`${userText}\n---\n${assistantText}`),
  };
}

export default function lazyReportShameShameShame(pi: any) {
  let sessionGuardActive = false;
  let turnGuardActive = false;
  let shameSelfCorrectTurn = false;
  let mutatingTurn = false;
  let currentUserText = "";
  let retryInProgress = false;
  let lastCandidate: Candidate | null = null;
  let lastWrittenExampleId: string | null = null;
  const retriedTurnIds = new Set<string>();
  const lastAudioPlayedAt = { value: 0 };

  pi.on("input", async (event: any) => {
    const text = String(event.text || "");
    beginGuardTurn(text, event.source);
    currentUserText = text;
    mutatingTurn = false;
    if (event.source !== "extension") retryInProgress = false;
    if (activatesGuard(text)) turnGuardActive = true;
    if (activatesShameSelfCorrection(text)) shameSelfCorrectTurn = true;
    return { action: "continue" };
  });

  pi.on("tool_call", async (event: any) => {
    const tool = String(event.toolName || "");
    const input = event.input || {};
    const command = String(input.command || "");
    if (["edit", "write"].includes(tool)) mutatingTurn = true;
    if (tool === "bash" && /\b(git\s+(?:commit|push|merge)|gh\s+(?:issue|pr)\s+(?:close|comment|edit|create)|npm\s+publish|pnpm\s+publish)\b/i.test(command)) {
      mutatingTurn = true;
    }
  });

  pi.on("before_agent_start", async (event: any) => {
    const prompt = String(event.prompt || "");
    const systemPrompt = String(event.systemPrompt || "");
    if (!sessionGuardActive && !turnGuardActive && !activatesGuard(prompt)) return;
    turnGuardActive = true;
    const shameSelfCorrection = shameSelfCorrectTurn
      ? "\n\n[Lazy Report Shame Self-Correction]\nThe user invoked $shame. Do not answer with meta-commentary about shame. Give the corrected answer in plain spoken English for the human to approve or correct. If the previous answer lacked proof, say Not verified or Missing instead of pretending it was proven. End with the exact titled footer below; after that, the human can label the raw candidate with /shame allow|reject|warn.\n\nStatus Report\n- Changed: ...\n- Verified: ...\n- Proof: ...\n- Not done: ..."
      : "";
    return {
      systemPrompt:
        systemPrompt +
        "\n\n[Lazy Report Shame Guard]\nIf you report delivery, GitHub work, commits, pushes, branches, SHAs, issue closure, or implementation status, end with a clear title and plain-spoken bullets. Include the user-visible change, verification/readback or Not verified, proof location or Missing, and remaining work if any. Git metadata and unit tests are supporting evidence, not the user-visible result. Do not invent proof." +
        shameSelfCorrection,
    };
  });

  pi.on("message_end", async (event: any, ctx: any) => {
    if (event.message?.role !== "assistant") return;
    const text = contentToText(event.message.content);
    if (!text.trim()) return;
    const forceStatus = sessionGuardActive || turnGuardActive || Boolean(activeContinuationState());
    const strictStatus = shameSelfCorrectTurn;
    let check = checkReport(text, forceStatus, mutatingTurn, strictStatus, currentUserText);
    const statusState = typeof (check as any)?.features?.state === "string" ? String((check as any).features.state) : undefined;
    const continuationCheck = evaluateContinuationGuard(statusState);
    if (continuationCheck && check.decision !== "reject") check = continuationCheck;
    let keepGuardForRetry = false;

    try {
      lastCandidate = makeCandidate(ctx, currentUserText, String(event.message.id || event.id || "unknown"), text, check, forceStatus);

      if (check.decision === "error") {
        ctx?.ui?.notify?.(`lazy-report-shame-shame-shame checker error: ${check.diagnostics || check.reason_codes.join(", ")}`, "warning");
        return;
      }
      if (check.decision !== "reject") return;

      const turnId = lastCandidate.turn_id;
      const pipelineClaim = claimGuardFollowUp({
        guard: "shame",
        messageId: String(event.message.id || event.id || turnId),
        assistantText: text,
        userText: currentUserText,
        reason: [...check.reason_codes, ...check.footer_failures].join(","),
        maxRetries: 1,
      });
      const alreadyRetried = retryInProgress || retriedTurnIds.has(turnId) || !pipelineClaim.ok;
      if (!alreadyRetried) retriedTurnIds.add(turnId);

      let reviewPacketPath = PENDING_REVIEW_PACKET;
      try {
        reviewPacketPath = writePendingReviewPacket(lastCandidate, check, alreadyRetried);
      } catch (error) {
        ctx?.ui?.notify?.(`lazy-report-shame-shame-shame could not write review packet: ${error instanceof Error ? error.message : String(error)}`, "warning");
      }

      const notice = rejectionNotice(lastCandidate, check, alreadyRetried, reviewPacketPath);
      playShameAudio(lastAudioPlayedAt);
      if (!alreadyRetried) {
        retryInProgress = true;
        keepGuardForRetry = strictStatus;
        try {
          pi.sendUserMessage(retryPrompt(lastCandidate, check, reviewPacketPath), { deliverAs: "followUp", expandPromptTemplates: false });
        } catch (_error) {
          try {
            pi.sendUserMessage(retryPrompt(lastCandidate, check, reviewPacketPath), { expandPromptTemplates: false });
          } catch {
            // Replacement still prevents the lazy answer from standing as the final visible answer.
          }
        }
      }

      return {
        message: {
          ...event.message,
          content: appendText(event.message.content, notice),
        },
      };
    } finally {
      if (!sessionGuardActive && !keepGuardForRetry) turnGuardActive = false;
      if (!keepGuardForRetry) shameSelfCorrectTurn = false;
      mutatingTurn = false;
      if (check.decision !== "reject") retryInProgress = false;
    }
  });

  pi.registerCommand("lazy-report-shame-shame-shame", {
    description: "Activate session-wide status footer reminders for delivery/status reports",
    handler: async (_args: string, ctx: any) => {
      sessionGuardActive = true;
      ctx.ui.notify(
        "🦥 Shame guard active. Delivery/status reports must end with Status Report bullets: Changed, Verified, Proof, Not done.",
        "warning",
      );
    },
  });

  pi.registerCommand("shame", {
    description: "Add the previous assistant response to the shame classifier training JSONL",
    handler: async (args: string, ctx: any) => {
      let parsed = parseShameArgs(args);
      if (parsed.error) {
        ctx.ui.notify(`/shame error: ${parsed.error}`, "error");
        return;
      }
      if (parsed.action === "show") {
        const candidate = lastCandidate || loadPendingCandidate();
        if (!candidate) {
          ctx.ui.notify(`No candidate captured yet. No pending review packet found at ${PENDING_REVIEW_PACKET}.`, "info");
          return;
        }
        const excerpt = candidate.assistant_text.replace(/\s+/g, " ").slice(0, 240) || "(no text extracted)";
        const reasons = candidate.machine_reason_codes.length ? candidate.machine_reason_codes.join(", ") : "none";
        ctx.ui.notify([
          "Shame review packet",
          `- Candidate: ${candidate.response_sha256}`,
          `- Pending packet: ${PENDING_REVIEW_PACKET}`,
          `- Machine: ${candidate.machine_decision} (${reasons})`,
          `- Checker: ${candidate.checker_version}`,
          `- Excerpt: ${excerpt}`,
          "- Human choices: /shame review; /shame reject <reason> -- <note>; /shame allow normal_answer -- <note>; /shame warn <reason> -- <note>",
          "- Correction target: the agent should answer plainly, then end with Status Report bullets: Changed, Verified, Proof, Not done.",
        ].join("\n"), "info");
        return;
      }
      if (parsed.action === "undo") {
        if (!lastWrittenExampleId) {
          ctx.ui.notify("No /shame training example from this session to undo.", "warning");
          return;
        }
        const removed = removeTrainingExample(lastWrittenExampleId, TRAINING_JSONL);
        ctx.ui.notify(removed ? `Removed /shame training example ${lastWrittenExampleId}` : `No matching /shame example found for ${lastWrittenExampleId}`, removed ? "info" : "warning");
        if (removed) lastWrittenExampleId = null;
        return;
      }

      let candidate = lastCandidate || loadPendingCandidate();
      if (!candidate) {
        const last = getLastAssistantEntry(ctx);
        if (!last) {
          ctx.ui.notify("No previous assistant response found to add to shame training data.", "error");
          return;
        }
        const check = checkReport(last.text, false, false);
        candidate = makeCandidate(ctx, currentUserText, last.id, last.text, check, false);
      }

      if (parsed.action === "review") {
        if (!ctx.hasUI || typeof ctx.ui?.select !== "function" || typeof ctx.ui?.input !== "function") {
          ctx.ui.notify("Interactive /shame review is unavailable here. Use /shame show, then /shame reject|allow|warn <reason> -- <note>.", "warning");
          return;
        }
        const choice = await ctx.ui.select("Label shame candidate", [
          "reject commit_laundering",
          "reject no_final_status_report",
          "reject missing_proof",
          "reject obvious_next_step_not_enacted",
          "warn jargon_no_status",
          "allow normal_answer",
          "needs_review unsure",
        ]);
        if (!choice) {
          ctx.ui.notify("/shame review cancelled; no training example written.", "info");
          return;
        }
        const [rawVerdict, ...rawReasons] = String(choice).split(/\s+/).filter(Boolean);
        const note = await ctx.ui.input("Why?", parsed.note || "");
        parsed = {
          action: "capture",
          verdict: rawVerdict as HumanVerdict,
          reasons: rawReasons.map((reason) => reason.toLowerCase().replace(/-/g, "_")),
          note: typeof note === "string" ? note : parsed.note,
        };
      }

      const exampleId = sha256(`${candidate.response_sha256}\n${parsed.verdict}\n${parsed.reasons.join(",")}\n${parsed.note}`);
      const exampleKey = exampleId.replace("sha256:", "shame_").slice(0, 254);
      const example = {
        _key: exampleKey,
        schema: "lazy_report_shame.training_example.v2",
        kind: "agent_status_shame_training_example",
        example_id: exampleId,
        created_at: new Date().toISOString(),
        source: "pi-extension-command:/shame",
        source_skill: "shame",
        human_verdict: parsed.verdict,
        human_reasons: parsed.reasons,
        classifier_label: parsed.verdict === "allow" ? "acceptable_update" : "bullshit_update",
        note: parsed.note,
        machine_decision: candidate.machine_decision,
        machine_reason_codes: candidate.machine_reason_codes,
        checker_version: candidate.checker_version,
        force_status: candidate.force_status,
        user_text: candidate.user_text,
        assistant_text: candidate.assistant_text,
        assistant_entry_id: candidate.assistant_entry_id,
        session_file: candidate.session_file,
        session_id: candidate.session_id,
        turn_id: candidate.turn_id,
        response_sha256: candidate.response_sha256,
        tags: ["shame", "classifier-training", `verdict:${parsed.verdict}`, ...parsed.reasons.map((reason) => `reason:${reason}`)],
        retrieval_text: [
          `verdict: ${parsed.verdict}`,
          `reasons: ${parsed.reasons.join(", ") || "none"}`,
          parsed.note ? `note: ${parsed.note}` : "",
          candidate.user_text ? `user: ${candidate.user_text}` : "",
          `assistant: ${candidate.assistant_text}`,
        ].filter(Boolean).join("\n"),
      };
      appendTrainingExample(example, TRAINING_JSONL);
      lastWrittenExampleId = exampleId;
      if (MEMORY_ENABLED) {
        try {
          const memory = await storeTrainingExampleInMemory(example);
          ctx.ui.notify(`Saved /shame example ${exampleId.slice(0, 19)} (${parsed.verdict}${parsed.reasons.length ? ":" + parsed.reasons.join(",") : ""}) to ${TRAINING_JSONL}, memory ${memory.collection}/${memory.key}, and searchable ${memory.search_collection}/${memory.search_key}`, "info");
        } catch (error) {
          ctx.ui.notify(`Saved /shame JSONL example ${exampleId.slice(0, 19)}, but memory write/read-back failed: ${error instanceof Error ? error.message : String(error)}`, "warning");
        }
      } else {
        ctx.ui.notify(`Saved /shame JSONL example ${exampleId.slice(0, 19)} (${parsed.verdict}${parsed.reasons.length ? ":" + parsed.reasons.join(",") : ""}); memory disabled`, "info");
      }
    },
  });
}
