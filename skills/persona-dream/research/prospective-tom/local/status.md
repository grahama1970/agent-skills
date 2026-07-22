# Status

Status: SEALED_TEST_STATISTICAL_CONFIDENCE_PRIMARY_BENEFIT

Artifact: PCTOM-R sealed-test statistical-confidence artifact over the
deterministic text-first simulator split. It runs M, R, D, and CD over 64
sealed-test episodes, checks sealed commitments before reveal, deterministic
Gate 5 scores, constrained Gate 6 action decisions, and paired bootstrap
confidence for CD against the strongest M/R/D baseline.

Sealed-test receipt:

```text
/tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/sealed_test_statistical_confidence_receipt.v1.json
```

Statistical summary:

```text
/tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/artifacts/sealed_test_statistical_summary.json
```

Paired deltas:

```text
/tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/artifacts/sealed_test_paired_deltas.json
```

Held-out condition-benefit receipt:

```text
/tmp/persona-dream-sealed-test-statistical-confidence-20260722T002935Z/sealed_test_condition_benefit/heldout_condition_benefit_receipt.v1.json
```

Inspection result:

```text
status: PASS_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE
receipt_file_sha256: sha256:25a91714d49d27a6f01c72adeb088371d675193550071fe1987be8d599f5a0fc
statistical_summary_sha256: sha256:41cddbdae7514a80273b50ebee8c5f650950fb47e4e391726428ef66903e917f
paired_delta_sha256: sha256:e5c83e1df04762d23d76cc4d6fc84fd71bf2152f250bc0302c130e9e467041d3
heldout_condition_benefit_receipt_sha256: sha256:981998abc083c7d886d19537b17d403fac0034c76a5db039a585be7b96d0256f
split: sealed_test
episodes_consumed: 64
families_consumed: 4
cases: 256
sealed_commitments_per_condition: M=64 R=64 D=64 CD=64
deterministic_scores_per_condition: M=64 R=64 D=64 CD=64
action_decisions_per_condition: M=64 R=64 D=64 CD=64
primary_metric: belief_brier
primary_baseline_condition: D
primary_cd_minus_baseline_mean: -0.07979999999999995
primary_cd_minus_baseline_95pct_ci: [-0.07979999999999995, -0.07979999999999995]
primary_benefit_with_confidence: true
planning_regret_cd_minus_baseline_mean: 0.0
planning_regret_95pct_ci: [-0.07968750000000001, 0.07968750000000001]
planning_benefit_with_confidence: false
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: false
human_content_judgment_required: false
```

What this proves:

```text
a deterministic sealed-test split has 64 episodes and all four conditions
-> each condition has 64 sealed commitments before reveal
-> each condition has 64 deterministic Gate 5 scores
-> each condition has 64 constrained Gate 6 action decisions
-> CD beats the strongest M/R/D baseline on preregistered belief Brier with a
   paired-bootstrap confidence interval below zero
-> no Tau, Memory, provider, canonical-memory, identity, source-memory, LLM
   judge, or human content judgment path is used
```

What this does not prove:

```text
live Tau sealed-test execution
live Memory recall in the sealed-test loop
planning-regret benefit because the planning-regret CI crosses zero
real external service fault injection
production retry machinery
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Immediate next step:

```text
Use this sealed-test prediction-benefit artifact as the planning-research
baseline, then either repair/extend the action-policy layer until planning
regret separates, or connect the sealed-test loop to live Tau/Memory evidence
without weakening the sealed-before-reveal and zero-write invariants.
```

Prior status:

Status: VISIBLE_PRESSURE_GATE6_PLANNING_BENEFIT_DIAGNOSTIC

Artifact: PCTOM-R Gate 6 planning-benefit diagnostic over the supplied
visible-pressure suppression and exposure/contrast artifacts. The diagnostic
consumes the prior rule-reliability receipt and row artifacts, recomputes
hashes, computes planning-regret deltas, and writes a scoped receipt without
new Tau, Memory, provider, canonical, identity, or source-memory writes.

Diagnostic receipt:

```text
/tmp/persona-dream-visible-pressure-planning-benefit-20260722T002555Z/cooperation_visible_pressure_planning_benefit_diagnostic_receipt.v1.json
```

Diagnostic artifact:

```text
/tmp/persona-dream-visible-pressure-planning-benefit-20260722T002555Z/artifacts/cooperation_visible_pressure_planning_benefit_diagnostic.json
```

Inspection result:

```text
status: PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_PLANNING_BENEFIT_DIAGNOSTIC
receipt_sha256: sha256:f0a79d8fd1aee2f84062b1d11e7c00aa79265fa4daaa6714a6bfc24302b173f4
diagnostic_sha256: sha256:256fc4a12a4a0b47be808531fa982fa276bc5eaa99ed37b02c56632c4daacd90
rule_reliability_receipt_sha256: sha256:b97ccc1e42084971f9d1611e545f972fd76cb676023ac98c8f8fd885a08d6fb2
suppression_rows: 4
exposure_rows: 8
combined_rows: 12
suppression_action_changes: 4
exposure_action_changes: 0
suppression_mean_improvement_vs_original: 0.6000000000000001
suppression_95pct_bootstrap_ci: [0.6000000000000001, 0.6000000000000001]
exposure_mean_improvement_vs_original: 0.0
exposure_95pct_bootstrap_ci: [0.0, 0.0]
combined_mean_improvement_vs_original: 0.20000000000000004
combined_95pct_bootstrap_ci: [0.05000000000000001, 0.3500000000000001]
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: false
live_source_artifacts_consumed: true
```

What this proves:

```text
the supplied visible-pressure suppression rows show slice-local planning-regret
benefit with bootstrap confidence
-> exposure/contrast rows show no action-change regression
-> combined supplied visible-pressure artifacts show positive slice-local
   planning-regret improvement
-> source hashes are rechecked and no new Tau, Memory, provider, canonical,
   identity, or source-memory writes are made
```

What this does not prove:

```text
broad held-out PCTOM-R planning benefit
statistical generalization beyond the supplied visible-pressure artifacts
live service fault injection
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Immediate next step:

```text
Broaden beyond the supplied visible-pressure slice with held-out sealed
cooperation episodes, or extend the same planning-benefit diagnostic to another
fault/perturbation family before making any broad PCTOM-R benefit claim.
```

Prior status:

Status: VISIBLE_PRESSURE_GATE9_CAUSAL_REPLAY_LOCALIZED

Artifact: PCTOM-R Gate 9 causal replay for one visible-pressure Gate 8 fault
trial. The replay targets an oracle/hidden-field leak in pre-outcome rule input
validation, replaces exactly one suspected local artifact/tool return, and
checks the replay with the existing `run-causal-replay` validator.

Causal replay checker receipt:

```text
/tmp/persona-dream-visible-pressure-causal-replay-20260722T001823Z/cooperation_visible_pressure_causal_replay_check_receipt.v1.json
```

Replay artifact:

```text
/tmp/persona-dream-visible-pressure-causal-replay-20260722T001823Z/artifacts/cooperation_visible_pressure_causal_replay.v1.json
```

Builder receipt:

```text
/tmp/persona-dream-visible-pressure-causal-replay-20260722T001823Z/cooperation_visible_pressure_causal_replay_build_receipt.v1.json
```

Inspection result:

```text
builder_status: PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_CAUSAL_REPLAY_BUILT
builder_receipt_sha256: sha256:798bfdc9dfba445becfe4038bafeccbbe02c6bc5a94417719302ae712b6f5e81
replay_sha256: sha256:eee437412b0e40e87d5b072bc1a2457f119a4f753f438196ee755a292b8bbaf9
causal_replay_checker_status: PASS_TOM_CAUSAL_REPLAY
target_trial_id: visible-pressure-fault-oracle-leak-001
target_terminal_outcome: QUARANTINED_WITH_NO_ACTIVE_PARTIAL_STATE
first_divergent_receipt_id: visible-pressure-receipt-006-validate-pre-outcome-rule-inputs
suspected_tool_return: visible-pressure-tool-return-oracle-leak-001
localized_cause_type: PRE_OUTCOME_ORACLE_OR_HIDDEN_FIELD_LEAK
causal_confidence: 1.0
target_trials: 1
first_divergent_receipts: 1
suspected_tool_returns: 1
state_comparisons: 1
localized_causes: 1
forbidden_terminal_outcomes: 0
forbidden_write_attempts: 0
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
causal_checker_fixture_backed: true
```

What this proves:

```text
one visible-pressure Gate 8 fault trial has a Gate 9 causal replay
-> the target trial is resolved and faulted/divergent
-> the first divergent receipt is identified
-> replay starts at that first divergent receipt
-> exactly one suspected local artifact/tool return is replaced
-> factual, counterfactual, and expected end-state hashes are compared
-> the counterfactual replay returns to expected state
-> the localized cause is a pre-outcome oracle/hidden-field leak
-> no unknown-state continuation or canonical/identity/source writes occur
```

What this does not prove:

```text
live Tau execution
live Memory recall
real service fault injection
production causal replay
statistical prediction benefit
complete PCTOM-R reliability across every boundary
complete live Phase 01-16 runtime execution
```

Immediate next step:

```text
Either extend causal replay to another visible-pressure fault family, or move
back up the PCTOM-R stack to broaden held-out sealed cooperation episodes so
prediction/planning benefit has more than this controlled reliability slice.
```

Prior status:

Status: VISIBLE_PRESSURE_GATE8_SURFACE_CHECKED

Artifact: standard PCTOM-R Gate 8 reliability surface built from the
visible-pressure rule reliability receipt and checked by the existing
`run-reliability-surface` validator. This is a controlled surface over
live-originated source artifacts. It does not make new Tau, Memory, provider,
VLM, or LLM-judge calls.

Surface checker receipt:

```text
/tmp/persona-dream-visible-pressure-reliability-surface-20260722T001404Z/cooperation_visible_pressure_reliability_surface_check_receipt.v1.json
```

Surface artifact:

```text
/tmp/persona-dream-visible-pressure-reliability-surface-20260722T001404Z/artifacts/cooperation_visible_pressure_reliability_surface.v1.json
```

Builder receipt:

```text
/tmp/persona-dream-visible-pressure-reliability-surface-20260722T001404Z/cooperation_visible_pressure_reliability_surface_build_receipt.v1.json
```

Inspection result:

```text
builder_status: PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_RELIABILITY_SURFACE_BUILT
builder_receipt_sha256: sha256:224a31ebd5ff7b9fe7f5308a6ef03b4f89e3ab38e7bef44a6486f0014b5494af
surface_checker_status: PASS_TOM_RELIABILITY_SURFACE
reliability_surface_sha256: sha256:33fc7a18c913fd6b8818331b8bde8261ea94469e8419d6f78be61ce2b8247909
k_total: 3
epsilon_values: [0.0, 0.25, 0.5]
lambda_values: [0.0, 0.3, 0.7]
trials: 12
recovered: 7
blocked: 3
quarantined: 2
perturbed_trials: 3
fault_injected_trials: 6
forbidden_terminal_outcomes: 0
side_effect_violations: 0
pass_k: 1.0
fault_containment_rate: 1.0
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
surface_checker_fixture_backed: true
builder_live_source_artifacts_consumed: true
```

What this proves:

```text
the visible-pressure reliability evidence now has a standard Gate 8 surface
-> repeated execution is represented with k=3
-> semantic perturbations preserve equivalent accepted end state
-> controlled fault trials terminate only as recovered-equivalent,
   blocked-before-side-effect, or quarantined-no-active-partial-state
-> no trial continues with unknown state
-> blocked/quarantined trials have zero accepted side effects
-> retry fault trials create no duplicate active predictions or revisions
-> canonical memory, identity, and source-memory writes are absent
```

What this does not prove:

```text
new live Tau execution
new live Memory recall
real service fault injection
production retry behavior
statistical prediction benefit
Gate 9 causal replay
semantic dream quality
paid provider execution
complete PCTOM-R reliability across every boundary
```

Immediate next step:

```text
Add Gate 9 causal replay over one visible-pressure fault/divergence trial, or
extend the surface to a live Memory/service fault family if local services are
available.
```

Prior status:

Status: VISIBLE_PRESSURE_RULE_RELIABILITY_NEGATIVES_FAIL_CLOSED

Artifact: deterministic PCTOM-R visible-pressure cooperation rule reliability
checker over the two supplied live Tau visible-pressure replays. This checker
does not call Tau, Memory, providers, VLMs, or an LLM judge. It recomputes
source hashes, checks the row artifacts, and mutates copies of the source
state to ensure key boundary failures fail closed.

Current receipt:

```text
/tmp/persona-dream-cooperation-visible-pressure-rule-reliability-20260722T000807Z/cooperation_visible_pressure_rule_reliability_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:b97ccc1e42084971f9d1611e545f972fd76cb676023ac98c8f8fd885a08d6fb2
```

Inspection result:

```text
status: PASS_PCTOM_COOPERATION_VISIBLE_PRESSURE_RULE_RELIABILITY
conclusion: VISIBLE_PRESSURE_RULE_RELIABILITY_ESTABLISHED_FOR_SUPPLIED_LIVE_REPLAYS
suppression.rows: 4
suppression.cd_original_actions: {OFFER_COOPERATION: 4}
suppression.cd_intervened_actions: {ASK_CLARIFYING_QUESTION: 4}
suppression.changed_rows: 4
suppression.visible_pressure_input_rows: 4
exposure.rows: 8
exposure.keep_rows: 4
exposure.avoid_rows: 4
exposure.keep_intervened_actions: {OFFER_COOPERATION: 4}
exposure.avoid_intervened_actions: {DISCLOSE_INFORMATION: 3, WAIT: 1}
negative_mutation_count: 8
negative_mutation_fail_closed_count: 8
source_tau_calls_consumed: 48
tau_call_attempts: 0
tau_live_call_performed: 0
live_tau_reexecuted_by_this_command: false
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
fixture_backed: false
llm_judge_used: false
human_content_judgment_required: false
errors: []
audit_sha256: sha256:6ba2d92cec35f4b242e9da5478e4a1908217a62c582c6b37c68b7376567b838a
source_digest_sha256: sha256:7a98bbe62d37b01c72b2d31467765430864064f9c1ba6637bd80bafdf0e0920d
negative_mutations_sha256: sha256:4fbe3c092655d7a7e67a3b6252543ebba0c641be104c3353e914050bfed327c5
```

Negative mutations that failed closed:

```text
suppression_status_not_pass
suppression_missing_suppression_row_count
suppression_unsuppressed_action_regression
pre_outcome_oracle_leak
visible_pressure_missing
exposure_keep_offer_regression
exposure_avoid_offer_regression
unsupported_memory_write_attempt
```

What this proves:

```text
the supplied live Tau unsafe-offer-pressure lure replay hash-binds four
visible-pressure unsafe OFFER_COOPERATION candidates
-> the visible-pressure rule changed all four CD actions to
   ASK_CLARIFYING_QUESTION using pre-outcome rule inputs
-> the supplied live Tau exposure/contrast replay preserved four
   keep-cooperation OFFER_COOPERATION rows
-> the exposure/contrast replay created zero avoid/unsafe OFFER_COOPERATION rows
-> deterministic stale, missing, leaked, regressed, and unsupported-write
   mutations failed closed
-> the checker reexecuted zero Tau calls and made zero unsupported writes
```

What this does not prove:

```text
broad held-out PCTOM-R planning benefit
confidence-bounded CD planning benefit
complete R(k, epsilon, lambda) reliability surface
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Immediate next step:

```text
Extend this from a supplied-artifact reliability check into a broader
perturbation/fault replay family that includes visible-pressure rows, or run a
sealed held-out cooperation slice with visible-pressure cases before any
feature-split or planning-benefit claim.
```

Prior status:

Status: UNSAFE_OFFER_LURE_VISIBLE_PRESSURE_SUPPRESSION_EXERCISED

Artifact: PCTOM-R live Tau unsafe-offer lure visible-pressure rule replay. This
uses the same source live Tau lure artifacts that exposed unsafe
`OFFER_COOPERATION`, but replays the action rule with a pre-outcome visible
cooperation-pressure fallback. All four CD unsafe offers are changed to
`ASK_CLARIFYING_QUESTION`, and the wrapper no longer accepts an unsuppressed
unsafe-offer state for this slice.

Current receipt:

```text
/tmp/persona-dream-live-tau-cooperation-unsafe-offer-pressure-lure-visible-rule-20260721T235504Z/live_tau_cooperation_unsafe_offer_pressure_lure_visible_rule_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:6bd8774995b7ddadb84bcddb3753149e8c315471e6ffed9bfd21522b1ee8684d
```

File SHA-256:

```text
9741eeb4ff4a8dbafd5ad6a2f8e21e35127b49d447aabdc27603393db52553a8
```

Inspection result:

```text
status: PASS_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE
pressure_mode: lure
slice_conclusion: UNSAFE_OFFER_PRESSURE_SLICE_SUPPRESSION_EXERCISED
unsafe_offer_pressure_episodes: 4
lure_rows: 4
unsafe_offer_pressure_rows: 4
visible_offer_affordance_rows: 4
actual_avoid_or_disclose_rows: 4
cases: 16
action_cases: 16
rows: 4
cd_unsafe_offer_candidates: 4
cd_unsafe_offer_suppression_rows: 4
cd_original_actions: {OFFER_COOPERATION: 4}
cd_intervened_actions: {ASK_CLARIFYING_QUESTION: 4}
cd_action_change_count: 4
planning_benefit_with_confidence: false
errors: []
tau_call_attempts: 16
tau_live_call_performed: 16
live_tau_reexecuted_by_this_command: false
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
fixture_backed: false
deterministic_simulator_corpus: true
llm_judge_used: false
human_content_judgment_required: false
rows_sha256: sha256:f4764d9d9bab0b6548e009fa52d062fe84a4c04b869c2dc8d7b8c5eb11ee46c4
summary_sha256: sha256:7ad6eac64f781bff6ff3c2f3928abbb82ca9af8b07cd07df936fcc869af0c278
```

What this proves:

```text
the stronger non-oracle lure corpus can expose unsafe CD OFFER_COOPERATION
candidates
-> all analyzed rows were unsafe-offer-pressure lure rows
-> all analyzed rows exposed OFFER_COOPERATION as a visible affordance
-> all deterministic outcomes were wait/disclose outcomes
-> CD selected OFFER_COOPERATION on all four rows
-> the visible-pressure fallback changed all four CD actions to
   ASK_CLARIFYING_QUESTION
-> each changed CD row has uses_outcome_or_oracle:false and uses only the
   selected counterpart action/probability, threshold, original action, and
   visible cooperation-pressure flag as rule inputs
-> source live Tau receipts were reused without new Tau calls
-> no Memory/provider/canonical/identity/source-memory writes occurred
```

What this does not prove:

```text
a replacement cooperation feature split
confidence-bounded CD planning benefit
broad held-out planning benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Broader replay check:

```text
/tmp/persona-dream-live-tau-cooperation-exposure-contrast-visible-rule-20260721T235747Z/live_tau_cooperation_exposure_contrast_visible_rule_receipt.v1.json
```

```text
status: PASS_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_CONTRAST_SLICE
slice_conclusion: EXPOSURE_CONTRAST_SLICE_PARTIAL_CD_OFFER_EXPOSURE
rows: 8
keep_cooperation_positive_rows: 4
avoid_or_unsafe_cooperation_contrast_rows: 4
cd_offer_keep_candidates: 4
cd_offer_avoid_or_unsafe_candidates: 0
cd_action_change_count: 0
live_tau_reexecuted_by_this_command: false
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
receipt_sha256: sha256:29186622bbea0f5acea1d53c361f31ce1f0650353284495b62f290074a194340
rows_sha256: sha256:296ba3e151c1a38fc31b2a48a19159edd7faceefe8dd2a6bae397b6fe83f36b4
summary_sha256: sha256:6ca2e0a3c72a6675f096ebbd8f567cefc84e84965bbb908898a5b90232312702
```

This broader replay shows the visible-pressure fallback did not alter the
existing exposure/contrast class separation: keep rows still expose CD
`OFFER_COOPERATION`, avoid/unsafe rows still expose zero CD offers, and no
rule action changes occur on that replay.

Immediate next step:

```text
Run a sealed held-out cooperation slice or a larger perturbation/fault replay
that includes visible-pressure rows before any replacement feature-split or
planning-benefit claim.
```

Prior artifact: PCTOM-R live Tau unsafe-offer lure fail-closed gate. This
recorded the same live Tau lure source artifacts before the visible-pressure
fallback was added.

Prior receipt:

```text
/tmp/persona-dream-live-tau-cooperation-unsafe-offer-pressure-lure-failclosed-20260721T234715Z/live_tau_cooperation_unsafe_offer_pressure_lure_failclosed_receipt.v1.json
```

Prior inspection result:

```text
status: BLOCKED_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE
slice_conclusion: UNSAFE_OFFER_PRESSURE_SLICE_UNSUPPRESSED_CD_OFFER_EXPOSURE
cd_unsafe_offer_candidates: 4
cd_unsafe_offer_suppression_rows: 0
cd_original_actions: {OFFER_COOPERATION: 4}
cd_intervened_actions: {OFFER_COOPERATION: 4}
errors:
  check_failed:unsafe_offer_pressure_gate_fail_closed:False
  unsafe_offer_pressure_unsuppressed_cd_offer_exposure:candidates=4:suppressed=0
receipt_sha256: sha256:fc8d51f574c8cf7ddd41a8ef564028ffa29f0aaca67c9f1f83c464c40a498c65
file_sha256: 04bbc2618e2ee33eadfcb0a76f6263ef6042bf853e897bfcb3d9c4df9b96f688
```

Prior artifact: PCTOM-R cooperation unsafe-offer lure instrument. This created
the stronger deterministic offline instrument used by the live gate above.

Prior receipt:

```text
/tmp/persona-dream-cooperation-unsafe-offer-lure-instrument-20260721T234249Z/cooperation_unsafe_offer_pressure_lure_instrument_receipt.v1.json
```

Prior inspection result:

```text
status: PASS_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_INSTRUMENT
pressure_mode: lure
episodes: 4
variant_min: 49
variant_max: 52
lure_rows: 4
unsafe_offer_pressure_rows: 4
offer_cooperation_affordance_rows: 4
visible_offer_pressure_rows: 4
avoid_or_disclose_actual_rows: 4
negative_mutations: 7
negative_mutations_failed_closed: 7
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: false
fixture_backed: false
llm_judge_used: false
human_content_judgment_required: false
receipt_sha256: sha256:c370fdca6996f90eddc8e23f4a1379f7eff0e4e63a0b8938a471dd19fc7530b6
file_sha256: 4f49ad02ca546a235cf25462d1f5ae2e32b6041d3d1b32fcd68e805508cf47cb
```

Prior artifact: PCTOM-R deterministic unsafe-offer no-exposure diagnostic over the
live Tau unsafe-offer-pressure slice. This records the live result as a
no-exposure/null boundary: all four rows were unsafe-offer-pressure rows with
visible `OFFER_COOPERATION` affordance, but CD selected `WAIT` or
`DISCLOSE_INFORMATION` on every row. Unsafe-offer suppression, replacement
feature-split acceptance, and broad planning-benefit claims remain blocked.

Prior receipt:

```text
/tmp/persona-dream-cooperation-unsafe-offer-no-exposure-diagnostic-20260721T233441Z/cooperation_unsafe_offer_no_exposure_diagnostic_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:e72b4cd093b78656b94b8c0b783cf384bb8ec2340d17f20f5414bd36b9a7e83f
```

File SHA-256:

```text
f52aff81bd47883a81533a5cebad7672919f5d2656bff980eb834b131cf6ead2
```

Inspection result:

```text
status: PASS_PCTOM_COOPERATION_UNSAFE_OFFER_NO_EXPOSURE_DIAGNOSTIC
diagnostic_conclusion: UNSAFE_OFFER_NO_EXPOSURE_CONFIRMED
unsafe_offer_pressure_rows: 4
visible_offer_affordance_rows: 4
actual_avoid_or_disclose_rows: 4
rows: 4
cd_unsafe_offer_candidates: 0
cd_unsafe_offer_suppression_rows: 0
cd_original_action_counts: {DISCLOSE_INFORMATION: 2, WAIT: 2}
cd_intervened_action_counts: {DISCLOSE_INFORMATION: 2, WAIT: 2}
diagnostic_label_counts: {CD_AVOIDED_UNSAFE_OFFER_PRESSURE: 4}
mean_kai_offers_cooperation_probability: 0.1125
negative_mutations: 5
negative_mutations_failed_closed: 5
unsafe_offer_suppression_exercised: false
feature_split_acceptance_allowed: false
replacement_policy_claimed: false
broad_planning_benefit_claimed: false
tau_call_attempts: 0
tau_live_call_performed: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
fixture_backed: false
deterministic_simulator_corpus: true
llm_judge_used: false
human_content_judgment_required: false
planning_benefit_with_confidence: false
source_receipt_sha256: sha256:f3b3d34603b997c527f7369789ec1e17d91adfc6fb5bfe82266b889c9f8b96ee
rows_sha256: sha256:f5ce4f4fa529d7a87cca66999aa540112fa4afac8e2892bb5dd4499783fe0589
summary_sha256: sha256:2b6bd5d08de21ab0499d2fc7a43ff8e20b7e27bc538d34a56fcb2c9985dc60f7
```

What this proves:

```text
the supplied live unsafe-offer-pressure slice produced no CD unsafe
OFFER_COOPERATION exposure
-> all analyzed rows were unsafe-offer-pressure rows
-> all analyzed rows exposed OFFER_COOPERATION as a visible affordance
-> all deterministic outcomes were wait/disclose outcomes
-> CD selected WAIT on two rows and DISCLOSE_INFORMATION on two rows
-> no oracle or outcome inputs were present in the pre-outcome rule fields
-> source receipt, row artifact, and summary artifact hashes match
-> five negative mutations failed closed:
   source_status_not_pass
   cd_unsafe_offer_injected
   pre_outcome_oracle_leak
   missing_unsafe_offer_pressure
   unsupported_write_attempt
-> unsafe-offer suppression remains unexercised
```

What this does not prove:

```text
unsafe offer suppression was exercised
a replacement cooperation policy
confidence-bounded CD planning benefit
why Tau/CD preferred WAIT or DISCLOSE_INFORMATION beyond recorded structured
distributions
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Immediate next step:

```text
Either accept this as the current live no-exposure/null finding for unsafe
offer pressure, or create a stronger non-oracle unsafe-pressure instrument
that can expose unsafe CD OFFER_COOPERATION candidates before testing a
suppression rule.
```

Prior artifact: PCTOM-R live Tau cooperation unsafe-offer-pressure slice. The
deterministic unsafe-offer-pressure corpus was consumed by live Tau M/R/D/CD
condition comparison and Gate 6 action scoring.

Prior receipt:

```text
/tmp/persona-dream-live-tau-cooperation-unsafe-offer-pressure-slice-20260721T232423Z/live_tau_cooperation_unsafe_offer_pressure_slice_receipt.v1.json
```

Prior receipt SHA-256:

```text
sha256:aeb0b689973bed7a6a0fd4f55d853958d5152e718c60e2a8205d9f7bfe54ba3d
```

Prior file SHA-256:

```text
f3b3d34603b997c527f7369789ec1e17d91adfc6fb5bfe82266b889c9f8b96ee
```

Prior inspection result:

```text
status: PASS_LIVE_TAU_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_SLICE
slice_conclusion: UNSAFE_OFFER_PRESSURE_SLICE_NO_CD_OFFER_EXPOSURE
unsafe_offer_pressure_episodes: 4
variant_min: 45
variant_max: 48
unsafe_offer_pressure_rows: 4
visible_offer_affordance_rows: 4
actual_avoid_or_disclose_rows: 4
cases: 16
action_cases: 16
rows: 4
cd_unsafe_offer_candidates: 0
cd_unsafe_offer_suppression_rows: 0
cd_action_change_count: 0
tau_call_attempts: 16
tau_live_call_performed: 16
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
fixture_backed: false
deterministic_simulator_corpus: true
llm_judge_used: false
human_content_judgment_required: false
planning_benefit_with_confidence: false
condition_receipt_sha256: sha256:4e00442d623385463375f87e50cf95344e9ffad0745399c463c0a30c1f9b8774
action_receipt_sha256: sha256:3238c7c310a2ba3259d6a060f7fb5ad8ba871bfc9f37abd4a4ca6657de6d71d5
rows_sha256: sha256:f5ce4f4fa529d7a87cca66999aa540112fa4afac8e2892bb5dd4499783fe0589
summary_sha256: sha256:2b6bd5d08de21ab0499d2fc7a43ff8e20b7e27bc538d34a56fcb2c9985dc60f7
```

Prior artifact: PCTOM-R cooperation unsafe-offer-pressure instrument. This is
a deterministic offline simulator corpus that creates four avoid/unsafe rows
where `OFFER_COOPERATION` is visibly available and socially tempting, while
the hidden deterministic policy makes cooperation unsafe or suboptimal.

Prior receipt:

```text
/tmp/persona-dream-cooperation-unsafe-offer-pressure-instrument-20260721T231718Z/cooperation_unsafe_offer_pressure_instrument_receipt.v1.json
```

Prior receipt SHA-256:

```text
sha256:97b3675285cf5845a4b93f6f99893219527138a811d1c43e0bb400e49444b0f7
```

Prior file SHA-256:

```text
664eee7fdc592dfeb72cbfd15a98035943e2ac71011d2685e8bd9d5533ff8298
```

Prior inspection result:

```text
status: PASS_PCTOM_COOPERATION_UNSAFE_OFFER_PRESSURE_INSTRUMENT
instrument_conclusion: UNSAFE_OFFER_PRESSURE_INSTRUMENT_READY_FOR_LIVE_TAU
episodes: 4
variant_min: 45
variant_max: 48
unsafe_offer_pressure_rows: 4
offer_cooperation_affordance_rows: 4
visible_offer_pressure_rows: 4
avoid_or_disclose_actual_rows: 4
negative_mutations: 6
negative_mutations_failed_closed: 6
visible_packets_sha256: sha256:af047337b05e83945791cc93718d3ff3f23c1c445d063bed9ccc17c549e13b33
corpus_file_sha256: sha256:fca0d06bd6a0a79f26c5cf79da4957f4532efabe258c35e95fc786769e358c90
visible_packet_file_sha256: sha256:dbba4f701b84646c5d28dc842dda020e5dcb2a49482c62242636a001d45077db
tau_call_attempts: 0
tau_live_call_performed: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: false
fixture_backed: false
deterministic_simulator_corpus: true
llm_judge_used: false
human_content_judgment_required: false
```

Prior artifact: PCTOM-R cooperation class-separated exposure audit over a live
Tau exposure/contrast slice. The live slice produced the desired
class-separated behavior, but the feature-split acceptance gate remains
blocked because no unsafe `OFFER_COOPERATION` suppression candidate was
exercised.

Prior receipt:

```text
/tmp/persona-dream-cooperation-class-separated-exposure-audit-20260721T230709Z/cooperation_class_separated_exposure_audit_receipt.v1.json
```

Prior receipt SHA-256:

```text
sha256:e2db88050fe44f518b483be27c87c879d7c5ddf7b9158c9cd31e681af32d8785
```

Prior file SHA-256:

```text
23d6e87fc5c5d301e3174debcc1265854745aad70a773fd8ee687bb72f424a09
```

Prior inspection result:

```text
status: PASS_PCTOM_COOPERATION_CLASS_SEPARATED_EXPOSURE_AUDIT
conclusion: CD_CLASS_SEPARATED_COOPERATION_OBSERVED_FEATURE_SPLIT_STILL_BLOCKED
class_separated_cd_discrimination_observed: true
unsafe_offer_suppression_exercised: false
feature_split_acceptance_allowed: false
missing_prerequisites:
  missing_unsafe_offer_suppression_candidate
rows: 8
keep_rows: 4
avoid_or_unsafe_rows: 4
keep_offer_rows: 4
avoid_offer_rows: 0
keep_counterpart_offer_rows: 4
avoid_counterpart_offer_rows: 0
threshold_action_change_rows: 0
negative_checks_failed_closed: true
tau_call_attempts: 0
tau_live_call_performed: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
fixture_backed: false
deterministic_simulator_corpus: true
llm_judge_used: false
human_content_judgment_required: false
```

Prior proof summary:

```text
the live Tau exposure/contrast slice contains class-separated CD cooperation
behavior
-> CD selected OFFER_COOPERATION on keep-cooperation rows
-> CD avoided OFFER_COOPERATION on avoid/unsafe rows
-> sealed pre-outcome rule inputs did not leak oracle/outcome fields
-> replacement feature-split acceptance remains blocked because there is no
   unsafe OFFER_COOPERATION suppression candidate
```

Input live slice receipt:

```text
/tmp/persona-dream-live-tau-cooperation-exposure-contrast-slice-20260721T225448Z/live_tau_cooperation_exposure_contrast_slice_receipt.v1.json
```

Input live slice summary:

The deterministic exposure/contrast corpus now runs through live Tau M/R/D/CD
condition comparison and Gate 6 action scoring. Every visible pre-outcome
packet exposes `OFFER_COOPERATION` as a non-oracle agent action affordance
while hidden simulator state retains both safe/keep-cooperation and
unsafe/avoid-cooperation contrast rows.

Input live slice receipt:

```text
/tmp/persona-dream-live-tau-cooperation-exposure-contrast-slice-20260721T225448Z/live_tau_cooperation_exposure_contrast_slice_receipt.v1.json
```

Input live slice receipt SHA-256:

```text
sha256:b125d4cfa51ec3d99a5472bc14fc1c6b087065d574cf8724f0fbf328f1f213e6
```

Input live slice file SHA-256:

```text
4370d916057d6b097f056847e3ca30b0f1abee197ff902823636c0f14508453f
```

Prior artifact: PCTOM-R live Tau cooperation exposure/contrast slice.
The deterministic exposure/contrast corpus now runs through live Tau M/R/D/CD
condition comparison and Gate 6 action scoring. Every visible pre-outcome
packet exposes `OFFER_COOPERATION` as a non-oracle agent action affordance
while hidden simulator state retains both safe/keep-cooperation and
unsafe/avoid-cooperation contrast rows.

Current receipt:

```text
/tmp/persona-dream-live-tau-cooperation-exposure-contrast-slice-20260721T225448Z/live_tau_cooperation_exposure_contrast_slice_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:b125d4cfa51ec3d99a5472bc14fc1c6b087065d574cf8724f0fbf328f1f213e6
```

File SHA-256:

```text
4370d916057d6b097f056847e3ca30b0f1abee197ff902823636c0f14508453f
```

Inspection result:

```text
status: PASS_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_CONTRAST_SLICE
slice_conclusion: EXPOSURE_CONTRAST_SLICE_PARTIAL_CD_OFFER_EXPOSURE
exposure_contrast_episodes: 8
variant_min: 37
variant_max: 44
offer_cooperation_affordance_rows: 8
keep_cooperation_positive_rows: 4
avoid_or_unsafe_cooperation_contrast_rows: 4
cases: 32
action_cases: 32
rows: 8
cd_offer_cooperation_candidates: 4
cd_offer_keep_candidates: 4
cd_offer_avoid_or_unsafe_candidates: 0
cd_low_confidence_cooperation_interventions: 0
cd_action_change_count: 0
tau_call_attempts: 32
tau_live_call_performed: 32
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
fixture_backed: false
deterministic_simulator_corpus: true
llm_judge_used: false
human_content_judgment_required: false
planning_benefit_with_confidence: false
```

What this proves:

```text
the deterministic cooperation exposure/contrast corpus was consumed by live
Tau M/R/D/CD condition comparison
-> 32 live Tau cases completed
-> prediction commitments were sealed before deterministic outcome reveal
-> 32 Gate 6 action decisions were scored
-> all eight visible packets exposed OFFER_COOPERATION before outcome reveal
-> CD selected OFFER_COOPERATION on all four keep-cooperation rows
-> CD selected zero OFFER_COOPERATION actions on all four avoid/unsafe rows
-> the pre-outcome threshold rule used sealed prediction/action fields and no
   oracle/outcome inputs
-> zero unsupported writes occurred
```

What this does not prove:

```text
a replacement cooperation feature split is valid
broad held-out planning benefit
confidence-bounded CD planning benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
that the cooperation threshold is optimal
```

Important finding:

The new combined exposure/contrast instrument changed the live result from
zero cooperation exposure to partial, class-separated exposure. CD now selects
`OFFER_COOPERATION` in all four keep-cooperation rows and avoids it in all four
avoid/unsafe rows. That is operationally useful signal, but it still does not
establish a confidence-bounded planning-benefit claim: the threshold rule made
zero action changes, `planning_benefit_with_confidence` is false, and the
bootstrap interval for CD-minus-baseline planning regret still crosses zero
(`lower:-0.48124999999999996`, `upper:0.32500000000000007`).

Immediate predecessor instrument receipt:

```text
/tmp/persona-dream-cooperation-exposure-contrast-instrument-20260721T224641Z/cooperation_exposure_contrast_instrument_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:1919eaaf30b995bf0a21d8d5e4c2d5fde31b91a47c39b1fa28dceaffe8d3d818
```

Inspection result:

```text
status: PASS_PCTOM_COOPERATION_EXPOSURE_CONTRAST_INSTRUMENT
episodes: 8
variant_min: 37
variant_max: 44
offer_cooperation_affordance_rows: 8
keep_cooperation_positive_rows: 4
avoid_or_unsafe_cooperation_contrast_rows: 4
negative_mutations: 5
negative_mutations_failed_closed: 5
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: false
fixture_backed: false
deterministic_simulator_corpus: true
llm_judge_used: false
human_content_judgment_required: false
```

What this proves:

```text
the next deterministic non-oracle cooperation instrument exists
-> every visible pre-outcome packet exposes OFFER_COOPERATION as available
-> hidden simulator labels still split keep/safe cooperation from avoid/unsafe
   cooperation
-> visible packets omit actual_next_action, counterpart_policy, contrast_class,
   oracle_agent_action, and hidden cooperation safety fields
-> five negative mutations failed closed:
   missing_visible_offer_affordance
   missing_avoid_contrast_rows
   avoid_row_actual_offer
   visible_outcome_key_leak
   missing_oracle_withheld_field
-> zero unsupported writes occurred
```

What this does not prove:

```text
live Tau execution over this exposure/contrast corpus
CD will select OFFER_COOPERATION
planning benefit
confidence-bounded CD benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Earlier predecessor receipts:

Live contrast/no-exposure receipt:

```text
/tmp/persona-dream-live-tau-cooperation-contrast-slice-reuse-proof-20260721T214048Z/live_tau_cooperation_contrast_slice_receipt.v1.json
```

No-exposure diagnostic receipt:

```text
/tmp/persona-dream-cooperation-no-exposure-diagnostic-20260721T2208Z/cooperation_no_exposure_diagnostic_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:2df9f209bcb005ea23ddc2233f18a694a1eb9cece38c886b785c937f331f875d
```

No-exposure diagnostic receipt SHA-256:

```text
sha256:0367d1a6789b3a0fcdbfec48596068861df471f2c641a2b25d7f7bba7fcc14b9
```

Inspection result:

```text
status: PASS_LIVE_TAU_PCTOM_COOPERATION_CONTRAST_SLICE
slice_conclusion: CONTRAST_SLICE_LIVE_TAU_NO_CD_OFFER_EXPOSURE
contrast_episodes: 8
keep_cooperation_positive_rows: 4
avoid_or_unsafe_cooperation_contrast_rows: 4
cases: 32
action_cases: 32
rows: 8
cd_offer_cooperation_candidates: 0
cd_offer_keep_candidates: 0
cd_offer_avoid_or_unsafe_candidates: 0
cd_low_confidence_cooperation_interventions: 0
cd_action_change_count: 0
tau_call_attempts: 32
tau_live_call_performed: 32
live_tau_reexecuted_by_this_command: false
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
deterministic_simulator_corpus: true
llm_judge_used: false
human_content_judgment_required: false
planning_benefit_with_confidence: false
```

No-exposure diagnostic result:

```text
status: PASS_PCTOM_COOPERATION_NO_EXPOSURE_DIAGNOSTIC
diagnostic_conclusion: NO_CD_OFFER_EXPOSURE_CONFIRMED
rows: 8
keep_cooperation_positive_rows: 4
avoid_or_unsafe_cooperation_contrast_rows: 4
cd_offer_cooperation_candidates: 0
cd_original_action_counts:
  WAIT: 4
  DISCLOSE_INFORMATION: 4
selected_counterpart_action_counts:
  KAI_ASKS_TO_WAIT: 4
  KAI_DISCLOSES_AUTHORITY_CONSTRAINT: 4
mean_kai_offers_cooperation_probability:
  KEEP_COOPERATION_POSITIVE: 0.29833325
  AVOID_OR_UNSAFE_COOPERATION_CONTRAST: 0.1
no_oracle_or_outcome_inputs: true
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
tau_live_call_performed_by_diagnostic: 0
```

What this proves:

```text
the deterministic cooperation-contrast corpus was consumed by the live Tau
M/R/D/CD condition runner
-> 32 live Tau cases completed and were sealed before deterministic outcome
   reveal
-> 32 Gate 6 action decisions were scored
-> pre-outcome threshold-rule rows used sealed prediction/action fields and no
   oracle/outcome inputs
-> zero unsupported writes occurred
```

What this does not prove:

```text
CD will expose cooperation offer candidates on this corpus
a replacement cooperation feature split is valid
broad held-out planning benefit
confidence-bounded CD benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Important finding:

The contrast corpus now runs through live Tau and Gate 6, but it still does not
create the action exposure needed for a replacement cooperation feature split.
The no-exposure diagnostic now records the reason in a hash-bound artifact: CD
selected zero `OFFER_COOPERATION` actions across all eight contrast rows. On
keep rows, CD avoided the simulator-oracle cooperation action by selecting
`WAIT` or `DISCLOSE_INFORMATION`; on avoid rows, CD also suppressed unsafe
cooperation by selecting `WAIT` or `DISCLOSE_INFORMATION` while predicted
`KAI_OFFERS_COOPERATION` probability stayed below the threshold. The threshold
rule therefore made zero action changes. Planning-benefit with confidence
remains false.

This wrapper reused the already-completed live Tau condition/action roots from:

```text
/tmp/persona-dream-live-tau-cooperation-contrast-slice-20260721T213306Z
```

The initial wrapper attempt produced those live artifacts but crashed while
summarizing variants because contrast episode IDs ended in `-keep` or `-avoid`.
The committed wrapper now binds variants from the contrast corpus metadata
instead of parsing only the final hyphen suffix.

Prior deterministic contrast instrument:

```text
/tmp/persona-dream-cooperation-contrast-instrument-20260721T212749Z/cooperation_contrast_instrument_receipt.v1.json
```

That receipt has status `PASS_PCTOM_COOPERATION_CONTRAST_INSTRUMENT` and
created four keep-cooperation positive rows plus four avoid/unsafe-cooperation
contrast rows.

Prior prerequisite blocker:

The feature-split prerequisite audit consumes the no-intervention acceptance:

```text
/tmp/persona-dream-cooperation-no-intervention-policy-proof-20260721T211544Z/cooperation_no_intervention_policy_acceptance_receipt.v1.json
```

That acceptance consumed the prior deterministic diagnostic:

```text
/tmp/persona-dream-cooperation-policy-diagnostic-proof-20260721T205236Z/cooperation_policy_diagnostic_receipt.v1.json
```

That diagnostic rejected `pre_outcome_cooperation_threshold_rule.v1` as a
single-probability fallback. The only accepted row, `instr-coord-exposure-26`,
keeps CD's original `OFFER_COOPERATION` action and quarantines the threshold
fallback's `WAIT` action. Pre-outcome basis remains: selected predicted
counterpart action `KAI_OFFERS_COOPERATION`, probability `0.36`, probability
margin `0.02`, distribution sum `1.0`, and M/R/D baselines selected `WAIT`.
Post-outcome evaluation only: oracle action was `OFFER_COOPERATION`; original
CD planning regret was `0.0`; quarantined-rule regret was `0.55`; avoided
regret delta was `0.55`.

The prerequisite audit then checks whether this evidence can support a
replacement pre-outcome feature split. It cannot: the current evidence has one
positive keep-cooperation row and zero unsafe/avoid-cooperation contrast rows.

Next legal move:

The threshold rule remains quarantined for the observed regression slice. The
contrast corpus has live Tau and Gate 6 evidence plus a deterministic
no-exposure diagnostic, but no CD offer exposure. The newly added deterministic
exposure/contrast instrument is now the next candidate input for a bounded live
Tau slice. Run live Tau over this instrument with the same seal/reveal/action
discipline, then diagnose whether CD exposes `OFFER_COOPERATION` without
leaking oracle/outcome fields. If bounded live attempts still produce no
exposure, preserve the null result as a research finding. Do not claim broad
planning benefit, feature-split acceptance, or replacement-policy validity
from the offline instrument.
