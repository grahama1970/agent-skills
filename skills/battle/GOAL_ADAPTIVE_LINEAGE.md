# Battle Adaptive Lineage Goal (Immutable)

> Scope note: this is a **separate immutable goal** from `GOAL.md` (the BATTLE-004
> race-spectator cockpit). That goal still stands for the race view. This goal
> governs **one canonical adaptive Battle** whose sole job is to prove — in both
> backend and UX — that adaptive lineage works as expected, with a **finished**
> interface and **proper PixiJS sprites**. Where this goal and `GOAL.md` overlap
> on the same surface, the receipt-truth and anti-fake-density invariants of both
> apply; this goal additionally re-authorizes the interface-completion and sprite
> work that `GOAL.md`'s "agent is no longer UI owner" boundary had frozen.

## One-line

A single canonical Battle demonstrates end to end that adaptive lineage works:
the backend emits a **live, non-mocked** four-specimen qualification receipt, and
the **finished** spectator renders that exact receipt — proper PixiJS sprites,
honest `LIVE` badge, and the real selection decision — at
the agent-skills Battle spectator host. For the 2026-07-20 recovery this is
`http://127.0.0.1:3003/#battle`; the live adaptive-lineage receipt renders in
the top-level Battle UX because `:3002` was held by a stale uninterruptible Vite
child and was not the accepted host.

## Canonical Subject Lock

- Battle id: `battle-004` (adaptive-lineage variant)
- CWE: `CWE-22`, Zip Slip path traversal, entrypoint `POST /api/import-zip`
  (inherited from the BATTLE-004 source lock; do not substitute smoke rungs).
- Accepted adaptive gate:

  ```text
  G0 -> {G1-A, G1-B} -> deterministic Judge selection -> G2 -> STOP
  ```

- Operator contract (immutable):
  - `G0` = none (seed ancestor)
  - `G1-A` = `method_replace`
  - `G1-B` = `oracle_or_parameter_mutation`
  - `G2` = `failure_guided_crossover`
- Selection tie-break: deterministic, decided by `novelty_distance` (higher wins),
  then the documented secondary order. The runner-up G1 is retained and shown.
- Adaptive mechanics being proven: **variation -> evaluation -> selection ->
  feedback-bound reproduction**. G2 must be bound to the selected-G1 evidence,
  both G1 outcomes, and the selection receipt.

## Immutable Goal

Produce and keep reproducible **one** adaptive Battle in which:

1. the backend generates a live, independently-auditable adaptive-lineage
   qualification receipt for `battle-004`, and
2. the spectator UI at `#battle` renders that receipt as a finished interface —
   the `G0 -> {G1-A, G1-B} -> G2` comparison with operators, changed AST
   dimensions, novelty, and the selected-vs-runner-up decision — using proper
   themed PixiJS sprites and an honest live/recorded proof badge.

The UI must reflect the backend. A stale deployment that does not contain the
current adaptive-lineage code is a goal failure, not an acceptable "it works in
tests" state.

## Backend Acceptance (the proof)

Command (regenerate; `/tmp` artifacts are ephemeral):

```bash
cd skills/battle
TAU_REPO=<tau repo with the local-app-import recognizer fix> \
  ./run.sh arena-adaptive-lineage-qualification battle-004 --out <OUT>
```

The run passes only when every accepted assertion holds:

- `adaptive-lineage-qualification.json` -> `status: PASS`, all 11 checks green.
- All four Tau stage manifests: `mocked:false`, `live:true`, `status:PASS`;
  real SciLLM + real Docker Judge (`python:3.12-slim`).
- Four source hashes recompute-match **and** are all distinct.
- Operators per the contract above.
- All four Docker-judged `vulnerable_original_confirmed=true`.
- G1-A and G1-B deltas both PASS `validate_technique_delta` and are
  operator-consistent (no cosmetic-only mutations).
- Selection picks the winner by the exact documented tie-break; the runner-up is
  recorded, not discarded.
- G2 has exactly one Judge attempt, is bound to the selected-G1 evidence + both
  G1 outcomes + the selection receipt, and its signature differs from the
  rejected G1.
- Budget within the accepted envelope (SciLLM / HTTP / generations / specimens /
  wall-clock).

A fail-closed FAIL (e.g. `g1_delta_validation_failed`, `budget_overrun`) is
honest output. Inspect `stop_condition`; do not blindly re-roll.

Normalize the passing run into the UX fixture with a truthful source tag:

```bash
./run.sh <cli> normalize-adaptive-lineage-fixture <OUT> --data-source live
# writes spectator/src/lineage/__fixtures__/adaptive-lineage-live.json
```

## UX Acceptance (finished interface)

The interface is "finished" only when all of the following are true in a live
browser at the active Battle spectator host. For the current recovery, use
`http://127.0.0.1:3003/#battle`:

- **Deployment aligned.** The served host must identify the current
  agent-skills Battle spectator source. For the 2026-07-20 recovery,
  `curl http://127.0.0.1:3003/__host.json` must return
  `host: agent-skills battle spectator` and entry
  `skills/battle/spectator/src/main.tsx`. A pi-mono UX Lab route or frozen
  older release is a failure.
- **Panel reachable and complete.** The adaptive-lineage view renders the four
  specimens `G0 -> {G1-A, G1-B} -> G2` with, per node: operator, changed AST
  dimensions, and `novelty` distance. The selection row names the selected id
  over the runner-up id and states the deciding criterion. No `not emitted` /
  placeholder gaps for fields the receipt actually carries.
- **Honest badge.** The proof badge shows `LIVE` (green, `data-proves-live=true`)
  **only** when the loaded fixture's `data_source === "live"`; otherwise
  `RECORDED · MECHANICS` (amber). No invented live proof.
- **Testable hooks present.** `data-qid` anchors render:
  `battle:adaptive-lineage:badge` (with `data-data-source` and
  `data-proves-live`), `battle:adaptive-lineage:selected`,
  `battle:adaptive-lineage:runner-up`.

## PixiJS Sprite Acceptance (proper sprites)

Today `spriteIdForLane` (`spectator/src/engine/battle-lane-variant-map.ts`)
**forces every lane to one atlas** — `BATTLE_ACTIVE_RUNNER_SPRITE_ID =
"plague_nurgling"` — "the only runner atlas enabled until additional atlases pass
visual acceptance." That single-atlas lock is exactly why all four adaptive
specimens render as the identical green nurgling. Closing this goal means keeping
that proven sprite AND admitting enough additional accepted sprites to make the
four specimens distinct.

### Included working sprite (mandatory anchor — already proven)

- **`plague_nurgling` is the included, working sprite.** It is real and renders:
  91-frame PixiJS atlas at `assets/sprites/pixijs/plague_nurgling.{png,json}`,
  loaded via `runnerSpritesheet("plague_nurgling")`, and it is the atlas the code
  already enables. Proof frame extracted and rendered:
  `assets/sprites/working-sprite-proof/WORKING--plague_nurgling--plague_nurgling_idle_0.png`
  (64x64, 2122 opaque px — a horned green demon, not a blank frame).
- This goal must never regress below **one** working, code-enabled, rendering
  sprite. `plague_nurgling` satisfies that floor today; do not disable it.

### Additional sprites (to make specimens distinct)

- The four lineage specimens must render as **distinct, themed PixiJS sprites**.
  Additional atlases already staged under `assets/sprites/pixijs/` (`red_human`,
  `blue_lizard`, `crimson_*`, `slug_demon`, `typhus`, `nurgling`, `skull_horn`,
  `purple_horn_imp`) are candidates. A second atlas (`red_human`) is confirmed to
  extract/render (`assets/sprites/working-sprite-proof/red_human--red_human_idle_0.png`),
  so the path to distinct sprites is viable, not hypothetical.
- Each additional atlas must reach the enabled set **only** through the accepted
  pipeline that produced the nurgling: the `/sprite-atlas` skill (deterministic
  inspect -> repair -> normalize -> validate -> pack -> promote) plus the `/tau`
  sprite creator <-> reviewer visual-acceptance loop (agents under `agents/`).
  No hand-waved "looks fine" promotion. When an atlas passes, add it to
  `BATTLE_RUNNER_SPRITE_IDS`' enabled selection, not just the type union.
- Sprite selection is driven by a **receipt-backed** lane->sprite mapping keyed
  on stable identity (team + generation + operator + selection role), so the same
  receipt always yields the same sprite. No randomness, no time-seeded choice.
  This replaces the current constant-return `spriteIdForLane`.
- The selected G1 and the runner-up G1 are visually distinguishable from each
  other and from G0/G2; the mapping is documented in the engine and covered by a
  unit test.
- Parent -> child spawn connectors originate from the emitting parent event, not
  the left edge (timeline placement invariant from `GOAL.md` still binds).
- Sprite effects (spawn / mutate / judge / promote) fire on **proven** receipt
  beats only. `proven:false` events must not paint victory/promoted/killed
  textures.

## Primary Proof

Three artifacts, all required, none optional:

1. **Backend receipt** — a fresh passing
   `arena-adaptive-lineage-qualification battle-004` run (paths + the 11-check
   summary), independently recomputable.
2. **Deterministic renderer proof** — spectator lineage suite green
   (`npx vitest run src/lineage/ src/lib/battle-adaptive-lineage.test.ts`) and
   the pixi sprite-mapping test green.
3. **Live-browser screenshot** — `#battle` in a real browser showing the four
   distinct sprites, the `G0 -> {G1-A, G1-B} -> G2` panel, the selection row, and
   the `LIVE` badge when the loaded fixture is `data_source:"live"`. This is the
   artifact that closes the "looks unfinished" gap; deterministic tests alone do
   not satisfy it.

## Non-Self-Serving Closure Rule

This goal is **not** closed by an agent-authored status line, an audit receipt
that only cites earlier agent receipts, DOM selector existence, WebGPT acceptance
alone, or a collapsed screenshot that hides the adaptive-lineage details. Those
artifacts may be supporting evidence, but they are not closure authority.

After any human challenge to visible UX quality, the goal returns to
`DISPUTED_PENDING_FRESH_UX_PROOF` until a new proof bundle exists with all of
the following:

- A freshly built and served agent-skills Battle spectator host.
- Browser proof against the accepted top-level route
  `http://127.0.0.1:3003/#battle`, not only `#battle/receipt`.
- The adaptive-lineage `<details>` panel explicitly expanded before capture.
- A screenshot or video that visibly shows the four distinct sprites, the score
  card, the `LIVE` badge, the selected-vs-runner-up decision, operators, changed
  AST dimensions, novelty values, and the descriptive exploit names.
- A machine-readable proof JSON that records `mocked:false`, `live:true`,
  host identity, route, viewport, console/page errors, failed network requests,
  canvas dimensions, badge attributes, sprite resource URLs, visible text
  assertions, and whether the lineage panel was expanded.
- A human acceptance note or an explicit external-review artifact if the human
  has disputed the visual result.

If any of these are missing, report the goal as pending or disputed. Do not use
phrases such as achieved, done, verified, green, or closed for this goal.

## Prior Recovery Evidence (2026-07-20; supporting, not closure by itself)

- [x] Fresh live backend receipt:
      `skills/battle/local/adaptive-lineage-relive-20260720T144034Z/adaptive-lineage-qualification.json`
      reports `status: PASS`, `run_id: arena-adaptive-lineage-20260720T144034Z`,
      `battle_id: battle-004`, 4 primary SciLLM calls, 4 HTTP completions,
      4 red specimens, no budget overrun, and G2 Judge completion.
- [x] Live fixture normalized with `data_source:"live"` and descriptive exploit
      names in `skills/battle/spectator/src/lineage/__fixtures__/adaptive-lineage-live.json`:
      `G0 Zip Slip Spark`, `G1-A Importlib Slipstream`,
      `G1-B Writestr Detour`, `G2 ZipInfo Switchback`.
- [x] Agent-skills host proof:
      `skills/battle/local/agent-skills-host-verify-20260720T1646Z/http-host-proof.json`
      identifies `host: agent-skills battle spectator` and entry
      `skills/battle/spectator/src/main.tsx`.
- [x] Historical receipt-route render proof:
      `skills/battle/local/agent-skills-host-verify-20260720T1646Z/surf-assertions.json`
      targets `http://127.0.0.1:3003/#battle/receipt?engine=pixi`, has
      `mocked:false`, `live:true`, screenshot bytes `254726`, contains
      `ADAPTIVE LINEAGE`, `LIVE: Qual PASS`, all four exploit names, and
      selected-G1 evidence, and excludes Sparta/error markers. This is retained
      as historical receipt-route evidence; the current acceptance route is
      `#battle`.
- [x] WebGPT UX sign-off:
      `skills/battle/local/webgpt-design-review-20260720T1742Z/response.md`
      starts with `ACCEPTED`; `response.raw.md` contains terminal sentinel
      `<<<WEBGPT_DONE:20260720T174108Z:099a3588>>>`; `response.meta.json`
      has `response_proof_status: response_proven`, `raw_contains_sentinel:true`,
      `controlled_tab_id == requested_tab_id`, and no clean-output
      contamination markers. Caveat: Surf reports `proof_status: degraded_focus`
      because focus changed after submission; this is degraded transport evidence,
      not clean background-mode proof.
- [x] Deterministic renderer proof:
      `cd skills/battle/spectator && node node_modules/vitest/vitest.mjs run src/lineage/ src/lib/battle-adaptive-lineage.test.ts src/engine/battle-lane-variant-map.test.ts`
      passed 3 files / 31 tests. The suite covers the adaptive lineage panel,
      live badge attributes, and receipt-backed distinct sprite mapping.
- [x] Agent-skills Pixi asset host proof:
      `curl -I http://127.0.0.1:3003/battle-sprites/pixijs/battle-sprite-assets.manifest.json`
      and `curl -I http://127.0.0.1:3003/battle-sprites/pixijs/plague_nurgling.png`
      returned HTTP 200. `scripts/serve-static.mjs` now serves the committed
      `public/battle-sprites/` symlink to `skills/battle/assets/sprites/pixijs`.
- [x] Live-browser Pixi proof:
      `skills/battle/local/agent-skills-host-verify-20260720T1755Z/playwright-render-proof.json`
      targets `http://127.0.0.1:3003/#battle/receipt?engine=pixi`, has
      `mocked:false`, `live:true`, `hasCanvas:true`, canvas `1030x277`,
      `data-data-source:"live"`, `data-proves-live:"true"`, no failed
      fixture/sprite/atlas requests, no boot errors, and no Sparta/render-blocked
      markers. The screenshot
      `skills/battle/local/agent-skills-host-verify-20260720T1755Z/playwright-receipt-pixi-canvas.png`
      visually shows the four named lineage specimens with four distinct Pixi
      sprites.
- [x] Top-level `#battle` UX proof:
      `skills/battle/local/battle-ux-integration-20260720T2022Z/battle-route-render-proof.json`
      targets `http://127.0.0.1:3003/#battle`, has `mocked:false`,
      `live:true`, `hasCanvas:true`, canvas `1030x277`,
      `data-data-source:"live"`, `data-proves-live:"true"`, no failed
      requests, no console errors, no Sparta/render-blocked markers, no
      standalone `battle:nav:live`, contains
      `G0 Zip Slip Spark`, `G1-A Importlib Slipstream`,
      `G1-B Writestr Detour`, `G2 ZipInfo Switchback`, contains none of the old
      ambiguous names, and reports no lane/roster name overflow. Screenshot:
      `skills/battle/local/battle-ux-integration-20260720T2022Z/battle-route-adaptive-lineage.png`.
- [x] Obvious-error cleanup proof:
      `skills/battle/local/battle-ux-obvious-errors-20260720T2047Z/battle-route-no-obvious-errors-proof.json`
      targets `http://127.0.0.1:3003/#battle`, has `mocked:false`,
      `live:true`, `hasCanvas:true`, `data-data-source:"live"`,
      `data-proves-live:"true"`, contains all four descriptive names, contains
      `QUALIFIED 4` and per-generation `QUALIFIED` lane labels, has
      `forbiddenHits:[]` for `not emitted`, Sparta/render-blocked markers, old
      ambiguous names, empty stderr/skills summary cards, `RUNNING 4`, `ACTIVE`
      lane labels, and Red/Blue dash score rows, and reports no failed requests,
      no console errors, and no lane/roster name overflow. Screenshot:
      `skills/battle/local/battle-ux-obvious-errors-20260720T2047Z/battle-route-no-obvious-errors.png`.
- [x] Final Surf/Pixi obvious-error proof:
      `skills/battle/local/surf-obvious-errors-20260720T2120Z/battle-obvious-errors-and-pixijs-proof.json`
      targets the served top-level `#battle` route, has `mocked:false`,
      `live:true`, `forbiddenHits:[]`, `has_scorecard:true`, live badge
      `data_source:"live"` / `proves_live:"true"`, canvas `1030x277`, and six
      observed Pixi sprite/manifest resource requests. Screenshot:
      `skills/battle/local/surf-obvious-errors-20260720T2120Z/battle-scorecard-restored.png`.

**GOAL STATUS: DISPUTED_PENDING_HUMAN_OR_EXTERNAL_UX_ACCEPTANCE**.

The prior audit receipt
`skills/battle/local/goal-adaptive-lineage-audit-20260721T0005Z.json` remains a
supporting evidence index: it reports `status:"PASS"`, `failed:[]`, local `HEAD`
and `origin/battle-adaptive-lineage-goal` both at the audited Battle evidence
commit `d476a192d28421bfbbe04aa69a87f1104e94aae1`, and cites the live backend
receipt plus final Surf/Pixi proof artifacts above. It does **not** close this
goal after the UX has been challenged, because it does not by itself establish a
fresh, expanded, human-acceptable top-level `#battle` visual state.

Fresh local browser evidence now exists at
`skills/battle/local/fresh-ux-proof-20260721T0130Z/fresh-visible-ux-proof.json`
with `status:"PASS"`, `failed:[]`, `mocked:false`, `live:true`, expanded
top-level route `http://127.0.0.1:3003/#battle`, host identity
`agent-skills battle spectator`, screenshot
`skills/battle/local/fresh-ux-proof-20260721T0130Z/battle-expanded-lineage.png`,
and positive checks for the scorecard, honest live badge, four descriptive
names, selected-vs-runner-up row, operators, novelty values, changed AST
dimensions, four lineage nodes, Pixi canvas, observed sprite resources, no
failed requests, no console errors, and no forbidden text. This satisfies the
fresh local proof rung, but the goal remains pending until the disputed visual
result receives human acceptance or an explicit external-review artifact.

## Allowed Scope

- `skills/battle/spectator/src/**` (canonical UI; incl. `lineage/**` and
  `engine/**` for the sprite mapping)
- `skills/battle/src/battle_skill/**` adaptive-lineage backend + CLI + fixture
  normalizers
- `skills/battle/assets/sprites/**` sprite atlases already present (use them; do
  not regenerate art in this pass unless an atlas frame is missing)
- `/sprite-atlas` skill + `/tau` sprite creator<->reviewer loop (agents under
  `agents/`) — the accepted method for validating and promoting any additional
  atlas to the enabled set
- Tau local-app-import recognizer (`~/workspace/experiments/tau`)
- The deployment release cut for `/mnt/storage12tb/deployments/agent-skills`
- This goal file and its plan/handoff docs

## Forbidden Drift

- No fake density: every specimen, operator, novelty value, sprite, and the
  selection decision must come from receipts / validated fixture fields.
- No invented live proof; no `LIVE` badge without `data_source:"live"`.
- Do not weaken `validate_technique_delta` or the AST validator to force a PASS.
- Do not change the accepted operator contract or the selection tie-break to make
  a run pass.
- No random / time-seeded sprite selection.
- No redesign of the BATTLE-004 race shell defined by `GOAL.md`; the adaptive
  panel and sprites are additive to that accepted layout.

## Retry And Stop Rule

If the same live-qualification FAIL, deployment mismatch, or sprite-rendering
defect survives two focused attempts, stop and write a blocker report with:

- failed command
- exact error / `stop_condition` output
- changed files
- screenshot + receipt artifacts
- current hypothesis
- one recommended next action
