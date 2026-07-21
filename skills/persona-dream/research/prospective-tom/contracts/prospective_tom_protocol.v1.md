# Prospective ToM Protocol v1

PCTOM-R starts as a text-first research lane. It must not alter the production
Phase 01-16 Persona Dream state machine until the research lane has mechanical
signal and fail-closed evidence.

## Gate 0 Lineage Contract

The first implemented contract is provenance-to-sealed-prediction lineage:

```text
live recall query receipt
-> accepted source id
-> normalized residue
-> dream branch
-> sealed ToM prediction commitment
```

The checker treats the chain as blocked unless every link is explicit and
hash-bound.

## Required Inputs

A protocol case directory contains:

```text
recall_receipts.json
normalized_residue.json
dream_branches.json
tom_prediction_commitment.json
```

## Invariants

- Each recall receipt has `query`, `scope`, `accepted_source_ids`, and
  `accepted_source_ids_sha256`.
- `accepted_source_ids_sha256` recomputes over canonical JSON for
  `accepted_source_ids`.
- Each normalized residue item has nonempty `scope`, `source_id`, and `text`.
- Each residue item names the recall receipt index that accepted its source id.
- Each residue `(scope, source_id)` resolves to that receipt's accepted source
  ids.
- Each dream branch resolves all residue references.
- Counterfactual branches are marked synthetic and cannot be ordinary evidence.
- Each prediction commitment is sealed before reveal by setting
  `outcome_visible` to `false`.
- The commitment's `prediction_payload_sha256` recomputes over
  `prediction_payload`.
- All prediction evidence references resolve to normalized residue.
- All prediction branch references resolve to dream branches.
- Probability distributions sum to one.

## Non-Goals For Gate 0

Gate 0 does not prove:

- model semantic quality;
- future prediction accuracy;
- hidden-world simulator correctness;
- outcome scoring;
- belief revision;
- repeated-trial reliability;
- live Tau execution;
- paid provider execution.

Those belong to later PCTOM-R gates.

## Gate 1 Social World Contract

Gate 1 creates a deterministic text-first social world. The evaluator knows the
hidden state; Embry only receives the observable history and information-access
view. Ground truth comes from simulator configuration and deterministic
counterpart policy, not from an LLM judge.

Each social episode must include:

```text
hidden_world_state
counterpart_beliefs
counterpart_goals
counterpart_preferences
counterpart_policy
information_access_by_agent
observable_history
allowed_next_actions
actual_next_action
ground_truth_tom_labels
```

The development corpus must contain 12 episodes:

```text
3 information_asymmetry_false_belief
3 preference_desire_uncertainty
3 trust_commitment_relationship
3 coordination_conflict
```

Gate 1 invariants:

- every actual next action is one of the allowed next actions;
- every actual next action matches the deterministic counterpart policy;
- each episode has at least one first-order ToM label;
- each episode has at least one second-order ToM label;
- every ToM label has `label_source: simulator_config`;
- no episode uses an LLM judge for ground truth;
- the episode list hash recomputes exactly.

Gate 1 does not prove model prediction accuracy, scoring, calibration, belief
revision, live Tau execution, or reliability under faults.

## Gate 2 ToM Distribution Contract

Gate 2 represents Theory-of-Mind hypotheses as structured probability
distributions, not prose labels. It consumes Gate 1 social episodes and a
sealed belief-distribution bundle.

Each bundle must include:

```text
episode_id
outcome_visible: false
sealed: true
canonical_memory_write: false
distributions[]
```

Each distribution must include:

```text
hypothesis_id
episode_id
perspective_order
subject
target
mental_state_type
proposition
distribution
evidence_refs
prediction_horizon
counterfactual
counterfactual_context
abstain
support_status
```

Gate 2 invariants:

- every probability distribution sums to one;
- supported hypotheses resolve evidence from agent-visible episode fields;
- hidden simulator state and ground-truth labels cannot be used as evidence;
- supported hypotheses match a first- or second-order Gate 1 label;
- unsupported hypotheses must be `abstained` or `pending` and assign
  probability 1.0 to `UNKNOWN`;
- `subject` and `target` remain separate;
- factual predictions cannot consume `synthetic_counterfactual` evidence;
- counterfactual hypotheses require explicit synthetic context;
- no bundle writes canonical memory;
- no bundle may expose the outcome before a later reveal gate.

Gate 2 does not prove prediction accuracy, calibration quality, Tau execution,
live Memory recall, outcome scoring, belief revision, or reliability under
faults.

## Gate 3 Counterfactual Branch Contract

Gate 3 represents factual and `do()`-style counterfactual branches before any
condition runner or persistence path can consume them.

Each branch bundle must include:

```text
episode_id
outcome_visible: false
canonical_memory_write: false
branches[]
```

Each branch must include:

```text
branch_id
episode_id
branch_type
synthetic
intervention
source_evidence_refs
held_fixed
predicted_bdi_distribution_refs
predicted_action_distribution
expected_observation
uncertainty
```

Gate 3 invariants:

- every bundle has at least one factual branch and one counterfactual branch;
- factual branches are not synthetic and have no intervention;
- counterfactual branches are synthetic and have exactly one intervention
  variable;
- the intervened variable is not listed as held fixed;
- intervention records are explicitly synthetic;
- branch evidence references resolve only to agent-visible episode fields;
- BDI distribution refs resolve to a sealed Gate 2 distribution bundle;
- factual branches use factual distributions;
- counterfactual branches use counterfactual distributions;
- predicted action distributions sum to one;
- predicted actions are drawn from the episode's allowed action vocabulary or
  `UNKNOWN`;
- no branch bundle writes canonical memory;
- no branch bundle exposes the outcome before a later reveal gate.

Gate 3 does not prove counterfactual causal correctness, prediction accuracy,
calibration quality, Tau execution, live Memory recall, outcome scoring, belief
revision, or reliability under faults.

## Gate 4 Sealed Prediction Ledger Contract

Gate 4 commits predictions before outcome reveal. It does not execute the
counterpart policy or score the result; it only proves that the prediction,
model receipts, and evidence bundle are immutable, hash-bound, and free of
outcome leakage at the commitment boundary.

Each commitment bundle must include:

```text
episode_id
sealed: true
outcome_visible: false
canonical_memory_write: false
commitments[]
```

Each commitment must include:

```text
prediction_id
episode_id
condition
sealed_at
outcome_visible: false
prediction_payload
prediction_payload_sha256
model_receipts
model_receipts_sha256
evidence_bundle
evidence_bundle_sha256
```

Gate 4 invariants:

- every commitment is sealed while `outcome_visible` is false;
- the prediction payload hash recomputes exactly;
- the model receipt bundle hash recomputes exactly;
- the evidence bundle hash recomputes exactly;
- evidence bundle hashes match the consumed Gate 2 distribution bundle and
  Gate 3 branch bundle;
- branch refs resolve to Gate 3 branches;
- belief distribution refs resolve to Gate 2 distributions;
- source evidence refs resolve only to agent-visible episode fields;
- prediction action distributions sum to one when present;
- hidden state, actual next action, ground-truth labels, outcome reveals, and
  scores are forbidden inside commitments;
- no canonical memory write occurs before outcome scoring;
- prediction edits after reveal are forbidden.

Gate 4 does not prove prediction accuracy, calibration quality, outcome reveal,
deterministic scoring, belief revision, Tau execution, live Memory recall, or
fault-injection reliability.

## Gate 5 Scoring Contract

Gate 5 reveals the deterministic outcome only after a sealed Gate 4 commitment
exists, then writes a scoring receipt. The scorer must recompute commitment
hashes before scoring and must reject any reveal that appears before the seal,
uses an unresolved prediction, exposes an impossible action, or treats a
synthetic counterfactual branch as literal history.

Each outcome reveal must include:

```text
schema
outcome_id
episode_id
prediction_id
revealed_at
outcome_visible: true
reveal_complete: true
canonical_memory_write: false
actual_next_action
hidden_state_labels
factual_branch_id
literal_history_branch_ids
equivalent_formulation_checks
```

Each scoring receipt must include deterministic metrics:

```text
action Brier score
action log loss
first-order ToM label scores
second-order ToM label scores
expected calibration error
risk-coverage/selective accuracy
equivalent-formulation consistency
counterfactual causal-sensitivity diagnostic
false-history rate
```

Gate 5 invariants:

- outcome reveal time is after the commitment seal time;
- the commitment payload, model receipts, and evidence bundle hashes still
  recompute before scoring;
- actual next action is in the deterministic episode action vocabulary;
- first- and second-order hidden-state labels come from simulator labels;
- Brier score and log loss are computed from sealed probability distributions;
- calibration and consistency metrics are computed deterministically;
- counterfactual branches are not counted as literal history;
- no canonical memory write occurs during reveal or scoring;
- scoring receipts do not alter the sealed prediction.

Gate 5 does not prove a prediction benefit over baselines, held-out statistical
calibration, action-selection regret, belief revision, Tau execution, live
Memory recall, or fault-injection reliability.

## Gate 6 Action Selection Contract

Gate 6 turns a scored prospective ToM prediction into a constrained action
choice. The checker consumes a PASS Gate 5 scoring receipt, the immutable
outcome reveal, and an action-selection fixture. It recomputes scoring/outcome
hashes, verifies the action vocabulary, and recomputes utility and planning
regret against a deterministic oracle policy.

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

Each action selection must include:

```text
episode_id
prediction_id
outcome_id
selected_action
scoring_receipt_sha256
outcome_reveal_sha256
action_options[]
oracle_policy
planning_regret
realized_outcome
decision_basis
canonical_memory_write: false
```

Gate 6 invariants:

- the consumed Gate 5 scoring receipt has PASS status;
- scoring receipt and outcome reveal hashes recompute exactly;
- selected action is in the constrained action vocabulary;
- selected action appears in the evaluated options;
- every option has task reward, social cost, information gain, expected
  utility, and policy-compliance fields;
- oracle policy matches the maximum-utility option;
- planning regret recomputes as oracle utility minus selected utility;
- realized task reward, social cost, and information gain are present;
- no canonical memory write occurs during action selection.

Gate 6 does not prove live model action generation, human social
appropriateness beyond deterministic simulator rules, belief revision, live
Memory recall, or fault-injection reliability.
