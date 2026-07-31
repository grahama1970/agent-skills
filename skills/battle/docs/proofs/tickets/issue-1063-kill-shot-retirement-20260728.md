# Issue 1063 Proof: Kill-Shot Fixture Retired Fail-Closed

Issue: https://github.com/grahama1970/agent-skills/issues/1063
Date: 2026-07-28

## Files Updated

- Removed `skills/battle/local/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json`
- Removed `skills/battle/spectator/public/battle-fixtures/battle-004-kill-shot-pixi-replay/battle.normalized_ux_fixture.json`
- Added `skills/battle/spectator/public/battle-fixtures/battle-004-kill-shot-pixi-replay/unsupported.json`
- Updated the receipt route registry to point `battle-004-kill-shot` at the unsupported marker
- Updated kill-shot proof scripts to prove retirement/fail-closed behavior
- Removed the `backend-eval` allowlist entry for the invalid fixture

## Disposition

The requested live regeneration path is not supported by current Battle code:
no producer emits a Judge-backed `blue.kill_confirmed`, `red.killed`, or
`tau.killed` receipt. The unsupported fixture was therefore retired fail-closed
instead of preserving an ungrounded killed terminal state.

## Deterministic Proof

```text
cd skills/battle/spectator
npm run -s prove:kill-shot-pixi
npm run -s prove:hg-kill-cue-replay
npm run -s prove:receipt-director-killed
```

Result:

```text
BATTLE_PROVE_KILL_SHOT_RETIRED_PASS
BATTLE_PROVE_HG_KILL_CUE_REPLAY_RETIRED_PASS
BATTLE_PROVE_RECEIPT_DIRECTOR_KILLED_RETIRED_PASS
```

```text
cd skills/battle/spectator
npx vitest run src/lib/battle-receipt-lineage.test.ts src/engine/battle-pixi-lineage.test.ts src/engine/battle-pixi-kill-shot.test.ts src/lib/battle-highlight-reel.test.ts src/lib/battle-receipt-beats.test.ts src/lib/battle-replay-cues.test.ts
```

Result: 6 files passed, 22 tests passed.

```text
cd skills/battle/spectator
npm run -s typecheck
```

Result: exit 0.

```text
cd skills/battle
./run.sh backend-eval --out-dir local/backend-eval-issue1063-retired-20260728-r2 --allow-live
```

Result: status `passed`, 13 passed / 0 failed / 13 total.

mocked: no
live: no
actually exercised: route fail-closed marker, removed normalized fixture path,
focused frontend unit tests, TypeScript typecheck, and deterministic backend eval
remains unverified: live kill semantics; this patch intentionally does not add
new kill semantics or synthetic kill receipts
