#!/usr/bin/env node
/** Exercise the production message_end/agent_end path with no stop-review bridge. */
import { rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const stem = "/tmp/shame-review-unavailable-course-correction";
process.env.LAZY_REPORT_SHAME_MEMORY_ENABLED = "0";
process.env.LAZY_REPORT_SHAME_AUDIO_ENABLED = "0";
process.env.LAZY_REPORT_SHAME_DEFAULT_MODE = "normal";
process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET = `${stem}-pending.json`;
process.env.LAZY_REPORT_SHAME_FAILURE_LOG = `${stem}-failures.jsonl`;
process.env.LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE = `${stem}-no-ledger.json`;
rmSync(`${stem}-pending.json.sessions`, { recursive: true, force: true });
writeFileSync(`${stem}-proof.txt`, "direct proof ok\n");
delete globalThis[Symbol.for("pi-subagents.stop-review")];

const { default: install } = await import(`${ROOT}/extensions/pi/lazy-report-shame-shame-shame/index.ts`);
const handlers = {};
const followUps = [];
const pi = {
  on(name, fn) { (handlers[name] ??= []).push(fn); },
  registerCommand() {},
  registerTool() {},
  appendEntry() {},
  sendUserMessage(text, options) { followUps.push({ text, options }); },
};
install(pi);
const ctx = {
  cwd: "/tmp",
  signal: { aborted: false },
  hasPendingMessages() { return false; },
  ui: { notify() {}, setStatus() {} },
  sessionManager: {
    getSessionId() { return "review-unavailable-course-correction"; },
    getSessionFile() { return `${stem}-session.jsonl`; },
  },
};
for (const fn of handlers.input ?? []) await fn({ text: "show the verified result", source: "user" }, ctx);
const status = {
  schema: "pi.agent_status.v1",
  goal: "prove missing reviewer course correction",
  state: "done",
  changed: ["no change: eval"],
  plain_answer: "The direct proof is ok.",
  verified: [{ command: `read ${stem}-proof.txt`, result: "direct proof ok" }],
  proof: [`${stem}-proof.txt`],
};
const event = {
  id: "assistant-eval",
  message: {
    id: "assistant-eval",
    role: "assistant",
    stopReason: "stop",
    provider: "openai-codex",
    model: "gpt-5.5",
    content: [{ type: "text", text: `Result.\n\`\`\`json\n${JSON.stringify(status)}\n\`\`\`` }],
  },
};
let replacement;
for (const fn of handlers.message_end ?? []) replacement = await fn(event, ctx);
for (const fn of handlers.agent_end ?? []) await fn({}, ctx);

if (!replacement || !Array.isArray(replacement.message?.content) || replacement.message.content.length !== 0) {
  throw new Error("unreviewed terminal response was not suppressed");
}
if (followUps.length !== 1 || !followUps[0].text.startsWith("SHAME_HARNESS_COURSE_CORRECTION")) {
  throw new Error("harness course correction was not queued");
}
if (!followUps[0].text.includes("do not create, attach, or discuss review proof")) {
  throw new Error("review repair was delegated to the agent");
}

for (const fn of handlers.input ?? []) await fn({ text: followUps[0].text, source: "extension" }, ctx);
const repeatedEvent = { ...event, id: "assistant-eval-retry", message: { ...event.message, id: "assistant-eval-retry" } };
let repeatedReplacement;
for (const fn of handlers.message_end ?? []) repeatedReplacement = await fn(repeatedEvent, ctx);
for (const fn of handlers.agent_end ?? []) await fn({}, ctx);
if (!repeatedReplacement || repeatedReplacement.message?.content?.length !== 0) {
  throw new Error("repeated unreviewed terminal response was not suppressed");
}
if (followUps.length !== 1) {
  throw new Error("missing reviewer caused an infinite harness course-correction loop");
}

console.log(JSON.stringify({
  schema: "lazy_report_shame.review_unavailable_course_correction_eval.v1",
  status: "PASS",
  unreviewed_terminal_suppressed: true,
  harness_course_correction_queued: true,
  repeat_course_correction_suppressed: true,
  agent_review_repair_forbidden: true,
}, null, 2));
