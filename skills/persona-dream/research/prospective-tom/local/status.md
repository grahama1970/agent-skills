# Status

Status: COOPERATION_CONTRAST_INSTRUMENT_CREATED

Artifact: PCTOM-R deterministic cooperation-contrast instrument with both
keep-cooperation positives and avoid/unsafe-cooperation contrast rows.

Current receipt:

```text
/tmp/persona-dream-cooperation-contrast-instrument-20260721T212749Z/cooperation_contrast_instrument_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:58118f340a778133193811afb7f379522a3c3b5f9c95748252f22170a86b9444
```

Inspection result:

```text
status: PASS_PCTOM_COOPERATION_CONTRAST_INSTRUMENT
episode_count: 8
variant_min: 29
variant_max: 36
keep_cooperation_positive_rows: 4
avoid_or_unsafe_cooperation_contrast_rows: 4
negative_checks_failed_closed: true
negative_mutations: 6
negative_mutations_failed_closed: 6
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: false
deterministic_simulator_corpus: true
llm_judge_used: false
human_content_judgment_required: false
```

What this proves:

```text
a deterministic cooperation-contrast corpus exists beyond variants 1-28
-> the corpus contains both keep-cooperation positive rows and
   avoid/unsafe-cooperation contrast rows
-> visible packets omit actual_next_action, counterpart_policy, contrast_class,
   oracle_agent_action, and hidden cooperation-safety fields
-> negative mutations fail closed:
   missing_avoid_or_unsafe_contrast
   missing_keep_cooperation_positive
   visible_outcome_key_leak
   variant_not_disjoint_from_prior_instruments
   counterpart_policy_actual_mismatch
   missing_contrast_class_withheld_field
-> no Tau calls or unsupported writes
```

What this does not prove:

```text
live Tau execution over the contrast corpus
CD will expose both cooperation action classes
a replacement cooperation feature split is valid
broad held-out planning benefit
confidence-bounded CD benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Important finding:

The contrast instrument closes the previous missing-data blocker at the
deterministic simulator-corpus layer. It creates four hidden-state cases where
cooperation is the correct counterpart action and four hidden-state cases where
wait/disclose is the correct counterpart action because cooperation is unsafe
or not authorized. Visible packets are separately hash-bound and withhold
outcome, policy, contrast class, oracle agent action, and hidden safety fields.

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
new contrast corpus is offline deterministic simulator evidence, not live Tau
evidence. The next PCTOM-R step is to run or adapt the live Tau condition
runner against this contrast corpus, then run action scoring, policy diagnostic,
and the feature-split prerequisite audit over live-originated contrast rows.
Do not claim broad planning benefit or replacement-policy validity from the
offline contrast corpus alone.
