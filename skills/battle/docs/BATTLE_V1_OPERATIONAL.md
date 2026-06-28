# Battle v1 Operational Slice

Battle v1 operational is the first production-shaped proof rung after
`battle-003`. It keeps the `battle-003` hidden SQLi/XSS Docker fixture but changes
the proof contract from a one-shot race into a four-party session:

1. Arena Team creates/selects the Docker target and hidden ground truth.
2. Red Team runs bounded asynchronous exploit probe workers.
3. Blue Team runs bounded asynchronous patch/regression workers.
4. Scorekeeper replays objective outcomes inside Docker and derives the
   scoreboard.
5. Warm-pond winners and negative evidence are promoted to `$memory`.
6. The monitor serves generated artifacts, including a force graph.

## Command

```bash
cd skills/battle
./run.sh battle-v1-operational battle-003 \
  --out /tmp/battle-v1-operational-a \
  --red-workers 2 \
  --blue-workers 2 \
  --max-attempts 4 \
  --require-memory
```

Run a second time against the same memory service to prove recall of promoted
mutations:

```bash
./run.sh battle-v1-operational battle-003 \
  --out /tmp/battle-v1-operational-b \
  --red-workers 2 \
  --blue-workers 2 \
  --max-attempts 4 \
  --require-memory
```

## Required artifacts

```text
arena-receipt.json
red/team-receipt.json
blue/team-receipt.json
scorekeeper/scorekeeper-receipt.json
context/memory-recall-receipt.json
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
- Memory promotion requires the `$memory` HTTP service unless the command is run
  with `--memory-optional`; acceptance should use `--require-memory`.
