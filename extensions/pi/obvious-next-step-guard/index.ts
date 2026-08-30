// Continue when a final answer names an obvious unblocked next step or reports an unblocked failure.
// Global Pi extension. Reload Pi with /reload after editing.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beginGuardTurn, claimGuardFollowUp } from "../guard-pipeline-shared.ts";

const EXTENSION_DIR = dirname(fileURLToPath(import.meta.url));
const CHECKER = join(EXTENSION_DIR, "obvious-next-step-check.mjs");
const DEFAULT_MAX_FOLLOWUPS = 3;
const MAX_EXCERPT_CHARS = 5_000;
const FAILED_TOOL_EXCERPT_CHARS = 1_200;

type CheckDecision = "pass" | "follow_up" | "error";

type CheckResult = {
  schema: "obvious_next_step_guard.check.v1";
  checker_version: string;
  decision: CheckDecision;
  reason_codes: string[];
  actions: string[];
  actionable_actions: string[];
  features: Record<string, unknown>;
  diagnostics?: string;
};

type RecentFailure = {
  toolName: string;
  command: string;
  excerpt: string;
  at: number;
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

function sha256(value: string): string {
  return "sha256:" + createHash("sha256").update(value).digest("hex");
}

function boolEnv(name: string, defaultValue: boolean): boolean {
  const value = process.env[name];
  if (value === undefined) return defaultValue;
  return /^(1|true|yes|on)$/i.test(value);
}

function intEnv(name: string, defaultValue: number): number {
  const raw = process.env[name];
  if (!raw) return defaultValue;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : defaultValue;
}

function parseCheckerPayload(stdout: string, stderr: string, status: number | null): CheckResult {
  let payload: any = null;
  try { payload = JSON.parse(String(stdout || "{}")); } catch { payload = null; }
  if (payload?.schema === "obvious_next_step_guard.check.v1") {
    return {
      schema: payload.schema,
      checker_version: String(payload.checker_version || "unknown"),
      decision: ["pass", "follow_up", "error"].includes(payload.decision) ? payload.decision : "error",
      reason_codes: Array.isArray(payload.reason_codes) ? payload.reason_codes.map(String) : [],
      actions: Array.isArray(payload.actions) ? payload.actions.map(String) : [],
      actionable_actions: Array.isArray(payload.actionable_actions) ? payload.actionable_actions.map(String) : [],
      features: payload.features && typeof payload.features === "object" ? payload.features : {},
      diagnostics: String(stderr || stdout || "").trim(),
    };
  }
  return {
    schema: "obvious_next_step_guard.check.v1",
    checker_version: "unknown",
    decision: "error",
    reason_codes: ["checker_output_unparseable"],
    actions: [],
    actionable_actions: [],
    features: { exit_status: status },
    diagnostics: String(stderr || stdout || "obvious-next-step checker failed without diagnostics").trim(),
  };
}

function checkObviousNextStep(text: string): CheckResult {
  const result = spawnSync("node", [CHECKER], {
    input: text,
    encoding: "utf8",
    timeout: 5_000,
    env: process.env,
  });
  if (result.error) {
    return {
      schema: "obvious_next_step_guard.check.v1",
      checker_version: "unknown",
      decision: "error",
      reason_codes: ["checker_spawn_error"],
      actions: [],
      actionable_actions: [],
      features: {},
      diagnostics: String(result.error.message || result.error),
    };
  }
  return parseCheckerPayload(String(result.stdout || ""), String(result.stderr || ""), result.status);
}

function truncate(text: string): string {
  if (text.length <= MAX_EXCERPT_CHARS) return text;
  return text.slice(0, MAX_EXCERPT_CHARS) + `\n\n[truncated by obvious-next-step-guard at ${MAX_EXCERPT_CHARS} chars]`;
}

function continuationNotice(check: CheckResult, used: number, max: number): string {
  const action = check.actionable_actions[0] || check.actions[0] || "(no action extracted)";
  return `🔁 CONTINUING_OBVIOUS_NEXT_STEP

The assistant named unfinished work or reported an unblocked failure and did not name a verified blocker, so Pi queued a follow-up instead of stopping.

Checker version: ${check.checker_version}
Reason codes: ${check.reason_codes.join(", ") || "none"}
Continuation budget: ${used}/${max}
Detected next action: ${action}`;
}

function continuationPrompt(previousAnswer: string, check: CheckResult, failure?: RecentFailure | null): string {
  const action = check.actionable_actions[0] || check.actions[0] || "the concrete next step you named";
  const excerpt = truncate(previousAnswer.trim());
  const failureContext = failure
    ? `\n\nLatest failed tool receipt:\n- tool: ${failure.toolName}\n- command: ${failure.command || "(not captured)"}\n- output excerpt:\n> ${failure.excerpt.replace(/\n/g, "\n> ")}`
    : "";
  return `CONTINUE_OBVIOUS_NEXT_STEP

Your previous answer named unfinished work or reported an unblocked failure with no verified blocker. Do not final-answer yet.

Execute this next action now:
${action}

If the action is genuinely blocked, prove the blocker with the required deterministic gate (for example triage-error or a Tau/Ask receipt when route policy requires it) and report the exact blocker. Otherwise continue until the action is completed and verified.${failureContext}

Previous answer excerpt:
${excerpt ? `> ${excerpt.replace(/\n/g, "\n> ")}` : "> (no text extracted)"}`;
}

function failedToolFromEvent(event: any): RecentFailure | null {
  const toolName = String(event?.toolName || "");
  const command = String(event?.input?.command || event?.input?.code || event?.input?.path || "");
  const text = contentToText(event?.content || event?.result?.content || event?.output || event?.result || "");
  const failed = event?.isError === true || /\bCommand exited with code\s+[1-9]\d*\b/i.test(text) || /\bexit(?:ed)?\s+(?:code|status)\s+[1-9]\d*\b/i.test(text);
  if (!failed) return null;
  return {
    toolName,
    command,
    excerpt: truncate(text || "(no tool output captured)").slice(0, FAILED_TOOL_EXCERPT_CHARS),
    at: Date.now(),
  };
}

export default function obviousNextStepGuard(pi: any) {
  const enabled = boolEnv("OBVIOUS_NEXT_STEP_GUARD_ENABLED", true);
  const maxFollowups = intEnv("OBVIOUS_NEXT_STEP_MAX_FOLLOWUPS", DEFAULT_MAX_FOLLOWUPS);
  let rootUserText = "";
  let recentFailure: RecentFailure | null = null;
  let extensionControlTurn = false;
  const followupsByRoot = new Map<string, number>();

  pi.on("input", async (event: any) => {
    if (event.source === "extension") {
      extensionControlTurn = true;
      return { action: "continue" };
    }
    rootUserText = String(event.text || "");
    beginGuardTurn(rootUserText, event.source);
    recentFailure = null;
    extensionControlTurn = false;
    return { action: "continue" };
  });

  pi.on("tool_result", async (event: any) => {
    const failure = failedToolFromEvent(event);
    if (failure) recentFailure = failure;
    else if (event?.isError !== true) recentFailure = null;
  });

  pi.on("message_end", async (event: any, ctx: any) => {
    if (!enabled) return;
    if (event.message?.role !== "assistant") return;
    if (extensionControlTurn) {
      extensionControlTurn = false;
      return;
    }

    const text = contentToText(event.message.content);
    const check = checkObviousNextStep(text);
    if (check.decision === "error") {
      ctx?.ui?.notify?.(`obvious-next-step-guard checker error: ${check.diagnostics || check.reason_codes.join(", ")}`, "warning");
      return;
    }
    if (check.decision !== "follow_up") return;

    const rootKey = sha256(rootUserText || text.slice(0, 500));
    const used = followupsByRoot.get(rootKey) || 0;
    if (used >= maxFollowups) {
      ctx?.ui?.notify?.(`obvious-next-step-guard follow-up budget exhausted (${used}/${maxFollowups})`, "warning");
      return;
    }
    const pipelineClaim = claimGuardFollowUp({
      guard: "obvious-next-step",
      messageId: String(event.message.id || event.id || rootKey),
      assistantText: text,
      userText: rootUserText,
      reason: check.reason_codes.join(","),
      maxRetries: maxFollowups,
    });
    if (!pipelineClaim.ok) {
      ctx?.ui?.notify?.(`obvious-next-step-guard skipped follow-up: ${pipelineClaim.reason}`, "warning");
      return;
    }
    const nextUsed = pipelineClaim.used;
    followupsByRoot.set(rootKey, nextUsed);

    try {
      pi.sendUserMessage(continuationPrompt(text, check, recentFailure), { deliverAs: "followUp", expandPromptTemplates: false });
    } catch (_error) {
      try {
        pi.sendUserMessage(continuationPrompt(text, check, recentFailure), { expandPromptTemplates: false });
      } catch {
        ctx?.ui?.notify?.("obvious-next-step-guard could not queue follow-up", "warning");
      }
    }

    return {
      message: {
        ...event.message,
        content: appendText(event.message.content, continuationNotice(check, nextUsed, maxFollowups)),
      },
    };
  });

  pi.registerCommand("obvious-next-step-guard", {
    description: "Show obvious-next-step guard status",
    handler: async (_args: string, ctx: any) => {
      ctx.ui.notify(`obvious-next-step-guard ${enabled ? "enabled" : "disabled"}; max follow-ups ${maxFollowups}`, enabled ? "info" : "warning");
    },
  });

  pi.registerCommand("reload-runtime", {
    description: "Reload extensions, skills, prompts, themes, and context files",
    handler: async (_args: string, ctx: any) => {
      await ctx.reload();
      return;
    },
  });
}
