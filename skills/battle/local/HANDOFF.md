# Handoff Report: battle adaptive-lineage receipt

**Timestamp**: 2026-07-21T01:25:00Z
**Active Agent**: Codex
**Branch**: `battle-adaptive-lineage-goal`
**Current objective**: finish `GOAL_ADAPTIVE_LINEAGE.md` recovery from the
agent-skills worktree, not the pi-mono shell.

> Evidence rule for the next agent: trust fresh browser artifacts and visible
> screenshot inspection over stale prose or agent-authored closure receipts.
> The prior 2026-07-20 live backend receipt, agent-skills `:3003` Pixi browser
> proof, WebGPT accepted review, and immutable-goal audit receipt remain
> supporting evidence only. The human disputed the visible UX closure on
> 2026-07-21, so the goal required fresh local proof plus human or external
> acceptance. That acceptance now exists in
> `skills/battle/local/webgpt-fresh-ux-review-20260721T0035Z/response.md`, and
> the final acceptance audit receipt is
> `skills/battle/local/final-acceptance-audit-20260721T0445Z.json`.
> After unrelated commits advanced the shared branch, the current-head
> revalidation receipt is
> `skills/battle/local/current-head-evidence-revalidation-20260721T0458Z.json`.
> It reports `status:"PASS"`, `failed:[]`, and revalidates the Battle evidence
> paths at branch head `6f8647981466db8f732c3914b9dd1581ecc2ddf2`, which matched
> `origin/battle-adaptive-lineage-goal` when generated.

## 1. Project Overview

- **Ecosystem**: Python Battle backend under `skills/battle/src/battle_skill`
  plus TypeScript/React/Pixi spectator under `skills/battle/spectator`.
- **Core purpose**: prove one canonical BATTLE-004 adaptive lineage:
  `G0 -> {G1-A, G1-B} -> G2`, with a live SciLLM + Docker qualification receipt
  and a spectator that renders that exact receipt with honest live/recorded
  state.
- **Current hosting decision**: agent-skills owns the spectator host. Use
  `http://127.0.0.1:3003/#battle`; that top-level Battle UX now renders the
  live adaptive-lineage receipt directly. Do not resume from
  `pi-mono/packages/ux-lab` or add/revive a standalone `#battle/live` route.

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
  `G0 Zip Slip Spark`, `G1-A Importlib Slipstream`,
  `G1-B Writestr Detour`, `G2 ZipInfo Switchback`.
- **Top-level Battle UX integration is now wired**:
  `#battle` is classified as receipt replay, defaults to the live adaptive
  lineage fixture, and defaults to Pixi unless `?engine=dom` is explicit.
  The visible nav points Adaptive Replay to `#battle`, moves the design mockup
  to `#battle/isolation`, and no longer exposes a standalone `#battle/live`
  nav affordance.
- **Agent-skills host exists and is committed**:
  `skills/battle/spectator/index.html`, `src/main.tsx`, `src/standalone.css`,
  and `scripts/{build-static,serve-static}.mjs`.
  `curl http://127.0.0.1:3003/__host.json` returns host
  `agent-skills battle spectator` and entry `skills/battle/spectator/src/main.tsx`.
- **Historical receipt-route browser proof exists**:
  `skills/battle/local/agent-skills-host-verify-20260720T1646Z/surf-assertions.json`
  targets `http://127.0.0.1:3003/#battle/receipt?engine=pixi`, `mocked:false`,
  `live:true`, screenshot bytes `254726`, and asserts visible text for
  `ADAPTIVE LINEAGE`, `LIVE: Qual PASS`, all four then-current exploit names,
  and selected-G1 evidence. This is superseded for UX acceptance by the current
  top-level `#battle` proof below.
- **Historical post-review browser screenshot exists**:
  `skills/battle/local/agent-skills-host-verify-20260720T1748Z/` contains
  `current-render.json`, `current-assertions.json`, and
  `surf-receipt-agent-skills-3003-current.png` for the same `:3003` receipt
  route. It is superseded for current UX acceptance by the top-level `#battle`
  proof below. Caveat:
  `current-assertions.json` has `hasCanvas:false`, so this proof should be used
  as receipt-view evidence, not as final Pixi canvas/sprite proof.
- **Final Pixi browser proof exists**:
  `skills/battle/local/agent-skills-host-verify-20260720T1755Z/` contains
  `playwright-render-proof.json` and `playwright-receipt-pixi-canvas.png`.
  The proof targets `http://127.0.0.1:3003/#battle/receipt?engine=pixi`,
  has `mocked:false`, `live:true`, `hasCanvas:true`, canvas `1030x277`,
  live badge attrs `data-data-source:"live"` and `data-proves-live:"true"`,
  no failed fixture/sprite/atlas requests, no boot errors, and no Sparta or
  render-blocked markers. Visual inspection confirms four distinct Pixi sprites
  for the four named lineage specimens.
- **Current top-level `#battle` UX proof exists**:
  `skills/battle/local/battle-ux-integration-20260720T2022Z/` contains
  `battle-route-render-proof.json` and `battle-route-adaptive-lineage.png`.
  It targets `http://127.0.0.1:3003/#battle`, has `mocked:false`,
  `live:true`, `hasCanvas:true`, live badge attrs
  `data-data-source:"live"` and `data-proves-live:"true"`, contains all four
  current descriptive names, contains no old ambiguous names, no Sparta text,
  no render-blocked text, no failed requests, no console errors, no standalone
  `battle:nav:live`, and reports no lane/roster name overflow.
- **Obvious-error cleanup proof exists**:
  `skills/battle/local/battle-ux-obvious-errors-20260720T2047Z/` contains
  `battle-route-no-obvious-errors-proof.json` and
  `battle-route-no-obvious-errors.png`. It targets
  `http://127.0.0.1:3003/#battle`, has `mocked:false`, `live:true`,
  `hasCanvas:true`, live badge attrs `data-data-source:"live"` and
  `data-proves-live:"true"`, contains all four descriptive names, and reports
  `forbiddenHits:[]` for `not emitted`, Sparta/render-blocked markers, old
  ambiguous names, empty stderr/skills summary cards, `RUNNING 4`, `ACTIVE`
  lane labels, and Red/Blue dash score rows. It also reports no failed requests,
  no console errors, and no lane/roster name overflow.
- **Prior Surf/Pixi obvious-error pass exists**:
  `skills/battle/local/surf-obvious-errors-20260720T2120Z/` contains
  `battle-obvious-errors-and-pixijs-proof.json`,
  `battle-scorecard-restored.text`, and `battle-scorecard-restored.png`.
  It targets the served top-level `#battle` route, has `mocked:false`,
  `live:true`, `forbiddenHits:[]`, `has_scorecard:true`, live badge
  `data_source:"live"` / `proves_live:"true"`, canvas `1030x277`, and six
  observed Pixi sprite/manifest resource requests. This pass is useful
  supporting evidence, but it is not sufficient after the human disputed whether
  the visible UX works as expected.
- **Fresh expanded top-level UX proof exists after challenge**:
  `skills/battle/local/fresh-ux-proof-20260721T0130Z/` contains
  `fresh-visible-ux-proof.json` and `battle-expanded-lineage.png`. The proof
  targets `http://127.0.0.1:3003/#battle`, has `status:"PASS"`, `failed:[]`,
  `mocked:false`, `live:true`, host identity `agent-skills battle spectator`,
  expanded lineage panel, scorecard present, live badge
  `data-data-source:"live"` / `data-proves-live:"true"`, all four descriptive
  exploit names, selected-vs-runner-up row, operators, novelty values, changed
  AST dimensions, four lineage nodes, Pixi canvas `1030x277`, observed sprite
  resources, no failed requests, no console errors, and no forbidden text.
  Visual inspection of the screenshot shows the expanded lineage panel above the
  race view, the scorecard, and four distinct Pixi sprites. This is current
  local evidence, but closure still requires human or external acceptance.
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
- Current final deterministic checks:
  - `node node_modules/vitest/vitest.mjs run src/lineage/ src/lib/battle-adaptive-lineage.test.ts src/engine/battle-lane-variant-map.test.ts`
    passed 3 files / 31 tests.
  - `node node_modules/vitest/vitest.mjs run src/lib/battle-receipt-lineage.test.ts src/lib/is-battle-pixi-engine.test.ts src/lib/battle-adaptive-lineage.test.ts src/lineage/battle-adaptive-lineage.test.ts src/lib/battle-lane-lifecycle-evidence.test.ts`
    passed 5 files / 34 tests after the obvious-error cleanup.
  - `node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json` passed.
  - `node scripts/build-static.mjs` passed.
  - `curl -I /battle-sprites/pixijs/battle-sprite-assets.manifest.json` and
    `curl -I /battle-sprites/pixijs/plague_nurgling.png` returned HTTP 200.
- Current evidence posture:
  - `mocked: no`
  - `live: yes`
  - exercised: real adaptive-lineage qualification receipt, normalized fixture,
    standalone agent-skills static host, live browser render, Pixi sprite canvas
  - WebGPT design acceptance: accepted with degraded-focus Surf transport

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
- **Do not trust `#battle/live` claims**. The valid primary UX is now
  `#battle`, with the live receipt rendered in-place. Keep `#battle/receipt`
  only as a compatible/deep-link receipt route, not as the main acceptance URL.
- **Fresh external acceptance exists after challenge**:
  `skills/battle/local/webgpt-fresh-ux-review-20260721T0035Z/response.md`
  contains `VERDICT: ACCEPT_CURRENT_UX_GATE`. Surf transport metadata in
  `response.meta.json` reports `status:"completed"`,
  `proof_status:"response_proven"`, `response_proof_status:"response_proven"`,
  exact tab routing (`requested_tab_id == controlled_tab_id == "837360432"`),
  `tab_was_created:false`, `raw_contains_sentinel:true`,
  `focus_changed:false`, and `transport_degraded:false`.
- **Final acceptance audit receipt exists**:
  `skills/battle/local/final-acceptance-audit-20260721T0445Z.json` reports
  `status:"PASS"`, `failed:[]`, `mocked:false`, `live:true`, and ties together
  deterministic local browser proof with the explicit WebGPT acceptance.
- **Current-head revalidation exists after later branch movement**:
  `skills/battle/local/current-head-evidence-revalidation-20260721T0458Z.json`
  reports `status:"PASS"`, `failed:[]`, `mocked:false`, `live:true`,
  `current_head:"6f8647981466db8f732c3914b9dd1581ecc2ddf2"`, and
  `remote_sha:"6f8647981466db8f732c3914b9dd1581ecc2ddf2"`. It verifies that
  the goal, handoff, final audit, fresh browser proof, screenshot, WebGPT
  request/response/meta/raw artifacts, and badge-hook source file are tracked at
  the current pushed branch head.
- **Repo is dirty from unrelated agents**. Stage Battle handoff/artifact paths
  explicitly only. Never `git add -A`.

## 5. Next Steps

1. Preserve the final acceptance audit receipt, WebGPT review artifacts, and
   current-head revalidation receipt.
2. Keep using `#battle` on the agent-skills host as the primary acceptance
   route. Treat `#battle/receipt` as a compatible deep link and do not revive
   standalone `#battle/live` without a new written goal.
3. Do not claim a new backend rerun; the final acceptance receipt closes the
   amended visible UX dispute by combining the existing live backend evidence,
   fresh local browser proof, and explicit external UX acceptance.

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
