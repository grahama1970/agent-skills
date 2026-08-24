---
name: ops-calendly
description: >
  Operate the Calendly integration for grahama.co: inspect Calendly API
  connectivity, generate safe public scheduling metadata, manage the
  CALENDLY_PAT GitHub secret, and plan real capacity holds for scheduling.
  Use for "calendly api", "calendly embed", "calendly secret",
  "grahama.co booking", "ops-calendly", or "meeting slot capacity".
triggers:
  - calendly api
  - calendly embed
  - calendly secret
  - grahama.co booking
  - ops-calendly
  - meeting slot capacity
  - booking scarcity
metadata:
  short-description: Calendly API ops for grahama.co scheduling
provides:
  - calendly-readiness
  - calendly-site-metadata
  - calendly-secret-management
  - scheduling-capacity-planning
composes:
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - scheduling
  - integration
  - developer-tooling
runtime_self_improvement: basic
disciplines:
  - observability-operations
  - developer-tooling
---

# Ops Calendly

Use this skill for the grahama.co Calendly integration and related Calendly API
operations. The core contract is simple: the personal access token is a
server-side/build-time credential, public site output contains only scheduling
links and display metadata, and any calendar-affecting operation fails closed
unless the human explicitly authorizes the exact mutation.

## Commands

```bash
./run.sh doctor --json
./run.sh event-types --json
./run.sh generate-site-metadata --out ../../site/calendly.json --json
./run.sh github-secret --repo grahama1970/agent-skills --json
./run.sh github-secret --repo grahama1970/agent-skills --execute --json
./run.sh capacity-holds plan --week current --target-ratio 0.45 --json
./run.sh capacity-holds execute --week current --reason focus --execute --json
./run.sh capacity-holds release --receipt <receipt.json> --execute --json
./run.sh sanity
```

`doctor`, `event-types`, and `generate-site-metadata` use `CALENDLY_PAT` from
the environment. The PAT may live in `~/.zshrc` for local development, but
production builds should receive it as a GitHub Actions secret named
`CALENDLY_PAT`. `github-secret --execute` sets that secret from the local
environment using `gh secret set`; without `--execute` it reports the intended
action only.

## Public Metadata

`generate-site-metadata` writes `calendly.json` with only public fields:
Calendly display name, slug, timezone, scheduling URL, active event type names,
durations, kinds, and scheduling URLs. It must never write bearer tokens, API
headers, raw user payloads, invitee data, or webhook secrets into the static
site bundle.

For deterministic local tests, pass `--fixture-me` and `--fixture-event-types`.
Fixture output is marked `generatedFromApi: false`; live API output is marked
`generatedFromApi: true`.

## Capacity Holds

`capacity-holds plan` computes real capacity holds for the current week. It
does not write to Calendly or Google Calendar. `capacity-holds execute` creates
real Busy events on the Google Calendar checked by Calendly, but only when the
caller passes `--execute`. `capacity-holds release` deletes events recorded in
a prior write receipt, also only with `--execute`.

The default and maximum target ratio is `0.45`. Treat that as a cap for
legitimate focus, delivery, travel, or admin time. Do not create or recommend
calendar holds whose purpose is only to make availability look scarce. Write
receipts are stored under `/mnt/storage12tb/skills/ops-calendly/receipts` by
default, or wherever `--receipt-out` points.

Calendar writes use the same local OAuth token contract as `ops-google-calendar`:
`~/.config/ops-google-calendar/token.json`, or `OPS_GCAL_CONFIG_DIR` when
overridden. The token must have the `calendar.events` scope.

## Boundaries

- No token output. Never print `CALENDLY_PAT`, Authorization headers, or full
  provider payloads that could contain sensitive details.
- Read-only by default. Secret writes and calendar writes require `--execute`.
- `capacity-holds release` may delete only events listed in a prior
  `ops_calendly.capacity_holds.write.v1` receipt.
- Fail closed on missing credentials. Preserve existing site metadata only when
  the caller requests it and the existing file already exists.
- Use the live Calendly API for integration proof when `CALENDLY_PAT` is
  available; fixture-backed sanity tests prove deterministic behavior only.

## References (retrieve on demand — do not vendor)

External docs drift; cite the canonical URLs and fetch them when needed
with `/context7` (library docs) or `/fetcher` (any URL/PDF) rather than
caching stale copies. Verified reachable (HTTP 200) 2026-08-24.

- Calendly developer portal: <https://developer.calendly.com/>
- Calendly API reference: <https://developer.calendly.com/api-docs>
- llms.txt (LLM-friendly doc index): <https://developer.calendly.com/llms.txt>
- llms-full.txt (expanded LLM index): <https://developer.calendly.com/llms-full.txt>

```bash
skills/context7/run.sh "calendly api scheduling"
skills/fetcher/run.sh "https://developer.calendly.com/api-docs"
```
