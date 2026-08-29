import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { appendInbox, readInbox, inboxKey } from "../inbox.mjs";

const HOOK = new URL("../claude-stop-hook.mjs", import.meta.url).pathname;

function runHook(env, input) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn("node", [HOOK], { env });
    let stdout = "";
    child.stdout.on("data", (d) => { stdout += d; });
    child.on("error", reject);
    child.on("close", (code) => resolvePromise({ stdout, code }));
    child.stdin.end(input);
  });
}

test("inboxKey prefers session ref, sanitizes", () => {
  assert.equal(inboxKey({ sessionRef: { value: "abc-123" }, paneId: "w1:p1" }), "abc-123");
  assert.equal(inboxKey({ sessionRef: null, paneId: "w1:p1" }), "w1_p1");
});

test("append then read then consume archives the file", () => {
  const dir = mkdtempSync(join(tmpdir(), "inbox-test-"));
  appendInbox("k1", { text: "hello", delivered: false }, dir);
  appendInbox("k1", { text: "again", delivered: true }, dir);
  const first = readInbox("k1", { dir });
  assert.equal(first.entries.length, 2);
  assert.equal(first.entries[0].text, "hello");
  const consumed = readInbox("k1", { consume: true, dir });
  assert.equal(consumed.entries.length, 2);
  assert.equal(readInbox("k1", { dir }).entries.length, 0);
  assert.ok(readdirSync(dir).some((f) => f.startsWith("k1.jsonl.consumed-")));
  assert.ok(!existsSync(join(dir, "k1.jsonl")));
});

test("stop hook is silent with empty inbox and blocks with pending messages", async () => {
  const dir = mkdtempSync(join(tmpdir(), "hook-test-"));
  const env = { ...process.env, PI_HERDR_BRIDGE_STATE: dir };
  const payload = JSON.stringify({ session_id: "sess-42" });

  const quiet = await runHook(env, payload);
  assert.equal(quiet.stdout, "");

  appendInbox("sess-42", { from: "codex-a", lane: "herdr-prompt", text: "need the schema", delivered: false }, join(dir, "inbox"));
  const blocked = await runHook(env, payload);
  const out = JSON.parse(blocked.stdout);
  assert.equal(out.decision, "block");
  assert.match(out.reason, /1 unread bridge message/);
  assert.match(out.reason, /need the schema/);
  assert.match(out.reason, /--key sess-42 --consume/);

  const rearmed = await runHook(env, JSON.stringify({ session_id: "sess-42", stop_hook_active: true }));
  assert.equal(rearmed.stdout, "");
});

test("herdr-prompt lane defers to inbox when pane is working", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gate-test-"));
  process.env.PI_HERDR_BRIDGE_STATE = dir;
  const { sendToTarget } = await import("../route.mjs");
  const roster = [{
    source: "herdr", provider: "claude", name: "busy pane", paneId: "w9:p9",
    cwd: "/x", status: "working",
    sessionRef: { kind: "id", value: "claude-busy-1", refSource: "herdr:claude" },
  }];
  const result = await sendToTarget("busy pane", "are you done?", { rosterOverride: roster, fromName: "tester" });
  assert.equal(result.ok, true);
  assert.equal(result.deferred, true);
  assert.equal(result.delivered, false);
  const inbox = readInbox("claude-busy-1", { dir: join(dir, "inbox") });
  assert.equal(inbox.entries.length, 1);
  assert.equal(inbox.entries[0].deferred, true);
  delete process.env.PI_HERDR_BRIDGE_STATE;
});
