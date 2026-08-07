---
name: cursor-agents
description: >
  Control and inspect Cursor Cloud Agents through the official Cursor Agents API.
  Use this when users ask for Cursor Agents, webcursor, cursor.com/agents control,
  Cursor Cloud Agent runs, Cursor agent usage, or Cursor agent API checks.
triggers:
  - cursor agents api
  - cursor cloud agents
  - webcursor
  - cursor.com/agents control
  - inspect cursor agent runs
  - cursor agent usage
provides:
  - cursor-agents-api-control
  - cursor-agent-run-inspection
  - cursor-agent-usage-inspection
composes: []
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - automation
  - external-api
  - verification
runtime_self_improvement: none
disciplines:
  - agentic-orchestration
  - developer-tooling
---

# Cursor Agents

Use this skill to control Cursor Cloud Agents through Cursor's documented REST
API at `https://api.cursor.com/v1`. Do not use `$surf`, `$browser-oracle`, or
`$ask cursor-browser` as the primary control path for `https://cursor.com/agents`.
Those browser paths are for visual inspection or Cursor's embedded ChatGPT
Browser view IDs, not for reliable Cursor Cloud Agent lifecycle control.

## Authentication

Set one of these environment variables:

```bash
export CURSOR_API_KEY=...
```

Fallback names are also accepted for local compatibility:

```bash
export CURSOR_AGENTS_API_KEY=...
export CURSOR_SERVICE_ACCOUNT_API_KEY=...
```

The API key is never printed by this skill. Requests default to HTTP Basic auth
with the key as the username and an empty password, matching Cursor's examples.
Use `--auth bearer` only when calling an endpoint that explicitly requires a
Bearer service account token.

## Commands

```bash
# Credential and models endpoint check.
./run.sh doctor --receipt /tmp/cursor-agents-doctor.json

# List supported models.
./run.sh models --json --receipt /tmp/cursor-agents-models.json

# Inspect an agent.
./run.sh agent <agent-id> --json

# Inspect recent runs for an agent.
./run.sh runs <agent-id> --limit 20 --json

# Inspect usage for an agent or one run.
./run.sh usage <agent-id> --run-id <run-id> --json

# Escape hatch for documented endpoints not yet wrapped.
./run.sh raw GET /v1/models --json
```

Mutating raw requests (`POST`, `PATCH`, `PUT`, `DELETE`) require `--yes`.
Agents must not create or mutate Cursor agents unless the human explicitly
authorizes the side effect.

## Receipts

Every command accepts `--receipt <path>`. Receipts include:

- schema version
- command
- endpoint path
- auth mode
- HTTP status
- response JSON when available
- bounded error details on failure

Receipts intentionally omit API keys and authorization headers.

## Browser UI Boundary

`https://cursor.com/agents` in Chrome can be useful for visual inspection with
Surf screenshots or JavaScript reads, but it is not the operational control
contract. If a user gives a Chrome tab id for that page, first confirm the tab
is live for inspection, then use this API skill for agent creation, polling,
runs, and usage.

`$ask cursor-browser` is a different integration: it controls Cursor's embedded
Browser pane through a local bridge and requires a `viewId`, not a Chrome tab id.

## Verification

```bash
./sanity.sh
```

This runs deterministic local HTTP-contract tests. It does not prove live Cursor
API availability.

```bash
./sanity-live.sh
```

This performs a non-mutating live `GET /v1/models` check and writes a receipt
under `/tmp`. It requires `CURSOR_API_KEY`.
