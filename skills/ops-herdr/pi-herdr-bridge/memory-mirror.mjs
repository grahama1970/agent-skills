// Fail-soft mirror of bridge messages into the $memory ArangoDB stack, via
// the memory daemon (http://127.0.0.1:8601) POST /upsert — never raw AQL or
// Qdrant calls, per best-practices-arangodb. Documents carry text + metadata
// only (no embedding arrays); semantic sync owns Qdrant.
import { toMemoryDocument, MEMORY_COLLECTION } from "./schema.mjs";

export const MEMORY_DAEMON_URL = process.env.MEMORY_DAEMON_URL?.trim() || "http://127.0.0.1:8601";

export async function mirrorMessages(messages, { acks = [], baseUrl = MEMORY_DAEMON_URL, collection = MEMORY_COLLECTION, timeoutMs = 10000, fetchImpl = fetch } = {}) {
  if (!messages || messages.length === 0) {
    return { mirrored: 0, ok: true, skipped: "no messages" };
  }
  const documents = messages.map((m) => toMemoryDocument(m, { acks }));
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const response = await fetchImpl(`${baseUrl}/upsert`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ collection, documents }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    const body = await response.text();
    if (!response.ok) {
      return { mirrored: 0, ok: false, error: `daemon ${response.status}: ${body.slice(0, 300)}` };
    }
    return { mirrored: documents.length, ok: true, daemon: body.slice(0, 300) };
  } catch (error) {
    // Fail-soft: the file inbox is the source of truth; a down daemon must
    // never block messaging. Caller records the miss for later backfill.
    return { mirrored: 0, ok: false, error: String(error) };
  }
}
