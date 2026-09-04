import { createHash } from "node:crypto";

export type GuardName = "shame" | "research-routing" | "obvious-next-step" | "ralph-wiggum" | string;

type GuardClaim = {
  guard: GuardName;
  rootKey: string;
  messageKey: string;
  reason: string;
  at: number;
  used: number;
  max: number;
};

type PipelineState = {
  schema: "pi.guard_pipeline.v1";
  rootText: string;
  rootKey: string;
  retryCounts: Map<string, number>;
  claims: Map<string, GuardClaim>;
  order: GuardName[];
  turnCounter: number;
};

const GLOBAL_KEY = Symbol.for("pi.guardPipeline.v1");
const DEFAULT_ORDER = ["shame", "research-routing", "obvious-next-step", "ralph-wiggum"];

function sha256(value: string): string {
  return "sha256:" + createHash("sha256").update(value).digest("hex");
}

function state(): PipelineState {
  const globalObject = globalThis as typeof globalThis & { [GLOBAL_KEY]?: PipelineState };
  if (!globalObject[GLOBAL_KEY]) {
    globalObject[GLOBAL_KEY] = {
      schema: "pi.guard_pipeline.v1",
      rootText: "",
      rootKey: "",
      retryCounts: new Map<string, number>(),
      claims: new Map<string, GuardClaim>(),
      order: DEFAULT_ORDER,
      turnCounter: 0,
    };
  }
  return globalObject[GLOBAL_KEY]!;
}

// A message ending is not an agent stopping: replacing tool-call content here
// deletes the work Pi is about to execute. Errors/aborts belong to the host.
export function isAssistantStop(message: any): boolean {
  return message?.role === "assistant" && message.stopReason === "stop"
    && !message.content?.some?.((part: any) => part?.type === "toolCall");
}

export function resetGuardRepairBudget(): void {
  const s = state();
  s.retryCounts.delete(s.rootKey);
}

export function beginGuardTurn(userText: string, source?: string): void {
  if (source === "extension") return;
  const s = state();
  s.rootText = String(userText || "");
  s.turnCounter += 1;
  s.rootKey = `${sha256(s.rootText || String(Date.now()))}:turn:${s.turnCounter}`;
}

export function guardPipelineStatus(): { rootKey: string; retryCount: number; claims: GuardClaim[]; order: GuardName[] } {
  const s = state();
  return {
    rootKey: s.rootKey,
    retryCount: s.retryCounts.get(s.rootKey) || 0,
    claims: [...s.claims.values()],
    order: [...s.order],
  };
}

export function claimGuardFollowUp(args: {
  guard: GuardName;
  messageId?: string;
  assistantText?: string;
  userText?: string;
  reason?: string;
  maxRetries?: number;
  continuation?: boolean;
}): { ok: boolean; reason: "claimed" | "message_already_claimed" | "retry_budget_exhausted"; used: number; max: number; claimedBy?: GuardClaim } {
  const s = state();
  if (!s.rootKey) {
    s.rootText = String(args.userText || "");
    s.rootKey = sha256(s.rootText || String(args.assistantText || "").slice(0, 500));
  }
  const assistantText = String(args.assistantText || "").slice(0, 2000);
  // Coordinate guards by the visible assistant draft, not by each guard's
  // private fallback id. message_end hooks often receive no stable message id
  // in probes/headless sessions; if one guard falls back to "unknown" and
  // another to "research-routing-message", both used to claim and rewrite the
  // same draft. Text-hashing makes one visible draft have one owner.
  const messageKey = assistantText ? `${s.rootKey}:${sha256(assistantText)}` : `${s.rootKey}:${String(args.messageId || sha256("empty-message"))}`;
  const claimedBy = s.claims.get(messageKey);
  const max = Number.isFinite(args.maxRetries) ? Math.max(0, Number(args.maxRetries)) : 1;
  const used = s.retryCounts.get(s.rootKey) || 0;
  if (claimedBy) return { ok: false, reason: "message_already_claimed", used, max, claimedBy };
  if (!args.continuation && used >= max) return { ok: false, reason: "retry_budget_exhausted", used, max };
  const nextUsed = used + (args.continuation ? 0 : 1);
  const claim: GuardClaim = {
    guard: args.guard,
    rootKey: s.rootKey,
    messageKey,
    reason: String(args.reason || ""),
    at: Date.now(),
    used: nextUsed,
    max,
  };
  s.retryCounts.set(s.rootKey, nextUsed);
  s.claims.set(messageKey, claim);
  return { ok: true, reason: "claimed", used: nextUsed, max, claimedBy: claim };
}
