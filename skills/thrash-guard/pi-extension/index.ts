// pi-thrash-guard: when the agent (or a subagent) thrashes — multiple repeated
// errors, or the same command retried with no progress — block further mutating
// tool calls until it diagnoses with triage-error (which shadows Jev) and/or
// web/brave search. Detection is deterministic (detector.mjs), never model
// judgment (best-practices-pi-extensions: desperation guards must be
// deterministic). Reads are never blocked, so investigation is always allowed.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const { ThrashDetector } = await import(
  join(dirname(fileURLToPath(import.meta.url)), "detector.mjs")
) as any;

export default function (pi: ExtensionAPI) {
  const detector = new ThrashDetector({
    window: Number(process.env.THRASH_GUARD_WINDOW ?? 6),
    threshold: Number(process.env.THRASH_GUARD_THRESHOLD ?? 3),
  });

  pi.on("tool_result", async (event: any) => {
    detector.recordResult(event?.isError);
  });

  pi.on("tool_call", async (event: any, ctx: any) => {
    const verdict = detector.inspectCall(event?.toolName, event?.input ?? {});
    if (verdict?.cleared) {
      ctx?.ui?.notify?.("thrash-guard: diagnosis observed; lock cleared", "info");
      return;
    }
    if (verdict?.block) {
      ctx?.ui?.notify?.("thrash-guard blocked a mutating call — diagnose first", "warn");
      return { block: true, reason: verdict.reason };
    }
    return;
  });
}
