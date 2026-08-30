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
    };
  }
  return globalObject[GLOBAL_KEY]!;
}

export function beginGuardTurn(userText: string, source?: string): void {
  if (source === "extension") return;
  const s = state();
  s.rootText = String(userText || "");
  s.rootKey = sha256(s.rootText || String(Date.now()));
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
}): { ok: boolean; reason: "claimed" | "message_already_claimed" | "retry_budget_exhausted"; used: number; max: number; claimedBy?: GuardClaim } {
  const s = state();
  if (!s.rootKey) {
    s.rootText = String(args.userText || "");
    s.rootKey = sha256(s.rootText || String(args.assistantText || "").slice(0, 500));
  }
  const messageKey = String(args.messageId || sha256(String(args.assistantText || "").slice(0, 2000)));
  const claimedBy = s.claims.get(messageKey);
  const max = Number.isFinite(args.maxRetries) ? Math.max(0, Number(args.maxRetries)) : 1;
  const used = s.retryCounts.get(s.rootKey) || 0;
  if (claimedBy) return { ok: false, reason: "message_already_claimed", used, max, claimedBy };
  if (used >= max) return { ok: false, reason: "retry_budget_exhausted", used, max };
  const nextUsed = used + 1;
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
