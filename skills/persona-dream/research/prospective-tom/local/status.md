# Status

Status: UNSAFE_OFFER_NO_EXPOSURE_CONFIRMED_SUPPRESSION_BLOCKED

Artifact: PCTOM-R deterministic unsafe-offer no-exposure diagnostic over the
live Tau unsafe-offer-pressure slice. This records the live result as a
no-exposure/null boundary: all four rows were unsafe-offer-pressure rows with
visible `OFFER_COOPERATION` affordance, but CD selected `WAIT` or
`DISCLOSE_INFORMATION` on every row. Unsafe-offer suppression, replacement
feature-split acceptance, and broad planning-benefit claims remain blocked.

Current receipt:

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
