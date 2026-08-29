// Strict v1 envelope for bridge inbox JSONL. Two record types share a file:
//   herdr-bridge.msg.v1 — a message
//   herdr-bridge.ack.v1 — an append-only read/ack marker for one message
// A message is unread until an ack record naming its id appears. Files are
// append-only; state changes are new records, never mutations.
import { randomUUID } from "node:crypto";

export const MSG_SCHEMA = "herdr-bridge.msg.v1";
export const ACK_SCHEMA = "herdr-bridge.ack.v1";
export const KINDS = ["question", "notification", "handoff", "completion", "nudge", "reply"];
export const LANES = ["intercom", "codex-queue", "herdr-prompt", "inbox-only", "test"];

function isParty(v) {
  return v && typeof v === "object"
    && typeof v.agent === "string" && v.agent.length > 0
    && (v.provider === undefined || typeof v.provider === "string")
    && (v.session_ref === undefined || v.session_ref === null || typeof v.session_ref === "string");
}

function isStringArray(v) {
  return Array.isArray(v) && v.every((x) => typeof x === "string");
}

export function makeMessage({
  from, to, text, kind = "notification", lane, delivered = false, deferred = false,
  reason, replyTo, expectsReply = false, skillChain, artifacts, goal,
}) {
  const msg = {
    schema: MSG_SCHEMA,
    id: randomUUID(),
    ts: Date.now(),
    kind,
    from,
    to,
    text,
    lane,
    delivered,
    deferred,
    expects_reply: expectsReply,
    skill_chain: {
      recommended: skillChain?.recommended ?? [],
      final: skillChain?.final ?? [],
    },
    artifacts: artifacts ?? [],
    ...(reason ? { reason } : {}),
    ...(replyTo ? { reply_to: replyTo } : {}),
    ...(goal ? { goal } : {}),
  };
  const problems = validateMessage(msg);
  if (problems.length > 0) throw new Error(`invalid bridge message: ${problems.join("; ")}`);
  return msg;
}

export function makeAck({ msgId, by, action = "read" }) {
  if (typeof msgId !== "string" || !msgId) throw new Error("ack requires msgId");
  if (action !== "read" && action !== "ack") throw new Error(`invalid ack action: ${action}`);
  return { schema: ACK_SCHEMA, id: randomUUID(), ts: Date.now(), msg_id: msgId, action, by: by ?? "unknown" };
}

export function validateMessage(m) {
  const problems = [];
  if (!m || typeof m !== "object") return ["not an object"];
  if (m.schema !== MSG_SCHEMA) problems.push(`schema must be ${MSG_SCHEMA}`);
  if (typeof m.id !== "string" || !m.id) problems.push("id required");
  if (typeof m.ts !== "number") problems.push("ts must be epoch ms number");
  if (!KINDS.includes(m.kind)) problems.push(`kind must be one of ${KINDS.join("|")}`);
  if (!isParty(m.from)) problems.push("from must be {agent, provider?, session_ref?}");
  if (!isParty(m.to)) problems.push("to must be {agent, provider?, session_ref?}");
  if (typeof m.text !== "string" || m.text.length === 0) problems.push("text required");
  if (!LANES.includes(m.lane)) problems.push(`lane must be one of ${LANES.join("|")}`);
  if (typeof m.delivered !== "boolean") problems.push("delivered must be boolean");
  if (typeof m.deferred !== "boolean") problems.push("deferred must be boolean");
  if (typeof m.expects_reply !== "boolean") problems.push("expects_reply must be boolean");
  if (!m.skill_chain || !isStringArray(m.skill_chain.recommended) || !isStringArray(m.skill_chain.final)) {
    problems.push("skill_chain must be {recommended: string[], final: string[]}");
  }
  if (!isStringArray(m.artifacts)) problems.push("artifacts must be string[]");
  if (m.reply_to !== undefined && typeof m.reply_to !== "string") problems.push("reply_to must be string");
  if (m.goal !== undefined && typeof m.goal !== "string") problems.push("goal must be string");
  return problems;
}

export function validateAck(a) {
  const problems = [];
  if (!a || typeof a !== "object") return ["not an object"];
  if (a.schema !== ACK_SCHEMA) problems.push(`schema must be ${ACK_SCHEMA}`);
  if (typeof a.id !== "string" || !a.id) problems.push("id required");
  if (typeof a.ts !== "number") problems.push("ts must be epoch ms number");
  if (typeof a.msg_id !== "string" || !a.msg_id) problems.push("msg_id required");
  if (a.action !== "read" && a.action !== "ack") problems.push("action must be read|ack");
  if (typeof a.by !== "string") problems.push("by must be string");
  return problems;
}

export function classifyRecord(record) {
  if (record && record.schema === MSG_SCHEMA) {
    const problems = validateMessage(record);
    return problems.length === 0 ? { type: "msg", record } : { type: "invalid", record, problems };
  }
  if (record && record.schema === ACK_SCHEMA) {
    const problems = validateAck(record);
    return problems.length === 0 ? { type: "ack", record } : { type: "invalid", record, problems };
  }
  return { type: "invalid", record, problems: ["unknown or missing schema"] };
}

// ArangoDB/$memory document shape, per best-practices-arangodb:
// - `_key` = message id (UUID, _key-legal)
// - NO embedding arrays — Qdrant owns vectors via the memory daemon's
//   semantic sync; this document carries text + metadata only
// - flat `text` field so BM25/ArangoSearch indexes the payload directly
// Insert via memory daemon POST /upsert {collection, documents:[...]}.
export const MEMORY_COLLECTION = "bridge_messages";

export function toMemoryDocument(message, { acks = [] } = {}) {
  const ack = acks.find((a) => a.msg_id === message.id);
  return {
    _key: message.id,
    schema: message.schema,
    ts: message.ts,
    kind: message.kind,
    from_agent: message.from.agent,
    from_provider: message.from.provider ?? null,
    from_session_ref: message.from.session_ref ?? null,
    to_agent: message.to.agent,
    to_provider: message.to.provider ?? null,
    to_session_ref: message.to.session_ref ?? null,
    text: message.text,
    lane: message.lane,
    delivered: message.delivered,
    deferred: message.deferred,
    expects_reply: message.expects_reply,
    reply_to: message.reply_to ?? null,
    goal: message.goal ?? null,
    skill_chain_recommended: message.skill_chain.recommended,
    skill_chain_final: message.skill_chain.final,
    artifacts: message.artifacts,
    read: Boolean(ack),
    read_ts: ack?.ts ?? null,
    read_by: ack?.by ?? null,
  };
}
