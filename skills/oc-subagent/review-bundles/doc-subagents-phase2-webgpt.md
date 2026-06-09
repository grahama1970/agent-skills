# WebGPT Review Request: doc-subagents Phase 2

## Request

Review the Phase 2 correction after the Phase 1 `NEEDS_CHANGES` verdict.
Return:

`VERDICT: PASS | NEEDS_CHANGES | BLOCKED`

Then list concrete corrections only. Review only. No commands. No repository edits.

## Phase 1 WebGPT Verdict

`VERDICT: NEEDS_CHANGES`

Required correction:

```text
Add an explicit README/router/default-route rule: doc-extractor owns source-prep section JSONL only; doc-qra owns doc2qra recall/memory distillation only; final canonical lore facts, Theory-of-Mind states, relationship states, graph upserts, retrieval units, and Qdrant materialization must route to a separate future lore-extractor flow/persona.
```

## Correction Applied

The README default routes section now contains:

```text
Doc Extractor prepares source documents into validated section JSONL with raw/clean alignment and repair notes. Use it only when source-prep artifacts are the work product; use Extractor for ordinary PDF/table/control/entity extraction.

Doc QRA converts prepared document artifacts into grounded summaries and QRA pairs through doc2qra. It owns recall aids and memory receipts, not source cleanup or final canon lore.

Final canonical lore facts, Theory-of-Mind states, relationship states, graph upserts, retrieval units, and Qdrant materialization are not owned by Doc Extractor or Doc QRA. Route those to a separate future lore-extractor flow or persona.
```

## Local Evidence

Targeted grep:

```text
130:- Final canonical lore facts, Theory-of-Mind states, relationship states, graph upserts, retrieval units, and Qdrant materialization are not owned by Doc Extractor or Doc QRA. Route those to a separate future lore-extractor flow or persona.
```

Persona structural validation:

```text
{'path': 'skills/oc-subagent/personas/doc-extractor/persona.yaml', 'id_matches_dir': True, 'has_memory': True, 'missing_required': [], 'has_pyproject': True, 'has_extractor': True, 'forbids_qra': True, 'requires_hashes': True}
{'path': 'skills/oc-subagent/personas/doc-qra/persona.yaml', 'id_matches_dir': True, 'has_memory': True, 'missing_required': [], 'has_pyproject': True, 'has_doc2qra': True, 'allows_doc_extractor_help': True, 'receipt_fields': True}
PERSONA_CONTRACT_CHECK: PASS
```

## Already Reviewed As Satisfied In Phase 1

Phase 1 WebGPT said everything else from Phase 0 appeared satisfied:

- distinct `doc-extractor` decision rule
- section integrity fields
- raw-text evidence rule
- sizing/resegmentation policy
- quarantine behavior
- alias repair constraints
- doc-qra receipt fields
- QRA-as-recall-only boundary
- bounded helper policy
- primary skills
- forbidden outputs

## Question

Does the Phase 2 README/router correction satisfy the remaining blocker?
