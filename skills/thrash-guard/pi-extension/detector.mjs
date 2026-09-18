// Pure, deterministic thrash detection. No pi imports so it is unit-testable.
//
// Two signals, because real thrash is not only tool errors:
//   1. errors        — tool_result.isError within a rolling window.
//   2. repetition    — the same normalized command issued N times in a window
//                      (the "keeps trying variants that return OK but do not
//                      work" pattern; e.g. repeated `surf click`/`surf js`
//                      that report OK but change nothing).
// Either signal at/above THRESHOLD within WINDOW engages the lock. A diagnostic
// call (triage-error classify / web_search / brave-search) clears it.

export const MUTATING = new Set(["bash", "edit", "write"]);

export function normalizeSignature(toolName, input) {
  if (toolName === "bash") {
    const cmd = String(input?.command ?? "");
    // Key on the command VERB (program + first subcommand), not the args.
    // Thrash retries vary the args/selector (e.g. `surf click <sel> --tab-id N`),
    // so collapsing to the verb is what makes repeats detectable. Skip leading
    // env-assignments and `cd x &&` prefixes to reach the real program.
    const toks = cmd
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim()
      .split(" ")
      .filter((t) => t && !t.includes("=") && t !== "&&" && t !== "cd" && t !== "sudo");
    return "bash:" + toks.slice(0, 2).join(" ");
  }
  if (toolName === "edit" || toolName === "write") {
    return toolName + ":" + String(input?.path ?? "");
  }
  return toolName + ":" + JSON.stringify(input ?? {}).slice(0, 40);
}

export function isDiagnosticCall(toolName, input) {
  if (toolName === "web_search" || toolName === "source_check") return true;
  if (typeof toolName === "string" && toolName.startsWith("brave_")) return true;
  const cmd = String(input?.command ?? "");
  if (/triage-error\/run\.sh\s+(classify|triage)/.test(cmd)) return true;
  if (/triage_error\.py\s+(classify|triage)/.test(cmd)) return true;
  if (/brave_search\.py\s+(web|context|local)/.test(cmd)) return true;
  return false;
}

export class ThrashDetector {
  constructor({ window = 6, threshold = 3 } = {}) {
    this.window = window;
    this.threshold = threshold;
    this.errors = []; // rolling booleans
    this.sigs = []; // rolling signatures
    this.locked = false;
  }

  // Call on every tool_result.
  recordResult(isError) {
    this.errors.push(Boolean(isError));
    while (this.errors.length > this.window) this.errors.shift();
    if (!this.locked && this.errorCount() >= this.threshold) this.locked = true;
    return this.locked;
  }

  // Call on every tool_call (before execution). Returns {block, reason} or null.
  // Also updates repetition tracking and clears the lock on a diagnostic call.
  inspectCall(toolName, input) {
    if (isDiagnosticCall(toolName, input)) {
      const wasLocked = this.locked;
      this.reset();
      return wasLocked ? { cleared: true } : null;
    }

    // repetition signal
    this.sigs.push(normalizeSignature(toolName, input));
    while (this.sigs.length > this.window) this.sigs.shift();
    if (!this.locked && this.maxRepeat() >= this.threshold) this.locked = true;

    if (this.locked && MUTATING.has(toolName)) {
      return {
        block: true,
        reason:
          `thrash-guard: ${this.errorCount()} errors / up to ${this.maxRepeat()} repeated ` +
          `signatures in the last ${this.window} calls. Stop guessing. Climb the ladder ` +
          `cheapest-first; stop at the first tier that resolves:\n` +
          `  Tier 0 (cheap/fast, Jev): skills/triage-error/run.sh classify --text "<failing signal>" --layer <layer> ` +
          `-> typed {code,cause,next_command} (Jev shadow). Catalog hit -> apply next_command and retry.\n` +
          `  Tier 1 (web): web_search / brave-search the failing signal for a known cause/fix.\n` +
          `  Tier 2 (bigger model): dispatch a subagent (openai-codex/gpt-5.5:high) with full context to diagnose and propose a fix.\n` +
          `  Tier 3 (browser reviewer): $ask webgpt with COMPREHENSIVE context (failing signal, what was tried, relevant code) for a fix.\n` +
          `  Tier 4 (implement): hand the agreed fix to a subagent (claude-sonnet-5) to implement in code, then verify by reading back the effect.\n` +
          `Running any Tier 0/1 diagnostic clears this lock. Then retry ${toolName}.`,
      };
    }
    return null;
  }

  errorCount() {
    return this.errors.filter(Boolean).length;
  }

  maxRepeat() {
    const counts = new Map();
    let max = 0;
    for (const s of this.sigs) {
      const n = (counts.get(s) ?? 0) + 1;
      counts.set(s, n);
      if (n > max) max = n;
    }
    return max;
  }

  reset() {
    this.errors = [];
    this.sigs = [];
    this.locked = false;
  }
}
