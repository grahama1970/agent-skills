{
"verdict": "needs_changes",
"blocking_findings": [
{
"file": "agents/casting-agent/AGENTS.md",
"issue": "The casting-agent contract hardcodes the preferred story visual package keys to Horus/Embry/Tyranids-specific entities even though persona-dream and the new panel-repair gate are supposed to be persona-agnostic.",
"why_it_matters": "persona-dream-panel-repair-gate composes casting-agent. A downstream worker using this contract can incorrectly require or preserve Horus/Embry-specific entities in unrelated persona dreams, violating the requirement that the gate derive characters, props, weather, memory cues, and references from the active story contract.",
"required_change": "Replace the hardcoded preferred package key list with generic schema examples such as characters.<character_id>, creatures.<creature_id>, scenery.<environment_id>, props.<prop_id>, and state explicitly that Horus/Embry keys are fixture examples only, not required schema keys."
},
{
"file": "agents/persona-dream-panel-repair-gate/AGENTS.md",
"issue": "The final panel status enum mixes intermediate pass states with final acceptance states: PASS_SCRIPT_COVERAGE and PASS_REFERENCE_EVIDENCE are listed as exact final panel statuses alongside PASS_VISUAL_REVIEW.",
"why_it_matters": "A project agent or join gate could treat any PASS_* status as sufficient and advance a panel that has only passed script or reference evidence but has not passed generated-image visual review/no-overlay/provider-media checks. This reopens the unreviewed-panel and report-only false progress failure mode.",
"required_change": "Use a single final acceptance status such as PASS_PANEL_REVIEWED or PASS_VISUAL_REVIEW, and move script/reference/no-overlay checks into explicit subgate fields. Provider eligibility must require all subgates PASS plus visual_review_status PASS, not merely any PASS_* final status."
},
{
"file": "agents/persona-dream-panel-repair-gate/AGENTS.md",
"issue": "The contract requires a pre-generation script coverage gate but does not require a distinct post-generation script/realism re-check receipt after the rendered image introduces new visible facts or omits required facts.",
"why_it_matters": "The observed failure mode included image outputs that changed scene contents after generation. Without a required post-generation script coverage receipt, a worker can regenerate an image, write only visual_review_receipt.json, and still leave introduced props, surfaces, weather behavior, or persona-memory cues unexplained before provider packaging.",
"required_change": "Add a required post_generation_script_coverage_receipt.json, or require script_coverage_receipt.json to contain pre_generation and post_generation sections. The receipt must fail if the generated image adds or omits important visible elements that are not reflected in the repaired script, realism ledger, and prompt delta."
},
{
"file": "agents/persona-dream-panel-repair-gate/AGENTS.md",
"issue": "The gate is still prose-only; there is no minimal machine-readable schema or fixture validator for the panel repair receipt and provider-readiness transition.",
"why_it_matters": "The next phase depends on a subagent contract preventing false readiness. Without at least a JSON schema or validator test for required receipts, final status semantics, provider_eligibility, media URL/hash requirements, voice_id requirements, and mode defaults, the orchestrator can accept a malformed or ambiguous receipt.",
"required_change": "Before using this as the controlling gate, add the smallest deterministic validator or schema test for the required output object: reject missing visual_review_receipt, no_overlay_receipt, source/reference receipts, post-generation script coverage, media URL/hash, provider voice_id for voiced scenes, callback/polling plan, external_task_id, and non-std/720p defaults unless explicitly waived."
}
],
"non_blocking_findings": [
{
"file": "agents/persona-dream-panel-repair-gate/AGENTS.md",
"issue": "The example run_id and paths are Horus/Embry-specific.",
"why_it_matters": "This is acceptable as an example, but after fixing the casting-agent hardcoding, the examples should be labeled as fixtures to avoid future schema drift."
}
],
"patch_suggestions": [
"In agents/persona-dream-panel-repair-gate/AGENTS.md, replace the Stop Conditions pass states with subgate fields: script_coverage_status, reference_evidence_status, visual_review_status, no_overlay_status, provider_media_status, and final status PASS_PANEL_REVIEWED|BLOCKED_...",
"Add provider-readiness fields to the required output: provider_media_urls, media_hashes, provider_mode, provider_resolution, callback_or_polling_plan, external_task_id, voice_id_status, cost_estimate, and provider_packet_status.",
"Add explicit language that provider_eligibility must be false unless final status is PASS_PANEL_REVIEWED and all required provider fields are present."
],
"tests_to_run": [
"Add a non-Horus fixture work order using different persona/entity ids and assert the requirement matrix does not require horus, embry, tyranids, patio_table, or other fixture-specific keys.",
"Add a fixture receipt with status PASS_SCRIPT_COVERAGE but missing visual_review_receipt/no_overlay_receipt and assert the provider gate rejects it.",
"Add a fixture where a regenerated image introduces a new visible prop/weather effect not covered by the script and assert post_generation_script_coverage blocks.",
"Add a fixture with a rectangular/pasted overlay and assert no_overlay_receipt fails and provider_eligibility remains false.",
"Add a provider packet fixture with local voice candidates but no provider voice_id, local media paths but no provider-accessible URLs/hashes, no callback/polling plan, no external_task_id, and pro/4K mode; assert it blocks."
],
"do_not_do": [
"Do not proceed to live Kling/provider execution.",
"Do not accept pasted overlays or report-only repairs.",
"Do not treat Horus/Embry fixture keys as required schema keys.",
"Do not mark provider packets ready from file existence, prompt text, or DOM/report display alone.",
"Do not accept voiced provider payloads from local voice clone candidates without provider voice_id values."
],
"aggregation_ready": false,
"missing_evidence": [
"No machine-readable panel repair receipt schema or validator was supplied.",
"No deterministic fixture proves non-Horus/persona-agnostic behavior.",
"No fixture proves PASS_SCRIPT_COVERAGE or PASS_REFERENCE_EVIDENCE cannot be mistaken for final panel readiness.",
"No fixture proves post-generation script coverage reruns after introduced or omitted visible elements.",
"No fixture proves provider packet rejection for missing URLs, hashes, voice_id, callback/polling, external_task_id, or std/720p defaults."
]
}
