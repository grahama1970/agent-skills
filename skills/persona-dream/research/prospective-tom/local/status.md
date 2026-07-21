# Status

Status: INSTRUMENT_READY_FOR_LIVE_TAU_SLICE

Artifact: PCTOM-R deterministic cooperation-exposure instrument.

Current receipt:

```text
/tmp/persona-dream-cooperation-exposure-instrument-proof-20260721T203146Z/cooperation_exposure_instrument_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:f24ac1bc75054959346274c974936c2f7dfe8c3651c07637af31f6382d341515
```

Inspection result:

```text
status: PASS_PCTOM_COOPERATION_EXPOSURE_INSTRUMENT
generator_version: pctom_cooperation_exposure_instrument.v1
variant_min: 25
variant_max: 28
episodes: 4
exposure_rows: 4
counterpart_action: KAI_OFFERS_COOPERATION
agent_action: OFFER_COOPERATION
visible_packet_hashes: 4
negative_mutations: 4
negative_mutations_failed_closed: 4
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: false
llm_judge_used: false
human_content_judgment_required: false
```

What this proves:

```text
deterministic held-out variants 25-28 exist
-> every row has deterministic KAI_OFFERS_COOPERATION outcome
-> visible packets omit actual_next_action and counterpart_policy fields
-> no outcome/policy trigger is exposed to the model packet
-> negative mutations fail closed:
   no_cooperation_exposure
   visible_outcome_key_leak
   variant_not_disjoint_from_prior_corpus
   missing_actual_next_action_withheld_field
```

What this does not prove:

```text
CD will select OFFER_COOPERATION in live Tau
planning benefit
confidence-bounded CD benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
```

Reason this supersedes the prior no-exposure blocker:

The prior variants 23-24 live slice had one cooperation-outcome row but zero CD
`OFFER_COOPERATION` candidates, so it could not score the cooperation-threshold
rule under natural held-out exposure. The instrument creates an explicit,
deterministic, outcome-hidden cooperation-exposure slice beyond the exhausted
variants 1-24 corpus.

Next legal move:

Adapt the live Tau condition-comparison runner to consume this instrument
corpus as an explicit evaluation slice, then rerun the pre-outcome
cooperation-threshold scoring against live-originated instrument artifacts. Do
not claim planning benefit from this instrument until live Tau predictions,
Gate 6 action rows, and post-outcome scoring receipts exist.
