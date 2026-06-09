# WebGPT Review Request: doc-subagents Phase 1

## Request

Review the implemented `doc-extractor` and `doc-qra` persona contracts. Return:

`VERDICT: PASS | NEEDS_CHANGES | BLOCKED`

Then list concrete corrections only. Review only. No commands. No repository edits.

## Changed Files

- `oc-subagent/personas/doc-extractor/persona.yaml`
- `oc-subagent/personas/doc-extractor/pyproject.toml`
- `oc-subagent/personas/doc-qra/persona.yaml`
- `oc-subagent/personas/doc-qra/pyproject.toml`
- `oc-subagent/personas/README.md`

This bundle is intentionally self-contained. The browser reviewer should use
the inlined content below and must not read local filesystem paths.

## Phase 0 WebGPT Verdict

`VERDICT: NEEDS_CHANGES`

Required corrections from Phase 0:

- Add a decision rule proving `doc-extractor` is distinct from the existing
  generic `extractor` persona.
- Add required section integrity fields: `source_hash`, `raw_text_sha256`,
  `cleaned_text_sha256`, `offset_unit`, `extractor_run_id`,
  `validation_status`, and `source_artifact_id`.
- State that raw text plus span/offset is the evidence source; cleaned text,
  summaries, and alias repairs are helper annotations only.
- Define section sizing, max size, overlap policy, and mandatory resegmentation
  conditions.
- Require quarantine/failure records for broken offsets, unverifiable repairs,
  missing raw spans, and over-normalized cleaned text.
- Add alias repair constraints and a not-canonical-proof warning.
- Add doc-qra receipt fields: `scope`, `collection`, `dry_run`, `stored_count`,
  `skipped_count`, `validator_verdict`, and `source_artifact_ids`.
- State that doc-qra QRAs are recall aids only, not canon facts, ToM states,
  relationship states, or graph-ready lore records.
- Route final lore extraction, Theory-of-Mind extraction, graph upsert, and
  Qdrant materialization to a separate future lore-extractor flow/persona.
- Persona YAMLs must explicitly list forbidden outputs and primary skills:
  `doc-extractor -> extractor,memory`; `doc-qra -> doc2qra,memory`.

## Local Structural Check

The project agent ran this local validation after editing:

```text
{'path': 'skills/oc-subagent/personas/doc-extractor/persona.yaml', 'id_matches_dir': True, 'has_memory': True, 'missing_required': [], 'has_pyproject': True, 'has_extractor': True, 'forbids_qra': True, 'requires_hashes': True}
{'path': 'skills/oc-subagent/personas/doc-qra/persona.yaml', 'id_matches_dir': True, 'has_memory': True, 'missing_required': [], 'has_pyproject': True, 'has_doc2qra': True, 'allows_doc_extractor_help': True, 'receipt_fields': True}
PERSONA_CONTRACT_CHECK: PASS
```

## Implementation Summary

### `doc-extractor`

Primary skills:

```yaml
primary_skills:
  - memory
  - extractor
```

Distinct decision rule:

```yaml
decision_rule: >
  Use this persona only when the requested work is source preparation for
  section-level downstream processing: raw/clean alignment, semantic sectioning,
  transcript/OCR cleanup notes, alias repair candidates, or section JSONL. Use
  the generic extractor persona for ordinary PDF/table/control/entity extraction
  that does not require this source-prep JSONL contract.
```

Core evidence rule:

```yaml
instructions:
  - Treat raw_text plus source span or offset as the evidence source.
  - Treat cleaned_text, summaries, alias repairs, and detected entities as helper annotations only.
  - Preserve raw form, normalized candidate, confidence, rationale, and a not_canonical_proof warning for every alias repair candidate.
  - Quarantine rather than accept sections with broken offsets, missing raw spans, unverifiable OCR repairs, unverifiable transcript repairs, or over-normalized cleaned text.
```

Section sizing policy:

```yaml
section_policy:
  target_size:
    chars_min: 1500
    chars_target: 6000
    chars_max: 16000
  overlap_policy:
    default_overlap_chars: 0
    allow_overlap_when: continuity_requires_boundary_context
    max_overlap_chars: 800
  mandatory_resegmentation_when:
    - section_exceeds_chars_max
    - section_mixes_unrelated_scenes
    - section_has_no_stable_label
    - downstream_consumer_reports_context_window_pressure
```

Required section fields:

```yaml
section_jsonl_contract:
  schema_version: persona_source_section.v1
  required_fields:
    - schema_version
    - source_id
    - section_id
    - section_kind
    - source_label
    - source_hash
    - source_artifact_id
    - extractor_run_id
    - raw_text_sha256
    - cleaned_text_sha256
    - offset_unit
    - start_offset
    - end_offset
    - raw_text
    - cleaned_text
    - detected_entities
    - alias_candidates
    - repair_notes
    - validation_status
    - warnings
```

Forbidden outputs:

```yaml
forbidden_outputs:
  - canonical_lore_facts
  - theory_of_mind_states
  - relationship_states
  - style_notes
  - canon_rules
  - qra_pairs
  - arango_upserts
  - qdrant_points
  - final_assurance_verdicts
```

### `doc-qra`

Primary skills:

```yaml
primary_skills:
  - memory
  - doc2qra
```

Core rules:

```yaml
instructions:
  - Use doc2qra as the runnable QRA engine.
  - Prefer doc2qra --from-extractor when extractor output is available.
  - Prefer dry-run mode for review or proof phases before storing memory lessons.
  - Run one doc2qra process at a time; do not launch parallel doc2qra processes.
  - Treat QRA pairs as recall aids only, not final canon facts, Theory-of-Mind states, relationship states, or graph-ready lore records.
  - Do not hand-craft or alter QRA prompts; doc2qra prompt changes require prompt-lab validation.
```

Receipt contract:

```yaml
qra_receipt_contract:
  required_fields:
    - source_artifact_ids
    - doc2qra_run_id
    - scope
    - collection
    - dry_run
    - summary_artifact
    - qra_pairs_artifact
    - extracted_count
    - stored_count
    - skipped_count
    - validator_verdict
    - grounding_threshold
    - memory_receipt
```

Allowed helper relationship:

```yaml
help_policy:
  allowed_patterns:
    - helper_agent: doc-extractor
      use_when:
        - broken_offsets
        - missing_raw_span
        - over_normalized_cleaned_text
        - ambiguous_alias_repair
        - sections_too_large_or_small
        - missing_stable_section_labels
      example: "$ask doc-extractor to resegment source sections with extractor@v1 on artifacts/source-prep/source-001"
```

Forbidden outputs:

```yaml
forbidden_outputs:
  - source_section_jsonl
  - raw_clean_alignment_repairs
  - canonical_lore_facts
  - theory_of_mind_states
  - relationship_states
  - style_notes
  - canon_rules
  - arango_lore_upserts
  - qdrant_points
  - sparta_qra_storage
  - final_assurance_verdicts
```

## Reviewer Questions

1. Do the implemented contracts satisfy the Phase 0 corrections?
2. Is the distinction between generic `extractor` and `doc-extractor` now clear
   enough to justify a top-level persona?
3. Is the `doc-qra -> doc-extractor` helper relationship bounded enough?
4. Are there any required contract fields or forbidden outputs still missing?
