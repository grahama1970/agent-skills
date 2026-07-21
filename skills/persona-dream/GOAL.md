# Persona Dream Immutable Goal

Last updated: 2026-07-21

## Controlling Goal

Meet the research goals of Persona Dream by proving that synthetic dreaming can
support prospective, calibrated Theory of Mind while the pipeline remains
receipt-backed, provenance-bound, and fail-closed under faults.

The controlling research program is PCTOM-R: Prospective Counterfactual
Theory-of-Mind Reliability.

This supersedes the prior media-spine and Kling-video goals for current work.
Those goals remain historical evidence in Git and in `GOAL_V2.md`, but they are
not the active critical path unless the human explicitly reactivates them.

## Alignment With README

`README.md` describes the broader Persona Dream research purpose: a persistent
persona can synthesize an explicitly synthetic dream from grounded memories,
observe it, interpret it, persist only supported ToM state, and later use that
memory without confusing imagination with literal history or mutating identity.

This `GOAL.md` narrows the active work to the next falsifiable research question
inside that broader program: whether counterfactual dreaming improves
prospective, calibrated Theory of Mind and planning decisions under robust
pipeline checks.

Therefore the current critical path is not provider/video generation, dream
aesthetic quality, dashboard presentation, or human-facing narrative polish. The
human does not need vague GitHub commit status or prose reassurance about
progress. The useful status is operational: which gate is active, which exact
file/command/artifact is being touched, which receipts or counts exist, what is
mocked versus live, and what concrete stop condition remains.

## Research Question

Can counterfactual dreaming improve an agent's calibrated predictions and
decisions about another mind compared with ordinary memory retrieval, textual
reflection, and single-trajectory dreaming, without corrupting memory,
identity, provenance, or pipeline state?

Success must be measured by future-facing, falsifiable outcomes:

- prediction accuracy for hidden beliefs, desires, goals, knowledge, and next
  actions;
- calibration and abstention behavior;
- planning regret and information-seeking utility;
- first- and second-order Theory-of-Mind consistency;
- non-destructive belief revision after outcome reveal;
- zero evidence-class corruption;
- zero unauthorized identity mutation;
- fail-closed behavior under memory, model, tool, schema, persistence, and
  retry faults.

## Active Research Namespace

All new work must start under:

```text
skills/persona-dream/research/prospective-tom/
```

Do not alter the production Phase 01-16 media state machine to prove this
research lane. The research lane must remain text-first until the sealed
forecast, scoring, belief-revision, and reliability contracts are proven.

## Non-Goals For Current Work

- No new paid Kling/provider video run.
- No richer dream renderer as the next milestone.
- No subjective dream-aesthetic quality gate as primary evidence.
- No dashboard or visual status surface before the protocol artifacts work.
- No canonical memory write for unscored prospective or counterfactual
  hypotheses.
- No identity update from one dream, trial, or interpretation.
- No LLM judge as ground truth when deterministic simulator labels exist.

## Gate Sequence

### Gate 0 - Provenance Prerequisite

Every prospective residue must map:

```text
query receipt
-> accepted raw source ID
-> normalized residue
-> dream branch
-> ToM prediction
```

Required proof: accepted source IDs and their stable hash are present in recall
receipts, and a deterministic checker rejects unresolved or unaccepted lineage.

### Gate 1 - Controlled Social World

Build deterministic text-first social episodes with evaluator-known hidden
state and agent-visible observations only.

Required scenario families:

- information asymmetry and false belief;
- preference and desire uncertainty;
- trust, commitment, and relationship state;
- coordination and conflict.

Each episode must include hidden world state, counterpart beliefs/goals/
preferences, deterministic counterpart policy, information access by agent,
observable history, allowed next actions, actual next action, and first- plus
second-order ToM labels from simulator configuration.

### Gate 2 - ToM Distributions

Represent ToM hypotheses as probabilistic distributions, not prose labels.

Hard invariants:

- probabilities sum to one;
- all evidence references resolve;
- self and other perspectives remain separate;
- counterfactual branches are explicitly marked;
- explanations are audit-only;
- unsupported hypotheses abstain or remain pending;
- prospective hypotheses are not canonical memory before outcome scoring.

### Gate 3 - Counterfactual Dream Branching

Generate factual and `do()`-style counterfactual branches with one intervened
variable, held-fixed variables, predicted BDI distributions, predicted next
actions, expected observations, uncertainty, and evidence basis.

Conditions must be comparable under equal call/token budgets:

- M: memory only;
- R: memory plus textual reflection;
- D: one synthetic dream trajectory;
- CD: counterfactual dream branches and explicit comparison.

Oracle evidence may be used only as a diagnostic to separate memory retrieval
failure from ToM reasoning failure.

### Gate 4 - Sealed Prediction Ledger

Every prediction must be committed before outcome reveal, with hashes for the
prediction payload, model receipts, and evidence bundle. Prediction edits after
reveal are forbidden.

### Gate 5 - Scoring

Score sealed predictions with deterministic metrics:

- Brier score;
- log loss;
- expected calibration error;
- abstention risk-coverage;
- first- and second-order label accuracy;
- consistency across logically equivalent formulations;
- causal sensitivity, invariance, counterfactual discrimination, and
  false-history rate.

### Gate 6 - Action Selection

The agent must choose an action from a constrained action set and score planning
quality against deterministic simulator reward/cost rules and an oracle policy.

Allowed action vocabulary:

```text
ASK_CLARIFYING_QUESTION
WAIT
DISCLOSE_INFORMATION
OFFER_COOPERATION
SET_BOUNDARY
ACT_INDEPENDENTLY
ABSTAIN
```

### Gate 7 - Non-Destructive Belief Revision

After outcome reveal, write a prior -> prediction error -> posterior chain.
The prior remains auditable. Evidence may update a hypothesis; a hypothesis may
not rewrite evidence.

### Gate 8 - Reliability Surface

Measure:

```text
R(k, epsilon, lambda)
```

where `k` is repeated executions, `epsilon` is semantic perturbation intensity,
and `lambda` is infrastructure/fault intensity.

Permitted terminal outcomes under faults:

```text
RECOVERED_WITH_EQUIVALENT_END_STATE
BLOCKED_BEFORE_SIDE_EFFECT
QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE
```

Forbidden terminal outcome:

```text
CONTINUED_WITH_UNKNOWN_STATE
```

### Gate 9 - Causal Replay

When a trial diverges, identify the first differing receipt, replay from that
boundary, remove or replace one suspected tool return, compare state, and write
a causal failure-localization receipt.

## Current Provenance Boundary

Current evidence boundaries:

```text
Gate 0 commit: 81f51b5689914782c54a4b9c5672579bcd97d440
Gate 1 commit: 0cecce8193606522a1d56283cc240c5bddc83c2a
Gate 2 commit: 6b6b7d843f1a24a1192273a3215f6b2f795fd734
Gate 3 commit: 781bc10e51c516f11930f274e30970c42d240297
Gate 4 commit: 82a0078294cd0a29e789151a59375428ed2e5a3c
Gate 5 commit: 81dd203200bcc3786ad561cb1845230254967069
Gate 1 proof root: /tmp/persona-dream-pctom-gate1-final-postpatch-20260721T001545Z
Gate 2 proof root: /tmp/persona-dream-pctom-gate2-postrebase-20260721T003945Z
Gate 3 proof root: /tmp/persona-dream-pctom-gate3-final-20260721T004724Z
Gate 4 proof root: /tmp/persona-dream-pctom-gate4-final-20260721T010232Z
Gate 5 proof root: /tmp/persona-dream-pctom-gate5-final-20260721T011122Z
Gate 6 proof root: /tmp/persona-dream-pctom-gate6-final-20260721T011945Z
```

Gate 0 proof summary:

```text
Gate 0 positive: PASS_PCTOM_GATE0_LINEAGE
Gate 0 negatives: 4 x BLOCKED_PCTOM_GATE0_LINEAGE
Gate 0 invariant: query receipt -> accepted raw source ID -> normalized residue -> dream branch -> ToM prediction
```

Gate 1 proof summary:

```text
json_files_parsed: 29
python_files_ast_parsed: 3
Gate 0 positive: PASS_PCTOM_GATE0_LINEAGE
Gate 0 negatives: 4 x BLOCKED_PCTOM_GATE0_LINEAGE
Gate 1 build: PASS_SOCIAL_EPISODE_CORPUS_BUILT
Gate 1 committed corpus: PASS_SOCIAL_EPISODE_CORPUS
Gate 1 corpus: 12 episodes, 4 families, 12 first-order labels, 12 second-order labels
Gate 1 bad-action negative: BLOCKED_SOCIAL_EPISODE_CORPUS
git_diff_check: clean
```

Gate 2 proof summary:

```text
json_files_parsed: 38
python_files_ast_parsed: 4
Gate 2 positive: PASS_TOM_BELIEF_DISTRIBUTIONS
Gate 2 distributions: 3
Gate 2 supported hypotheses: 2
Gate 2 abstained_or_pending hypotheses: 1
Gate 2 resolved_evidence_refs: 4
Gate 2 label_matched_distributions: 2
Gate 2 negatives: 7 x BLOCKED_TOM_BELIEF_DISTRIBUTIONS
git_diff_check: clean
```

Gate 3 proof summary:

```text
json_files_parsed: 47
python_files_ast_parsed: 5
Gate 3 distribution bundle: PASS_TOM_BELIEF_DISTRIBUTIONS
Gate 3 positive: PASS_COUNTERFACTUAL_BRANCHES
Gate 3 branches: 2
Gate 3 factual_branches: 1
Gate 3 counterfactual_branches: 1
Gate 3 interventions: 1
Gate 3 resolved_source_evidence_refs: 4
Gate 3 distribution_refs: 2
Gate 3 negatives: 6 x BLOCKED_COUNTERFACTUAL_BRANCHES
git_diff_check: clean
```

Gate 4 proof summary:

```text
json_files_parsed: 57
python_files_ast_parsed: 6
matrix_commands: 32
expected_negative_failures: 25
Gate 4 positive: PASS_TOM_PREDICTION_COMMITMENTS
Gate 4 commitments: 1
Gate 4 conditions: 1
Gate 4 branch_refs: 4
Gate 4 distribution_refs: 4
Gate 4 resolved_source_evidence_refs: 4
Gate 4 hashes_checked: 3
Gate 4 forbidden_outcome_paths: 0
Gate 4 negatives: 8 x BLOCKED_TOM_PREDICTION_COMMITMENTS
git_diff_check: clean
```

Gate 5 proof summary:

```text
json_files_parsed: 65
python_files_ast_parsed: 7
matrix_commands: 40
expected_negative_failures: 31
Gate 5 commitment precheck: PASS_TOM_PREDICTION_COMMITMENTS
Gate 5 positive: PASS_TOM_SCORING_RECEIPT
Gate 5 action_scores: 1
Gate 5 belief_scores: 2
Gate 5 first_order_scores: 1
Gate 5 second_order_scores: 1
Gate 5 equivalent_formulation_checks: 1
Gate 5 counterfactual_pairs: 1
Gate 5 false_history_rate: 0.0
Gate 5 action_brier: 0.2328
Gate 5 action_log_loss: 0.4780358009429998
Gate 5 expected_calibration_error: 0.3533333333333334
Gate 5 negatives: 6 x BLOCKED_TOM_SCORING_RECEIPT
git_diff_check: clean
```

Gate 6 proof summary:

```text
json_files_parsed: 74
python_files_ast_parsed: 8
matrix_commands: 47
expected_negative_failures: 37
Gate 6 positive: PASS_TOM_ACTION_SELECTION
Gate 6 actions_considered: 7
Gate 6 policy_compliant_actions: 7
Gate 6 selected_action: ASK_CLARIFYING_QUESTION
Gate 6 oracle_action: ASK_CLARIFYING_QUESTION
Gate 6 reward_components_checked: 21
Gate 6 planning_regret: 0.0
Gate 6 realized_task_reward: 0.8
Gate 6 realized_social_cost: 0.1
Gate 6 realized_information_gain: 0.4
Gate 6 negatives: 6 x BLOCKED_TOM_ACTION_SELECTION
git_diff_check: clean
```

This is fixture-backed deterministic evidence. It does not prove live Memory
recall, Tau text execution, semantic dream quality, prediction benefit,
held-out statistical calibration, live action improvement, belief revision,
fault-surface coverage, or complete Phase 01-16 runtime execution.

## Completion Rule

The goal is not complete until an artifact-backed final report cites local
receipts proving all of the following:

1. Gate 0 provenance chain holds for every accepted prospective trial residue.
2. Gate 1 controlled social episodes provide deterministic hidden-state ground
   truth.
3. Gate 2 ToM distributions pass invariant checks and unsupported hypotheses
   fail closed.
4. Gate 3 counterfactual branches remain distinguishable from literal history.
5. Gate 4 predictions are sealed before outcomes are revealed.
6. Gate 5 scoring computes prediction, calibration, consistency, and
   counterfactual metrics from sealed predictions.
7. Gate 6 action selection is scored for reward, social cost, information gain,
   and planning regret.
8. Gate 7 belief revision preserves prior hypotheses and writes posterior
   updates non-destructively.
9. Gate 8 repeated, perturbed, and fault-injected runs either recover to an
   equivalent end state, block before side effects, or quarantine partial state.
10. Gate 9 causal replay identifies the first divergent receipt for failed or
    unstable trials.

No agent may claim final, green, complete, fixed, verified, or closed for this
research goal unless those concrete proof artifacts exist and are cited.

## Next Critical Path

Implement Gate 7: non-destructive belief revision receipts that consume the
prior sealed hypothesis, scored prediction error, and revealed evidence, then
write a prior -> error -> posterior chain while preserving the prior as
auditable history.

The next accepted artifact must be inspectable as files and receipts under the
research namespace, with positive and negative fixtures. Mocked or fixture
checks prove wiring only; any later claim about live Memory, Tau, or autonomous
execution requires separate live receipts.
