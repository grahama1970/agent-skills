# Battle Adaptive Lineage Goal (Immutable)

## Operator Clarification (2026-08-22)

This immutable goal is not "finish a PixiJS game." The controlling goal is a
working adaptive Battle backend: an authorized Red/Blue security competition can
spawn, evaluate, select, and continue parent/child lineage from real
Judge-backed receipts, scorekeeper evidence, and memory promotion or
nonpromotion decisions.

PixiJS is a replay/spectator artifact. It is required only to make the receipts
inspectable and understandable. Replay polish cannot replace backend proof, and
backend adaptive lineage must not be treated as blocked on PixiJS polish beyond
truthful receipt inspectability.

> Scope note: this is a **separate immutable goal** from `GOAL.md` (the BATTLE-004
> race-spectator cockpit). That goal still stands for the race view. This goal
> governs **one canonical adaptive Battle** whose job is to prove backend
> adaptive lineage first and then replay that same evidence honestly. Where this
> goal and `GOAL.md` overlap on the same surface, the receipt-truth and
> anti-fake-density invariants of both apply. The spectator must not invent
> lineage truth, but PixiJS polish is not the core Battle product.

## Current State Addendum (2026-07-28)

Verification date: 2026-07-28. Source commit inspected:
`277afadfdea5`.

Original goal: the four-specimen adaptive-lineage proof
`G0 -> {G1-A,G1-B} -> G2` remains **MET** as accepted on 2026-07-18.
This addendum does not delete, weaken, or re-adjudicate that acceptance record.

Historical implementation descriptions in this file, including the former
single-atlas limitation and early engine-state notes, are retained as history.
They are superseded by the completion evidence below where that evidence records
four distinct accepted sprites, an honest live badge, and the finished
four-specimen comparison panel.

Current active goal: the later dual-team co-evolution amendment is separate
from the original four-specimen goal and is **NOT_MET** until its backend and
frontend tickets close with deterministic proof. The amendment requires one
canonical source-run fixture for populated Red and Blue mechanics trees,
same-team lineage isolation, Judge-owned outcomes, and score evidence that the
spectator can consume without importing unrelated mechanics data.

Active and related tickets, grouped by purpose:

- Deterministic health: #1035 added `backend-eval` and is closed; #1047 repaired
  or retired the invalid adaptive-live genetic replay fixture and is closed.
- Receipt truth: #1048 tracks the canonical dual-team co-evolution fixture;
  #1063 tracks the kill-shot replay's missing Judge-backed kill receipt and is
  currently `needs-human`.
- Frontend proof: #1064 tracks deriving the adaptive mechanics panel from the
  active receipt fixture instead of a static fixture import.
- Live lineage: #1065 tracks real Memory plus verified primitive end-to-end
  lineage lifecycle proof.
- Production scheduler work: #1066 tracks the first bounded proactive Red/Blue
  overlap slice; #46 remains the broader asynchronous scheduler epic.
- Completed dependency tickets: #1051, #1052, #1053, and #1054 closed supporting
  sprite loading, score evidence, self-certification removal, and deterministic
  QEMU port allocation work.

Current blocker summary: do not claim backend green, production readiness,
dual-team closure, or human UX acceptance from the original 2026-07-18
four-specimen proof. Those later claims require the active ticket receipts named
above.

## One-line

A single canonical Battle demonstrates that adaptive lineage works when the
backend emits **live, non-mocked** Red/Blue/Judge/scorekeeper/memory-bound
parent/child lineage receipts and the spectator replays those exact receipts
without inventing truth.

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

1. the backend runs an authorized `battle-004` adaptive lineage loop that binds
   Red/Blue parent and child generation, Judge replay, scorekeeper authority,
   and memory promotion or nonpromotion into auditable receipts;
2. the adaptive decision is derived from same-run Battle evidence, not static UI
   fixtures, self-certification, or post-hoc narrative; and
3. the spectator UI at `#battle`/PixiJS replays that same receipt set with an
   honest live/recorded proof badge and no invented lineage truth.

The UI must reflect the backend. A stale deployment that does not contain the
current adaptive-lineage code is a goal failure, not an acceptable "it works in
tests" state.

PixiJS is acceptance evidence for receipt inspectability, not the core closure
criterion. The immutable goal remains unmet if backend Red/Blue/Judge/
scorekeeper/memory lineage is not proven, even when the replay looks good.

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

## Current Readiness Override (2026-08-23)

The immutable goal remains the same, but the current project state must be
reported as **NOT_MET** until fresh, durable receipts satisfy the Primary Proof
section above.

The historical July acceptance record below is useful recovery evidence, not a
current completion claim. On 2026-08-23 the named durable receipt
`local/adaptive-live-proof-1784396246/adaptive-lineage-qualification.json` was
missing; only `local/adaptive-live-proof-1784396246/run.log` remained. The
generated `CURRENT_STATUS.json` also explicitly marks
`full_adaptive_improvement_proven` as unsupported and
`adaptive_lineage_effect` as partial/open.

Therefore agents must not stop at the old MET block. The next acceptable closure
path is:

1. regenerate a fresh durable `arena-adaptive-lineage-qualification battle-004`
   receipt under `skills/battle/local/`;
2. normalize that same receipt into the Pixi replay fixture with truthful
   `data_source`;
3. run the Battle agentic-evals coverage for adaptive lineage and Pixi replay;
4. capture fresh browser/Pixi proof from the same receipt set; and
5. regenerate `CURRENT_STATUS.json` so the status, goal doc, receipts, and
   tickets agree.

## Historical Completion Evidence — Recovery Only

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

**HISTORICAL STATUS: ACCEPTED ON 2026-07-18. CURRENT STATUS: NOT_MET UNTIL
REGENERATED WITH DURABLE RECEIPTS.**

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
