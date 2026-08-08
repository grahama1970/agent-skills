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
  - buzz-agent-request
composes:
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - operations
  - notification
  - agent-orchestration
runtime_self_improvement: basic
disciplines:
  - observability-operations
  - agentic-orchestration
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
- prepare agent-facing handoff text;
- post a bounded agent request and optionally read back channel messages for a
  response receipt.

Not established in v0:

- durable Buzz `KIND_JOB_REQUEST` events;
- semantic validation of Claude/Codex answer quality;
- appending decisions back into another skill's ledger;
- creating, editing, or deleting Buzz channels;
- direct relay HTTP signing independent of `buzz-cli`.

## Commands

```bash
./run.sh config doctor --json
./run.sh render-message --input summary.json --output message.md
./run.sh post --channel <uuid> --input message.json --dry-run
./run.sh post --channel <uuid> --input message.json
./run.sh ask-agent --input agent-request.json --dry-run
./run.sh ask-agent --input agent-request.json --wait
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
| `BUZZ_IDENTITY_KEY` | Backward-compatible local identity key; `run.sh` exports it as `BUZZ_PRIVATE_KEY` when the latter is unset. |
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
`ask-agent` is a generic message/readback primitive. It does not claim that the
agent completed the requested work unless a response event is observed.

Request payload:

```json
{
  "schema": "ops_buzz.agent_request.v1",
  "channel": "00000000-0000-0000-0000-000000000000",
  "target_agent": "codex",
  "mention_pubkey": "optional hex or npub",
  "prompt": "Inspect this monitor-opportunities run and summarize blockers.",
  "expected_response": "Return a short finding list with artifact paths.",
  "source_skill": "monitor-opportunities",
  "source_run_id": "run:example",
  "source_url": "http://example.invalid/report",
  "source_artifact": "/path/to/report-manifest.json",
  "timeout_seconds": 60,
  "poll_interval_seconds": 5,
  "readback_limit": 20
}
```

Receipt statuses:

| Status | Meaning |
|---|---|
| `DRY_RUN` | Rendered and validated without calling Buzz. |
| `REQUEST_FAILED` | Buzz send command exited non-zero. |
| `REQUEST_POSTED_NO_READBACK` | Request event was posted, but no response polling was requested. |
| `NO_RESPONSE` | Request posted and polling finished without observing a response. |
| `RESPONSE_OBSERVED` | A candidate response event was read back from the channel. |

Limits and non-claims:

- target agent identity or mention;
- source artifact path/URL;
- expected response contract;
- timeout and readback query;
- receipt containing the request event and observed response event.
- response observation is syntactic readback, not semantic acceptance;
- domain skills decide whether to use the response.

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
