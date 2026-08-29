#!/usr/bin/env node
// Claude Code Stop hook: when a Claude session finishes a turn, check its
// bridge inbox. If unread messages exist, block the stop with a reason that
// tells Claude to read them (via `bridge-cli.mjs inbox --key <session_id>
// --consume`) and act on them. With an empty inbox this is a silent no-op.
//
// Stop-hook contract: JSON on stdin includes {"session_id": ...}; printing
// {"decision":"block","reason":...} makes Claude continue instead of stopping.
import { readInbox } from "./inbox.mjs";

let raw = "";
process.stdin.setEncoding("utf-8");
for await (const chunk of process.stdin) raw += chunk;

let sessionId = null;
try {
  sessionId = JSON.parse(raw).session_id ?? null;
} catch {
  // no parseable payload -> nothing to check
}
if (!sessionId) process.exit(0);

// Prevent a block loop: if the transcript shows we already blocked once for
// this stop, stop_hook_active is true and we must allow the stop.
let stopHookActive = false;
try {
  stopHookActive = JSON.parse(raw).stop_hook_active === true;
} catch {
  // already handled above
}

const key = String(sessionId).replace(/[^a-zA-Z0-9._-]+/g, "_");
const { path, entries } = readInbox(key);
if (entries.length === 0 || stopHookActive) process.exit(0);

const preview = entries
  .slice(-5)
  .map((e) => `- from ${e.from ?? "unknown"} via ${e.lane ?? "?"}: ${String(e.text ?? "").slice(0, 200)}`)
  .join("\n");

process.stdout.write(JSON.stringify({
  decision: "block",
  reason:
    `You have ${entries.length} unread bridge message(s) from other agent sessions in ${path}.\n`
    + `${preview}\n`
    + `Read and consume them with: node ${new URL("./bridge-cli.mjs", import.meta.url).pathname} inbox --key ${key} --consume\n`
    + `Then act on each message (answer the question, note the handoff, or reply via the bridge send command) before stopping.`,
}));
process.exit(0);
