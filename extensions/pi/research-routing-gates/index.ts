import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { chmodSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beginGuardTurn, claimGuardFollowUp } from "../_shared/guard-pipeline-shared.ts";

const EXTENSION_DIR = dirname(fileURLToPath(import.meta.url));
const CHECKER = join(EXTENSION_DIR, "research-gate-check.mjs");

type ObservationKind = "memory" | "brave" | "dogpile" | "tau" | "triage_error" | "ask_webgpt" | "ask_fast_single" | "ask_roundtable" | "ask_compete" | "mvp" | "scan" | "other";
type Observation = {
  phase: "call" | "result";
  kind: ObservationKind;
  toolName: string;
  toolCallId?: string;
  command?: string;
  ok?: boolean;
};

type CheckResult = {
  schema: "pi_research_gate.check.v1";
  checker_version: string;
  decision: "pass" | "reject" | "error";
  reason_codes: string[];
  route: Record<string, boolean>;
  evidence: Record<string, unknown>;
  counts: Record<string, number>;
};

function textFromContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.map((part: any) => {
    if (part?.type === "text" && typeof part.text === "string") return part.text;
    if (typeof part?.content === "string") return part.content;
    return "";
  }).join("\n");
}

function commandText(input: any): string {
  if (!input || typeof input !== "object") return String(input || "");
  const parts: string[] = [];
  const add = (value: unknown) => {
    if (value === undefined || value === null) return;
    if (typeof value === "string") {
      if (value.trim()) parts.push(value);
      return;
    }
    if (Array.isArray(value)) {
      for (const item of value) add(item);
      return;
    }
    if (typeof value === "object") {
      const obj = value as any;
      add(obj.recipient_name);
      add(obj.toolName);
      add(obj.command);
      add(obj.code);
      add(obj.query);
      add(obj.queries);
      add(obj.args);
      add(obj.parameters);
      add(obj.tool_uses);
    }
  };
  add(input.command);
  add(input.code);
  add(input.query);
  add(input.queries);
  add(input.args);
  add(input.parameters);
  add(input.tool_uses);
  return parts.join("\n");
}

const COMMAND_MATCHERS: Array<{ kind: ObservationKind; pattern: RegExp }> = [
  { kind: "scan", pattern: /^(read|grep|find|ls)$/i },
  { kind: "memory", pattern: /\b(?:skills\/memory\/run\.sh|\.\/run\.sh)\s+recall\b|\b(memory-agent|graph_memory).*\brecall\b|\bhttpx\b[\s\S]{0,200}\/(?:recall|answer|intent)\b|\b127\.0\.0\.1:8601\/(?:recall|answer|intent)\b|\bPOST\s+\/(?:recall|answer|intent)\b/i },
  { kind: "mvp", pattern: /\b(?:mvp\/|\/mvp\/)[^\n]*(?:goal\.md|run\.sh|receipt\.json|manifest\.json)|\b(?:mkdir|find|test|ls)\b[^\n]*\bmvp\/|\bmvp\/[^\n]*\b(?:run\.sh|receipt\.json|goal\.md|manifest\.json)\b/i },
  { kind: "ask_fast_single", pattern: /\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+tau-dag\b[\s\S]{0,800}(?:^|\s)--handler\s+(?:claude-fable-low|gpt-5\.5-low|[^\s]*(?:qwen|kimi|deepseek|glm)[^\s]*-low)\b/im },
  { kind: "ask_compete", pattern: /\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+compete\b|(?:^|\s)--dag-template\s+compete\b|(?:^|\s)--pattern\s+compete\b/im },
  { kind: "ask_roundtable", pattern: /\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+tau-dag\b[\s\S]{0,600}(?:^|\s)(?:--dag-template\s+roundtable|--pattern\s+roundtable|--topology\s+concurrent)\b|\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+ask\b[\s\S]{0,300}(?:^|\s)--roundtable\b/im },
  { kind: "ask_webgpt", pattern: /\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+(?:webgpt|chatgpt)\b|\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+tau-dag\b[\s\S]{0,400}(?:^|\s)--handler\s+webgpt\b|\b(?:skills\/ask\/run\.sh|ask\/run\.sh|\.\/run\.sh)\s+one-shot\b[\s\S]{0,400}(?:^|\s)--handler\s+webgpt\b/im },
  { kind: "brave", pattern: /\b(?:skills\/brave-search\/run\.sh|brave_search\.py|\.\/run\.sh)\s+(?:web|context|summarize|local)\b/i },
  { kind: "dogpile", pattern: /\b(?:skills\/dogpile\/run\.sh|dogpile\/run\.sh|\.\/run\.sh)\s+search\b/i },
  { kind: "triage_error", pattern: /\b(?:skills\/triage-error\/run\.sh|triage-error\/run\.sh|\.\/run\.sh)\s+(?:classify|triage)\b/i },
  { kind: "tau", pattern: /\b(?:skills\/tau\/run\.sh|tau\/run\.sh|uv\s+run\s+tau)\b|\btau\.dag_contract\.v1\b|\btau\s+dag-run\b/i },
];

function matchIndex(pattern: RegExp, haystack: string): number | null {
  const match = pattern.exec(haystack);
  return match ? match.index : null;
}

function classifyCommands(toolName: string, input: any): Array<{ kind: ObservationKind; command: string }> {
  const command = commandText(input);
  const haystack = `${toolName}\n${command}`;
  const matches: Array<{ kind: ObservationKind; command: string; index: number; rank: number }> = [];

  COMMAND_MATCHERS.forEach((matcher, rank) => {
    if (matcher.kind === "scan" && /^(read|grep|find|ls)$/i.test(toolName)) {
      matches.push({ kind: "scan", command, index: 0, rank });
      return;
    }
    if (matcher.kind === "scan") {
      if (toolName === "bash") {
        const scanIndex = command.search(/\b(?:rg|grep|find|ls)\b\s+/i);
        if (scanIndex >= 0) matches.push({ kind: "scan", command, index: scanIndex, rank });
      }
      return;
    }
    const index = matchIndex(matcher.pattern, haystack);
    if (index !== null) matches.push({ kind: matcher.kind, command, index, rank });
  });

  if (/\bbrave[-_ ]search\b/i.test(toolName)) matches.push({ kind: "brave", command, index: 0, rank: 7 });
  if (/\bdogpile\b/i.test(toolName)) matches.push({ kind: "dogpile", command, index: 0, rank: 8 });
  if (/\btriage[-_ ]error\b/i.test(toolName)) matches.push({ kind: "triage_error", command, index: 0, rank: 9 });

  matches.sort((a, b) => a.index - b.index || a.rank - b.rank);
  const seen = new Set<ObservationKind>();
  const classified = [];
  for (const match of matches) {
    if (seen.has(match.kind)) continue;
    seen.add(match.kind);
    classified.push({ kind: match.kind, command: match.command });
  }
  return classified.length ? classified : [{ kind: "other", command }];
}

function isGuardGeneratedText(text: string): boolean {
  return /^\s*(?:🦥|🔁)?\s*(?:PI_GUARD_STATUS|REJECTED_BY_SLOTH_COURT|REJECTED_BY_RESEARCH_ROUTING_GATE|UNLAZY_FORCED_RETRY|RESEARCH_ROUTING_GATE_RETRY|CONTINUE_OBVIOUS_NEXT_STEP|CONTINUING_OBVIOUS_NEXT_STEP)\b/i.test(text);
}

function check(userText: string, assistantText: string, observations: Observation[], enabled: boolean): CheckResult {
  const result = spawnSync("node", [CHECKER], {
    input: JSON.stringify({ user_text: userText, assistant_text: assistantText, observations, enabled }),
    encoding: "utf8",
    timeout: 5000,
  });
  if (result.error) {
    return { schema: "pi_research_gate.check.v1", checker_version: "unknown", decision: "error", reason_codes: ["checker_spawn_error"], route: {}, evidence: {}, counts: {} };
  }
  try {
    const parsed = JSON.parse(String(result.stdout || "{}"));
    if (parsed?.schema === "pi_research_gate.check.v1") return parsed;
  } catch {}
  return { schema: "pi_research_gate.check.v1", checker_version: "unknown", decision: "error", reason_codes: ["checker_output_unparseable"], route: {}, evidence: {}, counts: {} };
}

function missingGateNames(checkResult: CheckResult): string[] {
  return checkResult.reason_codes.filter((code) => code.startsWith("missing_") || code.endsWith("_not_first_gate"));
}

function rejection(checkResult: CheckResult, queuedFollowUp: boolean, claimReason?: string): string {
  const missing = missingGateNames(checkResult);
  return `PI_GUARD_STATUS\n${JSON.stringify({
    schema: "pi_guard_status.v1",
    guard: "research-routing",
    status: "held",
    missing_reason_codes: missing.length ? missing : checkResult.reason_codes,
    checker_version: checkResult.checker_version,
    first_relevant_kind: String(checkResult.evidence?.first_relevant_kind ?? "none"),
    follow_up: {
      queued: queuedFollowUp,
      skipped_reason: queuedFollowUp ? null : (claimReason || "retry_budget_exhausted"),
    },
  }, null, 2)}`;
}

function legalCommandFor(reasonCode: string, userText: string): string {
  const prompt = userText || "research-routing gate retry";
  const triageText = `Research-routing missing gate for user task:\n${prompt}`;
  if (reasonCode === "missing_memory_recall_gate" || reasonCode === "memory_recall_not_first_gate") {
    return `cd /home/graham/workspace/experiments/agent-skills && skills/memory/run.sh recall --q ${JSON.stringify(prompt)} --brief`;
  }
  if (reasonCode === "missing_brave_search_gate") {
    return `cd /home/graham/workspace/experiments/agent-skills && skills/brave-search/run.sh web ${JSON.stringify(prompt)} --count 5`;
  }
  if (reasonCode === "missing_dogpile_gate") {
    return `cd /home/graham/workspace/experiments/agent-skills && skills/dogpile/run.sh search ${JSON.stringify(prompt)} --output-dir /tmp/pi-research-gate-dogpile`;
  }
  if (reasonCode === "missing_tau_or_triage_error_gate") {
    return `cd /home/graham/workspace/experiments/agent-skills && skills/triage-error/run.sh classify --text ${JSON.stringify(triageText)}`;
  }
  if (reasonCode === "missing_ask_webgpt_gate") {
    return `cd /home/graham/workspace/experiments/agent-skills && skills/ask/run.sh webgpt ${JSON.stringify(`Review this bounded question and return one answer with cited uncertainty: ${prompt}`)}`;
  }
  if (reasonCode === "missing_ask_fast_single_gate") {
    return `cd /home/graham/workspace/experiments/agent-skills && skills/ask/run.sh tau-dag ${JSON.stringify(`Exact user task:\n${prompt}\n\nReturn one likely cause, one next command, or NEEDS_ATTENTION.`)} --repo local/agent-skills --target broad-error-triage --immutable-goal "Return one likely cause, one next command, or NEEDS_ATTENTION." --handler claude-fable-low --execute --json`;
  }
  if (reasonCode === "missing_ask_roundtable_gate") {
    return `cd /home/graham/workspace/experiments/agent-skills && skills/ask/run.sh tau-dag ${JSON.stringify(`Shared context and decision question:\n${prompt}`)} --repo local/agent-skills --target research-routing-gate --immutable-goal "A receipt-backed recommendation with dissent surfaced" --dag-template roundtable --handler webgpt --handler claude-fable-high --handler gpt-5.5-high --topology concurrent --execute --json`;
  }
  if (reasonCode === "missing_ask_compete_gate") {
    return `cd /home/graham/workspace/experiments/agent-skills && skills/ask/run.sh compete ${JSON.stringify(`Isolated candidate task:\n${prompt}`)} --repo local/agent-skills --target research-routing-gate --immutable-goal "Select only a locally checkable winner or NO_WINNER" --handler webgpt --handler claude-fable-high --criterion deterministic-proof --execute --json`;
  }
  if (reasonCode === "missing_mvp_isolated_challenge_gate") {
    return `cd /home/graham/workspace/experiments/agent-skills && mkdir -p mvp/001-research-routing-gate && printf '%s\\n' ${JSON.stringify(prompt)} > mvp/001-research-routing-gate/goal.md && printf '%s\\n' '#!/usr/bin/env bash' 'set -euo pipefail' 'test -s goal.md' > mvp/001-research-routing-gate/run.sh && chmod +x mvp/001-research-routing-gate/run.sh && (cd mvp/001-research-routing-gate && ./run.sh && printf '{"ok":true}\\n' > receipt.json)`;
  }
  return `cd /home/graham/workspace/experiments/agent-skills && skills/triage-error/run.sh classify --text ${JSON.stringify(triageText)}`;
}

type RetryArtifacts = { receiptPath: string; scriptPath: string; commands: Array<{ reason: string; command: string }> };

function writeRetryReceipt(userText: string, checkResult: CheckResult): RetryArtifacts {
  const dir = join(tmpdir(), "pi-research-routing");
  mkdirSync(dir, { recursive: true });
  const hash = createHash("sha256").update(`${userText}\n${JSON.stringify(checkResult)}`).digest("hex").slice(0, 16);
  const receiptPath = join(dir, `${Date.now()}-${hash}.json`);
  const scriptPath = join(dir, `${Date.now()}-${hash}.sh`);
  const missing = missingGateNames(checkResult);
  const commands = missing.map((reason) => ({ reason, command: legalCommandFor(reason, userText) }));
  writeFileSync(scriptPath, ["#!/usr/bin/env bash", "set -euo pipefail", ...commands.map((entry) => entry.command), ""].join("\n"));
  chmodSync(scriptPath, 0o700);
  writeFileSync(receiptPath, JSON.stringify({
    schema: "pi_research_gate.retry_receipt.v1",
    created_at: new Date().toISOString(),
    user_text: userText,
    check_result: checkResult,
    missing_reason_codes: missing,
    run_script: scriptPath,
    next_commands: commands,
  }, null, 2));
  return { receiptPath, scriptPath, commands };
}

function retryPrompt(userText: string, checkResult: CheckResult): string {
  const missing = missingGateNames(checkResult);
  let artifacts: RetryArtifacts = { receiptPath: "not_written", scriptPath: "not_written", commands: [] };
  try { artifacts = writeRetryReceipt(userText, checkResult); } catch {}
  return `RESEARCH_ROUTING_GATE_RETRY\n${JSON.stringify({
    schema: "pi_research_gate.retry_prompt.v1",
    missing_reason_codes: missing.length ? missing : checkResult.reason_codes,
    run_script: artifacts.scriptPath,
    receipt_path: artifacts.receiptPath,
    next_commands: artifacts.commands,
  }, null, 2)}`;
}

export default function researchRoutingGates(pi: any) {
  let enabled = !/^(0|false|off|no)$/i.test(process.env.PI_RESEARCH_GATES_ENABLED || "1");
  let userText = "";
  let observations: Observation[] = [];
  let retrying = false;

  pi.on("input", async (event: any) => {
    const incomingText = String(event.text || "");
    if (event.source === "extension" || isGuardGeneratedText(incomingText)) {
      // A generated retry/continuation prompt starts a new evidence window. Keep
      // the original userText so routing still targets the user's task, but drop
      // observations from the failed attempt; otherwise a pre-retry scan keeps
      // causing memory_recall_not_first_gate even after the retry starts with
      // Memory. Some harness paths deliver guard follow-ups without source ===
      // "extension", so also key off the explicit guard marker.
      observations = [];
      retrying = true;
      return { action: "continue" };
    }
    userText = incomingText;
    beginGuardTurn(userText, event.source);
    observations = [];
    retrying = false;
    return { action: "continue" };
  });

  pi.on("before_agent_start", async (event: any) => {
    if (!enabled) return;
    return {
      systemPrompt: String(event.systemPrompt || "") + `\n\n[Research Routing Gates]\nFor substantive tasks, gates are machine evidence only. Start with $memory recall --brief or Memory /answer-/intent-/recall evidence. If the answer needs narrow current/external research, run $brave-search. If it needs comprehensive multi-source research, run $dogpile. If reporting BLOCKED, NEEDS_ATTENTION, timeout, or generic failure, run $triage-error or a $tau receipt. For broad/generic/ambiguous errors that need outside model sanity, use a fast non-browser low-reasoning Ask/Tau single-call from a different provider family before WebGPT or roundtable, usually --handler claude-fable-low. Use $ask webgpt for one bounded external review question, $ask roundtable for thrashing/milestone/high-stakes/strategic next-step deliberation after fast triage is insufficient, and $ask compete for two or more concrete candidate approaches or implementations. For MVP-first or unproven integration seams, create/read project mvp/NNN-name proof artifacts before broad implementation. Never claim a gate passed in prose; preserve commands, JSON, reports, or receipt paths.`, 
    };
  });

  pi.on("tool_call", async (event: any) => {
    for (const classified of classifyCommands(String(event.toolName || ""), event.input || {})) {
      observations.push({ phase: "call", kind: classified.kind, toolName: String(event.toolName || ""), toolCallId: String(event.toolCallId || ""), command: classified.command });
    }
  });

  pi.on("tool_result", async (event: any) => {
    for (const classified of classifyCommands(String(event.toolName || ""), event.input || {})) {
      observations.push({ phase: "result", kind: classified.kind, toolName: String(event.toolName || ""), toolCallId: String(event.toolCallId || ""), command: classified.command, ok: event.isError !== true });
    }
  });

  pi.on("message_end", async (event: any) => {
    if (event.message?.role !== "assistant") return;
    if (retrying && observations.length === 0) return;
    const assistantText = textFromContent(event.message.content);
    if (!assistantText.trim() || isGuardGeneratedText(assistantText)) return;
    const result = check(userText, assistantText, observations, enabled);
    if (result.decision === "error") return;
    if (result.decision !== "reject") return;
    const alreadyRetrying = retrying;
    retrying = true;
    const pipelineClaim = claimGuardFollowUp({
      guard: "research-routing",
      messageId: String(event.message.id || event.id || "research-routing-message"),
      assistantText,
      userText,
      reason: result.reason_codes.join(","),
      maxRetries: 1,
    });
    if (!alreadyRetrying && pipelineClaim.ok) {
      const prompt = retryPrompt(userText, result);
      try { pi.sendUserMessage(prompt, { deliverAs: "followUp", expandPromptTemplates: false }); }
      catch { try { pi.sendUserMessage(prompt, { expandPromptTemplates: false }); } catch {} }
    }
    if (!pipelineClaim.ok && pipelineClaim.reason === "message_already_claimed") return;
    return { message: { ...event.message, content: [{ type: "text", text: rejection(result, Boolean(!alreadyRetrying && pipelineClaim.ok), pipelineClaim.reason) }] } };
  });

  pi.registerCommand("research-gates", {
    description: "Toggle deterministic Memory/Brave/Dogpile/Tau/Triage routing gates",
    handler: async (args: string, ctx: any) => {
      const arg = String(args || "status").trim().toLowerCase();
      if (arg === "on") enabled = true;
      else if (arg === "off") enabled = false;
      else if (arg === "toggle") enabled = !enabled;
      ctx.ui.notify(`Research routing gates: ${enabled ? "on" : "off"}. Gates require machine receipts, not prose.`, enabled ? "info" : "warning");
    },
  });
}
