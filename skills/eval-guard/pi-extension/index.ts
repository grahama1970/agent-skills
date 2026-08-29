// pi-eval-guard: deterministic completion-claim and failure-report guard.
// On message_end, the assistant's final prose is judged by checker.mjs — never
// by the model itself (best-practices-pi-extensions "desperation guards must
// be deterministic"). Violations reject the answer and queue a forced retry
// with the checker's exact diagnostics.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const CHECKER = join(dirname(fileURLToPath(import.meta.url)), "..", "checker.mjs");

function runChecker(messageFile: string, extra: string[]): Promise<{ ok: boolean; violations: Array<{ code: string; cause: string; next_command: string }> }> {
  return new Promise((resolvePromise) => {
    execFile("node", [CHECKER, "--message-file", messageFile, ...extra], (error, stdout) => {
      try {
        resolvePromise(JSON.parse(stdout));
      } catch {
        // Checker crash must not eat the session; fail open but visibly.
        resolvePromise({ ok: true, violations: [] });
      }
    });
  });
}

export default function (pi: ExtensionAPI) {
  pi.on("message_end", async (event: any, ctx: any) => {
    const text: string = event?.message?.content
      ?.filter((b: any) => b.type === "text")
      .map((b: any) => b.text)
      .join("\n") ?? "";
    if (!text.trim()) return;

    const dir = mkdtempSync(join(tmpdir(), "eval-guard-"));
    const messageFile = join(dir, "message.txt");
    writeFileSync(messageFile, text);

    const extra: string[] = [];
    const skillDir = process.env.EVAL_GUARD_SKILL_DIR;
    const report = process.env.EVAL_GUARD_REPORT;
    if (skillDir) extra.push("--skill-dir", skillDir);
    if (report) extra.push("--report", report);

    const verdict = await runChecker(messageFile, extra);
    if (verdict.ok) return;

    const diagnostics = verdict.violations
      .map((v) => `- ${v.code}: ${v.cause}\n  next: ${v.next_command}`)
      .join("\n");
    ctx.ui?.notify?.(`eval-guard rejected the answer: ${verdict.violations.map((v) => v.code).join(", ")}`);
    pi.sendUserMessage(
      `Your last answer was rejected by the deterministic eval-guard checker:\n${diagnostics}\n`
      + `Rules: a works/complete claim needs a fresh /agentic-evals receipt with a real_world case; `
      + `a failure report needs a strict \`Triage: <code>\` line from /triage-error, not prose. `
      + `Fix the answer accordingly — run the named commands, or downgrade the claim to unverified.`,
      { deliverAs: "followUp" },
    );
  });
}
