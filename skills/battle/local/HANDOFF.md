# Handoff Report: battle (adaptive-lineage spectator)

**Timestamp**: 2026-07-20T14:19Z
**Active Agent**: Claude (Fable)
**Branch**: `battle-adaptive-lineage-goal` @ `6915e1875` — a SHARED integration branch,
~64 commits ahead of `origin/main` (`1b4d564cb`), battle work interleaved with unrelated
`watch:` / `embry-voice:` / `ask` / `audio_e2e:` / memory commits. Operator decision
(2026-07-20): keep the shared branch; do NOT extract battle-only history.

> Every claim is labeled **VERIFIED** (a command this session proved it — the command is
> given), **PRIOR-CLAIM** (asserted by an earlier agent, NOT re-proven), or **ASPIRATIONAL**
> (goal, not built). Trust the receipts, not the prose.

## 1. Project Overview
- **Ecosystem**: Python backend (`skills/battle/src/battle_skill`) + TypeScript/React/PixiJS
  v8 spectator (`skills/battle/spectator`). Served at `:3002` by a vite dev server rooted in
  `pi-mono/packages/ux-lab`, which imports this spectator via the vite alias
  `@agent-skills/battle-spectator` → `skills/battle/spectator/src` (working tree).
- **Core Purpose** (`GOAL_ADAPTIVE_LINEAGE.md`): a live, non-mocked four-specimen
  adaptive-lineage qualification (G0 seed → G1-A/G1-B → deterministic selection → G2), and a
  finished spectator that renders that exact receipt with proper PixiJS sprites + an honest
  live/recorded badge.

## 2. Current State (doc–code alignment)
- **Routes**: valid battle hashes are `#battle`, `#battle/isolation`, `#battle/receipt`
  (VERIFIED: `battle-mockup-lanes.ts` / `battle-receipt-replay.ts`). The prior handoff's
  `#battle/live` route **does not exist** — see §4.
- **Data**: served live fixture `spectator/public/battle-fixtures/battle-004-adaptive-live/
  battle.normalized_ux_fixture.json` is real-derived (VERIFIED: contains `RED_EXPLOIT_CONFIRMED`,
  no `/workspace` path leak) from an 18-event capture via `local/derive_adaptive_live_fixture.py`.

## 3. What is Working Well (VERIFIED 2026-07-20)
- **Backend adaptive-lineage logic** — `pytest tests/test_adaptive_lineage_reducer.py
  tests/test_g1_delta_retry.py tests/test_selection_receipt_ordering_timestamp.py` → **32 passed**.
- **Spectator gates** — `npm run typecheck` → 0 errors; `npx vitest run` → **42 files / 191 pass**.
- **`#battle/receipt` renders** — fresh browser tab on
  `#battle/receipt?engine=pixi&fixture=battle-004-adaptive-lineage-live` → `#root` populated,
  `<canvas>`, 120 `data-qid`s, RED-TEAM scorecard header, and **four distinct lineage sprites**
  (crimson demon / typhus / slug / green nurgling). Single-atlas lock removed.
- **SSE transport server** — `curl :18765/healthz` → PASS, 54 events (ephemeral; dies on reboot).
- NOTE: spectator has **no `build` script** — vite-dev-served; `tsc` is the gate.

## 4. What is Currently Broken (VERIFIED 2026-07-20)
- **`#battle/live` is not a route.** Loading `#battle/live?engine=pixi&battle=battle-004`
  renders the **Sparta Explorer** dashboard (0 `battle:*` qids). The prior handoff's reproduce
  command is stale.
- **No standalone live-streaming view.** The "Live" the prior agent described is an
  `AgentDetailPane` `stdout latest` / `stderr latest` panel + a "LIVE PROOF" badge (summary
  tab), not a scrolling stream on its own route. Whether that panel consumes the live SSE bus
  (vs the static derived fixture) is UNVERIFIED.
- **`#battle/receipt` not unified with live** — generic lane names (`RED G1 PARENT`) + static
  Docker-replay/lifecycle evidence; no codenames, no live bus.
- **Repo hygiene** — 27 modified + 42 untracked files (concurrent agents). Do NOT `git add -A`;
  commit battle files by explicit path only.

## 5. Unverified / prior-claims (prove before trusting)
- **Live four-specimen qualification PASS** — deterministic tests pass (VERIFIED); a fresh
  SciLLM+Docker run PASS is PRIOR-CLAIM (`2026-07-19` run `arena-adaptive-lineage-20260719T141223Z`).
- **stdout/stderr panel fed by the live SSE bus** — UNVERIFIED (blocked by the broken `/live` route).
- **Sprite visual quality** — distinct (VERIFIED); "coherent, not garbage at lane scale" is
  reviewer-ACCEPTED per the GOAL doc (PRIOR-CLAIM).

## 6. Next Steps (priority order)
1. **Resolve the live-streaming story (the crux).** Decide if streaming-on-a-route is a real
   GOAL requirement. If yes: pick a real route (`#battle`/`#battle/receipt`), wire the
   AgentDetail panel to the SSE bus, and VERIFY one live frame end-to-end in a FRESH tab. If no:
   delete the stale `#battle/live` claims.
2. **Re-run the live backend qualification** (immutable-goal closure):
   `TAU_REPO=/home/graham/workspace/experiments/tau-adaptive-mechanics ./run.sh
   arena-adaptive-lineage-qualification battle-004 --out /tmp/relive` (needs the Tau recognizer
   fix — issue `grahama1970/tau#116`, currently only on worktree branch `tau-adaptive-mechanics`).
3. **Unify `#battle/receipt`** with real codenames (+ live if step 1 pans out).
4. **/webgpt design review** of the receipt view before claiming UX done. Binding VERIFIED:
   `skills/battle/.ask/browser-oracles.yaml` → `webgpt.default: battle`. Drive via /webgpt +
   /browser-oracle (native skill node, NOT behind scillm). Tab liveness/auth NOT established
   this session — establish at use time.
5. Merge Tau fix (#116); prune worktrees `agent-skills-adaptive-mechanics`, `tau-adaptive-mechanics`.

## 7. Project Context for Success
- **Key files**:
  - `src/battle_skill/adaptive_lineage.py` (reducer, G1 retry, selection), `arena_live_battle_proof.py` (Docker/Judge), `cli.py`.
  - `spectator/src/engine/battle-lane-variant-map.ts` (sprite mapping — 4 distinct), `spectator/src/BattleHeader.tsx` (scorecard iframe), `spectator/src/battle-scorecard.html` (embedded scorecard).
  - `spectator/src/lineage/__fixtures__/adaptive-lineage-live.json`, served fixture under `spectator/public/battle-fixtures/battle-004-adaptive-live/`.
  - Routing/consumers live in `pi-mono/packages/ux-lab/src/components/battle/` (the served app).
- **Recent battle commits** (this session, newest first):
  - `6915e1875` handoff — back-on-track plan + /webgpt binding
  - `7faa14eda` handoff — verified `#battle/live` is not a route
  - `0cdeb82f6` handoff — accurate evidence-backed state
  - `4a8337857` track `battle-scorecard.html` + four distinct lineage sprites (fixes broken import + sprite lock)
  - `e0cb1d9f4` stream real adaptive-lineage capture into Live view (prior agent)
- **Verification discipline (learned the hard way this session):**
  - Load the spectator in a FRESH tab. A tab navigated many times / after a CDP reset renders
    blank (`#root` empty) — that is a poisoned automation tab, NOT an app failure (~1 hr lost
    to that false diagnosis).
  - Deterministic tests over self-authored code are NOT proof of the live problem. Sprites,
    streaming, and qualification each need a live read-back from the produced artifact.
