# Status

Status: BLOCKED_ON_NATURAL_COOPERATION_EXPOSURE

Artifact: PCTOM-R held-out cooperation exposure slice.

Current receipt:

```text
/tmp/persona-dream-live-tau-cooperation-exposure-slice-proof-20260721T200908Z/live_tau_cooperation_exposure_slice_receipt.v1.json
```

Receipt SHA-256:

```text
sha256:190a5c8c5313fb4298dc5840041e593713c9d1d4c436238fd69b912ca19608cb
```

Inspection result:

```text
status: BLOCKED_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_SLICE
conclusion: HELDOUT_COOPERATION_OUTCOME_PRESENT_BUT_CD_NO_OFFER_EXPOSURE
rows: 8
cases: 32
tau_call_attempts: 32
tau_live_call_performed: 32
cooperation_outcome_rows: 1
cd_offer_cooperation_candidates: 0
cd_low_confidence_cooperation_interventions: 0
cd_action_change_count: 0
memory_write_attempts: 0
provider_call_attempts: 0
canonical_memory_write_attempts: 0
identity_write_attempts: 0
source_memory_write_attempts: 0
mocked: false
live: true
```

Reason blocked:

The variants 23-24 held-out live Tau slice is disjoint from both the full64
variants 1-16 and the balanced derivation variants 17-22. It includes one
coordination/conflict cooperation-outcome row, but CD did not select
`OFFER_COOPERATION` from sealed `KAI_OFFERS_COOPERATION` predictions in any
row. Therefore the pre-outcome cooperation-threshold rule has no natural
held-out exposure to score in the exhausted 1-24 corpus.

What this proves:

```text
variant 23-24 live Tau slice executed
-> sealed M/R/D/CD prediction artifacts produced
-> Gate 6 action rows produced
-> pre-outcome cooperation rule recomputed
-> no natural held-out CD cooperation exposure found
-> planning-benefit claim failed closed
```

What this does not prove:

```text
broad held-out planning benefit
confidence-bounded CD planning benefit
semantic dream quality
paid provider execution
complete live Phase 01-16 runtime execution
that the cooperation threshold is optimal
```

Next legal move:

Add an explicit deterministic cooperation-exposure instrument or scenario
variant before rerunning held-out benefit checks. Do not keep spending live Tau
calls looking for accidental `OFFER_COOPERATION` exposure in the existing
variants 1-24 corpus.
