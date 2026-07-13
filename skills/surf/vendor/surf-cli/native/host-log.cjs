const fs = require("fs");

const DEFAULT_MAX_BYTES = 5 * 1024 * 1024;
const DEFAULT_BACKUP_COUNT = 2;
const DEFAULT_MAX_ENTRY_BYTES = 16 * 1024;

function positiveInteger(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function rotateLog(logFile, maxBytes, backupCount, incomingBytes) {
  let currentBytes = 0;
  try {
    currentBytes = fs.statSync(logFile).size;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }

  if (currentBytes + incomingBytes <= maxBytes) return false;

  // A grossly oversized legacy log is not useful as a backup and must not keep
  // consuming disk after bounded logging is installed.
  if (currentBytes > maxBytes * (backupCount + 1)) {
    fs.rmSync(logFile, { force: true });
    return true;
  }

  fs.rmSync(`${logFile}.${backupCount}`, { force: true });
  for (let index = backupCount - 1; index >= 1; index -= 1) {
    const source = `${logFile}.${index}`;
    if (fs.existsSync(source)) fs.renameSync(source, `${logFile}.${index + 1}`);
  }
  if (fs.existsSync(logFile)) fs.renameSync(logFile, `${logFile}.1`);
  return true;
}

function truncateUtf8(value, maxBytes) {
  const text = String(value);
  if (Buffer.byteLength(text) <= maxBytes) return text;
  const suffix = "...[truncated]";
  const budget = Math.max(0, maxBytes - Buffer.byteLength(suffix));
  return Buffer.from(text).subarray(0, budget).toString("utf8") + suffix;
}

function createBoundedLogger(options = {}) {
  const logFile = options.logFile || "/tmp/surf-host.log";
  const maxBytes = positiveInteger(options.maxBytes ?? process.env.SURF_HOST_LOG_MAX_BYTES, DEFAULT_MAX_BYTES);
  const backupCount = positiveInteger(options.backupCount ?? process.env.SURF_HOST_LOG_BACKUPS, DEFAULT_BACKUP_COUNT);
  const maxEntryBytes = Math.min(
    maxBytes,
    positiveInteger(options.maxEntryBytes ?? process.env.SURF_HOST_LOG_MAX_ENTRY_BYTES, DEFAULT_MAX_ENTRY_BYTES),
  );

  return (message) => {
    const timestamp = new Date().toISOString();
    const entry = `${timestamp} ${truncateUtf8(message, maxEntryBytes)}\n`;
    rotateLog(logFile, maxBytes, backupCount, Buffer.byteLength(entry));
    fs.appendFileSync(logFile, entry, { encoding: "utf8", mode: 0o600 });
  };
}

function summarizeExtensionMessage(message, payloadBytes) {
  const result = message && typeof message.result === "object" && message.result !== null
    ? message.result
    : null;
  const summary = {
    id: message?.id ?? null,
    type: message?.type ?? null,
    payloadBytes,
    keys: message && typeof message === "object" ? Object.keys(message).sort() : [],
  };

  if (message?.streamId != null) summary.streamId = message.streamId;
  if (message?.error != null) summary.error = truncateUtf8(message.error, 1000);
  if (result) {
    summary.resultKeys = Object.keys(result).sort();
    if (result.type != null) summary.resultType = result.type;
    if (result.error != null) summary.resultError = truncateUtf8(result.error, 1000);
  } else if (message?.result != null) {
    summary.resultType = typeof message.result;
  }

  return JSON.stringify(summary);
}

module.exports = {
  createBoundedLogger,
  rotateLog,
  summarizeExtensionMessage,
  truncateUtf8,
};
