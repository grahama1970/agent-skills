# Battle Handoff - main branch proof path

Timestamp: 2026-07-28T20:32Z
Branch rule: work only on `agent-skills@main`. Do not resume old Battle feature branches.

## Current Slice

Objective: inventory the existing Battle backend proof path, patch the obvious failures directly, and prove it without spending a reviewer competition.

Deterministic path found:

```bash
cd skills/battle
./run.sh backend-eval --out-dir <out>
./run.sh prove-backend-goal
./run.sh prove-spectator-source-build
```

## Repairs In This Slice

- Kill-shot Pixi replay fixture now uses canonical `blue.kill_confirmed` terminal events and consistent clock/timeline fields.
- Outcome validator now allows kill attribution only when the canonical terminal event is present while preserving the no-inference guard.
- Backend goal proof no longer assumes Battle is served from SPARTA's `:3002`; spectator proof starts its own Battle preview port.
- Spectator proof avoids unnecessary `npm install` when `node_modules` is already usable.
- Parent-spawn lifecycle enrichment now uses the fresh combiner artifact directory before the Vite build copies public fixtures.
- Adaptive lineage V13 proof no longer depends on `/tmp` source artifacts and samples the Pixi canvas for mobile visibility.
- Adaptive lineage validator supports depth-N spawn lineages while retaining the V14 memory boundary.
- Battle standalone Vite source-build path is wired for `$test-interactions`.

## Proof Receipts

Backend eval:

```bash
cd skills/battle
./run.sh backend-eval --out-dir local/backend-eval-20260728T-kill-shot-repair
```

Receipt: `skills/battle/local/backend-eval-20260728T-kill-shot-repair/receipt.json`

Result:

```json
{
  "mocked": false,
  "live": false,
  "summary": {
    "passed": 14,
    "failed": 0,
    "total": 14,
    "channels": [
      "adaptive_lineage_fixtures",
      "deterministic_contracts",
      "genetic_lifecycle_fixtures",
      "live_transport",
      "race_replay_fixtures"
    ]
  }
}
```

Full backend goal proof:

```bash
cd skills/battle
BATTLE_BACKEND_GOAL_PROOF_DIR=$PWD/local/backend-goal-proof-20260728T-kill-shot-repair-final ./run.sh prove-backend-goal
```

Log: `skills/battle/local/prove-backend-goal-20260728T-kill-shot-repair-final.log`
Receipt directory: `skills/battle/local/backend-goal-proof-20260728T-kill-shot-repair-final/`
Result markers:

```text
BATTLE_PROVE_SPECTATOR_PASS
OK: checked 566 test file(s); no mock+proof claim violations
BATTLE_PROVE_BACKEND_GOAL_PASS
```

Source-built Battle interaction proof:

```bash
cd skills/battle
./run.sh prove-spectator-source-build
```

Proof: `skills/battle/local/spectator-source-build-source-build-20260728T203204Z/proof.json`
Interaction results: `skills/battle/local/spectator-source-build-source-build-20260728T203204Z/captures/results.json`
Screenshot: `skills/battle/local/spectator-source-build-source-build-20260728T203204Z/captures/battle-receipt-controls/0012_pane-controls_screenshot.png`

Result:

```json
{
  "mocked": false,
  "live": true,
  "interaction_counts": {
    "total": 12,
    "passed": 12,
    "failed": 0,
    "warned": 0,
    "skipped": 0
  }
}
```

Visual inspection note: the screenshot visibly shows the source-built Battle header, roster search with `red`, selected timeline lane, zoom controls, live-events panel, and left/right pane toggles after the interaction sequence.

Focused code checks:

```bash
cd skills/battle
uv run pytest tests/test_battle_event_adapter_contract.py -q
# 99 passed

cd skills/battle/spectator
npm run test -- src/lib/battle-adaptive-lineage.test.ts src/lib/battle-adaptive-lineage-depth3.test.ts
# 8 passed

npm run typecheck
# exit 0
```

## Honest Scope

This slice proves the existing MVP backend proof path and the source-built interaction path. It does not prove production hosting, long-running provider reliability, audible playback, or that every future Battle product goal has been accepted by the human.

Any future UI claim must include `$test-interactions` output and an inspected screenshot. Any future backend readiness claim must include a fresh `prove-backend-goal` receipt or a narrower receipt that states exactly what it proves and does not prove.

Immutable Goal: NOT_MET
