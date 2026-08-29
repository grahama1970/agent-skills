// Live end-to-end eval of the v1 envelope through PRODUCTION surfaces only:
// bridge-cli.mjs (send/inbox), the real pi-intercom broker, and the real
// claude-stop-hook.mjs binary. No test fixtures, no direct module calls into
// inbox/route internals — everything goes through the CLI and hook exactly as
// an agent would use them.
//
// Flow:
//   1. bridge-cli listen  -> real broker peer (the message target)
//   2. bridge-cli send    -> live intercom delivery with kind/skill-chain/goal
//   3. bridge-cli inbox   -> read back a valid v1 envelope, unread=1
//   4. claude-stop-hook   -> blocks with the unread preview
//   5. bridge-cli inbox --ack <id> -> per-message ack, archive, mirror attempt
//   6. claude-stop-hook   -> silent
//   7. dead-letter: corrupt line -> inbox reports dead_lettered, message safe
import { spawn, execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdtempSync, appendFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const HERE = dirname(fileURLToPath(import.meta.url));
const CLI = join(HERE, "..", "bridge-cli.mjs");
const HOOK = join(HERE, "..", "claude-stop-hook.mjs");

const stateDir = mkdtempSync(join(tmpdir(), "envelope-e2e-"));
const env = { ...process.env, PI_HERDR_BRIDGE_STATE: stateDir };
const listenerName = `envelope-e2e-${process.pid}`;

function fail(step, detail) {
  console.log(JSON.stringify({ status: "FAIL", step, detail }));
  process.exit(1);
}

async function cli(args) {
  const { stdout } = await execFileAsync("node", [CLI, ...args], { env });
  return stdout;
}

function runHook(input) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn("node", [HOOK], { env });
    let stdout = "";
    child.stdout.on("data", (d) => { stdout += d; });
    child.on("error", reject);
    child.on("close", () => resolvePromise(stdout));
    child.stdin.end(input);
  });
}

// 1. Real broker listener via the CLI.
const listener = spawn("node", [CLI, "listen", "--name", listenerName], { env });
let listenerOut = "";
listener.stdout.on("data", (d) => { listenerOut += d; });
await new Promise((r) => setTimeout(r, 1200));

try {
  // 2. Live send through the intercom lane with full envelope fields.
  const sendOut = JSON.parse(await cli([
    "send", "--to", listenerName, "--text", "e2e: answer the schema question",
    "--from", "envelope-e2e-sender", "--kind", "question", "--expects-reply",
    "--goal", "prove envelope e2e", "--skill-chain", "debugger,ticket",
  ]).catch((e) => fail("send", String(e))));
  if (!sendOut.ok || sendOut.lane !== "intercom" || !sendOut.messageId) {
    fail("send", sendOut);
  }
  const sessionKey = sendOut.entry.sessionRef.value;

  // 3. Inbox read-back: valid envelope, unread=1.
  const box1 = JSON.parse(await cli(["inbox", "--key", sessionKey]));
  if (box1.unread_count !== 1) fail("inbox-unread", box1);
  const m = box1.messages[0];
  if (m.schema !== "herdr-bridge.msg.v1" || m.kind !== "question"
    || m.from.agent !== "envelope-e2e-sender"
    || m.skill_chain.recommended.join(",") !== "debugger,ticket"
    || m.goal !== "prove envelope e2e" || m.read !== false) {
    fail("envelope-shape", m);
  }

  // 4. Real stop hook blocks on the unread message.
  const blocked = await runHook(JSON.stringify({ session_id: sessionKey }));
  let hookOut;
  try {
    hookOut = JSON.parse(blocked);
  } catch {
    fail("hook-block", { raw: blocked });
  }
  if (hookOut.decision !== "block" || !hookOut.reason.includes("[question] from envelope-e2e-sender")) {
    fail("hook-block", hookOut);
  }

  // 5. Per-message ack through the CLI; expect archive + mirror attempt.
  const acked = JSON.parse(await cli(["inbox", "--key", sessionKey, "--ack", m.id, "--by", "e2e"]));
  if (!acked.ack || acked.ack.acked[0] !== m.id || acked.ack.remainingUnread !== 0 || !acked.ack.archived) {
    fail("ack", acked.ack);
  }
  if (!acked.memory_mirror || typeof acked.memory_mirror.ok !== "boolean") {
    fail("mirror-recorded", acked.memory_mirror);
  }
  const archives = readdirSync(join(stateDir, "inbox")).filter((f) => f.includes(".consumed-"));
  if (archives.length !== 1) fail("archive", archives);

  // 6. Hook is now silent.
  const silent = await runHook(JSON.stringify({ session_id: sessionKey }));
  if (silent !== "") fail("hook-silent", { raw: silent });

  // 7. Dead-letter: corrupt line does not poison a fresh inbox.
  appendFileSync(join(stateDir, "inbox", "corrupt-key.jsonl"), '{"schema":"bogus"}\nnot json\n');
  const box2 = JSON.parse(await cli(["inbox", "--key", "corrupt-key"]));
  if (box2.dead_lettered !== 2 || box2.unread_count !== 0) fail("dead-letter", box2);

  console.log(JSON.stringify({
    status: "PASS",
    surfaces: ["bridge-cli send/inbox/listen", "real pi-intercom broker", "claude-stop-hook.mjs"],
    message_id: m.id,
    lane: "intercom",
    delivered_live: true,
    hook_blocked_then_silent: true,
    per_message_ack_and_archive: true,
    memory_mirror_recorded: acked.memory_mirror,
    dead_letter_count: box2.dead_lettered,
    listener_received: listenerOut.includes("e2e: answer the schema question"),
  }, null, 2));
} finally {
  listener.kill();
}
