# Status

Status: COOPERATION_POLICY_DIAGNOSTIC_REJECTS_SINGLE_PROBABILITY_FALLBACK

Artifact: PCTOM-R deterministic cooperation policy diagnostic over live-originated instrument artifacts.

Current receipt:

```text
/tmp/persona-dream-cooperation-policy-diagnostic-proof-20260721T205236Z/cooperation_policy_diagnostic_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:ca61df14a35d3b6f75e2484d47083da27947303329b5369148f9b9bbda95a51c
```

Inspection result:

```text
status: PASS_PCTOM_COOPERATION_POLICY_DIAGNOSTIC
diagnostic_conclusion: REJECT_SINGLE_PROBABILITY_COOPERATION_FALLBACK
candidate_count: 1
label_counts: LOW_CONFIDENCE_TOP_ACTION_CORRECT_RULE_REGRESSION=1
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
live-originated cooperation candidate rows were deterministically classified
-> rule inputs were checked to exclude oracle/outcome fields
-> the only observed low-confidence cooperation candidate was correct before
   the threshold intervention
-> the single-probability fallback worsened that candidate
-> negative mutations fail closed:
   rule_input_oracle_outcome_leak
   missing_cd_cooperation_candidate
   summary_row_count_mismatch
-> no new Tau calls or unsupported writes
```

What this does not prove:

```text
replacement cooperation policy benefit
confidence-bounded CD benefit
planning benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Important finding:

The diagnostic rejects `pre_outcome_cooperation_threshold_rule.v1` as a
single-probability fallback. The only candidate, `instr-coord-exposure-26`, was
labeled `LOW_CONFIDENCE_TOP_ACTION_CORRECT_RULE_REGRESSION`. Pre-outcome
features: CD selected `OFFER_COOPERATION`; selected predicted counterpart
action was `KAI_OFFERS_COOPERATION`; probability was `0.36`; probability margin
was `0.02`; M/R/D baselines selected `WAIT`; distribution sum was `1.0`.
Post-outcome evaluation only: oracle action was `OFFER_COOPERATION`; original
CD planning regret was `0.0`; intervened regret was `0.55`; rule regression
delta was `+0.55`.

Next legal move:

Remove or quarantine the current threshold rule from any planning-benefit claim.
The next policy step must be either: (1) a no-intervention baseline acceptance
receipt that preserves the observed instrument benefit, or (2) a replacement
pre-outcome rule with additional features that can pass the same diagnostic and
negative checks without oracle/outcome inputs. Do not claim planning benefit
from the current cooperation threshold rule.
