# Round 2 Review: Persona-Dream Panel Repair Gate

## Reviewer Instructions

Review this as a code review request for Web GPT or another external reviewer.
Focus on correctness, regression risk, security, maintainability, test coverage, and mismatches between the stated intent and the actual diff.
Do not rewrite the entire implementation unless the diff is fundamentally unsafe.
Return findings first, grouped by severity, with concrete file/function references where possible.


## Decision Needed

Were the round-1 blocking findings repaired well enough to use the panel repair gate for the next phase?

## Rationale And Context

# Review Context Round 2: Persona-Dream Panel Repair Gate

## Objective

Round 1 WebGPT review returned `needs_changes`. This round asks whether the
blocking findings were repaired well enough to use the subagent contract and
validator as the next controlling gate for panel regeneration and Kling
preflight repair.

## Round 1 Blocking Findings

1. `agents/casting-agent/AGENTS.md` hardcoded Horus/Embry/Tyranids package keys.
2. `agents/persona-dream-panel-repair-gate/AGENTS.md` mixed intermediate pass
   statuses with final acceptance statuses.
3. The panel gate lacked a distinct post-generation script/realism receipt.
4. The gate was prose-only and lacked deterministic schema/validator coverage.

## Repairs Made

1. `agents/casting-agent/AGENTS.md`
   - Replaced hardcoded `characters.horus`, `characters.embry`,
     `creatures.tyranids`, and prop keys with generic entity-key patterns:
     `characters.<character_id>`, `creatures.<creature_id>`,
     `scenery.<environment_id>`, `props.<prop_id>`, `objects.<object_id>`,
     and `vehicles.<vehicle_id>`.
   - Explicitly states that Horus/Embry/Tyranids keys are fixture examples only.

2. `agents/persona-dream-panel-repair-gate/AGENTS.md`
   - Replaced partial final pass states with one normal final pass:
     `PASS_PANEL_REVIEWED`.
   - Moved script/reference/visual/no-overlay/provider checks into explicit
     subgate fields.
   - Added `post_generation_script_coverage_receipt.json`.
   - Added required provider fields: URLs, hashes, mode, resolution, callback or
     polling plan, external task ID, voice ID status, cost estimate, and provider
     packet status.
   - States that `provider_eligibility` stays false unless final status is
     `PASS_PANEL_REVIEWED` and every required subgate/provider field passes.

3. `skills/persona-dream/SKILL.md`
   - Added the validator command to the panel continuity/self-repair gate.
   - Clarified that `PASS_SCRIPT_COVERAGE`, `PASS_REFERENCE_EVIDENCE`, and
     `PASS_VISUAL_REVIEW` are rejected as final panel statuses.

4. New deterministic gate artifacts
   - `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`
   - `skills/persona-dream/scripts/validate_panel_repair_gate.py`
   - `skills/persona-dream/scripts/fixtures/panel_repair_gate_valid.json`
   - `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json`
   - `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json`

## Local Verification

Command:

```bash
bash skills/persona-dream/sanity.sh
```

Result:

- Static dream sanity: `status: ok`.
- Video-plan sanity: `status: ok`.
- Storyboard-first regression fixture: `status: ok`.
- `panel_repair_gate_valid.json` passed with `--require-provider-eligible`.
- `panel_repair_gate_invalid_partial_pass.json` failed as expected, including:
  - `PASS_SCRIPT_COVERAGE is an intermediate subgate, not a final panel status`
  - missing post-generation script coverage
  - missing visual/no-overlay receipts
  - missing provider URLs/hashes/callback/cost
- `panel_repair_gate_invalid_provider_fields.json` failed as expected, including:
  - non-std/720p default rejection
  - missing external task ID
  - missing callback/polling plan
  - local-only provider media URL
  - missing provider voice ID

## Decision Requested

Do these repairs satisfy the round-1 blocking review enough to proceed to the
next phase: using the panel repair gate to repair the current blocked
storyboard panels and Kling dry-run packet?

Return `needs_changes` if any blocking contract problem remains. Return
`satisfied` only if this gate is adequate for that next phase. This is not a
request to approve live Kling execution.


## Expected Safety Contract

Final readiness uses PASS_PANEL_REVIEWED only; script/reference/visual/no-overlay/provider checks are subgates.

Post-generation script coverage is mandatory after image generation changes visible facts.

The deterministic validator rejects partial pass statuses, missing post-generation coverage, local-only media URLs, missing hashes, missing provider voice IDs, missing callback/polling plan, missing external_task_id, and non-std/720p defaults without waiver.


## Prior Critique Being Rechecked

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


## Non-goals For This Review

Do not approve live Kling execution.

Do not review unrelated dirty worktree changes.


## Original Review Request

(No request file supplied; review the current repository changes.)

## Repository Snapshot

- Generated at: `2026-06-14T02:49:35.423856+00:00`
- Working directory: `/home/graham/workspace/experiments/agent-skills`
- Repository root: `/home/graham/workspace/experiments/agent-skills`
- Branch: `feat/webgpt-no-activate`
- Remote: `git@github.com:grahama1970/agent-skills.git`

## Git Status

```text
?? agents/casting-agent/AGENTS.md
?? agents/persona-dream-panel-repair-gate/AGENTS.md
?? skills/persona-dream/SKILL.md
?? skills/persona-dream/sanity.sh
?? skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json
?? skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json
?? skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json
?? skills/persona-dream/scripts/fixtures/panel_repair_gate_valid.json
?? skills/persona-dream/scripts/validate_panel_repair_gate.py
```

## Selected Review Files

These are the files intentionally selected for external review. Do not expand scope just because other files are changed in the worktree.

- `agents/casting-agent/AGENTS.md`
- `agents/persona-dream-panel-repair-gate/AGENTS.md`
- `skills/persona-dream/SKILL.md`
- `skills/persona-dream/sanity.sh`
- `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`
- `skills/persona-dream/scripts/validate_panel_repair_gate.py`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_valid.json`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json`

## Changed Files In Selected Scope

- `agents/casting-agent/AGENTS.md`
- `agents/persona-dream-panel-repair-gate/AGENTS.md`
- `skills/persona-dream/SKILL.md`
- `skills/persona-dream/sanity.sh`
- `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_valid.json`
- `skills/persona-dream/scripts/validate_panel_repair_gate.py`

## Diff

```diff
diff --git a/agents/casting-agent/AGENTS.md b/agents/casting-agent/AGENTS.md
new file mode 100644
index 000000000..1423a8f68
--- /dev/null
+++ b/agents/casting-agent/AGENTS.md
@@ -0,0 +1,116 @@
+---
+id: casting-agent
+kind: worker
+title: Casting agent
+surface: opencode_transport
+transport_role: explore
+opencode_agent: explore
+mode: propose_patches
+composes:
+- casting-agent
+- memory
+- brave-search
+- contact-sheet
+- best-practices-kling-contact-sheet
+- create-image
+- scillm
+- persona-dream
+consult_personas: []
+icon: search-check
+---
+
+# Casting Agent
+
+Researches and decides visual casting for story entities, then produces or
+orchestrates contact-sheet work orders.
+
+## Mission
+
+Given story context, extracted entities, and optional provided reference image
+paths, produce accepted visual casting contracts and drive the contact-sheet
+loop until all required visual packs are accepted or blocked with evidence.
+
+## Inputs
+
+- Preferred: `story_visual_package.json` with `schema:
+  persona_dream.story_visual_package.v1`.
+- Compatibility: `story_contract.md`, screenplay, or storyboard plus
+  `visual_entities.json`.
+- Optional context text for time, state, mood, and story role.
+- Optional reference image paths or URLs per entity.
+- Optional prior asset/memory recall instructions.
+
+The preferred package must use stable keys for every visual thing:
+
+```text
+characters.<character_id>.description
+creatures.<creature_id>.description
+scenery.<environment_id>.description
+props.<prop_id>.description
+objects.<object_id>.description
+vehicles.<vehicle_id>.description
+```
+
+Fixture-specific names such as `horus`, `embry`, `tyranids`, `patio_table`,
+`umbrella`, `tea_service`, and `sparta_device` are examples from one
+Horus/Embry dry-run only. They are not required schema keys. Preserve whatever
+stable entity IDs the active story contract supplies.
+
+Each keyed entity may include `image_file_paths`, `document_paths`, and
+`source_urls`. Treat embedded `image_file_paths` as provided references.
+
+## Required Behavior
+
+1. Read the story and entity contract.
+2. If a story visual package is provided, preserve its keyed entity structure
+   and normalize it into casting artifacts.
+3. Prefer provided reference images when present, including package-embedded
+   `image_file_paths`.
+4. Use `memory` to recall accepted prior assets when requested or useful.
+5. Use `brave-search` only for missing or insufficient references.
+6. Include state/time/mood in search queries and casting decisions.
+   Example: `pre-Heresy Horus Lupercal smiling charismatic`.
+7. Write or request:
+   - `casting_contract.json`
+   - `chosen_reference_inputs.json`
+   - `contact_sheet_work_order.json`
+8. Delegate panel generation and sheet assembly to `contact-sheet`.
+9. Apply `best-practices-kling-contact-sheet` to every Kling-ready Element.
+10. Review generated sheets against the casting contract.
+11. Retry bounded failures, then emit accepted or blocked receipts.
+
+## Limits
+
+- Do not call paid video providers.
+- Do not write memory/Qdrant directly; use `memory` or `contact-sheet`.
+- Do not treat Brave rank 1 as automatically correct.
+- Do not accept a contact sheet from file existence alone; inspect the sheet or
+  require a visual review receipt.
+- Stop if identity cannot be satisfied within retry budget.
+
+## Default Retry Budget
+
+```text
+max_search_rounds: 3
+max_generation_rounds_per_entity: 2
+max_review_rounds: 2
+```
+
+## Output Standard
+
+Return an operational snapshot with exact artifact paths, entity counts,
+reference counts, accepted/blocked status, and the next command or stop
+condition.
+
+## Post-run verification (mandatory when `runtime_self_improvement: substantial`)
+
+When this worker runs a substantial job with a durable output/job directory:
+
+1. Run `./run.sh verify --job-dir <job>` (or skill-specific verify documented in SKILL.md).
+2. **PASS** → continue handoff.
+3. **FAIL** → `./run.sh file-maintainer-ticket --job-dir <job> --create` — do **not** self-commit.
+
+WebGPT review belongs in the **skill-maintainer** cycle, not after every successful run.
+
+Rollout: see `skills/best-practices-skills/references/runtime-self-improvement.md`.
+Reference implementation: `skills/voice-segment-selector/references/maintainer-escalation.md`.

diff --git a/agents/persona-dream-panel-repair-gate/AGENTS.md b/agents/persona-dream-panel-repair-gate/AGENTS.md
new file mode 100644
index 000000000..c0b3a616f
--- /dev/null
+++ b/agents/persona-dream-panel-repair-gate/AGENTS.md
@@ -0,0 +1,240 @@
+---
+id: persona-dream-panel-repair-gate
+kind: worker
+title: Persona dream panel repair gate
+surface: opencode_transport
+transport_role: patch
+opencode_agent: build
+mode: workspace_write
+composes:
+- persona-dream
+- best-practices-script-writer
+- best-practices-self-improvement-loop
+- best-practices-kling-scene
+- best-practices-kling-contact-sheet
+- memory
+- brave-search
+- casting-agent
+- contact-sheet
+- create-storyboard
+- create-image
+- scillm
+consult_personas: []
+icon: scan-eye
+---
+
+# Persona Dream Panel Repair Gate
+
+Owns second-pass storyboard panel repair for `persona-dream` before a panel can
+enter a Kling/provider packet. This worker exists because generated images are
+non-deterministic: a panel can look plausible while still missing required
+characters, props, environmental physics, source-reference anchors, or script
+beats.
+
+## Mission
+
+Given a story contract, accepted references, panel script, generated panel image,
+and current failure ledger, run a bounded repair loop until the panel is either
+accepted with receipts or blocked with exact failed requirements.
+
+The worker must reduce orchestrator cognitive load. The project agent should be
+able to pass a compact work order and receive a clear panel verdict, repair
+artifacts, and the exact next stop condition.
+
+## Inputs
+
+Preferred work order:
+
+```json
+{
+  "run_id": "fixture-dream-run",
+  "panel_id": "panel_01",
+  "story_contract_path": "/absolute/path/story_contract.json",
+  "timed_beats_path": "/absolute/path/timed_beats.json",
+  "panel_script_path": "/absolute/path/panel_01_script.json",
+  "panel_image_path": "/absolute/path/panel_01.png",
+  "story_visual_package_path": "/absolute/path/story_visual_package.json",
+  "reference_manifest_path": "/absolute/path/accepted_references.json",
+  "persona_memory_manifest_path": "/absolute/path/persona_memory_receipts.json",
+  "brave_reference_manifest_path": "/absolute/path/brave_reference_receipts.json",
+  "continuity_ledger_path": "/absolute/path/panel_continuity_and_repair_ledger.json",
+  "provider_constraints_path": "/absolute/path/kling_provider_constraints.json",
+  "max_attempts": 4
+}
+```
+
+Compatibility inputs may be markdown or HTML report sections, but the worker
+must normalize them into a machine-readable requirement matrix before repair.
+The example values above are generic fixtures. A real work order must preserve
+the active run's actual story-derived entity IDs and must not require
+Horus/Embry/Tyranid-specific keys unless that specific story contract requires
+them.
+
+## Required Behavior
+
+1. Load the story, panel script, visual package, references, current panel image,
+   and prior failure ledger.
+2. Build `panel_requirement_matrix.json` with stable keys for every required:
+   - character, creature, environment, prop, vehicle/object, weather condition,
+     temperature cue, visible memory/ToM beat, sound cue, camera cue, and Kling
+     provider reference token.
+3. Run the pre-generation script coverage gate from
+   `best-practices-script-writer`:
+   - every visible or required object must have material state, motion/change
+     over time, lighting response, environmental interaction, and imperfection;
+   - every living/organic subject must have skin/body/eye/breathing or contact
+     realism cues where visible;
+   - weather, wind velocity, temperature, dust/rain/snow/sleet/hail or other
+     atmospheric conditions must be explicit when present;
+   - persona-memory and Theory-of-Mind cues must be present for speaking or
+     emotionally relevant personas when memory receipts exist.
+4. If the script fails, produce `second_pass_script_delta.json` and repair the
+   script before image regeneration. Do not generate a new panel from an
+   underspecified script.
+5. Check source-reference sufficiency:
+   - use project/human-provided references first;
+   - use `memory` for accepted prior assets and persona facts;
+   - use `brave-search` only for missing canon-sensitive references;
+   - record every query, result, chosen source, and rejection reason.
+6. Build a corrective image prompt package for `scillm` / `create-image`.
+   The prompt must include:
+   - exact required entities and their visual anchors;
+   - explicit absence constraints for known failures;
+   - environmental physics for props and weather;
+   - camera/lens/lighting/color lock from `best-practices-kling-scene`;
+   - no text labels, no contact-sheet borders, no pasted overlays.
+7. Generate through the approved image path (`scillm` / `create-image`) and
+   store generation receipts. Do not hand-write or composite final panels.
+8. Post-generation, inspect the rendered image and write
+   `visual_review_receipt.json`.
+9. Run a distinct post-generation script/realism re-check and write
+   `post_generation_script_coverage_receipt.json`. This receipt must compare
+   the repaired script against the actual generated image and fail when the
+   image introduces or omits important visible elements not reflected in the
+   script, realism ledger, and prompt delta.
+10. Reject any panel that:
+   - is missing a required character, prop, environment, creature, or object;
+   - replaces a character with the wrong identity;
+   - uses a pasted overlay or rectangle to satisfy a background element;
+   - stretches, crops, or distorts core subjects in a way that breaks provider
+     continuity;
+   - omits realism cues required by the script;
+   - lacks source-reference or memory receipts for canon/persona-sensitive
+     entities;
+   - lacks panel media URLs or hashes needed by a provider packet.
+11. Update the continuity ledger with the exact status transition and receipts.
+
+## Stop Conditions
+
+Use one of these exact final panel statuses:
+
+```text
+PASS_PANEL_REVIEWED
+HUMAN_ACCEPTED_WITH_WAIVER
+BLOCKED_UNREVIEWED_GENERATION
+BLOCKED_PENDING_INDEPENDENT_VERIFICATION
+BLOCKED_SCRIPT_COVERAGE
+BLOCKED_REFERENCE_EVIDENCE
+BLOCKED_VISUAL_CONTRADICTION
+BLOCKED_OVERLAY_OR_COMPOSITE
+BLOCKED_MAX_ATTEMPTS
+BLOCKED_ARTIFACT_INACCESSIBLE
+BLOCKED_PROVIDER_MEDIA_URLS
+BLOCKED_HUMAN_REVIEW_REQUIRED
+```
+
+Intermediate gates must be recorded in dedicated fields and must not be used as
+final panel status values:
+
+```text
+script_coverage_status: PASS|FAIL|WAIVED
+post_generation_script_coverage_status: PASS|FAIL|WAIVED
+reference_evidence_status: PASS|FAIL|WAIVED
+visual_review_status: PASS|FAIL|WAIVED
+no_overlay_status: PASS|FAIL|WAIVED
+provider_media_status: PASS|FAIL|WAIVED
+```
+
+A panel is provider-eligible only when final `status` is `PASS_PANEL_REVIEWED`
+and every required subgate is `PASS`, or when a human waiver explicitly names
+the failed requirement and downstream risk. A partial pass such as script-only,
+reference-only, or DOM/report-only review must keep `provider_eligibility:
+false`.
+
+## Required Outputs
+
+Return and persist:
+
+```json
+{
+  "run_id": "string",
+  "panel_id": "string",
+  "status": "PASS_PANEL_REVIEWED|HUMAN_ACCEPTED_WITH_WAIVER|BLOCKED_...",
+  "attempt": 1,
+  "max_attempts": 4,
+  "script_coverage_status": "PASS|FAIL|WAIVED",
+  "post_generation_script_coverage_status": "PASS|FAIL|WAIVED",
+  "reference_evidence_status": "PASS|FAIL|WAIVED",
+  "visual_review_status": "PASS|FAIL|WAIVED",
+  "no_overlay_status": "PASS|FAIL|WAIVED",
+  "provider_media_status": "PASS|FAIL|WAIVED",
+  "requirement_matrix": "/absolute/path/panel_requirement_matrix.json",
+  "script_coverage_receipt": "/absolute/path/script_coverage_receipt.json",
+  "post_generation_script_coverage_receipt": "/absolute/path/post_generation_script_coverage_receipt.json",
+  "second_pass_script_delta": "/absolute/path/second_pass_script_delta.json",
+  "reference_receipt": "/absolute/path/reference_receipt.json",
+  "repair_prompt_package": "/absolute/path/repair_prompt_package.json",
+  "generated_image_path": "/absolute/path/panel_01_attempt_02.png",
+  "generation_receipt": "/absolute/path/scillm_generation_receipt.json",
+  "visual_review_receipt": "/absolute/path/visual_review_receipt.json",
+  "no_overlay_receipt": "/absolute/path/no_overlay_receipt.json",
+  "provider_media_urls": ["https://..."],
+  "media_hashes": {"panel": "sha256:..."},
+  "provider_mode": "std",
+  "provider_resolution": "720p",
+  "callback_or_polling_plan": "/absolute/path/callback_or_polling_plan.json",
+  "external_task_id": "project-stable-task-id",
+  "voice_id_status": "PROVIDER_VOICE_ID_READY|SILENT_SCENE|BLOCKED_MISSING_PROVIDER_VOICE_ID",
+  "cost_estimate": "/absolute/path/cost_estimate.json",
+  "provider_packet_status": "BLOCKED_PROVIDER_GATE|DRY_RUN_NOT_LIVE_SUBMITTABLE|PROVIDER_READY",
+  "status_transition_log": "/absolute/path/status_transition_log.jsonl",
+  "provider_eligibility": false,
+  "remaining_blockers": []
+}
+```
+
+## Provider Boundary
+
+This worker never performs a live paid provider call. It may update dry-run
+provider eligibility fields, but live Kling execution remains blocked until the
+`persona-dream` provider final gate passes.
+
+The provider final gate must still verify:
+
+- all panel gates pass;
+- accepted storyboard and reference media are available as provider-accessible
+  URLs or an approved upload plan exists;
+- `mode` defaults to `std` / 720p unless explicitly approved otherwise;
+- `external_task_id` is present;
+- `callback_url` is reachable or a documented polling plan is accepted;
+- every `<<<voice_n>>>` has a provider `voice_id` or the scene is explicitly
+  silent;
+- the cost estimate and retry budget are recorded.
+
+`provider_eligibility` must remain `false` unless final `status` is
+`PASS_PANEL_REVIEWED`, every required subgate is `PASS`, provider media URLs and
+hashes are present, and the provider final gate requirements above are
+represented in receipts.
+
+## Output Standard
+
+Report as an operational snapshot:
+
+- Status/phase.
+- Current panel and artifact paths.
+- Evidence counts: required entities, missing entities, script failures,
+  generation attempts, review receipts.
+- Next stop condition or exact next command.
+
+Do not claim storyboard/provider readiness from file existence, prompt text, or
+DOM/report display alone.

diff --git a/skills/persona-dream/SKILL.md b/skills/persona-dream/SKILL.md
new file mode 100644
index 000000000..3e5ce7692
--- /dev/null
+++ b/skills/persona-dream/SKILL.md
@@ -0,0 +1,732 @@
+---
+name: persona-dream
+description: >
+  Create receipt-backed persona dream packets from memory residue. Use when a
+  persona should dream, reflect, or turn recent memories into persona insight;
+  when create-movie/dream.py feels too heavy for the goal; when the desired
+  output is a prompt, frame prompts, contact sheet, reflection, and memory
+  write receipt rather than a full movie; or when a downstream movie workflow
+  needs a dream_packet.json input.
+triggers:
+  - persona dream
+  - create dream
+  - dream packet
+  - dream from memory
+  - ask persona to dream about
+  - ask <persona> to dream about
+  - memory dream
+  - contact sheet dream
+  - persona insight dream
+provides:
+  - persona-dream-packet
+  - dream-reflection
+  - dream-contact-sheet
+  - memory-write-receipt
+composes:
+  - memory
+  - brave-search
+  - cinematic-technique-selector
+  - create-image
+  - create-movie
+  - create-persona
+complies:
+  - best-practices-skills
+  - best-practices-python
+  - best-practices-scillm
+  - best-practices-arangodb
+taxonomy:
+  - persistence
+  - creativity
+  - reflection
+  - memory
+---
+
+# Persona Dream
+
+Naming note: this skill is evolving toward `agentic-dreams`. The current
+directory/name remains `persona-dream` for compatibility with existing scripts,
+reports, paths, and stored artifacts, but the conceptual scope is automated
+dream-sequence planning for any persona or persona set, not a Horus-specific or
+Embry-specific workflow.
+
+Generate a narrow persona dream work product:
+
+```text
+persona memory residue -> dream packet -> prompt/frame prompts/contact sheet
+-> reflection -> optional memory write receipt
+```
+
+For video work, this skill may also produce a deterministic `video_plan`:
+
+```text
+dream packet -> story -> character/scene bible -> storyboard
+-> timed transcript -> multimodal prompts -> stage report
+```
+
+For Kling/video-oriented runs, insert a Look Lock step before storyboard prompt
+composition. If the scene has dialogue or character conflict, the same selector
+must also emit Script DNA before storyboard prompt composition:
+
+```text
+story + visual entities + memory/project recalls
+-> cinematic-technique-selector
+-> technique_selection.json / look_lock / script_dna / shot_bible
+-> storyboard + Kling scene packet
+```
+
+For experimental persona-dream Kling packets, default provider planning to the
+lowest acceptable review tier such as 720p/std. Higher modes such as 1080p/pro
+or any 4K path require an explicit cost/entitlement gate and current provider
+schema proof before live execution.
+
+This skill is not a full movie director. It owns the dream-specific story,
+storyboard, prompt packet, continuity contract, and short dream-sequence
+receipts. Full screenplay production, audio, score, narration, and polished
+movie review still route to `create-movie`. Minimal FFmpeg stitching is allowed
+only for the bounded short dream-sequence assembly mode after model clip
+receipts exist.
+
+For voiced dream videos, this skill may plan the audio handoff but does not own
+the audio lane:
+
+```text
+timed transcript -> voice_handoff_plan.json -> create-movie/audio-lane
+-> TTS / voice conversion / eval / mix / mux receipts
+```
+
+## Boundary
+
+Own:
+
+- Recall persona-specific memory residue.
+- Preserve source residue ids and scopes.
+- Detect simple tensions or contradictions between residue items.
+- Create a synthetic dream prompt, frame prompts, and contact sheet.
+- In `video_plan` mode, create a dream story, character/scene bible,
+  storyboard, timed transcript, multimodal prompt list, and stage report.
+- In Kling/video-oriented runs, request a structured Look Lock from
+  `$cinematic-technique-selector` so director/camera/lens/lighting/color-grade
+  choices are explicit and stable across shots.
+- In story/dialogue runs, request Script DNA from `$cinematic-technique-selector`
+  so story rhythm, dialogue pressure, conflict pattern, reveal logic, irony, and
+  theme are explicit before storyboard panels are written.
+- In `video_plan` mode, create a `voice_handoff_plan.json` that captures
+  speaker timing, voice identity boundaries, required receipts, and near-term
+  versus future voice lanes.
+- Define continuity checks and self-improvement loop criteria before accepting
+  generated keyframes or I2V clips.
+- Write a short persona reflection.
+- Store the reflection to memory only when explicitly requested.
+- Emit machine-readable receipts for every side effect.
+
+Do not own:
+
+- Full screenplay production, score, TTS, long-form editing, or polished final
+  MP4 review. Use `create-movie`.
+- Voice cloning, voice fine-tuning, line-level TTS rendering, audio mixing, or
+  final audio identity review. Use `create-movie`, `learn-voice`, `train-voice`,
+  `tts-horus`, or a dedicated audio lane as appropriate.
+- Direct provider calls to z-image, Wan, or other renderers outside the
+  explicit ComfyUI receipt path or a documented reviewed exception.
+- Deep external research as a default path. Use `$brave-search` as the normal
+  external lookup for canon-sensitive visual entities, current/fresh context,
+  and raw source receipts. Use `$dogpile` only as an explicit escalation for
+  broader multi-source thematic research, papers/videos/GitHub evidence, or
+  when Brave receipts are insufficient.
+- Persona identity rewrites. One dream may add a dated reflection, not mutate
+  durable identity unless a separate `create-persona` workflow accepts it.
+- Unreceipted memory writes.
+
+## Runtime
+
+```bash
+cd skills/persona-dream
+
+# Positive-control fixture run, no memory side effects.
+./run.sh generate --persona embry --fixture scripts/fixtures/sample_residue.json --output-dir /tmp/persona-dream-smoke
+
+# Live memory recall. Blocks with no_dream if no residue is found.
+./run.sh generate --persona embry
+
+# Live memory recall biased by an explicit topic from "$ask <persona> to dream about X".
+./run.sh generate --persona embry --about "SPARTA evidence cases and orbital telemetry"
+
+# Deterministic 30-second planning run for short dream video generation.
+./run.sh generate \
+  --mode video_plan \
+  --persona horus \
+  --secondary-persona embry \
+  --about "creating the SPARTA Explorer app" \
+  --scene "Horus and Embry have tea under a patio umbrella on a 40k void world while Tyranids play in the background." \
+  --duration-seconds 30
+
+# Live memory recall with explicit memory writeback.
+./run.sh generate --persona embry --write-memory
+```
+
+Default output directory:
+
+```text
+/mnt/storage12tb/skills/persona-dream/outputs/<run-id>/
+```
+
+If `/mnt/storage12tb` is unavailable, pass `--output-dir /tmp/...` explicitly.
+
+## Required Artifacts
+
+Every run writes:
+
+```text
+dream_request.json
+response.json
+```
+
+Successful dream runs also write:
+
+```text
+residue_links.json
+contradiction_report.json
+dream_packet.json
+dream_prompt.txt
+frame_prompts.json
+contact_sheet.png
+dream_reflection.md
+memory_write_receipt.json
+```
+
+`memory_write_receipt.json` must say `skipped` unless `--write-memory` was set
+and the memory API returned a successful response.
+
+`video_plan` runs additionally write:
+
+```text
+dream_story.md
+dream_story.json
+character_scene_bible.json
+technique_selection.json
+script_dna_selection.json
+storyboard.json
+timed_transcript.json
+multimodal_prompts.json
+voice_handoff_plan.json
+pipeline_stage_report.json
+pipeline_stage_report.md
+manifest.json
+```
+
+`voice_handoff_plan.json` must preserve:
+
+```text
+speaker ids
+line timing
+voice identity boundaries
+required audio receipts
+near-term TTS/conversion lane
+future curated-reference/fine-tuning lane
+```
+
+For Embry, actress references may be recorded only as cadence/style direction
+or replaced by authorized/synthetic references. The output voice must be a
+fictional Embry persona voice, not an exact living-actor identity clone.
+
+For a 30-second dream sequence, prefer four 7.5-second shots when the I2V
+backend supports the longer unit:
+
+```text
+4 clips * 7.5 seconds ~= 30 seconds
+121 frames per clip at 24 fps
+```
+
+If the 7.5-second path is unstable, fall back to six 5-second clips:
+
+```text
+6 clips * 5 seconds ~= 30 seconds
+81 frames per clip at 24 fps
+```
+
+## Fail-Closed Rules
+
+- If no residue is recalled, return `blocked` with `reason: no_dream`.
+- If `--about` is provided, use it to bias memory recall and dream prompts; do
+  not treat the topic itself as residue unless memory returns supporting items.
+- Do not fabricate residue. Fixture residue is allowed only for tests and is
+  marked with `source: fixture`.
+- Keep dream text labeled as synthetic.
+- Preserve `source_id`, `scope`, and recall metadata in `residue_links.json`.
+- Treat `$brave-search` receipts as the default external-search evidence when
+  external context is needed.
+- Treat `$dogpile` enrichment as optional escalation and degraded if unavailable.
+- Treat Wan 2.2 or other video renderers as downstream renderers, not the
+  definition of a dream. The planning artifacts must remain useful even if
+  generation fails.
+- Generated actor/public-figure imagery must be labeled synthetic and must not
+  be described as factual identity evidence.
+- If a generated keyframe or clip is inconsistent with the previous accepted
+  scene, do not advance to assembly. Record the failure, revise the prompt or
+  references, and retry within the bounded self-improvement loop.
+- Never claim final video success without a concrete stitched video artifact,
+  duration proof, clip receipts, and continuity inspection evidence.
+
+## Panel Continuity And Self-Repair Gate
+
+This skill is persona-agnostic. Horus/Embry, Kokoro, Nico, or any other
+persona pair is only a fixture instance of the same dream contract. Do not bake
+character-specific assumptions into the pipeline; extract the required
+characters, props, creatures, environments, and dynamic objects from the active
+story contract and validate those requirements per panel.
+
+Every generated panel must pass through a second-pass script/image check before
+it can feed a storyboard board, provider packet, or review page. Image
+generation is nondeterministic, so the first script is only a hypothesis about
+what should appear. After the image exists, run:
+
+```text
+panel script + generated panel image
+-> visual verifier lists what is actually visible, missing, cropped, merged,
+   static, pasted, or physically under-described
+-> script writer repairs the panel script, realism ledger, and prompt deltas
+-> image repair/regeneration only when the repaired script still requires
+   missing visual facts
+-> human/manual or VLM-assisted visual review
+```
+
+The post-generation script edit is required when the generated image introduces
+new visible facts, omits required facts, or makes a prop/environment behavior
+ambiguous. The script must explain every required and visible panel element that
+matters to the shot: characters, scale, props, foreground architecture,
+background creatures, weather, temperature, motion, sound when relevant,
+material state, and environmental interaction.
+
+Before a storyboard panel can feed a provider packet, write a
+`panel_continuity_and_repair_ledger.json` with one record per panel:
+
+```json
+{
+  "panel": 9,
+  "required_visible_entities": ["character_horus", "character_embry"],
+  "required_props": ["patio_table", "umbrella", "tea_service"],
+  "required_environment": ["void_world_patio", "distant_creatures"],
+  "required_dynamic_behaviors": [
+    "umbrella fabric ripples or stays intentionally taut with reason",
+    "tea steam curls, thins, or disperses",
+    "background creatures move behind the conversation"
+  ],
+  "visual_review_status": "FAILED_VISUAL_REVIEW",
+  "failed_requirements": ["character_embry_not_visibly_present"],
+  "repair_action": "regenerate_panel_with_corrective_scillm_image_prompt",
+  "repair_attempt": 1
+}
+```
+
+Hard gates:
+
+- Reject a panel if a required character is cropped out, hidden, merged into
+  another character, converted into an unrelated identity, or not visible enough
+  for review.
+- Reject a panel if the script fails to explain a required visible element or a
+  materially important generated element. "Everything" means every entity,
+  foreground prop, highlighted surface, creature, weather force, temperature
+  effect, motion cue, and sound cue that affects the shot's meaning or provider
+  prompt.
+- Reject a panel if a highlighted prop has no physical state or environmental
+  behavior. Umbrellas should ripple, strain, cast shadows, shed droplets, or be
+  explicitly still for a reason. Tea should steam, ripple, cool, reflect, or
+  stain. Paper should lift, curl, crease, slide, or be intentionally pinned.
+- Reject a panel if a moving creature or object lacks speed, direction,
+  friction/contact, pause/attention behavior when relevant, and sound when the
+  shot is audio-bearing. Example: a small creature crossing a stone railing must
+  state claw contact, skitter rhythm, speed, whether it pauses to look, and how
+  it exits frame.
+- Reject a panel if a required environment effect is pasted over the image as a
+  rectangular overlay instead of being regenerated as part of the scene.
+- Reject a panel if the text says an entity or prop is present but the rendered
+  panel does not visibly support that claim.
+
+Self-repair loop:
+
+```text
+visual review failure
+-> record failed requirements and failed image hash
+-> write corrected prompt with MUST INCLUDE / MUST NOT INCLUDE deltas
+-> call $scillm image generation through the receipt wrapper
+-> inspect the new image
+-> update panel symlinks, boards, receipts, and review page only if the new
+   image satisfies the failed requirements
+-> repeat until accepted, attempts exhausted, or blocked for missing source
+```
+
+Use `$scillm` image generation, not a chat completion, for image repair:
+
+```bash
+bash skills/scillm/run.sh generate-image \
+  --auth codex-oauth \
+  --prompt-file prompts/panel_09_repair.prompt.md \
+  --out storyboard/regenerated_panels/panel_09_repair.png \
+  --model gpt-image-2 \
+  --quality high
+```
+
+The corrected prompt must preserve all accepted upstream context and add only
+the course-correction constraints needed for the failed requirements. Do not
+paper over visual failures by changing the report text alone.
+
+Panel repair receipts must validate against the deterministic gate before any
+panel can contribute to provider readiness:
+
+```bash
+uv run --project skills/persona-dream python \
+  skills/persona-dream/scripts/validate_panel_repair_gate.py \
+  /path/to/panel_repair_gate_receipt.json \
+  --require-provider-eligible
+```
+
+The validator rejects partial pass labels such as `PASS_SCRIPT_COVERAGE`,
+`PASS_REFERENCE_EVIDENCE`, and `PASS_VISUAL_REVIEW` as final panel statuses.
+Script, reference, visual, no-overlay, post-generation script, and provider
+media checks are subgates; the only normal final pass state is
+`PASS_PANEL_REVIEWED`.
+
+## Provider Final Gate
+
+Before a Kling, Wan, ComfyUI, or other provider video call is allowed, write a
+final provider-readiness gate receipt. A provider packet is not live-submittable
+unless every required gate is `PASS` or explicitly human-accepted as an
+intentional exception.
+
+Required provider-readiness checks:
+
+- Story, entity extraction, casting/reference research, reference sheets,
+  storyboard panels, script realism, persona-memory grounding, visual
+  continuity, voice/audio, provider payload schema, cost/mode, async handling,
+  and artifact path/hash locks are all represented in machine-readable
+  receipts.
+- All storyboard panels have `visual_review_status: PASS` or an explicit
+  human-accepted exception. `GENERATED_UNREVIEWED` cannot feed a paid provider
+  call.
+- All panel scripts pass the second-pass script/image check. Missing required
+  entities, unexplained visible elements, static highlighted props, missing
+  weather/temperature effects, or pasted overlays block provider execution.
+- Experimental `persona-dream` provider planning defaults to `mode: std` /
+  720p. Any `pro`, 1080p, or 4K route requires explicit cost/entitlement proof
+  and current provider schema validation.
+- Provider `external_task_id` is present and stable for webhook reconciliation.
+- A reachable `callback_url` is configured, or a documented polling-only plan is
+  accepted by the operator and represented in the packet.
+- Provider-accessible media URLs exist for all uploaded images/audio, not only
+  local filesystem paths.
+- For voiced scenes, local voice candidates are not enough. Provider voice IDs
+  must exist before `voice_list` is live-submittable.
+
+Allowed status labels:
+
+- `PROVIDER_READY`: all gates pass and no paid-call approval is missing.
+- `BLOCKED_PROVIDER_GATE`: one or more required gates failed or are missing.
+- `BLOCKED_AWAITING_HUMAN_APPROVAL`: all technical gates pass, but paid-call
+  approval is missing.
+- `DRY_RUN_NOT_LIVE_SUBMITTABLE`: useful review packet, but one or more live
+  provider requirements are absent.
+
+## Image Generation Lane
+
+Still images are the normal visual unit for this skill: dream keyframes,
+character sheets, scene sheets, frame prompts, and contact sheets. Pick the
+image backend by the job, not by habit.
+
+Use GPT image generation for quality-sensitive or final assets:
+
+```text
+final keyframes
+character sheets
+contact sheets
+difficult prompt following
+scene continuity references
+identity-boundary-sensitive persona images
+images requiring detailed "must include" / "must not include" constraints
+```
+
+Preferred project-agent path:
+
+```bash
+python scripts/generate_image.py \
+  --auth codex-oauth \
+  --prompt-file artifacts/images/<asset>.prompt.md \
+  --out artifacts/images/<asset>.png \
+  --events-out artifacts/images/<asset>.events.jsonl
+```
+
+Use the `$scillm` HTTP image endpoint for headless, API-key, CI, or service
+flows. This path requires caller attribution and should be used for both GPT
+image models and Chutes image models:
+
+```text
+POST http://localhost:4001/v1/images/generations
+Authorization: Bearer sk-dev-proxy-123
+X-Caller-Skill: persona-dream
+```
+
+Use `model: gpt-image-2` when prompt specificity and final quality matter. GPT
+image prompts may be detailed and structured, and should preserve the dream
+contract with sections such as:
+
+```text
+SUBJECT
+CHARACTERS
+SCENE
+COMPOSITION
+CONTINUITY
+MOOD AND LIGHTING
+MUST INCLUDE
+MUST NOT INCLUDE
+OUTPUT
+```
+
+Use `model: z-image-turbo` through `$scillm` for fast drafts, cheap variants,
+pose/style exploration, rough perspective tests, and early contact-sheet
+options. Do not call Chutes image endpoints directly from this skill; route
+Chutes image models through `$scillm` so auth, retries, caller attribution, and
+receipts remain consistent.
+
+Use ComfyUI for still-image work only when graph control is the reason:
+
+```text
+pose-node workflows
+multi-view or character-sheet workflows
+ControlNet-like structure
+reusable editable workflow JSON
+human-inspectable graph state
+```
+
+Use Wan/TurboWan/ComfyUI I2V for motion after a keyframe is accepted. Do not
+use I2V as the default still-image generator.
+
+Every generated image or image batch must record:
+
+```text
+prompt file or rendered prompt
+model and auth path
+caller skill
+output image path
+receipt JSON
+event log when available
+hash
+identity_boundary_receipt.json for persona, actor-like, or public-figure-adjacent images
+```
+
+## Motion Backend Lane
+
+Motion generation is optional. Use it after `dream_packet.json` exists,
+normally through `create-movie`, DevOps, or a future renderer adapter. The core
+dream contract remains prompt/contact-sheet and memory reflection, because that
+is the work product that feeds persona memory.
+
+Preferred TurboDiffusion backend:
+
+```text
+Dockerized ComfyUI on the local A5000 running TurboDiffusion TurboWan2.2-I2V-A14B-720P
+```
+
+Use ComfyUI for short dream-motion clips when the TurboDiffusion Wan 2.2 model
+files are mounted and
+`/system_stats` plus `/object_info` prove the API is ready. ComfyUI provides the
+project agent with editable workflow JSON, an API queue, output receipts, and a
+human-inspectable graph that can later be opened in the web interface. `$surf`
+may inspect or screenshot that UI, but execution should remain API-first. Store
+`video_generation_receipt.json`, workflow JSON, API prompt JSON, output paths,
+and hashes for every generated clip.
+
+Chutes remains preferred for SPARTA LLM/VLM and for image/video models when the
+exact model fits the task and a schema/canary receipt proves readiness. Treat
+generic Chutes Wan2.1/turbowani2v examples as a different non-Turbo or
+unverified lane until the receipt proves otherwise. Do not use them as proof of
+the 4-step TurboDiffusion Wan2.2 path.
+
+For TurboDiffusion I2V, record the clip unit in the prompt packet:
+
+```text
+default: 81 frames, nominal 5-second clip
+extended: 121 frames, nominal 7.5-second clip
+fps: 24
+```
+
+The 7.5-second path is allowed for the four-shot 30-second plan, but it is a
+quality-sensitive generation choice. If a longer clip drifts, prefer prompt
+repair or splitting that shot into 5-second subclips over accepting continuity
+damage.
+
+## Audio / Voice Handoff Lane
+
+`persona-dream` emits `timed_transcript.json` and `voice_handoff_plan.json` so a
+separate audio lane can render voices without confusing planning proof with
+audio proof.
+
+Recommended near-term audio lane:
+
+```text
+Kokoro base TTS
+-> optional isolated KokoClone/Kanade conversion canary
+-> ffprobe converted WAVs
+-> FFmpeg dialogue bed
+-> FFmpeg mux with accepted silent video
+-> voice eval / listening receipt
+```
+
+Keep Kokoro/KokoClone receipts separate from ComfyUI receipts. ComfyUI owns
+image/video graph execution; it does not own deterministic dialogue timing,
+speaker identity receipts, future voice-training manifests, or mux proof.
+
+Recommended future Embry Sparta Chat voice lane:
+
+```text
+curated authorized reference clips
+-> transcript/alignment manifest
+-> voice candidate generation
+-> listening and/or model-assisted eval
+-> train-voice / tts-horus fine-tuning proof
+-> PersonaPlex live voice experiment only after offline clip proof
+```
+
+For any persona with local source audio, audiobook audio, interview audio, or
+provided reference media, route source-clip selection through
+`voice-segment-selector` or a voice/audio subagent that uses that skill. The
+voice selector must produce a durable job directory, `candidates.jsonl`, and
+review/export artifacts before any provider voice-clone step is considered
+ready.
+
+Example single-narrator audiobook selector lane:
+
+```bash
+PERSONA_ID=example_persona
+JOB=/tmp/voice-segment-selector-${PERSONA_ID}
+AUDIO=/path/to/persona/source_audio.wav
+
+skills/voice-segment-selector/run.sh prepare \
+  --input "$AUDIO" \
+  --job-dir "$JOB" \
+  --classifier f0 \
+  --no-transcribe \
+  --min-clip-sec 6 \
+  --max-clip-sec 18
+```
+
+If chapter metadata exists from `extract-audiobook`, add `--chapters-json`.
+Do not export, train, or upload a voice clone until the candidate has been
+reviewed and accepted. The provider voice state remains
+`VOICE_AUDIOBOOK_SOURCE_FOUND_PROVIDER_ID_MISSING` or
+`VOICE_CLONE_CANDIDATE_FOUND_PROVIDER_ID_MISSING` until a provider returns a
+custom `voice_id`.
+
+Local A5000 guidance from `/home/graham/workspace/experiments/Wan2.2/README.md`:
+
+```bash
+cd /home/graham/workspace/experiments/Wan2.2
+python generate.py \
+  --task ti2v-5B \
+  --size 1280*704 \
+  --ckpt_dir ./Wan2.2-TI2V-5B \
+  --offload_model True \
+  --convert_model_dtype \
+  --t5_cpu \
+  --image /path/to/reference.png \
+  --prompt "$(jq -r '.frame_prompts[0].prompt' /path/to/dream_packet.json)"
+```
+
+Use `Wan2.2-TI2V-5B` as the conservative local fallback for dream clips on a
+24GB GPU. Treat the 24GB path as borderline: run one clip at a time, prefer
+still-frame contact sheets for cheap runs, and fall back to no-video output on
+OOM.
+
+The distilled TurboDiffusion `TurboWan2.2-I2V-A14B-720P` ComfyUI path is a
+separate optimized backend. It may be practical on the A5000 only when the
+specific distilled model, UMT5 text encoder, VAE, and ComfyUI workflow are
+mounted and proven by receipt. Do not generalize that to non-distilled
+`T2V-A14B`, `I2V-A14B`, `S2V-14B`, or Animate-class jobs; route those to
+`devops` for RunPod or larger GPU planning because the local Wan docs describe
+those single-GPU paths as 80GB-class.
+
+## Research / Bakeoff
+
+Experimental story, contact-sheet, A/V lip-sync, and NAVA bakeoff materials live
+under:
+
+```text
+research/bakeoff/
+```
+
+This subtree is a research lane, not the default `persona-dream` runtime. It
+must preserve the bundle's no-memory-write rule, source-grounding rule,
+consented-voice rule, shared-base-video invariant for ElevenLabs versus WavTTS,
+and mandatory manual visual review before any PASS claim.
+
+Start with the no-network smoke path:
+
+```bash
+./run.sh research-bakeoff smoke
+```
+
+Supported research commands:
+
+```bash
+./run.sh research-bakeoff smoke
+./run.sh research-bakeoff story
+./run.sh research-bakeoff contact-sheet --dry-run
+./run.sh research-bakeoff elevenlabs
+./run.sh research-bakeoff wavtts --confirm-voice-consent --ref-audio /path/to/voice.wav --ref-text "Exact reference transcript."
+./run.sh research-bakeoff nava-inputs
+./run.sh research-bakeoff nava-dry-run --nava-repo /path/to/NAVA
+```
+
+The default voice lane for hosted A/V baseline work is ElevenLabs through fal.
+WavTTS requires explicit consent flags and owned/licensed/consented reference
+audio. NAVA remains an experimental joint audio-video comparator. Contact-sheet
+rendering uses a backend enum:
+
+```text
+dry_run | fal_flux | gpt_image | scillm_image | local_diffusion
+```
+
+Only `dry_run` and `fal_flux` are wired in this imported research bundle. Future
+GPT image or `$scillm` image execution must preserve caller attribution,
+receipts, and the backend-neutral `contact_sheets.json` contract. Use hosted or
+voice-clone lanes only after the required keys, rights, receipts, and manual
+review plan are available.
+
+## Contact Sheet Sub-Skill
+
+Use the local `contact-sheet` sub-skill when a story needs provider-ready visual
+references or recallable image assets:
+
+```bash
+./run.sh contact-sheet build \
+  --asset-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run> \
+  --index-qdrant \
+  --write-memory
+
+./run.sh contact-sheet retrieve --query "Embry SPARTA archive character sheet"
+```
+
+This layer extracts or accepts story-derived visual entities:
+
+```text
+characters[] -> character sheets
+environments[] -> room/world sheets
+objects[] -> prop/UI/furniture sheets
+creatures[] -> creature/background sheets
+scene_bindings[] -> provider prompt inputs
+```
+
+Generated images stay on `/mnt/storage12tb`. Memory stores canonical metadata
+and pointers to those files. Qdrant stores named `text_mm` and `image_mm`
+vectors for recall. Do not store vector arrays in memory/ArangoDB.
+
+## Validation
+
+Run:
+
+```bash
+./sanity.sh
+```
+
+The sanity gate runs a positive-control fixture and verifies that the required
+packet artifacts exist, that `contact_sheet.png` is a real PNG, and that memory
+writeback is skipped without `--write-memory`. It also runs a `video_plan`
+fixture and verifies the deterministic 30-second planning contract.

diff --git a/skills/persona-dream/sanity.sh b/skills/persona-dream/sanity.sh
new file mode 100755
index 000000000..34de40c57
--- /dev/null
+++ b/skills/persona-dream/sanity.sh
@@ -0,0 +1,156 @@
+#!/usr/bin/env bash
+set -euo pipefail
+
+SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
+PYTHON=(uv run --project "${SCRIPT_DIR}" python)
+OUT_DIR="$(mktemp -d /tmp/persona-dream-sanity.XXXXXX)"
+
+"${SCRIPT_DIR}/run.sh" generate \
+  --persona embry \
+  --fixture "${SCRIPT_DIR}/scripts/fixtures/sample_residue.json" \
+  --output-dir "${OUT_DIR}" \
+  --run-id sanity \
+  --no-write-memory
+
+"${PYTHON[@]}" - "${OUT_DIR}" <<'PY'
+import json
+import sys
+from pathlib import Path
+
+out = Path(sys.argv[1])
+required = [
+    "dream_request.json",
+    "response.json",
+    "residue_links.json",
+    "contradiction_report.json",
+    "dream_packet.json",
+    "dream_prompt.txt",
+    "frame_prompts.json",
+    "contact_sheet.png",
+    "dream_reflection.md",
+    "memory_write_receipt.json",
+]
+missing = [name for name in required if not (out / name).exists()]
+if missing:
+    raise SystemExit(f"missing artifacts: {missing}")
+
+if (out / "contact_sheet.png").read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
+    raise SystemExit("contact_sheet.png is not a PNG")
+
+packet = json.loads((out / "dream_packet.json").read_text())
+receipt = json.loads((out / "memory_write_receipt.json").read_text())
+response = json.loads((out / "response.json").read_text())
+
+assert packet["schema"] == "persona_dream.packet.v1"
+assert packet["persona"]["id"] == "embry"
+assert len(packet["frame_prompts"]) >= 3
+assert receipt["status"] == "skipped"
+assert response["status"] == "ok"
+
+print(json.dumps({
+    "status": "ok",
+    "mode": "static_dream",
+    "output_dir": str(out),
+    "artifact_count": len(required),
+    "frame_count": len(packet["frame_prompts"]),
+}, indent=2))
+PY
+
+VIDEO_OUT_DIR="$(mktemp -d /tmp/persona-dream-video-plan-sanity.XXXXXX)"
+
+"${SCRIPT_DIR}/run.sh" generate \
+  --mode video_plan \
+  --persona horus \
+  --secondary-persona embry \
+  --fixture "${SCRIPT_DIR}/scripts/fixtures/sample_residue.json" \
+  --about "creating the SPARTA Explorer app" \
+  --scene "Horus and Embry have tea under a patio table with an umbrella on a 40k void world where Tyranids are playing in the background." \
+  --duration-seconds 30 \
+  --output-dir "${VIDEO_OUT_DIR}" \
+  --run-id video-plan-sanity \
+  --no-write-memory
+
+"${PYTHON[@]}" - "${VIDEO_OUT_DIR}" <<'PY'
+import json
+import sys
+from pathlib import Path
+
+out = Path(sys.argv[1])
+required = [
+    "dream_story.md",
+    "dream_story.json",
+    "character_scene_bible.json",
+    "storyboard.json",
+    "timed_transcript.json",
+    "multimodal_prompts.json",
+    "voice_handoff_plan.json",
+    "pipeline_stage_report.json",
+    "pipeline_stage_report.md",
+    "manifest.json",
+]
+missing = [name for name in required if not (out / name).exists()]
+if missing:
+    raise SystemExit(f"missing video_plan artifacts: {missing}")
+
+timed = json.loads((out / "timed_transcript.json").read_text())
+prompts = json.loads((out / "multimodal_prompts.json").read_text())
+voice = json.loads((out / "voice_handoff_plan.json").read_text())
+bible = json.loads((out / "character_scene_bible.json").read_text())
+report = json.loads((out / "pipeline_stage_report.json").read_text())
+manifest = json.loads((out / "manifest.json").read_text())
+
+shots = timed["shots"]
+prompt_items = prompts["prompts"]
+durations = [shot["duration_sec"] for shot in shots]
+frame_counts = [prompt["num_frames"] for prompt in prompt_items]
+
+assert timed["schema"] == "persona_dream.timed_transcript.v1"
+assert timed["duration_seconds"] == 30
+assert len(shots) == 4
+assert durations == [7.5, 7.5, 7.5, 7.5]
+assert len(prompt_items) == 4
+assert frame_counts == [121, 121, 121, 121]
+assert voice["schema"] == "persona_dream.voice_handoff_plan.v1"
+assert voice["owner"] == "create-movie/audio-lane"
+assert {speaker["speaker_id"] for speaker in voice["speakers"]} == {"embry", "horus"}
+assert [line["speaker_id"] for line in voice["lines"]] == ["horus", "embry", "horus", "horus"]
+assert any("voice_identity_boundary_receipt.json" in receipt for receipt in voice["required_receipts"])
+assert bible["schema"] == "persona_dream.character_scene_bible.v1"
+assert {character["character_id"] for character in bible["characters"]} == {"embry", "horus"}
+assert bible["self_improvement_loop"]["schema"] == "persona_dream.self_improvement_loop.v1"
+assert report["schema"] == "persona_dream.pipeline_stage_report.v1"
+assert any(stage["stage_id"] == "stage_09_voice_handoff" for stage in report["stages"])
+assert any(stage["stage_id"] == "stage_10_self_improvement_loop" for stage in report["stages"])
+assert manifest["mode"] == "video_plan"
+assert "i2v" in manifest["next_lanes"]
+assert "voice_handoff_plan.json" in manifest["required_modes"]["video_plan"]
+
+print(json.dumps({
+    "status": "ok",
+    "mode": "video_plan",
+    "output_dir": str(out),
+    "artifact_count": len(required),
+    "shot_durations": durations,
+    "frame_counts": frame_counts,
+}, indent=2))
+PY
+
+"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_storyboard_first_fixture_regressions.py"
+
+"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
+  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_valid.json" \
+  --require-provider-eligible
+
+if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
+  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json" \
+  --require-provider-eligible; then
+  echo "invalid partial pass fixture unexpectedly passed" >&2
+  exit 1
+fi
+
+if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
+  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json" \
+  --require-provider-eligible; then
+  echo "invalid provider field fixture unexpectedly passed" >&2
+  exit 1
+fi

diff --git a/skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json b/skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json
new file mode 100644
index 000000000..c1ad9fd44
--- /dev/null
+++ b/skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json
@@ -0,0 +1,128 @@
+{
+  "$schema": "https://json-schema.org/draft/2020-12/schema",
+  "$id": "persona_dream.panel_repair_gate_receipt.v1",
+  "title": "Persona Dream Panel Repair Gate Receipt",
+  "type": "object",
+  "required": [
+    "schema",
+    "run_id",
+    "panel_id",
+    "status",
+    "script_coverage_status",
+    "post_generation_script_coverage_status",
+    "reference_evidence_status",
+    "visual_review_status",
+    "no_overlay_status",
+    "provider_media_status",
+    "requirement_matrix",
+    "script_coverage_receipt",
+    "post_generation_script_coverage_receipt",
+    "reference_receipt",
+    "generation_receipt",
+    "visual_review_receipt",
+    "no_overlay_receipt",
+    "provider_mode",
+    "provider_resolution",
+    "external_task_id",
+    "voice_id_status",
+    "provider_packet_status",
+    "provider_eligibility",
+    "remaining_blockers"
+  ],
+  "properties": {
+    "schema": {
+      "const": "persona_dream.panel_repair_gate_receipt.v1"
+    },
+    "run_id": {
+      "type": "string",
+      "minLength": 1
+    },
+    "panel_id": {
+      "type": "string",
+      "minLength": 1
+    },
+    "status": {
+      "enum": [
+        "PASS_PANEL_REVIEWED",
+        "HUMAN_ACCEPTED_WITH_WAIVER",
+        "BLOCKED_UNREVIEWED_GENERATION",
+        "BLOCKED_PENDING_INDEPENDENT_VERIFICATION",
+        "BLOCKED_SCRIPT_COVERAGE",
+        "BLOCKED_REFERENCE_EVIDENCE",
+        "BLOCKED_VISUAL_CONTRADICTION",
+        "BLOCKED_OVERLAY_OR_COMPOSITE",
+        "BLOCKED_MAX_ATTEMPTS",
+        "BLOCKED_ARTIFACT_INACCESSIBLE",
+        "BLOCKED_PROVIDER_MEDIA_URLS",
+        "BLOCKED_HUMAN_REVIEW_REQUIRED"
+      ]
+    },
+    "script_coverage_status": {
+      "enum": ["PASS", "FAIL", "WAIVED"]
+    },
+    "post_generation_script_coverage_status": {
+      "enum": ["PASS", "FAIL", "WAIVED"]
+    },
+    "reference_evidence_status": {
+      "enum": ["PASS", "FAIL", "WAIVED"]
+    },
+    "visual_review_status": {
+      "enum": ["PASS", "FAIL", "WAIVED"]
+    },
+    "no_overlay_status": {
+      "enum": ["PASS", "FAIL", "WAIVED"]
+    },
+    "provider_media_status": {
+      "enum": ["PASS", "FAIL", "WAIVED"]
+    },
+    "provider_media_urls": {
+      "type": "array",
+      "items": {
+        "type": "string",
+        "pattern": "^https?://"
+      }
+    },
+    "media_hashes": {
+      "type": "object",
+      "additionalProperties": {
+        "type": "string",
+        "pattern": "^sha256:"
+      }
+    },
+    "provider_mode": {
+      "enum": ["std", "pro", "4k"]
+    },
+    "provider_resolution": {
+      "type": "string",
+      "minLength": 1
+    },
+    "external_task_id": {
+      "type": "string",
+      "minLength": 1
+    },
+    "voice_id_status": {
+      "enum": [
+        "PROVIDER_VOICE_ID_READY",
+        "SILENT_SCENE",
+        "BLOCKED_MISSING_PROVIDER_VOICE_ID"
+      ]
+    },
+    "provider_packet_status": {
+      "enum": [
+        "BLOCKED_PROVIDER_GATE",
+        "DRY_RUN_NOT_LIVE_SUBMITTABLE",
+        "PROVIDER_READY"
+      ]
+    },
+    "provider_eligibility": {
+      "type": "boolean"
+    },
+    "remaining_blockers": {
+      "type": "array",
+      "items": {
+        "type": "string"
+      }
+    }
+  },
+  "additionalProperties": true
+}

diff --git a/skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json b/skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json
new file mode 100644
index 000000000..16d92f7b9
--- /dev/null
+++ b/skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json
@@ -0,0 +1,30 @@
+{
+  "schema": "persona_dream.panel_repair_gate_receipt.v1",
+  "run_id": "fixture-non-horus-dream",
+  "panel_id": "panel_01",
+  "status": "PASS_SCRIPT_COVERAGE",
+  "script_coverage_status": "PASS",
+  "post_generation_script_coverage_status": "FAIL",
+  "reference_evidence_status": "PASS",
+  "visual_review_status": "FAIL",
+  "no_overlay_status": "FAIL",
+  "provider_media_status": "FAIL",
+  "requirement_matrix": "/tmp/fixture/panel_requirement_matrix.json",
+  "script_coverage_receipt": "/tmp/fixture/script_coverage_receipt.json",
+  "post_generation_script_coverage_receipt": "",
+  "reference_receipt": "/tmp/fixture/reference_receipt.json",
+  "generation_receipt": "/tmp/fixture/scillm_generation_receipt.json",
+  "visual_review_receipt": "",
+  "no_overlay_receipt": "",
+  "provider_media_urls": [],
+  "media_hashes": {},
+  "provider_mode": "std",
+  "provider_resolution": "720p",
+  "callback_or_polling_plan": "",
+  "external_task_id": "fixture-non-horus-dream-panel-01",
+  "voice_id_status": "SILENT_SCENE",
+  "cost_estimate": "",
+  "provider_packet_status": "BLOCKED_PROVIDER_GATE",
+  "provider_eligibility": true,
+  "remaining_blockers": []
+}

diff --git a/skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json b/skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json
new file mode 100644
index 000000000..13ab3388f
--- /dev/null
+++ b/skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json
@@ -0,0 +1,34 @@
+{
+  "schema": "persona_dream.panel_repair_gate_receipt.v1",
+  "run_id": "fixture-non-horus-dream",
+  "panel_id": "panel_02",
+  "status": "PASS_PANEL_REVIEWED",
+  "script_coverage_status": "PASS",
+  "post_generation_script_coverage_status": "PASS",
+  "reference_evidence_status": "PASS",
+  "visual_review_status": "PASS",
+  "no_overlay_status": "PASS",
+  "provider_media_status": "PASS",
+  "requirement_matrix": "/tmp/fixture/panel_requirement_matrix.json",
+  "script_coverage_receipt": "/tmp/fixture/script_coverage_receipt.json",
+  "post_generation_script_coverage_receipt": "/tmp/fixture/post_generation_script_coverage_receipt.json",
+  "reference_receipt": "/tmp/fixture/reference_receipt.json",
+  "generation_receipt": "/tmp/fixture/scillm_generation_receipt.json",
+  "visual_review_receipt": "/tmp/fixture/visual_review_receipt.json",
+  "no_overlay_receipt": "/tmp/fixture/no_overlay_receipt.json",
+  "provider_media_urls": [
+    "/mnt/storage12tb/persona-dream/local-only-panel.png"
+  ],
+  "media_hashes": {
+    "panel": "missing-sha-prefix"
+  },
+  "provider_mode": "4k",
+  "provider_resolution": "4k",
+  "callback_or_polling_plan": "",
+  "external_task_id": "",
+  "voice_id_status": "BLOCKED_MISSING_PROVIDER_VOICE_ID",
+  "cost_estimate": "",
+  "provider_packet_status": "PROVIDER_READY",
+  "provider_eligibility": true,
+  "remaining_blockers": []
+}

diff --git a/skills/persona-dream/scripts/fixtures/panel_repair_gate_valid.json b/skills/persona-dream/scripts/fixtures/panel_repair_gate_valid.json
new file mode 100644
index 000000000..9ceec1518
--- /dev/null
+++ b/skills/persona-dream/scripts/fixtures/panel_repair_gate_valid.json
@@ -0,0 +1,40 @@
+{
+  "schema": "persona_dream.panel_repair_gate_receipt.v1",
+  "run_id": "fixture-non-horus-dream",
+  "panel_id": "panel_01",
+  "status": "PASS_PANEL_REVIEWED",
+  "attempt": 2,
+  "max_attempts": 4,
+  "script_coverage_status": "PASS",
+  "post_generation_script_coverage_status": "PASS",
+  "reference_evidence_status": "PASS",
+  "visual_review_status": "PASS",
+  "no_overlay_status": "PASS",
+  "provider_media_status": "PASS",
+  "requirement_matrix": "/tmp/fixture/panel_requirement_matrix.json",
+  "script_coverage_receipt": "/tmp/fixture/script_coverage_receipt.json",
+  "post_generation_script_coverage_receipt": "/tmp/fixture/post_generation_script_coverage_receipt.json",
+  "second_pass_script_delta": "/tmp/fixture/second_pass_script_delta.json",
+  "reference_receipt": "/tmp/fixture/reference_receipt.json",
+  "repair_prompt_package": "/tmp/fixture/repair_prompt_package.json",
+  "generated_image_path": "/tmp/fixture/panel_01_attempt_02.png",
+  "generation_receipt": "/tmp/fixture/scillm_generation_receipt.json",
+  "visual_review_receipt": "/tmp/fixture/visual_review_receipt.json",
+  "no_overlay_receipt": "/tmp/fixture/no_overlay_receipt.json",
+  "provider_media_urls": [
+    "https://storage.example.invalid/persona-dream/panel_01_attempt_02.png"
+  ],
+  "media_hashes": {
+    "panel": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
+  },
+  "provider_mode": "std",
+  "provider_resolution": "720p",
+  "callback_or_polling_plan": "/tmp/fixture/callback_or_polling_plan.json",
+  "external_task_id": "fixture-non-horus-dream-panel-01",
+  "voice_id_status": "SILENT_SCENE",
+  "cost_estimate": "/tmp/fixture/cost_estimate.json",
+  "provider_packet_status": "PROVIDER_READY",
+  "status_transition_log": "/tmp/fixture/status_transition_log.jsonl",
+  "provider_eligibility": true,
+  "remaining_blockers": []
+}

diff --git a/skills/persona-dream/scripts/validate_panel_repair_gate.py b/skills/persona-dream/scripts/validate_panel_repair_gate.py
new file mode 100644
index 000000000..354a2fa56
--- /dev/null
+++ b/skills/persona-dream/scripts/validate_panel_repair_gate.py
@@ -0,0 +1,194 @@
+#!/usr/bin/env python3
+"""Validate a persona-dream panel repair gate receipt.
+
+This intentionally avoids an external jsonschema dependency so the gate can run
+inside lightweight review and sanity environments.
+"""
+
+from __future__ import annotations
+
+import argparse
+import json
+import sys
+from pathlib import Path
+from typing import Any
+
+
+FINAL_STATUSES = {
+    "PASS_PANEL_REVIEWED",
+    "HUMAN_ACCEPTED_WITH_WAIVER",
+    "BLOCKED_UNREVIEWED_GENERATION",
+    "BLOCKED_PENDING_INDEPENDENT_VERIFICATION",
+    "BLOCKED_SCRIPT_COVERAGE",
+    "BLOCKED_REFERENCE_EVIDENCE",
+    "BLOCKED_VISUAL_CONTRADICTION",
+    "BLOCKED_OVERLAY_OR_COMPOSITE",
+    "BLOCKED_MAX_ATTEMPTS",
+    "BLOCKED_ARTIFACT_INACCESSIBLE",
+    "BLOCKED_PROVIDER_MEDIA_URLS",
+    "BLOCKED_HUMAN_REVIEW_REQUIRED",
+}
+
+PARTIAL_PASS_STATUSES = {
+    "PASS_SCRIPT_COVERAGE",
+    "PASS_REFERENCE_EVIDENCE",
+    "PASS_VISUAL_REVIEW",
+}
+
+SUBGATES = [
+    "script_coverage_status",
+    "post_generation_script_coverage_status",
+    "reference_evidence_status",
+    "visual_review_status",
+    "no_overlay_status",
+    "provider_media_status",
+]
+
+REQUIRED_RECEIPTS = [
+    "requirement_matrix",
+    "script_coverage_receipt",
+    "post_generation_script_coverage_receipt",
+    "reference_receipt",
+    "generation_receipt",
+    "visual_review_receipt",
+    "no_overlay_receipt",
+]
+
+
+def non_empty_string(value: Any) -> bool:
+    return isinstance(value, str) and bool(value.strip())
+
+
+def fail(errors: list[str], message: str) -> None:
+    errors.append(message)
+
+
+def validate_receipt(receipt: dict[str, Any], require_provider_eligible: bool) -> list[str]:
+    errors: list[str] = []
+
+    if receipt.get("schema") != "persona_dream.panel_repair_gate_receipt.v1":
+        fail(errors, "schema must be persona_dream.panel_repair_gate_receipt.v1")
+
+    for field in ("run_id", "panel_id"):
+        if not non_empty_string(receipt.get(field)):
+            fail(errors, f"{field} is required")
+
+    status = receipt.get("status")
+    if status in PARTIAL_PASS_STATUSES:
+        fail(errors, f"{status} is an intermediate subgate, not a final panel status")
+    if status not in FINAL_STATUSES:
+        fail(errors, f"status must be one of {sorted(FINAL_STATUSES)}")
+
+    for subgate in SUBGATES:
+        value = receipt.get(subgate)
+        if value not in {"PASS", "FAIL", "WAIVED"}:
+            fail(errors, f"{subgate} must be PASS, FAIL, or WAIVED")
+
+    for receipt_field in REQUIRED_RECEIPTS:
+        if not non_empty_string(receipt.get(receipt_field)):
+            fail(errors, f"{receipt_field} is required")
+
+    provider_eligible = receipt.get("provider_eligibility")
+    if not isinstance(provider_eligible, bool):
+        fail(errors, "provider_eligibility must be boolean")
+
+    remaining_blockers = receipt.get("remaining_blockers")
+    if not isinstance(remaining_blockers, list) or not all(
+        isinstance(item, str) for item in remaining_blockers
+    ):
+        fail(errors, "remaining_blockers must be a list of strings")
+
+    if receipt.get("provider_mode") != "std" and not receipt.get("provider_mode_waiver"):
+        fail(errors, "provider_mode must default to std unless provider_mode_waiver is true")
+
+    if receipt.get("provider_resolution") != "720p" and not receipt.get("provider_mode_waiver"):
+        fail(
+            errors,
+            "provider_resolution must default to 720p unless provider_mode_waiver is true",
+        )
+
+    if not non_empty_string(receipt.get("external_task_id")):
+        fail(errors, "external_task_id is required")
+
+    if not non_empty_string(receipt.get("callback_or_polling_plan")):
+        fail(errors, "callback_or_polling_plan is required")
+
+    voice_status = receipt.get("voice_id_status")
+    if voice_status not in {
+        "PROVIDER_VOICE_ID_READY",
+        "SILENT_SCENE",
+        "BLOCKED_MISSING_PROVIDER_VOICE_ID",
+    }:
+        fail(errors, "voice_id_status is invalid")
+
+    if not non_empty_string(receipt.get("cost_estimate")):
+        fail(errors, "cost_estimate is required")
+
+    provider_urls = receipt.get("provider_media_urls")
+    if not isinstance(provider_urls, list) or not provider_urls:
+        fail(errors, "provider_media_urls must contain at least one URL")
+    elif not all(isinstance(url, str) and url.startswith(("http://", "https://")) for url in provider_urls):
+        fail(errors, "provider_media_urls must be provider-accessible http(s) URLs")
+
+    media_hashes = receipt.get("media_hashes")
+    if not isinstance(media_hashes, dict) or not media_hashes:
+        fail(errors, "media_hashes must contain at least one sha256 hash")
+    elif not all(isinstance(value, str) and value.startswith("sha256:") for value in media_hashes.values()):
+        fail(errors, "media_hashes values must start with sha256:")
+
+    provider_packet_status = receipt.get("provider_packet_status")
+    if provider_packet_status not in {
+        "BLOCKED_PROVIDER_GATE",
+        "DRY_RUN_NOT_LIVE_SUBMITTABLE",
+        "PROVIDER_READY",
+    }:
+        fail(errors, "provider_packet_status is invalid")
+
+    hard_pass = (
+        status == "PASS_PANEL_REVIEWED"
+        and all(receipt.get(subgate) == "PASS" for subgate in SUBGATES)
+        and voice_status in {"PROVIDER_VOICE_ID_READY", "SILENT_SCENE"}
+        and receipt.get("provider_mode") == "std"
+        and receipt.get("provider_resolution") == "720p"
+        and provider_packet_status == "PROVIDER_READY"
+        and isinstance(provider_urls, list)
+        and bool(provider_urls)
+        and isinstance(media_hashes, dict)
+        and bool(media_hashes)
+        and not remaining_blockers
+    )
+
+    if provider_eligible and not hard_pass:
+        fail(errors, "provider_eligibility=true requires PASS_PANEL_REVIEWED and all provider subgates")
+
+    if require_provider_eligible and not hard_pass:
+        fail(errors, "receipt is not provider eligible")
+
+    if status == "PASS_PANEL_REVIEWED" and not hard_pass:
+        fail(errors, "PASS_PANEL_REVIEWED requires all subgates and provider fields to pass")
+
+    return errors
+
+
+def main(argv: list[str] | None = None) -> int:
+    parser = argparse.ArgumentParser()
+    parser.add_argument("receipt", type=Path)
+    parser.add_argument(
+        "--require-provider-eligible",
+        action="store_true",
+        help="Fail unless the receipt is provider-eligible.",
+    )
+    args = parser.parse_args(argv)
+
+    receipt = json.loads(args.receipt.read_text())
+    errors = validate_receipt(receipt, args.require_provider_eligible)
+    if errors:
+        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
+        return 1
+
+    print(json.dumps({"status": "PASS", "receipt": str(args.receipt)}, indent=2))
+    return 0
+
+
+if __name__ == "__main__":
+    sys.exit(main())
```

## Changed File Contents

### `agents/casting-agent/AGENTS.md`

```text
---
id: casting-agent
kind: worker
title: Casting agent
surface: opencode_transport
transport_role: explore
opencode_agent: explore
mode: propose_patches
composes:
- casting-agent
- memory
- brave-search
- contact-sheet
- best-practices-kling-contact-sheet
- create-image
- scillm
- persona-dream
consult_personas: []
icon: search-check
---

# Casting Agent

Researches and decides visual casting for story entities, then produces or
orchestrates contact-sheet work orders.

## Mission

Given story context, extracted entities, and optional provided reference image
paths, produce accepted visual casting contracts and drive the contact-sheet
loop until all required visual packs are accepted or blocked with evidence.

## Inputs

- Preferred: `story_visual_package.json` with `schema:
  persona_dream.story_visual_package.v1`.
- Compatibility: `story_contract.md`, screenplay, or storyboard plus
  `visual_entities.json`.
- Optional context text for time, state, mood, and story role.
- Optional reference image paths or URLs per entity.
- Optional prior asset/memory recall instructions.

The preferred package must use stable keys for every visual thing:

```text
characters.<character_id>.description
creatures.<creature_id>.description
scenery.<environment_id>.description
props.<prop_id>.description
objects.<object_id>.description
vehicles.<vehicle_id>.description
```

Fixture-specific names such as `horus`, `embry`, `tyranids`, `patio_table`,
`umbrella`, `tea_service`, and `sparta_device` are examples from one
Horus/Embry dry-run only. They are not required schema keys. Preserve whatever
stable entity IDs the active story contract supplies.

Each keyed entity may include `image_file_paths`, `document_paths`, and
`source_urls`. Treat embedded `image_file_paths` as provided references.

## Required Behavior

1. Read the story and entity contract.
2. If a story visual package is provided, preserve its keyed entity structure
   and normalize it into casting artifacts.
3. Prefer provided reference images when present, including package-embedded
   `image_file_paths`.
4. Use `memory` to recall accepted prior assets when requested or useful.
5. Use `brave-search` only for missing or insufficient references.
6. Include state/time/mood in search queries and casting decisions.
   Example: `pre-Heresy Horus Lupercal smiling charismatic`.
7. Write or request:
   - `casting_contract.json`
   - `chosen_reference_inputs.json`
   - `contact_sheet_work_order.json`
8. Delegate panel generation and sheet assembly to `contact-sheet`.
9. Apply `best-practices-kling-contact-sheet` to every Kling-ready Element.
10. Review generated sheets against the casting contract.
11. Retry bounded failures, then emit accepted or blocked receipts.

## Limits

- Do not call paid video providers.
- Do not write memory/Qdrant directly; use `memory` or `contact-sheet`.
- Do not treat Brave rank 1 as automatically correct.
- Do not accept a contact sheet from file existence alone; inspect the sheet or
  require a visual review receipt.
- Stop if identity cannot be satisfied within retry budget.

## Default Retry Budget

```text
max_search_rounds: 3
max_generation_rounds_per_entity: 2
max_review_rounds: 2
```

## Output Standard

Return an operational snapshot with exact artifact paths, entity counts,
reference counts, accepted/blocked status, and the next command or stop
condition.

## Post-run verification (mandatory when `runtime_self_improvement: substantial`)

When this worker runs a substantial job with a durable output/job directory:

1. Run `./run.sh verify --job-dir <job>` (or skill-specific verify documented in SKILL.md).
2. **PASS** → continue handoff.
3. **FAIL** → `./run.sh file-maintainer-ticket --job-dir <job> --create` — do **not** self-commit.

WebGPT review belongs in the **skill-maintainer** cycle, not after every successful run.

Rollout: see `skills/best-practices-skills/references/runtime-self-improvement.md`.
Reference implementation: `skills/voice-segment-selector/references/maintainer-escalation.md`.

```

### `agents/persona-dream-panel-repair-gate/AGENTS.md`

```text
---
id: persona-dream-panel-repair-gate
kind: worker
title: Persona dream panel repair gate
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- persona-dream
- best-practices-script-writer
- best-practices-self-improvement-loop
- best-practices-kling-scene
- best-practices-kling-contact-sheet
- memory
- brave-search
- casting-agent
- contact-sheet
- create-storyboard
- create-image
- scillm
consult_personas: []
icon: scan-eye
---

# Persona Dream Panel Repair Gate

Owns second-pass storyboard panel repair for `persona-dream` before a panel can
enter a Kling/provider packet. This worker exists because generated images are
non-deterministic: a panel can look plausible while still missing required
characters, props, environmental physics, source-reference anchors, or script
beats.

## Mission

Given a story contract, accepted references, panel script, generated panel image,
and current failure ledger, run a bounded repair loop until the panel is either
accepted with receipts or blocked with exact failed requirements.

The worker must reduce orchestrator cognitive load. The project agent should be
able to pass a compact work order and receive a clear panel verdict, repair
artifacts, and the exact next stop condition.

## Inputs

Preferred work order:

```json
{
  "run_id": "fixture-dream-run",
  "panel_id": "panel_01",
  "story_contract_path": "/absolute/path/story_contract.json",
  "timed_beats_path": "/absolute/path/timed_beats.json",
  "panel_script_path": "/absolute/path/panel_01_script.json",
  "panel_image_path": "/absolute/path/panel_01.png",
  "story_visual_package_path": "/absolute/path/story_visual_package.json",
  "reference_manifest_path": "/absolute/path/accepted_references.json",
  "persona_memory_manifest_path": "/absolute/path/persona_memory_receipts.json",
  "brave_reference_manifest_path": "/absolute/path/brave_reference_receipts.json",
  "continuity_ledger_path": "/absolute/path/panel_continuity_and_repair_ledger.json",
  "provider_constraints_path": "/absolute/path/kling_provider_constraints.json",
  "max_attempts": 4
}
```

Compatibility inputs may be markdown or HTML report sections, but the worker
must normalize them into a machine-readable requirement matrix before repair.
The example values above are generic fixtures. A real work order must preserve
the active run's actual story-derived entity IDs and must not require
Horus/Embry/Tyranid-specific keys unless that specific story contract requires
them.

## Required Behavior

1. Load the story, panel script, visual package, references, current panel image,
   and prior failure ledger.
2. Build `panel_requirement_matrix.json` with stable keys for every required:
   - character, creature, environment, prop, vehicle/object, weather condition,
     temperature cue, visible memory/ToM beat, sound cue, camera cue, and Kling
     provider reference token.
3. Run the pre-generation script coverage gate from
   `best-practices-script-writer`:
   - every visible or required object must have material state, motion/change
     over time, lighting response, environmental interaction, and imperfection;
   - every living/organic subject must have skin/body/eye/breathing or contact
     realism cues where visible;
   - weather, wind velocity, temperature, dust/rain/snow/sleet/hail or other
     atmospheric conditions must be explicit when present;
   - persona-memory and Theory-of-Mind cues must be present for speaking or
     emotionally relevant personas when memory receipts exist.
4. If the script fails, produce `second_pass_script_delta.json` and repair the
   script before image regeneration. Do not generate a new panel from an
   underspecified script.
5. Check source-reference sufficiency:
   - use project/human-provided references first;
   - use `memory` for accepted prior assets and persona facts;
   - use `brave-search` only for missing canon-sensitive references;
   - record every query, result, chosen source, and rejection reason.
6. Build a corrective image prompt package for `scillm` / `create-image`.
   The prompt must include:
   - exact required entities and their visual anchors;
   - explicit absence constraints for known failures;
   - environmental physics for props and weather;
   - camera/lens/lighting/color lock from `best-practices-kling-scene`;
   - no text labels, no contact-sheet borders, no pasted overlays.
7. Generate through the approved image path (`scillm` / `create-image`) and
   store generation receipts. Do not hand-write or composite final panels.
8. Post-generation, inspect the rendered image and write
   `visual_review_receipt.json`.
9. Run a distinct post-generation script/realism re-check and write
   `post_generation_script_coverage_receipt.json`. This receipt must compare
   the repaired script against the actual generated image and fail when the
   image introduces or omits important visible elements not reflected in the
   script, realism ledger, and prompt delta.
10. Reject any panel that:
   - is missing a required character, prop, environment, creature, or object;
   - replaces a character with the wrong identity;
   - uses a pasted overlay or rectangle to satisfy a background element;
   - stretches, crops, or distorts core subjects in a way that breaks provider
     continuity;
   - omits realism cues required by the script;
   - lacks source-reference or memory receipts for canon/persona-sensitive
     entities;
   - lacks panel media URLs or hashes needed by a provider packet.
11. Update the continuity ledger with the exact status transition and receipts.

## Stop Conditions

Use one of these exact final panel statuses:

```text
PASS_PANEL_REVIEWED
HUMAN_ACCEPTED_WITH_WAIVER
BLOCKED_UNREVIEWED_GENERATION
BLOCKED_PENDING_INDEPENDENT_VERIFICATION
BLOCKED_SCRIPT_COVERAGE
BLOCKED_REFERENCE_EVIDENCE
BLOCKED_VISUAL_CONTRADICTION
BLOCKED_OVERLAY_OR_COMPOSITE
BLOCKED_MAX_ATTEMPTS
BLOCKED_ARTIFACT_INACCESSIBLE
BLOCKED_PROVIDER_MEDIA_URLS
BLOCKED_HUMAN_REVIEW_REQUIRED
```

Intermediate gates must be recorded in dedicated fields and must not be used as
final panel status values:

```text
script_coverage_status: PASS|FAIL|WAIVED
post_generation_script_coverage_status: PASS|FAIL|WAIVED
reference_evidence_status: PASS|FAIL|WAIVED
visual_review_status: PASS|FAIL|WAIVED
no_overlay_status: PASS|FAIL|WAIVED
provider_media_status: PASS|FAIL|WAIVED
```

A panel is provider-eligible only when final `status` is `PASS_PANEL_REVIEWED`
and every required subgate is `PASS`, or when a human waiver explicitly names
the failed requirement and downstream risk. A partial pass such as script-only,
reference-only, or DOM/report-only review must keep `provider_eligibility:
false`.

## Required Outputs

Return and persist:

```json
{
  "run_id": "string",
  "panel_id": "string",
  "status": "PASS_PANEL_REVIEWED|HUMAN_ACCEPTED_WITH_WAIVER|BLOCKED_...",
  "attempt": 1,
  "max_attempts": 4,
  "script_coverage_status": "PASS|FAIL|WAIVED",
  "post_generation_script_coverage_status": "PASS|FAIL|WAIVED",
  "reference_evidence_status": "PASS|FAIL|WAIVED",
  "visual_review_status": "PASS|FAIL|WAIVED",
  "no_overlay_status": "PASS|FAIL|WAIVED",
  "provider_media_status": "PASS|FAIL|WAIVED",
  "requirement_matrix": "/absolute/path/panel_requirement_matrix.json",
  "script_coverage_receipt": "/absolute/path/script_coverage_receipt.json",
  "post_generation_script_coverage_receipt": "/absolute/path/post_generation_script_coverage_receipt.json",
  "second_pass_script_delta": "/absolute/path/second_pass_script_delta.json",
  "reference_receipt": "/absolute/path/reference_receipt.json",
  "repair_prompt_package": "/absolute/path/repair_prompt_package.json",
  "generated_image_path": "/absolute/path/panel_01_attempt_02.png",
  "generation_receipt": "/absolute/path/scillm_generation_receipt.json",
  "visual_review_receipt": "/absolute/path/visual_review_receipt.json",
  "no_overlay_receipt": "/absolute/path/no_overlay_receipt.json",
  "provider_media_urls": ["https://..."],
  "media_hashes": {"panel": "sha256:..."},
  "provider_mode": "std",
  "provider_resolution": "720p",
  "callback_or_polling_plan": "/absolute/path/callback_or_polling_plan.json",
  "external_task_id": "project-stable-task-id",
  "voice_id_status": "PROVIDER_VOICE_ID_READY|SILENT_SCENE|BLOCKED_MISSING_PROVIDER_VOICE_ID",
  "cost_estimate": "/absolute/path/cost_estimate.json",
  "provider_packet_status": "BLOCKED_PROVIDER_GATE|DRY_RUN_NOT_LIVE_SUBMITTABLE|PROVIDER_READY",
  "status_transition_log": "/absolute/path/status_transition_log.jsonl",
  "provider_eligibility": false,
  "remaining_blockers": []
}
```

## Provider Boundary

This worker never performs a live paid provider call. It may update dry-run
provider eligibility fields, but live Kling execution remains blocked until the
`persona-dream` provider final gate passes.

The provider final gate must still verify:

- all panel gates pass;
- accepted storyboard and reference media are available as provider-accessible
  URLs or an approved upload plan exists;
- `mode` defaults to `std` / 720p unless explicitly approved otherwise;
- `external_task_id` is present;
- `callback_url` is reachable or a documented polling plan is accepted;
- every `<<<voice_n>>>` has a provider `voice_id` or the scene is explicitly
  silent;
- the cost estimate and retry budget are recorded.

`provider_eligibility` must remain `false` unless final `status` is
`PASS_PANEL_REVIEWED`, every required subgate is `PASS`, provider media URLs and
hashes are present, and the provider final gate requirements above are
represented in receipts.

## Output Standard

Report as an operational snapshot:

- Status/phase.
- Current panel and artifact paths.
- Evidence counts: required entities, missing entities, script failures,
  generation attempts, review receipts.
- Next stop condition or exact next command.

Do not claim storyboard/provider readiness from file existence, prompt text, or
DOM/report display alone.

```

### `skills/persona-dream/SKILL.md`

```text
---
name: persona-dream
description: >
  Create receipt-backed persona dream packets from memory residue. Use when a
  persona should dream, reflect, or turn recent memories into persona insight;
  when create-movie/dream.py feels too heavy for the goal; when the desired
  output is a prompt, frame prompts, contact sheet, reflection, and memory
  write receipt rather than a full movie; or when a downstream movie workflow
  needs a dream_packet.json input.
triggers:
  - persona dream
  - create dream
  - dream packet
  - dream from memory
  - ask persona to dream about
  - ask <persona> to dream about
  - memory dream
  - contact sheet dream
  - persona insight dream
provides:
  - persona-dream-packet
  - dream-reflection
  - dream-contact-sheet
  - memory-write-receipt
composes:
  - memory
  - brave-search
  - cinematic-technique-selector
  - create-image
  - create-movie
  - create-persona
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-scillm
  - best-practices-arangodb
taxonomy:
  - persistence
  - creativity
  - reflection
  - memory
---

# Persona Dream

Naming note: this skill is evolving toward `agentic-dreams`. The current
directory/name remains `persona-dream` for compatibility with existing scripts,
reports, paths, and stored artifacts, but the conceptual scope is automated
dream-sequence planning for any persona or persona set, not a Horus-specific or
Embry-specific workflow.

Generate a narrow persona dream work product:

```text
persona memory residue -> dream packet -> prompt/frame prompts/contact sheet
-> reflection -> optional memory write receipt
```

For video work, this skill may also produce a deterministic `video_plan`:

```text
dream packet -> story -> character/scene bible -> storyboard
-> timed transcript -> multimodal prompts -> stage report
```

For Kling/video-oriented runs, insert a Look Lock step before storyboard prompt
composition. If the scene has dialogue or character conflict, the same selector
must also emit Script DNA before storyboard prompt composition:

```text
story + visual entities + memory/project recalls
-> cinematic-technique-selector
-> technique_selection.json / look_lock / script_dna / shot_bible
-> storyboard + Kling scene packet
```

For experimental persona-dream Kling packets, default provider planning to the
lowest acceptable review tier such as 720p/std. Higher modes such as 1080p/pro
or any 4K path require an explicit cost/entitlement gate and current provider
schema proof before live execution.

This skill is not a full movie director. It owns the dream-specific story,
storyboard, prompt packet, continuity contract, and short dream-sequence
receipts. Full screenplay production, audio, score, narration, and polished
movie review still route to `create-movie`. Minimal FFmpeg stitching is allowed
only for the bounded short dream-sequence assembly mode after model clip
receipts exist.

For voiced dream videos, this skill may plan the audio handoff but does not own
the audio lane:

```text
timed transcript -> voice_handoff_plan.json -> create-movie/audio-lane
-> TTS / voice conversion / eval / mix / mux receipts
```

## Boundary

Own:

- Recall persona-specific memory residue.
- Preserve source residue ids and scopes.
- Detect simple tensions or contradictions between residue items.
- Create a synthetic dream prompt, frame prompts, and contact sheet.
- In `video_plan` mode, create a dream story, character/scene bible,
  storyboard, timed transcript, multimodal prompt list, and stage report.
- In Kling/video-oriented runs, request a structured Look Lock from
  `$cinematic-technique-selector` so director/camera/lens/lighting/color-grade
  choices are explicit and stable across shots.
- In story/dialogue runs, request Script DNA from `$cinematic-technique-selector`
  so story rhythm, dialogue pressure, conflict pattern, reveal logic, irony, and
  theme are explicit before storyboard panels are written.
- In `video_plan` mode, create a `voice_handoff_plan.json` that captures
  speaker timing, voice identity boundaries, required receipts, and near-term
  versus future voice lanes.
- Define continuity checks and self-improvement loop criteria before accepting
  generated keyframes or I2V clips.
- Write a short persona reflection.
- Store the reflection to memory only when explicitly requested.
- Emit machine-readable receipts for every side effect.

Do not own:

- Full screenplay production, score, TTS, long-form editing, or polished final
  MP4 review. Use `create-movie`.
- Voice cloning, voice fine-tuning, line-level TTS rendering, audio mixing, or
  final audio identity review. Use `create-movie`, `learn-voice`, `train-voice`,
  `tts-horus`, or a dedicated audio lane as appropriate.
- Direct provider calls to z-image, Wan, or other renderers outside the
  explicit ComfyUI receipt path or a documented reviewed exception.
- Deep external research as a default path. Use `$brave-search` as the normal
  external lookup for canon-sensitive visual entities, current/fresh context,
  and raw source receipts. Use `$dogpile` only as an explicit escalation for
  broader multi-source thematic research, papers/videos/GitHub evidence, or
  when Brave receipts are insufficient.
- Persona identity rewrites. One dream may add a dated reflection, not mutate
  durable identity unless a separate `create-persona` workflow accepts it.
- Unreceipted memory writes.

## Runtime

```bash
cd skills/persona-dream

# Positive-control fixture run, no memory side effects.
./run.sh generate --persona embry --fixture scripts/fixtures/sample_residue.json --output-dir /tmp/persona-dream-smoke

# Live memory recall. Blocks with no_dream if no residue is found.
./run.sh generate --persona embry

# Live memory recall biased by an explicit topic from "$ask <persona> to dream about X".
./run.sh generate --persona embry --about "SPARTA evidence cases and orbital telemetry"

# Deterministic 30-second planning run for short dream video generation.
./run.sh generate \
  --mode video_plan \
  --persona horus \
  --secondary-persona embry \
  --about "creating the SPARTA Explorer app" \
  --scene "Horus and Embry have tea under a patio umbrella on a 40k void world while Tyranids play in the background." \
  --duration-seconds 30

# Live memory recall with explicit memory writeback.
./run.sh generate --persona embry --write-memory
```

Default output directory:

```text
/mnt/storage12tb/skills/persona-dream/outputs/<run-id>/
```

If `/mnt/storage12tb` is unavailable, pass `--output-dir /tmp/...` explicitly.

## Required Artifacts

Every run writes:

```text
dream_request.json
response.json
```

Successful dream runs also write:

```text
residue_links.json
contradiction_report.json
dream_packet.json
dream_prompt.txt
frame_prompts.json
contact_sheet.png
dream_reflection.md
memory_write_receipt.json
```

`memory_write_receipt.json` must say `skipped` unless `--write-memory` was set
and the memory API returned a successful response.

`video_plan` runs additionally write:

```text
dream_story.md
dream_story.json
character_scene_bible.json
technique_selection.json
script_dna_selection.json
storyboard.json
timed_transcript.json
multimodal_prompts.json
voice_handoff_plan.json
pipeline_stage_report.json
pipeline_stage_report.md
manifest.json
```

`voice_handoff_plan.json` must preserve:

```text
speaker ids
line timing
voice identity boundaries
required audio receipts
near-term TTS/conversion lane
future curated-reference/fine-tuning lane
```

For Embry, actress references may be recorded only as cadence/style direction
or replaced by authorized/synthetic references. The output voice must be a
fictional Embry persona voice, not an exact living-actor identity clone.

For a 30-second dream sequence, prefer four 7.5-second shots when the I2V
backend supports the longer unit:

```text
4 clips * 7.5 seconds ~= 30 seconds
121 frames per clip at 24 fps
```

If the 7.5-second path is unstable, fall back to six 5-second clips:

```text
6 clips * 5 seconds ~= 30 seconds
81 frames per clip at 24 fps
```

## Fail-Closed Rules

- If no residue is recalled, return `blocked` with `reason: no_dream`.
- If `--about` is provided, use it to bias memory recall and dream prompts; do
  not treat the topic itself as residue unless memory returns supporting items.
- Do not fabricate residue. Fixture residue is allowed only for tests and is
  marked with `source: fixture`.
- Keep dream text labeled as synthetic.
- Preserve `source_id`, `scope`, and recall metadata in `residue_links.json`.
- Treat `$brave-search` receipts as the default external-search evidence when
  external context is needed.
- Treat `$dogpile` enrichment as optional escalation and degraded if unavailable.
- Treat Wan 2.2 or other video renderers as downstream renderers, not the
  definition of a dream. The planning artifacts must remain useful even if
  generation fails.
- Generated actor/public-figure imagery must be labeled synthetic and must not
  be described as factual identity evidence.
- If a generated keyframe or clip is inconsistent with the previous accepted
  scene, do not advance to assembly. Record the failure, revise the prompt or
  references, and retry within the bounded self-improvement loop.
- Never claim final video success without a concrete stitched video artifact,
  duration proof, clip receipts, and continuity inspection evidence.

## Panel Continuity And Self-Repair Gate

This skill is persona-agnostic. Horus/Embry, Kokoro, Nico, or any other
persona pair is only a fixture instance of the same dream contract. Do not bake
character-specific assumptions into the pipeline; extract the required
characters, props, creatures, environments, and dynamic objects from the active
story contract and validate those requirements per panel.

Every generated panel must pass through a second-pass script/image check before
it can feed a storyboard board, provider packet, or review page. Image
generation is nondeterministic, so the first script is only a hypothesis about
what should appear. After the image exists, run:

```text
panel script + generated panel image
-> visual verifier lists what is actually visible, missing, cropped, merged,
   static, pasted, or physically under-described
-> script writer repairs the panel script, realism ledger, and prompt deltas
-> image repair/regeneration only when the repaired script still requires
   missing visual facts
-> human/manual or VLM-assisted visual review
```

The post-generation script edit is required when the generated image introduces
new visible facts, omits required facts, or makes a prop/environment behavior
ambiguous. The script must explain every required and visible panel element that
matters to the shot: characters, scale, props, foreground architecture,
background creatures, weather, temperature, motion, sound when relevant,
material state, and environmental interaction.

Before a storyboard panel can feed a provider packet, write a
`panel_continuity_and_repair_ledger.json` with one record per panel:

```json
{
  "panel": 9,
  "required_visible_entities": ["character_horus", "character_embry"],
  "required_props": ["patio_table", "umbrella", "tea_service"],
  "required_environment": ["void_world_patio", "distant_creatures"],
  "required_dynamic_behaviors": [
    "umbrella fabric ripples or stays intentionally taut with reason",
    "tea steam curls, thins, or disperses",
    "background creatures move behind the conversation"
  ],
  "visual_review_status": "FAILED_VISUAL_REVIEW",
  "failed_requirements": ["character_embry_not_visibly_present"],
  "repair_action": "regenerate_panel_with_corrective_scillm_image_prompt",
  "repair_attempt": 1
}
```

Hard gates:

- Reject a panel if a required character is cropped out, hidden, merged into
  another character, converted into an unrelated identity, or not visible enough
  for review.
- Reject a panel if the script fails to explain a required visible element or a
  materially important generated element. "Everything" means every entity,
  foreground prop, highlighted surface, creature, weather force, temperature
  effect, motion cue, and sound cue that affects the shot's meaning or provider
  prompt.
- Reject a panel if a highlighted prop has no physical state or environmental
  behavior. Umbrellas should ripple, strain, cast shadows, shed droplets, or be
  explicitly still for a reason. Tea should steam, ripple, cool, reflect, or
  stain. Paper should lift, curl, crease, slide, or be intentionally pinned.
- Reject a panel if a moving creature or object lacks speed, direction,
  friction/contact, pause/attention behavior when relevant, and sound when the
  shot is audio-bearing. Example: a small creature crossing a stone railing must
  state claw contact, skitter rhythm, speed, whether it pauses to look, and how
  it exits frame.
- Reject a panel if a required environment effect is pasted over the image as a
  rectangular overlay instead of being regenerated as part of the scene.
- Reject a panel if the text says an entity or prop is present but the rendered
  panel does not visibly support that claim.

Self-repair loop:

```text
visual review failure
-> record failed requirements and failed image hash
-> write corrected prompt with MUST INCLUDE / MUST NOT INCLUDE deltas
-> call $scillm image generation through the receipt wrapper
-> inspect the new image
-> update panel symlinks, boards, receipts, and review page only if the new
   image satisfies the failed requirements
-> repeat until accepted, attempts exhausted, or blocked for missing source
```

Use `$scillm` image generation, not a chat completion, for image repair:

```bash
bash skills/scillm/run.sh generate-image \
  --auth codex-oauth \
  --prompt-file prompts/panel_09_repair.prompt.md \
  --out storyboard/regenerated_panels/panel_09_repair.png \
  --model gpt-image-2 \
  --quality high
```

The corrected prompt must preserve all accepted upstream context and add only
the course-correction constraints needed for the failed requirements. Do not
paper over visual failures by changing the report text alone.

Panel repair receipts must validate against the deterministic gate before any
panel can contribute to provider readiness:

```bash
uv run --project skills/persona-dream python \
  skills/persona-dream/scripts/validate_panel_repair_gate.py \
  /path/to/panel_repair_gate_receipt.json \
  --require-provider-eligible
```

The validator rejects partial pass labels such as `PASS_SCRIPT_COVERAGE`,
`PASS_REFERENCE_EVIDENCE`, and `PASS_VISUAL_REVIEW` as final panel statuses.
Script, reference, visual, no-overlay, post-generation script, and provider
media checks are subgates; the only normal final pass state is
`PASS_PANEL_REVIEWED`.

## Provider Final Gate

Before a Kling, Wan, ComfyUI, or other provider video call is allowed, write a
final provider-readiness gate receipt. A provider packet is not live-submittable
unless every required gate is `PASS` or explicitly human-accepted as an
intentional exception.

Required provider-readiness checks:

- Story, entity extraction, casting/reference research, reference sheets,
  storyboard panels, script realism, persona-memory grounding, visual
  continuity, voice/audio, provider payload schema, cost/mode, async handling,
  and artifact path/hash locks are all represented in machine-readable
  receipts.
- All storyboard panels have `visual_review_status: PASS` or an explicit
  human-accepted exception. `GENERATED_UNREVIEWED` cannot feed a paid provider
  call.
- All panel scripts pass the second-pass script/image check. Missing required
  entities, unexplained visible elements, static highlighted props, missing
  weather/temperature effects, or pasted overlays block provider execution.
- Experimental `persona-dream` provider planning defaults to `mode: std` /
  720p. Any `pro`, 1080p, or 4K route requires explicit cost/entitlement proof
  and current provider schema validation.
- Provider `external_task_id` is present and stable for webhook reconciliation.
- A reachable `callback_url` is configured, or a documented polling-only plan is
  accepted by the operator and represented in the packet.
- Provider-accessible media URLs exist for all uploaded images/audio, not only
  local filesystem paths.
- For voiced scenes, local voice candidates are not enough. Provider voice IDs
  must exist before `voice_list` is live-submittable.

Allowed status labels:

- `PROVIDER_READY`: all gates pass and no paid-call approval is missing.
- `BLOCKED_PROVIDER_GATE`: one or more required gates failed or are missing.
- `BLOCKED_AWAITING_HUMAN_APPROVAL`: all technical gates pass, but paid-call
  approval is missing.
- `DRY_RUN_NOT_LIVE_SUBMITTABLE`: useful review packet, but one or more live
  provider requirements are absent.

## Image Generation Lane

Still images are the normal visual unit for this skill: dream keyframes,
character sheets, scene sheets, frame prompts, and contact sheets. Pick the
image backend by the job, not by habit.

Use GPT image generation for quality-sensitive or final assets:

```text
final keyframes
character sheets
contact sheets
difficult prompt following
scene continuity references
identity-boundary-sensitive persona images
images requiring detailed "must include" / "must not include" constraints
```

Preferred project-agent path:

```bash
python scripts/generate_image.py \
  --auth codex-oauth \
  --prompt-file artifacts/images/<asset>.prompt.md \
  --out artifacts/images/<asset>.png \
  --events-out artifacts/images/<asset>.events.jsonl
```

Use the `$scillm` HTTP image endpoint for headless, API-key, CI, or service
flows. This path requires caller attribution and should be used for both GPT
image models and Chutes image models:

```text
POST http://localhost:4001/v1/images/generations
Authorization: Bearer sk-dev-proxy-123
X-Caller-Skill: persona-dream
```

Use `model: gpt-image-2` when prompt specificity and final quality matter. GPT
image prompts may be detailed and structured, and should preserve the dream
contract with sections such as:

```text
SUBJECT
CHARACTERS
SCENE
COMPOSITION
CONTINUITY
MOOD AND LIGHTING
MUST INCLUDE
MUST NOT INCLUDE
OUTPUT
```

Use `model: z-image-turbo` through `$scillm` for fast drafts, cheap variants,
pose/style exploration, rough perspective tests, and early contact-sheet
options. Do not call Chutes image endpoints directly from this skill; route
Chutes image models through `$scillm` so auth, retries, caller attribution, and
receipts remain consistent.

Use ComfyUI for still-image work only when graph control is the reason:

```text
pose-node workflows
multi-view or character-sheet workflows
ControlNet-like structure
reusable editable workflow JSON
human-inspectable graph state
```

Use Wan/TurboWan/ComfyUI I2V for motion after a keyframe is accepted. Do not
use I2V as the default still-image generator.

Every generated image or image batch must record:

```text
prompt file or rendered prompt
model and auth path
caller skill
output image path
receipt JSON
event log when available
hash
identity_boundary_receipt.json for persona, actor-like, or public-figure-adjacent images
```

## Motion Backend Lane

Motion generation is optional. Use it after `dream_packet.json` exists,
normally through `create-movie`, DevOps, or a future renderer adapter. The core
dream contract remains prompt/contact-sheet and memory reflection, because that
is the work product that feeds persona memory.

Preferred TurboDiffusion backend:

```text
Dockerized ComfyUI on the local A5000 running TurboDiffusion TurboWan2.2-I2V-A14B-720P
```

Use ComfyUI for short dream-motion clips when the TurboDiffusion Wan 2.2 model
files are mounted and
`/system_stats` plus `/object_info` prove the API is ready. ComfyUI provides the
project agent with editable workflow JSON, an API queue, output receipts, and a
human-inspectable graph that can later be opened in the web interface. `$surf`
may inspect or screenshot that UI, but execution should remain API-first. Store
`video_generation_receipt.json`, workflow JSON, API prompt JSON, output paths,
and hashes for every generated clip.

Chutes remains preferred for SPARTA LLM/VLM and for image/video models when the
exact model fits the task and a schema/canary receipt proves readiness. Treat
generic Chutes Wan2.1/turbowani2v examples as a different non-Turbo or
unverified lane until the receipt proves otherwise. Do not use them as proof of
the 4-step TurboDiffusion Wan2.2 path.

For TurboDiffusion I2V, record the clip unit in the prompt packet:

```text
default: 81 frames, nominal 5-second clip
extended: 121 frames, nominal 7.5-second clip
fps: 24
```

The 7.5-second path is allowed for the four-shot 30-second plan, but it is a
quality-sensitive generation choice. If a longer clip drifts, prefer prompt
repair or splitting that shot into 5-second subclips over accepting continuity
damage.

## Audio / Voice Handoff Lane

`persona-dream` emits `timed_transcript.json` and `voice_handoff_plan.json` so a
separate audio lane can render voices without confusing planning proof with
audio proof.

Recommended near-term audio lane:

```text
Kokoro base TTS
-> optional isolated KokoClone/Kanade conversion canary
-> ffprobe converted WAVs
-> FFmpeg dialogue bed
-> FFmpeg mux with accepted silent video
-> voice eval / listening receipt
```

Keep Kokoro/KokoClone receipts separate from ComfyUI receipts. ComfyUI owns
image/video graph execution; it does not own deterministic dialogue timing,
speaker identity receipts, future voice-training manifests, or mux proof.

Recommended future Embry Sparta Chat voice lane:

```text
curated authorized reference clips
-> transcript/alignment manifest
-> voice candidate generation
-> listening and/or model-assisted eval
-> train-voice / tts-horus fine-tuning proof
-> PersonaPlex live voice experiment only after offline clip proof
```

For any persona with local source audio, audiobook audio, interview audio, or
provided reference media, route source-clip selection through
`voice-segment-selector` or a voice/audio subagent that uses that skill. The
voice selector must produce a durable job directory, `candidates.jsonl`, and
review/export artifacts before any provider voice-clone step is considered
ready.

Example single-narrator audiobook selector lane:

```bash
PERSONA_ID=example_persona
JOB=/tmp/voice-segment-selector-${PERSONA_ID}
AUDIO=/path/to/persona/source_audio.wav

skills/voice-segment-selector/run.sh prepare \
  --input "$AUDIO" \
  --job-dir "$JOB" \
  --classifier f0 \
  --no-transcribe \
  --min-clip-sec 6 \
  --max-clip-sec 18
```

If chapter metadata exists from `extract-audiobook`, add `--chapters-json`.
Do not export, train, or upload a voice clone until the candidate has been
reviewed and accepted. The provider voice state remains
`VOICE_AUDIOBOOK_SOURCE_FOUND_PROVIDER_ID_MISSING` or
`VOICE_CLONE_CANDIDATE_FOUND_PROVIDER_ID_MISSING` until a provider returns a
custom `voice_id`.

Local A5000 guidance from `/home/graham/workspace/experiments/Wan2.2/README.md`:

```bash
cd /home/graham/workspace/experiments/Wan2.2
python generate.py \
  --task ti2v-5B \
  --size 1280*704 \
  --ckpt_dir ./Wan2.2-TI2V-5B \
  --offload_model True \
  --convert_model_dtype \
  --t5_cpu \
  --image /path/to/reference.png \
  --prompt "$(jq -r '.frame_prompts[0].prompt' /path/to/dream_packet.json)"
```

Use `Wan2.2-TI2V-5B` as the conservative local fallback for dream clips on a
24GB GPU. Treat the 24GB path as borderline: run one clip at a time, prefer
still-frame contact sheets for cheap runs, and fall back to no-video output on
OOM.

The distilled TurboDiffusion `TurboWan2.2-I2V-A14B-720P` ComfyUI path is a
separate optimized backend. It may be practical on the A5000 only when the
specific distilled model, UMT5 text encoder, VAE, and ComfyUI workflow are
mounted and proven by receipt. Do not generalize that to non-distilled
`T2V-A14B`, `I2V-A14B`, `S2V-14B`, or Animate-class jobs; route those to
`devops` for RunPod or larger GPU planning because the local Wan docs describe
those single-GPU paths as 80GB-class.

## Research / Bakeoff

Experimental story, contact-sheet, A/V lip-sync, and NAVA bakeoff materials live
under:

```text
research/bakeoff/
```

This subtree is a research lane, not the default `persona-dream` runtime. It
must preserve the bundle's no-memory-write rule, source-grounding rule,
consented-voice rule, shared-base-video invariant for ElevenLabs versus WavTTS,
and mandatory manual visual review before any PASS claim.

Start with the no-network smoke path:

```bash
./run.sh research-bakeoff smoke
```

Supported research commands:

```bash
./run.sh research-bakeoff smoke
./run.sh research-bakeoff story
./run.sh research-bakeoff contact-sheet --dry-run
./run.sh research-bakeoff elevenlabs
./run.sh research-bakeoff wavtts --confirm-voice-consent --ref-audio /path/to/voice.wav --ref-text "Exact reference transcript."
./run.sh research-bakeoff nava-inputs
./run.sh research-bakeoff nava-dry-run --nava-repo /path/to/NAVA
```

The default voice lane for hosted A/V baseline work is ElevenLabs through fal.
WavTTS requires explicit consent flags and owned/licensed/consented reference
audio. NAVA remains an experimental joint audio-video comparator. Contact-sheet
rendering uses a backend enum:

```text
dry_run | fal_flux | gpt_image | scillm_image | local_diffusion
```

Only `dry_run` and `fal_flux` are wired in this imported research bundle. Future
GPT image or `$scillm` image execution must preserve caller attribution,
receipts, and the backend-neutral `contact_sheets.json` contract. Use hosted or
voice-clone lanes only after the required keys, rights, receipts, and manual
review plan are available.

## Contact Sheet Sub-Skill

Use the local `contact-sheet` sub-skill when a story needs provider-ready visual
references or recallable image assets:

```bash
./run.sh contact-sheet build \
  --asset-root /mnt/storage12tb/skills/persona-dream/outputs/<run-id>/research/bakeoff/<ref-run> \
  --index-qdrant \
  --write-memory

./run.sh contact-sheet retrieve --query "Embry SPARTA archive character sheet"
```

This layer extracts or accepts story-derived visual entities:

```text
characters[] -> character sheets
environments[] -> room/world sheets
objects[] -> prop/UI/furniture sheets
creatures[] -> creature/background sheets
scene_bindings[] -> provider prompt inputs
```

Generated images stay on `/mnt/storage12tb`. Memory stores canonical metadata
and pointers to those files. Qdrant stores named `text_mm` and `image_mm`
vectors for recall. Do not store vector arrays in memory/ArangoDB.

## Validation

Run:

```bash
./sanity.sh
```

The sanity gate runs a positive-control fixture and verifies that the required
packet artifacts exist, that `contact_sheet.png` is a real PNG, and that memory
writeback is skipped without `--write-memory`. It also runs a `video_plan`
fixture and verifies the deterministic 30-second planning contract.

```

### `skills/persona-dream/sanity.sh`

```text
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=(uv run --project "${SCRIPT_DIR}" python)
OUT_DIR="$(mktemp -d /tmp/persona-dream-sanity.XXXXXX)"

"${SCRIPT_DIR}/run.sh" generate \
  --persona embry \
  --fixture "${SCRIPT_DIR}/scripts/fixtures/sample_residue.json" \
  --output-dir "${OUT_DIR}" \
  --run-id sanity \
  --no-write-memory

"${PYTHON[@]}" - "${OUT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
required = [
    "dream_request.json",
    "response.json",
    "residue_links.json",
    "contradiction_report.json",
    "dream_packet.json",
    "dream_prompt.txt",
    "frame_prompts.json",
    "contact_sheet.png",
    "dream_reflection.md",
    "memory_write_receipt.json",
]
missing = [name for name in required if not (out / name).exists()]
if missing:
    raise SystemExit(f"missing artifacts: {missing}")

if (out / "contact_sheet.png").read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
    raise SystemExit("contact_sheet.png is not a PNG")

packet = json.loads((out / "dream_packet.json").read_text())
receipt = json.loads((out / "memory_write_receipt.json").read_text())
response = json.loads((out / "response.json").read_text())

assert packet["schema"] == "persona_dream.packet.v1"
assert packet["persona"]["id"] == "embry"
assert len(packet["frame_prompts"]) >= 3
assert receipt["status"] == "skipped"
assert response["status"] == "ok"

print(json.dumps({
    "status": "ok",
    "mode": "static_dream",
    "output_dir": str(out),
    "artifact_count": len(required),
    "frame_count": len(packet["frame_prompts"]),
}, indent=2))
PY

VIDEO_OUT_DIR="$(mktemp -d /tmp/persona-dream-video-plan-sanity.XXXXXX)"

"${SCRIPT_DIR}/run.sh" generate \
  --mode video_plan \
  --persona horus \
  --secondary-persona embry \
  --fixture "${SCRIPT_DIR}/scripts/fixtures/sample_residue.json" \
  --about "creating the SPARTA Explorer app" \
  --scene "Horus and Embry have tea under a patio table with an umbrella on a 40k void world where Tyranids are playing in the background." \
  --duration-seconds 30 \
  --output-dir "${VIDEO_OUT_DIR}" \
  --run-id video-plan-sanity \
  --no-write-memory

"${PYTHON[@]}" - "${VIDEO_OUT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
required = [
    "dream_story.md",
    "dream_story.json",
    "character_scene_bible.json",
    "storyboard.json",
    "timed_transcript.json",
    "multimodal_prompts.json",
    "voice_handoff_plan.json",
    "pipeline_stage_report.json",
    "pipeline_stage_report.md",
    "manifest.json",
]
missing = [name for name in required if not (out / name).exists()]
if missing:
    raise SystemExit(f"missing video_plan artifacts: {missing}")

timed = json.loads((out / "timed_transcript.json").read_text())
prompts = json.loads((out / "multimodal_prompts.json").read_text())
voice = json.loads((out / "voice_handoff_plan.json").read_text())
bible = json.loads((out / "character_scene_bible.json").read_text())
report = json.loads((out / "pipeline_stage_report.json").read_text())
manifest = json.loads((out / "manifest.json").read_text())

shots = timed["shots"]
prompt_items = prompts["prompts"]
durations = [shot["duration_sec"] for shot in shots]
frame_counts = [prompt["num_frames"] for prompt in prompt_items]

assert timed["schema"] == "persona_dream.timed_transcript.v1"
assert timed["duration_seconds"] == 30
assert len(shots) == 4
assert durations == [7.5, 7.5, 7.5, 7.5]
assert len(prompt_items) == 4
assert frame_counts == [121, 121, 121, 121]
assert voice["schema"] == "persona_dream.voice_handoff_plan.v1"
assert voice["owner"] == "create-movie/audio-lane"
assert {speaker["speaker_id"] for speaker in voice["speakers"]} == {"embry", "horus"}
assert [line["speaker_id"] for line in voice["lines"]] == ["horus", "embry", "horus", "horus"]
assert any("voice_identity_boundary_receipt.json" in receipt for receipt in voice["required_receipts"])
assert bible["schema"] == "persona_dream.character_scene_bible.v1"
assert {character["character_id"] for character in bible["characters"]} == {"embry", "horus"}
assert bible["self_improvement_loop"]["schema"] == "persona_dream.self_improvement_loop.v1"
assert report["schema"] == "persona_dream.pipeline_stage_report.v1"
assert any(stage["stage_id"] == "stage_09_voice_handoff" for stage in report["stages"])
assert any(stage["stage_id"] == "stage_10_self_improvement_loop" for stage in report["stages"])
assert manifest["mode"] == "video_plan"
assert "i2v" in manifest["next_lanes"]
assert "voice_handoff_plan.json" in manifest["required_modes"]["video_plan"]

print(json.dumps({
    "status": "ok",
    "mode": "video_plan",
    "output_dir": str(out),
    "artifact_count": len(required),
    "shot_durations": durations,
    "frame_counts": frame_counts,
}, indent=2))
PY

"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_storyboard_first_fixture_regressions.py"

"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_valid.json" \
  --require-provider-eligible

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json" \
  --require-provider-eligible; then
  echo "invalid partial pass fixture unexpectedly passed" >&2
  exit 1
fi

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json" \
  --require-provider-eligible; then
  echo "invalid provider field fixture unexpectedly passed" >&2
  exit 1
fi

```

### `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`

```text
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "persona_dream.panel_repair_gate_receipt.v1",
  "title": "Persona Dream Panel Repair Gate Receipt",
  "type": "object",
  "required": [
    "schema",
    "run_id",
    "panel_id",
    "status",
    "script_coverage_status",
    "post_generation_script_coverage_status",
    "reference_evidence_status",
    "visual_review_status",
    "no_overlay_status",
    "provider_media_status",
    "requirement_matrix",
    "script_coverage_receipt",
    "post_generation_script_coverage_receipt",
    "reference_receipt",
    "generation_receipt",
    "visual_review_receipt",
    "no_overlay_receipt",
    "provider_mode",
    "provider_resolution",
    "external_task_id",
    "voice_id_status",
    "provider_packet_status",
    "provider_eligibility",
    "remaining_blockers"
  ],
  "properties": {
    "schema": {
      "const": "persona_dream.panel_repair_gate_receipt.v1"
    },
    "run_id": {
      "type": "string",
      "minLength": 1
    },
    "panel_id": {
      "type": "string",
      "minLength": 1
    },
    "status": {
      "enum": [
        "PASS_PANEL_REVIEWED",
        "HUMAN_ACCEPTED_WITH_WAIVER",
        "BLOCKED_UNREVIEWED_GENERATION",
        "BLOCKED_PENDING_INDEPENDENT_VERIFICATION",
        "BLOCKED_SCRIPT_COVERAGE",
        "BLOCKED_REFERENCE_EVIDENCE",
        "BLOCKED_VISUAL_CONTRADICTION",
        "BLOCKED_OVERLAY_OR_COMPOSITE",
        "BLOCKED_MAX_ATTEMPTS",
        "BLOCKED_ARTIFACT_INACCESSIBLE",
        "BLOCKED_PROVIDER_MEDIA_URLS",
        "BLOCKED_HUMAN_REVIEW_REQUIRED"
      ]
    },
    "script_coverage_status": {
      "enum": ["PASS", "FAIL", "WAIVED"]
    },
    "post_generation_script_coverage_status": {
      "enum": ["PASS", "FAIL", "WAIVED"]
    },
    "reference_evidence_status": {
      "enum": ["PASS", "FAIL", "WAIVED"]
    },
    "visual_review_status": {
      "enum": ["PASS", "FAIL", "WAIVED"]
    },
    "no_overlay_status": {
      "enum": ["PASS", "FAIL", "WAIVED"]
    },
    "provider_media_status": {
      "enum": ["PASS", "FAIL", "WAIVED"]
    },
    "provider_media_urls": {
      "type": "array",
      "items": {
        "type": "string",
        "pattern": "^https?://"
      }
    },
    "media_hashes": {
      "type": "object",
      "additionalProperties": {
        "type": "string",
        "pattern": "^sha256:"
      }
    },
    "provider_mode": {
      "enum": ["std", "pro", "4k"]
    },
    "provider_resolution": {
      "type": "string",
      "minLength": 1
    },
    "external_task_id": {
      "type": "string",
      "minLength": 1
    },
    "voice_id_status": {
      "enum": [
        "PROVIDER_VOICE_ID_READY",
        "SILENT_SCENE",
        "BLOCKED_MISSING_PROVIDER_VOICE_ID"
      ]
    },
    "provider_packet_status": {
      "enum": [
        "BLOCKED_PROVIDER_GATE",
        "DRY_RUN_NOT_LIVE_SUBMITTABLE",
        "PROVIDER_READY"
      ]
    },
    "provider_eligibility": {
      "type": "boolean"
    },
    "remaining_blockers": {
      "type": "array",
      "items": {
        "type": "string"
      }
    }
  },
  "additionalProperties": true
}

```

### `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_partial_pass.json`

```text
{
  "schema": "persona_dream.panel_repair_gate_receipt.v1",
  "run_id": "fixture-non-horus-dream",
  "panel_id": "panel_01",
  "status": "PASS_SCRIPT_COVERAGE",
  "script_coverage_status": "PASS",
  "post_generation_script_coverage_status": "FAIL",
  "reference_evidence_status": "PASS",
  "visual_review_status": "FAIL",
  "no_overlay_status": "FAIL",
  "provider_media_status": "FAIL",
  "requirement_matrix": "/tmp/fixture/panel_requirement_matrix.json",
  "script_coverage_receipt": "/tmp/fixture/script_coverage_receipt.json",
  "post_generation_script_coverage_receipt": "",
  "reference_receipt": "/tmp/fixture/reference_receipt.json",
  "generation_receipt": "/tmp/fixture/scillm_generation_receipt.json",
  "visual_review_receipt": "",
  "no_overlay_receipt": "",
  "provider_media_urls": [],
  "media_hashes": {},
  "provider_mode": "std",
  "provider_resolution": "720p",
  "callback_or_polling_plan": "",
  "external_task_id": "fixture-non-horus-dream-panel-01",
  "voice_id_status": "SILENT_SCENE",
  "cost_estimate": "",
  "provider_packet_status": "BLOCKED_PROVIDER_GATE",
  "provider_eligibility": true,
  "remaining_blockers": []
}

```

### `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_provider_fields.json`

```text
{
  "schema": "persona_dream.panel_repair_gate_receipt.v1",
  "run_id": "fixture-non-horus-dream",
  "panel_id": "panel_02",
  "status": "PASS_PANEL_REVIEWED",
  "script_coverage_status": "PASS",
  "post_generation_script_coverage_status": "PASS",
  "reference_evidence_status": "PASS",
  "visual_review_status": "PASS",
  "no_overlay_status": "PASS",
  "provider_media_status": "PASS",
  "requirement_matrix": "/tmp/fixture/panel_requirement_matrix.json",
  "script_coverage_receipt": "/tmp/fixture/script_coverage_receipt.json",
  "post_generation_script_coverage_receipt": "/tmp/fixture/post_generation_script_coverage_receipt.json",
  "reference_receipt": "/tmp/fixture/reference_receipt.json",
  "generation_receipt": "/tmp/fixture/scillm_generation_receipt.json",
  "visual_review_receipt": "/tmp/fixture/visual_review_receipt.json",
  "no_overlay_receipt": "/tmp/fixture/no_overlay_receipt.json",
  "provider_media_urls": [
    "/mnt/storage12tb/persona-dream/local-only-panel.png"
  ],
  "media_hashes": {
    "panel": "missing-sha-prefix"
  },
  "provider_mode": "4k",
  "provider_resolution": "4k",
  "callback_or_polling_plan": "",
  "external_task_id": "",
  "voice_id_status": "BLOCKED_MISSING_PROVIDER_VOICE_ID",
  "cost_estimate": "",
  "provider_packet_status": "PROVIDER_READY",
  "provider_eligibility": true,
  "remaining_blockers": []
}

```

### `skills/persona-dream/scripts/fixtures/panel_repair_gate_valid.json`

```text
{
  "schema": "persona_dream.panel_repair_gate_receipt.v1",
  "run_id": "fixture-non-horus-dream",
  "panel_id": "panel_01",
  "status": "PASS_PANEL_REVIEWED",
  "attempt": 2,
  "max_attempts": 4,
  "script_coverage_status": "PASS",
  "post_generation_script_coverage_status": "PASS",
  "reference_evidence_status": "PASS",
  "visual_review_status": "PASS",
  "no_overlay_status": "PASS",
  "provider_media_status": "PASS",
  "requirement_matrix": "/tmp/fixture/panel_requirement_matrix.json",
  "script_coverage_receipt": "/tmp/fixture/script_coverage_receipt.json",
  "post_generation_script_coverage_receipt": "/tmp/fixture/post_generation_script_coverage_receipt.json",
  "second_pass_script_delta": "/tmp/fixture/second_pass_script_delta.json",
  "reference_receipt": "/tmp/fixture/reference_receipt.json",
  "repair_prompt_package": "/tmp/fixture/repair_prompt_package.json",
  "generated_image_path": "/tmp/fixture/panel_01_attempt_02.png",
  "generation_receipt": "/tmp/fixture/scillm_generation_receipt.json",
  "visual_review_receipt": "/tmp/fixture/visual_review_receipt.json",
  "no_overlay_receipt": "/tmp/fixture/no_overlay_receipt.json",
  "provider_media_urls": [
    "https://storage.example.invalid/persona-dream/panel_01_attempt_02.png"
  ],
  "media_hashes": {
    "panel": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "provider_mode": "std",
  "provider_resolution": "720p",
  "callback_or_polling_plan": "/tmp/fixture/callback_or_polling_plan.json",
  "external_task_id": "fixture-non-horus-dream-panel-01",
  "voice_id_status": "SILENT_SCENE",
  "cost_estimate": "/tmp/fixture/cost_estimate.json",
  "provider_packet_status": "PROVIDER_READY",
  "status_transition_log": "/tmp/fixture/status_transition_log.jsonl",
  "provider_eligibility": true,
  "remaining_blockers": []
}

```

### `skills/persona-dream/scripts/validate_panel_repair_gate.py`

```text
#!/usr/bin/env python3
"""Validate a persona-dream panel repair gate receipt.

This intentionally avoids an external jsonschema dependency so the gate can run
inside lightweight review and sanity environments.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


FINAL_STATUSES = {
    "PASS_PANEL_REVIEWED",
    "HUMAN_ACCEPTED_WITH_WAIVER",
    "BLOCKED_UNREVIEWED_GENERATION",
    "BLOCKED_PENDING_INDEPENDENT_VERIFICATION",
    "BLOCKED_SCRIPT_COVERAGE",
    "BLOCKED_REFERENCE_EVIDENCE",
    "BLOCKED_VISUAL_CONTRADICTION",
    "BLOCKED_OVERLAY_OR_COMPOSITE",
    "BLOCKED_MAX_ATTEMPTS",
    "BLOCKED_ARTIFACT_INACCESSIBLE",
    "BLOCKED_PROVIDER_MEDIA_URLS",
    "BLOCKED_HUMAN_REVIEW_REQUIRED",
}

PARTIAL_PASS_STATUSES = {
    "PASS_SCRIPT_COVERAGE",
    "PASS_REFERENCE_EVIDENCE",
    "PASS_VISUAL_REVIEW",
}

SUBGATES = [
    "script_coverage_status",
    "post_generation_script_coverage_status",
    "reference_evidence_status",
    "visual_review_status",
    "no_overlay_status",
    "provider_media_status",
]

REQUIRED_RECEIPTS = [
    "requirement_matrix",
    "script_coverage_receipt",
    "post_generation_script_coverage_receipt",
    "reference_receipt",
    "generation_receipt",
    "visual_review_receipt",
    "no_overlay_receipt",
]


def non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_receipt(receipt: dict[str, Any], require_provider_eligible: bool) -> list[str]:
    errors: list[str] = []

    if receipt.get("schema") != "persona_dream.panel_repair_gate_receipt.v1":
        fail(errors, "schema must be persona_dream.panel_repair_gate_receipt.v1")

    for field in ("run_id", "panel_id"):
        if not non_empty_string(receipt.get(field)):
            fail(errors, f"{field} is required")

    status = receipt.get("status")
    if status in PARTIAL_PASS_STATUSES:
        fail(errors, f"{status} is an intermediate subgate, not a final panel status")
    if status not in FINAL_STATUSES:
        fail(errors, f"status must be one of {sorted(FINAL_STATUSES)}")

    for subgate in SUBGATES:
        value = receipt.get(subgate)
        if value not in {"PASS", "FAIL", "WAIVED"}:
            fail(errors, f"{subgate} must be PASS, FAIL, or WAIVED")

    for receipt_field in REQUIRED_RECEIPTS:
        if not non_empty_string(receipt.get(receipt_field)):
            fail(errors, f"{receipt_field} is required")

    provider_eligible = receipt.get("provider_eligibility")
    if not isinstance(provider_eligible, bool):
        fail(errors, "provider_eligibility must be boolean")

    remaining_blockers = receipt.get("remaining_blockers")
    if not isinstance(remaining_blockers, list) or not all(
        isinstance(item, str) for item in remaining_blockers
    ):
        fail(errors, "remaining_blockers must be a list of strings")

    if receipt.get("provider_mode") != "std" and not receipt.get("provider_mode_waiver"):
        fail(errors, "provider_mode must default to std unless provider_mode_waiver is true")

    if receipt.get("provider_resolution") != "720p" and not receipt.get("provider_mode_waiver"):
        fail(
            errors,
            "provider_resolution must default to 720p unless provider_mode_waiver is true",
        )

    if not non_empty_string(receipt.get("external_task_id")):
        fail(errors, "external_task_id is required")

    if not non_empty_string(receipt.get("callback_or_polling_plan")):
        fail(errors, "callback_or_polling_plan is required")

    voice_status = receipt.get("voice_id_status")
    if voice_status not in {
        "PROVIDER_VOICE_ID_READY",
        "SILENT_SCENE",
        "BLOCKED_MISSING_PROVIDER_VOICE_ID",
    }:
        fail(errors, "voice_id_status is invalid")

    if not non_empty_string(receipt.get("cost_estimate")):
        fail(errors, "cost_estimate is required")

    provider_urls = receipt.get("provider_media_urls")
    if not isinstance(provider_urls, list) or not provider_urls:
        fail(errors, "provider_media_urls must contain at least one URL")
    elif not all(isinstance(url, str) and url.startswith(("http://", "https://")) for url in provider_urls):
        fail(errors, "provider_media_urls must be provider-accessible http(s) URLs")

    media_hashes = receipt.get("media_hashes")
    if not isinstance(media_hashes, dict) or not media_hashes:
        fail(errors, "media_hashes must contain at least one sha256 hash")
    elif not all(isinstance(value, str) and value.startswith("sha256:") for value in media_hashes.values()):
        fail(errors, "media_hashes values must start with sha256:")

    provider_packet_status = receipt.get("provider_packet_status")
    if provider_packet_status not in {
        "BLOCKED_PROVIDER_GATE",
        "DRY_RUN_NOT_LIVE_SUBMITTABLE",
        "PROVIDER_READY",
    }:
        fail(errors, "provider_packet_status is invalid")

    hard_pass = (
        status == "PASS_PANEL_REVIEWED"
        and all(receipt.get(subgate) == "PASS" for subgate in SUBGATES)
        and voice_status in {"PROVIDER_VOICE_ID_READY", "SILENT_SCENE"}
        and receipt.get("provider_mode") == "std"
        and receipt.get("provider_resolution") == "720p"
        and provider_packet_status == "PROVIDER_READY"
        and isinstance(provider_urls, list)
        and bool(provider_urls)
        and isinstance(media_hashes, dict)
        and bool(media_hashes)
        and not remaining_blockers
    )

    if provider_eligible and not hard_pass:
        fail(errors, "provider_eligibility=true requires PASS_PANEL_REVIEWED and all provider subgates")

    if require_provider_eligible and not hard_pass:
        fail(errors, "receipt is not provider eligible")

    if status == "PASS_PANEL_REVIEWED" and not hard_pass:
        fail(errors, "PASS_PANEL_REVIEWED requires all subgates and provider fields to pass")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument(
        "--require-provider-eligible",
        action="store_true",
        help="Fail unless the receipt is provider-eligible.",
    )
    args = parser.parse_args(argv)

    receipt = json.loads(args.receipt.read_text())
    errors = validate_receipt(receipt, args.require_provider_eligible)
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        return 1

    print(json.dumps({"status": "PASS", "receipt": str(args.receipt)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

```


## Review Questions

1. Are there correctness bugs or edge cases in the implementation?
2. Are there security, data-loss, concurrency, or rollback risks?
3. Are the tests or validation steps sufficient for the stated change?
4. Is the change scoped tightly, or does it introduce unrelated behavior?
5. What exact fixes should be made before this is committed?

## Required Output Format

Return:

# Merge-blocking findings

## High severity

### H1. <title>
- Evidence:
- Impact:
- Exact fix:
- Test that should fail before the fix:

## Medium severity

Only include if it should block merge or materially affect safety.

# Important test gaps

List only tests required before merge.

# Merge recommendation

Use exactly one:
- SAFE_TO_MERGE
- SAFE_WITH_CONDITIONS
- CHANGES_REQUESTED
- NOT_SAFE
