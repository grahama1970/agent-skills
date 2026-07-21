# Status

Status: LIVE_TAU_INSTRUMENT_SLICE_SCORED_THRESHOLD_RULE_NOT_BENEFICIAL

Artifact: PCTOM-R deterministic cooperation-exposure instrument consumed by live Tau M/R/D/CD condition/action/scoring path.

Current receipt:

```text
/tmp/persona-dream-live-tau-cooperation-instrument-slice-reuse-proof-20260721T204705Z/live_tau_cooperation_instrument_slice_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:6fec3c6804219613878a03cbc8bcd38adb8b523ab027d001467fe4769db8dae5
```

Inspection result:

```text
status: PASS_LIVE_TAU_PCTOM_COOPERATION_INSTRUMENT_SLICE
slice_conclusion: INSTRUMENT_COOPERATION_EXPOSURE_SCORED
instrument_episodes: 4
instrument_cooperation_exposure_rows: 4
condition_cases: 16
action_cases: 16
rows: 4
cd_offer_cooperation_candidates: 1
cd_low_confidence_cooperation_interventions: 1
cd_action_change_count: 1
tau_call_attempts: 16
tau_live_call_performed: 16
live_tau_reexecuted_by_receipt_command: false
live_tau_originated_artifacts_consumed: true
condition_used_external_instrument_corpus: true
tau_receipts_hash_bound: true
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
instrument corpus path
-> live Tau condition comparison with M/R/D/CD over 4 episodes
-> Gate 2 distributions, Gate 3 branches, Gate 4 sealed commitments, and
   Gate 5 scoring for all 16 condition cases
-> Gate 6 action scoring for all 16 condition cases
-> pre-outcome cooperation-threshold rule over sealed prediction/action fields
-> no oracle/outcome inputs in the rule
-> no unsupported writes
```

What this does not prove:

```text
confidence-bounded CD benefit
planning benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
that the cooperation threshold is beneficial or optimal
```

Important finding:

The instrument created live CD cooperation exposure. In variant
`instr-coord-exposure-26`, CD selected `OFFER_COOPERATION` from
`KAI_OFFERS_COOPERATION` with sealed probability `0.36`; the oracle action was
also `OFFER_COOPERATION`, so original CD planning regret was `0.0` while the
best baseline regret was `0.55`. The pre-outcome threshold rule
`LOW_CONFIDENCE_COOPERATION_FALLBACK_TO_WAIT` changed CD to `WAIT`, raising CD
regret to `0.55` and converting the original BENEFIT row to a TIE. Across the
four instrument rows, original CD-minus-baseline mean was `-0.1375`; intervened
CD-minus-baseline mean was `0.0`; improvement-vs-original mean was `-0.1375`.

Next legal move:

Treat the low-confidence cooperation-threshold rule as falsified on the first
live instrument exposure. Next work should add a deterministic policy diagnostic
that distinguishes "low confidence but top action is correct" from genuinely
unsafe cooperation, then either reject the threshold rule or replace it with a
pre-outcome rule that preserves the instrument benefit without using oracle or
outcome fields. Do not claim planning benefit from the current threshold rule.
