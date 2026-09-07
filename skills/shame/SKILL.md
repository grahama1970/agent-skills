---
name: shame
description: >
  Capture human-labeled bad agent updates, inspect retained failure history, and operate the Pi status/continuation guard and bounded task harness.
triggers:
  - shame this response
  - record this bullshit update
  - add this response to shame training
  - mark this response as commit laundering
  - mark shame false positive
  - mark shame false negative
  - vague status update
  - git-heavy response
provides:
  - classifier-training-data
  - response-label-capture
  - failure-history
composes:
  - memory
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - validation
  - feedback
  - training-data
disciplines:
  - evaluation-quality
  - developer-tooling
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Shame

One status/continuation guard, one bounded task runner, and one failure journal.
Human labels are separate from machine-observed failures. This skill records
examples; it does not train or promote a classifier.

The immutable goal and completion criteria live in `immutable_goal.json`.
The executable status contract is `scripts/agent_status_schema.py` (pydantic,
`extra="forbid"`). Full command examples and runtime details live in the primary
checkout's `extensions/pi/lazy-report-shame-shame-shame/README.md`.

## Operator and agent entrypoints

```text
/shame status                         # enabled/mode, last report, task, history, entrypoint hash
/shame task start /absolute/task.json # operator-approved task budget
/shame task status
/shame failures                       # recent failures from this session
/shame failures --all --limit 20       # explicit cross-session view
/shame show                           # latest raw candidate, not failure history
/shame review                         # interactive human label picker
/shame reject commit_laundering -- human explanation
/shame allow normal_answer -- human explanation
/shame warn jargon_no_status
/shame undo
/shame off|normal|strict
```

Agents can read the same journal with the read-only `shame_failures` tool
(`limit`, optional `all`) or `skills/shame/run.sh failures --json`.
Use `skills/shame/run.sh preflight <candidate.md|->` to run the same stop-boundary
status checker before spending a terminal retry; preflight never authorizes final
completion, because the final stop revalidates current proof bytes.
`/shame-task` and `/lazy-report-shame-shame-shame` remain compatibility commands.

## Stop-boundary behavior

- Preserve intermediate responses and tool calls. Validate only terminal
  assistant `stopReason="stop"` messages with no tool calls or queued work.
- Mutating or guard-forced runs must include one fenced `json` block containing
  `pi.agent_status.v1`. A leading `$shame`, `/shame`, or `/skill:shame` invocation
  activates self-correction; mentioning those names in an advisory question does
  not. Strict mode remains an explicit opt-in. Actual mutations remain guarded.
- Pydantic data decides status validity. Never classify status prose with regex
  or an LLM. Strip model status prose/raw JSON; render the visible answer before
  the `Status Report` metadata. Trailing prose after valid JSON is ignored.
- Immutable-goal turns must lead with a decisive answer headline: `IMMUTABLE_GOAL:
  COMPLETE`, `IMMUTABLE_GOAL: NOT_COMPLETE`, or `IMMUTABLE_GOAL: NEEDS_HUMAN`.
  Do not bury the goal state under proof, commits, or status metadata.
- Any validated `state=needs_human` classification must be sent through
  `$ops-discord` before the turn is accepted. No exceptions: if Discord delivery
  cannot return `ops_discord.notification_receipt.v1` with `status=SENT`,
  `message_id`, and `message_url`, the report is rejected rather than silently
  relying on chat visibility.
- Compile actionable status data once and dispatch at `agent_end`. Identical
  status text at distinct stops is legitimate; replaying one event is not.
- Aborts, errors, length limits, and shutdown do not start reporting retries.
- Every report-repair episode allows one output-only correction, armed or unarmed.
  `UNLAZY_FORCED_RETRY` identifies that correction: all tools are blocked and a
  failed correction cannot queue another. A typed `lazy_report_shame.recovery_decision.v1`
  separates formatting repair from missing evidence, unresolved work, and validator
  failure before any retry prompt is sent. Fresh human input clears correction
  and skill-read flags. Formatting repair cannot reopen accepted work.
- After two same-goal/triage failure fingerprints, require a plain human question,
  valid `debugger.proof.v1`, or `lazy_report_shame.debugger_failure_handoff.v1`
  with exact file:line and debugger error. Preserve the failure evidence.

## pi.agent_status.v1

Every status requires a non-empty `goal` and `changed` (use `no change: <reason>`
when appropriate). State-specific data:

| State | Required data |
|---|---|
| `done` | non-empty `verified[]` and `proof[]`; no `not_done` |
| `continuing` | `not_done[].item` and runnable `next_command` |
| `needs_human` | exact `needs_human.action` and `reason` |
| `failed` | `failure.triage.code` from triage-error or minted `*_unclassified_<8hex>` |
| `needs_brave_search` | `queries[]` |
| `needs_agent` | `project_agent_family`, cross-family `handler`, `question`, and a `brave-search` typed `parent_refs[]` entry |
| `needs_webgpt` | `question` and typed `parent_refs[]` entries from both `brave-search` and `ask` |
| `needs_roundtable` | immutable goal, question, at least three handlers |
| `needs_competition` | immutable goal, task, at least two handlers, criteria |

`not_done` is legal only with `continuing`; human actions belong in `needs_human`.
For `done`, proofs must be non-empty local files. Materialize URLs/digests through
the owning skill first. JSON proofs must declare a supported receipt schema and pass
that schema's checks, including `ticket.closure_receipt.v1` for ticket closure.
Each verified command/result pair must be backed by one proof record; unrelated
text matches across files do not authorize completion. This proves consistency,
not OS-level authenticity or universal obedience.

## Failure history versus human labels

Automatic append-only journal:

```text
/mnt/storage12tb/skills/shame/failures/events.jsonl
```

`LAZY_REPORT_SHAME_FAILURE_LOG` overrides the path. Events retain session identity,
kind, reason codes, goal when available, candidate/failure fingerprints, bounded
excerpts, and receipt paths. They cover rejected reports, agent-reported failures,
observed tool/provider errors, task-budget failures, and continuation dispatch exceptions.
An agent-reported failure is not independent proof of its underlying cause.

History reads default to the current session when available; `--all` requests all
sessions. The reader scans the last 4 MiB and bounds returned JSON to 32 KiB;
`tail_limited`, `output_limited`, and `malformed_lines` expose incomplete reads.
A log-write error is visible and does not create another retry loop. No automatic
backfill or classifier labeling is performed.

Latest candidate recovery remains session-scoped and atomic:
`/mnt/storage12tb/skills/shame/training/pending-review-packet.json.sessions/<sha256(session-id)>.json`.
`LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET` changes the base path, not isolation.
Legacy packets are read only by their recorded owner with a matching candidate hash.

Human labels use `lazy_report_shame.training_example.v2` and go to:
- `/mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl`
- Memory `shame_training_examples`
- Searchable `project_knowledge` shadow documents

Use Memory `POST /store`; verify both rows through `/recall/by-keys` and the shadow
through `/recall` with `tags=["shame"]`. No raw AQL or direct Arango/Qdrant writes.

```bash
skills/shame/run.sh capture --text "Committed and pushed." --verdict reject --reason vague_git_update
skills/shame/run.sh capture --session "$PI_SESSION_FILE" --entry-id ID --verdict allow --reason normal_answer
skills/shame/run.sh capture --no-memory --text "fixture" --verdict reject --reason synthetic_fixture
skills/shame/run.sh failures --all --limit 20 --json
skills/shame/run.sh audio status
skills/shame/run.sh audio install --source /path/to/single-shame.wav
```

Legacy labels remain supported. Audio policy: one short Chatterbox word, no bell
or loop; installer bounds are 0.9–2.5 seconds and at least 0.45 seconds active speech.

## Bounded tasks and ownership

An operator arms `pi.task_budget.v1` through `/shame task start` or
`SHAME_TASK_BUDGET`. It fixes one deliverable, write paths, named argv checks,
input/check-definition files, and deadlines. Raw shell/unapproved tools are
blocked; `task_check` runs approved checks. Passing unchanged inputs reuse evidence;
failures permit two repairs; reviews never automatically resubmit. All required
checks and delivery readbacks passing makes `accepted` terminal.

Explicit question mode is read/search-only and skips status/quality gates. Fresh
human questions after accepted/exhausted tasks can inspect history without reopening
execution. Approved commands are trusted capabilities, not OS-sandboxed programs.
No sudo is needed for these controls. Unarmed sessions retain compatibility behavior.

Ponytail remains generation guidance, not another gate. Architecture diagrams are
optional predeclared deliverables, never automatic stop-time work. Do not add
review rounds, new gates, or unrelated improvements after acceptance.

## Retained validation

Every enforcement feature must have retained `$agentic-evals` coverage and a
read-back receipt before completion is reported. Retain scoped changes through
commit/push when no external blocker prevents it; Git metadata is not product proof.

```bash
uv run --with pydantic python3 skills/shame/scripts/immutable_goal_schema.py validate skills/shame/immutable_goal.json
skills/agentic-evals/run.sh run skills/shame/fixtures/agentic_eval.json --output /tmp/shame-agentic-eval.json
skills/agentic-evals/run.sh run skills/shame/fixtures/agentic_eval.json --case invalid-proof-recovery --output /tmp/shame-proof-recovery-eval.json
```

One canonical catalog covers real Pi conversations, tool execution, CLI operations,
Memory, and installed audio. The extension catalog aliases it; do not run both.
Use `--case NAME` for focused checks. Mock-Pi drivers, fabricated proof helpers,
and the old prose-variation catalog are removed. See `fixtures/EVALUATION.md` for
coverage and explicit gaps. Never present a green count as proof of unchecked outcomes.

## Ecosystem

See `skills/agent-ecosystem/SKILL.md`. Shame owns status, feedback, and history;
the runner owns execution/acceptance; triage-error owns failure vocabulary;
Memory owns durable recall; Ponytail shapes generation. Authority-changing handoffs
use `pi.receipt_envelope.v1` or owner-specific typed receipts. Internal observations
and failure-history rows are not new acceptance authorities.
