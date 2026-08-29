# pi-herdr-bridge

Companion extension to [pi-intercom](https://github.com/nicobailon/pi-intercom)
(MIT). Adds cross-provider session discovery and messaging: Pi, Codex, and
Claude Code sessions on one machine can find each other and exchange bounded
text messages, using Herdr as the roster/transport for the non-Pi providers.

Upstream pi-intercom is untouched: this package joins the same broker as a
peer; it never patches installed pi-intercom code.

## Architecture

| Role | Owner |
|---|---|
| Registry + Pi delivery (turn-triggering) | pi-intercom broker (`~/.pi/agent/intercom/broker.sock`) |
| Codex/Claude/Pi pane discovery + session refs | `herdr agent list` |
| Codex inbound | `codex queue --thread <uuid> --message <text>` (codex-cli >= 0.149) |
| Claude / pane-only Pi inbound | `herdr agent prompt <pane_id> <text>` |
| Pi agent tool | `herdr_bridge` (registered by `index.ts`) |
| Non-Pi agents / scripts | `bridge-cli.mjs` |

Delivery lane is picked per target: `intercom` for broker-connected Pi
sessions, `codex-queue` for Codex panes with a session UUID, `herdr-prompt`
otherwise. Target resolution is fail-closed on ambiguity.

## CLI

```bash
node bridge-cli.mjs list [--json]
node bridge-cli.mjs send --to <name|session-ref|pane-id> --text "..." [--from <name>] [--expects-reply]
node bridge-cli.mjs listen --name <name>    # join broker, print inbound as JSONL
```

## Pi extension

Install by adding this directory as a package extension (or symlink into
`~/.pi/agent/extensions/`), then restart Pi. Registers the `herdr_bridge`
tool with `action=list|send`.

## Conventions

- Pane/queue messages are bounded notifications or questions. Durable work
  orders, receipts, and approvals stay file-based (ops-herdr pattern).
- `herdr agent prompt` types into a live terminal; it is only used for
  targets without a structured inbound lane, and inherits monitor-herdr's
  guidance: never assume submission from a zero exit alone.

## Tests

```bash
npm test          # framing, roster normalization, lane routing, fake-broker e2e
```

Live proof commands (run manually):

```bash
# broker round trip without touching a real agent session
node bridge-cli.mjs listen --name probe &
node bridge-cli.mjs send --to probe --text ping
```

## Protocol note

The broker protocol (length-prefixed JSON frames; `register`/`list`/`send`;
`registered`/`sessions`/`message`/`delivered` responses) was implemented from
reading pi-intercom `broker/{framing,paths,protocol}.ts` at its installed
version. If upstream bumps `INTERCOM_PROTOCOL_VERSION` (currently 1), re-read
those files before trusting this client.
