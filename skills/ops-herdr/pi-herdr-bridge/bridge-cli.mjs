#!/usr/bin/env node
// CLI for non-Pi agents (Codex, Claude Code, scripts) to join the bridge.
//   bridge-cli.mjs list [--json]
//   bridge-cli.mjs send --to <name|session-ref|pane-id> --text <text> [--from <name>] [--expects-reply]
//   bridge-cli.mjs listen --name <name>   (register on broker, print inbound as JSONL)
import { BrokerClient } from "./broker.mjs";
import { buildRoster, sendToTarget, pickLane } from "./route.mjs";
import { readInbox } from "./inbox.mjs";

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith("--")) {
        args[key] = next;
        i++;
      } else {
        args[key] = true;
      }
    } else {
      args._.push(a);
    }
  }
  return args;
}

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

const args = parseArgs(process.argv.slice(2));
const command = args._[0];

if (command === "list") {
  const { roster, errors } = await buildRoster({ fromName: args.from });
  const rows = roster.map((e) => ({ ...e, lane: pickLane(e) }));
  if (args.json) {
    process.stdout.write(JSON.stringify({ sessions: rows, errors }, null, 2) + "\n");
  } else {
    for (const r of rows) {
      const name = r.name || "(unnamed)";
      process.stdout.write(
        `${r.provider.padEnd(7)} ${String(r.lane).padEnd(13)} ${name}  [${r.sessionRef?.value ?? r.paneId}]  ${r.status ?? ""}  ${r.cwd}\n`,
      );
    }
    for (const e of errors) process.stderr.write(`warning: ${e}\n`);
  }
  process.exit(0);
} else if (command === "send") {
  if (!args.to || !args.text) fail("send requires --to and --text");
  const result = await sendToTarget(args.to, args.text, {
    fromName: args.from,
    expectsReply: Boolean(args["expects-reply"]),
  });
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  process.exit(result.ok ? 0 : 1);
} else if (command === "listen") {
  const client = new BrokerClient({ name: args.name || `bridge-listener-${process.pid}` });
  client.onInbound = (from, message) => {
    process.stdout.write(JSON.stringify({ from: { id: from.id, name: from.name, cwd: from.cwd }, message }) + "\n");
    // Ack so sender receipts resolve.
  };
  const sessionId = await client.connect();
  process.stderr.write(`listening as ${args.name || "(unnamed)"} sessionId=${sessionId}\n`);
  process.on("SIGINT", () => {
    client.close();
    process.exit(0);
  });
  // Keep process alive on the socket.
} else if (command === "inbox") {
  if (!args.key) fail("inbox requires --key <session-ref-or-pane-key>");
  const key = String(args.key).replace(/[^a-zA-Z0-9._-]+/g, "_");
  const { path, entries } = readInbox(key, { consume: Boolean(args.consume) });
  process.stdout.write(JSON.stringify({ path, count: entries.length, consumed: Boolean(args.consume), entries }, null, 2) + "\n");
  process.exit(0);
} else {
  fail("usage: bridge-cli.mjs <list|send|listen|inbox> [options]");
}
