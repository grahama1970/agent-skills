---
name: ops-buzz
description: >
  Buzz relay client for posting skill notifications, rendering Buzz-ready
  messages, querying recent channel messages, and checking Buzz CLI
  connectivity. Use when a skill needs to notify Buzz, post a morning report,
  inspect Buzz configuration, or prepare a Buzz agent-facing handoff.
allowed-tools:
  - Bash
  - Read
  - Write
triggers:
  - buzz
  - buzz notification
  - buzz relay
  - post to buzz
  - buzz morning report
  - buzz agent handoff
  - ask buzz agent
provides:
  - buzz-notification
  - buzz-message-query
  - buzz-config-readiness
composes: []
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - operations
  - notification
  - agent-orchestration
runtime_self_improvement: basic
---

# ops-buzz

Thin, agent-safe wrapper around the upstream `buzz-cli` surface.

Buzz is the chat and agent workspace. Domain skills remain the source of truth
for their own artifacts. `ops-buzz` only transports or queries Buzz messages and
records receipts for what it attempted.

## Grounded upstream contract

Use the existing Buzz CLI and relay model:

- `buzz-cli` is the agent-first CLI; it reads `BUZZ_RELAY_URL` and signs requests
  with `BUZZ_PRIVATE_KEY`.
- `buzz messages send --channel <uuid> --content -` posts a message from stdin.
- `buzz messages get --channel <uuid> --limit <n>` reads recent channel messages.
- `buzz messages search --query <text>` searches messages.
- Buzz's own agent guidance prefers Nostr events and `buzz-cli` over new bespoke
  HTTP endpoints.

Do not add a new Buzz relay endpoint from this skill. If a missing Buzz feature
is needed, implement it upstream in `buzz-cli`/Buzz first, then wrap it here.

## Current authority

Allowed:

- render a Buzz-ready Markdown message from a typed payload;
- dry-run a post and write a receipt;
- call `buzz messages send` when configuration exists and `--dry-run` is not set;
- call `buzz messages get` and `buzz messages search`;
- prepare agent-facing handoff text.

Not established in v0:

- durable Buzz agent job requests;
- verifying that Claude/Codex agents answered a message;
- appending decisions back into another skill's ledger;
- creating, editing, or deleting Buzz channels;
- direct relay HTTP signing independent of `buzz-cli`.

## Commands

```bash
./run.sh config doctor --json
./run.sh render-message --input summary.json --output message.md
./run.sh post --channel <uuid> --input message.json --dry-run
./run.sh post --channel <uuid> --input message.json
./run.sh messages get --channel <uuid> --limit 20
./run.sh messages search --query "monitor opportunities"
```

## Message payload contract

`render-message` and `post` accept JSON shaped like:

```json
{
  "schema": "ops_buzz.message.v1",
  "title": "Morning opportunities",
  "body": "4 opportunities found.",
  "source_skill": "monitor-opportunities",
  "source_run_id": "run:example",
  "source_url": "http://example.invalid/report",
  "external_effects": false,
  "items": [
    {"title": "Role", "subtitle": "Company", "url": "https://example.invalid"}
  ]
}
```

The producer validates the payload before rendering or posting and stamps:

```json
"seam_validation": {"kind": "ops_buzz.message.v1", "status": "PASS"}
```

`external_effects` must be `false` for dry-run and Stage 0 monitor summaries.
This field refers to the source workflow; posting a Buzz message is still a
Buzz write when `--dry-run` is omitted.

## Configuration

Environment variables:

| Variable | Meaning |
|---|---|
| `BUZZ_RELAY_URL` | Buzz relay URL. Defaults are owned by `buzz-cli`; set explicitly for production use. |
| `BUZZ_PRIVATE_KEY` | Nostr private key used by `buzz-cli` for NIP-98 signing. |
| `BUZZ_BIN` | Optional path/name for `buzz`; defaults to `buzz`. |

Optional local config:

```text
ops-buzz.config.json
```

This file is gitignored and may store non-secret defaults such as channel IDs.
Secrets belong in the environment, not in the skill directory.

## Composition pattern

For `$monitor-opportunities`:

1. `$monitor-opportunities` writes the source-of-truth report manifest.
2. It renders a small `ops_buzz.message.v1` payload with report URL, shortlist,
   blockers, source health, and `external_effects=false`.
3. It calls `skills/ops-buzz/run.sh post --channel <uuid> --input <payload>`.
4. The returned receipt is stored alongside the monitor run.

The Buzz channel is an interactive front door. It is not the decision ledger.

## Agent-facing handoffs

Buzz may have Claude and Codex agents that can read `agent-skills/skills`.
Until a live agent-response receipt exists, this skill treats agent handoffs as
messages only. A future promotion may add `ask-agent` with:

- target agent identity or mention;
- source artifact path/URL;
- expected response contract;
- timeout and readback query;
- receipt containing the request event and observed response event.

## Safety

- Do not send credentials in message content.
- Do not infer a Buzz write succeeded from subprocess exit alone; capture stdout,
  stderr, exit code, and parsed JSON when possible.
- Do not claim agent completion from a posted mention; a response event must be
  read back.
- Do not mutate another skill's ledger directly. Domain skills own their own
  decisions and receipts.

## Eval posture

`eval_not_required`: v0 is a deterministic CLI transport wrapper with no
autonomous agent behavior. `sanity.sh` covers positive rendering, missing-config
negative control, dry-run no-network behavior, and payload/schema validation.
Live Buzz posting is intentionally opt-in because it requires local relay,
identity, and channel configuration.
