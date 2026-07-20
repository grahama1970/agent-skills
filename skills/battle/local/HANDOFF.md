# Handoff Report: battle adaptive-lineage receipt

**Timestamp**: 2026-07-20T17:48:56Z
**Active Agent**: Codex
**Branch**: `battle-adaptive-lineage-goal`
**Current objective**: finish `GOAL_ADAPTIVE_LINEAGE.md` recovery from the
agent-skills worktree, not the pi-mono shell.

> Evidence rule for the next agent: trust receipts and command artifacts, not
> stale prose. Current recovery evidence is the 2026-07-20 live backend receipt,
> the agent-skills `:3003` browser proof, and the WebGPT accepted review in
> `skills/battle/local/webgpt-design-review-20260720T1742Z/`.

## 1. Project Overview

- **Ecosystem**: Python Battle backend under `skills/battle/src/battle_skill`
  plus TypeScript/React/Pixi spectator under `skills/battle/spectator`.
- **Core purpose**: prove one canonical BATTLE-004 adaptive lineage:
  `G0 -> {G1-A, G1-B} -> G2`, with a live SciLLM + Docker qualification receipt
  and a spectator that renders that exact receipt with honest live/recorded
  state.
- **Current hosting decision**: agent-skills owns the receipt host. Use
  `http://127.0.0.1:3003/#battle/receipt?engine=pixi`. Do not resume from
  `pi-mono/packages/ux-lab` or add a standalone `#battle/live` route.

## 2. Current State

- **Backend receipt is fresh and live**:
  `skills/battle/local/adaptive-lineage-relive-20260720T144034Z/adaptive-lineage-qualification.json`.
  It reports `status: PASS`, `run_id: arena-adaptive-lineage-20260720T144034Z`,
  `battle_id: battle-004`, 4 primary SciLLM calls, 4 HTTP completions,
  4 red specimens, no budget overrun, and exactly one G2 Judge completion.
- **Fixture is normalized with descriptive exploit names**:
  `skills/battle/spectator/src/lineage/__fixtures__/adaptive-lineage-live.json`
  has `data_source: live`, selected `G1-A`, runner-up `G1-B`, criterion
  `novelty_distance`, and names:
  `G0 Seed Slip`, `G1-A Module Slip`, `G1-B Arc Courier`, `G2 ZipInfo Path`.
- **Agent-skills host exists and is committed**:
  `skills/battle/spectator/index.html`, `src/main.tsx`, `src/standalone.css`,
  and `scripts/{build-static,serve-static}.mjs`.
  `curl http://127.0.0.1:3003/__host.json` returns host
  `agent-skills battle spectator` and entry `skills/battle/spectator/src/main.tsx`.
- **Live-browser proof exists**:
  `skills/battle/local/agent-skills-host-verify-20260720T1646Z/surf-assertions.json`
  targets `http://127.0.0.1:3003/#battle/receipt?engine=pixi`, `mocked:false`,
  `live:true`, screenshot bytes `254726`, and asserts visible text for
  `ADAPTIVE LINEAGE`, `LIVE: Qual PASS`, all four exploit names, and
  `G1-A Module Slip · selected G1`.
- **Fresh post-review browser screenshot exists**:
  `skills/battle/local/agent-skills-host-verify-20260720T1748Z/` contains
  `current-render.json`, `current-assertions.json`, and
  `surf-receipt-agent-skills-3003-current.png` for the same `:3003` receipt
  route. Visual inspection confirms the agent-skills Battle receipt is visible
  with `G0 Seed Slip`, `G1-A Module Slip`, `G1-B Arc Courier`, and
  `G2 ZipInfo Path`, with no Sparta Explorer content. Caveat:
  `current-assertions.json` has `hasCanvas:false`, so this proof should be used
  as receipt-view evidence, not as final Pixi canvas/sprite proof.
- **WebGPT acceptance for this new host exists**:
  `skills/battle/local/webgpt-design-review-20260720T1742Z/response.md` starts
  with `ACCEPTED`, and `response.raw.md` contains the terminal sentinel. The
  Surf meta is degraded-focus (`status: recovered_focus_changed`) but
  `response_proof_status: response_proven`, `raw_contains_sentinel:true`,
  clean output is uncontaminated, and the controlled tab id matches.

## 3. What is Working Well

- Recent Battle commits on this branch:
  - `f3d9d5c36 battle: host receipt from agent-skills`
  - `4e6eda537 battle: name adaptive lineage exploits`
  - `e5e2893a7 battle: render live adaptive lineage receipt`
- Focused deterministic checks already passed for the committed host work:
  - `node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json`
  - `node scripts/build-static.mjs`
  - Curl of `:3003/__host.json`
  - Surf screenshot/assertion readback of the receipt route
- Current evidence posture:
  - `mocked: no`
  - `live: yes`
  - exercised: real adaptive-lineage qualification receipt, normalized fixture,
    standalone agent-skills static host, live browser render
  - WebGPT design acceptance: accepted with degraded-focus Surf transport
  - unverified for full immutable-goal closure: distinct Pixi sprite/canvas
    proof from the newest browser capture

## 4. What is Currently Broken Or Pending

- **Prior WebGPT transport blocker was cleared**. See
  `skills/battle/local/webgpt-agent-skills-host-blocker-20260720T1721Z.md`.
  After Surf host restart, a text-only sanity reached
  `proof_status: response_proven`, and the Battle screenshot review returned
  `ACCEPTED`.
- **Existing Battle WebGPT tab is busy**. Tab `837359249` contains the prior
  `:3003` review prompt and still showed `Thinking` / `Stop answering` when
  inspected. Do not submit a new prompt into that tab while it is busy.
- **Port `3002` is unusable in this session**. It is held by a stale D-state Vite
  child from an earlier attempt. Use `3003` until reboot or kernel release.
- **Do not trust `#battle/live` claims**. That route was verified false earlier;
  valid served hashes are `#battle`, `#battle/isolation`, and `#battle/receipt`.
- **Do not treat the current handoff as full immutable-goal closure**. The
  recovery evidence is strong enough to put the project back on the
  agent-skills-hosted receipt path, but the broader goal text still names Pixi
  sprite acceptance and deterministic renderer tests as primary proof.
- **Repo is dirty from unrelated agents**. Stage Battle handoff/artifact paths
  explicitly only. Never `git add -A`.

## 5. Next Steps

1. Commit and push this handoff plus the accepted WebGPT and fresh browser proof
   artifacts by explicit path.
2. Re-run or restore the deterministic renderer proof if the next agent is
   closing the full immutable goal: spectator lineage suite, Pixi sprite-mapping
   test, and a browser proof that actually demonstrates the expected sprite
   surface.
3. Audit the immutable goal checklist. Do not use closure language unless the
   final report cites backend receipt, browser screenshot/assertions, WebGPT
   response, deterministic renderer proof, sprite/canvas proof if applicable,
   and remote commit proof.

## 6. Project Context for Success

- **Key files**:
  - `skills/battle/src/battle_skill/adaptive_lineage.py`
  - `skills/battle/src/battle_skill/arena_live_battle_proof.py`
  - `skills/battle/spectator/src/lib/battle-adaptive-lineage-view-model.ts`
  - `skills/battle/spectator/src/lib/battle-data.ts`
  - `skills/battle/spectator/src/main.tsx`
  - `skills/battle/spectator/scripts/build-static.mjs`
  - `skills/battle/spectator/scripts/serve-static.mjs`
- **Current local server**:
  `node scripts/serve-static.mjs --host 127.0.0.1 --port 3003` from
  `skills/battle/spectator`.
- **Avoid npm** in this environment. `npm --version` and Vite operations hung.
  Use direct Node scripts:
  ```bash
  cd skills/battle/spectator
  node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json
  node scripts/build-static.mjs
  node scripts/serve-static.mjs --host 127.0.0.1 --port 3003
  ```
- **Do not move back to pi-mono**. The current recovery path is agent-skills
  hosted receipt evidence plus WebGPT acceptance for that host.
