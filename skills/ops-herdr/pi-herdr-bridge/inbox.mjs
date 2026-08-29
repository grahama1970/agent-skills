// Durable per-target inbox. Every bridge send is also appended here, so a
// busy or dead target can catch up later and no message is ever lost.
// Files: ~/.local/state/pi-herdr-bridge/inbox/<key>.jsonl
// Consumed files are renamed to <key>.jsonl.consumed-<epoch> (never deleted).
import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

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

export function appendInbox(key, record, dir = inboxDir()) {
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const path = inboxPath(key, dir);
  appendFileSync(path, JSON.stringify({ ts: Date.now(), ...record }) + "\n", { mode: 0o600 });
  return path;
}

export function readInbox(key, { consume = false, dir = inboxDir() } = {}) {
  const path = inboxPath(key, dir);
  if (!existsSync(path)) return { path, entries: [] };
  const entries = readFileSync(path, "utf-8")
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return { unparseable: line };
      }
    });
  if (consume && entries.length > 0) {
    renameSync(path, `${path}.consumed-${Date.now()}`);
  }
  return { path, entries };
}
