---
name: ticket
description: >
  File, split, look up, lease, verify, comment, close, and route GitHub tickets
  for agent-resolved bugs, features, design changes, maintenance, questions,
  and triage. Use when users say ticket bug, ticket feature, ticket lookup,
  split changes into tickets, lease a GitHub issue, attach proof, close a ticket,
  or trigger GitHub Actions verification for a ticket.
triggers:
  - ticket bug
  - ticket feature
  - ticket lookup
  - create github issue
  - file a ticket
  - split design changes into tickets
  - lease a github issue
  - attach proof to issue
  - close a ticket with proof
  - trigger github actions for a ticket
provides:
  - github-ticket-filing
  - ticket-fleet-splitting
  - ticket-lookup
  - ticket-lease-routing
  - ticket-proof-attachment
  - github-actions-ticket-verification
composes:
  - best-practices-github-ticket
complies:
  - best-practices-skills
  - best-practices-github-ticket
  - best-practices-python
taxonomy:
  - governance
  - orchestration
  - validation
  - proof
runtime_self_improvement: basic
---

# Ticket

Thin CLI for GitHub ticket filing and issue lifecycle operations. It applies
`$best-practices-github-ticket` ticket body contracts and delegates guarded
issue state changes to `skills/best-practices-github-ticket/scripts/gh-ticket-tools.sh`.

In the shared maintainer architecture, `$ticket` is the work-item boundary
between monitor/reporting skills and Tau-backed repair workers. Monitors may
draft or explicitly create tickets; maintainers lease one ticket at a time;
reviewers/verifiers attach deterministic proof before closure.

## Use

```bash
skills/ticket/run.sh bug "Fix stale WebGPT tab recovery" \
  --target skills/surf \
  --observed "webgpt.submit fails after stale CDP attach" \
  --expected "emits exact extract/resume command or repairs safely" \
  --repro "Run webgpt.submit against a stale controlled tab" \
  --proof "focused surf test plus webgpt preflight smoke"

skills/ticket/run.sh feature "Add compact design sidebar" \
  --target skills/hum/ui \
  --limitation "Design requests arrive as broad batches" \
  --capability "Split UI work into independently verifiable tickets" \
  --workflow "Designer files one focused change per acceptance criterion" \
  --acceptance "Each ticket has screenshot proof and a focused test" \
  --proof "targeted UI test plus screenshot"

skills/ticket/run.sh fleet design-review.md \
  --target skills/hum/ui \
  --route design_or_ux \
  --agent designer

skills/ticket/run.sh maintenance "Repair monitor-skill-health finding" \
  --target skills/example \
  --invariant "Target skill passes its monitor-skill-health finding" \
  --cleanup "Concrete violation emitted by latest_results.jsonl" \
  --scoped-files "skills/example/SKILL.md" \
  --proof "skills/monitor-skill-health/run.sh audit --skill example --no-memory --no-deep-review --json" \
  --route backend_python_or_skill_runtime \
  --agent agent-skill-maintainer \
  --label monitor-skill-health
```

Ticket creation is preview-first. Add `--apply` to create issues. Lifecycle
commands such as `lease`, `comment`, `block`, `release`, `close`, and
`close-duplicate` call the guarded helper.

## Commands

| Command | Purpose |
| --- | --- |
| `bug`, `feature`, `optimization`, `maintenance`, `question`, `triage` | Build and optionally create one compliant GitHub issue. |
| `fleet FILE` | Split a list of requested changes into one ticket preview per item; `--apply` files them. |
| `lookup` | Search, next, or show issues through the guarded helper. |
| `lease`, `comment`, `block`, `release`, `close`, `close-duplicate` | Guarded issue lifecycle wrappers. |
| `verify ISSUE --cmd CMD` | Run deterministic local commands and write a proof file. |
| `attach-proof ISSUE --file proof.md` | Comment proof on the issue. |
| `ci status`, `ci rerun`, `ci dispatch` | Explicit GitHub Actions status/rerun/dispatch helpers. |

## Cross-repo dependencies

When a ticket cannot proceed until another ships, record the dependency
machine-readably so `project-watchdog` can clear it:

```bash
skills/ticket/run.sh block 149 \
  --reason reason.md \
  --blocked-by grahama1970/graph-memory-operator#61 \
  --release
```

Repeatable. Downstream gets `blocked:upstream` plus a `blocked-by: owner/repo#N`
comment; upstream gets `blocks-downstream` and a back-link.

Every reference is validated **before** the downstream issue is touched, and a
reference that cannot be read is refused. The watchdog poll fails closed, so a
bad reference would stall the downstream ticket forever rather than erroring.

## Per-ticket bootstrap context

`project-watchdog` forwards the whole issue body to the repair node, so the body
is the only project context a stateless, cron-dispatched agent receives. Name the
load-bearing files and skills at file time instead of making it rediscover them
on every tick:

```bash
skills/ticket/run.sh bug "Fix the thing" \
  --target skills/example \
  --observed "..." --expected "..." --repro "..." \
  --proof "live run against the real service, read back from the receipt" \
  --context-file GOAL.md \
  --context-file skills/example/src/thing.py \
  --required-skill best-practices-python \
  --required-skill review-code \
  --depends-on grahama1970/agent-skills#1040
```

All three are optional and repeatable, and available on `bug`, `feature`,
`optimization`, and `maintenance` — the agent-routable types. Omitting them
leaves the body byte-identical to before. They are mirrored into the
`ticket-skill` marker block for machine reads, and `--depends-on` renders
`blocked-by: owner/repo#N`.

Only the VARIABLE context belongs here. Universal execution policy — read
project knowledge, lease one issue, fail closed, retain proof — lives in
`best-practices-github-ticket` and is referenced, not copied into every issue:
identical boilerplate in every body dilutes the ticket-specific signal and costs
context on every dispatch.

## Rules

- Do not file vague tickets. Missing target or proof becomes `triage`.
- Prefer one independently verifiable acceptance criterion per ticket.
- For monitor-created maintenance tickets, use the monitor finding as the
  current state and the focused re-audit command as required proof.
- Use `fleet --dry-run` review before `fleet --apply`.
- Do not close without a non-empty proof file and a leased issue.
- GitHub Actions evidence is useful, but CI green alone is not closure proof.
- Do not use this skill to bypass `$best-practices-github-ticket`.
