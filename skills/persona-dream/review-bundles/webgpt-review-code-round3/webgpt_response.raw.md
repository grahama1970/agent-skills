{
"verdict": "needs_changes",
"blocking_findings": [
{
"file": "skills/persona-dream/scripts/validate_panel_repair_gate.py",
"issue": "Provider voice source receipts are only checked for existence and JSON-object parseability, not for matching provider voice_id evidence.",
"why_it_matters": "A voiced panel can set voice_id_status=PROVIDER_VOICE_ID_READY and provide provider_voice_ids.voice_1.source_receipt pointing at any JSON object, such as the requirement matrix, while the validator accepts the claimed provider and voice_id from the main receipt. That leaves the round-2 assertion-only voice readiness blocker only partially repaired.",
"required_change": "When voice_id_status=PROVIDER_VOICE_ID_READY and --require-provider-eligible is used, require each source_receipt to contain minimal matching evidence: a PASS/READY status or verdict, the same provider, the same voice_id, and ideally the matching voice token. Add a fixture where source_receipt exists and is valid JSON but does not contain the claimed provider voice_id, and assert validation fails."
},
{
"file": "skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json",
"issue": "The schema still diverges from the validator because required fields are missing property definitions and type constraints.",
"why_it_matters": "The schema requires fields such as callback_or_polling_plan, cost_estimate, requirement_matrix, script_coverage_receipt, post_generation_script_coverage_receipt, reference_receipt, generation_receipt, visual_review_receipt, and no_overlay_receipt, but those fields are not defined under properties. With additionalProperties=true, a schema-only consumer can accept null, numbers, or arbitrary objects where the validator requires non-empty paths and JSON receipt artifacts. This leaves the schema weaker than the validator, which was a round-2 blocking finding.",
"required_change": "Add explicit property definitions for every required field. At minimum, make all receipt-path fields, callback_or_polling_plan, and cost_estimate non-empty strings. Update check_panel_repair_gate_schema_consistency.py to fail when any required field lacks a property definition or when validator-required string fields are not typed as strings with minLength >= 1. Add invalid schema fixtures or a unit check proving null callback_or_polling_plan/cost_estimate and missing receipt path types are rejected by the schema."
}
],
"non_blocking_findings": [
{
"file": "skills/persona-dream/scripts/validate_panel_repair_gate.py",
"issue": "The validator main path assumes the top-level receipt is a JSON object.",
"why_it_matters": "A non-object JSON receipt would likely raise an AttributeError instead of returning the normal structured FAIL payload. This is fail-closed at process level but less useful for orchestration.",
"suggestion": "After json.loads, explicitly check isinstance(receipt, dict) and return a JSON FAIL with a clear error."
}
],
"patch_suggestions": [
"Extend status_matches or add a voice_source_matches helper that validates voice source receipts independently from panel subgate receipts.",
"Make the schema consistency check compare required fields, property presence, expected string/object/array/boolean types, and enum parity for status fields.",
"Add a valid voiced fixture, not only a silent-scene fixture, so provider voice readiness has a positive-control test."
],
"tests_to_run": [
"bash skills/persona-dream/sanity.sh",
"A new invalid voiced fixture where provider_voice_ids.voice_1.source_receipt points to a valid JSON object without the claimed provider/voice_id must fail.",
"A new valid voiced fixture with source_receipt containing matching provider, voice_id, token, and PASS/READY status must pass under --require-provider-eligible.",
"A schema consistency test must fail if any required schema field is absent from properties.",
"A schema validation test must reject null or non-string callback_or_polling_plan, cost_estimate, and required receipt-path fields."
],
"do_not_do": [
"Do not proceed to live Kling/provider execution.",
"Do not treat a provider_voice_ids entry as evidence unless its source_receipt contains matching provider voice_id proof.",
"Do not use panel_repair_gate_receipt.schema.json as an independent acceptance gate until required field property definitions and types match the validator."
],
"aggregation_ready": false,
"missing_evidence": [
"No positive-control voiced fixture proves concrete provider voice_id evidence is accepted only when backed by a matching source receipt.",
"No negative fixture proves an existing but irrelevant source_receipt fails voice readiness.",
"No schema consistency evidence proves every required validator field is defined with matching type constraints in the JSON schema."
]
}
<<<WEBGPT_DONE:20260614T031832Z:ab763144>>>
