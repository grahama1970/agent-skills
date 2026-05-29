# /ask Collaboration Status Contract

## Purpose

Multi-round **project agent + WebGPT** collaboration must not rely on chat
memory alone. Each review round uses a shared **`COLLABORATION_STATUS.md`**
(absolute path, auto-attached when embedded in the `$ask webgpt` question) so
both sides agree on:

- what is **accomplished** (proven),
- what is **in progress** (standing),
- what is **blocked**,
- whether **goals are met** for this round (dual agreement only),
- when **human assistance** is required.

`$plan-iterate` (or the human) **authors** goals and phase acceptance.
`$ask webgpt` **reviews** evidence against those bullets — it does not own the
backlog or close phases.

## Required file: `COLLABORATION_STATUS.md`

The project agent (or `plan-iterate package`) must refresh this file **before
every** `$ask webgpt` review round on a bound `--webgpt-project`.

Minimum sections:

```markdown
## North star
(one line — durable product intent)

## Accomplished
- bullet + proof path (ledger accepted, live e2e log, ask-id, etc.)

## Standing (not closed)
- what works in code/repo but is not yet accepted / not in scope this round

## Blockers
- Agent-actionable: …
- Human-required: … (only when agent cannot proceed)

## This round acceptance
1. …
2. …

## Agreement (round N)
- Project agent local gates: PASS | FAIL (command + log path)
- WebGPT review: PENDING | PASS | NEEDS_CHANGES | BLOCKED (ask-id path)
- Goals met this round: NO | YES (YES only if both PASS on same bullets above)
- Human needed: NO | YES (reason)
```

## Per-goal status (required)

Every tracked goal MUST carry exactly one status:

| Status | Meaning |
|--------|---------|
| **complete** | Proven with cited evidence (ledger `accepted`, live e2e log, `$ask` artifact `PASS`, etc.) |
| **outstanding** | In scope and actively remaining; not yet proven or not yet accepted |
| **blocked** | Cannot advance without a named blocker (human, infra, missing dependency) |
| **pending** | Not started yet, or waiting on a prerequisite goal |

Use a **Goals** table (recommended) or one line per goal under **Standing** / **Accomplished**:

```markdown
## Goals

| ID | Goal | Status | Proof / blocker |
|----|------|--------|-----------------|
| G-05 | Phase 05 full turn DAG accepted | outstanding | turn_loop not ledger-accepted |
| G-v03 | v0.3 isolated exec_smoke_call smoke | complete | mvp_v03_smoke_proof.json |
```

Rules:

- Do not mark **complete** without a proof path in the same row.
- **blocked** must name the blocker in **Proof / blocker** or **Blockers**.
- **This round acceptance** bullets should reference goal IDs when possible.
- **Goals met this round: YES** only when every bullet's linked goals are **complete** AND WebGPT + local gates both PASS.

WebGPT must answer against **This round acceptance** only. It must not
redefine north star or add out-of-scope phase work in a PASS verdict.

## Dual agreement (closure)

**Goals met / complete for a round** requires **both**:

| Party | Proof |
|-------|--------|
| **Project agent** | Deterministic gates pass (tests, live e2e, `plan-iterate` validation logs) recorded in **Agreement** |
| **WebGPT** | `$ask` artifact verdict **`PASS`** on the same acceptance bullets |

Neither party may unilaterally declare phase accepted, overall plan complete,
or "we are done" from prose alone.

### Agreement matrix

| Local gates | WebGPT | Next action |
|-------------|--------|-------------|
| PASS | PASS | **Goals met this round: YES**; eligible for `plan-iterate close-phase` |
| PASS | NEEDS_CHANGES | Patch; refresh status; re-run local gates; re-ask WebGPT |
| FAIL | PASS | **Trust local proof**; fix implementation; do not treat WebGPT PASS as closure |
| FAIL | NEEDS_CHANGES | Patch; refresh status; re-run |
| either | BLOCKED | See human escalation |
| PASS | (timeout / no artifact) | Infra recovery; retry `$ask webgpt`; **Goals met: NO** |

## WebGPT verdict vocabulary

WebGPT must return exactly one of:

- **`PASS`** — all **This round acceptance** bullets satisfied against attached evidence
- **`NEEDS_CHANGES`** — specific, actionable fixes (file/path anchored)
- **`BLOCKED`** — missing dependency or product decision the project agent cannot resolve

Optional machine-readable line:

```text
VERDICT: PASS
```

## Human assistance

Escalate to the human when **any** of:

1. WebGPT returns **`BLOCKED`** with a human-only dependency.
2. **Human-required** is non-empty in **Blockers** and the agent cannot clear it.
3. **`MAX_ROUNDS`** reached on the bounded loop.
4. **Disagreement** persists after one reconcile attempt.
5. `$plan-iterate continue` or `guard-final` returns **`HUMAN_REQUIRED`**.

Human-facing status: current state, blocker, proposed decision, evidence paths,
what changed since last round, whether human decision is required (max 3 questions).

## `$ask` invocation (required shape)

```bash
./run.sh ask webgpt "Read /path/to/COLLABORATION_STATUS.md.
Review ONLY 'This round acceptance'.
Return VERDICT: PASS | NEEDS_CHANGES | BLOCKED." \
  --webgpt-project <project-name> \
  --ask-id <stable-ask-id> \
  --run-output-root /tmp/ask-webgpt-<project> \
  --overwrite
```

Always embed the **absolute path** to `COLLABORATION_STATUS.md`. Proof is
`*.status.json`, not assistant paraphrase.

## Anti-patterns

- WebGPT PASS without local live e2e when bullets require them
- Project agent "done" without WebGPT PASS when review is required
- Skipping **COLLABORATION_STATUS.md** on round 2+ of the same `--webgpt-project`
- WebGPT inventing acceptance criteria mid-review
