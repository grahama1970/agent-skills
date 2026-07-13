## Task

Read `requirements.json` and return one JSON object conforming exactly to
`f36.webgpt_complete_family_batch.v1`. Produce exactly one complete family for
every exported requirement, in the same order. Do not omit, duplicate, merge,
or invent a requirement.

## Closed top-level schema

```json
{
  "schema": "f36.webgpt_complete_family_batch.v1",
  "export_id": "exact requirements.json export_id",
  "canonical_input_sha256": "exact requirements.json canonical_input_sha256",
  "synthetic": true,
  "operational_authority": false,
  "certification_authority": false,
  "families": []
}
```

No other top-level fields are permitted.

## Closed family schema

Each `families[]` item must contain exactly:

```json
{
  "schema": "f36.webgpt_complete_family.v1",
  "stable_item_id": "exact exported value",
  "engineering_qra_family_id": "exact exported value",
  "engineering_obligation_id": "exact exported value",
  "requirement_id": "exact exported value",
  "requirement_revision_id": "exact exported value",
  "requirement_content_hash": "exact exported value",
  "primary_component_family_id": "exact exported value",
  "canonical_question": "one grammatical engineering question",
  "canonical_answer": "one nonempty engineering answer",
  "canonical_intent": {
    "engineering_obligation_id": "exact exported value",
    "primary_component_family_id": "exact exported value",
    "protected_object_or_interface": "source-derived text",
    "condition": "source-derived text",
    "required_behavior": "source-derived text",
    "expected_outcome": "source-derived text",
    "source_fragments": {
      "protected_object_or_interface": "exact contiguous fragment from source title, statement, or rationale",
      "condition": "exact contiguous fragment from source title, statement, or rationale",
      "required_behavior": "exact contiguous fragment from source title, statement, or rationale",
      "expected_outcome": "exact contiguous fragment from source title, statement, or rationale"
    }
  },
  "variants": [],
  "synthetic": true,
  "operational_authority": false,
  "certification_authority": false,
  "engineering_qra_state": "generated_candidate",
  "sparta_applicability": "not_assessed",
  "sparta_resolution": "not_run",
  "resolved_control_ids": [],
  "crosswalk_chain_ids": [],
  "evidence_case_id": null
}
```

No other family or nested fields are permitted.

## Five required variants

Return exactly the five exported variant IDs in this exact order:

1. `operator` / `simple`
2. `project_manager` / `simple`
3. `systems_engineer` / `medium`
4. `cybersecurity_compliance_officer` / `medium`
5. `mission_assurance_cybersecurity_reviewer` / `advanced`

Each variant must contain exactly:

```json
{
  "variant_id": "exact exported value",
  "role": "exact exported role",
  "difficulty": "exact exported difficulty",
  "question": "unique grammatical question",
  "answer": "byte-identical copy of canonical_answer",
  "intent_hash": "sha256 of canonical_intent using sorted compact UTF-8 JSON"
}
```

The canonical question and all five variants must ask about the same bounded
engineering obligation. Each question and the canonical answer must preserve
anchors for the source-derived object/interface, condition, required behavior,
and expected outcome. Different audiences may receive different wording, but
not a different condition, object, behavior, outcome, threshold, or obligation.

## Prohibited content

- Do not introduce SPARTA, control IDs, crosswalks, techniques, evidence cases,
  findings, hazards, or acceptance decisions.
- Do not invent component IDs, numeric thresholds, test results, evidence,
  certification, approval, operational claims, conditions, behaviors, objects,
  outcomes, or obligations absent from the exported source record.
- Do not promote authority or change any immutable ID, owner, revision, or hash.
- Do not return prose outside the JSON artifact.

A malformed, missing, duplicate, expanded, authority-bearing, or partially
complete batch will be rejected atomically. Human review remains mandatory.
