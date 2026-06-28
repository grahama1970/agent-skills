# Battle v0

Battle v0 is a deterministic, local fixture contract proof for the battle skill's
missing judge boundary.

It follows the useful part of the goal-locked harness pattern: every meaningful
transition leaves a local artifact that another agent or human can inspect,
replay, or reject. Battle v0 does not hide scoring inside model reasoning. Red
proves the seeded exploit, Blue applies a deterministic patched file, Judge
verifies the synced arena, and the scoreboard is derived from the Judge receipt.

This is a proof rung, not a production Battle campaign. Treat the generated
receipts, monitor index, Playwright screenshot, and CDP screenshot as evidence
for this rung only.

## Claim Scope

```json
{
  "mocked": false,
  "live": "local_deterministic_fixture",
  "agentic": false,
  "models_used": []
}
```

This proves only:

- Red receipt emission for a seeded local exploit check.
- Blue receipt emission for deterministic patched-file replacement.
- Independent Judge receipt emission after Blue is synced into the arena.
- Scoreboard status and verdict derived from the Judge receipt.
- Monitor index generation for generated artifacts.
- Artifact-backed monitor rendering when those artifacts are copied into
  `monitor/battle/public/artifacts/battle-001`.

## Artifact Contract

The backend run writes these required artifacts:

```text
battle-plan.json
red-receipt.json
blue-receipt.json
judge/judge-receipt.json
scoreboard.json
monitor-index.json
run-receipt.json
```

The React monitor must load generated artifacts from:

```text
/artifacts/battle-001/monitor-index.json
/artifacts/battle-001/scoreboard.json
/artifacts/battle-001/red-receipt.json
/artifacts/battle-001/blue-receipt.json
/artifacts/battle-001/judge/judge-receipt.json
```

If any required generated artifact is missing or unreadable, the monitor must
fail closed with `BATTLE MONITOR BLOCKED` and must not be used as UI acceptance
evidence.

## Non-Claims

Battle v0 does not prove:

- real Red agent behavior
- real Blue agent behavior
- scillm or OpenCode execution
- anvil or code-runner patch quality
- multi-round learning
- Docker or QEMU modes
- memory learning
- Lean or QRA assurance

## Validation

Run from `skills/battle`:

```bash
./run.sh battle-fixture battle-001 --out /tmp/battle-001
python3 -m json.tool /tmp/battle-001/red-receipt.json
python3 -m json.tool /tmp/battle-001/blue-receipt.json
python3 -m json.tool /tmp/battle-001/judge/judge-receipt.json
python3 -m json.tool /tmp/battle-001/scoreboard.json
python3 -m json.tool /tmp/battle-001/monitor-index.json
python3 -m json.tool /tmp/battle-001/run-receipt.json
```

Then copy generated artifacts into the monitor public directory:

```bash
rm -rf monitor/battle/public/artifacts/battle-001
mkdir -p monitor/battle/public/artifacts/battle-001
cp -R /tmp/battle-001/* monitor/battle/public/artifacts/battle-001/
```

Run from `skills/battle/monitor/battle`:

```bash
npm install
npm run build
npm run test:e2e
test -f test-results/battle-monitor.png
```

UI acceptance also requires a live browser/CDP screenshot of the generated
artifact route. DOM assertions and build success are not visual proof by
themselves.
