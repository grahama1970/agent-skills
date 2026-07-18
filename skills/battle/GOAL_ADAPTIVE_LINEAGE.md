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
`http://localhost:3002/#battle`.

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
browser at `http://localhost:3002/#battle`:

- **Deployment aligned.** `:3002` serves the **current** spectator source
  (contains `spectator/src/lib/battle-adaptive-lineage.ts` and the current
  `BattleLineageComparisonPanel.tsx`). The host resolves
  `@agent-skills/battle-spectator` via
  `/mnt/storage12tb/deployments/agent-skills/current`; that release must be
  re-cut so `current` points at a build containing this goal's code. A frozen
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

## Completion Criteria — MET (evidence per line)

- [x] Adaptive backend and Tau recognizer fix **committed** — `origin/main`
      `9ac0b5438` (battle-only commits); Tau fix committed on
      `tau-adaptive-mechanics`.
- [x] `arena-adaptive-lineage-qualification battle-004` PASS, 11/11,
      `mocked:false`, `live:true` — fresh durable receipt at
      `local/adaptive-live-proof-1784396246/` (all 4 stages live, ≥4 distinct hashes).
- [x] `adaptive-lineage-live.json` normalized `data_source:"live"` (validator PASS).
- [x] `current` re-cut to release `995ea0ad8` containing this code; `:3002` HTTP 200
      serving it (verified via `@fs` + live render).
- [x] `#battle/receipt` renders G0 -> {G1-A, G1-B} -> G2 with operators, AST deltas,
      novelty, selection row — verified live, no false gaps.
- [x] Badge = `LIVE` (`data-proves-live=true`, `data-data-source=live`) — verified live.
- [x] `plague_nurgling` mandatory floor: enabled, G0 seed, renders; proof frame in
      `working-sprite-proof/`.
- [x] Four distinct sprites (nurgling / crimson_chainsaw_demon / slug_demon / typhus),
      each ACCEPTED by the `/sprite-atlas` + `/tau` sprite-reviewer loop (which
      REJECTED crimson_hornbreaker + skull_horn); receipt-backed map, unit-tested.
- [x] Parent->child connectors from the emitting parent — `EdgeRow` renders
      `G0->G1-A`, `G0->G1-B`, `G1-A->G2` (G2 from its selected parent G1-A, not the
      left edge); lineage-flow harness shows parent->child spawn connectors.
- [x] Live-browser screenshot attached — `working-sprite-proof/LIVE-battle-adaptive-lineage-proof.jpg`.
- [x] `data-qid` anchors present — badge / selected / runner-up.
- [x] Backend adaptive suite (green), spectator suite (**191 pass**), pixi sprite
      test (green); typecheck clean. (Note: 2 pre-existing `tests/` failures —
      `child_tau_dag_private_boundary`, `proof_card_fixture_contract` — fail on the
      merge-base and are unrelated to this goal.)

**GOAL STATUS: MET** — 2026-07-18, verified end to end.

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
