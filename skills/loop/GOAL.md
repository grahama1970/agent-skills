# GOAL: loop Codex smoke spike

**Status:** Proof gate pending; not production-ready.
**Last updated:** 2026-06-12

## Objective

Prove one clean Codex smoke test for the v2 `$loop` bundle.

This is not production work. Do not add features. Do not work on cron, GitHub,
PR babysitting, production maintenance, or Scillm integration. Do not modify the
design unless the smoke fails and the failure is concrete.

## Current Verdict

```json
{
  "verdict": "CONTINUE_AS_SPIKE",
  "production_ready": false,
  "reason": "Static bundle and architecture are coherent, but live Codex skill/subagent behavior is not proven yet.",
  "next_gate": "One clean parse-duration live smoke test.",
  "abandon_condition": "Named subagents or receipt production fail in a way that cannot be fixed with a small skill/prompt adjustment."
}
```

## Keep If Smoke Proves

1. Codex recognizes `$loop`.
2. Codex spawns `explorer -> coder -> code-reviewer`.
3. `code-reviewer` stays read-only.
4. The run writes `.loop/runs/<loop_id>/final-receipt.json`.
5. `validate_loop_receipt.py` passes.
6. `sample-target` tests pass.
7. Changed-file scope check passes.
8. The loop stops within max attempts.

## Abandon Or Redesign If

1. Codex ignores the skill.
2. Codex does not reliably spawn named subagents.
3. The reviewer edits files.
4. Receipts are missing or fake.
5. The parent cannot produce predictable `.loop/runs` artifacts.
6. The system only works when a human manually steers every step.

## Required Smoke Procedure

Run static checks in a clean v2 starter repo:

```bash
python -m unittest discover -s tests
python .agents/skills/loop/scripts/doctor.py --repo . --print-json
```

Then start Codex from the repo root and run the sample parse-duration `$loop`
prompt.

## Required Proof

- `explorer`, `coder`, and `code-reviewer` subagents spawned in order.
- `code-reviewer` was read-only.
- `.loop/runs/<loop_id>/final-receipt.json` exists.
- `validate_loop_receipt.py` passes.
- `python -m unittest discover -s sample-target/tests` passes.
- `check_changed_files.py` passes for `sample-target/src/time/**` and `sample-target/tests/**`.
- `attempts_used <= 3`.
- Final `PASS` only if `code-reviewer` returned `PASS`.

## Stop Condition

Return exactly one of:

- `PASS`: all required proof exists and validates.
- `NEEDS_CHANGES`: smoke ran and produced concrete repairable failures.
- `BLOCKED`: Codex skill/subagent behavior or receipt production fails in a way
  that cannot be repaired by a small skill or prompt adjustment.
