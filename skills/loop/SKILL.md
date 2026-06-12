---
name: loop
description: >
  Bounded Codex workflow for one artifact slot: inspect, produce or edit,
  verify, and repair until verifier PASS, BLOCKED, or max attempts.
metadata:
  short-description: One-artifact inspect -> produce -> verify loop
---

# Loop Skill

Use `$loop` when the user wants Codex to complete one bounded artifact until a checkable outcome is reached, such as:

- `$loop implement function X with explorer, coder, and code-reviewer until PASS`
- `$loop repair Widget X until code-reviewer passes or 3 attempts are used`
- `$loop produce an evidence case draft and verify it until PASS or BLOCKED`

User-facing simplicity is the product. Keep the prompt small; keep the protocol here.

## Boundary with project orchestration

`$loop` is a transaction for one artifact slot, not a project DAG engine.

Outer orchestrators such as Scillm DAG, a project agent, or another planner own
multi-node project plans, cross-artifact dependencies, scheduling, fanout/fanin
across independent artifacts, and promotion decisions. `$loop` owns the inner
completion cycle for one artifact:

```text
inspect -> produce/edit -> verify -> repair -> receipt
```

Do not grow this skill into a generic dependency scheduler. If a workflow spans
multiple independent artifacts, keep that graph outside `$loop` and call `$loop`
as the worker for each artifact-sized node.

## Design contract

- Prompt = intent.
- This skill = bounded protocol.
- Subagents = labor.
- Durable run files = source of truth.
- Code-reviewer = fresh judgment.
- Receipt validator = trust gate.
- Caps = safety.

Do not replace this with a one-off external harness unless the user explicitly asks. Do use the small deterministic scripts bundled with this skill for preflight, receipt validation, and scope checks.

Recipes live under `references/recipes/`. They describe bounded one-artifact
flows, not arbitrary DAG execution.

Generic one-artifact receipts may use `receipt_type: "loop-run.v1"` and the
validator at `scripts/validate_loop_run_receipt.py`. This schema is constrained:
one artifact slot, optional read-only exploration fanout, at most one
write-capable producer lane, and a required fresh read-only verifier for
`VERIFIER_PASS`. It is not a dependency planner.

## Hard requirements

1. Explicitly ask Codex to spawn subagents by name. Default code-change loops use `explorer`, `coder`, and `code-reviewer`; documentation loops may use `explorer`, `technical-writer`, and `code-reviewer`.
2. Never run two write-capable agents in the same worktree at the same time.
3. Keep subagent nesting shallow. Recommended project config: `agents.max_depth = 1`.
4. Final `PASS` is valid only when the final `code-reviewer` receipt verdict is `PASS`.
5. The `code-reviewer` must be read-only and must report `edited_files: []`.
6. Stop on `PASS`, `BLOCKED`, `MAX_ATTEMPTS`, or human decision needed.
7. Save a durable run directory before returning a final summary.
8. After each subagent completes, save its receipt and close that subagent handle before spawning the next phase.

## Default policy

Unless the user says otherwise:

- `max_attempts`: 3
- `agent_sequence`: `explorer` → producer (`coder` or `technical-writer`) → `code-reviewer`
- `reasoning_effort`: medium for any subagent whose reasoning level is not specified
- `parallel_writers`: forbidden
- `reviewer_mode`: fresh read-only
- `stop_on`: reviewer PASS, reviewer BLOCKED, max attempts, unclear human decision
- `subagent_lifecycle`: spawn → wait → save receipt → close_agent → next phase

`wait` is not the same as `close_agent`. A completed but unclosed subagent may
still count against the runtime's open-thread budget. The loop should keep at
most one active subagent handle in the default sequential repair path.

## Resolve before starting

Resolve these values. Ask one concise clarification if any required value is missing and cannot be safely inferred.

- `objective`
- `allowed_scope.include`
- `allowed_scope.exclude` if needed
- `max_attempts`
- `reasoning_effort` per subagent, defaulting unspecified subagents to medium
- `done_condition`
- immediate run or scheduled run

## Preflight

Before spawning subagents, run the static preflight if scripts are available:

```bash
python .agents/skills/loop/scripts/doctor.py --repo . --print-json
```

If the preflight reports missing skill files, missing custom agents, invalid config, or an unsafe repository state that would make the loop ambiguous, stop with `BLOCKED` and report the missing item.

## Durable run layout

Create one run directory and keep it unchanged for the run:

```text
.loop/runs/<loop_id>/
  intent.md
  explorer-receipt.json
  attempts/
    01/
      coder-receipt.json
      changed-files.txt
      diff.patch
      tests.log
      code-reviewer-receipt.json
    02/
      ...
  final-receipt.json
  status.md
```

Use durable files rather than chat memory as the source of truth. Do not approve a task from a child summary alone; inspect the actual diff, checks, and reviewer receipt.

## Immediate loop protocol

### 1. Explore

Spawn `explorer` first unless the user explicitly says to skip exploration.

Instruction to child:

```text
You are the explorer subagent for this $loop run.
Stay read-only. Do not edit files.
Map the objective, allowed scope, likely target files, likely tests, constraints, risks, and smallest implementation path.
Return an Explorer Receipt JSON and no final verdict.
```

Save the Explorer Receipt as `.loop/runs/<loop_id>/explorer-receipt.json`.
After the receipt is saved, close the explorer subagent handle before spawning
the coder.

### 2. Implement attempt N

Spawn `coder` for exactly one implementation or repair attempt.

Instruction to child:

```text
You are the coder subagent for attempt N of this $loop run.
Use the objective, allowed scope, explorer receipt, and any code-reviewer findings from the prior attempt.
Make the smallest scoped patch.
Touch only allowed files.
Run relevant tests/checks when available.
Return a Coder Receipt JSON. Do not mark the task approved.
```

After the coder returns, capture:

```bash
python .agents/skills/loop/scripts/capture_attempt_artifacts.py \
  --out-dir .loop/runs/<loop_id>/attempts/NN
```

`changed-files.txt` must use the same changed-file sources as the scope checker:
unstaged tracked changes, staged/index changes, and untracked files, excluding
`.loop/**` run artifacts. `diff.patch` must include reviewable content for
unstaged tracked, staged/index, and untracked files.

Run targeted tests/checks when known and save the output to `tests.log`. If no deterministic test exists, record a concrete `no_test_explanation`.
After the coder receipt and attempt artifacts are saved, close the coder
subagent handle before spawning `code-reviewer`.

### 3. Review attempt N

Spawn `code-reviewer` after the coder finishes. Do not run it before the diff/check artifacts exist.

Instruction to child:

```text
You are the code-reviewer subagent for attempt N of this $loop run.
Stay fresh and read-only. Do not edit files.
Review actual repository state, not only the coder summary.
Use the objective, allowed scope, explorer receipt, changed-files.txt, diff.patch, tests.log if present, and relevant source files.
Return exactly one verdict: PASS, NEEDS_CHANGES, or BLOCKED.
Return a Code-Reviewer Receipt JSON with edited_files: [].
```

Save the Code-Reviewer Receipt as `.loop/runs/<loop_id>/attempts/NN/code-reviewer-receipt.json`.
After the receipt is saved, close the code-reviewer subagent handle before
deciding whether to stop or spawn the next coder attempt.

### 4. Decide

- `PASS`: stop immediately. Write `final-receipt.json` with `final_verdict: PASS` and `stop_reason: REVIEWER_PASS`.
- `NEEDS_CHANGES`: if attempts remain, pass only the concrete reviewer findings to `coder` for the next attempt.
- `BLOCKED`: stop. Write `final_verdict: BLOCKED` and `stop_reason: REVIEWER_BLOCKED`.
- max attempts used without PASS: stop. Write `final_verdict: NEEDS_CHANGES` and `stop_reason: MAX_ATTEMPTS`.

Never continue after a reviewer PASS. Never continue after max attempts.

If spawning a subagent fails because of an open-thread or agent-handle limit,
close all completed subagent handles, then retry the same spawn once. If the
retry fails, stop with `BLOCKED` and record the failed spawn and close attempts
in `status.md` and the final receipt if one can be produced.

## Final receipt

Write the final receipt to `.loop/runs/<loop_id>/final-receipt.json` and validate it:

```bash
python .agents/skills/loop/scripts/validate_loop_receipt.py .loop/runs/<loop_id>/final-receipt.json --print-summary
```

Return a short human summary plus the final receipt path. If the user or project agent asks for machine output, return the final JSON only.

## Scheduled mode

Scheduling is not a core `$loop` responsibility. Prefer an outer orchestrator
such as Scillm DAG, a project agent, cron wrapper, or CI job to decide when to
call `$loop`.

If the user explicitly provides `schedule:`, `cron:`, or `rerun:`, use this
legacy helper path:

1. Normalize the loop prompt into `.loop/jobs/<job-name>/prompt.md`.
2. Ensure the saved prompt explicitly says to use `explorer`, `coder`, and `code-reviewer` subagents.
3. Generate a reviewed cron entry with `scripts/render_cron.py`.
4. Do not silently install cron. Show the generated crontab line unless the user explicitly asks to install it.
5. If `run_now: true`, run one immediate loop after registration.
6. Return a schedule registration receipt.

Recommended helper:

```bash
python .agents/skills/loop/scripts/render_cron.py \
  --job-name <job-name> \
  --schedule '<cron expression>' \
  --repo '<repo root>' \
  --prompt-file '.loop/jobs/<job-name>/prompt.md' \
  --out-dir '.loop/jobs'
```

Cron is non-interactive. The generated runner defaults to `LOOP_CODEX_CMD='codex exec -'`; users may override `LOOP_CODEX_CMD` for their environment. The runner uses a lock directory so scheduled runs do not overlap.

## Receipt validation commands

Changed-file scope:

```bash
python .agents/skills/loop/scripts/check_changed_files.py \
  --include 'src/**' \
  --include 'tests/**'
```

Final receipt:

```bash
python .agents/skills/loop/scripts/validate_loop_receipt.py .loop/runs/<loop_id>/final-receipt.json --print-summary
```

Generic one-artifact receipt:

```bash
python .agents/skills/loop/scripts/validate_loop_run_receipt.py .loop/runs/<loop_id>/final-receipt.json --print-summary
```

## Failure modes

Return `BLOCKED`, not a fake PASS, when:

- required custom agents are missing;
- allowed scope is unclear;
- the reviewer edited files;
- tests/checks are required but cannot be run;
- the diff touches disallowed files;
- child receipts are absent or malformed;
- a human product/security decision is needed.
