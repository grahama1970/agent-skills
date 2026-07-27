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
| `lease`, `comment`, `block`, `release`, `close`, `close-duplicate` | Guarded issue lifecycle wrappers. `close` requires `--results`. |
| `file-upstream FILE` | File a blocking ticket in another repo and cross-link it to the blocked one. |
| `verify ISSUE --cmd CMD` | Run deterministic local commands and write a proof file. |
| `attach-proof ISSUE --file proof.md` | Comment proof on the issue. |
| `ci status`, `ci rerun`, `ci dispatch` | Explicit GitHub Actions status/rerun/dispatch helpers. |

## Cross-repo dependencies

When a ticket cannot proceed until another project ships something, record the
dependency machine-readably so `project-watchdog` can clear it automatically.

Link an upstream ticket that already exists:

```bash
skills/ticket/run.sh block 149 \
  --reason reason.md \
  --blocked-by grahama1970/graph-memory-operator#61 \
  --release
```

File the upstream ticket and link it in one step:

```bash
skills/ticket/run.sh file-upstream "Memory /recall must return tool_chains" \
  --downstream grahama1970/tau#149 \
  --upstream-repo grahama1970/graph-memory-operator \
  --type bug --target src/graph_memory/recall.py \
  --current-state "recall(brief=true) omits tool_chains entirely" \
  --requested-outcome "recall returns a populated tool_chains item" \
  --proof "pytest tests/unit/test_recall_chain_contract.py plus a live read-back" \
  --route backend_python_or_skill_runtime \
  --apply
```

The upstream body is built through the same ticket contract as any other
ticket; this only adds cross-links. Both commands validate the reference and
refuse one that cannot be read, because the watchdog poll fails closed — a bad
reference would stall the downstream ticket forever rather than erroring.

Downstream gets `blocked:upstream` plus a `blocked-by: owner/repo#N` comment.
Upstream gets `blocks-downstream` and a back-link. When every declared upstream
closes, the watchdog removes the label and the ticket returns to the routable
pool.

## Agent routing

Tickets are stamped `agent-work` at file time when they carry a concrete
`--route` and their type is not `question` or `triage`. That label is what the
`project-watchdog` router selects on; without it a ticket is invisible to
automated dispatch. Human-first types and unknown routes are deliberately left
unstamped.

## Proof contract

**Filing.** `--proof` must name a live end-to-end command. A deterministic test
alone is refused, because a fixed expectation can be satisfied by a change that
targets the expectation rather than the behaviour. Observed 2026-07-27: a ticket
proved by `pytest test_calc.py -q` was satisfied by a patch that subclassed
`int` and overrode `__eq__` so the result compared equal to two different
numbers. The test passed; an independent reviewer re-ran it and it passed too.

A path is not an entrypoint: `pytest tests/test_e2e.py` is still a deterministic
runner and is refused.

**Closing.** `close` requires `--results`, an
`agent_skills.ticket_closure_evidence.v1` document:

```json
{
  "schema": "agent_skills.ticket_closure_evidence.v1",
  "issue": 123,
  "unit": {"command": "uv run pytest -q", "exit_code": 0, "passed": 56},
  "e2e": {
    "command": "./run.sh sanity-live.sh --allow-live",
    "exit_code": 0,
    "mocked": false,
    "live": true,
    "artifact": "/abs/path/receipt.json"
  }
}
```

Closure is refused unless both suites exit 0, `e2e.mocked` is false, `e2e.live`
is true, `e2e.command` is not a deterministic runner, and `e2e.artifact` exists
and is non-empty — read back from disk here, because a tool's own success
response is not proof that it wrote anything.

See `best-practices-github-ticket`, Verification Contract.

## Rules

- Do not file vague tickets. Missing target or proof becomes `triage`.
- Prefer one independently verifiable acceptance criterion per ticket.
- For monitor-created maintenance tickets, use the monitor finding as the
  current state and the focused re-audit command as required proof.
- Use `fleet --dry-run` review before `fleet --apply`.
- Do not close without a non-empty proof file and a leased issue.
- GitHub Actions evidence is useful, but CI green alone is not closure proof.
- Do not use this skill to bypass `$best-practices-github-ticket`.
