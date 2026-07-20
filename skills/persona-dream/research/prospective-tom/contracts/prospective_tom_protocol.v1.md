# Prospective ToM Protocol v1

PCTOM-R starts as a text-first research lane. It must not alter the production
Phase 01-16 Persona Dream state machine until the research lane has mechanical
signal and fail-closed evidence.

## Gate 0 Lineage Contract

The first implemented contract is provenance-to-sealed-prediction lineage:

```text
live recall query receipt
-> accepted source id
-> normalized residue
-> dream branch
-> sealed ToM prediction commitment
```

The checker treats the chain as blocked unless every link is explicit and
hash-bound.

## Required Inputs

A protocol case directory contains:

```text
recall_receipts.json
normalized_residue.json
dream_branches.json
tom_prediction_commitment.json
```

## Invariants

- Each recall receipt has `query`, `scope`, `accepted_source_ids`, and
  `accepted_source_ids_sha256`.
- `accepted_source_ids_sha256` recomputes over canonical JSON for
  `accepted_source_ids`.
- Each normalized residue item has nonempty `scope`, `source_id`, and `text`.
- Each residue item names the recall receipt index that accepted its source id.
- Each residue `(scope, source_id)` resolves to that receipt's accepted source
  ids.
- Each dream branch resolves all residue references.
- Counterfactual branches are marked synthetic and cannot be ordinary evidence.
- Each prediction commitment is sealed before reveal by setting
  `outcome_visible` to `false`.
- The commitment's `prediction_payload_sha256` recomputes over
  `prediction_payload`.
- All prediction evidence references resolve to normalized residue.
- All prediction branch references resolve to dream branches.
- Probability distributions sum to one.

## Non-Goals For Gate 0

Gate 0 does not prove:

- model semantic quality;
- future prediction accuracy;
- hidden-world simulator correctness;
- outcome scoring;
- belief revision;
- repeated-trial reliability;
- live Tau execution;
- paid provider execution.

Those belong to later PCTOM-R gates.
