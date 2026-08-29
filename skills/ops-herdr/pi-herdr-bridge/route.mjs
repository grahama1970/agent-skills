// Per-provider delivery routing.
// pi (intercom-connected) -> broker send (structured, can trigger a turn)
// codex                   -> codex queue --thread <uuid|name> --message <text>
// claude / pi (pane-only) -> herdr agent prompt <pane_id> <text>
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { BrokerClient } from "./broker.mjs";
import { herdrRoster, mergeRoster, normalizeBrokerSessions, resolveTarget } from "./roster.mjs";
import { appendInbox, inboxKey } from "./inbox.mjs";

const execFileAsync = promisify(execFile);

export function pickLane(entry) {
  if (entry.source === "intercom") return "intercom";
  if (entry.provider === "codex" && entry.sessionRef?.kind === "id") return "codex-queue";
  if (entry.paneId) return "herdr-prompt";
  return null;
}

async function sendCodexQueue(entry, text, { codexBin = "codex" } = {}) {
  const { stdout, stderr } = await execFileAsync(
    codexBin,
    ["queue", "--thread", entry.sessionRef.value, "--message", text],
  );
  return { lane: "codex-queue", thread: entry.sessionRef.value, stdout: stdout.trim(), stderr: stderr.trim() };
}

async function sendHerdrPrompt(entry, text, { herdrBin = "herdr" } = {}) {
  const { stdout, stderr } = await execFileAsync(
    herdrBin,
    ["agent", "prompt", entry.paneId, text],
  );
  return { lane: "herdr-prompt", paneId: entry.paneId, stdout: stdout.trim(), stderr: stderr.trim() };
}

async function sendIntercom(entry, text, { fromName, expectsReply } = {}) {
  const client = new BrokerClient({ name: fromName || "herdr-bridge" });
  try {
    await client.connect();
    const result = await client.send(entry.sessionRef.value, text, { expectsReply });
    return {
      lane: "intercom",
      to: entry.sessionRef.value,
      delivery: result.delivery,
      brokerResult: result.type,
      ...(result.reason ? { reason: result.reason } : {}),
    };
  } finally {
    client.close();
  }
}

export async function buildRoster({ fromName } = {}) {
  const [herdrEntries, brokerEntries] = await Promise.all([
    herdrRoster().catch((error) => ({ error: String(error) })),
    (async () => {
      const client = new BrokerClient({ name: fromName || "herdr-bridge-roster" });
      try {
        const selfId = await client.connect();
        const sessions = await client.listSessions();
        return normalizeBrokerSessions(sessions, selfId);
      } finally {
        client.close();
      }
    })().catch((error) => ({ error: String(error) })),
  ]);
  const errors = [];
  const herdrOk = Array.isArray(herdrEntries) ? herdrEntries : (errors.push(`herdr: ${herdrEntries.error}`), []);
  const brokerOk = Array.isArray(brokerEntries) ? brokerEntries : (errors.push(`intercom: ${brokerEntries.error}`), []);
  return { roster: mergeRoster(brokerOk, herdrOk), errors };
}

// Statuses where typing into a pane risks feeding a working agent, an
// approval dialog, or an unknown surface. intercom and codex-queue lanes have
// real queues upstream; only the raw-terminal lane needs this gate.
const HERDR_PROMPT_UNSAFE_STATUSES = new Set(["working", "blocked", "unknown"]);

export async function sendToTarget(query, text, opts = {}) {
  const { roster, errors } = opts.rosterOverride
    ? { roster: opts.rosterOverride, errors: [] }
    : await buildRoster(opts);
  const resolved = resolveTarget(roster, query);
  if (resolved.error) {
    return { ok: false, error: resolved.error, matches: resolved.matches, rosterErrors: errors };
  }
  const entry = resolved.entry;
  const lane = pickLane(entry);
  if (!lane) {
    return { ok: false, error: `no delivery lane for target (provider=${entry.provider}, source=${entry.source})`, entry };
  }
  const key = inboxKey(entry);
  const base = { from: opts.fromName ?? null, to: query, lane, text };

  if (lane === "herdr-prompt" && HERDR_PROMPT_UNSAFE_STATUSES.has(entry.status)) {
    const inboxFile = appendInbox(key, { ...base, delivered: false, deferred: true, reason: `pane status ${entry.status}` });
    return {
      ok: true,
      deferred: true,
      delivered: false,
      entry,
      lane,
      inbox: inboxFile,
      note: `target pane is ${entry.status}; message stored in inbox only — a Stop hook or monitor tick surfaces it`,
      rosterErrors: errors,
    };
  }

  const senders = { "intercom": sendIntercom, "codex-queue": sendCodexQueue, "herdr-prompt": sendHerdrPrompt };
  try {
    const result = await senders[lane](entry, text, opts);
    const inboxFile = appendInbox(key, { ...base, delivered: true });
    return { ok: true, delivered: true, entry, inbox: inboxFile, ...result, rosterErrors: errors };
  } catch (error) {
    const inboxFile = appendInbox(key, { ...base, delivered: false, error: String(error) });
    return { ok: false, error: String(error), lane, entry, inbox: inboxFile, rosterErrors: errors };
  }
}
