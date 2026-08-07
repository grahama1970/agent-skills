# project-watchdog

> **Disciplines:** agentic-orchestration · observability-operations

A cron that keeps registered projects moving without a human babysitting them.

Each tick tries three lanes in order and stops at the first with work.

## 1. Repair — fix an open ticket

Scans registered repos for `agent-work` tickets, leases one, and dispatches a
two-seat creator/reviewer DAG through `$ask tau-dag`. The creator writes in a
worktree created from `origin/main` for that dispatch; it commits to its own
branch and must not push. When it finishes, the ticket is marked `agent-done`
and stops being routable — the work is a branch awaiting review, not a landed
fix.

## 2. Closure audit — closing a ticket is a claim

Two seats of different model families judge each `COMPLETED` closure against the
ticket's own acceptance criterion and required proof, reading the proof
artifacts the closure cited.

    any FAIL      → reopened, agent-work restored, back to the repair lane
    all PASS      → closure-verified, stays closed
    no verdict    → left closed and unverified

## 3. Completion attestation — an empty queue is not proof

When nothing is open and nothing is left to audit, a browser seat (WebGPT by
default — a different transport from the models that did the work) decides
whether the project is genuinely finished. On FAIL it names tickets to reopen
and the cycle repeats.

## Use

    ./run.sh status                      # registry, state, lock, cron
    ./run.sh tick --project <id>         # dry run, no mutation
    ./run.sh tick --apply --project <id> # one bounded dispatch
    ./run.sh set-state project paused --project <id> --reason "..."
    ./run.sh install-cron --apply
    ./sanity.sh

Exit codes: `0` success or deliberate refusal, `1` operational failure,
`2` caller error.

## What it refuses to do

- Dispatch a ticket it could not lease — nothing else stops a second repair.
- Author a repair in the registered checkout, or on a dirty target.
- Reset a worktree holding unmerged commits.
- Accept a closure whose proof cannot be shown, or reopen one that merely
  cannot be judged.
- Report a tick that serviced nothing as success when the reason will not clear
  on its own.

## Evaluation

    ./sanity.sh                                              # 45 behavioural gates
    uv run pytest tests -q                                   # 154 unit tests
    ~/.claude/skills/agentic-evals/run.sh run fixtures/agentic_eval.json

The eval fixture is regression-first: every adversarial case reproduces a defect
that actually happened, and each was verified by mutation to fail when its
defect is reintroduced.

See `SKILL.md` for the routing contract and `PROJECT_KNOWLEDGE.md` for current
state, decisions, and open questions.
