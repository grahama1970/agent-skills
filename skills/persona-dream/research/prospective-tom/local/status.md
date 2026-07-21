# Status

Status: COOPERATION_CONTRAST_NO_EXPOSURE_DIAGNOSED

Artifact: PCTOM-R live Tau cooperation-contrast slice over the deterministic
contrast corpus, with Gate 6 action scoring and pre-outcome threshold-rule
rows.

Current receipt:

```text
/tmp/persona-dream-live-tau-cooperation-contrast-slice-reuse-proof-20260721T214048Z/live_tau_cooperation_contrast_slice_receipt.v1.json
```

Current no-exposure diagnostic receipt:

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
contrast corpus now has live Tau and Gate 6 evidence plus a deterministic
no-exposure diagnostic, but still no CD offer exposure. The next PCTOM-R step is
to design a non-oracle, pre-outcome exposure instrument or prompt/corpus
adjustment that can produce CD cooperation action exposure while retaining
avoid/unsafe contrast rows. If bounded attempts still produce no exposure,
preserve the null result as a research finding. Do not claim broad planning
benefit, feature-split acceptance, or replacement-policy validity from this
slice.
