# Inspection

Gate 0 command family:

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

## Gate 3 Inspection

Command family:

```bash
skills/persona-dream/run.sh check-counterfactual-branches \
  --corpus skills/persona-dream/research/prospective-tom/fixtures/gate1/development/social_episode_corpus.v1.json \
  --distributions <tom_belief_distribution_bundle.json> \
  --branches <counterfactual_branch_bundle.json> \
  --receipt-out <receipt.json> \
  --json
```

Final proof root:

```text
/tmp/persona-dream-pctom-gate3-final-20260721T004724Z
```

Positive result:

```text
status: PASS_COUNTERFACTUAL_BRANCHES
branches: 2
factual_branches: 1
counterfactual_branches: 1
interventions: 1
resolved_source_evidence_refs: 4
distribution_refs: 2
```

Negative fixture results:

```text
counterfactual_not_synthetic: BLOCKED_COUNTERFACTUAL_BRANCHES
factual_uses_counterfactual_distribution: BLOCKED_COUNTERFACTUAL_BRANCHES
held_fixed_includes_intervention: BLOCKED_COUNTERFACTUAL_BRANCHES
hidden_source_evidence: BLOCKED_COUNTERFACTUAL_BRANCHES
missing_factual_branch: BLOCKED_COUNTERFACTUAL_BRANCHES
unresolved_distribution_ref: BLOCKED_COUNTERFACTUAL_BRANCHES
```

Inspection limitation:

```text
fixture_backed: true
live: false
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
```

## Gate 1 Inspection

Build command:

```bash
skills/persona-dream/run.sh build-social-episode-corpus \
  --split development \
  --episodes-per-family 3 \
  --generated-at 2026-07-20T00:00:00Z \
  --output skills/persona-dream/research/prospective-tom/fixtures/gate1/development/social_episode_corpus.v1.json \
  --receipt-out /tmp/persona-dream-pctom-gate1-build-receipt.json \
  --json
```

Build result:

```text
status: PASS_SOCIAL_EPISODE_CORPUS_BUILT
episode_count: 12
family_counts: 3 per family across 4 families
episodes_sha256: sha256:713877facd124815548959012da04818d31e8790ed4b914bcdb1b59b8a759d3e
corpus_sha256: sha256:3b80c6a04f24dda488d881b0934ae8200e71cef67d94258d8eec09af8f465028
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
```

Latest final proof root:

```text
/tmp/persona-dream-pctom-gate1-final-20260721T001454Z
```

Positive result:

```text
status: PASS_SOCIAL_EPISODE_CORPUS
episodes: 12
families: 4
first_order_labels: 12
second_order_labels: 12
errors: 0
```

Negative mutation result:

```text
status: BLOCKED_SOCIAL_EPISODE_CORPUS
exit: 1
errors:
- episodes_sha256_mismatch
- episode_0_actual_next_action_not_allowed:INVALID_UNLISTED_ACTION
- episode_0_policy_actual_mismatch:KAI_HINTS_CONSTRAINT:INVALID_UNLISTED_ACTION
```

## Gate 2 Inspection

Command family:

```bash
skills/persona-dream/run.sh check-tom-belief-distributions \
  --corpus skills/persona-dream/research/prospective-tom/fixtures/gate1/development/social_episode_corpus.v1.json \
  --bundle <gate2-bundle.json> \
  --receipt-out <receipt.json> \
  --json
```

Final proof root:

```text
/tmp/persona-dream-pctom-gate2-postrebase-20260721T003945Z
```

Positive result:

```text
status: PASS_TOM_BELIEF_DISTRIBUTIONS
distributions: 3
supported: 2
abstained_or_pending: 1
label_matched_distributions: 2
resolved_evidence_refs: 4
```

Negative fixture results:

```text
bad_probability_sum: BLOCKED_TOM_BELIEF_DISTRIBUTIONS
canonical_memory_write: BLOCKED_TOM_BELIEF_DISTRIBUTIONS
counterfactual_literal_mix: BLOCKED_TOM_BELIEF_DISTRIBUTIONS
hidden_evidence_ref: BLOCKED_TOM_BELIEF_DISTRIBUTIONS
outcome_visible: BLOCKED_TOM_BELIEF_DISTRIBUTIONS
perspective_label_mismatch: BLOCKED_TOM_BELIEF_DISTRIBUTIONS
unsupported_not_abstained: BLOCKED_TOM_BELIEF_DISTRIBUTIONS
```

Inspection limitation:

```text
fixture_backed: true
live: false
tau_call_attempts: 0
memory_write_attempts: 0
provider_call_attempts: 0
```
