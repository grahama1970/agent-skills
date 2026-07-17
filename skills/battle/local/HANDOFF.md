# Handoff Report: Battle Adaptive Lineage

**Timestamp**: 2026-07-17T16:54:52-04:00
**Active Agent**: Codex
**Status**: `PENDING_ADAPTIVE_IMPLEMENTATION`

## 1. Project Overview

- **Ecosystem**: Python Battle control plane, Tau/SciLLM model workers, and
  Docker Judge execution.
- **Current objective**: Make adaptive lineage perform a bounded,
  receipt-backed variation-evaluation-selection-reproduction loop for canonical
  BATTLE-004 Zip Slip.
- **Accepted gate**:

```text
G0 -> {G1-A, G1-B} -> deterministic Judge selection -> G2 -> STOP
```

- A G2 patched-target bypass is recorded as improvement but is **not required**
  for this gate. The gate proves adaptive mechanics, not convergence.
- No UI, Memory promotion, new arena, unbounded swarm, or broader Battle
  campaign belongs in this gate.

## 2. Repository and Worktree State

### Published refs used by the current proof

- `grahama1970/agent-skills@c79bc820e153c4e9029b11ed72b560acdb3c3fba`
- `grahama1970/tau@d03098293a76b07c54c5c1f03d667b02bf542be8`
- Tau remote `main` was positively checked at `d0309829` after push.

### Human worktree warning

The main `agent-skills` checkout is on branch `battle-ux8-live-contract` and is
heavily dirty with unrelated spectator, music, sprite, and other project work.
Treat every modified/untracked path as irreplaceable human work. Do not stash,
reset, clean, switch, or stage broadly.

Use clean task worktrees for implementation. Existing proof worktrees:

```text
/tmp/agent-skills-lineage-proof-c79bc820
/tmp/tau-slice05-push
```

The Tau proof worktree is detached at the pushed task commit. Verify refs before
reusing or create fresh clean worktrees.

## 3. What Works

### Causal pressure-backed lineage rung

The original child materialization failure was a Tau validator false negative.
The live child loaded local `app.py` through the exact standard-library
`importlib.util.spec_from_file_location` pattern, but Tau only recognized
literal `from app import import_zip` or `import app` strings.

Tau commit `d0309829` replaced that substring gate with bounded AST recognition
and added positive/negative focused tests. Verification before push:

```text
uv run ruff check ...                                      PASS
uv run pytest -q tests/test_battle_live_handoff.py \
  tests/test_battle_adaptive_lineage_tau_contract.py       11 passed
```

Fresh non-mocked live proof:

```text
/tmp/battle-adaptive-lineage-live-repair.XCLG1P
```

Command:

```bash
cd /tmp/agent-skills-lineage-proof-c79bc820/skills/battle
TAU_REPO=/tmp/tau-slice05-push \
  ./run.sh arena-prekill-survival-proof battle-004 \
  --out /tmp/battle-adaptive-lineage-live-repair.XCLG1P \
  --red-workers 2 --blue-workers 2
```

Result: exit `0`, `mocked:false`, real SciLLM calls, Docker Judge execution.
The receipts show:

```text
red-0 pressure observed                    80.783404
red-0 strategic_pre_kill decision          84.533597
red-1 materialized                        105.334346
red-0 terminal Judge receipt              105.655068
red-1 post-terminal Judge attempt starts  105.655241
```

The child confirmed the vulnerable original and was blocked after the Blue
patch (`BLUE_SUCCESS`). Important raw artifacts:

```text
/tmp/battle-adaptive-lineage-live-repair.XCLG1P/run-receipt.json
/tmp/battle-adaptive-lineage-live-repair.XCLG1P/lineage-receipts.json
/tmp/battle-adaptive-lineage-live-repair.XCLG1P/tau-live/spawn-decision-receipt.json
/tmp/battle-adaptive-lineage-live-repair.XCLG1P/tau-live/red/workers/red-1/materialized-artifact-receipt.json
/tmp/battle-adaptive-lineage-live-repair.XCLG1P/judge/replays/red-1__blue-1/attempt-receipt.json
```

This proves causal child spawning and post-terminal execution only.

## 4. What Is Still Broken

The current implementation is **not adaptive lineage in the accepted sense**.

1. Descendants receive receipt IDs, paths, and hashes, but not a bounded content
   packet containing parent source, complete strategy genome, and Judge
   observations.
2. `red-1` receives the generic Red prompt. It is not required to declare or
   perform a parent-relative mutation.
3. The current run produced near-equivalent parent/child Zip Slip techniques.
4. There is one child only. No sibling comparison, deterministic selection, or
   feedback-bound next generation exists.
5. No `battle.adaptive_lineage_qualification.v1` receipt exists.
6. No independent blind validator exists. WebGPT failed to deliver the requested
   implementation/validator ZIP; do not imply otherwise.

Exact current blocker:

```text
red-1 receives inherited receipt bindings but not bounded parent evidence
content required to produce and validate a parent-relative mutation
```

## 5. Accepted Implementation Contract

### Tau responsibilities

- Extend `src/tau_coding/battle_live_handoff.py` and
  `src/tau_coding/battle_scillm.py`; preserve existing causal mode.
- Embed hash-bound `battle.parent_evidence_packet.v1` content in descendant
  handoffs: parent exploit source, complete strategy genome, public scenario
  constraints, pressure/Judge observations, and G2 selection feedback.
- Exclude hidden Arena truth and unexposed Blue internals.
- Require generated descendants to return `mutation_operator` and
  `technique_delta` alongside `exploit_py` and `strategy_genome`.
- Use exactly:

```text
G1-A  method_replace
G1-B  oracle_or_parameter_mutation
G2    failure_guided_crossover
```

- Preserve provider response bytes and all receipt/source hashes. Never rewrite
  generated exploit code.

### Battle responsibilities

- Extend `src/battle_skill/arena_live_battle_proof.py`; change CLI only if a
  qualification-mode switch is required.
- Orchestrate exactly four Red specimens: G0, G1-A, G1-B, selected G2.
- Reuse one fixed Blue artifact for descendant Judge evaluations.
- Derive a code-based `battle.technique_signature.v1` from Python AST and
  normalized literals using:

```text
app_load_mode
archive_entry_construction
traversal_representation
target_call_form
success_oracle
exception_handling
```

- Write `battle.technique_delta_validation.v1`. Require different source hashes,
  at least one changed dimension, novelty distance >= 1, and code changes that
  match the claimed operator.
- Judge both G1 candidates and write objective
  `battle.candidate_fitness_receipt.v1` receipts.
- Select deterministically by: vulnerable original confirmed, patched bypass,
  greater novelty, lower duration, then lexicographic candidate ID.
- Write `battle.lineage_selection_receipt.v1` only after both G1 Judge receipts.
- Spawn G2 with selected G1 evidence, both G1 outcomes, and the selection
  receipt; then execute one G2 Judge attempt and stop.
- Write fail-closed `battle.adaptive_lineage_qualification.v1`; this receipt must
  control top-level status/exit when qualification mode is requested.

### Fixed budgets and stop conditions

```text
6 primary SciLLM calls maximum
8 HTTP completions maximum including JSON repair
4 Red specimens maximum
2 descendant generations maximum
1 fixed Blue artifact
1,200 seconds maximum
no red-3
stop after G2 Judge regardless of outcome
```

Stop immediately for a missing evidence packet, invalid mutation contract,
duplicate G1 technique signature, both G1 candidates failing the vulnerable
original, reproduction of a rejected signature, missing G2 feedback bindings,
or any budget overrun. Three matching live failures are one systemic failure;
do not continue reproducing it.

## 6. WebGPT Collaboration State

Authoritative assessment artifacts:

```text
/tmp/battle-adaptive-lineage-learning-assess-20260717-assess-response.md
/tmp/battle-adaptive-lineage-learning-assess-20260717-assess-response.meta.json
```

The human accepted the four-specimen/two-generation contract above.

Battle WebGPT tab:

```text
tab id: 837359249
url: https://chatgpt.com/g/g-p-6a408ce3c7a081918022e0eb6673aae3-battle/c/6a5a1f2b-0ac0-83ea-84a7-126c8acc0818
```

Do not create another tab.

Code-bundle generation failed twice:

1. The original attached-source request stalled for over 20 minutes at one
   narration sentence and was stopped.
2. Focused recovery returned only the text
   `PATCH adaptive_lineage_v2_patch.zip`; no downloadable attachment existed.
   Surf exited `8` with
   `required_attachment_missing:adaptive_lineage_v2_patch.zip`.

Failure evidence:

```text
/tmp/battle-adaptive-lineage-v2-code-recovery-response.md
/tmp/battle-adaptive-lineage-v2-code-recovery-response.raw.md
/tmp/battle-adaptive-lineage-v2-code-recovery-response.meta.json
```

The external code-generation family has reached its two-attempt limit. Do not
spend another cycle requesting the same ZIP. The architecture is accepted;
implementation remains pending.

## 7. Next Steps for the New Agent

1. Re-read this handoff and keep the accepted gate literal. Do not substitute
   the already-passing causal rung.
2. Inventory both repositories and create clean task worktrees from published
   refs. Do not alter the dirty human Battle worktree.
3. Implement Tau's bounded parent evidence and mutation-output contract first.
4. Add focused deterministic Tau tests, including private-evidence exclusion,
   exact hash binding, operator validation, and backward compatibility.
5. Implement Battle's code-derived signatures, G1 fitness/selection receipts,
   feedback-bound G2 orchestration, and qualification reducer.
6. Run focused Battle/Tau tests. Label them deterministic contract evidence, not
   live proof.
7. Run one fresh live qualification within the fixed call/time budgets.
8. Inspect raw receipts and independently check hashes, ordering, operators,
   signatures, selection determinism, G2 bindings, and call counts.
9. Commit and push task-only changes to both `main` branches only after the live
   qualification and independent artifact checks pass.

The accepted task plan is also preserved at:

```text
/tmp/battle-adaptive-lineage-v2-tasks.yaml
```

Its `/tmp` location is non-durable; this handoff is the durable contract.

## 8. Claim Discipline

- Current causal rung: `mocked:no`, `live:yes`, raw Docker/SciLLM proof exists.
- Four-specimen adaptive qualification: `mocked:no`, `live:no`, not implemented.
- Unit tests may prove wiring/contracts only. They cannot close the adaptive
  gate.
- WebGPT assessments are advisory design evidence, not closure proof.
- Do not report adaptive lineage working until one fresh qualification receipt
  and its underlying Tau/Judge artifacts satisfy every accepted assertion.

## 9. Key Files

```text
skills/battle/src/battle_skill/arena_live_battle_proof.py
skills/battle/src/battle_skill/cli.py
skills/battle/tests/test_arena_live_battle_proof_contract.py
/home/graham/workspace/experiments/tau/src/tau_coding/battle_live_handoff.py
/home/graham/workspace/experiments/tau/src/tau_coding/battle_scillm.py
/home/graham/workspace/experiments/tau/tests/test_battle_live_handoff.py
/home/graham/workspace/experiments/tau/tests/test_battle_adaptive_lineage_tau_contract.py
```
