# Issue 1064 Proof: Adaptive Lineage Panel Source Binding

Ticket: https://github.com/grahama1970/agent-skills/issues/1064

## Repair

- Removed the static `adaptive-lineage-live.json` mechanics import from the receipt route.
- Bound the adaptive lineage mechanics panel to the currently loaded fixture source metadata.
- Added fixture SHA-256/source URL propagation through the shared Battle fixture loader.
- Added a source-bound panel mode that renders V13 canonical dual-team mechanics and fails closed for V14 when `mechanics_trees` is absent.
- Added regression coverage for V13 -> V14 route switching so stale V13/static fixture data cannot remain in the panel.
- Fixed receipt-route interaction failures found by `$test-interactions`: nav title/action metadata, timeline scrub metadata, and 44px touch targets for receipt controls.

## Deterministic Proof

### Full Battle spectator gate

Command:

```bash
BATTLE_HOST=http://127.0.0.1:3005 \
BATTLE_LIVE_TRANSPORT_BASE=http://127.0.0.1:18765 \
BATTLE_LIVE_TRANSPORT_PROOF_DIR=/home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-1064-pr8-live-transport-proof \
BATTLE_ADAPTIVE_V13_CAMPAIGN_ROOT=/home/graham/workspace/experiments/agent-skills/skills/battle/local/qualification-matrix-20260723b/seed-0 \
BATTLE_ADAPTIVE_V13_PROOF_DIR=/home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-1064-adaptive-v13-proof \
BATTLE_ADAPTIVE_PANEL_SOURCE_PROOF_DIR=/home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-1064-adaptive-panel-source-proof \
../run.sh prove-spectator
```

Result: `BATTLE_PROVE_SPECTATOR_PASS`.

This exercised backend UX contract validation, spectator typecheck, Vitest, sparse negative gate, Pixi sanity, receipt replay, fresh fixture replay, Hunger Games notification/retired kill gates, no-mockup-leakage, lifecycle, proof-card routes, shared fixture loader, PR6 genetic Pixi, PR8 live transport, V13 adaptive lineage Pixi, and the new adaptive lineage panel source-binding proof.

### Focused source-binding proof

Artifact: `skills/battle/local/issue-1064-adaptive-panel-source-proof/proof.json`

Result:

- `pass: true`
- `mocked: false`
- `live: true`
- V13 panel/race source match: `battle-004-adaptive-lineage-v13`
- V13 public fixture SHA-256: `bb7f8876d2f44c6072097a065b9a1cec11c85af2115e1fee14d1cdf1326c95ba`
- V13 canonical nodes: `blue-g1`, `blue-g2`, `red-g1`, `red-g2`
- V14 panel/race source match: `battle-004-adaptive-memory-v14`
- V14 public fixture SHA-256: `0cc4a9c0e11a41bea751fa2b90876fc6256c718816855807080893c7fece3524`
- V14 fail-closed mode: `proof-unavailable`
- Static fixture leakage checks passed for V13 and V14.
- Browser error check passed.

Screenshots:

- `skills/battle/local/issue-1064-adaptive-panel-source-proof/screenshots/01-v13-source-bound-panel.png`
- `skills/battle/local/issue-1064-adaptive-panel-source-proof/screenshots/02-v14-proof-unavailable-panel.png`

### V13 adaptive lineage Pixi proof

Artifact: `skills/battle/local/issue-1064-adaptive-v13-proof/proof-summary.json`

Result:

- `pass: true`
- `mocked: false`
- `live: true`
- fixture event count: `24`
- fixture lane count: `4`
- lineage edge count: `2`
- retained campaign receipt SHA-256: `2527310d662b33c18695d724b0757ff604097fe70e2841b385e3f9c277bf19d7`
- retained events JSONL SHA-256: `9d7e013ebd2ac68d4fe12ca4183b77ff9664363c877aac747da89840995e2aa3`
- mobile four-lane state, no page overflow, stable Pixi mount, and four-runner pixel occupancy checks passed.

### Required `$test-interactions`

Command:

```bash
/home/graham/workspace/experiments/agent-skills/skills/test-interactions/run.sh run \
  --manifest /home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-1064-test-interactions/manifest.json \
  --output-dir /home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-1064-test-interactions/captures
```

Result: `7 PASS / 0 FAIL / 0 WARN / 7 total`.

Artifact: `skills/battle/local/issue-1064-test-interactions/captures/results.json`

Screenshots inspected:

- `skills/battle/local/issue-1064-test-interactions/captures/receipt-source-binding/0001_source-bound-panel_screenshot.png`
- `skills/battle/local/issue-1064-test-interactions/captures/receipt-source-binding/0007_proof-buttons_click.png`

The screenshots visibly show the source-bound receipt panel, route chrome, lane selection state, and receipt proof text after interaction.

### Code-level checks

Commands:

```bash
cd skills/battle/spectator && npm run -s typecheck
cd skills/battle/spectator && npx vitest run
cd skills/battle/spectator && npm run -s build
```

Results:

- Typecheck exited `0`.
- Vitest: `43 files passed`, `189 tests passed`.
- Vite production build exited `0`.

## Evidence Scope

- mocked: no
- live: yes, for browser/CDP checks, local Vite route, local HTTP/SSE transport adapter, and deterministic local fixture HTTP loads
- exercised: receipt-route fixture loading, source metadata hashing, source-bound adaptive panel rendering, V13/V14 route switching, Pixi V13 playback/geometry, and qid-based interaction checks
- remains unverified: production deployment, live backend execution, Memory service correctness, external provider behavior, and backend scoring changes
