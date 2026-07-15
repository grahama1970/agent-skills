const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  createBoundedLogger,
  summarizeExtensionMessage,
} = require("../native/host-log.cjs");

test("extension message summaries exclude response bodies", () => {
  const secretPayload = `data:image/png;base64,${"A".repeat(200_000)}`;
  const message = {
    id: 42,
    result: {
      type: "object",
      value: { screenshot: secretPayload },
    },
  };

  const summary = summarizeExtensionMessage(message, Buffer.byteLength(JSON.stringify(message)));

  assert.match(summary, /"id":42/);
  assert.match(summary, /"payloadBytes":200/);
  assert.match(summary, /"resultKeys":\["type","value"\]/);
  assert.doesNotMatch(summary, /data:image|AAAA/);
  assert.ok(Buffer.byteLength(summary) < 300);
});

test("bounded logger discards a grossly oversized legacy log", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "surf-host-log-"));
  const logFile = path.join(directory, "host.log");
  fs.writeFileSync(logFile, "x".repeat(5000));
  const log = createBoundedLogger({ logFile, maxBytes: 1000, backupCount: 2, maxEntryBytes: 200 });

  log("Host starting");

  const content = fs.readFileSync(logFile, "utf8");
  assert.match(content, /Host starting/);
  assert.ok(fs.statSync(logFile).size < 250);
  assert.equal(fs.existsSync(`${logFile}.1`), false);
  fs.rmSync(directory, { recursive: true, force: true });
});

test("bounded logger rotates ordinary logs and caps individual entries", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "surf-host-log-"));
  const logFile = path.join(directory, "host.log");
  const log = createBoundedLogger({ logFile, maxBytes: 300, backupCount: 2, maxEntryBytes: 80 });

  for (let index = 0; index < 12; index += 1) log(`${index}:${"z".repeat(200)}`);

  for (const candidate of [logFile, `${logFile}.1`, `${logFile}.2`]) {
    if (fs.existsSync(candidate)) assert.ok(fs.statSync(candidate).size <= 300);
  }
  assert.ok(fs.existsSync(`${logFile}.1`));
  assert.match(fs.readFileSync(logFile, "utf8"), /\[truncated\]/);
  fs.rmSync(directory, { recursive: true, force: true });
});
