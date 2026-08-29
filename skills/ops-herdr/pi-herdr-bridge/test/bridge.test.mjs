import { test } from "node:test";
import assert from "node:assert/strict";
import net from "node:net";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { encodeFrame, createFrameReader, BrokerClient } from "../broker.mjs";
import { normalizeHerdrAgents, normalizeBrokerSessions, mergeRoster, resolveTarget } from "../roster.mjs";
import { pickLane } from "../route.mjs";

test("framing round-trips split and coalesced frames", () => {
  const messages = [];
  const reader = createFrameReader((m) => messages.push(m), (e) => { throw e; });
  const f1 = encodeFrame({ type: "registered", sessionId: "s1" });
  const f2 = encodeFrame({ type: "session_left", sessionId: "s2" });
  const combined = Buffer.concat([f1, f2]);
  reader(combined.subarray(0, 3));
  reader(combined.subarray(3, f1.length + 2));
  reader(combined.subarray(f1.length + 2));
  assert.deepEqual(messages, [
    { type: "registered", sessionId: "s1" },
    { type: "session_left", sessionId: "s2" },
  ]);
});

test("framing rejects oversized frames", () => {
  const errors = [];
  const reader = createFrameReader(() => {}, (e) => errors.push(e), 16);
  reader(encodeFrame({ type: "message", pad: "x".repeat(100) }));
  assert.equal(errors.length, 1);
  assert.match(errors[0].message, /exceeds maximum/);
});

const HERDR_FIXTURE = {
  result: {
    agents: [
      { agent: "codex", agent_session: { agent: "codex", kind: "id", source: "herdr:codex", value: "uuid-codex-1" }, agent_status: "idle", cwd: "/repo/a", pane_id: "w1:p1", tab_id: "w1:t1", terminal_id: "t1", workspace_id: "w1" },
      { agent: "claude", agent_session: { agent: "claude", kind: "id", source: "herdr:claude", value: "uuid-claude-1" }, agent_status: "working", cwd: "/repo/b", pane_id: "w1:p2", tab_id: "w1:t2", terminal_id: "t2", terminal_title_stripped: "fix tickets", workspace_id: "w1" },
      { agent: "pi", agent_session: { agent: "pi", kind: "path", source: "herdr:pi", value: "/home/u/.pi/agent/sessions/x/s.jsonl" }, agent_status: "idle", cwd: "/repo/c", pane_id: "w1:p3", tab_id: "w1:t3", terminal_id: "t3", workspace_id: "w1" },
    ],
  },
};

test("roster normalizes herdr and broker entries and resolves targets", () => {
  const herdr = normalizeHerdrAgents(HERDR_FIXTURE);
  assert.equal(herdr.length, 3);
  assert.equal(herdr[0].sessionRef.value, "uuid-codex-1");

  const broker = normalizeBrokerSessions(
    [
      { id: "pi-sess-1", name: "researcher", cwd: "/repo/c", model: "m", pid: 1, startedAt: 0, lastActivity: 0 },
      { id: "self", name: "me", cwd: "/x", model: "m", pid: 2, startedAt: 0, lastActivity: 0 },
    ],
    "self",
  );
  assert.equal(broker.length, 1);

  const roster = mergeRoster(broker, herdr);

  assert.equal(resolveTarget(roster, "researcher").entry.sessionRef.value, "pi-sess-1");
  assert.equal(resolveTarget(roster, "fix tickets").entry.provider, "claude");
  assert.equal(resolveTarget(roster, "uuid-codex-1").entry.provider, "codex");
  assert.equal(resolveTarget(roster, "w1:p3").entry.provider, "pi");
  assert.match(resolveTarget(roster, "nope").error, /no session matches/);
});

test("resolveTarget fails closed on ambiguity", () => {
  const dup = normalizeHerdrAgents({
    result: { agents: [
      { agent: "claude", agent_session: { kind: "id", source: "s", value: "v1" }, agent_status: "idle", cwd: "/a", pane_id: "p1", terminal_title_stripped: "same", workspace_id: "w" },
      { agent: "claude", agent_session: { kind: "id", source: "s", value: "v2" }, agent_status: "idle", cwd: "/b", pane_id: "p2", terminal_title_stripped: "same", workspace_id: "w" },
    ] },
  });
  const result = resolveTarget(dup, "same");
  assert.match(result.error, /ambiguous/);
  assert.equal(result.matches.length, 2);
});

test("pickLane routes per provider", () => {
  const herdr = normalizeHerdrAgents(HERDR_FIXTURE);
  const broker = normalizeBrokerSessions([{ id: "pi-1", cwd: "/", model: "m", pid: 1, startedAt: 0, lastActivity: 0 }], null);
  assert.equal(pickLane(broker[0]), "intercom");
  assert.equal(pickLane(herdr.find((e) => e.provider === "codex")), "codex-queue");
  assert.equal(pickLane(herdr.find((e) => e.provider === "claude")), "herdr-prompt");
  assert.equal(pickLane(herdr.find((e) => e.provider === "pi")), "herdr-prompt");
});

test("BrokerClient registers, lists, and sends against a fake broker", async () => {
  const dir = mkdtempSync(join(tmpdir(), "bridge-test-"));
  const socketPath = join(dir, "broker.sock");
  const seen = [];
  const server = net.createServer((socket) => {
    const reader = createFrameReader((msg) => {
      seen.push(msg);
      if (msg.type === "register") {
        socket.write(encodeFrame({ type: "registered", sessionId: "fake-1" }));
      } else if (msg.type === "list") {
        socket.write(encodeFrame({
          type: "sessions",
          requestId: msg.requestId,
          sessions: [{ id: "peer-1", name: "peer", cwd: "/", model: "m", pid: 9, startedAt: 0, lastActivity: 0 }],
        }));
      } else if (msg.type === "send") {
        socket.write(encodeFrame({ type: "delivered", messageId: msg.message.id, delivery: "socket_delivered", retryable: false, outcomeKnown: true }));
      }
    }, () => {});
    socket.on("data", reader);
  });
  await new Promise((r) => server.listen(socketPath, r));

  const client = new BrokerClient({ socketPath, name: "tester" });
  const sessionId = await client.connect();
  assert.equal(sessionId, "fake-1");
  const sessions = await client.listSessions();
  assert.equal(sessions[0].name, "peer");
  const delivery = await client.send("peer", "hello");
  assert.equal(delivery.delivery, "socket_delivered");
  client.close();
  server.close();
  assert.equal(seen[0].type, "register");
  assert.equal(seen[0].session.name, "tester");
});
