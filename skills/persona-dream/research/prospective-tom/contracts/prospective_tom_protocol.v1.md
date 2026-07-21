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
