# Issue #46 async Battle scheduler proof

Date: 2026-07-28

## Scope

Issue #46 is the parent Battle async scheduler epic. The closure evidence is cumulative across the bounded slices that now exist in `skills/battle`:

- #1066 proves one Red worker and one proactive Blue worker overlap in the same deterministic Docker fixture, with JSON event-ledger timestamps and no Red exploit/finding in Blue's first-action input.
- #1065 proves live Memory-backed adaptive lineage storage and recall for Battle team evidence.
- This #46 proof proves the stronger BATTLE-004 pre-kill survival rung: bounded Red/Blue worker matrix, live Tau/Scillm handoffs, persona-tagged workers, public-only team visibility, Docker Judge replay, lineage receipts, and scorekeeper outcome.

This proof does not claim unbounded Battle swarm execution, Blue kill, fastest crash, promotion, QEMU/AFL campaigns, or overnight production scheduling.

## Commands

```bash
./skills/battle/run.sh arena-prekill-survival-proof battle-004 \
  --out /home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-46-arena-prekill-survival-proof \
  --red-workers 2 \
  --blue-workers 2 \
  --timeout-s 120
```

Result: exit `0`; `status=PASS`, `mocked=false`, `live=brave_search_docker_arena_oracle_tau_harness`.

```bash
cd skills/battle && UV_PROJECT_ENVIRONMENT=/tmp/issue46-uv-venv \
  uv run --project . python -m pytest tests/test_arena_live_battle_proof_contract.py -q
```

Result: `17 passed in 0.56s`

```bash
UV_PROJECT_ENVIRONMENT=/tmp/issue46-sanity-uv-venv \
  skills/battle/sanity.sh > /tmp/issue-46-battle-sanity.out 2>&1
```

Result: exit `0`; tail includes `BATTLE_BACKEND_EVAL_ALL_PASS`, backend eval `13/13`, and `Result: PASS`.

## Primary receipts

Proof directory:

`skills/battle/local/issue-46-arena-prekill-survival-proof/`

Receipt hashes:

```text
5dbc2b7f6163be4388f6cd48398483d18328f697083bbb87272eb7e1ab1c3f64  run-receipt.json
1c8808ee8a542b0aeaceb4892a00f1720f76250f7612c9e7e4d2f6469253e188  tau-live/manifest.json
8ac64166ebb901ee092f0b423fbc484592eb8a58211da00259ff8f55dd7255e9  scoreboard.json
22deb1ed1f6b8fa656f40c7c37c2bd2e1d6c6f5bb2e130d62be426fe9b6a675f  judge/judge-receipt.json
884ab75025d917b857f14c4202b6f54c2530057848632161a7bf4bc760f960b4  lineage-receipts.json
14524e4459ed948a308607badccf2594dfee24c3d0c3772d56bd26fda7880f4b  exploit-lifecycle-receipts.json
```

## Acceptance mapping

Async bounded worker matrix:

```json
{
  "blue_materialized": 2,
  "blue_requested": 2,
  "blue_success_pairs": 4,
  "judged_pairs": 4,
  "red_child_spawn_requested": true,
  "red_initial_requested": 1,
  "red_materialized": 2,
  "red_prekill_survival_requested": true,
  "red_requested": 2
}
```

Scheduler ticks / overlap evidence:

- `run-receipt.json.timing_receipts.schema`: `battle.control_plane_timing_receipts.v1`
- `run-receipt.json.timing_receipts.source`: `battle_control_plane_perf_counter`
- `timing_receipts.events`: `arena_context_ready`, `initial_tau_manifest_ready`, `visibility_validation_ready`, `judge-receipt`, `lineage-receipts`
- #1066 companion proof: `skills/battle/docs/proofs/tickets/issue-1066-overlap-round-20260728.md` records the strict overlap inequalities `blue_started_at < red_terminal_at` and `red_started_at < blue_terminal_at` in `event-ledger.json`.

Public-only team boundary:

```json
{
  "status": "PASS",
  "private_input_leaks": [],
  "worker_count": 4,
  "proves": [
    "Red/Blue Tau handoff and receipt artifacts do not reference Arena private paths or answer-key strings."
  ]
}
```

CWE and scenario context:

```json
{
  "schema": "battle.arena_scenario.v1",
  "scenario_id": "arena-zip-slip-import-001",
  "cwe": "CWE-22",
  "public_entrypoint": "/api/import-zip",
  "hidden_vulnerability_family": "Zip Slip path traversal"
}
```

Live Scillm/persona worker receipts:

```json
[
  {"team": "red", "worker_id": "red-0", "status": "PASS", "persona": "battle-red-public-auditor", "surface": "scillm.chat_completions", "model": "gpt-5.5", "materialized_status": "PASS"},
  {"team": "blue", "worker_id": "blue-0", "status": "PASS", "persona": "battle-blue-public-hardener", "surface": "scillm.chat_completions", "model": "gpt-5.5", "materialized_status": "PASS"},
  {"team": "blue", "worker_id": "blue-1", "status": "PASS", "persona": "battle-blue-public-hardener-variant-1", "surface": "scillm.chat_completions", "model": "gpt-5.5", "materialized_status": "PASS"},
  {"team": "red", "worker_id": "red-1", "status": "PASS", "persona": "battle-red-public-auditor-variant-1", "surface": "scillm.chat_completions", "model": "gpt-5.5", "materialized_status": "PASS"}
]
```

Blue defensive strategy receipts:

- `tau-live/blue/scillm-call-receipt.json`: `status=PASS`, `mocked=false`, `live=true`, selected methods include `canonicalize_destination_with_resolve`, traversal rejection, resolved target confinement, symlink rejection, and API preservation.
- `tau-live/blue/workers/blue-1/scillm-call-receipt.json`: `status=PASS`, `mocked=false`, `live=true`, selected methods include destination root canonicalization, absolute/drive path rejection, parent-directory rejection, resolved path confinement, and Zip symlink rejection.

Red exploit and Judge/scorekeeper receipts:

- `tau-live/red/scillm-call-receipt.json` and `tau-live/red/workers/red-1/scillm-call-receipt.json`: both `status=PASS`, `mocked=false`, `live=true`.
- `judge/judge-receipt.json`: Docker replay receipt with `status=PASS`.
- `scoreboard.json`: `status=PASS`, `verdict=BLUE_SUCCESS`, `judged_pair_count=4`, `blue_success_count=4`, `red_materialized_count=2`, `blue_materialized_count=2`.

Pre-kill lineage survival:

```json
{
  "status": "PASS",
  "errors": [],
  "lineage_request": {
    "mode": "prekill_survival_parent_decision",
    "status": "PASS"
  }
}
```

Live Memory companion proof:

- `skills/battle/docs/proofs/tickets/issue-1065-live-memory-lineage-20260728.md`
- `skills/battle/local/issue-1065-live-memory-proof/proof-summary.json`
- #1065 command result: `status=PASS`, `mocked=false`, `live=true`; Red/Blue store+upsert acks were real; next-generation recall found the owning survivor; negative controls were empty.

## Evidence classification

- mocked: no
- live: yes
- exercised: live Brave Search/Docker Arena oracle/Tau handoff/Scillm worker matrix, public-only visibility validation, Docker Judge replay, scorekeeper, pre-kill lineage survival, focused contract tests, and full Battle sanity.
- remains unverified: unbounded swarm execution, Blue kill, fastest crash, promotion, QEMU/AFL campaigns, and overnight production scheduling.
