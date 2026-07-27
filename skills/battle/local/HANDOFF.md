# Handoff Report: Battle

**Timestamp**: 2026-07-27T15:09:51-04:00
**Active Agent**: Codex
**Branch**: `battle-adaptive-lineage-goal`
**Workspace**: `/home/graham/workspace/experiments/agent-skills/skills/battle`

## 1. Project Overview

- **Ecosystem**: Python backend skill plus TypeScript/React/PixiJS spectator.
- **Core Purpose**: Battle is a Red vs Blue security competition orchestrator. It schedules Red/Blue personas, runs target/team executable code in Docker, collects objective Judge receipts, scores outcomes, and promotes useful learning into Memory.
- **Current Active Goal Context**: `GOAL_ADAPTIVE_LINEAGE.md` is the controlling local goal. It now includes the 2026-07-23 operator amendment for dual-team co-evolution: isolated Red and Blue adaptive lineages with the Judge as the only shared party.
- **Canonical Spectator Host**: `http://127.0.0.1:3003/#battle`. Current host check on 2026-07-27 returned `host:"agent-skills battle spectator"` and `entry:"skills/battle/spectator/src/main.tsx"`.

## 2. Current State (Doc-Code Alignment)

- **Documented Features**:
  - Battle control plane for Red/Blue rounds, Docker isolation, receipts, scorekeeping, reports, and Memory promotion.
  - Deterministic proof rungs from `battle-001` through BATTLE-004 adaptive lineage, live Tau child DAG, compile/runtime/population fixtures, Pixi spectator, live transport contract, and SSE adapter.
  - Current goal adds Red+Blue co-evolution and strict knowledge isolation.
- **Implemented Reality**:
  - Core backend contains many receipt/fixture/adaptive-lineage modules under `src/battle_skill/`, with broad tests under `tests/`.
  - Spectator lives in `spectator/` and builds a static served app at `:3003`.
  - Latest Battle-specific pushed commit is `39e2def8b Fix Battle Pixi spectator interactions`, which repaired Pixi culling/labels, qid/COTS controls, and selected served sprite atlases. It also committed live proof receipts under `local/`.
  - Current branch `HEAD` is `851167653de9861cfae28979030de9107c9f9c82`, containing later repo commits outside Battle; `git log -- skills/battle` still shows `39e2def8b` as the latest Battle path change.
- **Drift/Misalignments**:
  - The previous top section of this handoff said "spectator UI BROKEN" and cited a `42/43 FAIL` interaction run. That is stale after `39e2def8b`: committed receipts now show generated `$test-interactions` `1/1 PASS` and targeted controls `12/12 PASS`.
  - `GOAL_ADAPTIVE_LINEAGE.md` still says the overall goal is `DISPUTED_PENDING_ACCEPTANCE`. Do not treat the Pixi/control repair as closure of the full immutable goal.
  - `docs/01_TASKS.md` is historical and still lists early setup tasks unchecked. It does not reflect the current mature backend/spectator state.

## 3. What is Working Well

- **Handoff fact script**: `bash skills/handoff/run.sh` from `skills/battle` completed and produced repo/doc/todo structure facts.
- **Spectator static build**: `cd skills/battle/spectator && node scripts/build-static.mjs` passed on 2026-07-27.
- **Live host identity**: `curl http://127.0.0.1:3003/__host.json` returned the agent-skills Battle spectator source.
- **Pixi broad audit**: `cd skills/battle/spectator && node scripts/prove-battle-no-obvious-errors.mjs` passed on 2026-07-27:
  - no console/page errors;
  - no 404s;
  - canvas present throughout;
  - playhead advanced;
  - four current lanes materialized: `red-g1`, `red-g2`, `blue-g1`, `blue-g2`;
  - zero DOM lane rows;
  - no forbidden text;
  - child spawn transition observed.
- **Committed interaction receipts from 2026-07-25**:
  - Generated scan: `skills/battle/local/test-interactions-final-assets-20260725T1731/captures/results.json`, `1 PASS / 0 FAIL / 0 WARN`.
  - Targeted controls: `skills/battle/local/test-interactions-final-assets-targeted-20260725T1731/captures/results.json`, `12 PASS / 0 FAIL / 0 WARN`.
- **Committed Pixi receipt from 2026-07-25**:
  - `skills/battle/local/pixi-late-playhead-proof-20260725T1731/receipt.json`, `pass:true`, `mocked:"no"`, `live:"yes"`.
  - Frozen samples at 3s, 55s, 95s, and 132s loaded via Chromium and captured full-page/canvas screenshots with no errors or 404s.
- **Sprite cleanup receipt from 2026-07-25**:
  - `skills/battle/local/sprite-atlas-cleanup-proof-20260725T1731/receipt.json`.
  - Regenerated and validated served Pixi atlases for `crimson_chainsaw_demon`, `crimson_hornbreaker`, and `plague_nurgling`.
  - `crimson_chainsword_berserker` was intentionally not shipped because candidate conversion fell back to uniform slicing.

## 4. What is Currently Broken

- **Battle root sanity fails immediately**:
  - Command: `cd skills/battle && ./sanity.sh`
  - Result: FAIL at step 2.
  - Signature: `Generated directory must not live in skill root: /home/graham/workspace/experiments/agent-skills/skills/battle/.venv`
  - Interpretation: this is repository hygiene, not a backend logic failure. The script refuses a real generated `.venv` in the skill root unless it is absent or symlinked.
- **Spectator TypeScript check fails**:
  - Command: `cd skills/battle/spectator && node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json`
  - Result: FAIL.
  - Signature: `src/BattleDashboard.tsx(67,6): error TS2322 ... Property 'raceData' does not exist on type 'IntrinsicAttributes & Props'.`
  - Interpretation: `build-static.mjs` passes, but the stricter typecheck is blocked by `BattleDashboard.tsx` props drift.
- **Full immutable goal remains open/disputed**:
  - `GOAL_ADAPTIVE_LINEAGE.md` still records `DISPUTED_PENDING_ACCEPTANCE`.
  - The 2026-07-23 co-evolution amendment is larger than the recent Pixi repair: it requires isolated Red and Blue adaptive lineages, real scorecard semantics, and Judge-mediated evaluation without cross-team knowledge leakage.
- **Worktree is very dirty**:
  - Many Battle local artifacts, backend fixtures, spectator files, and tests are modified or untracked.
  - There are also repo-wide unrelated staged/unmerged changes outside Battle.
  - Do not use `git add -A`, broad restore/reset/stash, or broad checkout. Stage explicit task paths only.
- **Generated/failed local candidates remain untracked**:
  - `skills/battle/local/sprite-atlas-cleanup-proof-20260725T1731/candidate*/` contains failed or comparison atlas candidates. They are evidence only and were not shipped.

## 5. Next Steps

1. **Fix root sanity hygiene first**:
   - Remove, relocate, or symlink `skills/battle/.venv` in a way that preserves user work and complies with repository rules.
   - Rerun `cd skills/battle && ./sanity.sh`.
2. **Fix the strict spectator typecheck**:
   - Inspect `spectator/src/BattleDashboard.tsx` and the component it calls at line 67.
   - Resolve the `raceData`/`Props` mismatch narrowly.
   - Rerun `node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json`.
3. **If UI changes are made, rerun live interaction proof**:
   - Use `skills/test-interactions/run.sh generate/run` against `http://127.0.0.1:3003/#battle`.
   - Also rerun `node scripts/prove-battle-no-obvious-errors.mjs`.
   - Inspect screenshots; DOM assertions alone are not visual proof.
4. **Continue the actual adaptive co-evolution goal only after hygiene gates are green**:
   - Backend must prove isolated Red and Blue lineages.
   - UX must render two isolated trees and Judge mediation from receipts.
   - Do not invent UI-only live status or score values.
5. **Sprite follow-up**:
   - Do not promote `crimson_chainsword_berserker` from the current contact sheet until row detection/conversion produces a visually acceptable atlas without uniform fallback.

## 6. Project Context for Success

- **Key backend files**:
  - `src/battle_skill/cli.py`
  - `src/battle_skill/adaptive_red_blue_lineage_canary.py`
  - `src/battle_skill/adaptive_selection.py`
  - `src/battle_skill/arena_live_battle_proof.py`
  - `src/battle_skill/battle_event_adapter.py`
  - `src/battle_skill/normalized_adaptive_lineage_fixture.py`
  - `src/battle_skill/team_artifact_pipeline.py`
  - `utils/clean_sprite_atlas.py`
- **Key spectator files**:
  - `spectator/src/BattleSpectatorArena.tsx`
  - `spectator/src/RaceViewport.tsx`
  - `spectator/src/SpectatorRail.tsx`
  - `spectator/src/AgentDetailPane.tsx`
  - `spectator/src/engine/BattleRacePixiSpike.tsx`
  - `spectator/src/engine/battle-pixi-scene.ts`
  - `spectator/src/engine/battle-pixi-event-labels.ts`
  - `spectator/src/engine/battle-pixi-game-mechanics.ts`
  - `spectator/scripts/prove-battle-no-obvious-errors.mjs`
- **Important local receipts**:
  - `local/test-interactions-final-assets-20260725T1731/captures/results.json`
  - `local/test-interactions-final-assets-targeted-20260725T1731/captures/results.json`
  - `local/pixi-late-playhead-proof-20260725T1731/receipt.json`
  - `local/sprite-atlas-cleanup-proof-20260725T1731/receipt.json`
- **Recent Battle commits**:
  - `39e2def8b Fix Battle Pixi spectator interactions`
  - `78183ee5a battle: update current handoff`
  - `5f8b5bced battle: surface replay evidence in rail`
  - `7b0a1341b battle: prove full replay UX`
  - `2a5ffced3 battle: make receipt replay actually play`
- **Live server note**:
  - On 2026-07-27, port `3003` was served by `node` pid `812552` from `skills/battle/spectator`.
  - Always verify the serving repo with `curl /__host.json` and `/proc/<pid>/cwd` or equivalent before editing user-facing UI.

## 7. Evidence Notes

```text
mocked: no
live: yes
actually exercised:
  - handoff fact script
  - Battle root sanity up to its generated-directory hygiene gate
  - spectator static build
  - spectator TypeScript typecheck
  - live Pixi/browser broad audit at :3003
  - existing committed interaction/Pixi/sprite receipts
remains unverified:
  - full Battle sanity after .venv hygiene repair
  - strict spectator typecheck after BattleDashboard props repair
  - fresh 2026-07-27 rerun of test-interactions
  - full dual-team co-evolution immutable goal
```

Immutable Goal: NOT_MET
