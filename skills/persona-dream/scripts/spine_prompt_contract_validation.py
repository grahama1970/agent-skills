"""Deterministic Persona Dream spine prompt-contract validators."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERIALIZED_TEXT_FIELDS = {
    "text",
    "description",
    "story",
    "source_context",
    "prompt",
    "script",
    "dialogue",
    "action",
    "summary",
}

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def require_sha256(value: Any, path: str, blockers: list[str], code: str = "invalid_sha256") -> str:
    if not isinstance(value, str) or not SHA256_RE.match(value):
        blockers.append(f"{code}:{path}")
        return ""
    return value


def require_path_hash(path_value: Any, sha_value: Any, path: str, blockers: list[str]) -> None:
    local_path = require_nonempty_string(path_value, f"{path}.path", blockers, "missing_path")
    expected_sha = require_sha256(sha_value, f"{path}.sha256", blockers)
    if not local_path or not expected_sha:
        return
    resolved = Path(local_path)
    if not resolved.exists():
        blockers.append(f"missing_hashed_file:{path}.path")
        return
    actual_sha = sha256_path(resolved)
    if actual_sha != expected_sha:
        blockers.append(f"sha256_mismatch:{path}:{actual_sha}")


def looks_like_serialized_json(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not ((text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]"))):
        return False
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, (dict, list))


def iter_serialized_text_values(value: Any, path: str = "") -> list[str]:
    blockers: list[str] = []
    if isinstance(value, dict):
        raw_source = value.get("raw_source")
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key == "raw_source" and isinstance(child, dict):
                continue
            if key in SERIALIZED_TEXT_FIELDS or key.startswith("prompt_sections"):
                if looks_like_serialized_json(child):
                    blockers.append(f"serialized_json_blob_in_prompt_text:{child_path}")
            blockers.extend(iter_serialized_text_values(child, child_path))
        if isinstance(raw_source, dict):
            if raw_source.get("may_feed_prompt") is not False or raw_source.get("may_display_directly") is not False:
                blockers.append("raw_source_not_quarantined")
            if "content" in raw_source and "content_hash" in raw_source:
                expected_hash = require_sha256(raw_source.get("content_hash"), "raw_source.content_hash", blockers)
                if expected_hash and sha256_text(str(raw_source.get("content"))) != expected_hash:
                    blockers.append("raw_source_content_hash_mismatch")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            blockers.extend(iter_serialized_text_values(child, f"{path}[{index}]"))
    return blockers


def require_mapping(value: Any, path: str, blockers: list[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        blockers.append(f"{code}:{path}")
        return {}
    return value


def require_nonempty_list(value: Any, path: str, blockers: list[str], code: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        blockers.append(f"{code}:{path}")
        return []
    return value


def require_nonempty_string(value: Any, path: str, blockers: list[str], code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        blockers.append(f"{code}:{path}")
        return ""
    return value


def validate_phase01(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != "persona_dream.phase01.memory_residue_contract.v1":
        blockers.append("schema_mismatch:persona_dream.phase01.memory_residue_contract.v1")
    if payload.get("phase") != "01_memory_residue":
        blockers.append("phase_mismatch:01_memory_residue")
    require_nonempty_string(payload.get("run_id"), "run_id", blockers, "missing_run_id")
    source_residue = require_nonempty_list(payload.get("source_residue"), "source_residue", blockers, "missing_source_residue")
    for index, residue in enumerate(source_residue):
        item = require_mapping(residue, f"source_residue[{index}]", blockers, "invalid_source_residue")
        require_nonempty_string(item.get("source_id"), f"source_residue[{index}].source_id", blockers, "missing_source_id")
        require_sha256(item.get("source_hash"), f"source_residue[{index}].source_hash", blockers, "missing_source_hash")
        if "source_path" in item:
            require_path_hash(item.get("source_path"), item.get("source_hash"), f"source_residue[{index}]", blockers)
    typed_idea = require_mapping(payload.get("typed_idea_fields"), "typed_idea_fields", blockers, "missing_typed_idea_fields")
    require_nonempty_string(typed_idea.get("premise"), "typed_idea_fields.premise", blockers, "missing_typed_premise")
    require_nonempty_list(payload.get("prompt_safe_text"), "prompt_safe_text", blockers, "missing_prompt_safe_text")
    for index, media_ref in enumerate(payload.get("media_references", [])):
        media = require_mapping(media_ref, f"media_references[{index}]", blockers, "invalid_media_reference")
        require_nonempty_string(media.get("asset_id"), f"media_references[{index}].asset_id", blockers, "missing_asset_id")
        require_path_hash(media.get("path"), media.get("sha256"), f"media_references[{index}]", blockers)
    downstream = require_mapping(payload.get("downstream_contract"), "downstream_contract", blockers, "missing_downstream_contract")
    if downstream.get("may_feed_phase02") is not True:
        blockers.append("downstream_contract_may_feed_phase02_not_true")
    if payload.get("serialized_json_as_prompt_text_allowed") is not False:
        blockers.append("serialized_json_as_prompt_text_allowed_not_false")
    blockers.extend(iter_serialized_text_values(payload))
    return blockers


def validate_phase02(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != "persona_dream.phase02.story_contract_prompt.v1":
        blockers.append("schema_mismatch:persona_dream.phase02.story_contract_prompt.v1")
    if payload.get("phase") != "02_story":
        blockers.append("phase_mismatch:02_story")
    require_nonempty_string(payload.get("run_id"), "run_id", blockers, "missing_run_id")
    inputs = require_mapping(payload.get("input_contracts"), "input_contracts", blockers, "missing_input_contracts")
    require_nonempty_string(inputs.get("memory_residue_contract_path"), "input_contracts.memory_residue_contract_path", blockers, "missing_memory_residue_contract_path")
    require_mapping(payload.get("typed_source_context"), "typed_source_context", blockers, "missing_typed_source_context")
    story = require_mapping(payload.get("story_contract"), "story_contract", blockers, "missing_story_contract")
    require_nonempty_string(story.get("title"), "story_contract.title", blockers, "missing_story_title")
    require_nonempty_string(story.get("logline"), "story_contract.logline", blockers, "missing_story_logline")
    require_nonempty_string(story.get("story"), "story_contract.story", blockers, "missing_story")
    require_nonempty_list(story.get("beats"), "story_contract.beats", blockers, "missing_story_beats")
    matrix = require_mapping(payload.get("interaction_matrix"), "interaction_matrix", blockers, "missing_interaction_matrix")
    require_nonempty_list(matrix.get("entities"), "interaction_matrix.entities", blockers, "missing_interaction_matrix_entities")
    require_nonempty_list(matrix.get("edges"), "interaction_matrix.edges", blockers, "missing_interaction_matrix_edges")
    require_mapping(payload.get("visual_continuity_seeds"), "visual_continuity_seeds", blockers, "missing_visual_continuity_seeds")
    downstream = require_mapping(payload.get("downstream_contract"), "downstream_contract", blockers, "missing_downstream_contract")
    if downstream.get("may_feed_phase06") is not True:
        blockers.append("downstream_contract_may_feed_phase06_not_true")
    if payload.get("serialized_json_as_prompt_text_allowed") is not False:
        blockers.append("serialized_json_as_prompt_text_allowed_not_false")
    blockers.extend(iter_serialized_text_values(payload))
    return blockers


def validate_phase06(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != "persona_dream.phase06.script_prompt_contract.v1":
        blockers.append("schema_mismatch:persona_dream.phase06.script_prompt_contract.v1")
    if payload.get("phase") != "06_script":
        blockers.append("phase_mismatch:06_script")
    require_nonempty_string(payload.get("run_id"), "run_id", blockers, "missing_run_id")
    inputs = require_mapping(payload.get("input_contracts"), "input_contracts", blockers, "missing_input_contracts")
    require_nonempty_string(inputs.get("story_contract_path"), "input_contracts.story_contract_path", blockers, "missing_story_contract_path")
    script = require_mapping(payload.get("script"), "script", blockers, "missing_script")
    rows = require_nonempty_list(script.get("rows"), "script.rows", blockers, "missing_script_rows")
    for index, row_value in enumerate(rows):
        row = require_mapping(row_value, f"script.rows[{index}]", blockers, "invalid_script_row")
        require_nonempty_string(row.get("row_id"), f"script.rows[{index}].row_id", blockers, "missing_row_id")
        require_nonempty_string(row.get("action"), f"script.rows[{index}].action", blockers, "missing_row_action")
        require_nonempty_list(row.get("required_entities"), f"script.rows[{index}].required_entities", blockers, "missing_row_required_entities")
    timed_beats = require_nonempty_list(payload.get("timed_beats"), "timed_beats", blockers, "missing_timed_beats")
    for index, beat_value in enumerate(timed_beats):
        beat = require_mapping(beat_value, f"timed_beats[{index}]", blockers, "invalid_timed_beat")
        require_nonempty_string(beat.get("beat_id"), f"timed_beats[{index}].beat_id", blockers, "missing_beat_id")
        require_nonempty_string(beat.get("story_function"), f"timed_beats[{index}].story_function", blockers, "ambiguous_timed_beat")
    require_nonempty_list(payload.get("timed_transcript"), "timed_transcript", blockers, "missing_timed_transcript")
    require_nonempty_list(payload.get("entity_environment_script_table"), "entity_environment_script_table", blockers, "missing_entity_environment_script_table")
    asset_usage = require_mapping(payload.get("asset_usage"), "asset_usage", blockers, "missing_asset_usage")
    for entity, usage_value in asset_usage.items():
        usage = require_mapping(usage_value, f"asset_usage.{entity}", blockers, "loose_asset_usage")
        if usage.get("required") is not True:
            blockers.append(f"optional_required_entity:{entity}")
        if usage.get("usage") not in {"hard_identity_reference", "required_prop_reference", "required_environment_reference"}:
            blockers.append(f"loose_asset_usage:{entity}")
    coverage = require_mapping(payload.get("interaction_matrix_coverage"), "interaction_matrix_coverage", blockers, "missing_interaction_matrix_coverage")
    if "covered_edges" not in coverage or "uncovered_edges" not in coverage:
        blockers.append("missing_interaction_matrix_coverage")
    require_mapping(payload.get("realism_contract"), "realism_contract", blockers, "missing_realism_contract")
    storyboard_constraints = require_mapping(payload.get("storyboard_constraints"), "storyboard_constraints", blockers, "missing_storyboard_constraints")
    if storyboard_constraints.get("panel_count") is None:
        blockers.append("missing_storyboard_constraints_panel_count")
    downstream = require_mapping(payload.get("downstream_contract"), "downstream_contract", blockers, "missing_downstream_contract")
    if downstream.get("may_feed_phase07") is not True:
        blockers.append("downstream_contract_may_feed_phase07_not_true")
    if payload.get("serialized_json_as_prompt_text_allowed") is not False:
        blockers.append("serialized_json_as_prompt_text_allowed_not_false")
    blockers.extend(iter_serialized_text_values(payload))
    return blockers


def validate_phase07(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema") != "persona_dream.phase07.panel_prompt_contract.v2":
        blockers.append("schema_mismatch:persona_dream.phase07.panel_prompt_contract.v2")
    for field in ("run_id", "tau_run_id", "panel_id", "frame_id", "time_range", "compiled_from"):
        require_nonempty_string(payload.get(field), field, blockers, f"missing_{field}")
    require_mapping(payload.get("state_contract"), "state_contract", blockers, "missing_state_contract")
    creator_must_not_write = payload.get("state_contract", {}).get("creator_must_not_write") if isinstance(payload.get("state_contract"), dict) else None
    if not isinstance(creator_must_not_write, list) or "accepted_frame" not in creator_must_not_write:
        blockers.append("state_contract_creator_must_not_write_missing_accepted_frame")
    scope = require_mapping(payload.get("generation_scope"), "generation_scope", blockers, "missing_generation_scope")
    if scope.get("live_image_call_started") is not False:
        blockers.append("live_image_call_started_not_false")
    require_mapping(payload.get("model_policy"), "model_policy", blockers, "missing_model_policy")
    identities = require_nonempty_list(payload.get("required_identities"), "required_identities", blockers, "missing_required_identities")
    identity_requirements = require_mapping(payload.get("identity_requirements"), "identity_requirements", blockers, "missing_identity_requirements")
    reference_assets = require_mapping(payload.get("identity_reference_assets"), "identity_reference_assets", blockers, "missing_identity_reference_assets")
    for identity in identities:
        if not isinstance(identity, str) or not identity:
            blockers.append("invalid_required_identity")
            continue
        requirement = require_mapping(identity_requirements.get(identity), f"identity_requirements.{identity}", blockers, "missing_identity_requirement")
        visibility = require_mapping(requirement.get("visibility"), f"identity_requirements.{identity}.visibility", blockers, "missing_identity_visibility")
        if requirement.get("required") is not True:
            blockers.append(f"identity_not_required:{identity}")
        if visibility.get("spatially_implied_allowed") is True:
            blockers.append(f"required_identity_spatially_implied:{identity}")
        asset = require_mapping(reference_assets.get(identity), f"identity_reference_assets.{identity}", blockers, "missing_identity_reference_asset")
        require_nonempty_string(asset.get("asset_id"), f"identity_reference_assets.{identity}.asset_id", blockers, "missing_identity_asset_id")
        require_path_hash(asset.get("path"), asset.get("sha256"), f"identity_reference_assets.{identity}", blockers)
    continuity_assets = require_mapping(payload.get("temporal_continuity_reference_assets"), "temporal_continuity_reference_assets", blockers, "missing_temporal_continuity_reference_assets")
    for asset_name, asset_value in continuity_assets.items():
        asset = require_mapping(asset_value, f"temporal_continuity_reference_assets.{asset_name}", blockers, "invalid_temporal_continuity_reference_asset")
        if "path" in asset or "sha256" in asset:
            require_path_hash(asset.get("path"), asset.get("sha256"), f"temporal_continuity_reference_assets.{asset_name}", blockers)
    require_mapping(payload.get("camera_contract"), "camera_contract", blockers, "missing_camera_contract")
    require_nonempty_list(payload.get("environment_requirements"), "environment_requirements", blockers, "missing_environment_requirements")
    require_nonempty_string(payload.get("story_action"), "story_action", blockers, "missing_story_action")
    prompt_sections = require_mapping(payload.get("prompt_sections"), "prompt_sections", blockers, "missing_prompt_sections")
    for section in ("SUBJECT", "CHARACTERS", "SCENE", "MUST_INCLUDE", "MUST_NOT_INCLUDE"):
        require_nonempty_string(prompt_sections.get(section), f"prompt_sections.{section}", blockers, "missing_prompt_section")
    provider_shape = require_mapping(payload.get("provider_request_shape"), "provider_request_shape", blockers, "missing_provider_request_shape")
    require_nonempty_list(provider_shape.get("image_reference_inputs"), "provider_request_shape.image_reference_inputs", blockers, "missing_image_reference_inputs")
    blockers.extend(iter_serialized_text_values(payload))
    return blockers


def status_for(phase: str, blockers: list[str]) -> str:
    if not blockers:
        return {
            "01": "PASS_MEMORY_RESIDUE_CONTRACT",
            "02": "PASS_STORY_CONTRACT",
            "06": "PASS_SCRIPT_CONTRACT",
            "07": "PASS_PROMPT_CONTRACT",
        }[phase]
    if phase == "01" and any("serialized_json" in blocker for blocker in blockers):
        return "BLOCKED_SERIALIZED_MEMORY_TEXT"
    return {
        "01": "BLOCKED_MEMORY_RESIDUE_CONTRACT",
        "02": "BLOCKED_STORY_CONTRACT",
        "06": "BLOCKED_SCRIPT_CONTRACT",
        "07": "BLOCKED_PROMPT_CONTRACT",
    }[phase]


def build_receipt(
    *,
    phase: str,
    contract_path: Path,
    status: str,
    blockers: list[str],
    exercised: str,
    unverified: str,
) -> dict[str, Any]:
    return {
        "schema": f"persona_dream.phase{phase}.prompt_contract_validation_receipt.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": sha256_path(contract_path.resolve()),
        "status": status,
        "blockers": blockers,
        "live": False,
        "mocked": False,
        "provider_live": False,
        "live_image_call_started": False,
        "exercised": exercised,
        "unverified": unverified,
    }
