# Handoff: Battle Adaptive Lineage — GOAL MET (backend + UX live)

## Ticket Closure Addendum (2026-07-28 17:15 UTC)

Active worktree:

`/home/graham/workspace/experiments/agent-skills-issue1049-20260728`

Remote proof tip:

`origin/main ba0e4fc75733e7bd0ce49fa52e11b69d8378a663`

### Battle-directory ticket state

Open `battle` label query:

```bash
gh issue list --repo grahama1970/agent-skills --state open --label battle --limit 100
```

Result: `[]`

Open Battle title query:

```bash
gh search issues --repo grahama1970/agent-skills --state open 'battle in:title'
```

Result: only #1040, `Triage 195 unrelated commits stranded on battle-adaptive-lineage-goal`.
#1040 is not a `skills/battle` implementation or proof ticket. It targets
`/home/graham/workspace/experiments/agent-skills` primary-worktree cleanup and
lists `skills/persona-dream/local/HANDOFF.md` as the scoped file. It remains a
separate repository-maintenance ticket, not a Battle-directory blocker.

### Closed Battle tickets and receipts

- #1049: proof addendum preserved without rewriting the original immutable goal.
- #1048: canonical dual-team co-evolution fixture and Judge-backed scoreboard.
- #1063: invalid kill-shot replay retired; backend eval health preserved.
- #1064: spectator adaptive mechanics panel derives from loaded receipt fixture.
- #1065: live Memory-backed lineage proof.
  - Commit: `e1b05a7cc351cc00e32713e111696b3b8500b7be`
  - Proof: `skills/battle/docs/proofs/tickets/issue-1065-live-memory-lineage-20260728.md`
  - Receipt: `skills/battle/local/issue-1065-live-memory-proof/proof-summary.json`
  - Evidence: `status=PASS`, `mocked=false`, `live=true`; Red/Blue store+upsert acks real; next-generation recall found the owning survivor; negative controls empty.
- #1066: one Red worker and one proactive Blue worker overlap in a deterministic Docker fixture.
  - Commit: `64f5b18e7d7601da8944d5feb7d91afaee1bcf84`
  - Proof: `skills/battle/docs/proofs/tickets/issue-1066-overlap-round-20260728.md`
  - Receipt: `skills/battle/local/issue-1066-overlap-round-proof/proof-summary.json`
  - Evidence: `status=PASS`, `mocked=false`, `live=true`; `blue_started_at < red_terminal_at`; `red_started_at < blue_terminal_at`; Blue first input has no Red finding/exploit artifact.
- #46: parent async scheduler epic.
  - Commit: `ba0e4fc75733e7bd0ce49fa52e11b69d8378a663`
  - Proof: `skills/battle/docs/proofs/tickets/issue-46-async-battle-scheduler-20260728.md`
  - Receipt: `skills/battle/local/issue-46-arena-prekill-survival-proof/run-receipt.json`
  - Evidence: `status=PASS`, `mocked=false`, `live=brave_search_docker_arena_oracle_tau_harness`; `red_materialized=2`; `blue_materialized=2`; `judged_pairs=4`; `prekill_survival_contract.status=PASS`; Docker Judge and scorekeeper receipts present.

### Commands that last exercised the Battle closure set

```bash
cd skills/battle && UV_PROJECT_ENVIRONMENT=/tmp/issue1066-uv-venv \
  uv run --project . python -m pytest tests/test_overlap_round.py -q
```

Result: `1 passed in 0.30s`

```bash
./skills/battle/run.sh prove-overlap-round \
  --out /home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-1066-overlap-round-proof \
  --timeout-s 30
```

Result: `status=PASS`, `mocked=false`, `live=true`

```bash
./skills/battle/run.sh arena-prekill-survival-proof battle-004 \
  --out /home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-46-arena-prekill-survival-proof \
  --red-workers 2 --blue-workers 2 --timeout-s 120
```

Result: `status=PASS`, `mocked=false`, `live=brave_search_docker_arena_oracle_tau_harness`

```bash
cd skills/battle && UV_PROJECT_ENVIRONMENT=/tmp/issue46-uv-venv \
  uv run --project . python -m pytest tests/test_arena_live_battle_proof_contract.py -q
```

Result: `17 passed in 0.56s`

```bash
UV_PROJECT_ENVIRONMENT=/tmp/issue46-sanity-uv-venv \
  skills/battle/sanity.sh > /tmp/issue-46-battle-sanity.out 2>&1
```

Result: exit `0`; backend eval `13/13`; `Result: PASS`.

### Current cautions for the next agent

- Do not use the contaminated primary worktree at `/home/graham/workspace/experiments/agent-skills` as a source of truth for Battle closure; it is the subject of #1040 and contains extensive unrelated dirty state.
- Continue Battle work from a clean lane-named worktree and committed proof receipts.
- UI work still requires `$pixijs`, `$best-practices-battle-pixi`, relevant React best practices, and `$test-interactions`; the #1065/#1066/#46 closure work above was backend/proof only.

## Current State Addendum (2026-07-28)

Source commit inspected: `277afadfdea5`.

This handoff preserves the historical 2026-07-18 acceptance record for the
original four-specimen adaptive-lineage goal. It must not be read as closure for
the later dual-team co-evolution amendment. Current active state is summarized
in `GOAL_ADAPTIVE_LINEAGE.md#current-state-addendum-2026-07-28`:

- original `G0 -> {G1-A,G1-B} -> G2` four-specimen goal: `MET` on 2026-07-18;
- later dual-team co-evolution amendment: `NOT_MET`;
- deterministic health dependencies: #1035 and #1047 closed;
- receipt-truth blockers: #1048 and #1063;
- frontend consumption blocker: #1064;
- live lineage blocker: #1065;
- bounded proactive Red/Blue overlap blocker: #1066, with #46 as the broader
  scheduler epic.

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

## Resolved this session (were caveats, now closed)
1. **Deploy — done properly.** A clean git-sha release is cut per commit
   (`git archive main | tar -x` into `releases/<sha>`), `current` repointed, and
   vite restarted (kill the :3002 tree → the dev supervisor respawns it reading the
   new `current`). Current live release: `995ea0ad8`. The frozen `2a3c82e12` release
   was restored to pristine (the earlier in-place overlay was fully reverted).
2. **PixiJS HMR init — fixed.** `ensureBattlePixiAssets` now catches pixi's
   "Assets already initialized" (its global singleton survives HMR while this
   module's state resets) and treats it as success, so runner sprites paint
   reliably without a hard reload.
3. **Sprite acceptance — reviewer loop actually run.** An independent
   sprite-reviewer gave per-atlas visual verdicts (not my eyeball): REJECTED
   `crimson_hornbreaker` (garbled) and flagged `skull_horn` (REVISE), and caught
   that the two crimson G1 specimens weren't distinguishable. Fixed: dropped both
   from the enabled set, re-mapped G1-B → `slug_demon`; the four live specimens are
   now distinct silhouettes (verified live). Rejections locked in by unit test.

## Remaining honest note
- **Music**: system is wired (AudioContext score runtime, functional sound-arm
  control, cue bindings) and covered by passing tests (`music-m1`, `score-package`,
  `hg-death-notification`, `hg-kill-cue-replay`). Live *audible* playback could not
  be captured via browser automation even on the `hgDeathDemo=1` cue route with
  sound armed — Web Audio does not fully unlock without a trusted human gesture.
  This is a headless-verification limit, not evidence of a defect. Not a
  `GOAL_ADAPTIVE_LINEAGE` requirement.
- Branch `battle-adaptive-lineage-goal` is redundant (its battle commits are on
  `origin/main`) and can be deleted.

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
