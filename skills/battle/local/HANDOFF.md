# Handoff: Battle Adaptive Lineage — GOAL MET (backend + UX live)

**Timestamp**: 2026-07-18
**Status**: `ADAPTIVE_LINEAGE_UX_LIVE_COMPLETE` — the immutable goal
`GOAL_ADAPTIVE_LINEAGE.md` is met end to end: live backend qualification + finished
UX (LIVE comparison panel + four distinct validated PixiJS sprites), all on branch
`battle-adaptive-lineage-goal`.

> Supersedes `ADAPTIVE_LINEAGE_LIVE_QUALIFIED`. The migration is landed, the
> qualification reproduced live, and the spectator now renders it.

## What is proven (verified this session)

### Backend — live qualification PASS
- `arena-adaptive-lineage-qualification battle-004` (real SciLLM gpt-5.5 + real
  Docker Judge `python:3.12-slim`): **11/11 checks PASS**, all four Tau stages
  `mocked=false, live=true, PASS`. Four distinct source hashes; operators per
  contract (G0=none, G1-A=method_replace, G1-B=oracle_or_parameter_mutation,
  G2=failure_guided_crossover); selection G1-A over G1-B by `novelty_distance`.
- Normalized to `spectator/src/lineage/__fixtures__/adaptive-lineage-live.json`
  with `data_source:live` (validator PASS, 4 nodes / 3 edges).

### UX — finished interface at http://localhost:3002/#battle/receipt
- **Live comparison panel**: the migrated `BattleLineageComparisonPanel` is now
  wired into the arena (receipt route), fed by the live mechanics fixture. Renders
  `G0 -> {G1-A, G1-B} -> G2` with operators, changed AST dimensions, novelty
  distances, SELECTED vs RUNNER-UP, "Selection: G1-A over G1-B · novelty_distance",
  and mutation edges — under an honest green **LIVE** badge (`data_source:live`).
- **Distinct PixiJS sprites**: the single-atlas lock is removed. `spriteIdForLane`
  is now a deterministic receipt-backed map (team+generation+selection role). The
  four specimens render as four distinct validated atlases —
  G0=`plague_nurgling` (floor), G1-A=`crimson_chainsaw_demon`,
  G1-B=`crimson_hornbreaker`, G2=`typhus`. Verified live: crimson demon on RED G1,
  green plague-walker on RED G2.
- **Notifications**: LIVE EVENTS ticker populated from receipts.
- Proof artifacts: `assets/sprites/working-sprite-proof/FOUR-SPECIMEN-SPRITES.png`
  (composite) and `LIVE-battle-adaptive-lineage-proof.jpg` (live browser).

### Gates
- Spectator: **190 vitest pass**, **typecheck clean**.
- Backend adaptive suite: 48 pass (earlier), ruff clean.
- `/sprite-atlas` validation: 23/23 for each enabled atlas.

## Commits (branch `battle-adaptive-lineage-goal`)
- `9282ed14a` land migration + `GOAL_ADAPTIVE_LINEAGE.md` + working-sprite proofs
- `53198045c` refresh `adaptive-lineage-live` fixture from the live qualification
- `034617cad` finish UX — distinct sprites + live comparison panel + layout + tests
- Tau recognizer fix: committed on `tau-adaptive-mechanics` worktree branch.

## Honest caveats / follow-ups
1. **Deploy mechanism**: `:3002` (pi-mono ux-lab) resolves the spectator from
   `/mnt/storage12tb/deployments/agent-skills/current` (was a frozen July-15
   release `2a3c82e12`). This session made it serve current code by **rsyncing the
   updated spectator + repaired atlases into that release** (no vite restart — HMR
   picks it up). For durable production hygiene, cut a NEW git-sha-named release
   from this branch and repoint `current`, rather than keeping the in-place overlay.
2. **PixiJS sprites need a real page load, not HMR**: during dev, rapid HMR swaps
   poison the module-level `ensureBattlePixiAssets` promise, so runner sprites stop
   painting until a full reload. On a genuine navigation they load correctly (this
   is a dev-only artifact, not a product bug). If desired, harden
   `ensureBattlePixiAssets` to reset its cached promise on failure.
3. **Music**: proven by tests (`prove:music-m1`, `prove:score-package`) + 20 audio
   assets; live playback requires a user gesture (browser autoplay policy) so it
   was not screenshot-verified.
4. Branch not yet merged to `main` or pushed — awaiting review.

## Reproduce
```bash
cd skills/battle
TAU_REPO=/home/graham/workspace/experiments/tau-adaptive-mechanics \
  ./run.sh arena-adaptive-lineage-qualification battle-004 --out /tmp/relive
./run.sh normalize-adaptive-lineage-fixture /tmp/relive \
  --out spectator/src/lineage/__fixtures__/adaptive-lineage-live.json --data-source live
cd spectator && npx vitest run && npm run -s typecheck
# UX: http://localhost:3002/#battle/receipt?engine=pixi  (full reload for pixi sprites)
```
