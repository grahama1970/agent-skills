# Handoff Report: Battle Adaptive Lineage — LIVE QUALIFIED

**Timestamp**: 2026-07-18T14:06:28Z
**Active Agent**: Claude (Fable)
**Status**: `ADAPTIVE_LINEAGE_LIVE_QUALIFIED` — backend + front-end implemented,
one fresh live qualification PASS independently verified.

> Supersedes the prior `PENDING_ADAPTIVE_IMPLEMENTATION` handoff. The accepted
> four-specimen adaptive gate is implemented and proven live.

## 0. IMPORTANT — location of the code (needs migration into this repo)

The code was built in a linked git worktree, NOT in this `agent-skills`
working tree, because the prior handoff instructed "use clean task worktrees; do
not alter the dirty human checkout." The human has since asked that all work live
in `agent-skills/skills/battle` directly. **The changes still need to be migrated
into this repo.** Current source of truth:

```text
Battle changes:  /home/graham/workspace/experiments/agent-skills-adaptive-mechanics/skills/battle
                 branch battle-adaptive-mechanics (base c79bc820e)
Tau changes:     /home/graham/workspace/experiments/tau-adaptive-mechanics
                 branch tau-adaptive-mechanics (base d0309829)
```

Note: during the session the main `agent-skills` checkout was switched from
`battle-ux8-live-contract` to `main` and reset to `origin/main` by concurrent
activity (git reflog). Confirm the intended branch before migrating.

### Files to bring into `agent-skills/skills/battle` (all task-only, additive)

New:
```text
src/battle_skill/technique_signature.py
src/battle_skill/adaptive_lineage.py
src/battle_skill/adaptive_lineage_mechanics_fixture.py
scripts/build_adaptive_lineage_recorded_fixture.py
tests/test_technique_signature_contract.py
tests/test_adaptive_lineage_reducer.py
tests/test_live_specimen_provider_wiring.py
tests/test_adaptive_lineage_fixture.py
spectator/src/lib/battle-adaptive-lineage.ts
spectator/src/lineage/battle-adaptive-lineage.test.ts
spectator/src/lineage/__fixtures__/adaptive-lineage-recorded.json
spectator/src/lineage/__fixtures__/adaptive-lineage-live.json
```
Modified:
```text
src/battle_skill/arena_live_battle_proof.py   (+ run_live_adaptive_lineage_qualification)
src/battle_skill/cli.py                        (+ 2 commands)
spectator/src/lib/battle-types.ts              (adaptive lineage types)
spectator/src/lineage/BattleLineageComparisonPanel.tsx  (real adaptive render)
```
Tau (in `~/workspace/experiments/tau`):
```text
src/tau_coding/battle_live_handoff.py          (robust local-app-import recognizer)
tests/test_battle_adaptive_lineage_tau_contract.py
```

## 1. Accepted gate — now MET

```text
G0 -> {G1-A, G1-B} -> deterministic Judge selection -> G2 -> STOP
```

Proves adaptive MECHANICS (variation -> evaluation -> selection ->
feedback-bound reproduction). A live qualification satisfying every accepted
assertion was produced and independently audited.

## 2. Live qualification result (the proof)

```bash
cd <battle skill dir>
TAU_REPO=<tau repo with the recognizer fix> \
  ./run.sh arena-adaptive-lineage-qualification battle-004 --out <OUT>
```

Latest passing run (ephemeral /tmp — regenerate to reproduce):

```text
/tmp/battle-adaptive-live-run6/adaptive-lineage-qualification.json   status: PASS
/tmp/battle-adaptive-live-run6/receipts/{specimen,fitness,lineage-selection}-*.json
/tmp/battle-adaptive-live-run6/stage-{G0,G1-A,G1-B,G2}/tau-live/...   mocked:false live:true
```

All 11 checks green. Independently verified:

- `mocked:false`, `live:true`, `status:PASS` on all four Tau stage manifests;
  real SciLLM (gpt-5.5) + real Docker Judge (`python:3.12-slim`).
- Four source hashes recompute-match AND are all distinct.
- Operators per contract: G0=none, G1-A=`method_replace`,
  G1-B=`oracle_or_parameter_mutation`, G2=`failure_guided_crossover`.
- All four Docker-judged `vulnerable_original_confirmed=true` (~1.1s each).
- G1-A delta PASS (novelty 2: `app_load_mode`+`target_call_form`); G1-B delta
  PASS (novelty 1: `archive_entry_construction`); both operator-consistent.
- Selection picked **G1-A over G1-B by `novelty_distance` (2>1)** per the exact
  tie-break order.
- G2 bound to selected-G1 evidence + both G1 outcomes + selection receipt;
  exactly one G2 Judge attempt; G2 signature differs from rejected G1 (novelty 3).
- Budget within envelope: 4 SciLLM / 4 HTTP / 2 generations / 4 specimens / 4.6s.

## 3. Front-end (UX showcase)

- Live fixture: `spectator/src/lineage/__fixtures__/adaptive-lineage-live.json`
  (`data_source:"live"`, normalized from run6 via
  `battle_skill.cli normalize-adaptive-lineage-fixture <OUT> --data-source live`).
- `spectator/src/lineage/BattleLineageComparisonPanel.tsx` renders
  G0 -> {G1-A, G1-B} -> G2 with operators, changed AST dimensions, novelty, and
  the selected-vs-runner-up decision. Badge is `LIVE` (green) only when
  `data_source==="live"`; else `RECORDED · MECHANICS` (amber).
- **Outstanding:** a live-browser screenshot of the running spectator (current
  proof is passing `renderToStaticMarkup` tests). Use `./run.sh prove-spectator`.

## 4. Test status (all green)

- Battle Python adaptive suite: **65 pass, ruff clean**.
- Tau adaptive suite: **19 pass, ruff clean**.
- Spectator: **186 vitest pass, typecheck clean**.

## 5. Operator steering (why live PASS is reliable)

`_operator_guidance` in `adaptive_lineage.py` steers each descendant toward the
AST dimensions its operator must move, with concrete before/after code and
explicit prohibition of cosmetic changes (wrapper functions, `../`->`../../`).
It does NOT weaken the AST validator — every exploit is still checked by
`validate_technique_delta`.

## 6. Debugging history (6 live runs, each a DISTINCT root cause)

1. FAIL @ G1-A: recognizer lacked `importlib.import_module` -> added.
2. FAIL @ G1-A: recognizer brittle for `spec_from_file_location`+`getattr` ->
   made recognizer robust (systemic fix).
3. FAIL (fail-closed) `g1_delta_validation_failed`: cosmetic mutations ->
   sharpened operator steering.
4. FAIL @ G0: transient Blue `app.py` truncation (unrelated model noise) ->
   re-ran.
5. FAIL (fail-closed) `budget_overrun`: descendant-generation double-count ->
   orchestrator-only, regression-tested.
6. **PASS** — clean, independently verified.

## 7. Next steps

1. **Migrate the code** from the worktrees into `agent-skills/skills/battle`
   (and the Tau change into `~/workspace/experiments/tau`) — see section 0 file
   list. Task-only, additive.
2. Decide commit/branch strategy (confirm intended branch first — checkout moved
   to `main` during the session).
3. (Optional) Live-browser screenshot of the spectator LIVE badge.
4. (Optional resilience) Bounded retry for transient G0 Blue truncation.
5. Reproduce the live PASS to re-confirm; `/tmp` artifacts are ephemeral. A
   fail-closed FAIL on cosmetic mutations is honest — inspect `stop_condition`,
   never re-roll blindly.

## 8. Claim discipline

- Adaptive four-specimen qualification: `mocked:false`, `live:yes`, **PASS**,
  independently audited. Reproduce to re-confirm.
- 90+ deterministic tests prove wiring/contracts; the live receipt closes the
  gate.
- Front-end renders the live receipt with an honest LIVE badge; visual
  screenshot still outstanding.
