# Inspection

Command family:

```bash
skills/persona-dream/run.sh check-prospective-tom-protocol \
  --case-root <fixture-case-root> \
  --receipt-out <receipt.json> \
  --json
```

Latest local inspection output root:

```text
/tmp/persona-dream-pctom-gate0-check-20260720T231148Z
```

Observed results:

```text
positive/lineage_ok: exit 0, PASS_PCTOM_GATE0_LINEAGE
negative/bad_source_hash: exit 1, BLOCKED_PCTOM_GATE0_LINEAGE
negative/unaccepted_residue: exit 1, BLOCKED_PCTOM_GATE0_LINEAGE
negative/unresolved_branch: exit 1, BLOCKED_PCTOM_GATE0_LINEAGE
negative/outcome_visible: exit 1, BLOCKED_PCTOM_GATE0_LINEAGE
```

Positive fixture counts:

```text
recall_receipts: 1
accepted_source_ids: 2
normalized_residue: 2
dream_branches: 2
prediction_evidence_links: 2
prediction_branch_links: 2
errors: 0
```

Targeted negative blockers:

```text
bad_source_hash: recall_receipt_0_accepted_source_ids_sha256_mismatch
unaccepted_residue: residue_0_source_not_accepted:persona-dream:memory_42
unresolved_branch: prediction_unresolved_dream_branch_ref:missing-branch
outcome_visible: commitment_outcome_visible_not_false
```

Inspection limitation:

```text
fixture_backed: true
live: false
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
```
