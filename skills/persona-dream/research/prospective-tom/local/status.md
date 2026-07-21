# Status

Status: LIVE_TAU_COOPERATION_CONTRAST_SLICE_NO_CD_OFFER_EXPOSURE

Artifact: PCTOM-R live Tau cooperation-contrast slice over the deterministic
contrast corpus, with Gate 6 action scoring and pre-outcome threshold-rule
rows.

Current receipt:

```text
/tmp/persona-dream-live-tau-cooperation-contrast-slice-reuse-proof-20260721T214048Z/live_tau_cooperation_contrast_slice_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:2df9f209bcb005ea23ddc2233f18a694a1eb9cece38c886b785c937f331f875d
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
CD selected zero `OFFER_COOPERATION` actions across all eight contrast rows:
zero keep-cooperation offer candidates and zero avoid/unsafe offer candidates.
The threshold rule therefore made zero action changes. Planning-benefit with
confidence remains false.

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
contrast corpus now has live Tau and Gate 6 evidence, but no CD offer exposure.
The next PCTOM-R step is to diagnose why CD avoided `OFFER_COOPERATION` on both
keep and avoid contrast rows, then either adjust the contrast prompt/corpus to
produce action exposure or explicitly record this as a no-exposure live result.
Do not claim broad planning benefit or replacement-policy validity from this
slice.
