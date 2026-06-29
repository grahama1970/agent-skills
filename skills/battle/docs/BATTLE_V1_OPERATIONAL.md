# Battle v1 Operational Slice

Battle v1 operational is the first production-shaped proof rung after
`battle-003`. It keeps the `battle-003` hidden SQLi/XSS Docker fixture but changes
the proof contract from a one-shot race into a four-party session:

1. Arena Team creates/selects the Docker target and hidden ground truth.
2. Red Team runs bounded asynchronous exploit probe workers.
3. Blue Team runs bounded asynchronous patch/regression workers.
4. A live research broker runs agent-side Brave/GitHub/Dogpile lanes
   concurrently before warm-pond candidate selection.
5. Scorekeeper replays objective outcomes inside Docker and derives the
   scoreboard.
6. Warm-pond winners and negative evidence are promoted to `$memory`.
7. The monitor serves generated artifacts, including a force graph.

## Command

```bash
cd skills/battle
./run.sh battle-v1-operational battle-003 \
  --out /tmp/battle-v1-operational-a \
  --red-workers 2 \
  --blue-workers 2 \
  --max-attempts 4 \
  --require-memory \
  --research-broker
```

Run a second time against the same memory service to prove recall of promoted
mutations:

```bash
./run.sh battle-v1-operational battle-003 \
  --out /tmp/battle-v1-operational-b \
  --red-workers 2 \
  --blue-workers 2 \
  --max-attempts 4 \
  --require-memory \
  --research-broker
```

## Required artifacts

```text
arena-receipt.json
red/team-receipt.json
blue/team-receipt.json
scorekeeper/scorekeeper-receipt.json
context/memory-recall-receipt.json
context/research-broker-receipt.json
context/memory-promotion-receipt.json
context/context-receipt.json
scoreboard.json
monitor-index.json
run-receipt.json
subagent-ledger.sqlite
graph/battle-v1-force-graph.json
```

## Validation

```bash
python3 sanity/battle_v1_operational_acceptance.py \
  /tmp/battle-v1-operational-a \
  --allow-first-recall-empty

python3 sanity/battle_v1_operational_acceptance.py \
  /tmp/battle-v1-operational-b \
  --require-recall-found
```

Current live research-broker proof:

```bash
./run.sh battle-v1-operational battle-003 \
  --out /tmp/battle-v1-research-dispatch-001 \
  --red-workers 1 \
  --blue-workers 1 \
  --max-attempts 1 \
  --require-memory \
  --tau-live \
  --research-broker

python3 sanity/battle_v1_operational_acceptance.py \
  /tmp/battle-v1-research-dispatch-001 \
  --allow-first-recall-empty \
  --min-red-workers 1 \
  --min-blue-workers 1
```

Observed receipt fields:

```text
/tmp/battle-v1-research-dispatch-001/run-receipt.json status=PASS verdict=BLUE_SUCCESS
/tmp/battle-v1-research-dispatch-001/tau-live/manifest.json status=PASS
/tmp/battle-v1-research-dispatch-001/tau-live/manifest.json scheduling.mode=asyncio.as_completed
/tmp/battle-v1-research-dispatch-001/context/research-broker-receipt.json status=PASS
/tmp/battle-v1-research-dispatch-001/context/research-broker-receipt.json mode=threadpool_as_completed
/tmp/battle-v1-research-dispatch-001/context/research-broker-receipt.json passed_lane_count=5
/tmp/battle-v1-research-dispatch-001/context/warm-pond-receipt.json selection_rule="highest research-adjusted affinity, deterministic id tiebreaker, Docker replay before memory promotion"
/tmp/battle-v1-research-dispatch-001/context/warm-pond-receipt.json research_weighted_candidate_count=6
/tmp/battle-v1-research-dispatch-001/context/warm-pond-receipt.json research_weighted_combination_count=8
/tmp/battle-v1-research-dispatch-001/red/workers/red-0-exploit-sqli-admin-or/worker-receipt.json research_dispatch.research_boost=0.2
/tmp/battle-v1-research-dispatch-001/blue/workers/blue-0-defense-parameterized-like/worker-receipt.json research_dispatch.research_boost=0.2
acceptance -> BATTLE_V1_OPERATIONAL_ACCEPTANCE_PASS
```

Monitor proof:

```bash
rm -rf monitor/battle/public/artifacts/battle-v1-operational
mkdir -p monitor/battle/public/artifacts/battle-v1-operational
cp -R /tmp/battle-v1-operational-b/* monitor/battle/public/artifacts/battle-v1-operational/
cd monitor/battle
npm install
npm run build
npm run test:e2e
test -f test-results/battle-monitor-v1-operational.png
```

## Rollback

The slice is additive. Remove the new CLI command and delete:

```text
src/battle_skill/battle_v1_operational.py
sanity/battle_v1_operational_acceptance.py
docs/BATTLE_V1_OPERATIONAL.md
```

Then remove the Battle v1 operational Playwright test block if it was added.
Generated artifacts under `/tmp` and `monitor/battle/public/artifacts` are safe
to delete.

## Known limitations

- This slice does not execute an unbounded swarm.
- It does not integrate QEMU or AFL campaigns.
- It does not route real Tau repair loops or Scillm batch tool execution.
- It does not wire the right-sidebar chat to orchestration mutations.
- It uses the existing deterministic `battle-003` tiny Python target.
- Research lanes are retrieval only. They must not run cloned PoC or exploit
  code on the host.
- Memory promotion requires the `$memory` HTTP service unless the command is run
  with `--memory-optional`; acceptance should use `--require-memory`.
