// Durable per-target inbox with the strict v1 envelope (schema.mjs).
// Files: ~/.local/state/pi-herdr-bridge/inbox/<key>.jsonl — append-only.
// A message is unread until an ack record naming its id appears in the file.
// Invalid records are moved to dead-letter.jsonl on read, never silently kept.
import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { classifyRecord, makeAck, validateMessage } from "./schema.mjs";

export function inboxDir(env = process.env) {
  const base = env.PI_HERDR_BRIDGE_STATE?.trim()
    || join(env.XDG_STATE_HOME?.trim() || join(homedir(), ".local/state"), "pi-herdr-bridge");
  return join(base, "inbox");
}

export function inboxKey(entry) {
  const raw = entry.sessionRef?.value || entry.paneId || "unknown";
  return raw.replace(/[^a-zA-Z0-9._-]+/g, "_");
}

export function inboxPath(key, dir = inboxDir()) {
  return join(dir, `${key}.jsonl`);
}

function appendRecord(key, record, dir) {
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const path = inboxPath(key, dir);
  appendFileSync(path, JSON.stringify(record) + "\n", { mode: 0o600 });
  return path;
}

export function appendMessage(key, message, dir = inboxDir()) {
  const problems = validateMessage(message);
  if (problems.length > 0) throw new Error(`refusing to append invalid message: ${problems.join("; ")}`);
  return appendRecord(key, message, dir);
}

export function appendAck(key, msgId, { by, action = "read", dir = inboxDir() } = {}) {
  return appendRecord(key, makeAck({ msgId, by, action }), dir);
}

// Read the inbox: returns messages with computed read state, plus acks.
// Invalid lines are appended to dead-letter.jsonl and reported.
export function readInbox(key, { dir = inboxDir() } = {}) {
  const path = inboxPath(key, dir);
  if (!existsSync(path)) return { path, messages: [], unread: [], acks: [], dead: 0 };
  const lines = readFileSync(path, "utf-8").split("\n").filter(Boolean);
  const messages = [];
  const acks = [];
  let dead = 0;
  for (const line of lines) {
    let parsed;
    try {
      parsed = JSON.parse(line);
    } catch {
      parsed = { raw: line };
    }
    const c = classifyRecord(parsed);
    if (c.type === "msg") messages.push(c.record);
    else if (c.type === "ack") acks.push(c.record);
    else {
      dead += 1;
      appendFileSync(join(dir, "dead-letter.jsonl"), JSON.stringify({ ts: Date.now(), inbox: key, problems: c.problems, record: parsed }) + "\n", { mode: 0o600 });
    }
  }
  const ackedIds = new Set(acks.map((a) => a.msg_id));
  const withState = messages.map((m) => ({ ...m, read: ackedIds.has(m.id) }));
  return { path, messages: withState, unread: withState.filter((m) => !m.read), acks, dead };
}

// Ack specific message ids (or every unread when ids is empty). When every
// message in the file is read afterwards, the file is archived (renamed),
// never deleted.
export function ackMessages(key, ids, { by, dir = inboxDir() } = {}) {
  const before = readInbox(key, { dir });
  const targets = ids && ids.length > 0
    ? before.unread.filter((m) => ids.includes(m.id))
    : before.unread;
  for (const m of targets) appendAck(key, m.id, { by, dir });
  const after = readInbox(key, { dir });
  let archived = null;
  if (after.messages.length > 0 && after.unread.length === 0) {
    archived = `${after.path}.consumed-${Date.now()}`;
    renameSync(after.path, archived);
  }
  return { acked: targets.map((m) => m.id), remainingUnread: after.unread.length, archived };
}
