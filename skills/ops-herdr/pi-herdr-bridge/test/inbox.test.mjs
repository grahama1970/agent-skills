import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readdirSync, appendFileSync, mkdirSync, existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { appendMessage, appendAck, readInbox, ackMessages, inboxKey } from "../inbox.mjs";
import { makeMessage, validateMessage, toMemoryDocument, MEMORY_COLLECTION } from "../schema.mjs";
import { mirrorMessages } from "../memory-mirror.mjs";

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

function msg(overrides = {}) {
  return makeMessage({
    from: { agent: "codex-a", provider: "codex", session_ref: "uuid-a" },
    to: { agent: "claude-b", provider: "claude", session_ref: "sess-42" },
    text: "need the schema",
    kind: "question",
    lane: "inbox-only",
    expectsReply: true,
    skillChain: { recommended: ["debugger", "ticket"] },
    artifacts: ["/tmp/work-order.md"],
    goal: "close ticket 1842",
    ...overrides,
  });
}

test("inboxKey prefers session ref, sanitizes", () => {
  assert.equal(inboxKey({ sessionRef: { value: "abc-123" }, paneId: "w1:p1" }), "abc-123");
  assert.equal(inboxKey({ sessionRef: null, paneId: "w1:p1" }), "w1_p1");
});

test("schema validates and rejects", () => {
  const m = msg();
  assert.deepEqual(validateMessage(m), []);
  assert.ok(validateMessage({ ...m, kind: "gossip" }).length > 0);
  assert.ok(validateMessage({ ...m, skill_chain: { recommended: "nope", final: [] } }).length > 0);
  assert.ok(validateMessage({ ...m, from: { provider: "codex" } }).length > 0);
});

test("append, per-message ack, archive on fully-read", () => {
  const dir = mkdtempSync(join(tmpdir(), "inbox-v1-"));
  const m1 = msg();
  const m2 = msg({ text: "second question" });
  appendMessage("k1", m1, dir);
  appendMessage("k1", m2, dir);

  let box = readInbox("k1", { dir });
  assert.equal(box.unread.length, 2);
  assert.equal(box.messages[0].read, false);

  const partial = ackMessages("k1", [m1.id], { by: "tester", dir });
  assert.deepEqual(partial.acked, [m1.id]);
  assert.equal(partial.remainingUnread, 1);
  assert.equal(partial.archived, null);

  box = readInbox("k1", { dir });
  assert.equal(box.messages.find((m) => m.id === m1.id).read, true);
  assert.equal(box.unread.length, 1);

  const full = ackMessages("k1", [], { by: "tester", dir });
  assert.deepEqual(full.acked, [m2.id]);
  assert.ok(full.archived);
  assert.ok(readdirSync(dir).some((f) => f.includes(".consumed-")));
  assert.equal(readInbox("k1", { dir }).messages.length, 0);
});

test("invalid records go to dead-letter, not the message list", () => {
  const dir = mkdtempSync(join(tmpdir(), "inbox-dead-"));
  mkdirSync(dir, { recursive: true });
  appendMessage("k2", msg(), dir);
  appendFileSync(join(dir, "k2.jsonl"), '{"schema":"bogus","x":1}\nnot even json\n');
  const box = readInbox("k2", { dir });
  assert.equal(box.messages.length, 1);
  assert.equal(box.dead, 2);
  assert.ok(existsSync(join(dir, "dead-letter.jsonl")));
  assert.equal(readFileSync(join(dir, "dead-letter.jsonl"), "utf-8").trim().split("\n").length, 2);
});

test("toMemoryDocument is arango-ready: _key, flat fields, no vectors", () => {
  const m = msg();
  const doc = toMemoryDocument(m, { acks: [{ msg_id: m.id, ts: 123, by: "claude-b" }] });
  assert.equal(doc._key, m.id);
  assert.equal(doc.from_agent, "codex-a");
  assert.equal(doc.to_session_ref, "sess-42");
  assert.deepEqual(doc.skill_chain_recommended, ["debugger", "ticket"]);
  assert.equal(doc.read, true);
  assert.equal(doc.read_by, "claude-b");
  assert.ok(!("embedding" in doc));
  assert.equal(MEMORY_COLLECTION, "bridge_messages");
});

test("mirrorMessages posts to /upsert and fails soft", async () => {
  const m = msg();
  const calls = [];
  const okFetch = async (url, init) => {
    calls.push({ url, body: JSON.parse(init.body) });
    return { ok: true, status: 200, text: async () => '{"ok":true}' };
  };
  const good = await mirrorMessages([m], { baseUrl: "http://fake:1", fetchImpl: okFetch });
  assert.equal(good.ok, true);
  assert.equal(good.mirrored, 1);
  assert.equal(calls[0].url, "http://fake:1/upsert");
  assert.equal(calls[0].body.collection, "bridge_messages");
  assert.equal(calls[0].body.documents[0]._key, m.id);

  const down = await mirrorMessages([m], { baseUrl: "http://fake:1", fetchImpl: async () => { throw new Error("ECONNREFUSED"); } });
  assert.equal(down.ok, false);
  assert.match(down.error, /ECONNREFUSED/);
});

test("stop hook is silent when empty, blocks on unread, respects stop_hook_active", async () => {
  const dir = mkdtempSync(join(tmpdir(), "hook-v1-"));
  const env = { ...process.env, PI_HERDR_BRIDGE_STATE: dir };
  const payload = JSON.stringify({ session_id: "sess-42" });

  const quiet = await runHook(env, payload);
  assert.equal(quiet.stdout, "");

  appendMessage("sess-42", msg(), join(dir, "inbox"));
  const blocked = await runHook(env, payload);
  const out = JSON.parse(blocked.stdout);
  assert.equal(out.decision, "block");
  assert.match(out.reason, /1 unread bridge message/);
  assert.match(out.reason, /\[question\] from codex-a/);
  assert.match(out.reason, /need the schema/);

  const rearmed = await runHook(env, JSON.stringify({ session_id: "sess-42", stop_hook_active: true }));
  assert.equal(rearmed.stdout, "");
});

test("herdr-prompt lane defers to inbox when pane is working", async () => {
  const dir = mkdtempSync(join(tmpdir(), "gate-v1-"));
  process.env.PI_HERDR_BRIDGE_STATE = dir;
  const { sendToTarget } = await import("../route.mjs");
  const roster = [{
    source: "herdr", provider: "claude", name: "busy pane", paneId: "w9:p9",
    cwd: "/x", status: "working",
    sessionRef: { kind: "id", value: "claude-busy-1", refSource: "herdr:claude" },
  }];
  const result = await sendToTarget("busy pane", "are you done?", { rosterOverride: roster, fromName: "tester", kind: "question" });
  assert.equal(result.ok, true);
  assert.equal(result.deferred, true);
  assert.equal(result.delivered, false);
  assert.ok(result.messageId);
  const box = readInbox("claude-busy-1", { dir: join(dir, "inbox") });
  assert.equal(box.unread.length, 1);
  assert.equal(box.unread[0].deferred, true);
  assert.equal(box.unread[0].kind, "question");
  delete process.env.PI_HERDR_BRIDGE_STATE;
});
