# Status

Status: COOPERATION_FEATURE_SPLIT_PREREQUISITE_AUDIT_BLOCKS_REPLACEMENT_POLICY

Artifact: PCTOM-R cooperation feature-split prerequisite audit over the
live-originated no-intervention acceptance and policy diagnostic artifacts.

Current receipt:

```text
/tmp/persona-dream-cooperation-feature-split-prereq-audit-20260721T212150Z/cooperation_feature_split_prerequisite_audit_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:b4b382e52f0d85c4a0f5144057f5145d96a1d5b30b0bcee8cf13daa09d827acb
```

Inspection result:

```text
status: PASS_PCTOM_COOPERATION_FEATURE_SPLIT_PREREQUISITE_AUDIT
conclusion: FEATURE_SPLIT_BLOCKED_INSUFFICIENT_CONTRAST
feature_split_acceptance_allowed: false
missing_prerequisites: missing_unsafe_or_avoid_cooperation_contrast_candidate
accepted_keep_cooperation_positive_candidates: 1
diagnostic_keep_cooperation_label_count: 1
diagnostic_avoid_or_unsafe_cooperation_candidates: 0
diagnostic_avoid_or_unsafe_label_count: 0
diagnostic_candidate_count: 1
negative_checks_failed_closed: true
tau_call_attempts: 0
tau_live_call_performed: 0
live_tau_originated_artifacts_consumed: true
live_tau_reexecuted_by_this_command: false
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
llm_judge_used: false
human_content_judgment_required: false
```

What this proves:

```text
current live-originated cooperation evidence is one-sided for replacement
feature-split learning
-> the accepted keep-cooperation row has pre-outcome basis that excludes
   oracle/outcome fields
-> no replacement cooperation policy or broad planning-benefit claim is
   accepted by this audit
-> negative mutations fail closed:
   acceptance_status_not_pass
   broad_planning_benefit_claim_injected
   accepted_pre_outcome_oracle_leak
   missing_keep_cooperation_candidate
-> no new Tau calls or unsupported writes
```

What this does not prove:

```text
a replacement cooperation feature split is valid
broad held-out planning benefit
replacement cooperation policy benefit
confidence-bounded CD benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Important finding:

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

The threshold rule remains quarantined for the observed regression slice, and a
replacement feature split is now explicitly blocked by insufficient contrast.
The next PCTOM-R step is to create or collect a broader cooperation-exposure
slice containing both keep-cooperation positives and unsafe/avoid-cooperation
contrast rows, then rerun this prerequisite audit before attempting any
replacement policy. Do not claim broad planning benefit or replacement-policy
validity from the current one-sided evidence.
