// Deferred-message redelivery with quiescence proof, TTL, and dead-letter.
//
// A deferred message (lane "inbox-only") sits in the target's inbox because the
// pane was working/blocked/unknown at send time. This module:
//   1. finds unacked deferred messages across all inboxes;
//   2. re-resolves each target against the live roster;
//   3. proves the pane quiescent by DOUBLE-SAMPLING its content (status alone
//      lies: panes report idle mid-task) before typing anything;
//   4. delivers and acks on success;
//   5. expires messages past TTL to dead-letter with a triage-error code
//      (herdr_pane_unaddressable) instead of waiting forever.
//
// No regex classification anywhere; decisions come from record fields,
// roster entries, and byte-identical pane readbacks.
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { appendAck, appendMessage, inboxDir, readInbox } from "./inbox.mjs";
import { buildRoster, sendToTarget } from "./route.mjs";
import { makeMessage } from "./schema.mjs";

const execFileAsync = promisify(execFile);

export const DEFAULT_TTL_MS = 6 * 60 * 60 * 1000; // 6 hours
export const QUIESCENCE_SAMPLE_GAP_MS = 4000;
export const DEAD_LETTER_TRIAGE_CODE = "herdr_pane_unaddressable";

async function readPane(paneId, { herdrBin = "herdr" } = {}) {
  try {
    const { stdout } = await execFileAsync(herdrBin, ["agent", "read", paneId, "--lines", "40"]);
    return { ok: true, content: stdout };
  } catch (error) {
    return { ok: false, error: String(error) };
  }
}

// A pane is quiescent only when two reads a few seconds apart are byte-identical.
// Unreadable counts as busy, never as free.
export async function isQuiescent(paneId, { gapMs = QUIESCENCE_SAMPLE_GAP_MS, herdrBin } = {}) {
  const first = await readPane(paneId, { herdrBin });
  if (!first.ok) return { quiescent: false, reason: "pane_unreadable", detail: first.error };
  await new Promise((resolve) => setTimeout(resolve, gapMs));
  const second = await readPane(paneId, { herdrBin });
  if (!second.ok) return { quiescent: false, reason: "pane_unreadable", detail: second.error };
  if (first.content !== second.content) return { quiescent: false, reason: "pane_redrawing" };
  return { quiescent: true, reason: "two_identical_samples" };
}

function deferredUnread(key, dir) {
  const { messages, unread } = readInbox(key, { dir });
  const unreadIds = new Set(unread.map((m) => m.id));
  return messages.filter((m) => m.deferred === true && unreadIds.has(m.id));
}

export async function flushDeferred({ ttlMs = DEFAULT_TTL_MS, dryRun = false, fromName = "herdr-bridge-flush", dir = inboxDir() } = {}) {
  const results = [];
  if (!existsSync(dir)) return { ok: true, results, note: "no inbox directory" };
  const keys = readdirSync(dir).filter((f) => f.endsWith(".jsonl") && f !== "dead-letter.jsonl").map((f) => f.slice(0, -6));
  if (keys.length === 0) return { ok: true, results, note: "no inboxes" };

  const { roster, errors } = await buildRoster({ fromName });
  const now = Date.now();

  for (const key of keys) {
    for (const msg of deferredUnread(key, dir)) {
      const ageMs = now - Date.parse(msg.at || 0);
      const target = msg.to?.session_ref || msg.to?.agent;
      const record = { key, messageId: msg.id, target, age_ms: ageMs };

      if (ageMs > ttlMs) {
        if (!dryRun) {
          appendAck(key, msg.id, { by: fromName, action: "expired", dir });
          const dead = makeMessage({
            from: { agent: fromName, session_ref: null },
            to: msg.to,
            text: msg.text,
            kind: "dead-letter",
            lane: "dead-letter",
            delivered: false,
            deferred: false,
          });
          dead.triage = { code: DEAD_LETTER_TRIAGE_CODE, cause: `deferred message exceeded TTL (${Math.round(ageMs / 60000)}m) without an addressable pane`, next_command: `node pi-herdr-bridge/bridge-cli.mjs list  # confirm target session, then resend` };
          appendMessage("dead-letter", dead, dir);
        }
        results.push({ ...record, action: "expired_to_dead_letter", triage_code: DEAD_LETTER_TRIAGE_CODE });
        continue;
      }

      const entry = roster.find((e) => (e.sessionRef?.value || e.paneId) === target || e.name === target);
      if (!entry || !entry.paneId) {
        results.push({ ...record, action: "skipped", reason: "target_not_in_roster_or_no_pane" });
        continue;
      }

      const q = await isQuiescent(entry.paneId);
      if (!q.quiescent) {
        results.push({ ...record, action: "still_deferred", reason: q.reason });
        continue;
      }

      if (dryRun) {
        results.push({ ...record, action: "would_deliver", pane: entry.paneId });
        continue;
      }
      const sent = await sendToTarget(entry.paneId, msg.text, { fromName, rosterOverride: roster });
      if (sent.ok && sent.delivered) {
        appendAck(key, msg.id, { by: fromName, action: "redelivered", dir });
        results.push({ ...record, action: "delivered", pane: entry.paneId });
      } else {
        results.push({ ...record, action: "delivery_failed", error: sent.error || sent.note });
      }
    }
  }
  return { ok: true, results, rosterErrors: errors };
}
