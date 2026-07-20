# Handoff Report: battle (adaptive-lineage spectator)

**Timestamp**: 2026-07-20
**Branch**: `battle-adaptive-lineage-goal` — a SHARED integration branch, ~64 commits
ahead of `origin/main` (1b4d564cb). Battle work is interleaved with unrelated
`watch:`, `embry-voice:`, `ask tau-dag`, `audio_e2e:`, memory, and PixiJS-skill
commits from other agents. Decision (operator, 2026-07-20): **keep the shared
branch** — do NOT attempt battle-only history extraction (would be ~12 interleaved
commits cherry-picked onto main with near-certain conflicts). Battle ships when this
branch merges.

Every claim below is labeled VERIFIED (a command in the 2026-07-20 session proved it)
or PRIOR-CLAIM (asserted by an earlier agent, NOT re-verified this session).

## 1. Overview
- Python (`src/battle_skill`) backend + TypeScript/React/PixiJS v8 spectator (`spectator/`).
- Adaptive lineage: G0 seed → G1-A/G1-B candidates → deterministic selection → G2
  descendant, surfaced in the arena/DAW spectator with a live SSE transport.

## 2. VERIFIED working (2026-07-20)
- **App renders.** Fresh browser tab on `#battle/receipt?engine=pixi&fixture=battle-004-adaptive-lineage-live`
  loads full: `#root` populated, `<canvas>` present, 120 `[data-qid]` nodes. (A blank
  page earlier was a POISONED automation tab — navigated 10×, session reset — NOT the app.)
- **Four distinct lineage sprites render.** The four lanes show four different sprites
  (crimson demon / typhus / slug / green nurgling), not the old single-atlas lock and not
  garbage. Screenshot: `/tmp/claude-chrome-screenshots-HOEApt/screenshot-1784548415439-5.png`.
- **Backend adaptive tests**: `pytest tests/test_g1_delta_retry.py test_selection_receipt_ordering_timestamp.py test_adaptive_lineage_reducer.py` → 32 passed.
- **Spectator**: `tsc` typecheck 0 errors; `vitest run` → 42 files / 191 tests pass
  (incl. `battle-lane-variant-map.test.ts` 11/11).
- **SSE server** up: `curl :18765/healthz` → PASS, 54 events (ephemeral — dies on reboot).
- NOTE: the spectator has **no `build` script** — it is vite-dev-served (`:3002`, root
  `pi-mono/packages/ux-lab`, which imports this spectator via the `@agent-skills/battle-spectator`
  vite alias → the working tree). "Production build" gates do not apply; typecheck is the gate.

## 3. Fixed this session (committed `4a8337857`)
- **Broken import resolved.** `spectator/src/battle-scorecard.html` was untracked but
  imported (`?raw`) by the already-committed `BattleHeader.tsx` — a clean checkout of
  `e0cb1d9f4` would not build. Now tracked.
- **Distinct sprites.** Removed the single-atlas lock in `spectator/src/engine/battle-lane-variant-map.ts`:
  enabled the four reviewer-ACCEPTED atlases (`plague_nurgling, crimson_chainsaw_demon,
  slug_demon, typhus`) and made `spriteIdForLane` map team+generation+role → distinct
  sprite via `LANE_SPRITE_TABLE` (per `GOAL_ADAPTIVE_LINEAGE.md`).

## 4. Battle commits ahead of origin/main (the deliverable, newest → oldest)
```
4a8337857  track scorecard html + four distinct lineage sprites   (this session)
e0cb1d9f4  stream real adaptive-lineage capture into Live view
cfb9f7cf7  adaptive-lineage panel receipt-authoritative (WebGPT BLOCK fix)
2f3ab21e8  fix campaign event journal source_created_at
4919c1641  proof_card PR3B test deterministic
ebf05ef11  fix pytest collection + stale child_tau_dag assertions
1a29893d0  mark adaptive-lineage immutable goal MET
36aa85060  update handoff — deploy/pixi/sprite caveats resolved
71df4d498  sprite creator↔reviewer loop; fix mapping + pixi HMR init
66f6c2872  record adaptive-lineage UX-live completion handoff
034617cad  finish adaptive-lineage UX — distinct sprites + live comparison panel
9282ed14a  land adaptive-lineage migration + adaptive immutable goal
```

## 5. Open / not done
- **`#battle/receipt` vs `#battle/live` not unified.** Streaming console + real codenames
  are on `#battle/live` only; `#battle/receipt` shows static Docker-replay/lifecycle
  evidence + generic lane names. (PRIOR-CLAIM: `#battle/live` streaming works — NOT
  re-verified this session.)
- **Ephemeral SSE server** — background process, dies on reboot; restart via §6.
- **Tau recognizer fix** (importlib/spec_from_file_location robustness for method_replace
  mutations) lives only on worktree branch `tau-adaptive-mechanics` + GitHub issue
  `grahama1970/tau#116`; NOT merged into the tau repo.
- **Leftover worktrees** from earlier sessions: `/home/graham/workspace/experiments/agent-skills-adaptive-mechanics`,
  `/home/graham/workspace/experiments/tau-adaptive-mechanics`. Prune when done.

## 6. Run / reproduce
```bash
cd skills/battle
python3 local/derive_adaptive_live_fixture.py   # regenerate served live fixture
uv run --project "$PWD" python -m battle_skill.cli serve-live-transport \
  --fixture spectator/public/battle-fixtures/battle-004-adaptive-live/battle.normalized_ux_fixture.json \
  --battle-id battle-004 --host 127.0.0.1 --port 18765
# open in a FRESH tab (avoid a poisoned automation tab):
#   http://localhost:3002/#battle/receipt?engine=pixi&fixture=battle-004-adaptive-lineage-live
#   http://localhost:3002/#battle/live?engine=pixi&battle=battle-004
```

## 7. Housekeeping
- Working tree carries heavy unrelated churn from concurrent agents (24 modified, 44
  untracked at handoff time). Do NOT `git add -A` — commit battle files by explicit path only.
- `skills/battle/skills/` is a mis-rooted run-artifact tree (untracked). Many
  `local/*-verify*` and `local/battle-004-*` dirs are run scratch.

## 8. Suggested next step
Unify `#battle/receipt` with the live streaming console + real codenames so the
mockup-matched race view and the live data are one screen (was the prior agent's top
next-step; still open). Re-verify `#battle/live` streaming FIRST — it is only a
PRIOR-CLAIM.
