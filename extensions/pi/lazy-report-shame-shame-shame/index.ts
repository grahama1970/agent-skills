// Humorous final-report guard for lazy failure reporting disguised as progress.
// Global Pi extension. Reload Pi with /reload after editing.

import { spawnSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beginGuardTurn, claimGuardFollowUp, isAssistantStop, resetGuardRepairBudget } from "../_shared/guard-pipeline-shared.ts";
import { installTaskBudget } from "./task-budget.ts";
import { failureLogPath, historyOptions, readFailureHistory, recordFailure } from "./failure-history.mjs";
import { stripTerminalStatusFrame } from "./terminal-status-frame.mjs";

const EXTENSION_DIR = dirname(fileURLToPath(import.meta.url));
// JSON-first checker (2026-09-01): regex/prose classification is banned.
// status-json-check.mjs validates a pi.agent_status.v1 block via pydantic.
const REPORT_CHECK = join(EXTENSION_DIR, "status-json-check.mjs");
const SHAME_AUDIO = process.env.LAZY_REPORT_SHAME_AUDIO || join(EXTENSION_DIR, "shame.wav");
const TRAINING_JSONL = process.env.LAZY_REPORT_SHAME_TRAINING_JSONL || "/mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl";
const PENDING_REVIEW_PACKET = process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET || "/mnt/storage12tb/skills/shame/training/pending-review-packet.json";
const SPIRAL_TICKET_OUTBOX = process.env.LAZY_REPORT_SHAME_SPIRAL_TICKET_OUTBOX || "/mnt/storage12tb/skills/shame/ticket-outbox";
const AGENT_SKILLS_ROOT = process.env.AGENT_SKILLS_ROOT || "/home/graham/workspace/experiments/agent-skills";
const CONFIGURED_MEMORY_URL = process.env.MEMORY_SERVICE_URL || process.env.MEMORY_API_URL || "";
const MEMORY_URL = (CONFIGURED_MEMORY_URL.startsWith("unix://") ? "http://127.0.0.1:8601" : (CONFIGURED_MEMORY_URL || "http://127.0.0.1:8601")).replace(/\/+$/, "");
const MEMORY_COLLECTION = process.env.SHAME_MEMORY_COLLECTION || "shame_training_examples";
const MEMORY_SEARCH_COLLECTION = process.env.SHAME_MEMORY_SEARCH_COLLECTION || "project_knowledge";
// Exact-match helpers: the no-regex/no-prose-classification policy bans regex
// even over control tokens. These use tokenization + set membership only.
const FALSEY_FLAG_VALUES = new Set(["0", "false", "off", "no"]);
function flagDisabled(value: unknown): boolean {
  return FALSEY_FLAG_VALUES.has(String(value ?? "").trim().toLowerCase());
}
function tokenize(text: unknown): string[] {
  const out: string[] = [];
  let current = "";
  for (const ch of String(text ?? "")) {
    if (ch === " " || ch === "\t" || ch === "\n" || ch === "\r") {
      if (current) { out.push(current); current = ""; }
    } else {
      current += ch.toLowerCase();
    }
  }
  if (current) out.push(current);
  return out;
}
function hasLeadingToken(text: unknown, tokens: Set<string>): boolean {
  return tokens.has(tokenize(text)[0] || "");
}
function baseToolName(toolName: unknown): string {
  const raw = String(toolName || "").trim();
  if (!raw) return "";
  const dotted = raw.split(".").pop() || raw;
  const slashed = dotted.split("/").pop() || dotted;
  return slashed;
}
const SHAME_TOKENS = new Set(["$shame", "/shame", "/skill:shame"]);
const GUARD_TOKENS = new Set([...SHAME_TOKENS, "$unlazy", "/unlazy", "/skill:unlazy"]);
const CLOSED_TICKET_STATUSES = new Set(["closed", "done", "complete", "completed", "merged"]);
const PASSING_GATE_STATUSES = new Set(["pass", "passed", "ok", "complete", "completed", "closed"]);
function isMutatingShellCommand(command: string): boolean {
  const tokens = tokenize(command);
  for (let i = 0; i < tokens.length; i += 1) {
    const tok = tokens[i];
    if (tok === "git" && ["commit", "push", "merge"].includes(tokens[i + 1] ?? "")) return true;
    if (tok === "gh" && ["issue", "pr"].includes(tokens[i + 1] ?? "") && ["close", "comment", "edit", "create"].includes(tokens[i + 2] ?? "")) return true;
    if ((tok === "npm" || tok === "pnpm") && (tokens[i + 1] ?? "") === "publish") return true;
  }
  return false;
}

const MEMORY_ENABLED = !flagDisabled(process.env.LAZY_REPORT_SHAME_MEMORY_ENABLED || "1");
const AUDIO_COOLDOWN_MS = 10_000;
const CONTINUATION_GUARD_FILE = process.env.LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE || "/mnt/storage12tb/skills/shame/continuation-guard/current.json";
const OPS_DISCORD_RUN = process.env.LAZY_REPORT_SHAME_OPS_DISCORD_RUN || "/home/graham/workspace/experiments/agent-skills/skills/ops-discord/run.sh";
const OPS_DISCORD_NEEDS_HUMAN_CHANNEL = process.env.LAZY_REPORT_SHAME_OPS_DISCORD_NEEDS_HUMAN_CHANNEL || "horus";
const NEEDS_HUMAN_DISCORD_RECEIPT_DIR = process.env.LAZY_REPORT_SHAME_NEEDS_HUMAN_DISCORD_RECEIPT_DIR || "/mnt/storage12tb/skills/shame/needs-human-discord";

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
  review_packet_path?: string;
  turn_id: string;
};

function stripStatusJson(content: unknown): unknown {
  // The checker and renderer share one selector so validation and stripping
  // agree on delimiters, ambiguity, and the exact frame span.
  if (typeof content === "string") return stripTerminalStatusFrame(content);
  if (!Array.isArray(content)) return content;
  return content.map((part: any) => {
    if (part && part.type === "text" && typeof part.text === "string" && part.text.includes('"pi.agent_status.v1"')) {
      return { ...part, text: stripTerminalStatusFrame(part.text) };
    }
    return part;
  });
}

function renderStatusLine(status: any): string {
  const lines = [];
  // Plain-spoken verdict first (operator 2026-09-11): plain_answer carries the
  // human-readable verdict; answer remains the <=300-char machine headline.
  if (status?.plain_answer) lines.push(`Answer: ${String(status.plain_answer)}`);
  else if (status?.answer) lines.push(`Answer: ${String(status.answer)}`);
  lines.push("Status Report");
  lines.push(`- Goal: ${String(status?.goal || "unknown")}`);
  lines.push(`- State: ${String(status?.state || "unknown")}`);
  if (status?.run_dir) lines.push(`- Run dir: ${String(status.run_dir)}`);
  const changed = Array.isArray(status?.changed) ? status.changed : [];
  for (const item of changed) lines.push(`- Changed: ${String(item)}`);
  // Verified display shows the command and that a proof backs it; the raw
  // result substring stays in the JSON for anti-fabrication validation only.
  // Dumping fragments here rendered meaningless headings to the human.
  const verified = Array.isArray(status?.verified) ? status.verified : [];
  if (verified.length) {
    lines.push(`- Verified: ${verified.length} command(s), each backed by a proof file below`);
    for (const item of verified) lines.push(`- Verified: ${String(item?.command || "") } (receipt-backed)`);
  }
  const proof = Array.isArray(status?.proof) ? status.proof : [];
  for (const item of proof) lines.push(`- Proof: ${String(item)}`);
  const artifacts = Array.isArray(status?.artifacts) ? status.artifacts : [];
  for (const item of artifacts) lines.push(`- Artifact: ${String(item)}`);
  const receipts = Array.isArray(status?.receipts) ? status.receipts : [];
  for (const item of receipts) lines.push(`- Receipt: ${String(item)}`);
  const nodes = Array.isArray(status?.nodes) ? status.nodes : [];
  for (const item of nodes) lines.push(`- Node: ${String(item?.id || "")} -> ${String(item?.status || "")}${item?.artifact ? ` artifact=${String(item.artifact)}` : ""}${item?.receipt ? ` receipt=${String(item.receipt)}` : ""}`);
  const blocked = Array.isArray(status?.blocked) ? status.blocked : [];
  for (const item of blocked) lines.push(`- Blocked: ${String(item?.item || "")} -> ${String(item?.reason || "")}${item?.next_command ? ` -> ${String(item.next_command)}` : ""}`);
  const missing = Array.isArray(status?.missing_artifacts) ? status.missing_artifacts : [];
  for (const item of missing) lines.push(`- Missing artifact: ${String(item)}`);
  const notDone = Array.isArray(status?.not_done) ? status.not_done : [];
  if (notDone.length) {
    for (const item of notDone) lines.push(`- Not done: ${String(item?.item || "")} -> ${String(item?.next_command || "")}`);
  } else {
    lines.push("- Not done: none");
  }
  if (status?.needs_human?.action) lines.push(`- Needs Human: ${String(status.needs_human.action)} because ${String(status.needs_human.reason || "")}`);
  if (status?.failure?.triage?.code) lines.push(`- Failure: ${String(status.failure.triage.code)} -> ${String(status.failure.triage.cause || "")} -> ${String(status.failure.triage.next_command || "")}`);
  return lines.join("\n");
}

const SHAME_MODES = new Set(["off", "normal", "strict"]);
const DEFAULT_SHAME_MODE = SHAME_MODES.has(String(process.env.LAZY_REPORT_SHAME_DEFAULT_MODE || "").trim().toLowerCase())
  ? String(process.env.LAZY_REPORT_SHAME_DEFAULT_MODE).trim().toLowerCase()
  : "normal";

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

function textBlock(text: string): { type: "text"; text: string } {
  return { type: "text", text };
}

function appendText(content: unknown, text: string): unknown {
  if (typeof content === "string") {
    const base = content.trimEnd();
    return [textBlock(base ? `${base}\n\n${text}` : text)];
  }
  if (!Array.isArray(content)) return [textBlock(text)];
  return [...content, { type: "text", text: `\n\n${text}` }];
}

function controlLine(text: string): string {
  return String(text ?? "").trimStart().split("\n", 1)[0].trim();
}

function activatesGuard(text: string): boolean {
  return hasLeadingToken(text, GUARD_TOKENS)
    || controlLine(text) === "UNLAZY_FORCED_RETRY"
    || controlLine(text) === "CONTINUE_FROM_AGENT_STATUS";
}

function activatesShameSelfCorrection(text: string): boolean {
  return hasLeadingToken(text, SHAME_TOKENS) || controlLine(text) === "UNLAZY_FORCED_RETRY";
}

function sha256(value: string): string {
  return "sha256:" + createHash("sha256").update(value).digest("hex");
}

function nonEmptyText(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text ? text : null;
}

function normalizeTriageCode(value: unknown): string | null {
  const text = nonEmptyText(value);
  if (!text) return null;
  let normalized = "";
  for (const ch of text) normalized += ch === "-" ? "_" : ch.toLowerCase();
  return normalized;
}

function stripCommandPunctuation(value: string): string {
  let text = value.trim();
  const wrappers = new Set(["`", "'", "\"", "(", ")", "[", "]", "{", "}", ",", ";", ":"]);
  while (text && wrappers.has(text[0])) text = text.slice(1);
  while (text && wrappers.has(text[text.length - 1])) text = text.slice(0, -1);
  return text;
}

function commandTokens(value: unknown): string[] {
  return tokenize(value).map(stripCommandPunctuation).filter(Boolean);
}

function isCommandPath(token: string): boolean {
  return token.includes("/")
    || token.endsWith(".sh")
    || token.endsWith(".py")
    || token.endsWith(".mjs")
    || token.endsWith(".js")
    || token.endsWith(".ts");
}

function isCommandRunner(token: string): boolean {
  return new Set(["uv", "python", "python3", "node", "bash", "sh", "npm", "pnpm", "pytest", "git", "gh"]).has(token);
}

function isEnvironmentAssignment(token: string): boolean {
  return !token.startsWith("-") && token.includes("=") && token.indexOf("=") > 0;
}

function skipEnvPrefix(tokens: string[]): number {
  if (tokens[0] !== "env") return 0;
  let i = 1;
  while (i < tokens.length) {
    const token = tokens[i];
    if (isEnvironmentAssignment(token)) {
      i += 1;
    } else if (token === "-u" || token === "--unset") {
      i += 2;
    } else if (token.startsWith("-")) {
      i += 1;
    } else {
      break;
    }
  }
  return i;
}

function skipUvRunPrefix(tokens: string[], start: number): number {
  if (tokens[start] !== "uv" || tokens[start + 1] !== "run") return start;
  let i = start + 2;
  const valueOptions = new Set([
    "-p",
    "--config-file",
    "--directory",
    "--env-file",
    "--from",
    "--index",
    "--index-url",
    "--keyring-provider",
    "--link-mode",
    "--package",
    "--project",
    "--python",
    "--resolution",
    "--with",
    "--with-editable",
    "--with-requirements",
  ]);
  while (i < tokens.length) {
    const token = tokens[i];
    if (token === "--") return i + 1;
    if (isEnvironmentAssignment(token)) {
      i += 1;
    } else if (valueOptions.has(token)) {
      i += 2;
    } else if ([...valueOptions].some((option) => token.startsWith(`${option}=`))) {
      i += 1;
    } else if (token.startsWith("-")) {
      i += 1;
    } else {
      break;
    }
  }
  return i;
}

function pythonScriptIndex(tokens: string[], start: number): number {
  let i = start + 1;
  const valueOptions = new Set(["-c", "-m", "-W", "-X"]);
  while (i < tokens.length) {
    const token = tokens[i];
    if (token === "--") return i + 1;
    if (valueOptions.has(token)) return token === "-m" ? i : i + 1;
    if ([...valueOptions].some((option) => token.startsWith(`${option}`) && token.length > option.length)) return i;
    if (token.startsWith("-")) {
      i += 1;
    } else {
      return i;
    }
  }
  return start;
}

function substantiveCommandIndex(tokens: string[]): number {
  let start = skipEnvPrefix(tokens);
  start = skipUvRunPrefix(tokens, start);
  const token = tokens[start];
  if (token === "python" || token === "python3") return pythonScriptIndex(tokens, start);
  if (["node", "bash", "sh"].includes(token) && tokens[start + 1]) return start + 1;
  if (start < tokens.length) return start;
  return -1;
}

function flagValueToken(token: string, flag: string): string | null {
  const prefix = `${flag}=`;
  return token.startsWith(prefix) && token.length > prefix.length ? token.slice(prefix.length) : null;
}

function stableCommandIdentity(kind: string, value: unknown): string | null {
  const tokens = commandTokens(value);
  if (!tokens.length) return null;

  let commandIndex = substantiveCommandIndex(tokens);
  if (commandIndex >= 0 && tokens[commandIndex - 1] === "-m") commandIndex -= 1;
  if (commandIndex >= 0 && tokens[commandIndex - 1] === "-c") commandIndex -= 1;
  if (commandIndex >= 0 && !isCommandPath(tokens[commandIndex]) && !isCommandRunner(tokens[commandIndex]) && !["-m", "-c"].includes(tokens[commandIndex])) commandIndex = -1;
  if (commandIndex < 0) {
    for (let i = 0; i < tokens.length; i += 1) {
      if (isCommandPath(tokens[i])) {
        commandIndex = i;
        break;
      }
    }
  }
  if (commandIndex < 0) {
    commandIndex = tokens.findIndex(isCommandRunner);
  }
  if (commandIndex < 0) return null;

  const command = tokens[commandIndex] === "-m" && tokens[commandIndex + 1]
    ? `python_module:${tokens[commandIndex + 1]}`
    : (tokens[commandIndex] === "-c" ? "python_inline" : tokens[commandIndex]);
  const subcommandIndex = tokens[commandIndex] === "-m" ? commandIndex + 2 : commandIndex + 1;
  const pieces = [`${kind}:${command}`];
  const subcommand = tokens[subcommandIndex];
  if (subcommand && !subcommand.startsWith("-")) pieces.push(`subcommand:${subcommand}`);

  for (let i = commandIndex + 1; i < tokens.length; i += 1) {
    const token = tokens[i];
    for (const flag of ["--case", "--check", "--target", "--id"]) {
      const inline = flagValueToken(token, flag);
      if (inline) pieces.push(`${flag}:${inline}`);
      else if (token === flag && tokens[i + 1]) pieces.push(`${flag}:${tokens[i + 1]}`);
    }
  }
  return pieces.join("\n");
}

function trustedGoalIdentity(status: any): string | null {
  const goalHash = nonEmptyText(status?.goal_hash);
  if (goalHash) return `goal_hash:${goalHash.toLowerCase()}`;
  const goalId = nonEmptyText(status?.goal_id);
  if (goalId) return `goal_id:${goalId}`;
  return null;
}

function failedOperationIdentity(status: any, triage: any): string | null {
  const verified = Array.isArray(status?.verified) ? status.verified : [];
  for (const item of verified) {
    const command = stableCommandIdentity("verified_command", item?.command);
    if (command) return command;
  }
  const nextCommand = stableCommandIdentity("triage_next_command", triage?.next_command);
  if (nextCommand) return nextCommand;
  return null;
}

function ownerNormalizedTriageIdentity(triage: any): string | null {
  const triageCode = normalizeTriageCode(triage?.code);
  if (!triageCode) return null;
  return [
    "triage_owner:triage-error",
    `triage_code:${triageCode}`,
  ].join("\n");
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

function checkReport(text: string, forceStatus: boolean, mutatingTurn: boolean, strictStatus = false, userText = "", formatOnlyRetry = false): CheckResult {
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
      LRSSS_FORMAT_ONLY_RETRY: formatOnlyRetry ? "1" : "0",
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

function compileStatusCommand(status: unknown): { command: string | null; reason: string } | null {
  const result = spawnSync("node", [join(EXTENSION_DIR, "compile-status-command.mjs")], {
    input: JSON.stringify(status),
    encoding: "utf8",
    timeout: 5000,
  });
  if (result.error || result.status !== 0) return null;
  try {
    const parsed = JSON.parse(String(result.stdout || ""));
    return { command: parsed.command ?? null, reason: String(parsed.reason || "unknown") };
  } catch {
    return null;
  }
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
  return CLOSED_TICKET_STATUSES.has(String(value || "").trim().toLowerCase());
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
  return (state.gates || []).filter((gate) => !PASSING_GATE_STATUSES.has(String(gate.status || "").trim().toLowerCase()));
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
      validation_result: {
        schema: "pi.agent_status.validation_result.v1",
        valid: false,
        errors: [{ type: "continuation_guard_unresolved_work", loc: ["state"], msg: "state=done conflicts with continuation guard", ctx: { failures } }],
        steering: [{ code: "continuation_guard_unresolved_work", loc: ["state"], action: "continue_from_guard", command: nextAction }],
      },
    },
    footer_failures: failures,
    diagnostics: "",
  };
}

function statusFailureFingerprint(status: any): string | null {
  const triage = status?.failure?.triage;
  if (status?.state !== "failed" || !triage?.code) return null;
  const goalIdentity = trustedGoalIdentity(status);
  const triageIdentity = ownerNormalizedTriageIdentity(triage);
  const operationIdentity = failedOperationIdentity(status, triage);
  if (!goalIdentity || !triageIdentity || !operationIdentity) return null;
  return sha256([
    goalIdentity,
    triageIdentity,
    operationIdentity,
  ].map(String).join("\n"));
}

function statusFailureJournalFields(status: any): Record<string, unknown> {
  const triage = status?.failure?.triage;
  const triageCode = normalizeTriageCode(triage?.code);
  const operationIdentity = triage ? failedOperationIdentity(status, triage) : null;
  return {
    goal: trustedGoalIdentity(status),
    goal_text: nonEmptyText(status?.goal),
    goal_hash: nonEmptyText(status?.goal_hash)?.toLowerCase() || null,
    goal_id: nonEmptyText(status?.goal_id),
    triage_owner: triageCode ? "triage-error" : null,
    triage_code: triageCode,
    operation_identity: operationIdentity,
  };
}

function stableReasonCodesIdentity(reasonCodes: unknown): string | null {
  if (!Array.isArray(reasonCodes)) return null;
  const codes = [...new Set(reasonCodes.map(normalizeTriageCode).filter(Boolean) as string[])].sort();
  return codes.length ? `check_reason_codes:${codes.join(",")}` : null;
}

function recoveryJournalCheckId(status: any, decision: Record<string, unknown>, check?: CheckResult): string {
  const statusFingerprint = statusFailureFingerprint(status);
  const pieces = [
    `recovery_action:${String(decision.action || "unknown")}`,
    `format_only:${decision.format_only === true ? "true" : "false"}`,
  ];
  if (statusFingerprint) pieces.push(`status_failure:${statusFingerprint}`);
  const checkIdentity = stableReasonCodesIdentity(check?.reason_codes);
  if (checkIdentity) pieces.push(checkIdentity);
  return pieces.join("\n");
}

function readJsonFile(path: unknown): any | null {
  const raw = String(path || "").trim();
  if (!raw || raw.includes("\n") || !existsSync(raw)) return null;
  try { return JSON.parse(readFileSync(raw, "utf8")); } catch { return null; }
}

function hasDebuggerProof(status: any): boolean {
  const proof = Array.isArray(status?.proof) ? status.proof : [];
  return proof.some((path) => {
    const doc = readJsonFile(path);
    return doc?.schema === "debugger.proof.v1"
      && doc?.stopped?.hit === true
      && doc?.assessment?.proofValid === true
      && doc?.assessment?.variableInspectionValid === true;
  });
}

function hasDebuggerFailureHandoff(status: any): boolean {
  if (status?.state !== "needs_human") return false;
  const proof = Array.isArray(status?.proof) ? status.proof : [];
  return proof.some((path) => {
    const doc = readJsonFile(path);
    return doc?.schema === "lazy_report_shame.debugger_failure_handoff.v1"
      && typeof doc?.breakpoint?.file === "string"
      && Number.isInteger(doc?.breakpoint?.line)
      && doc.breakpoint.line > 0
      && typeof doc?.error === "string"
      && doc.error.trim();
  });
}

function isPlainHumanQuestion(status: any): boolean {
  if (status?.state !== "needs_human") return false;
  const action = String(status?.needs_human?.action || "").trim();
  if (!action.endsWith("?")) return false;
  if (action.includes("\n") || action.includes("```") || action.includes("{") || action.includes("}")) return false;
  return tokenize(action).length <= 40;
}

function evaluateRepeatedFailureGuard(status: any, failureCounts: Map<string, number>, repeatedFailure: { fingerprint: string | null; count: number }): CheckResult | null {
  const fingerprint = statusFailureFingerprint(status);
  if (fingerprint) {
    const count = (failureCounts.get(fingerprint) || 0) + 1;
    failureCounts.set(fingerprint, count);
    if (count >= 2) {
      repeatedFailure.fingerprint = fingerprint;
      repeatedFailure.count = count;
    }
  }

  if (!repeatedFailure.fingerprint) return null;
  if (hasDebuggerProof(status) || hasDebuggerFailureHandoff(status) || isPlainHumanQuestion(status)) {
    repeatedFailure.fingerprint = null;
    repeatedFailure.count = 0;
    return null;
  }
  if (fingerprint && fingerprint !== repeatedFailure.fingerprint) return null;

  return {
    schema: "lazy_report_shame.report_check.v2",
    checker_version: "repeated-failure-guard-v1",
    decision: "reject",
    reason_codes: ["repeated_failure_requires_debugger_or_human_question"],
    features: {
      fingerprint: repeatedFailure.fingerprint,
      count: repeatedFailure.count,
      validation_result: {
        schema: "pi.agent_status.validation_result.v1",
        valid: false,
        errors: [{ type: "repeated_failure_requires_debugger_or_human_question", loc: ["failure"], msg: "same failure fingerprint repeated", ctx: { count: repeatedFailure.count } }],
        steering: [{
          code: "repeated_failure_requires_debugger_or_human_question",
          loc: ["failure"],
          action: "ask_human_or_cite_debugger_proof",
          accepted_schemas: ["debugger.proof.v1", "lazy_report_shame.debugger_failure_handoff.v1"],
        }],
      },
    },
    footer_failures: ["repeated_same_fingerprint_failure_without_debugger_or_human_question"],
    diagnostics: "",
  };
}

function notifyNeedsHumanViaDiscord(status: any): { ok: true; receiptPath: string; messageUrl?: string } | { ok: false; reason: string; receiptPath?: string } {
  if (status?.state !== "needs_human") return { ok: true, receiptPath: "" };
  const content = [
    `Needs human: ${String(status?.goal || "agent task")}`,
    `Action: ${String(status?.needs_human?.action || "unspecified")}`,
    `Reason: ${String(status?.needs_human?.reason || "unspecified")}`,
  ].join("\n").slice(0, 1800);
  const proc = spawnSync(OPS_DISCORD_RUN, [
    "notify", "--discord-bot", "--channel-name", OPS_DISCORD_NEEDS_HUMAN_CHANNEL,
    "--content", content, "--json",
  ], { encoding: "utf8", timeout: 60_000 });
  const receiptPath = join(
    NEEDS_HUMAN_DISCORD_RECEIPT_DIR,
    `${Date.now()}-${createHash("sha256").update(JSON.stringify(status)).digest("hex").slice(0, 12)}.json`,
  );
  mkdirSync(dirname(receiptPath), { recursive: true });
  const raw = String(proc.stdout || "").trim();
  let receipt: any = null;
  try { receipt = JSON.parse(raw); } catch { /* checked below */ }
  writeFileSync(receiptPath, raw || JSON.stringify({ stderr: proc.stderr, status: proc.status }, null, 2));
  if (proc.status !== 0 || receipt?.schema !== "ops_discord.notification_receipt.v1" || receipt?.status !== "SENT" || !receipt?.message_id || !receipt?.message_url) {
    return { ok: false, reason: String(proc.stderr || proc.stdout || `ops-discord exited ${proc.status}`).slice(0, 500), receiptPath };
  }
  return { ok: true, receiptPath, messageUrl: String(receipt.message_url) };
}

function playShameAudio(lastPlayedAt: { value: number }): void {
  if (flagDisabled(process.env.LAZY_REPORT_SHAME_AUDIO_ENABLED || "1")) return;
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
      schema: "lazy_report_shame.correction_contract.v1",
      next_command: "rewrite_final_answer_with_valid_agent_status_json",
      required_status: {
        json_schema: "pi.agent_status.v1",
        final_fenced_json: true,
        continuing_requires_not_done_next_command: true,
        proof_must_be_real: true,
      },
    },
  };
}

function sessionIdentity(ctx: any): string | undefined {
  return ctx?.sessionManager?.getSessionId?.() || ctx?.sessionManager?.getSessionFile?.();
}

function pendingReviewPath(identity: string | undefined): string | null {
  return identity ? join(`${PENDING_REVIEW_PACKET}.sessions`, `${sha256(identity).slice(7)}.json`) : null;
}

function writePendingReviewPacket(candidate: Candidate, check: CheckResult, retried: boolean): string {
  const path = pendingReviewPath(candidate.session_id || candidate.session_file);
  if (!path) throw new Error("pending review packet requires session identity");
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  const temp = `${path}.${randomUUID()}.tmp`;
  writeFileSync(temp, JSON.stringify(makeReviewPacket(candidate, check, retried), null, 2) + "\n", { encoding: "utf8", mode: 0o600 });
  renameSync(temp, path);
  candidate.review_packet_path = path;
  return path;
}

function loadPendingCandidate(ctx: any): Candidate | null {
  const identity = sessionIdentity(ctx);
  if (!identity) return null;
  const scoped = pendingReviewPath(identity)!;
  const path = existsSync(scoped) ? scoped : PENDING_REVIEW_PACKET;
  if (!existsSync(path)) return null;
  try {
    const packet = JSON.parse(readFileSync(path, "utf8"));
    const candidate = packet?.candidate;
    if (!candidate || typeof candidate.assistant_text !== "string" || typeof candidate.response_sha256 !== "string") return null;
    if ((candidate.session_id || candidate.session_file) !== identity) return null;
    if (sha256(candidate.assistant_text) !== candidate.response_sha256) return null;
    return {
      review_packet_path: path,
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

function validationResult(check: CheckResult): unknown {
  const result = check.features?.validation_result;
  if (result && typeof result === "object") return result;
  return {
    schema: "pi.agent_status.validation_result.v1",
    valid: false,
    errors: check.reason_codes.map((code) => ({ type: code, loc: [], msg: code, ctx: {} })),
    steering: check.reason_codes.map((code) => ({ code, loc: [], action: "fix_field" })),
  };
}

function recoveryDecision(check: CheckResult, retried: boolean, taskPhase?: string): Record<string, unknown> {
  const codes = new Set(check.reason_codes);
  const has = (items: string[]) => items.some((item) => codes.has(item));
  if (retried) return { schema: "lazy_report_shame.recovery_decision.v1", action: "stop_retry", format_only: true, allowed_tools: [], reason: "status_contract_retry_exhausted" };
  if (has(["validator_script_missing", "validator_invocation_failed", "validator_crashed", "duplicate_detector_failed"])) {
    return { schema: "lazy_report_shame.recovery_decision.v1", action: "validator_failure", format_only: false, allowed_tools: [], reason: "status_validator_failed" };
  }
  if (has(["continuation_guard_unresolved_work", "task_acceptance_checks_incomplete", "task_budget_exhausted"])) {
    return { schema: "lazy_report_shame.recovery_decision.v1", action: "continue_execution", format_only: false, allowed_tools: [], reason: "unresolved_work", next_command: check.features?.next_action || null };
  }
  if (taskPhase === "accepted" || has(["task_already_accepted"])) {
    return { schema: "lazy_report_shame.recovery_decision.v1", action: "output_only_repair", format_only: true, allowed_tools: [], reason: "accepted_task_report_repair" };
  }
  if (has(["proof_json_schema_missing", "proof_schema_unsupported", "ticket_closure_receipt_not_closed"])) {
    return { schema: "lazy_report_shame.recovery_decision.v1", action: "existing_proof_substitution", format_only: true, allowed_tools: [], reason: "cite_existing_typed_receipt" };
  }
  // Proof-missing done reports are safely copy-repairable now that the retry
  // is a single-target byte-for-byte continuing status (no tools needed); the
  // compiled follow-up then drives the model to finish with real proof.
  if (has(["proof_reference_unresolved", "proof_path_missing", "proof_empty", "done_requires_proof", "done_requires_verified", "verified_not_backed_by_proof"])) {
    return { schema: "lazy_report_shame.recovery_decision.v1", action: "output_only_repair", format_only: true, allowed_tools: [], reason: "missing_executable_evidence_copy_repair" };
  }
  return { schema: "lazy_report_shame.recovery_decision.v1", action: "output_only_repair", format_only: true, allowed_tools: [], reason: "status_field_repair" };
}

function rejectionAction(decision: Record<string, unknown>): Record<string, unknown> {
  if (decision.action === "continue_execution") return { action: "continue_from_guard", command: decision.next_command || null };
  if (decision.action === "validator_failure") return { action: "needs_triage", reason: decision.reason };
  if (decision.action === "stop_retry") return { action: "stop_retry", reason: decision.reason };
  return { action: "emit_pi_agent_status_v1", reason: decision.reason };
}

function rejectionNotice(candidate: Candidate, check: CheckResult, retried: boolean, reviewPacketPath: string, decision: Record<string, unknown>): string {
  return `REJECTED_BY_SLOTH_COURT
\`\`\`json
${JSON.stringify({
    schema: "lazy_report_shame.rejection_notice.v1",
    candidate_hash: candidate.response_sha256,
    checker: check.checker_version,
    decision: check.decision,
    reason_codes: check.reason_codes,
    footer_failures: check.footer_failures,
    diagnostics_sha256: check.diagnostics ? sha256(check.diagnostics) : null,
    review_packet: reviewPacketPath,
    recovery_decision: decision,
    next: rejectionAction(decision),
  })}
\`\`\``;
}

function statusFromCandidate(candidate: Candidate, check: CheckResult): any {
  if (check.features?.status) return check.features.status;
  const start = candidate.assistant_text.lastIndexOf("```json");
  const end = start >= 0 ? candidate.assistant_text.indexOf("```", start + 7) : -1;
  if (start >= 0 && end > start) {
    try { return JSON.parse(candidate.assistant_text.slice(start + 7, end)); } catch { return null; }
  }
  return null;
}

function retryEvidenceSnapshot(candidate: Candidate, check: CheckResult): Array<Record<string, unknown>> {
  const status: any = statusFromCandidate(candidate, check);
  const proofs = Array.isArray(status?.proof) ? status.proof.map(String) : [];
  const errors = Array.isArray((check.features?.validation_result as any)?.errors) ? (check.features?.validation_result as any).errors : [];
  return proofs.slice(0, 8).map((proof: string) => {
    const matched = errors.filter((error: any) => error?.ctx?.proof === proof).map((error: any) => String(error.type || "invalid_proof"));
    const item: Record<string, unknown> = { proof, validation: matched.length ? "rejected" : "admitted", reason_codes: matched };
    if (existsSync(proof)) {
      try {
        const raw = readFileSync(proof);
        item.digest = sha256(raw.toString("utf8"));
        const parsed = JSON.parse(raw.toString("utf8"));
        if (parsed?.schema) item.schema = String(parsed.schema);
      } catch { item.validation = "unreadable"; }
    }
    return item;
  });
}

function guardContinuingStatus(userText: string): Record<string, unknown> {
  const firstLine = String(userText || "").split("\n").map((l) => l.trim()).find((l) => l.length > 0) || "";
  const goal = firstLine.slice(0, 120) || "continue the original task";
  return {
    schema: "pi.agent_status.v1",
    goal,
    state: "continuing",
    changed: ["no change: guard-substituted continuing status after prose-only stop"],
    not_done: [{
      item: "finish the original task with verified proof, then preflight the final status",
      next_command: "write the final answer to /tmp/candidate.md and run skills/shame/run.sh preflight /tmp/candidate.md",
    }],
  };
}

function suggestedRetryStatus(candidate: Candidate, check: CheckResult): Record<string, unknown> {
  const status: any = statusFromCandidate(candidate, check) || {};
  const goal = String(status.goal || "continue the original task").trim();
  return {
    schema: "pi.agent_status.v1",
    goal,
    state: "continuing",
    changed: Array.isArray(status.changed) && status.changed.length ? status.changed.map(String) : ["no change: status repair only"],
    not_done: [{
      item: "finish the original task with verified proof, then preflight the final status",
      next_command: "write the final answer to /tmp/candidate.md and run skills/shame/run.sh preflight /tmp/candidate.md",
    }],
  };
}

function writeSpiralTicketRequest(candidate: Candidate, check: CheckResult, reviewPacketPath: string, decision: Record<string, unknown>): string {
  const status = check.features?.status;
  const stableEpisode = statusFailureFingerprint(status) || candidate.turn_id;
  const checkIdentity = stableReasonCodesIdentity(check.reason_codes);
  const fingerprint = sha256([
    candidate.session_id || candidate.session_file || "unknown-session",
    stableEpisode,
    `recovery_action:${String(decision.action || "unknown")}`,
    `format_only:${decision.format_only === true ? "true" : "false"}`,
    checkIdentity || "check_reason_codes:none",
  ].join("\n"));
  const id = fingerprint.slice(7, 23);
  mkdirSync(SPIRAL_TICKET_OUTBOX, { recursive: true });
  const requestPath = join(SPIRAL_TICKET_OUTBOX, `${id}.json`);
  if (existsSync(requestPath)) return requestPath;
  const bodyPath = join(SPIRAL_TICKET_OUTBOX, `${id}.md`);
  const title = `Fix shame spiral ${id}`;
  const body = [
    `# ${title}`,
    "",
    "## Current state",
    "A shame report repair exhausted its bounded retry budget. This should be rare and must become repair work instead of chat-only noise.",
    "",
    "## Failure codes",
    ...check.reason_codes.map((code) => `- ${code}`),
    "",
    "## Required proof",
    "Run a retained shame eval that reproduces the spiral class and proves the fix prevents the same retry exhaustion.",
    "",
    "## Context",
    `- review_packet: ${reviewPacketPath}`,
    `- candidate_hash: ${candidate.response_sha256}`,
    `- checker: ${check.checker_version}`,
  ].join("\n");
  writeFileSync(bodyPath, body + "\n");
  const ticketCommand = [
    "skills/ticket/run.sh maintenance",
    JSON.stringify(title),
    "--target skills/shame",
    "--invariant", JSON.stringify("Shame spirals are converted into tracked repair work instead of silently exhausting retries."),
    "--cleanup", JSON.stringify(check.reason_codes.join(", ")),
    "--scoped-files skills/shame",
    "--proof", JSON.stringify("retained shame eval for the reported spiral class"),
    "--route backend_python_or_skill_runtime",
    "--agent agent-skill-maintainer",
    "--label agent-work",
    "--apply",
  ].join(" ");
  const request = {
    schema: "lazy_report_shame.spiral_ticket_request.v1",
    fingerprint,
    title,
    target: "skills/shame",
    route: "backend_python_or_skill_runtime",
    agent: "agent-skill-maintainer",
    labels: ["agent-work"],
    reason_codes: check.reason_codes,
    candidate_hash: candidate.response_sha256,
    checker: check.checker_version,
    review_packet: reviewPacketPath,
    recovery_decision: decision,
    body_path: bodyPath,
    ticket_command: ticketCommand,
    watchdog_route: "project-watchdog -> ticket_repair",
  };
  if (!flagDisabled(process.env.LAZY_REPORT_SHAME_SPIRAL_TICKET_APPLY ?? "1")) {
    const applied = spawnSync("bash", ["-lc", ticketCommand], { cwd: AGENT_SKILLS_ROOT, encoding: "utf8", timeout: 30000 });
    (request as any).ticket_apply = {
      attempted: true,
      exit_code: applied.status,
      stdout_excerpt: String(applied.stdout || "").slice(0, 2000),
      stderr_excerpt: String(applied.stderr || "").slice(0, 2000),
    };
  }
  writeFileSync(requestPath, JSON.stringify(request, null, 2) + "\n");
  return requestPath;
}

function retryPrompt(candidate: Candidate, check: CheckResult, reviewPacketPath: string, decision: Record<string, unknown>, taskBudget?: object): string {
  // Rich packet retained for /shame show + telemetry; it is NOT inlined into
  // the model-visible retry prompt (single-target contract below).
  const packet = {
    schema: "lazy_report_shame.retry_request.v1",
    format_only: true,
    // A5 consistency (2026-09-11): the tool_call gate ALLOWS read + preflight
    // during format repair (A3). Advertising [] here told models tools were
    // fully blocked, so they composed the retry from memory and failed on
    // schema details preflight would have caught. Keep this in lockstep with
    // the formatRepairTurn gate in the tool_call handler.
    allowed_tools: ["read", "bash: skills/shame/run.sh preflight"],
    max_corrections: 1,
    ...(taskBudget ? { task_budget: taskBudget } : {}),
    candidate_hash: candidate.response_sha256,
    checker: check.checker_version,
    reason_codes: check.reason_codes,
    diagnostics_sha256: check.diagnostics ? sha256(check.diagnostics) : null,
    review_packet: reviewPacketPath,
    validation_result: validationResult(check),
    recovery_decision: decision,
    evidence_snapshot: retryEvidenceSnapshot(candidate, check),
    suggested_status: suggestedRetryStatus(candidate, check),
    next: rejectionAction(decision),
  };
  try {
    writeFileSync(join(dirname(reviewPacketPath), "retry-packet.json"), JSON.stringify(packet, null, 2) + "\n");
  } catch { /* best-effort telemetry */ }
  // Single-target retry (WebGPT rank 4): the correction context must contain
  // exactly ONE JSON object. Rejection-notice parroting came from competing
  // JSON attractors; the rich packet stays in the review/telemetry file only.
  const target = suggestedRetryStatus(candidate, check);
  const placeholderNote = String((target as any).answer || "").includes("ANSWER_PLACEHOLDER")
    ? " Replace ANSWER_PLACEHOLDER_REPLACE_WITH_YOUR_ONE_SENTENCE_ANSWER with your one-sentence answer to the user's question."
    : "";
  return `UNLAZY_FORCED_RETRY
One-shot format correction. Do not re-answer the task. Do not call tools.
Your entire reply must be exactly this fenced json block, byte for byte:${placeholderNote}
\`\`\`json
${JSON.stringify(target, null, 2)}
\`\`\``;
}

function continuationPrompt(statusState: string, compiled: { command: string; reason?: string }): string {
  return `CONTINUE_FROM_AGENT_STATUS
\`\`\`json
${JSON.stringify({
  schema: "lazy_report_shame.follow_up.v1",
  status_state: statusState,
  reason: compiled.reason || `agent_status_${statusState}`,
  command: compiled.command,
})}
\`\`\``;
}

function parseShameArgs(args: string): { action: "capture" | "show" | "undo" | "review"; verdict: HumanVerdict; reasons: string[]; note: string; error?: string } {
  const trimmed = String(args || "").trim();
  if (!trimmed) return { action: "capture", verdict: "needs_review", reasons: [], note: "" };
  if (tokenize(trimmed)[0] === "show") return { action: "show", verdict: "needs_review", reasons: [], note: "" };
  if (tokenize(trimmed)[0] === "review") return { action: "review", verdict: "needs_review", reasons: [], note: trimmed.slice(trimmed.toLowerCase().indexOf("review") + 6).trim() };
  if (tokenize(trimmed)[0] === "undo") return { action: "undo", verdict: "needs_review", reasons: [], note: trimmed.slice(trimmed.toLowerCase().indexOf("undo") + 4).trim() };

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
  let budget: ReturnType<typeof installTaskBudget>;
  let sessionGuardActive = false;
  let turnGuardActive = false;
  let shameSelfCorrectTurn = false;
  let formatRepairTurn = false;
  let mutatingTurn = false;
  let shameSkillContractRequired = false;
  let shameSkillContractRead = false;
  let currentUserText = "";
  let pendingFollowUp: string | null = null;
  // Feature 1 (from ponytail): session-persisted guard mode via custom entries.
  // off = no enforcement; normal = mutating turns need status JSON; strict = every substantive turn.
  let sessionMode: string = DEFAULT_SHAME_MODE;
  let lastCandidate: Candidate | null = null;
  let lastWrittenExampleId: string | null = null;
  const failureCounts = new Map<string, number>();
  const repeatedFailure = { fingerprint: null as string | null, count: 0 };
  const lastAudioPlayedAt = { value: 0 };
  const loadedSourceHash = sha256(readFileSync(fileURLToPath(import.meta.url), "utf8"));
  let lastReportState: string | undefined;
  const enabled = () => sessionMode !== "off" || budget?.current?.contract.mode === "task";
  function syncBadge(ctx: any) {
    const label = enabled() ? `ON · ${sessionMode === "off" ? "task policy" : sessionMode}` : "OFF";
    ctx?.ui?.setStatus?.("shame", `🦥 ${label}${lastReportState ? ` · last: ${lastReportState}` : ""}`);
  }

  pi.on("session_start", async (event: any, ctx: any) => {
    const entries = Array.isArray(event?.entries) ? event.entries : [];
    for (let i = entries.length - 1; i >= 0; i -= 1) {
      const entry = entries[i];
      if (entry?.type === "custom" && entry?.customType === "shame-mode" && SHAME_MODES.has(String(entry?.data?.mode))) {
        sessionMode = String(entry.data.mode);
        break;
      }
    }
    try { syncBadge(ctx); } catch { /* optional UI */ }
  });

  pi.on("input", async (event: any) => {
    const text = String(event.text || "");
    beginGuardTurn(text, event.source);
    // Preserve the human's original question across guard-injected follow-ups;
    // overwriting it with CONTINUE/RETRY text silently disabled the answer gate.
    if (event.source !== "extension") currentUserText = text;
    pendingFollowUp = null;
    mutatingTurn = false;
    // Derive turn state anew. A previous correction must not contaminate a
    // fresh human question, and discussing a skill is not invoking its guard.
    turnGuardActive = activatesGuard(text);
    formatRepairTurn = controlLine(text) === "UNLAZY_FORCED_RETRY";
    shameSelfCorrectTurn = activatesShameSelfCorrection(text);
    shameSkillContractRequired = shameSelfCorrectTurn && !formatRepairTurn;
    shameSkillContractRead = false;
    return { action: "continue" };
  });

  pi.on("tool_result", async (event: any, ctx: any) => {
    if (event.isError) recordFailure(ctx, { kind: "tool_error_observed", tool_name: event.toolName, tool_call_id: event.toolCallId,
      error_excerpt: contentToText(event.content).slice(0, 1000) });
    const tool = baseToolName(event.toolName);
    const input = event.input || {};
    const path = String(input.path || "");
    if (tool === "read" && path.endsWith("/skills/shame/SKILL.md") && !event.isError) {
      shameSkillContractRead = true;
    }
  });

  pi.on("tool_call", async (event: any) => {
    const tool = baseToolName(event.toolName);
    const input = event.input || {};
    const command = String(input.command || "");
    if (formatRepairTurn) {
      // A3: the read-only preflight checker is the one tool that prevents a
      // wasted retry; blocking it forced blind guesses (2026-09-08 spiral).
      const isPreflight = tool === "bash" && /(^|\s|\/)run\.sh preflight(\s|$)/.test(command) && !isMutatingShellCommand(command);
      if (tool === "read" || isPreflight) return;
      return {
        block: true, terminate: true,
        reason: JSON.stringify({ code: "format_repair_tools_forbidden", allowed_tools: ["read", "bash: skills/shame/run.sh preflight"], max_corrections: 1 }),
      };
    }
    if (shameSkillContractRequired && !shameSkillContractRead && !["read", "shame_failures"].includes(tool)) {
      return {
        block: true,
        reason: JSON.stringify({
          code: "skill_contract_unread",
          skill: "shame",
          next_steps: [{
            next_command: "Read /home/graham/workspace/experiments/agent-skills/skills/shame/SKILL.md before acting on $shame or /shame.",
            sha256: sha256(readFileSync("/home/graham/workspace/experiments/agent-skills/skills/shame/SKILL.md", "utf8")),
          }],
        }),
      };
    }
    if (["edit", "write"].includes(tool)) mutatingTurn = true;
    if (tool === "bash" && isMutatingShellCommand(command)) {
      mutatingTurn = true;
    }
  });

  pi.on("before_agent_start", async (event: any, ctx: any) => {
    try { syncBadge(ctx); } catch { /* optional UI */ }
    const prompt = String(event.prompt || "");
    if (sessionGuardActive || turnGuardActive || activatesGuard(prompt)) {
      turnGuardActive = true;
    }
    // Do not inject prose reminders into ordinary project-agent context. The
    // deterministic checker/retry path owns enforcement; system-prompt noise was
    // making agents talk about the guard instead of the project work.
    return;
  });

  // Pi drains agent_end follow-ups inside the same prompt promise. At
  // agent_settled print mode can exit before a newly started prompt completes.
  pi.on("agent_end", async (_event: any, ctx: any) => {
    if (!pendingFollowUp || ctx?.hasPendingMessages?.() || ctx?.signal?.aborted) return;
    const prompt = pendingFollowUp;
    pendingFollowUp = null;
    try { pi.sendUserMessage(prompt, { deliverAs: "followUp", expandPromptTemplates: false }); }
    catch (error) {
      recordFailure(ctx, { kind: "continuation_dispatch_exception", error_excerpt: String(error).slice(0, 1000) });
      throw error;
    }
  });

  pi.on("session_shutdown", async () => { pendingFollowUp = null; });

  pi.on("message_end", async (event: any, ctx: any) => {
    if (event.message?.role !== "assistant") return;
    if (event.message.stopReason === "error") recordFailure(ctx, { kind: "provider_error_observed",
      provider: event.message.provider, model: event.message.model, response_id: event.message.responseId,
      error_excerpt: String(event.message.errorMessage || "provider error without message").slice(0, 1000) });
    pendingFollowUp = null;
    // Preserve intermediate text AND tool calls, guard state, and retry budget.
    // Only a terminal model response can be a completion-report candidate.
    if (!isAssistantStop(event.message) || ctx?.signal?.aborted || ctx?.hasPendingMessages?.()) return;
    if (budget.current?.contract.mode === "question" || budget.current?.answerOnlyTurn) {
      if (budget.current.contract.mode === "question") budget.current.questionAnswered();
      return;
    }
    if (sessionMode === "off" && !budget.current) return;
    const text = contentToText(event.message.content);
    // A4: a guard token on a turn with zero mutating tool calls is an advisory
    // question; do not arm the full done/proof contract for it (2026-09-08:
    // five rejections, all on non-mutating Q&A turns).
    const guardArmed = (sessionGuardActive || turnGuardActive) && (mutatingTurn || formatRepairTurn);
    const forceStatus = Boolean(budget.current) || sessionMode === "strict" || mutatingTurn || guardArmed || Boolean(activeContinuationState());
    const strictStatus = shameSelfCorrectTurn;
    let check = checkReport(text, forceStatus, mutatingTurn, strictStatus, currentUserText, formatRepairTurn);
    const statusState = typeof (check as any)?.features?.state === "string" ? String((check as any).features.state) : undefined;
    const status = (check as any)?.features?.status;
    const continuationCheck = evaluateContinuationGuard(statusState);
    if (continuationCheck && check.decision !== "reject") check = continuationCheck;
    const repeatedFailureCheck = status && check.decision !== "reject"
      ? evaluateRepeatedFailureGuard(status, failureCounts, repeatedFailure)
      : null;
    if (repeatedFailureCheck) check = repeatedFailureCheck;
    if (status && check.decision !== "reject" && statusState === "needs_human") {
      const delivery = notifyNeedsHumanViaDiscord(status);
      if (delivery.ok === false) {
        check = {
          schema: "lazy_report_shame.report_check.v2",
          checker_version: "needs-human-discord-v1",
          decision: "reject",
          reason_codes: ["needs_human_discord_delivery_failed"],
          footer_failures: [],
          diagnostics: delivery.reason,
          features: {
            state: statusState,
            status,
            validation_result: {
              schema: "pi.agent_status.validation_result.v1",
              valid: false,
              errors: [{ type: "needs_human_discord_delivery_failed", loc: ["needs_human"], msg: "state=needs_human must be delivered through ops-discord", ctx: { receipt: delivery.receiptPath || null } }],
              steering: [{ code: "needs_human_discord_delivery_failed", loc: ["needs_human"], action: "send_ops_discord_notification", receipt: delivery.receiptPath || null }],
            },
          },
        };
      }
    }
    if (status && check.decision !== "reject" && budget.current) {
      const reason = budget.current.validReport(statusState!);
      if (reason) check = {
        schema: "lazy_report_shame.report_check.v2", checker_version: "task-budget-v1", decision: "reject",
        reason_codes: [reason], footer_failures: [], diagnostics: "",
        features: { validation_result: { schema: "pi.agent_status.validation_result.v1", valid: false,
          errors: [{ type: reason, loc: ["state"], msg: reason, ctx: { receipt: budget.current.receipt } }],
          steering: [{ code: reason, action: "report_task_budget_state", phase: budget.current.phase, receipt: budget.current.receipt }] } },
      };
    }
    let keepGuardForRetry = false;

    try {
      lastCandidate = makeCandidate(ctx, currentUserText, String(event.message.id || event.id || "unknown"), text, check, forceStatus);

      if (check.decision === "error") {
        ctx?.ui?.notify?.(`lazy-report-shame-shame-shame checker error: ${check.diagnostics || check.reason_codes.join(", ")}`, "warning");
        check = {
          ...check,
          decision: "reject",
          reason_codes: ["checker_error_fail_closed", ...check.reason_codes],
          footer_failures: ["checker_error_fail_closed", ...check.footer_failures],
        };
        lastCandidate = makeCandidate(ctx, currentUserText, String(event.message.id || event.id || "unknown"), text, check, forceStatus);
      }
      if (check.decision !== "reject") {
        if (statusState === "failed") recordFailure(ctx, { kind: "agent_reported_failure", ...statusFailureJournalFields(status),
          reason_codes: [normalizeTriageCode(status.failure?.triage?.code) || String(status.failure?.triage?.code || "")],
          cause: status.failure?.triage?.cause, check_id: statusFailureFingerprint(status), candidate_hash: lastCandidate.response_sha256 });
        // JSON-first keep-going and escalation: every validated status compiles
        // through compile-status-command.mjs (pure data -> command; no regex).
        // continuing and needs_* escalation states queue their exact compiled
        // command; done/needs_human/failed compile to null and end the turn.
        let displayReturn: any = undefined;
        if (status && typeof statusState === "string") {
          resetGuardRepairBudget();
          // Representation conditioning (WebGPT 2026-09-11) + answer-visibility
          // (operator 2026-08-31): keep the model's own answer prose and
          // canonical fenced status JSON in model-visible history verbatim,
          // then APPEND the rendered Status Report footer. The old strip+rewrite
          // removed the fence and taught imitating models a prose-only shape
          // (20/24 failures); appending preserves both contracts.
          const line = renderStatusLine(status);
          displayReturn = { message: { ...event.message, content: appendText(event.message.content, line) } };
          lastReportState = statusState;
          try { syncBadge(ctx); } catch { /* optional UI */ }
          const compiled = compileStatusCommand(status);
          if (compiled?.command) {
            const claim = claimGuardFollowUp({
              guard: "shame-status-compiler",
              messageId: String(event.message.id || event.id || "unknown"),
              assistantText: text,
              userText: currentUserText,
              reason: compiled.reason || `agent_status_${statusState}`,
              continuation: true,
              message: event.message,
            });
            if (claim.ok) pendingFollowUp = continuationPrompt(statusState, compiled);
          }
          return displayReturn;
        }
        return displayReturn;
      }

      // Guard-owned deterministic repair (WebGPT rank 2): a prose-only stop is
      // the 20/24 failure class. Instead of burning the model's one retry on
      // re-authoring what the guard already knows, substitute a safe
      // `continuing` status built from session state, revalidate it through the
      // real checker, and keep the canonical fence in history. `done` is never
      // synthesized; this substitution is the episode's one correction.
      if (check.decision === "reject"
        && check.reason_codes.length === 1
        && check.reason_codes[0] === "missing_agent_status_json"
        && !budget.current) {
        const substituted = guardContinuingStatus(currentUserText);
        const canonicalFence = "```json\n" + JSON.stringify(substituted, null, 2) + "\n```";
        const recheck = checkReport(`${text}\n\n${canonicalFence}`, forceStatus, mutatingTurn, strictStatus, currentUserText, false);
        if (recheck.decision === "pass") {
          recordFailure(ctx, { kind: "guard_substituted_status", goal: substituted.goal,
            reason_codes: ["missing_agent_status_json"], checker_version: check.checker_version,
            candidate_hash: sha256(text) });
          resetGuardRepairBudget();
          lastReportState = "continuing";
          try { syncBadge(ctx); } catch { /* optional UI */ }
          const compiled = compileStatusCommand(substituted);
          if (compiled?.command) {
            const claim = claimGuardFollowUp({
              guard: "shame-status-compiler",
              messageId: String(event.message.id || event.id || "unknown"),
              assistantText: text,
              userText: currentUserText,
              reason: compiled.reason || "agent_status_continuing",
              continuation: true,
              message: event.message,
            });
            if (claim.ok) pendingFollowUp = continuationPrompt("continuing", compiled);
          }
          return { message: { ...event.message, content: appendText(event.message.content, canonicalFence) } };
        }
      }

      const turnId = lastCandidate.turn_id;
      const plannedDecision = recoveryDecision(check, false, budget.current?.phase);
      const wantsFormatRepair = plannedDecision.format_only === true;
      const formatAllowed = wantsFormatRepair && !formatRepairTurn && (!budget.current || budget.current.requestFormatRepair());
      const pipelineClaim = claimGuardFollowUp({
        guard: "shame",
        messageId: String(event.message.id || event.id || turnId),
        assistantText: text,
        userText: currentUserText,
        reason: [...check.reason_codes, ...check.footer_failures].join(","),
        maxRetries: 1,
      });
      const alreadyRetried = !formatAllowed || !pipelineClaim.ok;
      if (alreadyRetried && budget.current) budget.current.save("task_format_repair_exhausted");

      let reviewPacketPath = PENDING_REVIEW_PACKET;
      try {
        reviewPacketPath = writePendingReviewPacket(lastCandidate, check, alreadyRetried);
      } catch (error) {
        ctx?.ui?.notify?.(`lazy-report-shame-shame-shame could not write review packet: ${error instanceof Error ? error.message : String(error)}`, "warning");
      }

      const finalDecision = recoveryDecision(check, alreadyRetried, budget.current?.phase);
      let spiralTicketRequestPath: string | null = null;
      if (alreadyRetried) {
        try { spiralTicketRequestPath = writeSpiralTicketRequest(lastCandidate, check, reviewPacketPath, finalDecision); }
        catch (error) { recordFailure(ctx, { kind: "spiral_ticket_request_failed", error_excerpt: String(error).slice(0, 1000), reason_codes: check.reason_codes }); }
      }
      recordFailure(ctx, { kind: alreadyRetried ? "report_retry_exhausted" : "report_rejected", ...(status ? statusFailureJournalFields(status) : { goal: null }),
        candidate_hash: lastCandidate.response_sha256, check_id: recoveryJournalCheckId(status, finalDecision, check),
        reason_codes: check.reason_codes, checker_version: check.checker_version, review_packet: reviewPacketPath,
        excerpt: candidateExcerpt(lastCandidate), retry: { planned: !alreadyRetried, reason: pipelineClaim.reason }, spiral_ticket_request: spiralTicketRequestPath });
      const notice = rejectionNotice(lastCandidate, check, alreadyRetried, reviewPacketPath, finalDecision);
      playShameAudio(lastAudioPlayedAt);
      if (!alreadyRetried) {
        keepGuardForRetry = strictStatus;
        pendingFollowUp = retryPrompt(lastCandidate, check, reviewPacketPath, finalDecision, budget.current ? {
          phase: budget.current.phase, receipt: budget.current.receipt, allowed_tools: [], format_repair_limit: 1,
        } : undefined);
      }

      return {
        message: {
          ...event.message,
          content: [textBlock(notice)],
        },
      };
    } finally {
      if (!sessionGuardActive && !keepGuardForRetry) turnGuardActive = false;
      if (!keepGuardForRetry) shameSelfCorrectTurn = false;
      mutatingTurn = false;
    }
  });

  pi.registerCommand("lazy-report-shame-shame-shame", {
    description: "Activate session-wide status footer reminders for delivery/status reports",
    handler: async (_args: string, ctx: any) => {
      sessionGuardActive = true;
      ctx.ui.notify(
        "🦥 Shame guard active. Delivery/status reports must include valid pi.agent_status.v1 JSON.",
        "warning",
      );
    },
  });

  pi.registerCommand("shame", {
    description: "Add the previous assistant response to the shame classifier training JSONL",
    handler: async (args: string, ctx: any) => {
      // Feature 1: /shame off|normal|strict — session-persisted guard mode.
      const modeArg = String(args || "").trim().toLowerCase();
      if (SHAME_MODES.has(modeArg)) {
        sessionMode = modeArg;
        try { pi.appendEntry("shame-mode", { mode: modeArg }); } catch { /* persistence best-effort */ }
        try { syncBadge(ctx); } catch { /* optional UI */ }
        ctx.ui.notify(`shame guard mode: ${sessionMode} (persisted for this session)`, "info");
        return;
      }
      if (modeArg === "status") {
        syncBadge(ctx);
        ctx.ui.notify(JSON.stringify({ enabled: enabled(), mode: sessionMode, last_report: lastReportState || null,
          task: budget.current?.phase || "unarmed", failure_log: failureLogPath(), loaded_source_hash: loadedSourceHash,
          reload_required: loadedSourceHash !== sha256(readFileSync(fileURLToPath(import.meta.url), "utf8")) }, null, 2), "info");
        return;
      }
      if (modeArg === "task" || modeArg.startsWith("task ")) {
        await budget.command(args.trim().slice(4).trim(), ctx); syncBadge(ctx); return;
      }
      if (modeArg === "failures" || modeArg.startsWith("failures ")) {
        try {
          const options = historyOptions(args.trim().split(/\s+/).slice(1));
          ctx.ui.notify(JSON.stringify(readFailureHistory({ sessionId: sessionIdentity(ctx), ...options }), null, 2), "info");
        } catch (error) { ctx.ui.notify(String(error), "error"); }
        return;
      }
      let parsed = parseShameArgs(args);
      if (parsed.error) {
        ctx.ui.notify(`/shame error: ${parsed.error}`, "error");
        return;
      }
      if (parsed.action === "show") {
        const candidate = lastCandidate || loadPendingCandidate(ctx);
        if (!candidate) {
          ctx.ui.notify(`No candidate captured yet. No matching pending review packet found at ${pendingReviewPath(sessionIdentity(ctx)) || "(session identity unavailable)"}.`, "info");
          return;
        }
        const excerpt = candidate.assistant_text.replace(/\s+/g, " ").slice(0, 240) || "(no text extracted)";
        const reasons = candidate.machine_reason_codes.length ? candidate.machine_reason_codes.join(", ") : "none";
        ctx.ui.notify([
          "Shame review packet",
          `- Candidate: ${candidate.response_sha256}`,
          `- Pending packet: ${candidate.review_packet_path || pendingReviewPath(sessionIdentity(ctx))}`,
          `- Machine: ${candidate.machine_decision} (${reasons})`,
          `- Checker: ${candidate.checker_version}`,
          `- Excerpt: ${excerpt}`,
          "- Human choices: /shame review; /shame reject <reason> -- <note>; /shame allow normal_answer -- <note>; /shame warn <reason> -- <note>",
          "- Correction target: the agent should answer plainly, then include valid pi.agent_status.v1 JSON.",
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

      let candidate = lastCandidate || loadPendingCandidate(ctx);
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
  pi.registerTool?.({ name: "shame_failures", label: "Shame failure history",
    description: "Read retained Shame failures. Current session by default; all=true explicitly requests cross-session history. No checks or writes.",
    parameters: { type: "object", properties: { limit: { type: "integer", minimum: 1, maximum: 200 }, all: { type: "boolean" } }, additionalProperties: false },
    async execute(_id: string, params: any, _signal: any, _update: any, ctx: any) {
      const data = readFailureHistory({ sessionId: sessionIdentity(ctx), ...params });
      return { content: [textBlock(JSON.stringify(data))], details: data };
    },
  });
  budget = installTaskBudget(pi);
}
