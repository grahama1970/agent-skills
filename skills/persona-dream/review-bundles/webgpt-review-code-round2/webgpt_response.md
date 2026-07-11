{
"verdict": "needs_changes",
"blocking_findings": [
{
"file": "skills/persona-dream/scripts/validate_panel_repair_gate.py",
"issue": "Provider voice readiness can be accepted without any actual provider voice_id evidence. The validator treats voice_id_status=PROVIDER_VOICE_ID_READY as sufficient, but the receipt schema/output contract does not require a provider voice-id map, voice manifest, or parsed voice receipt containing concrete provider voice_id values.",
"why_it_matters": "The review requirement says voice clone candidates without provider voice_id must block voiced provider payloads. A worker can currently set voice_id_status=PROVIDER_VOICE_ID_READY and pass --require-provider-eligible with no provider voice IDs at all, which could allow a voiced Kling/provider packet to advance on an assertion rather than evidence.",
"required_change": "Add a required evidence field for voiced scenes, for example provider_voice_ids or voice_identity_receipt. The validator must require either voice_id_status=SILENT_SCENE or a non-empty provider voice_id for every required voice token. Add a fixture where voice_id_status=PROVIDER_VOICE_ID_READY but no provider voice IDs are present and assert validation fails."
},
{
"file": "skills/persona-dream/scripts/validate_panel_repair_gate.py",
"issue": "The validator only checks that receipt-path fields are non-empty strings; it does not require referenced receipts to exist or contain matching PASS/FAIL evidence.",
"why_it_matters": "A panel can pass by declaring visual_review_status=PASS, no_overlay_status=PASS, post_generation_script_coverage_status=PASS, and reference_evidence_status=PASS while pointing visual_review_receipt, no_overlay_receipt, post_generation_script_coverage_receipt, and reference_receipt at nonexistent or unparseable files. That leaves unreviewed panels, pasted overlays, missing source anchors, and missing post-generation realism checks enforceable only by prose, not by the deterministic gate.",
"required_change": "Under --require-provider-eligible, resolve required receipt paths relative to the receipt file or an explicit artifact root, require each file to exist and parse as JSON, and require minimal matching status fields for script coverage, post-generation coverage, reference evidence, visual review, and no-overlay review. Add fixtures with missing or corrupt visual/no-overlay/post-generation/reference receipts that must fail."
},
{
"file": "skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json",
"issue": "The JSON schema is weaker than the validator and omits provider-readiness fields from required, including provider_media_urls, media_hashes, callback_or_polling_plan, and cost_estimate.",
"why_it_matters": "The bundle presents the schema as a machine-readable gate artifact, but a schema-only consumer could accept provider receipts that the validator rejects. This creates two incompatible contracts for the same panel gate and weakens orchestration safety.",
"required_change": "Synchronize the schema with validate_panel_repair_gate.py: require provider_media_urls, media_hashes, callback_or_polling_plan, cost_estimate, and any new provider_voice_ids/voice receipt field. Add a deterministic schema/validator consistency test or run the invalid fixtures through both gates."
}
],
"non_blocking_findings": [
{
"file": "skills/persona-dream/scripts/validate_panel_repair_gate.py",
"issue": "--require-provider-eligible checks the computed hard_pass but does not require provider_eligibility itself to be true.",
"why_it_matters": "This is fail-closed for execution if callers also inspect provider_eligibility, but it is surprising for a flag named --require-provider-eligible.",
"suggestion": "When --require-provider-eligible is set, also require provider_eligibility is true, or rename the flag to --require-hard-pass."
}
],
"patch_suggestions": [
"Add receipt_artifact_root or infer artifact root from the panel receipt path so validator path checks are deterministic and do not depend on cwd.",
"Make the valid fixture include small real JSON receipt files in a fixture directory rather than /tmp placeholder paths.",
"Add provider_voice_ids as an object keyed by voice token, with values containing provider, voice_id, source_receipt, and hash or version where available."
],
"tests_to_run": [
"bash skills/persona-dream/sanity.sh",
"uv run --project skills/persona-dream python skills/persona-dream/scripts/validate_panel_repair_gate.py <valid fixture with real receipt artifacts> --require-provider-eligible",
"A new invalid fixture with voice_id_status=PROVIDER_VOICE_ID_READY but no provider_voice_ids must fail.",
"A new invalid fixture with PASS_PANEL_REVIEWED and nonexistent visual_review_receipt/no_overlay_receipt/post_generation_script_coverage_receipt/reference_receipt must fail.",
"A schema consistency test must assert all fields required by the validator for provider eligibility are present in panel_repair_gate_receipt.schema.json required fields."
],
"do_not_do": [
"Do not proceed to live Kling/provider execution.",
"Do not treat provider_voice_id readiness as satisfied from a status string alone.",
"Do not accept panel readiness when review receipt paths are placeholders, missing, or unparseable.",
"Do not use the JSON schema as an independent acceptance gate until it is synchronized with the validator."
],
"aggregation_ready": false,
"missing_evidence": [
"No deterministic fixture proves voiced scenes require concrete provider voice_id values.",
"No deterministic fixture proves missing or corrupt visual/no-overlay/post-generation/reference receipts fail.",
"No evidence that the JSON schema and validator enforce the same required provider-readiness fields."
]
}
