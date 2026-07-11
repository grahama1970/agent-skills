# Round 4 Review: Persona-Dream Panel Repair Gate

## Reviewer Instructions

Review this as a code review request for Web GPT or another external reviewer.
Focus on correctness, regression risk, security, maintainability, test coverage, and mismatches between the stated intent and the actual diff.
Do not rewrite the entire implementation unless the diff is fundamentally unsafe.
Return findings first, grouped by severity, with concrete file/function references where possible.


## Decision Needed

Were the round-3 blocking findings repaired well enough to use the panel repair gate for the next phase?

## Rationale And Context

# Review Context Round 4: Persona-Dream Panel Repair Gate

## Objective

Round 3 WebGPT review returned `needs_changes`. This round asks whether the
remaining blockers are now repaired well enough to proceed to the next phase:
using the panel repair gate to repair blocked storyboard panels and the Kling
dry-run packet.

## Round 3 Blocking Findings

1. Provider voice source receipts were checked for existence/JSON only, not for
   matching `provider`, `voice_id`, and voice token evidence.
2. The JSON schema still diverged from the validator because required fields
   lacked property definitions/type constraints.

## Repairs Made

1. `skills/persona-dream/scripts/validate_panel_repair_gate.py`
   - Added `voice_source_matches`.
   - Under `--require-provider-eligible`, each provider voice source receipt
     must contain PASS/READY status or verdict, matching `provider`, matching
     `voice_id`, and matching `voice_token`.
   - Non-object top-level receipts now return structured JSON `FAIL` instead of
     an attribute error.

2. Voice fixtures
   - Updated `panel_repair_gate_artifacts/provider_voice_clone_receipt.json` to
     include `status: PASS`, `provider: kling`, `voice_id:
     voice_fixture_123`, and `voice_token: voice_1`.
   - Added `panel_repair_gate_valid_voiced.json`, which passes provider-eligible
     validation only with a matching provider voice receipt.
   - Added `panel_repair_gate_invalid_voice_source_mismatch.json`, which points
     at an existing valid JSON object that does not contain the matching
     provider voice proof and fails validation.

3. `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`
   - Added explicit property definitions for every required receipt/path field:
     `requirement_matrix`, `script_coverage_receipt`,
     `post_generation_script_coverage_receipt`, `reference_receipt`,
     `generation_receipt`, `visual_review_receipt`, `no_overlay_receipt`.
   - Added non-empty string definitions for `callback_or_polling_plan`,
     `external_task_id`, `cost_estimate`, and `provider_resolution`.
   - Added `minItems: 1` for `provider_media_urls`.
   - Added `minProperties: 1` for `media_hashes`.

4. `skills/persona-dream/scripts/check_panel_repair_gate_schema_consistency.py`
   - Now fails if any required schema field lacks a property definition.
   - Now checks required string fields have `type: string` and `minLength >= 1`.
   - Now checks required array/object fields have the expected constraints.

## Local Verification

Command:

```bash
bash skills/persona-dream/sanity.sh
```

Result:

- Overall command exited 0.
- Valid silent fixture passed.
- Valid voiced fixture passed.
- Invalid partial-pass fixture failed.
- Invalid provider-fields fixture failed.
- Invalid provider-voice-ID-claim fixture failed.
- Invalid missing-receipts fixture failed.
- Invalid voice source mismatch fixture failed with:
  - `voice source receipt provider does not match claimed provider`
  - `voice source receipt voice_id does not match claimed voice_id`
  - `voice source receipt voice_token does not match claimed token`
- Schema consistency check passed.

## Decision Requested

Are the round-3 blocking findings now repaired well enough to proceed to the
next phase: using this gate to repair the current blocked storyboard/panel
artifacts?

Return `satisfied` only for that next repair phase. Do not approve live Kling
execution.


## Expected Safety Contract

Provider voice readiness requires a source receipt with matching provider, voice_id, voice_token, and PASS/READY evidence.

The panel repair schema defines every required field with type constraints consistent with the validator.

Sanity proves valid silent and voiced receipts pass, while partial pass, missing provider fields, missing receipts, and voice source mismatches fail.


## Prior Critique Being Rechecked

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


## Non-goals For This Review

Do not approve live Kling execution.


## Original Review Request

(No request file supplied; review the current repository changes.)

## Repository Snapshot

- Generated at: `2026-06-14T03:43:27.767687+00:00`
- Working directory: `/home/graham/workspace/experiments/agent-skills`
- Repository root: `/home/graham/workspace/experiments/agent-skills`
- Branch: `feat/webgpt-no-activate`
- Remote: `git@github.com:grahama1970/agent-skills.git`

## Git Status

```text
?? skills/persona-dream/sanity.sh
?? skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json
?? skills/persona-dream/scripts/check_panel_repair_gate_schema_consistency.py
?? skills/persona-dream/scripts/fixtures/panel_repair_gate_artifacts/provider_voice_clone_receipt.json
?? skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json
?? skills/persona-dream/scripts/fixtures/panel_repair_gate_valid_voiced.json
?? skills/persona-dream/scripts/validate_panel_repair_gate.py
```

## Selected Review Files

These are the files intentionally selected for external review. Do not expand scope just because other files are changed in the worktree.

- `skills/persona-dream/scripts/validate_panel_repair_gate.py`
- `skills/persona-dream/scripts/check_panel_repair_gate_schema_consistency.py`
- `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`
- `skills/persona-dream/sanity.sh`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_valid_voiced.json`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_artifacts/provider_voice_clone_receipt.json`

## Changed Files In Selected Scope

- `skills/persona-dream/sanity.sh`
- `skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json`
- `skills/persona-dream/scripts/check_panel_repair_gate_schema_consistency.py`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_artifacts/provider_voice_clone_receipt.json`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json`
- `skills/persona-dream/scripts/fixtures/panel_repair_gate_valid_voiced.json`
- `skills/persona-dream/scripts/validate_panel_repair_gate.py`

## Diff

```diff
diff --git a/skills/persona-dream/sanity.sh b/skills/persona-dream/sanity.sh
new file mode 100755
index 000000000..97ebd34ef
--- /dev/null
+++ b/skills/persona-dream/sanity.sh
@@ -0,0 +1,183 @@
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
+"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
+  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_valid_voiced.json" \
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
+
+if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
+  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_voice_id_claim.json" \
+  --require-provider-eligible; then
+  echo "invalid voice id claim fixture unexpectedly passed" >&2
+  exit 1
+fi
+
+if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
+  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_missing_receipts.json" \
+  --require-provider-eligible; then
+  echo "invalid missing receipts fixture unexpectedly passed" >&2
+  exit 1
+fi
+
+if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
+  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json" \
+  --require-provider-eligible; then
+  echo "invalid voice source mismatch fixture unexpectedly passed" >&2
+  exit 1
+fi
+
+"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_panel_repair_gate_schema_consistency.py"

diff --git a/skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json b/skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json
new file mode 100644
index 000000000..a886d48f7
--- /dev/null
+++ b/skills/persona-dream/schemas/panel_repair_gate_receipt.schema.json
@@ -0,0 +1,199 @@
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
+    "provider_media_urls",
+    "media_hashes",
+    "provider_mode",
+    "provider_resolution",
+    "callback_or_polling_plan",
+    "external_task_id",
+    "voice_id_status",
+    "provider_voice_ids",
+    "cost_estimate",
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
+    "requirement_matrix": {
+      "type": "string",
+      "minLength": 1
+    },
+    "script_coverage_receipt": {
+      "type": "string",
+      "minLength": 1
+    },
+    "post_generation_script_coverage_receipt": {
+      "type": "string",
+      "minLength": 1
+    },
+    "reference_receipt": {
+      "type": "string",
+      "minLength": 1
+    },
+    "generation_receipt": {
+      "type": "string",
+      "minLength": 1
+    },
+    "visual_review_receipt": {
+      "type": "string",
+      "minLength": 1
+    },
+    "no_overlay_receipt": {
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
+      "minItems": 1,
+      "items": {
+        "type": "string",
+        "pattern": "^https?://"
+      }
+    },
+    "media_hashes": {
+      "type": "object",
+      "minProperties": 1,
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
+    "callback_or_polling_plan": {
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
+    "provider_voice_ids": {
+      "type": "object",
+      "additionalProperties": {
+        "type": "object",
+        "required": ["provider", "voice_id", "source_receipt"],
+        "properties": {
+          "provider": {
+            "type": "string",
+            "minLength": 1
+          },
+          "voice_id": {
+            "type": "string",
+            "minLength": 1
+          },
+          "source_receipt": {
+            "type": "string",
+            "minLength": 1
+          },
+          "hash": {
+            "type": "string"
+          },
+          "version": {
+            "type": "string"
+          }
+        },
+        "additionalProperties": true
+      }
+    },
+    "cost_estimate": {
+      "type": "string",
+      "minLength": 1
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

diff --git a/skills/persona-dream/scripts/check_panel_repair_gate_schema_consistency.py b/skills/persona-dream/scripts/check_panel_repair_gate_schema_consistency.py
new file mode 100644
index 000000000..abe813c66
--- /dev/null
+++ b/skills/persona-dream/scripts/check_panel_repair_gate_schema_consistency.py
@@ -0,0 +1,94 @@
+#!/usr/bin/env python3
+"""Check panel repair schema includes validator provider-required fields."""
+
+from __future__ import annotations
+
+import json
+from pathlib import Path
+
+
+SCRIPT_DIR = Path(__file__).resolve().parent
+SCHEMA_PATH = SCRIPT_DIR.parent / "schemas" / "panel_repair_gate_receipt.schema.json"
+
+REQUIRED_BY_VALIDATOR = {
+    "provider_media_urls",
+    "media_hashes",
+    "callback_or_polling_plan",
+    "cost_estimate",
+    "provider_voice_ids",
+    "external_task_id",
+    "voice_id_status",
+    "provider_mode",
+    "provider_resolution",
+    "provider_packet_status",
+    "provider_eligibility",
+}
+
+STRING_MIN_LENGTH_FIELDS = {
+    "run_id",
+    "panel_id",
+    "requirement_matrix",
+    "script_coverage_receipt",
+    "post_generation_script_coverage_receipt",
+    "reference_receipt",
+    "generation_receipt",
+    "visual_review_receipt",
+    "no_overlay_receipt",
+    "callback_or_polling_plan",
+    "external_task_id",
+    "cost_estimate",
+    "provider_resolution"
+}
+
+ARRAY_MIN_ITEMS_FIELDS = {
+    "provider_media_urls"
+}
+
+OBJECT_FIELDS = {
+    "media_hashes",
+    "provider_voice_ids"
+}
+
+
+def main() -> int:
+    schema = json.loads(SCHEMA_PATH.read_text())
+    required = set(schema.get("required", []))
+    properties = schema.get("properties", {})
+    missing_required = sorted(REQUIRED_BY_VALIDATOR - required)
+    missing_properties = sorted(required - set(properties))
+    invalid_string_fields = sorted(
+        field for field in STRING_MIN_LENGTH_FIELDS
+        if field in properties
+        and not (
+            properties[field].get("type") == "string"
+            and properties[field].get("minLength", 0) >= 1
+        )
+    )
+    invalid_array_fields = sorted(
+        field for field in ARRAY_MIN_ITEMS_FIELDS
+        if field in properties
+        and not (
+            properties[field].get("type") == "array"
+            and properties[field].get("minItems", 0) >= 1
+        )
+    )
+    invalid_object_fields = sorted(
+        field for field in OBJECT_FIELDS
+        if field in properties and properties[field].get("type") != "object"
+    )
+    failures = {
+        "missing_required": missing_required,
+        "missing_properties": missing_properties,
+        "invalid_string_fields": invalid_string_fields,
+        "invalid_array_fields": invalid_array_fields,
+        "invalid_object_fields": invalid_object_fields,
+    }
+    if any(failures.values()):
+        print(json.dumps({"status": "FAIL", **failures}, indent=2))
+        return 1
+    print(json.dumps({"status": "PASS", "schema": str(SCHEMA_PATH)}, indent=2))
+    return 0
+
+
+if __name__ == "__main__":
+    raise SystemExit(main())

diff --git a/skills/persona-dream/scripts/fixtures/panel_repair_gate_artifacts/provider_voice_clone_receipt.json b/skills/persona-dream/scripts/fixtures/panel_repair_gate_artifacts/provider_voice_clone_receipt.json
new file mode 100644
index 000000000..cf5d0badd
--- /dev/null
+++ b/skills/persona-dream/scripts/fixtures/panel_repair_gate_artifacts/provider_voice_clone_receipt.json
@@ -0,0 +1,6 @@
+{
+  "status": "PASS",
+  "provider": "kling",
+  "voice_id": "voice_fixture_123",
+  "voice_token": "voice_1"
+}

diff --git a/skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json b/skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json
new file mode 100644
index 000000000..25e9476ee
--- /dev/null
+++ b/skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json
@@ -0,0 +1,41 @@
+{
+  "schema": "persona_dream.panel_repair_gate_receipt.v1",
+  "run_id": "fixture-non-horus-dream",
+  "panel_id": "panel_06",
+  "status": "PASS_PANEL_REVIEWED",
+  "script_coverage_status": "PASS",
+  "post_generation_script_coverage_status": "PASS",
+  "reference_evidence_status": "PASS",
+  "visual_review_status": "PASS",
+  "no_overlay_status": "PASS",
+  "provider_media_status": "PASS",
+  "requirement_matrix": "panel_repair_gate_artifacts/requirement_matrix.json",
+  "script_coverage_receipt": "panel_repair_gate_artifacts/script_coverage_receipt.json",
+  "post_generation_script_coverage_receipt": "panel_repair_gate_artifacts/post_generation_script_coverage_receipt.json",
+  "reference_receipt": "panel_repair_gate_artifacts/reference_receipt.json",
+  "generation_receipt": "panel_repair_gate_artifacts/generation_receipt.json",
+  "visual_review_receipt": "panel_repair_gate_artifacts/visual_review_receipt.json",
+  "no_overlay_receipt": "panel_repair_gate_artifacts/no_overlay_receipt.json",
+  "provider_media_urls": [
+    "https://storage.example.invalid/persona-dream/panel_06.png"
+  ],
+  "media_hashes": {
+    "panel": "sha256:1111111111111111111111111111111111111111111111111111111111111111"
+  },
+  "provider_mode": "std",
+  "provider_resolution": "720p",
+  "callback_or_polling_plan": "panel_repair_gate_artifacts/callback_or_polling_plan.json",
+  "external_task_id": "fixture-non-horus-dream-panel-06",
+  "voice_id_status": "PROVIDER_VOICE_ID_READY",
+  "provider_voice_ids": {
+    "voice_1": {
+      "provider": "kling",
+      "voice_id": "voice_fixture_123",
+      "source_receipt": "panel_repair_gate_artifacts/requirement_matrix.json"
+    }
+  },
+  "cost_estimate": "panel_repair_gate_artifacts/cost_estimate.json",
+  "provider_packet_status": "PROVIDER_READY",
+  "provider_eligibility": true,
+  "remaining_blockers": []
+}

diff --git a/skills/persona-dream/scripts/fixtures/panel_repair_gate_valid_voiced.json b/skills/persona-dream/scripts/fixtures/panel_repair_gate_valid_voiced.json
new file mode 100644
index 000000000..4f8889231
--- /dev/null
+++ b/skills/persona-dream/scripts/fixtures/panel_repair_gate_valid_voiced.json
@@ -0,0 +1,42 @@
+{
+  "schema": "persona_dream.panel_repair_gate_receipt.v1",
+  "run_id": "fixture-non-horus-dream",
+  "panel_id": "panel_05",
+  "status": "PASS_PANEL_REVIEWED",
+  "script_coverage_status": "PASS",
+  "post_generation_script_coverage_status": "PASS",
+  "reference_evidence_status": "PASS",
+  "visual_review_status": "PASS",
+  "no_overlay_status": "PASS",
+  "provider_media_status": "PASS",
+  "requirement_matrix": "panel_repair_gate_artifacts/requirement_matrix.json",
+  "script_coverage_receipt": "panel_repair_gate_artifacts/script_coverage_receipt.json",
+  "post_generation_script_coverage_receipt": "panel_repair_gate_artifacts/post_generation_script_coverage_receipt.json",
+  "reference_receipt": "panel_repair_gate_artifacts/reference_receipt.json",
+  "generation_receipt": "panel_repair_gate_artifacts/generation_receipt.json",
+  "visual_review_receipt": "panel_repair_gate_artifacts/visual_review_receipt.json",
+  "no_overlay_receipt": "panel_repair_gate_artifacts/no_overlay_receipt.json",
+  "provider_media_urls": [
+    "https://storage.example.invalid/persona-dream/panel_05.png"
+  ],
+  "media_hashes": {
+    "panel": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
+  },
+  "provider_mode": "std",
+  "provider_resolution": "720p",
+  "callback_or_polling_plan": "panel_repair_gate_artifacts/callback_or_polling_plan.json",
+  "external_task_id": "fixture-non-horus-dream-panel-05",
+  "voice_id_status": "PROVIDER_VOICE_ID_READY",
+  "provider_voice_ids": {
+    "voice_1": {
+      "provider": "kling",
+      "voice_id": "voice_fixture_123",
+      "source_receipt": "panel_repair_gate_artifacts/provider_voice_clone_receipt.json",
+      "hash": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
+    }
+  },
+  "cost_estimate": "panel_repair_gate_artifacts/cost_estimate.json",
+  "provider_packet_status": "PROVIDER_READY",
+  "provider_eligibility": true,
+  "remaining_blockers": []
+}

diff --git a/skills/persona-dream/scripts/validate_panel_repair_gate.py b/skills/persona-dream/scripts/validate_panel_repair_gate.py
new file mode 100644
index 000000000..bd4425153
--- /dev/null
+++ b/skills/persona-dream/scripts/validate_panel_repair_gate.py
@@ -0,0 +1,338 @@
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
+RECEIPT_STATUS_FIELDS = {
+    "script_coverage_receipt": "script_coverage_status",
+    "post_generation_script_coverage_receipt": "post_generation_script_coverage_status",
+    "reference_receipt": "reference_evidence_status",
+    "visual_review_receipt": "visual_review_status",
+    "no_overlay_receipt": "no_overlay_status",
+}
+
+PROVIDER_REQUIRED_FIELDS = {
+    "provider_media_urls",
+    "media_hashes",
+    "callback_or_polling_plan",
+    "cost_estimate",
+    "provider_voice_ids",
+}
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
+def resolve_artifact_path(value: str, base_dir: Path) -> Path:
+    path = Path(value)
+    if path.is_absolute():
+        return path
+    return base_dir / path
+
+
+def read_json_artifact(value: str, base_dir: Path, field: str, errors: list[str]) -> dict[str, Any] | None:
+    path = resolve_artifact_path(value, base_dir)
+    if not path.exists():
+        fail(errors, f"{field} does not exist: {path}")
+        return None
+    try:
+        loaded = json.loads(path.read_text())
+    except Exception as exc:  # noqa: BLE001 - validator should report data errors.
+        fail(errors, f"{field} is not valid JSON: {path}: {exc}")
+        return None
+    if not isinstance(loaded, dict):
+        fail(errors, f"{field} must contain a JSON object: {path}")
+        return None
+    return loaded
+
+
+def status_matches(artifact: dict[str, Any], expected: str) -> bool:
+    observed = artifact.get("status") or artifact.get("verdict")
+    if isinstance(observed, str) and observed.upper() == expected:
+        return True
+    if expected == "PASS" and observed in {"ok", "passed", "PASS"}:
+        return True
+    return False
+
+
+def voice_source_matches(
+    artifact: dict[str, Any],
+    token: str,
+    provider: str,
+    voice_id: str,
+) -> list[str]:
+    errors: list[str] = []
+    observed = artifact.get("status") or artifact.get("verdict")
+    if not (
+        isinstance(observed, str)
+        and observed.upper() in {"PASS", "READY", "PROVIDER_VOICE_ID_READY"}
+    ):
+        errors.append("voice source receipt status/verdict must be PASS or READY")
+    if artifact.get("provider") != provider:
+        errors.append("voice source receipt provider does not match claimed provider")
+    if artifact.get("voice_id") != voice_id:
+        errors.append("voice source receipt voice_id does not match claimed voice_id")
+    if artifact.get("voice_token") != token:
+        errors.append("voice source receipt voice_token does not match claimed token")
+    return errors
+
+
+def validate_receipt(
+    receipt: dict[str, Any],
+    require_provider_eligible: bool,
+    base_dir: Path,
+) -> list[str]:
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
+    provider_voice_ids = receipt.get("provider_voice_ids")
+    if not isinstance(provider_voice_ids, dict):
+        fail(errors, "provider_voice_ids must be an object")
+    if voice_status == "PROVIDER_VOICE_ID_READY":
+        if not provider_voice_ids:
+            fail(errors, "provider_voice_ids is required when voice_id_status=PROVIDER_VOICE_ID_READY")
+        else:
+            for token, voice in provider_voice_ids.items():
+                if not isinstance(token, str) or not token.startswith("voice_"):
+                    fail(errors, f"provider_voice_ids key must be a voice token: {token!r}")
+                if not isinstance(voice, dict):
+                    fail(errors, f"provider_voice_ids.{token} must be an object")
+                    continue
+                if not non_empty_string(voice.get("provider")):
+                    fail(errors, f"provider_voice_ids.{token}.provider is required")
+                if not non_empty_string(voice.get("voice_id")):
+                    fail(errors, f"provider_voice_ids.{token}.voice_id is required")
+                if not non_empty_string(voice.get("source_receipt")):
+                    fail(errors, f"provider_voice_ids.{token}.source_receipt is required")
+                elif require_provider_eligible:
+                    source_artifact = read_json_artifact(
+                        voice["source_receipt"],
+                        base_dir,
+                        f"provider_voice_ids.{token}.source_receipt",
+                        errors,
+                    )
+                    if source_artifact is not None:
+                        source_errors = voice_source_matches(
+                            source_artifact,
+                            token,
+                            voice["provider"],
+                            voice["voice_id"],
+                        )
+                        for source_error in source_errors:
+                            fail(errors, f"provider_voice_ids.{token}.source_receipt: {source_error}")
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
+    if require_provider_eligible:
+        for receipt_field in REQUIRED_RECEIPTS:
+            value = receipt.get(receipt_field)
+            if non_empty_string(value):
+                artifact = read_json_artifact(value, base_dir, receipt_field, errors)
+                expected_status_field = RECEIPT_STATUS_FIELDS.get(receipt_field)
+                if artifact is not None and expected_status_field:
+                    expected_status = receipt.get(expected_status_field)
+                    if expected_status == "PASS" and not status_matches(artifact, "PASS"):
+                        fail(errors, f"{receipt_field} does not contain matching PASS evidence")
+
+        for field in ("callback_or_polling_plan", "cost_estimate"):
+            value = receipt.get(field)
+            if non_empty_string(value):
+                read_json_artifact(value, base_dir, field, errors)
+
+    hard_pass = (
+        status == "PASS_PANEL_REVIEWED"
+        and all(receipt.get(subgate) == "PASS" for subgate in SUBGATES)
+        and voice_status in {"PROVIDER_VOICE_ID_READY", "SILENT_SCENE"}
+        and (
+            voice_status == "SILENT_SCENE"
+            or (isinstance(provider_voice_ids, dict) and bool(provider_voice_ids))
+        )
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
+    if require_provider_eligible and provider_eligible is not True:
+        fail(errors, "--require-provider-eligible requires provider_eligibility=true")
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
+        "--artifact-root",
+        type=Path,
+        default=None,
+        help="Base directory for relative receipt paths. Defaults to the panel receipt directory.",
+    )
+    parser.add_argument(
+        "--require-provider-eligible",
+        action="store_true",
+        help="Fail unless the receipt is provider-eligible.",
+    )
+    args = parser.parse_args(argv)
+
+    receipt_path = args.receipt.resolve()
+    receipt = json.loads(receipt_path.read_text())
+    if not isinstance(receipt, dict):
+        print(json.dumps({"status": "FAIL", "errors": ["receipt must be a JSON object"]}, indent=2))
+        return 1
+    base_dir = args.artifact_root.resolve() if args.artifact_root else receipt_path.parent
+    errors = validate_receipt(receipt, args.require_provider_eligible, base_dir)
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

"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_valid_voiced.json" \
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

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_voice_id_claim.json" \
  --require-provider-eligible; then
  echo "invalid voice id claim fixture unexpectedly passed" >&2
  exit 1
fi

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_missing_receipts.json" \
  --require-provider-eligible; then
  echo "invalid missing receipts fixture unexpectedly passed" >&2
  exit 1
fi

if "${PYTHON[@]}" "${SCRIPT_DIR}/scripts/validate_panel_repair_gate.py" \
  "${SCRIPT_DIR}/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json" \
  --require-provider-eligible; then
  echo "invalid voice source mismatch fixture unexpectedly passed" >&2
  exit 1
fi

"${PYTHON[@]}" "${SCRIPT_DIR}/scripts/check_panel_repair_gate_schema_consistency.py"

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
    "provider_media_urls",
    "media_hashes",
    "provider_mode",
    "provider_resolution",
    "callback_or_polling_plan",
    "external_task_id",
    "voice_id_status",
    "provider_voice_ids",
    "cost_estimate",
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
    "requirement_matrix": {
      "type": "string",
      "minLength": 1
    },
    "script_coverage_receipt": {
      "type": "string",
      "minLength": 1
    },
    "post_generation_script_coverage_receipt": {
      "type": "string",
      "minLength": 1
    },
    "reference_receipt": {
      "type": "string",
      "minLength": 1
    },
    "generation_receipt": {
      "type": "string",
      "minLength": 1
    },
    "visual_review_receipt": {
      "type": "string",
      "minLength": 1
    },
    "no_overlay_receipt": {
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
      "minItems": 1,
      "items": {
        "type": "string",
        "pattern": "^https?://"
      }
    },
    "media_hashes": {
      "type": "object",
      "minProperties": 1,
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
    "callback_or_polling_plan": {
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
    "provider_voice_ids": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["provider", "voice_id", "source_receipt"],
        "properties": {
          "provider": {
            "type": "string",
            "minLength": 1
          },
          "voice_id": {
            "type": "string",
            "minLength": 1
          },
          "source_receipt": {
            "type": "string",
            "minLength": 1
          },
          "hash": {
            "type": "string"
          },
          "version": {
            "type": "string"
          }
        },
        "additionalProperties": true
      }
    },
    "cost_estimate": {
      "type": "string",
      "minLength": 1
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

### `skills/persona-dream/scripts/check_panel_repair_gate_schema_consistency.py`

```text
#!/usr/bin/env python3
"""Check panel repair schema includes validator provider-required fields."""

from __future__ import annotations

import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR.parent / "schemas" / "panel_repair_gate_receipt.schema.json"

REQUIRED_BY_VALIDATOR = {
    "provider_media_urls",
    "media_hashes",
    "callback_or_polling_plan",
    "cost_estimate",
    "provider_voice_ids",
    "external_task_id",
    "voice_id_status",
    "provider_mode",
    "provider_resolution",
    "provider_packet_status",
    "provider_eligibility",
}

STRING_MIN_LENGTH_FIELDS = {
    "run_id",
    "panel_id",
    "requirement_matrix",
    "script_coverage_receipt",
    "post_generation_script_coverage_receipt",
    "reference_receipt",
    "generation_receipt",
    "visual_review_receipt",
    "no_overlay_receipt",
    "callback_or_polling_plan",
    "external_task_id",
    "cost_estimate",
    "provider_resolution"
}

ARRAY_MIN_ITEMS_FIELDS = {
    "provider_media_urls"
}

OBJECT_FIELDS = {
    "media_hashes",
    "provider_voice_ids"
}


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text())
    required = set(schema.get("required", []))
    properties = schema.get("properties", {})
    missing_required = sorted(REQUIRED_BY_VALIDATOR - required)
    missing_properties = sorted(required - set(properties))
    invalid_string_fields = sorted(
        field for field in STRING_MIN_LENGTH_FIELDS
        if field in properties
        and not (
            properties[field].get("type") == "string"
            and properties[field].get("minLength", 0) >= 1
        )
    )
    invalid_array_fields = sorted(
        field for field in ARRAY_MIN_ITEMS_FIELDS
        if field in properties
        and not (
            properties[field].get("type") == "array"
            and properties[field].get("minItems", 0) >= 1
        )
    )
    invalid_object_fields = sorted(
        field for field in OBJECT_FIELDS
        if field in properties and properties[field].get("type") != "object"
    )
    failures = {
        "missing_required": missing_required,
        "missing_properties": missing_properties,
        "invalid_string_fields": invalid_string_fields,
        "invalid_array_fields": invalid_array_fields,
        "invalid_object_fields": invalid_object_fields,
    }
    if any(failures.values()):
        print(json.dumps({"status": "FAIL", **failures}, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "schema": str(SCHEMA_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

```

### `skills/persona-dream/scripts/fixtures/panel_repair_gate_artifacts/provider_voice_clone_receipt.json`

```text
{
  "status": "PASS",
  "provider": "kling",
  "voice_id": "voice_fixture_123",
  "voice_token": "voice_1"
}

```

### `skills/persona-dream/scripts/fixtures/panel_repair_gate_invalid_voice_source_mismatch.json`

```text
{
  "schema": "persona_dream.panel_repair_gate_receipt.v1",
  "run_id": "fixture-non-horus-dream",
  "panel_id": "panel_06",
  "status": "PASS_PANEL_REVIEWED",
  "script_coverage_status": "PASS",
  "post_generation_script_coverage_status": "PASS",
  "reference_evidence_status": "PASS",
  "visual_review_status": "PASS",
  "no_overlay_status": "PASS",
  "provider_media_status": "PASS",
  "requirement_matrix": "panel_repair_gate_artifacts/requirement_matrix.json",
  "script_coverage_receipt": "panel_repair_gate_artifacts/script_coverage_receipt.json",
  "post_generation_script_coverage_receipt": "panel_repair_gate_artifacts/post_generation_script_coverage_receipt.json",
  "reference_receipt": "panel_repair_gate_artifacts/reference_receipt.json",
  "generation_receipt": "panel_repair_gate_artifacts/generation_receipt.json",
  "visual_review_receipt": "panel_repair_gate_artifacts/visual_review_receipt.json",
  "no_overlay_receipt": "panel_repair_gate_artifacts/no_overlay_receipt.json",
  "provider_media_urls": [
    "https://storage.example.invalid/persona-dream/panel_06.png"
  ],
  "media_hashes": {
    "panel": "sha256:1111111111111111111111111111111111111111111111111111111111111111"
  },
  "provider_mode": "std",
  "provider_resolution": "720p",
  "callback_or_polling_plan": "panel_repair_gate_artifacts/callback_or_polling_plan.json",
  "external_task_id": "fixture-non-horus-dream-panel-06",
  "voice_id_status": "PROVIDER_VOICE_ID_READY",
  "provider_voice_ids": {
    "voice_1": {
      "provider": "kling",
      "voice_id": "voice_fixture_123",
      "source_receipt": "panel_repair_gate_artifacts/requirement_matrix.json"
    }
  },
  "cost_estimate": "panel_repair_gate_artifacts/cost_estimate.json",
  "provider_packet_status": "PROVIDER_READY",
  "provider_eligibility": true,
  "remaining_blockers": []
}

```

### `skills/persona-dream/scripts/fixtures/panel_repair_gate_valid_voiced.json`

```text
{
  "schema": "persona_dream.panel_repair_gate_receipt.v1",
  "run_id": "fixture-non-horus-dream",
  "panel_id": "panel_05",
  "status": "PASS_PANEL_REVIEWED",
  "script_coverage_status": "PASS",
  "post_generation_script_coverage_status": "PASS",
  "reference_evidence_status": "PASS",
  "visual_review_status": "PASS",
  "no_overlay_status": "PASS",
  "provider_media_status": "PASS",
  "requirement_matrix": "panel_repair_gate_artifacts/requirement_matrix.json",
  "script_coverage_receipt": "panel_repair_gate_artifacts/script_coverage_receipt.json",
  "post_generation_script_coverage_receipt": "panel_repair_gate_artifacts/post_generation_script_coverage_receipt.json",
  "reference_receipt": "panel_repair_gate_artifacts/reference_receipt.json",
  "generation_receipt": "panel_repair_gate_artifacts/generation_receipt.json",
  "visual_review_receipt": "panel_repair_gate_artifacts/visual_review_receipt.json",
  "no_overlay_receipt": "panel_repair_gate_artifacts/no_overlay_receipt.json",
  "provider_media_urls": [
    "https://storage.example.invalid/persona-dream/panel_05.png"
  ],
  "media_hashes": {
    "panel": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  },
  "provider_mode": "std",
  "provider_resolution": "720p",
  "callback_or_polling_plan": "panel_repair_gate_artifacts/callback_or_polling_plan.json",
  "external_task_id": "fixture-non-horus-dream-panel-05",
  "voice_id_status": "PROVIDER_VOICE_ID_READY",
  "provider_voice_ids": {
    "voice_1": {
      "provider": "kling",
      "voice_id": "voice_fixture_123",
      "source_receipt": "panel_repair_gate_artifacts/provider_voice_clone_receipt.json",
      "hash": "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    }
  },
  "cost_estimate": "panel_repair_gate_artifacts/cost_estimate.json",
  "provider_packet_status": "PROVIDER_READY",
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

RECEIPT_STATUS_FIELDS = {
    "script_coverage_receipt": "script_coverage_status",
    "post_generation_script_coverage_receipt": "post_generation_script_coverage_status",
    "reference_receipt": "reference_evidence_status",
    "visual_review_receipt": "visual_review_status",
    "no_overlay_receipt": "no_overlay_status",
}

PROVIDER_REQUIRED_FIELDS = {
    "provider_media_urls",
    "media_hashes",
    "callback_or_polling_plan",
    "cost_estimate",
    "provider_voice_ids",
}


def non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def resolve_artifact_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base_dir / path


def read_json_artifact(value: str, base_dir: Path, field: str, errors: list[str]) -> dict[str, Any] | None:
    path = resolve_artifact_path(value, base_dir)
    if not path.exists():
        fail(errors, f"{field} does not exist: {path}")
        return None
    try:
        loaded = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 - validator should report data errors.
        fail(errors, f"{field} is not valid JSON: {path}: {exc}")
        return None
    if not isinstance(loaded, dict):
        fail(errors, f"{field} must contain a JSON object: {path}")
        return None
    return loaded


def status_matches(artifact: dict[str, Any], expected: str) -> bool:
    observed = artifact.get("status") or artifact.get("verdict")
    if isinstance(observed, str) and observed.upper() == expected:
        return True
    if expected == "PASS" and observed in {"ok", "passed", "PASS"}:
        return True
    return False


def voice_source_matches(
    artifact: dict[str, Any],
    token: str,
    provider: str,
    voice_id: str,
) -> list[str]:
    errors: list[str] = []
    observed = artifact.get("status") or artifact.get("verdict")
    if not (
        isinstance(observed, str)
        and observed.upper() in {"PASS", "READY", "PROVIDER_VOICE_ID_READY"}
    ):
        errors.append("voice source receipt status/verdict must be PASS or READY")
    if artifact.get("provider") != provider:
        errors.append("voice source receipt provider does not match claimed provider")
    if artifact.get("voice_id") != voice_id:
        errors.append("voice source receipt voice_id does not match claimed voice_id")
    if artifact.get("voice_token") != token:
        errors.append("voice source receipt voice_token does not match claimed token")
    return errors


def validate_receipt(
    receipt: dict[str, Any],
    require_provider_eligible: bool,
    base_dir: Path,
) -> list[str]:
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

    provider_voice_ids = receipt.get("provider_voice_ids")
    if not isinstance(provider_voice_ids, dict):
        fail(errors, "provider_voice_ids must be an object")
    if voice_status == "PROVIDER_VOICE_ID_READY":
        if not provider_voice_ids:
            fail(errors, "provider_voice_ids is required when voice_id_status=PROVIDER_VOICE_ID_READY")
        else:
            for token, voice in provider_voice_ids.items():
                if not isinstance(token, str) or not token.startswith("voice_"):
                    fail(errors, f"provider_voice_ids key must be a voice token: {token!r}")
                if not isinstance(voice, dict):
                    fail(errors, f"provider_voice_ids.{token} must be an object")
                    continue
                if not non_empty_string(voice.get("provider")):
                    fail(errors, f"provider_voice_ids.{token}.provider is required")
                if not non_empty_string(voice.get("voice_id")):
                    fail(errors, f"provider_voice_ids.{token}.voice_id is required")
                if not non_empty_string(voice.get("source_receipt")):
                    fail(errors, f"provider_voice_ids.{token}.source_receipt is required")
                elif require_provider_eligible:
                    source_artifact = read_json_artifact(
                        voice["source_receipt"],
                        base_dir,
                        f"provider_voice_ids.{token}.source_receipt",
                        errors,
                    )
                    if source_artifact is not None:
                        source_errors = voice_source_matches(
                            source_artifact,
                            token,
                            voice["provider"],
                            voice["voice_id"],
                        )
                        for source_error in source_errors:
                            fail(errors, f"provider_voice_ids.{token}.source_receipt: {source_error}")

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

    if require_provider_eligible:
        for receipt_field in REQUIRED_RECEIPTS:
            value = receipt.get(receipt_field)
            if non_empty_string(value):
                artifact = read_json_artifact(value, base_dir, receipt_field, errors)
                expected_status_field = RECEIPT_STATUS_FIELDS.get(receipt_field)
                if artifact is not None and expected_status_field:
                    expected_status = receipt.get(expected_status_field)
                    if expected_status == "PASS" and not status_matches(artifact, "PASS"):
                        fail(errors, f"{receipt_field} does not contain matching PASS evidence")

        for field in ("callback_or_polling_plan", "cost_estimate"):
            value = receipt.get(field)
            if non_empty_string(value):
                read_json_artifact(value, base_dir, field, errors)

    hard_pass = (
        status == "PASS_PANEL_REVIEWED"
        and all(receipt.get(subgate) == "PASS" for subgate in SUBGATES)
        and voice_status in {"PROVIDER_VOICE_ID_READY", "SILENT_SCENE"}
        and (
            voice_status == "SILENT_SCENE"
            or (isinstance(provider_voice_ids, dict) and bool(provider_voice_ids))
        )
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

    if require_provider_eligible and provider_eligible is not True:
        fail(errors, "--require-provider-eligible requires provider_eligibility=true")

    if require_provider_eligible and not hard_pass:
        fail(errors, "receipt is not provider eligible")

    if status == "PASS_PANEL_REVIEWED" and not hard_pass:
        fail(errors, "PASS_PANEL_REVIEWED requires all subgates and provider fields to pass")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help="Base directory for relative receipt paths. Defaults to the panel receipt directory.",
    )
    parser.add_argument(
        "--require-provider-eligible",
        action="store_true",
        help="Fail unless the receipt is provider-eligible.",
    )
    args = parser.parse_args(argv)

    receipt_path = args.receipt.resolve()
    receipt = json.loads(receipt_path.read_text())
    if not isinstance(receipt, dict):
        print(json.dumps({"status": "FAIL", "errors": ["receipt must be a JSON object"]}, indent=2))
        return 1
    base_dir = args.artifact_root.resolve() if args.artifact_root else receipt_path.parent
    errors = validate_receipt(receipt, args.require_provider_eligible, base_dir)
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
