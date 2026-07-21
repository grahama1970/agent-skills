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

## Live Tau Gate 2-4 Bridge

The live Tau bridge exercises the same Gate 2, Gate 3, and Gate 4 contracts
with one real Tau text-reasoning call:

```text
deterministic social episode visible packet
-> Tau text reasoning receipt
-> Tau-authored ToM distribution bundle
-> Tau-authored factual/counterfactual branch bundle
-> sealed prediction commitment with Tau receipt hash-bound
-> existing Gate 2/3/4 checkers
```

Required live bridge fields:

```text
mocked: false
live: true when Tau reports live_call_performed
fixture_backed: false
deterministic_simulator_corpus_fixture_backed: true
human_content_judgment_required: false
memory_write_attempts: 0
provider_call_attempts: 0
tau_call_attempts: 1
```

The bridge must preserve the raw Tau receipt and parsed JSON. If Tau returns
malformed JSON, invalid field names, hidden outcome leakage, unresolved refs,
bad probabilities, canonical/source/identity writes, or a non-PASS Tau status,
the bridge writes `BLOCKED_LIVE_TAU_PCTOM_GATE2_4` and does not repair the model
output into a pass artifact.

This bridge proves live Tau transport plus deterministic Gate 2-4 acceptance
for one bounded text-first case. It does not prove prediction benefit,
calibration quality beyond invariant checks, outcome reveal/scoring, belief
revision, live Memory recall for the same case, real fault injection, or Phase
01-16 media runtime execution.

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

### Live-Originated Condition Action Bridge

`run_live_tau_condition_action_selection.py` is the live-originated Gate 6
bridge. It consumes a repeated live Tau condition-comparison receipt and its
hash-bound M/R/D/CD case artifacts, then writes one constrained action-selection
record per accepted case.

Bridge invariants:

- base receipt status is `PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON`;
- base receipt is `mocked: false`, `live: true`, `fixture_backed: false`;
- base receipt has at least four sealed/scored cases per M/R/D/CD condition;
- each consumed case has PASS Gate 5 scoring and a live Tau receipt in its
  predecessor chain;
- selected actions are mapped from sealed predicted counterpart actions into
  the constrained Gate 6 action vocabulary;
- oracle policy comes from deterministic simulator policy and outcome labels,
  not an LLM judge;
- every condition has at least one action decision and one reward/regret score;
- no Tau call, Memory write, provider call, canonical write, identity write, or
  source-memory write occurs in the bridge.

The bridge proves live-originated Gate 6 instrumentation. It does not prove
held-out planning benefit, longitudinal belief revision, real external service
fault injection, production retry behavior, complete Phase 01-16 execution,
paid provider execution, or semantic dream quality.

## Gate 7 - Non-Destructive Belief Revision

Gate 7 consumes the sealed prior ToM hypothesis, PASS scoring receipt, and
revealed outcome. It writes a prior -> prediction-error -> posterior revision
record while preserving the prior as auditable history.

Each belief revision must include:

```text
revision_id
episode_id
prediction_id
prior_hypothesis_id
prior_distribution
prior_distribution_sha256
prior_audit_ref
observed_outcome_id
outcome_reveal_sha256
scoring_receipt_sha256
prediction_error
surprise
posterior_distribution
posterior_distribution_sha256
update_reason
update_evidence_refs
evidence_mutations: []
supersedes_for_current_use: true
prior_remains_auditable: true
canonical_memory_write: false
identity_write: false
source_memory_write: false
```

Gate 7 invariants:

- the consumed scoring receipt has PASS status;
- the outcome reveal is complete and visible;
- the prior hypothesis resolves to the sealed Gate 2 distribution bundle;
- the prior snapshot and its hash match the sealed hypothesis exactly;
- prediction error and surprise match the scoring receipt;
- the posterior distribution is hash-bound and sums to one;
- the outcome reveal is cited as update evidence;
- no evidence, source memory, or identity record is rewritten;
- no canonical memory write occurs during belief revision.

Gate 7 does not prove live Tau belief-revision generation, longitudinal recall
after revision, live Memory recall, fault-injection reliability, semantic
quality of the posterior explanation, or provider/video execution.

### Action-Linked Revision Bridge

`run_live_tau_action_linked_revision.py` is the live-originated Gate 7 bridge
from action decisions to non-destructive belief revision. It consumes a
`PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION` receipt and its M/R/D/CD Gate 6
case artifacts, then writes one strict `tom_belief_revision.v1` record per
accepted action case.

Bridge invariants:

- base receipt status is `PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION`;
- base receipt is `mocked: false`, `live: true`, `fixture_backed: false`;
- base receipt has at least four action decisions and reward/regret scores per
  M/R/D/CD condition;
- every consumed action case has PASS Gate 6 status;
- every written revision passes the ordinary Gate 7 checker;
- action linkage is stored in the aggregate receipt/index, not inside the
  strict `tom_belief_revision.v1` object;
- sealed priors remain auditable and posterior distributions are hash-bound;
- evidence mutations, canonical writes, identity writes, and source-memory
  writes are absent;
- no Tau call, Memory write, provider call, canonical write, identity write, or
  source-memory write occurs in the bridge.

The bridge proves action-linked Gate 7 instrumentation over live-originated
artifacts. It does not prove longitudinal recall after revision, held-out
benefit, real external service fault injection, production retry behavior,
complete Phase 01-16 execution, paid provider execution, or semantic dream
quality.

### Revision Recall Bridge

`run_live_tau_revision_recall.py` is the deterministic recall/use bridge over
action-linked revisions. It consumes a
`PASS_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION` receipt, builds recall documents
from the strict revision records, and runs condition-scoped local recall queries
against those documents.

Bridge invariants:

- base receipt status is `PASS_LIVE_TAU_PCTOM_ACTION_LINKED_REVISION`;
- base receipt is `mocked: false`, `live: true`, `fixture_backed: false`;
- base receipt has 16 PASS Gate 7 revision cases and at least one prior and
  posterior action-linked revision per M/R/D/CD condition;
- recall documents distinguish sealed prior distributions from current-use
  posterior distributions;
- synthetic counterfactual branches do not appear in literal-history branch
  ids for the recalled context;
- canonical writes, identity writes, source-memory writes, provider calls, and
  Tau calls are absent;
- `live_memory_recall_performed` is explicitly false unless the Memory service
  is actually queried.

The bridge proves deterministic artifact recall over live-originated revision
artifacts. It does not prove live Memory recall after revision, held-out
benefit, real external service fault injection, production retry behavior,
complete Phase 01-16 execution, paid provider execution, or semantic dream
quality.

## Live Tau Gate 5/7 Score-Revision Bridge

The live Tau score-revision bridge consumes a previously accepted live
Tau-originated Gate 2-4 case. It must not call Tau again or edit the sealed
prediction. It reveals the deterministic simulator outcome after the sealed
commitment, runs the Gate 5 scorer, writes a Gate 7 prior -> error -> posterior
revision, and then validates the revision.

The required chain is:

```text
live Tau Gate 2-4 receipt
-> Tau-authored sealed prediction commitment
-> deterministic simulator outcome reveal
-> Gate 5 scoring receipt
-> Gate 7 belief revision receipt
```

Required bridge fields:

```text
mocked: false
live: true when the consumed Tau bridge reports a live call
live_tau_originated_commitment_consumed: true
fixture_backed: false
deterministic_simulator_corpus_fixture_backed: true
human_content_judgment_required: false
memory_write_attempts: 0
provider_call_attempts: 0
tau_call_attempts: 0
```

The bridge must write:

```text
artifacts/tom_outcome_reveal.json
artifacts/tom_belief_revision.json
receipts/tom_scoring_receipt.json
receipts/belief_revision_check_receipt.json
live_tau_score_revision_receipt.v1.json
```

Accepted status:

```text
PASS_LIVE_TAU_PCTOM_SCORE_REVISION
```

Blocked status:

```text
BLOCKED_LIVE_TAU_PCTOM_SCORE_REVISION
```

This bridge proves a live Tau-originated sealed commitment can be consumed by
deterministic reveal/scoring and non-destructive belief revision for one bounded
text-first case without Memory writes, provider calls, new Tau calls, or human
content judgment. It does not prove held-out prediction benefit, statistical
calibration over many episodes, factual second-order live Tau scoring when the
consumed bundle lacks a factual second-order hypothesis, live Memory recall for
the same scored trial, longitudinal recall after revision, real service fault
injection or causal replay, complete Phase 01-16 runtime execution, paid
provider execution, or video quality.

## Gate 8 - Reliability Surface

Gate 8 measures a local PCTOM-R analogue of:

```text
R(k, epsilon, lambda)
```

where `k` is repeated executions, `epsilon` is semantic perturbation intensity,
and `lambda` is fault intensity. The first implementation is deterministic and
fixture-backed: it checks the reliability-surface receipt contract before live
service fault injection exists.

Each reliability surface must include:

```text
surface_id
episode_id
condition
k
epsilon_values[]
lambda_values[]
trials[]
canonical_memory_write: false
identity_write: false
source_memory_write: false
```

Each trial must include:

```text
trial_id
repeat_group_id
episode_id
condition
k
epsilon
lambda
perturbations[]
faults[]
terminal_outcome
end_state_equivalence_sha256
side_effect_count
active_partial_state
unknown_state_continued: false
duplicate_active_predictions
duplicate_active_revisions
canonical_memory_write: false
identity_write: false
source_memory_write: false
```

Allowed terminal outcomes:

```text
RECOVERED_WITH_EQUIVALENT_END_STATE
BLOCKED_BEFORE_SIDE_EFFECT
QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE
```

Forbidden terminal outcome:

```text
CONTINUED_WITH_UNKNOWN_STATE
```

Gate 8 invariants:

- at least one repeat group has `k` executions;
- at least one trial uses semantic perturbation (`epsilon > 0`);
- at least one trial injects a fault (`lambda > 0`);
- recovered trials keep the same end-state equivalence hash within their repeat
  group;
- blocked trials have zero side effects;
- quarantined trials have zero side effects and no active partial state;
- unknown-state continuation is never accepted;
- retries do not duplicate active predictions or active revisions;
- no canonical memory, identity, or source-memory write occurs.

Gate 8 does not prove live Tau execution, live Memory recall, real service
fault injection, production retry behavior, statistical prediction benefit, or
Gate 9 causal replay.

## Gate 9 - Causal Replay

Gate 9 diagnoses a failed, quarantined, or divergent Gate 8 reliability trial by
replaying from the first receipt where state diverged. It asks which specific
tool return or persistence event caused downstream divergence. The first
implementation is deterministic and fixture-backed: it checks a causal replay
receipt against a Gate 8 reliability surface before production replay exists.

Each causal replay must include:

```text
replay_id
surface_id
trial_id
reliability_surface_sha256
first_divergent_receipt
replay_start_receipt_id
suspected_tool_return
comparison
localized_cause
terminal_outcome
unknown_state_continued: false
canonical_memory_write: false
identity_write: false
source_memory_write: false
```

The first divergent receipt must include:

```text
receipt_id
receipt_index
boundary
expected_state_sha256
observed_state_sha256
```

The suspected tool return must be exactly one object, not a list, and its
operation must be one of:

```text
REMOVE_TOOL_RETURN
REPLACE_TOOL_RETURN
```

Gate 9 invariants:

- the reliability surface hash recomputes exactly;
- the target trial resolves inside the Gate 8 reliability surface;
- the target trial is faulted, quarantined, blocked, or otherwise divergent;
- the first divergent receipt has different expected and observed state hashes;
- replay starts at the first divergent receipt, not a later boundary;
- exactly one suspected tool return is removed or replaced;
- factual, counterfactual, and expected end-state hashes are compared;
- the counterfactual replay must match the expected end state for a PASS;
- a causal failure-localization receipt names the cause, receipt, tool return,
  confidence, and evidence references;
- `CONTINUED_WITH_UNKNOWN_STATE` is forbidden;
- no canonical memory, identity, or source-memory write occurs.

Gate 9 does not prove live Tau execution, live Memory recall, real service fault
injection, production causal replay, statistical prediction benefit, or complete
live Phase 01-16 runtime execution.

## Live Tau Gate 8/9 Reliability Bridge

The live Tau reliability bridge consumes a previously accepted live
Tau-originated Gate 5/7 score-revision case as the reliability subject. It
constructs a bounded reliability surface over hash-bound live-originated
artifacts, injects a controlled stale-artifact boundary, validates the surface
with Gate 8, then writes and validates a Gate 9 causal replay for the stale
artifact.

The required chain is:

```text
live Tau Gate 5/7 score-revision receipt
-> current live-originated artifact manifest
-> stale or controlled-stale artifact manifest
-> Gate 8 reliability surface
-> Gate 9 causal replay
-> live reliability bridge receipt
```

Required bridge fields:

```text
mocked: false
live: true when the consumed score-revision bridge reports live
live_tau_originated_case_consumed: true
fixture_backed: false
deterministic_simulator_corpus_fixture_backed: true
controlled_fault_definition: true
human_content_judgment_required: false
memory_write_attempts: 0
provider_call_attempts: 0
tau_call_attempts: 0
```

Gate 8 must include:

```text
at least one repeat group with k >= 2
at least one semantic perturbation
at least one fault-injected trial
no CONTINUED_WITH_UNKNOWN_STATE
no canonical/source/identity writes
no duplicate active predictions
no duplicate active revisions
```

The stale-artifact trial must end in:

```text
QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE
```

Gate 9 must identify the first divergent receipt, replace or remove exactly one
suspected tool return, compare factual/counterfactual/expected end-state hashes,
and localize `STALE_ARTIFACT` without continuing unknown state or writing
canonical/source/identity records.

Accepted status:

```text
PASS_LIVE_TAU_PCTOM_RELIABILITY_BRIDGE
```

Blocked status:

```text
BLOCKED_LIVE_TAU_PCTOM_RELIABILITY_BRIDGE
```

This bridge proves bounded controlled-fault containment and causal localization
over live Tau-originated PCTOM artifacts. It does not prove external service
fault injection, production retry machinery, statistical prediction benefit,
held-out M/R/D/CD comparison, longitudinal recall after revision, complete live
Phase 01-16 runtime execution, paid provider execution, or video quality.

## Condition Comparison Instrumentation

The deterministic condition comparison runner validates the experimental
instrument before live model comparison. It builds a calibration social episode
corpus, runs M, R, D, and CD condition priors through the existing Gate 2, Gate
3, Gate 4, and Gate 5 validators, then aggregates Brier and log-loss metrics by
condition.

The required chain is:

```text
calibration social episode corpus
-> M/R/D/CD condition priors
-> Gate 2 ToM distribution bundles
-> Gate 3 factual/counterfactual branch bundles
-> Gate 4 sealed prediction commitments
-> Gate 5 deterministic outcome reveals and scoring receipts
-> condition comparison receipt
```

Required fields:

```text
mocked: false
fixture_backed: false
deterministic_simulator_corpus_fixture_backed: true
human_content_judgment_required: false
memory_write_attempts: 0
provider_call_attempts: 0
tau_call_attempts: 0 for deterministic instrumentation
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
sealed_commitments_per_condition[M/R/D/CD] >= 1
deterministic_scores_per_condition[M/R/D/CD] >= 1
```

Accepted status:

```text
PASS_PCTOM_CONDITION_COMPARISON
```

Blocked status:

```text
BLOCKED_PCTOM_CONDITION_COMPARISON
```

This runner proves the condition-comparison instrument can seal, reveal, score,
and aggregate all four condition lanes without unsupported writes or human
content judgment. A negative result is valid evidence. If CD does not beat the
strongest baseline on the preregistered primary metric, the receipt must report
that directly rather than reframe success around narrative quality or secondary
metrics.

This deterministic instrumentation does not prove live model prediction
benefit, Tau-authored condition outputs, held-out test-set benefit,
action-selection regret improvement, external service fault injection,
production retry machinery, longitudinal recall after revision, complete live
Phase 01-16 runtime execution, paid provider execution, or semantic dream
quality.

## Live Tau Condition Comparison

The live Tau condition comparison runner is the first text-first condition
execution artifact after deterministic instrumentation. It makes one sanctioned
Tau text-reasoning call per condition lane and sends Tau-authored outputs
through the same Gate 2, Gate 3, Gate 4, and Gate 5 validators.

The required chain is:

```text
calibration social episode corpus
-> live Tau call for M
-> live Tau call for R
-> live Tau call for D
-> live Tau call for CD
-> Gate 2 ToM distribution bundles
-> Gate 3 factual/counterfactual branch bundles
-> Gate 4 sealed prediction commitments with Tau receipt hashes
-> Gate 5 deterministic outcome reveals and scoring receipts
-> live Tau condition comparison receipt
```

Required fields:

```text
mocked: false
fixture_backed: false
deterministic_simulator_corpus_fixture_backed: true
human_content_judgment_required: false
conditions: M, R, D, CD
tau_call_attempts: >= 4
tau_receipts_hash_bound: true
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
sealed_commitments_per_condition[M/R/D/CD] >= 1
deterministic_scores_per_condition[M/R/D/CD] >= 1
```

Accepted status:

```text
PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON
```

Blocked status:

```text
BLOCKED_LIVE_TAU_PCTOM_CONDITION_COMPARISON
```

This runner proves only the bounded live-model condition instrumentation: Tau
authored M/R/D/CD structured outputs, accepted cases were sealed before reveal,
and deterministic scoring ran without unsupported writes or human content
judgment. A negative or mixed condition metric is valid evidence and must be
reported directly.

This live Tau comparison does not prove held-out test-set prediction benefit,
action-selection regret improvement, external service fault injection,
production retry machinery, longitudinal recall after revision, complete live
Phase 01-16 runtime execution, paid provider execution, or video quality.

## Held-Out Condition Benefit Receipt

The held-out condition-benefit runner freezes a deterministic held-out split,
runs M/R/D/CD through the same Gate 2-5 condition comparison validators, then
computes Gate 6 constrained action decisions over every scored case. It is a
deterministic research artifact, not a live Tau or Memory run.

Required chain:

```text
explicitly frozen held-out social episode corpus
-> M/R/D/CD Gate 2 ToM distribution bundles
-> M/R/D/CD Gate 3 branch bundles
-> M/R/D/CD Gate 4 sealed commitments
-> M/R/D/CD Gate 5 deterministic scores
-> M/R/D/CD Gate 6 constrained action decisions
-> held-out condition benefit receipt
```

Required fields:

```text
mocked: false
split: explicitly_frozen_heldout or sealed_test
fixture_backed: false
deterministic_simulator_corpus_fixture_backed: true
conditions: M, R, D, CD
sealed_commitments_per_condition[M/R/D/CD] >= 1
deterministic_scores_per_condition[M/R/D/CD] >= 1
action_decisions_per_condition[M/R/D/CD] >= 1
primary_metric: preregistered proper score or planning regret
strongest_baseline_condition: one of M, R, D
cd_minus_strongest_baseline: reported even if positive, zero, or negative
oracle_policy_reference: deterministic_simulator_policy.v1
llm_judge_used: false
human_content_judgment_required: false
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
```

Accepted status:

```text
PASS_PCTOM_HELDOUT_CONDITION_BENEFIT
```

Blocked status:

```text
BLOCKED_PCTOM_HELDOUT_CONDITION_BENEFIT
```

This receipt may report a positive, null, or negative CD delta. Positive
benefit on one preregistered score is not a final research success claim unless
planning benefit, calibration, belief revision, evidence-class safety, and
fault containment are also proven at the required scope.

## Live Tau Condition Reliability Bridge

The live Tau condition reliability bridge consumes a repeated live Tau
condition-comparison receipt and validates controlled Gate 8/9 reliability
properties over the produced condition artifacts. It does not make new Tau,
Memory, provider, canonical memory, identity, or source-memory calls.

The required chain is:

```text
repeated live Tau condition comparison receipt
-> condition artifact manifest
-> controlled fault manifests
-> Gate 8 reliability surface
-> Gate 9 causal replay for a divergent fault
-> live Tau condition reliability bridge receipt
```

Required fields:

```text
mocked: false
base_receipt: repeated live Tau condition comparison receipt
conditions: M, R, D, CD
fault_families: stale_artifact, missing_graph_edge, malformed_structured_output, interrupted_persistence_or_retry
terminal_outcomes subset: RECOVERED_WITH_EQUIVALENT_END_STATE, BLOCKED_BEFORE_SIDE_EFFECT, QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE
continued_with_unknown_state: 0
causal_replay_receipts: >= 1
human_content_judgment_required: false
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
```

Accepted status:

```text
PASS_LIVE_TAU_PCTOM_CONDITION_RELIABILITY_BRIDGE
```

Blocked status:

```text
BLOCKED_LIVE_TAU_PCTOM_CONDITION_RELIABILITY_BRIDGE
```

This bridge proves bounded local reliability checks over live-originated
condition artifacts: repeated and perturbed trials preserve equivalent accepted
state, controlled artifact faults are blocked or quarantined without unknown
continuation, interrupted retry has no duplicate active prediction or revision,
and one stale-artifact divergence is causally localized. It does not prove real
external service fault injection, production retry machinery, held-out
prediction benefit, action-selection regret improvement, longitudinal recall,
complete Phase 01-16 runtime execution, paid provider execution, or video
quality.

## Live Gate 0 Bridge - Memory Recall To Prospective Case

After the fixture-backed Gate 0-9 contracts exist, the first live validation
bridge exercises the existing Persona Dream live Memory recall generator and
mechanically derives a PCTOM-R Gate 0 case from the accepted live residue.

This bridge must:

- run the generator without fixtures;
- keep `write_memory` disabled;
- require the live Memory checker to return `PASS_LIVE_MEMORY_RECALL`;
- copy the live recall receipts, including `accepted_source_ids` and
  `accepted_source_ids_sha256`;
- normalize only live accepted residue with nonempty `scope`, `source_id`, and
  `text`;
- map every normalized residue item back to its accepting query receipt;
- derive factual and counterfactual branches from the accepted residue without
  human content judgment;
- create a sealed prediction commitment with `outcome_visible: false`;
- run the ordinary Gate 0 checker against the derived case;
- write a live bridge receipt that states `mocked`, `live`, `fixture_backed`,
  Memory write attempts, Tau call attempts, and provider call attempts.

Accepted status:

```text
PASS_LIVE_PCTOM_GATE0_LINEAGE
```

Blocked status:

```text
BLOCKED_LIVE_PCTOM_GATE0_LINEAGE
```

This bridge proves live recall source IDs can survive normalization into a
prospective PCTOM-R lineage case. It does not prove live Tau generation of ToM
distributions or commitments, outcome scoring, belief revision, fault-injected
live reliability, semantic memory quality, paid provider execution, or complete
live Phase 01-16 runtime execution.

## Sealed-Test Statistical-Confidence Bridge

After deterministic held-out condition-benefit evidence exists, the
statistical-confidence bridge expands the same text-first runner to a sealed
64-episode test split and computes paired CD-minus-strongest-baseline bootstrap
confidence intervals.

This bridge must:

- generate 16 deterministic episodes per scenario family;
- consume exactly 64 episodes and 256 M/R/D/CD cases;
- require M, R, D, and CD to each produce 64 sealed commitments before reveal;
- require M, R, D, and CD to each produce 64 deterministic Gate 5 scores;
- require M, R, D, and CD to each produce 64 constrained Gate 6 action
  decisions;
- compare CD against the strongest M/R/D baseline for the preregistered
  `belief_brier` proper score;
- write paired deltas and bootstrap summary artifacts with stable hashes;
- require the primary paired confidence interval upper bound to be below zero;
- report planning-regret confidence separately without treating a tied or
  crossing-zero interval as a planning benefit;
- keep human content judgment, LLM judging, Memory writes, provider calls,
  canonical writes, identity writes, and source-memory writes absent.

Accepted status:

```text
PASS_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE
```

Blocked status:

```text
BLOCKED_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE
```

Current accepted receipt:

```text
/tmp/persona-dream-sealed-test-statistical-confidence-20260721T043620Z/sealed_test_statistical_confidence_receipt.v1.json
```

This bridge proves deterministic sealed-test statistical benefit for the
preregistered belief Brier score only. It does not prove planning-regret
benefit, live Tau sealed-test execution, live Memory recall in the sealed-test
loop, real external service fault injection, production retry machinery,
complete live Phase 01-16 runtime execution, paid provider execution, video
quality, or semantic dream quality.

## Live Fault-Injection Surface Bridge

The live fault-injection surface bridge consumes the deterministic sealed-test
statistical-confidence receipt and the live Memory revision-recall receipt. It
then probes live Memory `/recall` failure modes and creates controlled local
fault manifests for model-output, tool-return, schema, persistence, and retry
boundaries.

Pipeline:

```text
sealed-test statistical-confidence receipt
+ live Memory revision-recall receipt
-> live Memory baseline/malformed/unreachable/collection probes
-> controlled model/tool/schema/persistence/retry fault manifests
-> fault trials with permitted terminal outcomes
-> causal replay receipt for memory collection visibility
-> live fault-injection surface receipt
```

Required checks:

```text
base sealed-test receipt status: PASS_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE
base live Memory receipt status: PASS_PCTOM_LIVE_MEMORY_REVISION_RECALL
fault_families_present >= 8
live_memory_fault_probes >= 3
permitted_terminal_outcomes_only: true
continued_with_unknown_state: 0
side_effect_violations: 0
causal_replay_receipts >= 1
canonical/source/identity/provider/Tau attempts: 0
```

Accepted status:

```text
PASS_PCTOM_LIVE_FAULT_INJECTION_SURFACE
```

Blocked status:

```text
BLOCKED_PCTOM_LIVE_FAULT_INJECTION_SURFACE
```

Current accepted receipt:

```text
/tmp/persona-dream-live-fault-injection-surface-20260721T044950Z/live_fault_injection_surface_receipt.v1.json
```

This bridge proves bounded live Memory fault probing plus controlled local
fault containment over hash-bound PCTOM-R predecessor receipts. It does not
prove live Tau sealed-test execution, production retry machinery inside a
deployed orchestrator, paid provider execution, video/audio quality, semantic
dream quality, or complete live Phase 01-16 runtime execution.
