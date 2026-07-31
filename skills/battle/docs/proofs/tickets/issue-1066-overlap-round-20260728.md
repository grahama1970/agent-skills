# Issue #1066 overlap round proof

Date: 2026-07-28

## Scope

Issue #1066 requires one Battle round to start exactly one Red worker and one proactive Blue worker concurrently against the same deterministic Docker fixture. Blue's first action must use only public scenario/target input, the Judge must derive the outcome from runtime receipts, and the ledger must show:

- `blue_started_at < red_terminal_at`
- `red_started_at < blue_terminal_at`

This proof does not claim the broader multi-round production scheduler epic is complete.

## Implementation

- `skills/battle/src/battle_skill/orchestrator.py`: `run_round_concurrent` now submits Red and proactive Blue futures before awaiting either future. Blue receives an empty findings list for its first action.
- `skills/battle/scripts/prove_overlap_round.py`: deterministic Docker-backed overlap proof with JSON event ledger, worker receipts, Judge replay receipt, and scorekeeper receipt.
- `skills/battle/run.sh`: added `prove-overlap-round` command.
- `skills/battle/tests/test_overlap_round.py`: focused regression test that asserts proactive Blue starts before Red finishes and receives no Red findings.
- `skills/battle/sanity.sh`: corrected the known-defect set initialization so the backend eval summary can complete.

## Commands

```bash
cd skills/battle && uv run --project . python -m pytest tests/test_overlap_round.py -q
```

Result: `1 passed in 0.52s`

```bash
./skills/battle/run.sh prove-overlap-round \
  --out /home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-1066-overlap-round-proof \
  --timeout-s 30
```

Result: `status=PASS`, `mocked=false`, `live=true`

```bash
skills/battle/sanity.sh > /tmp/issue-1066-battle-sanity.out 2>&1
```

Result: exit `0`; tail includes `BATTLE_BACKEND_EVAL_ALL_PASS`, backend eval `13/13`, and `Result: PASS`.

```bash
git diff --check -- \
  skills/battle/run.sh \
  skills/battle/sanity.sh \
  skills/battle/src/battle_skill/orchestrator.py \
  skills/battle/scripts/prove_overlap_round.py \
  skills/battle/tests/test_overlap_round.py
```

Result: exit `0`

## Receipt summary

Proof directory:

`skills/battle/local/issue-1066-overlap-round-proof/`

Receipt hashes:

```text
b3c09dee0a587bbf6316c1b30f60b57574ed24fdf924b07b1f85fdc814186b23  proof-summary.json
f4786f536d9cb5a67851c0587f1b9b4f3e35761ada4689c8c756013bc74d9ca6  event-ledger.json
d75a49c27136ce197c2d34b3af0a4d64eeed66d319c3e6d54c569eafcacebfb3  blue-first-action-input.json
377cdd4dcf99f48b0e0f1882a38cac522f39973a6299b4a6b06673739728915f  judge-receipt.json
96ef3232bd5893c73dc0d81cbc473143f772c7f2103722fa76b9fed0e0817079  scorekeeper-receipt.json
```

Overlap timestamps from `proof-summary.json`:

```json
{
  "blue_started_at_ns": 689297295092925,
  "blue_terminal_at_ns": 689297825998117,
  "red_started_at_ns": 689297294811772,
  "red_terminal_at_ns": 689298095926445
}
```

Checks:

```json
{
  "blue_first_input_has_no_red_artifact": true,
  "blue_started_before_red_terminal": true,
  "judge_replay_present": true,
  "one_blue_worker": true,
  "one_red_worker": true,
  "red_started_before_blue_terminal": true,
  "scorekeeper_present": true
}
```

Blue first-action input:

```json
{
  "public_target": "fixture/target/app.py",
  "received_red_exploit_artifact": false,
  "received_red_finding": false,
  "scenario_id": "overlap-zip-slip-deterministic",
  "schema": "battle.blue_first_action_input.v1",
  "target_sha256": "d332b8a7aad66d36d653450f0899e0fc2ea38d802d77591d06b05b78dab89b97"
}
```

## Evidence classification

- mocked: no
- live: yes
- exercised: focused orchestrator concurrency regression, Docker-backed deterministic Red/Blue overlap proof, Judge replay receipt, scorekeeper receipt, full Battle sanity script.
- remains unverified: broader multi-round production scheduler epic, multi-worker swarm scheduling, provider-routed Battle execution.
