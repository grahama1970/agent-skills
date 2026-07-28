"use strict";

// Chunked composer insertion shared by every browser client.
//
// A single Input.insertText carrying the whole prompt stalls past the native
// host's extension timeout on heavy conversations: agent-skills#1034 saw a 32KB
// prompt never return on a long ChatGPT project thread while the same prompt
// succeeded on a fresh tab, and agent-skills#1036 tracked the identical
// single-call pattern in the other clients. Chunking keeps every extension
// round-trip small; the caret stays at the end of the composer, so sequential
// inserts rebuild the prompt in order.

const { throwIfAborted } = require("./abort.cjs");

const DEFAULT_CHUNK_CHARS = 6000;
const DEFAULT_TIMEOUT_MS = 90000;

function positiveInt(raw, fallback) {
  const value = Number.parseInt(raw || "", 10);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

// Read the environment per call so a caller can tune a single submit without
// reloading the module. SURF_WEBGPT_INSERT_* stays honoured because it shipped
// with the ChatGPT-only fix.
function promptInsertChunkChars() {
  return positiveInt(
    process.env.SURF_PROMPT_INSERT_CHUNK_CHARS || process.env.SURF_WEBGPT_INSERT_CHUNK_CHARS,
    DEFAULT_CHUNK_CHARS,
  );
}

function promptInsertTimeoutMs() {
  return positiveInt(
    process.env.SURF_PROMPT_INSERT_TIMEOUT_MS || process.env.SURF_WEBGPT_INSERT_TIMEOUT_MS,
    DEFAULT_TIMEOUT_MS,
  );
}

async function insertPromptText(inputCdp, prompt, signal) {
  const text = String(prompt ?? "");
  const timeoutMs = promptInsertTimeoutMs();
  const chunkChars = promptInsertChunkChars();
  if (text.length <= chunkChars) {
    await inputCdp("Input.insertText", { text }, timeoutMs);
    return 1;
  }
  let chunks = 0;
  for (let offset = 0; offset < text.length; offset += chunkChars) {
    if (signal) throwIfAborted(signal);
    await inputCdp("Input.insertText", { text: text.slice(offset, offset + chunkChars) }, timeoutMs);
    chunks += 1;
  }
  return chunks;
}

module.exports = {
  DEFAULT_CHUNK_CHARS,
  DEFAULT_TIMEOUT_MS,
  insertPromptText,
  promptInsertChunkChars,
  promptInsertTimeoutMs,
};
