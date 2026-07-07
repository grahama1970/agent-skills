from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner
from jsonschema import Draft202012Validator


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import battle_skill.battle_event_adapter as battle_event_adapter  # noqa: E402
import battle_skill.cli as battle_cli  # noqa: E402
import battle_skill.ux_contract_validator as ux_contract_validator  # noqa: E402
from battle_skill.battle_event_adapter import adapt_proof_dir, generate_fixture_files  # noqa: E402
from battle_skill.ux_contract_validator import (  # noqa: E402
    DEFAULT_HANDOFF_SUMMARY_SCHEMA_PATH,
    DEFAULT_RENDERER_BUNDLE_SCHEMA_PATH,
    DEFAULT_RENDERER_VALUES_SCHEMA_PATH,
    DEFAULT_RENDERER_FIXTURE_RESOLUTION_SCHEMA_PATH,
    DEFAULT_UX_DATA_CONTRACT_INDEX_SCHEMA_PATH,
    EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA,
    EXPECTED_RENDERER_BUNDLE_SCHEMA,
    EXPECTED_RENDERER_VALUES_SCHEMA,
    EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA,
    EXPECTED_RENDERER_FIXTURE_RESOLUTION_COMMAND,
    EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH,
    EXPECTED_RENDERER_BUNDLE_COMMAND,
    EXPECTED_RENDERER_BUNDLE_PATH,
    EXPECTED_RENDERER_VALUES_COMMAND,
    EXPECTED_RENDERER_VALUES_PATH,
    EXPECTED_PARENT_SPAWN_PROOF_COMMAND,
    EXPECTED_UX_DATA_CONTRACT_INDEX_COMMAND,
    EXPECTED_UX_DATA_CONTRACT_INDEX_PATH,
    REQUIRED_GOAL_SOURCE_PHRASES,
    REQUIRED_RENDER_GUARDS,
    REQUIRED_SUMMARY_VALIDATION_COMMANDS,
    ContractError,
    export_renderer_bundle_from_resolution_path,
    export_renderer_values_from_bundle_path,
    export_ux_data_contract_index_from_summary_path,
    resolve_renderer_fixture_from_summary_path,
    validate_renderer_bundle,
    validate_renderer_bundle_schema,
    validate_renderer_values,
    validate_renderer_values_schema,
    validate_ux_data_contract_index,
    validate_ux_data_contract_index_schema,
    validate_renderer_fixture_resolution,
    validate_renderer_fixture_resolution_schema,
    validate_fixture,
    validate_fixture_schema,
    validate_handoff_summary,
    validate_handoff_summary_schema,
    validate_handoff_summary_path,
)


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "battle.normalized_ux_fixture.v1.schema.json"
SUMMARY_PATH = Path(__file__).resolve().parents[1] / "local" / "battle-004-ux-json-contract-summary.json"
SUMMARY_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "battle.backend_ux_json_contract_summary.v1.schema.json"
RESOLUTION_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "battle.ux_renderer_fixture_resolution.v1.schema.json"
BUNDLE_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "battle.ux_renderer_bundle.v1.schema.json"
VALUES_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "battle.ux_renderer_values.v1.schema.json"
INDEX_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "battle.ux_data_contract_index.v1.schema.json"


def test_normalized_ux_json_schema_tracks_backend_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["properties"]["schema"]["const"] == "battle.normalized_ux_fixture.v1"
    assert "activitySegments" in schema["$defs"]["lane"]["required"]
    assert "cockpit" in schema["$defs"]["lane"]["required"]
    assert "spectator_shell" in schema["required"]
    assert "lineage_request" in schema["required"]
    assert "renderer_binding_contract" in schema["required"]
    assert schema["$defs"]["spectator_shell"]["properties"]["schema"]["const"] == "battle.spectator_shell.v1"
    assert schema["$defs"]["lineage_request"]["properties"]["schema"]["const"] == "battle.lineage_request.v1"
    assert schema["$defs"]["lineage_request"]["properties"]["status"]["enum"] == ["NOT_REQUESTED", "NOT_PROVEN", "PASS"]
    assert schema["$defs"]["renderer_binding_contract"]["properties"]["schema"]["const"] == "battle.renderer_binding_contract.v1"
    renderer_bindings = schema["$defs"]["renderer_binding_contract"]["properties"]
    assert "lane_start_elapsed_x" in renderer_bindings["elapsed_timeline_axis"]["required"]
    assert (
        renderer_bindings["elapsed_timeline_axis"]["properties"]["lane_start_elapsed_x"]["const"]
        == "timeline_lane_start_model.starts[].elapsed_line_must_start_at_x"
    )
    assert "activity_segment_elapsed_start_x" in renderer_bindings["elapsed_timeline_axis"]["required"]
    assert (
        renderer_bindings["elapsed_timeline_axis"]["properties"]["activity_segment_elapsed_start_x"]["const"]
        == "lane_activity_timeline_model.lanes[].segments[].elapsed_start_x"
    )
    assert "timeline_lane_start_model" in renderer_bindings["lane_activity_and_label_layout"]["required"]
    assert "activity_timeline_model" in renderer_bindings["lane_activity_and_label_layout"]["required"]
    assert schema["$defs"]["lane_cockpit"]["properties"]["schema"]["const"] == "battle.lane_cockpit.v1"
    assert schema["$defs"]["event"]["properties"]["evidence"]["$ref"] == "#/$defs/evidence"
    assert "proof_blockers" in schema["required"]
    assert schema["properties"]["proof_blockers"]["items"]["$ref"] == "#/$defs/proof_blocker"
    assert schema["$defs"]["proof_blocker"]["properties"]["schema"]["const"] == "battle.proof_blocker.v1"
    assert schema["$defs"]["proof_blocker"]["properties"]["blocker"]["$ref"] == "#/$defs/worker_blocker"
    assert schema["$defs"]["evidence"]["properties"]["blocker"]["$ref"] == "#/$defs/worker_blocker"
    assert schema["$defs"]["worker_blocker"]["properties"]["schema"]["const"] == "battle.worker_blocker.v1"
    assert "message" in schema["$defs"]["worker_blocker"]["required"]
    assert "receipt_path" in schema["$defs"]["worker_blocker"]["required"]
    assert "keyframes" in schema["$defs"]["playhead"]["required"]
    assert schema["$defs"]["replay_cta"]["properties"]["label"]["const"] == "REPLAY IN DOCKER"
    assert schema["$defs"]["replay_cta"]["properties"]["state"]["enum"] == ["receipt_only", "executable"]
    assert schema["$defs"]["timeline"]["properties"]["scroll_axis"]["const"] == "horizontal"
    assert schema["$defs"]["scenario"]["properties"]["public_entrypoint"]["pattern"] == "^/"


def test_ux_renderer_value_schemas_require_elapsed_binding_contract_paths() -> None:
    for schema_path in [SUMMARY_SCHEMA_PATH, VALUES_SCHEMA_PATH]:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        renderer_bindings = schema["properties"]["renderer_binding_contract"]["properties"] if schema_path == VALUES_SCHEMA_PATH else schema["$defs"]["renderer_binding_contract"]["properties"]

        elapsed_axis = renderer_bindings["elapsed_timeline_axis"]
        assert "lane_start_model" in elapsed_axis["required"]
        assert elapsed_axis["properties"]["lane_start_model"]["const"] == "timeline_lane_start_model"
        assert "lane_start_elapsed_x" in elapsed_axis["required"]
        assert (
            elapsed_axis["properties"]["lane_start_elapsed_x"]["const"]
            == "timeline_lane_start_model.starts[].elapsed_line_must_start_at_x"
        )
        assert "lane_end_elapsed_x" in elapsed_axis["required"]
        assert elapsed_axis["properties"]["lane_end_elapsed_x"]["const"] == "timeline_lane_start_model.starts[].elapsed_line_end_x"
        assert "activity_model" in elapsed_axis["required"]
        assert elapsed_axis["properties"]["activity_model"]["const"] == "lane_activity_timeline_model"
        assert "activity_segment_elapsed_start_x" in elapsed_axis["required"]
        assert (
            elapsed_axis["properties"]["activity_segment_elapsed_start_x"]["const"]
            == "lane_activity_timeline_model.lanes[].segments[].elapsed_start_x"
        )
        assert "activity_segment_elapsed_end_x" in elapsed_axis["required"]
        assert (
            elapsed_axis["properties"]["activity_segment_elapsed_end_x"]["const"]
            == "lane_activity_timeline_model.lanes[].segments[].elapsed_end_x"
        )

        lane_layout = renderer_bindings["lane_activity_and_label_layout"]
        assert "timeline_lane_start_model" in lane_layout["required"]
        assert lane_layout["properties"]["timeline_lane_start_model"]["const"] == "timeline_lane_start_model"
        assert "activity_timeline_model" in lane_layout["required"]
        assert lane_layout["properties"]["activity_timeline_model"]["const"] == "lane_activity_timeline_model"


def test_renderer_fixture_resolution_schema_tracks_backend_contract() -> None:
    schema = json.loads(RESOLUTION_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert DEFAULT_RENDERER_FIXTURE_RESOLUTION_SCHEMA_PATH == RESOLUTION_SCHEMA_PATH
    assert schema["properties"]["schema"]["const"] == EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA
    assert schema["properties"]["battle_id"]["const"] == "battle-004"
    assert schema["properties"]["fixture_key"]["const"] == "authoritative_parent_spawn_fixture"
    assert schema["properties"]["fixture_status"]["const"] == "PASS"
    assert schema["properties"]["fixture_lineage_mode"]["const"] == "receipt_backed"
    assert schema["properties"]["fixture_child_spawn_count"]["minimum"] == 1
    assert schema["properties"]["mocked"]["const"] is False


def test_renderer_bundle_schema_tracks_backend_contract() -> None:
    schema = json.loads(BUNDLE_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert DEFAULT_RENDERER_BUNDLE_SCHEMA_PATH == BUNDLE_SCHEMA_PATH
    assert schema["properties"]["schema"]["const"] == EXPECTED_RENDERER_BUNDLE_SCHEMA
    assert schema["properties"]["resolution"]["properties"]["schema"]["const"] == EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA
    assert schema["properties"]["resolution"]["properties"]["fixture_key"]["const"] == "authoritative_parent_spawn_fixture"
    assert schema["properties"]["resolution"]["properties"]["fixture_child_spawn_count"]["minimum"] == 1
    assert schema["properties"]["resolution"]["properties"]["mocked"]["const"] is False
    assert schema["properties"]["fixture"]["properties"]["schema"]["const"] == "battle.normalized_ux_fixture.v1"
    assert schema["properties"]["fixture"]["properties"]["battle_id"]["const"] == "battle-004"
    assert schema["properties"]["fixture"]["properties"]["scenario"]["properties"]["public_entrypoint"]["const"] == "/api/import-zip"
    assert schema["properties"]["fixture"]["properties"]["scenario"]["properties"]["cwe"]["const"] == "CWE-22"
    assert schema["properties"]["fixture"]["properties"]["lineage"]["properties"]["mode"]["const"] == "receipt_backed"
    assert schema["properties"]["fixture"]["properties"]["lineage"]["properties"]["spawn_count"]["minimum"] == 1
    assert schema["properties"]["fixture"]["properties"]["scoreboard"]["properties"]["child_spawn_count"]["minimum"] == 1
    assert schema["properties"]["fixture"]["properties"]["timeline"]["properties"]["scroll_axis"]["const"] == "horizontal"
    assert schema["properties"]["fixture"]["properties"]["timeline"]["properties"]["playhead"]["properties"]["can_animate"]["const"] is True
    assert (
        schema["properties"]["fixture"]["properties"]["timeline"]["properties"]["playhead"]["properties"]["animation_semantics"]["const"]
        == "receipt_replay_only"
    )
    assert schema["properties"]["fixture"]["properties"]["lanes"]["minItems"] == 2


def test_renderer_values_schema_tracks_backend_contract() -> None:
    schema = json.loads(VALUES_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert DEFAULT_RENDERER_VALUES_SCHEMA_PATH == VALUES_SCHEMA_PATH
    assert schema["properties"]["schema"]["const"] == EXPECTED_RENDERER_VALUES_SCHEMA
    assert schema["properties"]["battle_id"]["const"] == "battle-004"
    assert schema["properties"]["proof_generation_contract"]["properties"]["canonical_command"]["const"] == EXPECTED_PARENT_SPAWN_PROOF_COMMAND
    assert schema["properties"]["proof_generation_contract"]["properties"]["spawn_red_child_on_blue_success"]["const"] is True
    assert schema["properties"]["scenario"]["properties"]["public_entrypoint"]["const"] == "/api/import-zip"
    assert schema["properties"]["scenario"]["properties"]["cwe"]["const"] == "CWE-22"
    assert schema["properties"]["proof_mode"]["const"] == "receipt_backed_fixture"
    assert schema["properties"]["mocked"]["const"] is False
    assert "spectator_shell" in schema["required"]
    assert schema["properties"]["spectator_shell"]["properties"]["schema"]["const"] == "battle.spectator_shell.v1"
    assert schema["properties"]["spectator_shell"]["properties"]["battle_title"]["const"] == "BATTLE-004 · POST /api/import-zip"
    assert schema["properties"]["shell"]["properties"]["schema"]["const"] == "battle.spectator_shell.v1"
    assert schema["properties"]["lineage"]["properties"]["mode"]["const"] == "receipt_backed"
    assert schema["properties"]["lineage"]["properties"]["spawn_count"]["minimum"] == 1
    assert "lane_phase_coverage" in schema["required"]
    assert schema["properties"]["lane_phase_coverage"]["minItems"] == 2
    assert schema["properties"]["lane_phase_coverage"]["items"]["properties"]["phases"]["contains"]["const"] == "research"
    assert schema["properties"]["lanes"]["minItems"] == 2
    assert "proof_blockers" in schema["required"]
    assert schema["properties"]["proof_blockers"]["items"]["properties"]["schema"]["const"] == "battle.proof_blocker.v1"
    assert schema["properties"]["proof_blockers"]["items"]["properties"]["blocker"]["properties"]["schema"]["const"] == "battle.worker_blocker.v1"
    assert schema["properties"]["scoreboard"]["properties"]["child_spawn_count"]["minimum"] == 1
    assert schema["properties"]["timeline"]["properties"]["scroll_axis"]["const"] == "horizontal"
    assert schema["properties"]["timeline"]["properties"]["playhead"]["properties"]["can_animate"]["const"] is True
    assert (
        schema["properties"]["timeline"]["properties"]["playhead"]["properties"]["animation_semantics"]["const"]
        == "receipt_replay_only"
    )
    assert "timeline_time_model" in schema["required"]
    assert schema["properties"]["timeline_time_model"]["properties"]["mode"]["const"] == "receipt_order_with_round_clock"
    assert schema["properties"]["timeline_time_model"]["properties"]["x_axis_mode"]["const"] == "receipt_order_percent"
    assert schema["properties"]["timeline_time_model"]["properties"]["x_position_is_elapsed_time"]["const"] is False
    assert "timeline_viewport_model" in schema["required"]
    assert schema["properties"]["timeline_viewport_model"]["properties"]["schema"]["const"] == "battle.timeline_viewport_model.v1"
    assert schema["properties"]["timeline_viewport_model"]["properties"]["mode"]["const"] == "receipt_replay_scroll_viewport"
    assert schema["properties"]["timeline_viewport_model"]["properties"]["scroll_axis"]["const"] == "horizontal"
    assert (
        schema["properties"]["timeline_viewport_model"]["properties"]["render_rules"]["contains"]["const"]
        == "Render the timeline as a horizontally scrollable receipt-order viewport."
    )
    assert "timeline_lane_start_model" in schema["required"]
    assert schema["properties"]["timeline_lane_start_model"]["properties"]["schema"]["const"] == "battle.timeline_lane_start_model.v1"
    assert schema["properties"]["timeline_lane_start_model"]["properties"]["mode"]["const"] == "receipt_order_lane_starts"
    assert (
        schema["properties"]["timeline_lane_start_model"]["properties"]["render_rules"]["contains"]["const"]
        == "Render child lanes from child_spawn_start/source_receipt_id, not from global time zero."
    )
    assert "lane_activity_timeline_model" in schema["required"]
    assert schema["properties"]["lane_activity_timeline_model"]["properties"]["schema"]["const"] == "battle.lane_activity_timeline_model.v1"
    assert schema["properties"]["lane_activity_timeline_model"]["properties"]["mode"]["const"] == "receipt_backed_activity_segments"
    assert (
        schema["properties"]["lane_activity_timeline_model"]["properties"]["render_rules"]["contains"]["const"]
        == "Do not invent research, payload, mutate, trigger, patch, crash, or terminal phases client-side."
    )
    assert "timeline_label_layout_model" in schema["required"]
    assert schema["properties"]["timeline_label_layout_model"]["properties"]["schema"]["const"] == "battle.timeline_label_layout_model.v1"
    assert schema["properties"]["timeline_label_layout_model"]["properties"]["mode"]["const"] == "receipt_event_label_slots"
    assert (
        schema["properties"]["timeline_label_layout_model"]["properties"]["render_rules"]["contains"]["const"]
        == "Use label_band and collision_group from this model; do not infer label stacking from pixel position alone."
    )
    assert "lineage_render_model" in schema["required"]
    assert schema["properties"]["lineage_render_model"]["properties"]["schema"]["const"] == "battle.lineage_render_model.v1"
    assert schema["properties"]["lineage_render_model"]["properties"]["mode"]["const"] == "receipt_backed_parent_child"
    assert schema["properties"]["lineage_render_model"]["properties"]["groups"]["minItems"] == 1
    assert schema["properties"]["lineage_render_model"]["properties"]["connectors"]["minItems"] == 1
    assert (
        schema["properties"]["lineage_render_model"]["properties"]["render_rules"]["contains"]["const"]
        == "Render connector origin from parent_event_id/source_receipt_id, not from the graph left edge."
    )
    assert "spawn_gate_model" in schema["required"]
    assert schema["properties"]["spawn_gate_model"]["properties"]["schema"]["const"] == "battle.spawn_gate_model.v1"
    assert schema["properties"]["spawn_gate_model"]["properties"]["mode"]["const"] == "receipt_backed_spawn_gates"
    assert (
        schema["properties"]["spawn_gate_model"]["properties"]["render_rules"]["contains"]["const"]
        == "Render parent-child lanes only from spawn_gate_model.gates where renderable is true."
    )
    assert "selected_lane_model" in schema["required"]
    assert schema["properties"]["selected_lane_model"]["properties"]["schema"]["const"] == "battle.selected_lane_model.v1"
    assert schema["properties"]["selected_lane_model"]["properties"]["selection_strategy"]["const"] == "first_receipt_backed_child_lane"
    assert (
        schema["properties"]["selected_lane_model"]["properties"]["render_rules"]["contains"]["const"]
        == "Use lane_index and JSON pointers from this object; do not assume lane 0 is selected."
    )
    assert "outcome_truth_constraints_model" in schema["required"]
    assert (
        schema["properties"]["outcome_truth_constraints_model"]["properties"]["schema"]["const"]
        == "battle.outcome_truth_constraints_model.v1"
    )
    assert (
        schema["properties"]["outcome_truth_constraints_model"]["properties"]["mode"]["const"]
        == "receipt_backed_outcome_gates"
    )
    assert (
        schema["properties"]["outcome_truth_constraints_model"]["properties"]["render_rules"]["contains"]["const"]
        == "Read outcome permissions from this model before rendering dramatic states."
    )
    backed_schema = schema["properties"]["receipt_backed_values"]
    assert backed_schema["properties"]["timeline_x_axis_mode"]["const"] == "receipt_order_percent"
    assert backed_schema["properties"]["timeline_x_position_is_elapsed_time"]["const"] is False
    assert backed_schema["properties"]["timeline_playhead_keyframe_count"]["minimum"] == 2
    assert backed_schema["properties"]["lane_phase_coverage_count"]["minimum"] == 2
    assert backed_schema["properties"]["lane_start_model_count"]["minimum"] == 2
    assert backed_schema["properties"]["lane_activity_segment_count"]["minimum"] == 2
    assert backed_schema["properties"]["timeline_label_count"]["minimum"] == 1
    assert backed_schema["properties"]["timeline_label_collision_group_count"]["minimum"] == 1
    assert backed_schema["properties"]["lanes_with_research_count"]["minimum"] == 2
    assert backed_schema["properties"]["lanes_with_spawn_handoff_count"]["minimum"] == 2
    assert backed_schema["properties"]["parent_lane_ids"]["minItems"] == 1
    assert backed_schema["properties"]["child_lane_ids"]["minItems"] == 1
    assert backed_schema["properties"]["spawn_receipt_ids"]["minItems"] == 1


def test_ux_data_contract_index_schema_tracks_backend_contract() -> None:
    schema = json.loads(INDEX_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert DEFAULT_UX_DATA_CONTRACT_INDEX_SCHEMA_PATH == INDEX_SCHEMA_PATH
    assert schema["properties"]["schema"]["const"] == EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA
    assert schema["properties"]["battle_id"]["const"] == "battle-004"
    assert schema["properties"]["current_agent_scope"]["const"] == "backend_json_contract_only"
    assert schema["properties"]["mocked"]["const"] is False
    assert schema["properties"]["canonical_scenario"]["properties"]["public_entrypoint"]["const"] == "/api/import-zip"
    assert schema["properties"]["canonical_scenario"]["properties"]["cwe"]["const"] == "CWE-22"
    assert schema["properties"]["proof_generation_contract"]["properties"]["canonical_command"]["const"] == EXPECTED_PARENT_SPAWN_PROOF_COMMAND
    assert schema["properties"]["proof_generation_contract"]["properties"]["red_workers"]["const"] == 2
    assert schema["properties"]["proof_generation_contract"]["properties"]["blue_workers"]["const"] == 2
    assert schema["properties"]["receipt_backed_values"]["properties"]["child_spawn_count"]["minimum"] == 1
    assert schema["properties"]["receipt_backed_values"]["properties"]["timeline_x_axis_mode"]["const"] == "receipt_order_percent"
    assert schema["properties"]["receipt_backed_values"]["properties"]["timeline_x_position_is_elapsed_time"]["const"] is False
    assert schema["properties"]["receipt_backed_values"]["properties"]["timed_lane_event_count"]["minimum"] == 1
    assert schema["properties"]["receipt_backed_values"]["properties"]["playhead_elapsed_monotonic_by_x"]["const"] is False
    assert schema["properties"]["timing_contract"]["properties"]["schema"]["const"] == "battle.ux_timing_contract.v1"
    assert schema["properties"]["timing_contract"]["properties"]["source"]["const"] == "/timeline_time_model"
    assert schema["properties"]["timing_contract"]["properties"]["x_position_is_elapsed_time"]["const"] is False
    assert schema["properties"]["timing_contract"]["properties"]["receipt_elapsed_keyframes_are_monotonic_by_x"]["const"] is False
    assert schema["properties"]["receipt_backed_values"]["properties"]["timeline_playhead_keyframe_count"]["minimum"] == 2
    assert schema["properties"]["receipt_backed_values"]["properties"]["lane_phase_coverage_count"]["minimum"] == 2
    assert schema["properties"]["receipt_backed_values"]["properties"]["lane_start_model_count"]["minimum"] == 2
    assert schema["properties"]["receipt_backed_values"]["properties"]["lane_activity_segment_count"]["minimum"] == 2
    assert schema["properties"]["receipt_backed_values"]["properties"]["timeline_label_count"]["minimum"] == 1
    assert schema["properties"]["receipt_backed_values"]["properties"]["timeline_label_collision_group_count"]["minimum"] == 1
    assert "renderer_value_paths" in schema["required"]
    assert schema["properties"]["renderer_value_paths"]["properties"]["proof_generation_contract"]["const"] == "/proof_generation_contract"
    assert schema["properties"]["renderer_value_paths"]["properties"]["timeline_viewport_model"]["const"] == "/timeline_viewport_model"
    assert schema["properties"]["renderer_value_paths"]["properties"]["timeline_lane_start_model"]["const"] == "/timeline_lane_start_model"
    assert schema["properties"]["renderer_value_paths"]["properties"]["lane_activity_timeline_model"]["const"] == "/lane_activity_timeline_model"
    assert schema["properties"]["renderer_value_paths"]["properties"]["timeline_label_layout_model"]["const"] == "/timeline_label_layout_model"
    assert schema["properties"]["renderer_value_paths"]["properties"]["lineage_render_model"]["const"] == "/lineage_render_model"
    assert schema["properties"]["renderer_value_paths"]["properties"]["spawn_gate_model"]["const"] == "/spawn_gate_model"
    assert schema["properties"]["renderer_value_paths"]["properties"]["selected_lane_model"]["const"] == "/selected_lane_model"
    assert schema["properties"]["renderer_value_paths"]["properties"]["outcome_truth_constraints_model"]["const"] == "/outcome_truth_constraints_model"
    assert schema["properties"]["renderer_value_paths"]["properties"]["replay_cta_values"]["const"] == "/selected_lane_model/replay_cta"
    assert schema["properties"]["renderer_value_paths"]["properties"]["selected_lane_cockpit"]["const"] == "/selected_lane_model/cockpit"
    assert "authoritative_renderer_values" in schema["required"]
    assert "artifact_digests" in schema["required"]
    assert schema["properties"]["artifact_digests"]["required"] == [
        "authoritative_renderer_values",
        "authoritative_normalized_fixture",
        "renderer_fixture_resolution",
        "renderer_bundle",
        "goal_source",
    ]
    assert schema["$defs"]["artifact_digest"]["properties"]["sha256"]["pattern"] == "^[0-9a-f]{64}$"


def test_backend_ux_handoff_summary_exposes_lineage_request_contract() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    assert summary["schema"] == "battle.backend_ux_json_contract_summary.v1"
    assert summary["battle_id"] == "battle-004"
    assert summary["canonical_scenario"] == {
        "public_entrypoint": "/api/import-zip",
        "cwe": "CWE-22",
        "hidden_vulnerability_family": "Zip Slip path traversal",
        "runtime_image": "python:3.12-slim",
        "target_language": "python",
    }
    assert summary["proof_generation_contract"]["canonical_command"] == EXPECTED_PARENT_SPAWN_PROOF_COMMAND
    assert summary["proof_generation_contract"]["red_workers"] == 2
    assert summary["proof_generation_contract"]["blue_workers"] == 2
    assert summary["proof_generation_contract"]["spawn_red_child_on_blue_success"] is True
    assert summary["goal_source_contract"]["source"] == "/home/graham/workspace/experiments/agent-skills/skills/battle/GOAL.md"
    assert summary["goal_source_contract"]["canonical_battle_id"] == "battle-004"
    assert summary["goal_source_contract"]["canonical_public_entrypoint"] == "/api/import-zip"
    assert summary["goal_source_contract"]["canonical_cwe"] == "CWE-22"
    assert summary["goal_source_contract"]["canonical_vulnerability_family"] == "Zip Slip path traversal"
    assert summary["goal_source_contract"]["current_agent_scope"] == "backend_json_contract_only"
    assert "timeline playhead/viewport values" in summary["goal_source_contract"]["must_provide"]
    assert "React layout" in summary["goal_source_contract"]["must_not_provide"]
    assert "invented child lanes, kills, fastest crash, promotion, live replay, or Blue block counts" in summary["goal_source_contract"]["must_not_provide"]
    assert summary["current_agent_boundary"]["owner"] == "battle_backend_json_contract"
    assert "React component layout" in summary["current_agent_boundary"]["does_not_own"]

    assert summary["renderer_fixture_resolution"] == {
        "schema": EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA,
        "json": EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH,
        "validation_command": EXPECTED_RENDERER_FIXTURE_RESOLUTION_COMMAND,
        "purpose": "Concrete schema-validated JSON pointer telling the UX renderer to load the canonical parent-spawn fixture.",
    }
    assert summary["renderer_bundle"] == {
        "schema": EXPECTED_RENDERER_BUNDLE_SCHEMA,
        "json": EXPECTED_RENDERER_BUNDLE_PATH,
        "validation_command": EXPECTED_RENDERER_BUNDLE_COMMAND,
        "purpose": "Self-contained backend JSON bundle containing the resolver metadata and selected normalized fixture values for the UX renderer.",
    }
    assert summary["renderer_values"] == {
        "schema": EXPECTED_RENDERER_VALUES_SCHEMA,
        "json": EXPECTED_RENDERER_VALUES_PATH,
        "validation_command": EXPECTED_RENDERER_VALUES_COMMAND,
        "purpose": "Compact backend-owned values extracted from the selected renderer bundle for direct UX consumption without client-side fixture selection.",
    }
    assert summary["data_contract_index"] == {
        "schema": EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA,
        "json": EXPECTED_UX_DATA_CONTRACT_INDEX_PATH,
        "validation_command": EXPECTED_UX_DATA_CONTRACT_INDEX_COMMAND,
        "purpose": "Single backend-owned source index naming the authoritative renderer values, normalized fixture, supporting artifacts, validation commands, and non-UI agent boundary.",
    }

    parent_spawn = summary["renderer_binding_contract"]["parent_spawn_and_collapse"]
    assert parent_spawn["request"] == "lineage_request"
    assert parent_spawn["request_status"] == "lineage_request.status"
    assert parent_spawn["request_condition"] == "lineage_request.condition"
    assert parent_spawn["spawn_records"] == "lineage.spawns[]"
    assert parent_spawn["parent_lane_children"] == "lanes[].children[]"
    elapsed_axis = summary["renderer_binding_contract"]["elapsed_timeline_axis"]
    assert elapsed_axis["lane_start_model"] == "timeline_lane_start_model"
    assert elapsed_axis["lane_start_elapsed_x"] == "timeline_lane_start_model.starts[].elapsed_line_must_start_at_x"
    assert elapsed_axis["lane_end_elapsed_x"] == "timeline_lane_start_model.starts[].elapsed_line_end_x"
    assert elapsed_axis["activity_model"] == "lane_activity_timeline_model"
    assert elapsed_axis["activity_segment_elapsed_start_x"] == "lane_activity_timeline_model.lanes[].segments[].elapsed_start_x"
    assert elapsed_axis["activity_segment_elapsed_end_x"] == "lane_activity_timeline_model.lanes[].segments[].elapsed_end_x"
    lane_layout = summary["renderer_binding_contract"]["lane_activity_and_label_layout"]
    assert lane_layout["timeline_lane_start_model"] == "timeline_lane_start_model"
    assert lane_layout["activity_timeline_model"] == "lane_activity_timeline_model"

    parent_fixture = summary["authoritative_parent_spawn_fixture"]
    assert (
        parent_fixture["normalized_json"]
        == "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-parent-spawn.normalized.json"
    )
    assert parent_fixture["mocked"] is False
    assert parent_fixture["lineage_request"]["requested"] is True
    assert parent_fixture["lineage_request"]["status"] == "PASS"
    assert parent_fixture["lineage"]["spawn_count"] == 1

    sparse_fixture = summary["authoritative_sparse_fixture"]
    assert (
        sparse_fixture["normalized_json"]
        == "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-sparse.normalized.json"
    )
    assert sparse_fixture["mocked"] is False
    assert sparse_fixture["lineage_request"]["requested"] is False
    assert sparse_fixture["lineage_request"]["status"] == "NOT_REQUESTED"
    assert sparse_fixture["lineage"]["spawn_count"] == 0

    assert (
        "Use lineage_request to explain requested-but-unproven child spawn; do not render children from lineage_request alone."
        in summary["required_render_guards"]
    )
    assert set(summary["required_render_guards"]) >= REQUIRED_RENDER_GUARDS
    assert set(summary["required_backend_validation_commands"]) >= REQUIRED_SUMMARY_VALIDATION_COMMANDS
    assert "lineage_request requested/not-requested/proven state" in summary["normalized_ux_json_schema"]["covers"]


def test_backend_ux_handoff_summary_matches_local_normalized_artifacts() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    for fixture_key in ["authoritative_parent_spawn_fixture", "authoritative_sparse_fixture"]:
        fixture_summary = summary[fixture_key]
        fixture_path = Path(fixture_summary["normalized_json"])
        assert fixture_path.exists(), f"{fixture_key} normalized_json is missing: {fixture_path}"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

        validate_fixture(fixture)
        _validate_json_schema(fixture)

        assert fixture["battle_id"] == summary["battle_id"]
        assert fixture["scenario"]["public_entrypoint"] == summary["canonical_scenario"]["public_entrypoint"]
        assert fixture["scenario"]["cwe"] == summary["canonical_scenario"]["cwe"]
        assert fixture["scenario"]["hidden_vulnerability_family"] == summary["canonical_scenario"]["hidden_vulnerability_family"]
        assert fixture["spectator_shell"]["battle_title"] == "BATTLE-004 · POST /api/import-zip"
        assert fixture["mocked"] == fixture_summary["mocked"]
        assert fixture["live_source"] == fixture_summary["live_source"]
        assert fixture["status"] == fixture_summary["status"]
        assert fixture["lineage_request"]["requested"] == fixture_summary["lineage_request"]["requested"]
        assert fixture["lineage_request"]["mode"] == fixture_summary["lineage_request"]["mode"]
        assert fixture["lineage_request"]["status"] == fixture_summary["lineage_request"]["status"]
        assert fixture["lineage_request"]["receipt"] == fixture_summary["lineage_request"]["receipt"]
        assert fixture["lineage"]["mode"] == fixture_summary["lineage"]["mode"]
        assert fixture["lineage"]["spawn_count"] == fixture_summary["lineage"]["spawn_count"]
        assert fixture["lineage"]["parent_lane_ids"] == fixture_summary["lineage"]["parent_lane_ids"]
        assert fixture["lineage"]["child_lane_ids"] == fixture_summary["lineage"]["child_lane_ids"]
        assert fixture["scoreboard"]["child_spawn_count"] == fixture_summary["scoreboard"]["child_spawn_count"]
        assert fixture["timeline"]["playhead"]["current_x"] == fixture_summary["timeline"]["playhead"]["current_x"]
        assert len(fixture["timeline"]["playhead"]["keyframes"]) == fixture_summary["timeline"]["playhead"]["keyframe_count"]
        assert [frame["x"] for frame in fixture["timeline"]["playhead"]["keyframes"]] == fixture_summary["timeline"]["playhead"]["keyframe_x_values"]
        assert fixture["timeline"]["viewport"]["initial_min_x"] == fixture_summary["timeline"]["viewport"]["initial_min_x"]
        assert fixture["timeline"]["viewport"]["initial_max_x"] == fixture_summary["timeline"]["viewport"]["initial_max_x"]
        assert (
            fixture["ux_contract"]["receipt_backed_values"]["child_spawn_request_status"]
            == fixture_summary["lineage_request"]["status"]
        )


def test_backend_ux_handoff_summary_validator_reports_fixture_states() -> None:
    report = validate_handoff_summary_path(SUMMARY_PATH)

    assert report["status"] == "PASS"
    assert report["battle_id"] == "battle-004"
    assert report["canonical_scenario"]["public_entrypoint"] == "/api/import-zip"
    assert report["canonical_scenario"]["cwe"] == "CWE-22"
    assert report["proof_generation_contract"]["canonical_command"] == EXPECTED_PARENT_SPAWN_PROOF_COMMAND
    assert report["proof_generation_contract"]["spawn_red_child_on_blue_success"] is True
    assert report["handoff_summary_json_schema"] == str(DEFAULT_HANDOFF_SUMMARY_SCHEMA_PATH)
    assert report["goal_source_contract"]["source"] == "/home/graham/workspace/experiments/agent-skills/skills/battle/GOAL.md"
    assert report["goal_source_checked"] == "/home/graham/workspace/experiments/agent-skills/skills/battle/GOAL.md"
    assert report["goal_source_required_phrases"] == sorted(REQUIRED_GOAL_SOURCE_PHRASES)
    assert "/api/import-zip" in report["goal_source_required_phrases"]
    assert "CWE-22" in report["goal_source_required_phrases"]
    assert report["goal_source_contract"]["current_agent_scope"] == "backend_json_contract_only"
    assert report["goal_source_contract"]["canonical_public_entrypoint"] == "/api/import-zip"
    assert report["summary"] == str(SUMMARY_PATH)
    assert report["agent_boundary"]["owner"] == "battle_backend_json_contract"
    assert "React component layout" in report["agent_boundary"]["does_not_own"]
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    assert set(report["minimum_required_backend_validation_commands"]) == REQUIRED_SUMMARY_VALIDATION_COMMANDS
    assert report["reported_backend_validation_commands"] == summary["required_backend_validation_commands"]
    assert set(report["reported_backend_validation_commands"]) >= REQUIRED_SUMMARY_VALIDATION_COMMANDS
    assert "cd skills/battle && uv run pytest tests/test_battle_event_adapter_contract.py -q" in report["reported_backend_validation_commands"]
    assert report["required_render_guard_count"] == len(REQUIRED_RENDER_GUARDS)
    assert report["reported_render_guard_count"] >= report["required_render_guard_count"]
    assert report["renderer_binding_sections"] == [
        "agent_detail_cockpit",
        "battle_shell",
        "docker_replay_cta",
        "elapsed_timeline_axis",
        "lane_activity_and_label_layout",
        "moving_playhead",
        "parent_spawn_and_collapse",
        "round_time",
        "scrollable_timeline",
    ]
    assert report["recommended_renderer_fixture"] == {
        "fixture_key": "authoritative_parent_spawn_fixture",
        "normalized_json": "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-parent-spawn.normalized.json",
        "selection_reason": "Use this fixture for the UX renderer because it is the local canonical BATTLE-004 PASS fixture with receipt-backed lineage, parent spawn, child lane values, playhead keyframes, and Docker replay CTA state.",
        "required_status": "PASS",
        "required_lineage_mode": "receipt_backed",
        "required_child_spawn_count_min": 1,
        "proof_mode": "receipt_backed_fixture",
        "fixture_status": "PASS",
        "fixture_lineage_mode": "receipt_backed",
        "fixture_child_spawn_count": 1,
        "fixture_playhead_current_x": 98,
        "fixture_playhead_keyframe_x_values": [14, 33, 50, 58, 62, 66, 67, 76, 82, 86, 96, 98],
    }
    assert report["data_contract_index"]["timing_contract"]["schema"] == "battle.ux_timing_contract.v1"
    assert report["data_contract_index"]["timing_contract"]["x_axis_mode"] == "receipt_order_percent"
    assert report["data_contract_index"]["timing_contract"]["x_position_is_elapsed_time"] is False
    assert report["data_contract_index"]["timing_contract"]["receipt_elapsed_keyframe_count"] == 12
    assert report["data_contract_index"]["timing_contract"]["receipt_elapsed_keyframes_are_monotonic_by_x"] is False
    assert report["data_contract_index"]["timing_contract"]["timed_lane_event_count"] == 12
    assert (
        "Animate the playhead as receipt replay only; do not present it as a live timer."
        in report["data_contract_index"]["timing_contract"]["render_rules"]
    )
    assert (
        report["fixtures"]["authoritative_parent_spawn_fixture"]["normalized_json"]
        == "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-parent-spawn.normalized.json"
    )
    assert report["fixtures"]["authoritative_parent_spawn_fixture"]["mocked"] is False
    assert report["fixtures"]["authoritative_parent_spawn_fixture"]["lineage_request_status"] == "PASS"
    assert report["fixtures"]["authoritative_parent_spawn_fixture"]["child_spawn_count"] == 1
    assert report["fixtures"]["authoritative_parent_spawn_fixture"]["timeline_mode"] == "receipt_order"
    assert report["fixtures"]["authoritative_parent_spawn_fixture"]["timeline_supports_pan"] is True
    assert report["fixtures"]["authoritative_parent_spawn_fixture"]["timeline_supports_zoom"] is True
    assert report["fixtures"]["authoritative_parent_spawn_fixture"]["playhead_current_x"] == 98
    assert report["fixtures"]["authoritative_parent_spawn_fixture"]["playhead_keyframe_x_values"] == [14, 33, 50, 58, 62, 66, 67, 76, 82, 86, 96, 98]
    assert report["fixtures"]["authoritative_parent_spawn_fixture"]["viewport"] == {
        "initial_min_x": 45,
        "initial_max_x": 100,
        "min_zoom": 0.75,
        "max_zoom": 4.0,
        "proof_mode": "receipt_backed_fixture",
    }
    assert report["fixtures"]["authoritative_sparse_fixture"]["mocked"] is False
    assert report["fixtures"]["authoritative_sparse_fixture"]["lineage_request_status"] == "NOT_REQUESTED"
    assert report["fixtures"]["authoritative_sparse_fixture"]["child_spawn_count"] == 0
    assert report["fixtures"]["authoritative_sparse_fixture"]["timeline_mode"] == "receipt_order"
    assert report["fixtures"]["authoritative_sparse_fixture"]["timeline_supports_pan"] is True
    assert report["fixtures"]["authoritative_sparse_fixture"]["timeline_supports_zoom"] is True
    assert report["fixtures"]["authoritative_sparse_fixture"]["playhead_current_x"] == 82
    assert report["fixtures"]["authoritative_sparse_fixture"]["playhead_keyframe_x_values"] == [14, 33, 50, 82]
    assert report["fixtures"]["authoritative_sparse_fixture"]["viewport"] == {
        "initial_min_x": 37,
        "initial_max_x": 97,
        "min_zoom": 0.75,
        "max_zoom": 4.0,
        "proof_mode": "receipt_backed_fixture",
    }


def test_cli_resolves_recommended_renderer_fixture() -> None:
    runner = CliRunner()

    result = runner.invoke(
        battle_cli.app,
        ["resolve-ux-renderer-fixture", str(SUMMARY_PATH)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA
    assert payload["status"] == "PASS"
    assert payload["battle_id"] == "battle-004"
    assert payload["fixture_key"] == "authoritative_parent_spawn_fixture"
    assert (
        payload["normalized_json"]
        == "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-parent-spawn.normalized.json"
    )
    assert payload["fixture_status"] == "PASS"
    assert payload["fixture_lineage_mode"] == "receipt_backed"
    assert payload["fixture_child_spawn_count"] == 1
    assert payload["fixture_playhead_current_x"] == 98
    assert payload["mocked"] is False
    assert payload["live_source"] == "brave_search_docker_arena_oracle_tau_harness"


def test_cli_writes_recommended_renderer_fixture_resolution(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "battle-004-renderer-fixture-resolution.json"

    result = runner.invoke(
        battle_cli.app,
        ["resolve-ux-renderer-fixture", str(SUMMARY_PATH), "--out", str(out)],
    )

    assert result.exit_code == 0, result.output
    stdout_payload = json.loads(result.output)
    file_payload = json.loads(out.read_text(encoding="utf-8"))
    assert file_payload == stdout_payload
    validate_renderer_fixture_resolution_schema(file_payload)
    validate_renderer_fixture_resolution(file_payload)
    assert file_payload["schema"] == EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA
    assert file_payload["normalized_json"].endswith("battle-004-parent-spawn.normalized.json")


def test_cli_validates_renderer_fixture_resolution(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "battle-004-renderer-fixture-resolution.json"
    payload = resolve_renderer_fixture_from_summary_path(SUMMARY_PATH)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = runner.invoke(
        battle_cli.app,
        ["validate-ux-renderer-fixture-resolution", str(out)],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["status"] == "PASS"
    assert report["schema"] == EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA
    assert report["fixture_child_spawn_count"] == 1
    assert report["fixture_playhead_current_x"] == 98
    assert report["mocked"] is False


def test_cli_rejects_renderer_fixture_resolution_without_spawn(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "battle-004-renderer-fixture-resolution.json"
    payload = resolve_renderer_fixture_from_summary_path(SUMMARY_PATH)
    payload["fixture_child_spawn_count"] = 0
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = runner.invoke(
        battle_cli.app,
        ["validate-ux-renderer-fixture-resolution", str(out)],
    )

    assert result.exit_code == 1
    assert "fixture_child_spawn_count" in result.output


def test_renderer_bundle_embeds_selected_parent_spawn_fixture() -> None:
    bundle = export_renderer_bundle_from_resolution_path(Path(EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH))

    validate_renderer_bundle_schema(bundle)
    validate_renderer_bundle(bundle)
    assert bundle["schema"] == EXPECTED_RENDERER_BUNDLE_SCHEMA
    assert bundle["resolution"]["fixture_key"] == "authoritative_parent_spawn_fixture"
    assert bundle["fixture"]["battle_id"] == "battle-004"
    assert bundle["fixture"]["scoreboard"]["child_spawn_count"] == 1
    assert bundle["fixture"]["timeline"]["playhead"]["current_x"] == 98
    assert bundle["fixture"]["mocked"] is False


def test_cli_exports_and_validates_renderer_bundle(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "battle-004-renderer-bundle.json"

    export_result = runner.invoke(
        battle_cli.app,
        ["export-ux-renderer-bundle", EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH, "--out", str(out)],
    )
    assert export_result.exit_code == 0, export_result.output
    export_report = json.loads(export_result.output)
    assert export_report["schema"] == EXPECTED_RENDERER_BUNDLE_SCHEMA
    assert export_report["child_spawn_count"] == 1
    assert out.exists()

    validate_result = runner.invoke(
        battle_cli.app,
        ["validate-ux-renderer-bundle", str(out)],
    )
    assert validate_result.exit_code == 0, validate_result.output
    validate_report = json.loads(validate_result.output)
    assert validate_report["schema"] == EXPECTED_RENDERER_BUNDLE_SCHEMA
    assert validate_report["playhead_current_x"] == 98


def test_renderer_bundle_rejects_fixture_resolution_mismatch() -> None:
    bundle = export_renderer_bundle_from_resolution_path(Path(EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH))
    bundle["fixture"]["scoreboard"]["child_spawn_count"] = 0

    with pytest.raises(ContractError, match="child_spawn_count"):
        validate_renderer_bundle(bundle)


def test_renderer_bundle_schema_rejects_sparse_embedded_fixture() -> None:
    bundle = export_renderer_bundle_from_resolution_path(Path(EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH))
    bundle["fixture"]["lineage"]["mode"] = "missing"
    bundle["fixture"]["lineage"]["spawn_count"] = 0
    bundle["fixture"]["lineage"]["groups"] = []
    bundle["fixture"]["lineage"]["spawns"] = []
    bundle["fixture"]["scoreboard"]["child_spawn_count"] = 0
    bundle["fixture"]["lanes"] = bundle["fixture"]["lanes"][:1]

    with pytest.raises(ContractError, match="Battle UX renderer bundle schema validation failed"):
        validate_renderer_bundle_schema(bundle)


def test_renderer_values_extracts_direct_ux_values_from_bundle() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))

    validate_renderer_values_schema(values)
    validate_renderer_values(values)
    validate_renderer_values(values, check_sources=True)
    assert values["schema"] == EXPECTED_RENDERER_VALUES_SCHEMA
    assert values["battle_id"] == "battle-004"
    assert values["scenario"]["public_entrypoint"] == "/api/import-zip"
    assert values["scenario"]["cwe"] == "CWE-22"
    assert values["spectator_shell"] == values["shell"]
    assert values["spectator_shell"]["battle_title"] == "BATTLE-004 · POST /api/import-zip"
    assert values["lineage"]["mode"] == "receipt_backed"
    assert values["lineage"]["spawn_count"] == 1
    assert values["proof_blockers"] == []
    assert values["scoreboard"]["child_spawn_count"] == 1
    assert values["timeline"]["playhead"]["current_x"] == 98
    assert values["timeline"]["playhead"]["animation_semantics"] == "receipt_replay_only"
    assert [frame["x"] for frame in values["timeline"]["playhead"]["keyframes"]] == [14, 33, 50, 58, 62, 66, 67, 76, 82, 86, 96, 98]
    assert values["timeline_time_model"]["mode"] == "receipt_order_with_round_clock"
    assert values["timeline_time_model"]["x_axis_mode"] == "receipt_order_percent"
    assert values["timeline_time_model"]["x_position_is_elapsed_time"] is False
    assert (
        "Every lane event must include a numeric elapsed_seconds value from the source receipt."
        in values["timeline_time_model"]["elapsed_time_axis_requirements"]
    )
    assert (
        "The adapter must validate monotonic elapsed timestamps before setting x_position_is_elapsed_time=true."
        in values["timeline_time_model"]["elapsed_time_axis_requirements"]
    )
    assert values["timeline_time_model"]["round_clock"]["allotted_seconds"] == values["battle_clock"]["allotted_seconds"]
    assert values["timeline_time_model"]["round_clock"]["elapsed_seconds"] == values["battle_clock"]["elapsed_seconds"]
    assert values["timeline_time_model"]["playhead"]["current_x"] == 98
    assert values["timeline_time_model"]["playhead"]["receipt_elapsed_seconds"] == values["timeline"]["playhead"]["elapsed_seconds"]
    assert values["timeline_time_model"]["receipt_elapsed_keyframe_count"] == 12
    assert values["timeline_time_model"]["receipt_elapsed_keyframes_are_monotonic_by_x"] is False
    assert "Render x positions as receipt-order positions, not wall-clock seconds." in values["timeline_time_model"]["render_rules"]
    assert values["timeline_elapsed_axis_model"]["schema"] == "battle.timeline_elapsed_axis_model.v1"
    assert values["timeline_elapsed_axis_model"]["x_axis_mode"] == "elapsed_seconds"
    assert values["timeline_elapsed_axis_model"]["x_position_is_elapsed_time"] is True
    assert values["timeline_elapsed_axis_model"]["keyframe_count"] == 12
    assert values["timeline_elapsed_axis_model"]["keyframes_are_monotonic"] is True
    elapsed_keyframes = values["timeline_elapsed_axis_model"]["keyframes"]
    assert values["timeline_elapsed_axis_model"]["playhead"]["current_elapsed_seconds"] == elapsed_keyframes[-1]["elapsed_seconds"]
    assert values["timeline_elapsed_axis_model"]["playhead"]["current_x"] == elapsed_keyframes[-1]["x"]
    assert [frame["receipt_order_x"] for frame in values["timeline_elapsed_axis_model"]["keyframes"]] == [14, 33, 50, 58, 62, 66, 76, 86, 67, 82, 96, 98]
    assert "Use timeline_elapsed_axis_model for DAW-style elapsed-time placement." in values["timeline_elapsed_axis_model"]["render_rules"]
    assert values["receipt_backed_values"]["timed_lane_event_count"] == 12
    assert values["receipt_backed_values"]["lane_event_count_for_timing"] == 12
    assert values["receipt_backed_values"]["complete_elapsed_activity_segment_count"] == 12
    assert values["receipt_backed_values"]["activity_segment_count_for_timing"] == 12
    assert values["receipt_backed_values"]["timed_playhead_keyframe_count"] == 12
    assert values["receipt_backed_values"]["playhead_elapsed_monotonic_by_x"] is False
    assert values["receipt_backed_values"]["elapsed_axis_x_axis_mode"] == "elapsed_seconds"
    assert values["receipt_backed_values"]["elapsed_axis_x_position_is_elapsed_time"] is True
    assert values["receipt_backed_values"]["elapsed_axis_keyframe_count"] == 12
    assert values["receipt_backed_values"]["elapsed_axis_keyframes_are_monotonic"] is True
    assert values["timeline_viewport_model"]["schema"] == "battle.timeline_viewport_model.v1"
    assert values["timeline_viewport_model"]["mode"] == "receipt_replay_scroll_viewport"
    assert values["timeline_viewport_model"]["scroll_axis"] == "horizontal"
    assert values["timeline_viewport_model"]["supports_pan"] is True
    assert values["timeline_viewport_model"]["supports_zoom"] is True
    assert values["timeline_viewport_model"]["bounds"] == {"min_x": 0, "max_x": 100}
    assert values["timeline_viewport_model"]["initial_window"]["min_x"] == 45
    assert values["timeline_viewport_model"]["initial_window"]["max_x"] == 100
    assert values["timeline_viewport_model"]["initial_window"]["width_x"] == 55
    assert values["timeline_viewport_model"]["zoom"]["min_zoom"] == 0.75
    assert values["timeline_viewport_model"]["zoom"]["max_zoom"] == 4.0
    assert values["timeline_viewport_model"]["playhead_follow"]["current_x"] == 98
    assert values["timeline_viewport_model"]["playhead_follow"]["keyframe_count"] == 12
    assert values["timeline_viewport_model"]["playhead_follow"]["keyframe_x_values"] == [14, 33, 50, 58, 62, 66, 67, 76, 82, 86, 96, 98]
    assert values["timeline_viewport_model"]["playhead_follow"]["follow_policy"] == "keep_current_keyframe_visible_without_claiming_live_time"
    assert values["timeline_viewport_model"]["pan_policy"]["clamp_to_bounds"] is True
    assert "Render the timeline as a horizontally scrollable receipt-order viewport." in values["timeline_viewport_model"]["render_rules"]
    assert values["timeline_lane_start_model"]["schema"] == "battle.timeline_lane_start_model.v1"
    assert values["timeline_lane_start_model"]["mode"] == "receipt_order_lane_starts"
    assert values["timeline_lane_start_model"]["start_count"] == 2
    assert values["timeline_lane_start_model"]["starts"][0]["lane_id"] == "payload-857-receipt"
    assert values["timeline_lane_start_model"]["starts"][0]["start_kind"] == "parent_lane_start"
    assert values["timeline_lane_start_model"]["starts"][0]["line_must_start_at_x"] == 7
    assert values["timeline_lane_start_model"]["starts"][0]["elapsed_start_seconds"] == values["lanes"][0]["start_elapsed_seconds"]
    assert values["timeline_lane_start_model"]["starts"][0]["elapsed_line_must_start_at_x"] == elapsed_keyframes[0]["x"]
    assert values["timeline_lane_start_model"]["starts"][0]["elapsed_line_end_x"] == elapsed_keyframes[9]["x"]
    assert values["timeline_lane_start_model"]["starts"][1]["lane_id"] == "payload-857-red-1"
    assert values["timeline_lane_start_model"]["starts"][1]["start_kind"] == "child_spawn_start"
    assert values["timeline_lane_start_model"]["starts"][1]["start_source"] == "lineage.spawns[].child_x_start"
    assert values["timeline_lane_start_model"]["starts"][1]["line_must_start_at_x"] == 62
    assert values["timeline_lane_start_model"]["starts"][1]["elapsed_start_seconds"] == values["lineage"]["spawns"][0]["child_start_elapsed_seconds"]
    assert values["timeline_lane_start_model"]["starts"][1]["elapsed_line_must_start_at_x"] == elapsed_keyframes[4]["x"]
    assert values["timeline_lane_start_model"]["starts"][1]["elapsed_line_end_x"] == elapsed_keyframes[-1]["x"]
    assert values["timeline_lane_start_model"]["starts"][1]["source_receipt_id"] == "lineage-spawn-payload-857-receipt-to-payload-857-red-1"
    assert values["timeline_lane_start_model"]["starts"][1]["source_event_id"] == "payload-857-red-1:spawned-from:payload-857-receipt"
    assert (
        "Render child lanes from child_spawn_start/source_receipt_id, not from global time zero."
        in values["timeline_lane_start_model"]["render_rules"]
    )
    assert (
        "For elapsed-time/DAW placement, render each lane line from elapsed_line_must_start_at_x."
        in values["timeline_lane_start_model"]["render_rules"]
    )
    assert values["lane_activity_timeline_model"]["schema"] == "battle.lane_activity_timeline_model.v1"
    assert values["lane_activity_timeline_model"]["mode"] == "receipt_backed_activity_segments"
    assert values["lane_activity_timeline_model"]["lane_count"] == 2
    assert values["lane_activity_timeline_model"]["segment_count"] == 12
    assert values["lane_activity_timeline_model"]["phases"] == [
        "handoff",
        "judge_replay",
        "materialize",
        "patch_gate",
        "payload",
        "research",
        "useful_signal",
    ]
    assert values["lane_activity_timeline_model"]["lanes"][0]["segment_count"] == 7
    parent_first_segment = values["lane_activity_timeline_model"]["lanes"][0]["segments"][0]
    assert parent_first_segment["segment_id"] == "payload-857-receipt:segment:01"
    assert parent_first_segment["phase"] == "materialize"
    assert parent_first_segment["label"] == "spawn / materialize"
    assert parent_first_segment["start_x"] == 7
    assert parent_first_segment["end_x"] == 14
    assert parent_first_segment["start_elapsed_seconds"] == values["lanes"][0]["start_elapsed_seconds"]
    assert parent_first_segment["end_elapsed_seconds"] == values["lanes"][0]["start_elapsed_seconds"]
    assert parent_first_segment["elapsed_start_x"] == parent_first_segment["elapsed_end_x"]
    assert parent_first_segment["elapsed_axis_source"] == "timeline_elapsed_axis_model"
    assert parent_first_segment["source_event_id"] is None
    assert parent_first_segment["proof_mode"] == "receipt_backed_fixture"
    assert values["lane_activity_timeline_model"]["lanes"][1]["segment_count"] == 5
    child_first_segment = values["lane_activity_timeline_model"]["lanes"][1]["segments"][0]
    assert child_first_segment["start_x"] == 62
    assert child_first_segment["start_elapsed_seconds"] == values["lineage"]["spawns"][0]["child_start_elapsed_seconds"]
    assert child_first_segment["elapsed_start_x"] == values["timeline_lane_start_model"]["starts"][1]["elapsed_line_must_start_at_x"]
    assert child_first_segment["phase"] == "handoff"
    assert (
        "Do not invent research, payload, mutate, trigger, patch, crash, or terminal phases client-side."
        in values["lane_activity_timeline_model"]["render_rules"]
    )
    assert (
        "For elapsed-time/DAW placement, render segments from elapsed_start_x to elapsed_end_x."
        in values["lane_activity_timeline_model"]["render_rules"]
    )
    assert values["timeline_label_layout_model"]["schema"] == "battle.timeline_label_layout_model.v1"
    assert values["timeline_label_layout_model"]["mode"] == "receipt_event_label_slots"
    assert values["timeline_label_layout_model"]["label_count"] == 12
    assert values["timeline_label_layout_model"]["collision_group_count"] == 7
    parent_x05 = next(
        group for group in values["timeline_label_layout_model"]["collision_groups"] if group["collision_group"] == "x05"
    )
    assert parent_x05["event_count"] == 2
    assert parent_x05["bands"] == ["lower", "upper"]
    assert parent_x05["priority_order"] == [
        "payload-857-receipt:useful",
        "payload-857-receipt:spawn:payload-857-red-1",
    ]
    x06 = next(group for group in values["timeline_label_layout_model"]["collision_groups"] if group["collision_group"] == "x06")
    assert x06["lane_ids"] == ["payload-857-receipt", "payload-857-red-1"]
    assert x06["priority_order"] == [
        "payload-857-red-1:spawned-from:payload-857-receipt",
        "payload-857-receipt:blue",
        "payload-857-red-1:arena",
    ]
    parent_labels = values["timeline_label_layout_model"]["lanes"][0]["labels"]
    assert parent_labels[2]["slot_key"] == "payload-857-receipt:x05:upper"
    assert parent_labels[2]["suppress_when_colliding"] is False
    assert parent_labels[0]["suppress_when_colliding"] is True
    assert (
        "Use label_band and collision_group from this model; do not infer label stacking from pixel position alone."
        in values["timeline_label_layout_model"]["render_rules"]
    )
    assert values["lineage_render_model"]["schema"] == "battle.lineage_render_model.v1"
    assert values["lineage_render_model"]["mode"] == "receipt_backed_parent_child"
    assert values["lineage_render_model"]["collapse_source"] == "lineage.groups"
    assert values["lineage_render_model"]["connector_source"] == "lineage.spawns"
    assert values["lineage_render_model"]["group_count"] == 1
    assert values["lineage_render_model"]["connector_count"] == 1
    assert values["lineage_render_model"]["groups"][0]["parent_lane_id"] == "payload-857-receipt"
    assert values["lineage_render_model"]["groups"][0]["child_lane_ids"] == ["payload-857-red-1"]
    assert values["lineage_render_model"]["groups"][0]["collapsible"] is True
    assert values["lineage_render_model"]["groups"][0]["expanded_by_default"] is True
    assert values["lineage_render_model"]["connectors"][0]["parent_event_id"] == "payload-857-receipt:spawn:payload-857-red-1"
    assert values["lineage_render_model"]["connectors"][0]["child_event_id"] == "payload-857-red-1:spawned-from:payload-857-receipt"
    assert values["lineage_render_model"]["connectors"][0]["parent_connector_x"] == 58
    assert values["lineage_render_model"]["connectors"][0]["child_connector_x"] == 62
    assert values["lineage_render_model"]["connectors"][0]["source_receipt_id"] == "lineage-spawn-payload-857-receipt-to-payload-857-red-1"
    assert values["spawn_gate_model"]["schema"] == "battle.spawn_gate_model.v1"
    assert values["spawn_gate_model"]["mode"] == "receipt_backed_spawn_gates"
    assert values["spawn_gate_model"]["gate_count"] == 1
    assert values["spawn_gate_model"]["renderable_gate_count"] == 1
    spawn_gate = values["spawn_gate_model"]["gates"][0]
    assert spawn_gate["renderable"] is True
    assert spawn_gate["parent_lane_id"] == "payload-857-receipt"
    assert spawn_gate["child_lane_id"] == "payload-857-red-1"
    assert spawn_gate["parent_event_id"] == "payload-857-receipt:spawn:payload-857-red-1"
    assert spawn_gate["child_event_id"] == "payload-857-red-1:spawned-from:payload-857-receipt"
    assert spawn_gate["spawn_receipt_id"] == "lineage-spawn-payload-857-receipt-to-payload-857-red-1"
    assert spawn_gate["required_sources"]["parent_lane_exists"] is True
    assert spawn_gate["required_sources"]["child_lane_exists"] is True
    assert spawn_gate["required_sources"]["lineage_receipt_present"] is True
    assert spawn_gate["required_sources"]["parent_spawn_event_present"] is True
    assert spawn_gate["required_sources"]["child_spawn_event_present"] is True
    assert spawn_gate["required_sources"]["blue_success_pair_count"] == 4
    assert len(spawn_gate["blue_success_pairs"]) == 4
    assert "Render parent-child lanes only from spawn_gate_model.gates where renderable is true." in values["spawn_gate_model"]["render_rules"]
    assert values["selected_lane_model"]["schema"] == "battle.selected_lane_model.v1"
    assert values["selected_lane_model"]["selection_strategy"] == "first_receipt_backed_child_lane"
    assert values["selected_lane_model"]["lane_id"] == "payload-857-red-1"
    assert values["selected_lane_model"]["lane_index"] == 1
    assert values["selected_lane_model"]["lane_path"] == "/lanes/1"
    assert values["selected_lane_model"]["cockpit_path"] == "/lanes/1/cockpit"
    assert values["selected_lane_model"]["replay_cta_path"] == "/lanes/1/replay/cta"
    assert values["selected_lane_model"]["cockpit"] == values["lanes"][1]["cockpit"]
    assert values["selected_lane_model"]["replay_cta"] == values["lanes"][1]["replay"]["cta"]
    truth = values["outcome_truth_constraints_model"]
    assert truth["schema"] == "battle.outcome_truth_constraints_model.v1"
    assert truth["mode"] == "receipt_backed_outcome_gates"
    assert truth["allowed"]["child_lineage"]["allowed"] is True
    assert truth["allowed"]["child_lineage"]["count"] == 1
    assert truth["allowed"]["child_lineage"]["lane_ids"] == ["payload-857-red-1"]
    assert truth["allowed"]["blue_blocks"]["allowed"] is True
    assert truth["allowed"]["blue_blocks"]["event_count"] == 4
    assert truth["allowed"]["blue_blocks"]["blue_success_pair_count"] == 4
    assert truth["allowed"]["blue_blocks"]["lane_ids"] == ["payload-857-receipt", "payload-857-red-1"]
    assert truth["allowed"]["docker_replay_cta"]["allowed"] is True
    assert truth["allowed"]["docker_replay_cta"]["receipt_only_count"] == 2
    assert truth["allowed"]["docker_replay_cta"]["executable_count"] == 0
    assert truth["forbidden"]["blue_kill"]["allowed"] is False
    assert truth["forbidden"]["fastest_crash"]["allowed"] is False
    assert truth["forbidden"]["survivor_promotion"]["allowed"] is False
    assert truth["forbidden"]["live_replay_execution"]["allowed"] is False
    assert "Read outcome permissions from this model before rendering dramatic states." in truth["render_rules"]
    assert values["receipt_backed_values"]["timeline_x_axis_mode"] == "receipt_order_percent"
    assert values["receipt_backed_values"]["timeline_x_position_is_elapsed_time"] is False
    assert values["receipt_backed_values"]["round_allotted_seconds"] == values["battle_clock"]["allotted_seconds"]
    assert values["receipt_backed_values"]["round_elapsed_seconds"] == values["battle_clock"]["elapsed_seconds"]
    assert values["receipt_backed_values"]["round_remaining_seconds"] == values["battle_clock"]["remaining_seconds"]
    assert values["receipt_backed_values"]["timeline_viewport_initial_min_x"] == 45
    assert values["receipt_backed_values"]["timeline_viewport_initial_max_x"] == 100
    assert values["receipt_backed_values"]["timeline_viewport_min_zoom"] == 0.75
    assert values["receipt_backed_values"]["timeline_viewport_max_zoom"] == 4.0
    assert values["receipt_backed_values"]["timeline_playhead_keyframe_count"] == 12
    assert values["receipt_backed_values"]["lane_phase_coverage_count"] == 2
    assert values["receipt_backed_values"]["lane_start_model_count"] == 2
    assert values["receipt_backed_values"]["lane_activity_segment_count"] == 12
    assert values["receipt_backed_values"]["timeline_label_count"] == 12
    assert values["receipt_backed_values"]["timeline_label_collision_group_count"] == 7
    assert values["receipt_backed_values"]["lanes_with_research_count"] == 2
    assert values["receipt_backed_values"]["lanes_with_spawn_handoff_count"] == 2
    assert values["receipt_backed_values"]["parent_lane_ids"] == ["payload-857-receipt"]
    assert values["receipt_backed_values"]["child_lane_ids"] == ["payload-857-red-1"]
    assert values["receipt_backed_values"]["spawn_receipt_ids"] == ["lineage-spawn-payload-857-receipt-to-payload-857-red-1"]
    assert values["lanes"][0]["children"] == ["payload-857-red-1"]
    assert values["lanes"][0]["collapsible"] is True
    assert values["lanes"][1]["parentId"] == "payload-857-receipt"
    assert values["lanes"][0]["replay"]["cta"]["label"] == "REPLAY IN DOCKER"
    assert values["lanes"][0]["replay"]["cta"]["state"] == "receipt_only"
    assert values["lane_phase_coverage"][0]["lane_id"] == "payload-857-receipt"
    assert values["lane_phase_coverage"][0]["has_research"] is True
    assert values["lane_phase_coverage"][0]["has_spawn_handoff"] is True
    assert values["lane_phase_coverage"][0]["phases"] == [
        "materialize",
        "research",
        "payload",
        "useful_signal",
        "handoff",
        "patch_gate",
        "judge_replay",
    ]
    assert values["lane_phase_coverage"][1]["lane_id"] == "payload-857-red-1"
    assert values["lane_phase_coverage"][1]["parent_id"] == "payload-857-receipt"
    assert values["lane_phase_coverage"][1]["phases"] == ["handoff", "research", "payload", "useful_signal", "patch_gate"]
    assert "Fastest crash" in values["forbidden_inferences"]


def test_renderer_values_source_validation_rejects_drift() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["timeline"]["playhead"]["current_x"] = 97
    values["receipt_backed_values"]["playhead_current_x"] = 97

    with pytest.raises(ContractError, match="renderer values timeline must match source_fixture"):
        validate_renderer_values(values, check_sources=True)


def test_cli_exports_and_validates_renderer_values(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "battle-004-ux-renderer-values.json"

    export_result = runner.invoke(
        battle_cli.app,
        ["export-ux-renderer-values", EXPECTED_RENDERER_BUNDLE_PATH, "--out", str(out)],
    )
    assert export_result.exit_code == 0, export_result.output
    export_report = json.loads(export_result.output)
    assert export_report["schema"] == EXPECTED_RENDERER_VALUES_SCHEMA
    assert export_report["child_spawn_count"] == 1
    assert export_report["playhead_current_x"] == 98
    assert out.exists()

    validate_result = runner.invoke(
        battle_cli.app,
        ["validate-ux-renderer-values", str(out)],
    )
    assert validate_result.exit_code == 0, validate_result.output
    validate_report = json.loads(validate_result.output)
    assert validate_report["schema"] == EXPECTED_RENDERER_VALUES_SCHEMA
    assert validate_report["child_spawn_count"] == 1
    assert validate_report["playhead_current_x"] == 98


def test_renderer_values_rejects_sparse_lineage() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["lineage"]["mode"] = "missing"
    values["lineage"]["spawn_count"] = 0
    values["scoreboard"]["child_spawn_count"] = 0

    with pytest.raises(ContractError, match="lineage.spawn_count"):
        validate_renderer_values(values)


def test_renderer_values_rejects_child_lane_starting_before_spawn() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["lanes"][1]["xStart"] = 1
    values["lane_phase_coverage"] = [
        {**entry, "x_start": 1 if entry["lane_id"] == "payload-857-red-1" else entry["x_start"]}
        for entry in values["lane_phase_coverage"]
    ]

    with pytest.raises(ContractError, match="must start at or after its lineage spawn x position"):
        validate_renderer_values(values)


def test_renderer_values_rejects_time_model_claiming_elapsed_x_axis() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["timeline_time_model"]["x_position_is_elapsed_time"] = True

    with pytest.raises(ContractError, match="x_position_is_elapsed_time"):
        validate_renderer_values(values)


def test_renderer_values_rejects_missing_elapsed_time_axis_requirements() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["timeline_time_model"]["elapsed_time_axis_requirements"] = []

    with pytest.raises(ContractError, match="elapsed_time_axis_requirements"):
        validate_renderer_values(values)


def test_renderer_values_rejects_stale_lineage_render_connector() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["lineage_render_model"]["connectors"][0]["parent_connector_x"] = 1

    with pytest.raises(ContractError, match="lineage_render_model"):
        validate_renderer_values(values)


def test_renderer_values_rejects_stale_spawn_gate_model() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["spawn_gate_model"]["gates"][0]["required_sources"]["child_spawn_event_present"] = False

    with pytest.raises(ContractError, match="spawn_gate_model"):
        validate_renderer_values(values)


def test_renderer_values_rejects_stale_selected_lane_model() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["selected_lane_model"]["lane_id"] = "payload-857-receipt"

    with pytest.raises(ContractError, match="selected_lane_model"):
        validate_renderer_values(values)


def test_renderer_values_rejects_stale_timeline_lane_start_model() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["timeline_lane_start_model"]["starts"][1]["line_must_start_at_x"] = 0

    with pytest.raises(ContractError, match="timeline_lane_start_model"):
        validate_renderer_values(values)


def test_renderer_values_rejects_stale_lane_activity_timeline_model() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["lane_activity_timeline_model"]["lanes"][1]["segments"][0]["start_x"] = 0

    with pytest.raises(ContractError, match="lane_activity_timeline_model"):
        validate_renderer_values(values)


def test_renderer_values_rejects_stale_outcome_truth_constraints_model() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["outcome_truth_constraints_model"]["forbidden"]["fastest_crash"]["allowed"] = True

    with pytest.raises(ContractError, match="outcome_truth_constraints_model"):
        validate_renderer_values(values)


def test_renderer_values_rejects_stale_timeline_viewport_model() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["timeline_viewport_model"]["playhead_follow"]["current_x"] = 96

    with pytest.raises(ContractError, match="timeline_viewport_model"):
        validate_renderer_values(values)


def test_renderer_values_rejects_stale_timeline_label_layout_model() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["timeline_label_layout_model"]["lanes"][0]["labels"][2]["label_band"] = "lower"

    with pytest.raises(ContractError, match="timeline_label_layout_model"):
        validate_renderer_values(values)


def test_renderer_values_rejects_stale_receipt_backed_time_summary() -> None:
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["receipt_backed_values"]["timeline_x_axis_mode"] = "elapsed_seconds"

    with pytest.raises(ContractError, match="timeline_x_axis_mode"):
        validate_renderer_values(values)


def test_ux_data_contract_index_exports_authoritative_backend_json_sources() -> None:
    index = export_ux_data_contract_index_from_summary_path(SUMMARY_PATH)

    validate_ux_data_contract_index_schema(index)
    validate_ux_data_contract_index(index)
    assert index["schema"] == EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA
    assert index["battle_id"] == "battle-004"
    assert index["current_agent_scope"] == "backend_json_contract_only"
    assert index["authoritative_renderer_values"] == EXPECTED_RENDERER_VALUES_PATH
    assert index["authoritative_normalized_fixture"] == str(Path(EXPECTED_RENDERER_VALUES_PATH).with_name("battle-004-parent-spawn.normalized.json"))
    assert index["proof_generation_contract"]["canonical_command"] == EXPECTED_PARENT_SPAWN_PROOF_COMMAND
    assert index["proof_generation_contract"]["spawn_red_child_on_blue_success"] is True
    assert index["proof_generation_contract"]["red_workers"] == 2
    assert index["proof_generation_contract"]["blue_workers"] == 2
    assert index["supporting_artifacts"]["renderer_bundle"] == EXPECTED_RENDERER_BUNDLE_PATH
    assert EXPECTED_RENDERER_VALUES_COMMAND in index["required_validation_commands"]
    assert EXPECTED_UX_DATA_CONTRACT_INDEX_COMMAND in index["required_validation_commands"]
    assert index["renderer_value_paths"]["spectator_shell"] == "/spectator_shell"
    assert index["renderer_value_paths"]["proof_generation_contract"] == "/proof_generation_contract"
    assert index["renderer_value_paths"]["shell"] == "/shell"
    assert index["renderer_value_paths"]["timeline"] == "/timeline"
    assert index["renderer_value_paths"]["timeline_time_model"] == "/timeline_time_model"
    assert index["renderer_value_paths"]["timeline_elapsed_axis_model"] == "/timeline_elapsed_axis_model"
    assert index["renderer_value_paths"]["timeline_viewport_model"] == "/timeline_viewport_model"
    assert index["renderer_value_paths"]["timeline_lane_start_model"] == "/timeline_lane_start_model"
    assert index["renderer_value_paths"]["lane_activity_timeline_model"] == "/lane_activity_timeline_model"
    assert index["renderer_value_paths"]["timeline_label_layout_model"] == "/timeline_label_layout_model"
    assert index["renderer_value_paths"]["lineage_render_model"] == "/lineage_render_model"
    assert index["renderer_value_paths"]["spawn_gate_model"] == "/spawn_gate_model"
    assert index["renderer_value_paths"]["selected_lane_model"] == "/selected_lane_model"
    assert index["renderer_value_paths"]["outcome_truth_constraints_model"] == "/outcome_truth_constraints_model"
    assert index["renderer_value_paths"]["lane_phase_coverage"] == "/lane_phase_coverage"
    assert index["renderer_value_paths"]["replay_cta_values"] == "/selected_lane_model/replay_cta"
    assert index["renderer_value_paths"]["selected_lane_cockpit"] == "/selected_lane_model/cockpit"
    assert index["receipt_backed_values"]["child_spawn_count"] == 1
    assert index["receipt_backed_values"]["playhead_current_x"] == 98
    assert index["receipt_backed_values"]["timeline_x_axis_mode"] == "receipt_order_percent"
    assert index["receipt_backed_values"]["timeline_x_position_is_elapsed_time"] is False
    assert index["receipt_backed_values"]["elapsed_axis_x_axis_mode"] == "elapsed_seconds"
    assert index["receipt_backed_values"]["elapsed_axis_x_position_is_elapsed_time"] is True
    assert index["receipt_backed_values"]["elapsed_axis_keyframe_count"] == 12
    assert index["receipt_backed_values"]["elapsed_axis_keyframes_are_monotonic"] is True
    assert index["receipt_backed_values"]["timed_lane_event_count"] == 12
    assert index["receipt_backed_values"]["lane_event_count_for_timing"] == 12
    assert index["receipt_backed_values"]["complete_elapsed_activity_segment_count"] == 12
    assert index["receipt_backed_values"]["activity_segment_count_for_timing"] == 12
    assert index["receipt_backed_values"]["timed_playhead_keyframe_count"] == 12
    assert index["receipt_backed_values"]["playhead_elapsed_monotonic_by_x"] is False
    assert index["timing_contract"]["schema"] == "battle.ux_timing_contract.v1"
    assert index["timing_contract"]["source"] == "/timeline_time_model"
    assert index["timing_contract"]["x_axis_mode"] == "receipt_order_percent"
    assert index["timing_contract"]["x_position_is_elapsed_time"] is False
    assert index["timing_contract"]["receipt_elapsed_keyframe_count"] == 12
    assert index["timing_contract"]["receipt_elapsed_keyframes_are_monotonic_by_x"] is False
    assert index["timing_contract"]["timed_lane_event_count"] == 12
    assert index["timing_contract"]["playhead_elapsed_monotonic_by_x"] is False
    assert (
        "Render x positions as receipt-order positions, not wall-clock seconds."
        in index["timing_contract"]["render_rules"]
    )
    assert index["receipt_backed_values"]["round_allotted_seconds"] == 1200
    assert index["receipt_backed_values"]["timeline_viewport_initial_min_x"] == 45
    assert index["receipt_backed_values"]["timeline_viewport_initial_max_x"] == 100
    assert index["receipt_backed_values"]["timeline_viewport_min_zoom"] == 0.75
    assert index["receipt_backed_values"]["timeline_viewport_max_zoom"] == 4.0
    assert index["receipt_backed_values"]["timeline_playhead_keyframe_count"] == 12
    assert index["receipt_backed_values"]["lane_phase_coverage_count"] == 2
    assert index["receipt_backed_values"]["lane_start_model_count"] == 2
    assert index["receipt_backed_values"]["lane_activity_segment_count"] == 12
    assert index["receipt_backed_values"]["timeline_label_count"] == 12
    assert index["receipt_backed_values"]["timeline_label_collision_group_count"] == 7
    assert index["receipt_backed_values"]["lanes_with_research_count"] == 2
    assert index["receipt_backed_values"]["lanes_with_spawn_handoff_count"] == 2
    assert index["receipt_backed_values"]["parent_lane_ids"] == ["payload-857-receipt"]
    assert index["receipt_backed_values"]["child_lane_ids"] == ["payload-857-red-1"]
    assert index["receipt_backed_values"]["spawn_receipt_ids"] == ["lineage-spawn-payload-857-receipt-to-payload-857-red-1"]
    assert set(index["artifact_digests"]) == {
        "authoritative_renderer_values",
        "authoritative_normalized_fixture",
        "renderer_fixture_resolution",
        "renderer_bundle",
        "goal_source",
    }
    assert index["artifact_digests"]["authoritative_renderer_values"]["path"] == EXPECTED_RENDERER_VALUES_PATH
    assert len(index["artifact_digests"]["authoritative_renderer_values"]["sha256"]) == 64
    assert "React layout" in index["render_boundary"]["project_agent_must_not_provide"]


def test_ux_data_contract_index_rejects_stale_artifact_digest() -> None:
    index = export_ux_data_contract_index_from_summary_path(SUMMARY_PATH)
    index["artifact_digests"]["authoritative_renderer_values"]["sha256"] = "0" * 64

    with pytest.raises(ContractError, match="artifact_digests.authoritative_renderer_values.sha256"):
        validate_ux_data_contract_index(index)


def test_ux_data_contract_index_rejects_stale_renderer_value_path() -> None:
    index = export_ux_data_contract_index_from_summary_path(SUMMARY_PATH)
    index["renderer_value_paths"]["lineage_render_model"] = "/lineage"

    with pytest.raises(ContractError, match="renderer_value_paths"):
        validate_ux_data_contract_index(index)


def test_ux_data_contract_index_rejects_stale_timing_contract() -> None:
    index = export_ux_data_contract_index_from_summary_path(SUMMARY_PATH)
    index["timing_contract"]["x_position_is_elapsed_time"] = True

    with pytest.raises(ContractError, match="timing_contract"):
        validate_ux_data_contract_index(index)


def test_ux_data_contract_index_rejects_wrong_authoritative_values_path() -> None:
    index = export_ux_data_contract_index_from_summary_path(SUMMARY_PATH)
    index["authoritative_renderer_values"] = "/tmp/not-the-battle-renderer-values.json"

    with pytest.raises(ContractError, match="authoritative_renderer_values"):
        validate_ux_data_contract_index(index)


def test_cli_exports_and_validates_ux_data_contract_index(tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "battle-004-ux-data-contract-index.json"

    export_result = runner.invoke(
        battle_cli.app,
        ["export-ux-data-contract-index", str(SUMMARY_PATH), "--out", str(out)],
    )
    assert export_result.exit_code == 0, export_result.output
    export_report = json.loads(export_result.output)
    assert export_report["schema"] == EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA
    assert export_report["authoritative_renderer_values"] == EXPECTED_RENDERER_VALUES_PATH
    assert export_report["child_spawn_count"] == 1
    assert out.exists()

    validate_result = runner.invoke(
        battle_cli.app,
        ["validate-ux-data-contract-index", str(out)],
    )
    assert validate_result.exit_code == 0, validate_result.output
    validate_report = json.loads(validate_result.output)
    assert validate_report["schema"] == EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA
    assert validate_report["playhead_current_x"] == 98


def test_ux_data_contract_index_export_can_bootstrap_missing_index(tmp_path: Path) -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    summary.pop("data_contract_index")
    bootstrap_summary = tmp_path / "summary-without-index.json"
    bootstrap_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ContractError, match="data_contract_index"):
        validate_handoff_summary(summary)

    index = export_ux_data_contract_index_from_summary_path(bootstrap_summary)
    validate_ux_data_contract_index(index)
    assert index["schema"] == EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA
    assert index["authoritative_renderer_values"] == EXPECTED_RENDERER_VALUES_PATH
    assert index["receipt_backed_values"]["child_spawn_count"] == 1


def test_renderer_fixture_resolver_is_backend_contract() -> None:
    payload = resolve_renderer_fixture_from_summary_path(SUMMARY_PATH)

    validate_renderer_fixture_resolution_schema(payload)
    validate_renderer_fixture_resolution(payload)
    assert payload["schema"] == EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA
    assert payload["status"] == "PASS"
    assert payload["fixture_key"] == "authoritative_parent_spawn_fixture"
    assert payload["fixture_status"] == "PASS"
    assert payload["fixture_lineage_mode"] == "receipt_backed"
    assert payload["fixture_child_spawn_count"] == 1
    assert payload["fixture_playhead_current_x"] == 98
    assert payload["fixture_playhead_keyframe_x_values"] == [14, 33, 50, 58, 62, 66, 67, 76, 82, 86, 96, 98]
    assert payload["mocked"] is False
    assert payload["live_source"] == "brave_search_docker_arena_oracle_tau_harness"


def test_renderer_fixture_resolution_rejects_sparse_or_static_playhead() -> None:
    payload = resolve_renderer_fixture_from_summary_path(SUMMARY_PATH)
    payload["fixture_child_spawn_count"] = 0

    with pytest.raises(ContractError, match="fixture_child_spawn_count"):
        validate_renderer_fixture_resolution(payload)

    payload = resolve_renderer_fixture_from_summary_path(SUMMARY_PATH)
    payload["fixture_playhead_current_x"] = 82

    with pytest.raises(ContractError, match="final keyframe"):
        validate_renderer_fixture_resolution(payload)


def test_backend_ux_handoff_summary_validator_checks_goal_source_contents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    stale_goal = tmp_path / "GOAL.md"
    stale_goal.write_text("# stale\nPOST /api/session/verify\n", encoding="utf-8")
    summary["goal_source_contract"]["source"] = str(stale_goal)
    monkeypatch.setattr(ux_contract_validator, "EXPECTED_GOAL_SOURCE_PATH", str(stale_goal))

    with pytest.raises(ContractError, match="missing required GOAL.md phrases"):
        validate_handoff_summary(summary)


def test_backend_ux_handoff_summary_validator_checks_renderer_values_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    broken_values = tmp_path / "battle-004-ux-renderer-values.json"
    values = export_renderer_values_from_bundle_path(Path(EXPECTED_RENDERER_BUNDLE_PATH))
    values["lineage"]["spawn_count"] = 0
    values["scoreboard"]["child_spawn_count"] = 0
    broken_values.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["renderer_values"]["json"] = str(broken_values)
    monkeypatch.setattr(ux_contract_validator, "EXPECTED_RENDERER_VALUES_PATH", str(broken_values))

    with pytest.raises(ContractError, match="summary.renderer_values.json violates Battle UX renderer values contract"):
        validate_handoff_summary(summary)


def test_backend_ux_handoff_summary_validator_checks_renderer_bundle_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    broken_bundle = tmp_path / "battle-004-renderer-bundle.json"
    bundle = export_renderer_bundle_from_resolution_path(Path(EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH))
    bundle["fixture"]["lineage"]["spawn_count"] = 0
    bundle["fixture"]["scoreboard"]["child_spawn_count"] = 0
    broken_bundle.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["renderer_bundle"]["json"] = str(broken_bundle)
    monkeypatch.setattr(ux_contract_validator, "EXPECTED_RENDERER_BUNDLE_PATH", str(broken_bundle))

    with pytest.raises(ContractError, match="summary.renderer_bundle.json violates Battle UX renderer bundle contract"):
        validate_handoff_summary(summary)


def test_backend_ux_handoff_summary_validator_checks_data_contract_index_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    broken_index = tmp_path / "battle-004-ux-data-contract-index.json"
    index = export_ux_data_contract_index_from_summary_path(SUMMARY_PATH)
    index["receipt_backed_values"]["child_spawn_count"] = 0
    broken_index.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["data_contract_index"]["json"] = str(broken_index)
    monkeypatch.setattr(ux_contract_validator, "EXPECTED_UX_DATA_CONTRACT_INDEX_PATH", str(broken_index))

    with pytest.raises(ContractError, match="summary.data_contract_index.json violates Battle UX data contract index"):
        validate_handoff_summary(summary)


def test_adapter_emits_parent_child_lineage_only_from_receipts(tmp_path: Path) -> None:
    proof_dir = _write_tau_public_only_proof(tmp_path, include_lineage=True)

    fixture = adapt_proof_dir(proof_dir=proof_dir, battle_id="battle-004")
    validate_fixture(fixture)
    _validate_json_schema(fixture)

    lanes = {lane["id"]: lane for lane in fixture["lanes"]}
    event_types = {event["event_type"] for event in fixture["events"]}

    assert fixture["mocked"] is False
    assert fixture["live_source"] == "brave_search_docker_arena_oracle_tau_harness"
    assert fixture["scenario"]["public_entrypoint"] == "/api/import-zip"
    assert fixture["scenario"]["cwe"] == "CWE-22"
    assert fixture["spectator_shell"]["schema"] == "battle.spectator_shell.v1"
    assert fixture["spectator_shell"]["battle_title"] == "BATTLE-004 · POST /api/import-zip"
    assert fixture["spectator_shell"]["facts"][2] == {"label": "Target", "value": "POST /api/import-zip"}
    assert fixture["spectator_shell"]["facts"][4] == {"label": "Round time", "value": "03:04 / 04:00"}
    assert fixture["spectator_shell"]["event_ticker"]["label"] == "Receipt events"
    assert fixture["spectator_shell"]["event_ticker"]["count"] == len(fixture["events"])
    assert fixture["spectator_shell"]["event_ticker"]["live"] is False
    assert fixture["lineage_request"] == {
        "condition": "parent lane must have a Judge BLUE_SUCCESS attempt before Tau child spawn is requested",
        "mode": "spawn_red_child_after_blue_success",
        "proof_mode": "receipt_backed_fixture",
        "receipt": "lineage-receipts.json",
        "requested": True,
        "schema": "battle.lineage_request.v1",
        "status": "PASS",
    }
    assert fixture["renderer_binding_contract"]["schema"] == "battle.renderer_binding_contract.v1"
    assert fixture["renderer_binding_contract"]["battle_shell"]["title"] == "spectator_shell.battle_title"
    assert fixture["renderer_binding_contract"]["round_time"]["clock_source"] == "battle_clock"
    assert fixture["renderer_binding_contract"]["moving_playhead"]["keyframes"] == "timeline.playhead.keyframes[]"
    assert fixture["renderer_binding_contract"]["elapsed_timeline_axis"]["model"] == "timeline_elapsed_axis_model"
    assert fixture["renderer_binding_contract"]["elapsed_timeline_axis"]["keyframes"] == "timeline_elapsed_axis_model.keyframes[]"
    assert fixture["renderer_binding_contract"]["elapsed_timeline_axis"]["elapsed_x"] == "timeline_elapsed_axis_model.keyframes[].x"
    assert (
        fixture["renderer_binding_contract"]["elapsed_timeline_axis"]["legacy_receipt_order_x"]
        == "timeline_elapsed_axis_model.keyframes[].receipt_order_x"
    )
    assert fixture["renderer_binding_contract"]["elapsed_timeline_axis"]["lane_start_model"] == "timeline_lane_start_model"
    assert (
        fixture["renderer_binding_contract"]["elapsed_timeline_axis"]["lane_start_elapsed_x"]
        == "timeline_lane_start_model.starts[].elapsed_line_must_start_at_x"
    )
    assert (
        fixture["renderer_binding_contract"]["elapsed_timeline_axis"]["activity_segment_elapsed_start_x"]
        == "lane_activity_timeline_model.lanes[].segments[].elapsed_start_x"
    )
    assert fixture["renderer_binding_contract"]["lane_activity_and_label_layout"]["timeline_lane_start_model"] == "timeline_lane_start_model"
    assert fixture["renderer_binding_contract"]["lane_activity_and_label_layout"]["activity_timeline_model"] == "lane_activity_timeline_model"
    assert fixture["renderer_binding_contract"]["parent_spawn_and_collapse"]["request"] == "lineage_request"
    assert fixture["renderer_binding_contract"]["parent_spawn_and_collapse"]["request_status"] == "lineage_request.status"
    assert fixture["renderer_binding_contract"]["parent_spawn_and_collapse"]["groups"] == "lineage.groups[]"
    assert fixture["renderer_binding_contract"]["agent_detail_cockpit"]["selected_tau_identity"] == "lanes[].cockpit.selected_tau_exploit_subagent"
    assert fixture["renderer_binding_contract"]["docker_replay_cta"]["state"] == "lanes[].replay.cta.state"

    assert fixture["lineage"]["mode"] == "receipt_backed"
    assert fixture["lineage"]["spawn_count"] == 1
    assert fixture["lineage"]["parent_lane_ids"] == ["payload-857-receipt"]
    assert fixture["lineage"]["child_lane_ids"] == ["payload-857-red-1"]
    assert fixture["lineage"]["groups"] == [
        {
            "child_lane_ids": ["payload-857-red-1"],
            "collapsible": True,
            "expanded_by_default": True,
            "group_id": "lineage:payload-857-receipt",
            "lane_count": 2,
            "lane_ids": ["payload-857-receipt", "payload-857-red-1"],
            "parent_lane_id": "payload-857-receipt",
            "proof_mode": "receipt_backed_fixture",
            "spawn_receipt_ids": ["lineage-spawn-red-0-red-1"],
        }
    ]
    assert fixture["scoreboard"]["child_spawn_count"] == 1
    assert fixture["timeline"]["scroll_axis"] == "horizontal"
    assert fixture["timeline"]["playhead"]["current_x"] == 98
    assert fixture["timeline"]["playhead"]["animation_semantics"] == "receipt_replay_only"
    assert [frame["x"] for frame in fixture["timeline"]["playhead"]["keyframes"]] == [14, 33, 50, 58, 62, 66, 67, 76, 82, 86, 96, 98]
    assert [frame["elapsed_seconds"] for frame in fixture["timeline"]["playhead"]["keyframes"]] == [
        1.63961,
        111.566487,
        111.566487,
        113.636948,
        139.503599,
        139.503599,
        139.504352,
        139.503599,
        140.536077,
        139.503599,
        141.582963,
        142.60098,
    ]
    assert fixture["timeline"]["viewport"]["initial_min_x"] == 45
    assert fixture["timeline"]["viewport"]["initial_max_x"] == 100

    parent = lanes["payload-857-receipt"]
    child = lanes["payload-857-red-1"]
    useful_event = next(event for event in parent["events"] if event["kind"] == "useful")
    spawn_event = next(event for event in parent["events"] if event["kind"] == "handoff")
    assert useful_event["label_band"] == "upper"
    assert useful_event["marker_priority"] == 90
    assert useful_event["collision_group"] == "x05"
    assert spawn_event["label_band"] == "lower"
    assert spawn_event["marker_priority"] == 85
    assert spawn_event["collision_group"] == "x05"
    assert [event["x"] for event in parent["events"]] == [14, 33, 50, 58, 67, 82]
    assert parent["children"] == ["payload-857-red-1"]
    assert parent["lineageGroupId"] == "lineage:payload-857-receipt"
    assert parent["collapsible"] is True
    assert parent["expandedByDefault"] is True
    assert parent["terminal"] == "blocked_handoff"
    assert parent["runnerState"] == "blocked_handoff"
    assert parent["start_elapsed_seconds"] == 1.63961
    assert parent["end_elapsed_seconds"] == 140.536077
    assert parent["duration_elapsed_seconds"] == 138.896467
    assert [event["elapsed_seconds"] for event in parent["events"]] == [
        1.63961,
        111.566487,
        111.566487,
        113.636948,
        139.504352,
        140.536077,
    ]
    assert parent["activitySegments"][0] == {
        "end_elapsed_seconds": 1.63961,
        "end_x": 14,
        "id": "payload-857-receipt:segment:01",
            "label": "spawn / materialize",
            "phase": "materialize",
            "proof_mode": "receipt_backed_fixture",
            "source_event_id": None,
            "start_elapsed_seconds": 1.63961,
            "start_x": 7,
        }
    assert parent["replay"]["label"] == "REPLAY IN DOCKER"
    assert parent["replay"]["kind"] == "receipt_only"
    assert parent["replay"]["can_execute_now"] is False
    assert parent["replay"]["cta"] == {
        "disabled_reason": "No executable replay endpoint or command receipt is attached to this selected lane.",
        "icon": "container",
        "label": "REPLAY IN DOCKER",
        "proof_mode": "receipt_backed_fixture",
        "state": "receipt_only",
        "tooltip": "Judge replay receipt is available; live container execution is not attached.",
        "visible": True,
    }
    assert child["parentId"] == "payload-857-receipt"
    assert parent["cockpit"]["schema"] == "battle.lane_cockpit.v1"
    assert parent["cockpit"]["proof_label"] == "FIXTURE TRACE"
    assert parent["cockpit"]["selected_tau_exploit_subagent"]["actor_id"] == "payload-857-receipt"
    assert parent["cockpit"]["selected_tau_exploit_subagent"]["tau_subagent_id"] == "red-0"
    assert parent["cockpit"]["selected_tau_exploit_subagent"]["missing_tau_id"] is False
    assert list(parent["cockpit"]["public_trace"]) == [
        "observation",
        "hypothesis",
        "action",
        "result",
        "learned",
        "next_move",
    ]
    assert parent["cockpit"]["blue_outcome"]["forced_handoff"] is True
    assert parent["cockpit"]["blue_outcome"]["killed"] is False
    assert parent["cockpit"]["skills_tools"][0]["proof_label"] == "FIXTURE SKILL TRACE"
    assert parent["cockpit"]["memory_project_knowledge_events"] == []
    assert parent["cockpit"]["replay"]["cta"]["state"] == "receipt_only"
    assert child["lineageGroupId"] == "lineage:payload-857-receipt"
    assert child["collapsible"] is False
    assert child["expandedByDefault"] is True
    assert child["generation"] == 2
    assert child["cockpit"]["selected_tau_exploit_subagent"]["generation"] == 2
    assert child["cockpit"]["selected_tau_exploit_subagent"]["parent_lane_id"] == "payload-857-receipt"
    assert child["cockpit"]["current_turn"]["phase"] == "child_red_exploit"
    assert child["cockpit"]["public_trace"]["observation"] == "Spawned from parent lane payload-857-receipt at x=62."
    assert child["xStart"] == 62
    assert child["start_elapsed_seconds"] == 139.503599
    assert child["end_elapsed_seconds"] == 142.60098
    assert child["duration_elapsed_seconds"] == 3.097381
    assert all(event["x"] >= child["xStart"] for event in child["events"])
    assert [event["x"] for event in child["events"]] == [62, 66, 76, 86, 96, 98]
    assert [event["elapsed_seconds"] for event in child["events"]] == [
        139.503599,
        139.503599,
        139.503599,
        139.503599,
        141.582963,
        142.60098,
    ]
    assert child["activitySegments"][0]["start_x"] == 62
    assert child["activitySegments"][0]["start_elapsed_seconds"] == 139.503599
    assert child["activitySegments"][0]["end_elapsed_seconds"] == 139.503599
    assert child["activitySegments"][0]["phase"] == "handoff"
    assert all(segment["start_x"] >= child["xStart"] for segment in child["activitySegments"])
    assert "ZIP_SLIP_CONFIRMED" in child["inheritedContext"]
    assert fixture["lineage"]["spawns"][0]["spawn_elapsed_seconds"] == 113.636948
    assert fixture["lineage"]["spawns"][0]["child_start_elapsed_seconds"] == 139.503599
    assert fixture["lineage"]["spawns"][0]["spawn_duration_elapsed_seconds"] == 25.866651
    assert fixture["lineage"]["spawns"][0]["timing_source"] == "battle_control_plane_perf_counter"

    assert "tau.spawned_child" in event_types
    assert "blue.kill_confirmed" not in event_types
    assert "tau.fastest_crash" not in event_types
    assert "tau.promoted" not in event_types

    assert "A parent Red lane spawned a child Red lane from an explicit lineage receipt." in fixture["claims"]["proves"]
    assert "Child-spawn lineage." not in fixture["claims"]["does_not_prove"]
    assert fixture["ux_contract"]["receipt_backed_values"]["child_spawn_count"] == 1
    assert fixture["ux_contract"]["receipt_backed_values"]["child_spawn_requested"] is True
    assert fixture["ux_contract"]["receipt_backed_values"]["child_spawn_request_status"] == "PASS"
    assert fixture["ux_contract"]["receipt_backed_values"]["blue_blocked_lane_ids"] == [
        "payload-857-receipt",
        "payload-857-red-1",
    ]
    assert fixture["ux_contract"]["receipt_backed_values"]["lineage_group_count"] == 1
    assert fixture["ux_contract"]["receipt_backed_values"]["playhead_current_x"] == 98
    assert (
        "Use lane.replay.cta to render Docker replay button state; receipt_only means visible but not executable."
        in fixture["ux_contract"]["required_render_guards"]
    )
    assert (
        "Use lane.activitySegments for between-marker action labels; do not invent exploit phases client-side."
        in fixture["ux_contract"]["required_render_guards"]
    )
    assert (
        "Use lineage_request to explain requested-but-unproven child spawn; do not render children from lineage_request alone."
        in fixture["ux_contract"]["required_render_guards"]
    )
    assert "Fastest crash" in fixture["ux_contract"]["forbidden_inferences"]


def test_contract_validator_enforces_portable_json_schema(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)

    validate_fixture_schema(fixture, schema_path=SCHEMA_PATH)

    broken = json.loads(json.dumps(fixture))
    broken["timeline"]["scroll_axis"] = "vertical"
    with pytest.raises(ContractError, match="timeline.scroll_axis"):
        validate_fixture_schema(broken, schema_path=SCHEMA_PATH)


def test_handoff_summary_validator_enforces_portable_json_schema() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    validate_handoff_summary_schema(summary)

    broken = json.loads(json.dumps(summary))
    broken["canonical_scenario"]["public_entrypoint"] = "/api/session/verify"
    with pytest.raises(ContractError, match="canonical_scenario.public_entrypoint"):
        validate_handoff_summary_schema(broken)


def test_handoff_summary_schema_requires_playhead_keyframe_values() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    del summary["authoritative_sparse_fixture"]["timeline"]["playhead"]["keyframe_x_values"]

    with pytest.raises(ContractError, match="keyframe_x_values"):
        validate_handoff_summary_schema(summary)


def test_handoff_summary_validator_rejects_stale_proof_generation_command() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    summary["proof_generation_contract"]["canonical_command"] = (
        "cd skills/battle && ./run.sh arena-tau-public-only-proof battle-004 --out /tmp/battle-004-sparse"
    )

    with pytest.raises(ContractError, match="proof_generation_contract.canonical_command"):
        validate_handoff_summary(summary)


def test_handoff_summary_schema_requires_recommended_renderer_fixture() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    del summary["recommended_renderer_fixture"]

    with pytest.raises(ContractError, match="recommended_renderer_fixture"):
        validate_handoff_summary_schema(summary)


def test_handoff_summary_validator_rejects_stale_playhead_summary() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    summary["authoritative_sparse_fixture"]["timeline"]["playhead"]["current_x"] = 50

    with pytest.raises(ContractError, match="timeline.playhead.current_x must match fixture"):
        validate_handoff_summary(summary)


def test_handoff_summary_validator_rejects_stale_keyframe_summary() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    summary["authoritative_parent_spawn_fixture"]["timeline"]["playhead"]["keyframe_x_values"] = [14, 33, 50]

    with pytest.raises(ContractError, match="timeline.playhead.keyframe_x_values must match fixture"):
        validate_handoff_summary(summary)


def test_handoff_summary_validator_rejects_sparse_recommended_renderer_fixture() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    summary["recommended_renderer_fixture"]["fixture_key"] = "authoritative_sparse_fixture"
    summary["recommended_renderer_fixture"]["normalized_json"] = summary["authoritative_sparse_fixture"]["normalized_json"]

    with pytest.raises(ContractError, match="fixture_key must be authoritative_parent_spawn_fixture"):
        validate_handoff_summary(summary)


def test_handoff_summary_validator_rejects_stale_recommended_renderer_path() -> None:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    summary["recommended_renderer_fixture"]["normalized_json"] = summary["authoritative_sparse_fixture"]["normalized_json"]

    with pytest.raises(ContractError, match="recommended_renderer_fixture.normalized_json must match"):
        validate_handoff_summary(summary)


def test_adapter_fails_closed_when_lineage_receipt_is_missing_or_invalid(tmp_path: Path) -> None:
    proof_dir = _write_tau_public_only_proof(tmp_path, include_lineage=True, invalid_lineage=True)

    fixture = adapt_proof_dir(proof_dir=proof_dir, battle_id="battle-004")
    validate_fixture(fixture)
    _validate_json_schema(fixture)

    lanes = {lane["id"]: lane for lane in fixture["lanes"]}
    event_types = {event["event_type"] for event in fixture["events"]}

    assert fixture["lineage"]["mode"] == "missing"
    assert fixture["lineage_request"]["requested"] is True
    assert fixture["lineage_request"]["status"] == "NOT_PROVEN"
    assert fixture["lineage_request"]["receipt"] == "lineage-receipts.json"
    assert fixture["lineage"]["spawn_count"] == 0
    assert fixture["lineage"]["groups"] == []
    assert fixture["scoreboard"]["child_spawn_count"] == 0
    assert "tau.spawned_child" not in event_types

    assert "children" not in lanes["payload-857-receipt"]
    assert "parentId" not in lanes["payload-857-red-1"]
    assert lanes["payload-857-receipt"]["terminal"] == "blocked"

    assert "Child-spawn lineage." in fixture["claims"]["does_not_prove"]
    assert fixture["ux_contract"]["receipt_backed_values"]["child_spawn_count"] == 0
    assert fixture["ux_contract"]["receipt_backed_values"]["child_spawn_requested"] is True
    assert fixture["ux_contract"]["receipt_backed_values"]["child_spawn_request_status"] == "NOT_PROVEN"
    assert (
        "Do not render child lanes unless lineage.spawn_count > 0 and child lane ids exist in lanes[]."
        in fixture["ux_contract"]["required_render_guards"]
    )


def test_validator_rejects_method_prefixed_entrypoint(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["scenario"]["public_entrypoint"] = "POST /api/import-zip"

    with pytest.raises(ContractError, match="public_entrypoint"):
        validate_fixture(fixture)


def test_validator_rejects_spectator_shell_target_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["spectator_shell"]["facts"][2]["value"] = "POST /api/session/verify"

    with pytest.raises(ContractError, match="spectator_shell Target fact"):
        validate_fixture(fixture)


def test_validator_rejects_renderer_binding_path_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["renderer_binding_contract"]["moving_playhead"]["keyframes"] = "timeline.keyframes[]"

    with pytest.raises(ContractError, match="renderer_binding_contract.moving_playhead.keyframes"):
        validate_fixture(fixture)


def test_validator_rejects_lineage_request_pass_without_spawn(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=False)
    fixture["lineage_request"] = {
        "schema": "battle.lineage_request.v1",
        "requested": True,
        "mode": "spawn_red_child_after_blue_success",
        "condition": "parent lane must have a Judge BLUE_SUCCESS attempt before Tau child spawn is requested",
        "status": "PASS",
        "receipt": "lineage-receipts.json",
        "proof_mode": "receipt_backed_fixture",
    }
    fixture["ux_contract"]["receipt_backed_values"]["child_spawn_requested"] = True
    fixture["ux_contract"]["receipt_backed_values"]["child_spawn_request_status"] = "PASS"

    with pytest.raises(ContractError, match="lineage_request PASS requires positive"):
        validate_fixture(fixture)


def test_validator_rejects_child_lane_without_lineage(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=False)
    parent = next(lane for lane in fixture["lanes"] if lane["id"] == "payload-857-receipt")
    child = next(lane for lane in fixture["lanes"] if lane["id"] == "payload-857-red-1")
    parent["children"] = ["payload-857-red-1"]
    child["parentId"] = "payload-857-receipt"

    with pytest.raises(ContractError, match="without lineage"):
        validate_fixture(fixture)


def test_validator_rejects_spawned_child_event_without_lineage(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=False)
    fixture["events"].append(
        {
            "id": "unsafe-spawn",
            "ts": fixture["generated_at"],
            "battle_id": "battle-004",
            "team": "red",
            "actor_id": "payload-857-receipt",
            "actor_kind": "tau_exploit_subagent",
            "event_type": "tau.spawned_child",
            "summary": "Unsafe invented child event.",
            "proof_mode": "receipt_backed_fixture",
        }
    )
    fixture["ux_contract"]["receipt_backed_values"]["event_count"] = len(fixture["events"])

    with pytest.raises(ContractError, match="tau.spawned_child requires"):
        validate_fixture(fixture)


def test_validator_rejects_blue_block_without_blue_success_pair(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=False)
    block_event = next(event for event in fixture["events"] if event["event_type"] == "blue.blocked_red")
    block_event["target_actor_ids"] = ["payload-not-in-scoreboard"]

    with pytest.raises(ContractError, match="BLUE_SUCCESS pair"):
        validate_fixture(fixture)


def test_validator_rejects_executable_replay_without_endpoint_or_receipt(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    replay = fixture["lanes"][0]["replay"]
    replay["can_execute_now"] = True
    replay["cta"]["state"] = "executable"
    replay["cta"]["disabled_reason"] = None
    replay["endpoint"] = None
    replay["command_receipt_id"] = None

    with pytest.raises(ContractError, match="executable replay requires"):
        validate_fixture(fixture)


def test_validator_rejects_missing_replay_cta(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    del fixture["lanes"][0]["replay"]["cta"]

    with pytest.raises(ContractError, match="replay.cta"):
        validate_fixture(fixture)


def test_validator_rejects_receipt_only_replay_with_executable_cta(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    replay = fixture["lanes"][0]["replay"]
    replay["can_execute_now"] = False
    replay["cta"]["state"] = "executable"
    replay["cta"]["disabled_reason"] = None

    with pytest.raises(ContractError, match="receipt_only"):
        validate_fixture(fixture)


def test_validator_rejects_cockpit_replay_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["lanes"][0]["cockpit"]["replay"]["receipt_id"] = "different-judge-receipt"

    with pytest.raises(ContractError, match="cockpit.replay.receipt_id"):
        validate_fixture(fixture)


def test_validator_rejects_lane_fastest_crash_without_receipt_event(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["lanes"][0]["terminal"] = "fastest_crash"
    fixture["lanes"][0]["runnerState"] = "fastest_crash"

    with pytest.raises(ContractError, match="fastest_crash requires"):
        validate_fixture(fixture)


def test_validator_rejects_leaderboard_promotion_without_receipt_event(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["leaderboard"][0]["status"] = "promoted"

    with pytest.raises(ContractError, match="status=promoted requires"):
        validate_fixture(fixture)


def test_validator_rejects_live_stream_clock_without_receipts(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["battle_clock"]["mode"] = "live_stream"

    with pytest.raises(ContractError, match="battle_clock.mode"):
        validate_fixture(fixture)


def test_validator_rejects_inconsistent_remaining_time(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["battle_clock"]["allotted_seconds"] = 240
    fixture["battle_clock"]["elapsed_seconds"] = 120
    fixture["battle_clock"]["remaining_seconds"] = 200

    with pytest.raises(ContractError, match="remaining_seconds"):
        validate_fixture(fixture)


def test_validator_rejects_timeline_count_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["timeline"]["event_count"] = len(fixture["events"]) + 1

    with pytest.raises(ContractError, match="timeline.event_count"):
        validate_fixture(fixture)


def test_validator_rejects_unsorted_event_order(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["events"][0]["order_index"] = 99

    with pytest.raises(ContractError, match="order_index"):
        validate_fixture(fixture)


def test_validator_rejects_unsorted_lane_event_order(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    parent = next(lane for lane in fixture["lanes"] if lane["id"] == "payload-857-receipt")
    parent["events"][0], parent["events"][1] = parent["events"][1], parent["events"][0]

    with pytest.raises(ContractError, match="events must be sorted by order_index"):
        validate_fixture(fixture)


def test_validator_rejects_missing_timeline_playhead(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    del fixture["timeline"]["playhead"]

    with pytest.raises(ContractError, match="timeline.playhead"):
        validate_fixture(fixture)


def test_validator_rejects_unsorted_playhead_keyframes(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["timeline"]["playhead"]["keyframes"][0]["x"] = 99

    with pytest.raises(ContractError, match="keyframes"):
        validate_fixture(fixture)


def test_validator_rejects_playhead_keyframe_not_backed_by_lane_event(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["timeline"]["playhead"]["keyframes"][0]["event_id"] = "missing-event"

    with pytest.raises(ContractError, match="keyframes\\[\\]\\.event_id must reference a lane event"):
        validate_fixture(fixture)


def test_validator_rejects_playhead_current_x_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["timeline"]["playhead"]["current_x"] = 97

    with pytest.raises(ContractError, match="current_x must equal the final keyframe x"):
        validate_fixture(fixture)


def test_validator_rejects_missing_timeline_viewport(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    del fixture["timeline"]["viewport"]

    with pytest.raises(ContractError, match="timeline.viewport"):
        validate_fixture(fixture)


def test_validator_rejects_lineage_group_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["lineage"]["groups"][0]["child_lane_ids"] = []

    with pytest.raises(ContractError, match="lane_ids"):
        validate_fixture(fixture)


def test_validator_rejects_missing_lane_event_layout_metadata(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    del fixture["lanes"][0]["events"][0]["label_band"]

    with pytest.raises(ContractError, match="label_band"):
        validate_fixture(fixture)


def test_validator_rejects_missing_lane_cockpit(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    del fixture["lanes"][0]["cockpit"]

    with pytest.raises(ContractError, match="cockpit"):
        validate_fixture(fixture)


def test_validator_rejects_child_lane_event_before_spawn(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    child = next(lane for lane in fixture["lanes"] if lane.get("parentId") == "payload-857-receipt")
    child["events"][1]["x"] = child["xStart"] - 1

    with pytest.raises(ContractError, match="before lane xStart"):
        validate_fixture(fixture)


def test_validator_rejects_lane_event_after_lane_end(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    parent = next(lane for lane in fixture["lanes"] if lane["id"] == "payload-857-receipt")
    parent["events"][0]["x"] = parent["xEnd"] + 1

    with pytest.raises(ContractError, match="after lane xEnd"):
        validate_fixture(fixture)


def test_validator_rejects_child_activity_segment_before_spawn(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    child = next(lane for lane in fixture["lanes"] if lane.get("parentId") == "payload-857-receipt")
    child["activitySegments"][0]["start_x"] = child["xStart"] - 1

    with pytest.raises(ContractError, match="activity segment"):
        validate_fixture(fixture)


def test_validator_rejects_missing_authoritative_field_metadata(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    del fixture["ux_contract"]["authoritative_fields"]["lineage"]

    with pytest.raises(ContractError, match="authoritative_fields missing"):
        validate_fixture(fixture)


def test_validator_rejects_missing_required_render_guard(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["ux_contract"]["required_render_guards"] = [
        guard
        for guard in fixture["ux_contract"]["required_render_guards"]
        if not guard.startswith("Do not render child lanes")
    ]

    with pytest.raises(ContractError, match="required_render_guards missing"):
        validate_fixture(fixture)


def test_validator_rejects_missing_forbidden_inference(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, include_lineage=True)
    fixture["ux_contract"]["forbidden_inferences"] = [
        item for item in fixture["ux_contract"]["forbidden_inferences"] if item != "Fastest crash"
    ]

    with pytest.raises(ContractError, match="forbidden_inferences missing"):
        validate_fixture(fixture)


def test_generate_fixture_files_writes_only_validated_json_and_ts(tmp_path: Path) -> None:
    proof_dir = _write_tau_public_only_proof(tmp_path, include_lineage=True)
    out = tmp_path / "battle-004.generated.json"
    ts_out = tmp_path / "battle-data.generated.ts"

    fixture = generate_fixture_files(proof_dir=proof_dir, battle_id="battle-004", out=out, ts_out=ts_out)

    assert out.exists()
    assert ts_out.exists()
    written = json.loads(out.read_text(encoding="utf-8"))
    validate_fixture(written)
    assert written == fixture
    ts_text = ts_out.read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in ts_text
    assert "generatedBattleFixture" in ts_text
    assert "payload-857-red-1" in ts_text


def test_generate_fixture_files_refuses_to_write_when_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proof_dir = _write_tau_public_only_proof(tmp_path, include_lineage=True)
    out = tmp_path / "invalid-generated.json"
    ts_out = tmp_path / "invalid-generated.ts"

    def reject_fixture(_: dict[str, Any]) -> None:
        raise ContractError("forced invalid fixture")

    monkeypatch.setattr(battle_event_adapter, "validate_fixture", reject_fixture)

    with pytest.raises(typer.BadParameter, match="forced invalid fixture"):
        generate_fixture_files(proof_dir=proof_dir, battle_id="battle-004", out=out, ts_out=ts_out)

    assert not out.exists()
    assert not ts_out.exists()


def _fixture(tmp_path: Path, *, include_lineage: bool) -> dict[str, Any]:
    proof_dir = _write_tau_public_only_proof(tmp_path, include_lineage=include_lineage)
    fixture = adapt_proof_dir(proof_dir=proof_dir, battle_id="battle-004")
    validate_fixture(fixture)
    return fixture


def test_tau_public_only_blocked_workers_expose_scillm_auth_blocker(tmp_path: Path) -> None:
    proof_dir = _write_tau_public_only_auth_blocked_proof(tmp_path)
    fixture = adapt_proof_dir(proof_dir=proof_dir, battle_id="battle-004")
    validate_fixture(fixture)

    assert fixture["status"] == "INSUFFICIENT_EVIDENCE"
    assert fixture["lineage_request"]["requested"] is True
    assert fixture["lineage_request"]["status"] == "NOT_PROVEN"
    assert fixture["lineage"]["spawn_count"] == 0
    assert fixture["scoreboard"]["red_materialized_count"] == 0
    assert fixture["scoreboard"]["blue_materialized_count"] == 0
    assert fixture["ux_contract"]["receipt_backed_values"]["proof_blocker_count"] == 2

    proof_blockers = fixture["proof_blockers"]
    assert len(proof_blockers) == 2
    assert proof_blockers[0]["schema"] == "battle.proof_blocker.v1"
    assert proof_blockers[0]["team"] == "red"
    assert proof_blockers[0]["worker_id"] == "red-0"
    assert proof_blockers[0]["lane_id"] == "payload-857-receipt"
    assert proof_blockers[0]["action_id"] is None
    assert proof_blockers[0]["receipt_id"] == "red-0-scillm-call-receipt"
    assert proof_blockers[0]["blocker"]["kind"] == "provider_auth_error"
    assert proof_blockers[1]["team"] == "blue"
    assert proof_blockers[1]["worker_id"] == "blue-0"
    assert proof_blockers[1]["action_id"] == "blue-receipt-backed-patch"

    lane = fixture["lanes"][0]
    assert "provider_auth_error: All groups exhausted for model='gpt-5.5'" in lane["stdout"][0]
    red_event = next(event for event in fixture["events"] if event["id"] == "red-0-red-blocked")
    assert red_event["event_type"] == "tau.artifact_blocked"
    assert "provider_auth_error" in red_event["summary"]
    blocker = red_event["evidence"]["blocker"]
    assert blocker == {
        "schema": "battle.worker_blocker.v1",
        "kind": "provider_auth_error",
        "message": "All groups exhausted for model='gpt-5.5' (chain=['gpt-5.5']): No Codex OAuth token available.",
        "http_status": 401,
        "provider": "codex-oauth",
        "provider_auth_status": "not_configured_or_expired",
        "model_requested": "gpt-5.5",
        "project_agent_message": "Run `codex login` on the host, ensure ~/.codex/auth.json is mounted into the scillm proxy, then check GET /v1/scillm/auth before retrying.",
        "receipt_path": str(proof_dir / "tau-live" / "red" / "scillm-call-receipt.json"),
        "proof_mode": "receipt_backed_fixture",
    }
    scillm_receipts = [receipt for receipt in fixture["receipts"] if receipt["receipt_type"] == "scillm_call"]
    assert {receipt["receipt_id"] for receipt in scillm_receipts} == {"red-0-scillm-call-receipt", "blue-0-scillm-call-receipt"}


def _validate_json_schema(fixture: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(fixture), key=lambda error: list(error.path))
    assert errors == []


def _write_tau_public_only_proof(tmp_path: Path, *, include_lineage: bool, invalid_lineage: bool = False) -> Path:
    proof_dir = tmp_path / "proof"
    run_id = "test-run-001"
    generated_at = "2026-07-04T21:34:55Z"

    _write_json(
        proof_dir / "run-receipt.json",
        {
            "battle_id": "battle-004",
            "run_id": run_id,
            "created_at": generated_at,
            "status": "PASS",
            "verdict": "BLUE_SUCCESS",
            "mocked": False,
            "live": "brave_search_docker_arena_oracle_tau_harness",
            **(
                {
                    "lineage_request": {
                        "requested": True,
                        "mode": "spawn_red_child_after_blue_success",
                        "condition": "parent lane must have a Judge BLUE_SUCCESS attempt before Tau child spawn is requested",
                        "status": "NOT_PROVEN" if invalid_lineage else "PASS",
                        "receipt": "lineage-receipts.json",
                    }
                }
                if include_lineage
                else {}
            ),
        },
    )
    _write_json(
        proof_dir / "arena" / "scenario.json",
        {
            "battle_id": "battle-004",
            "scenario_id": "arena-zip-slip-import-001",
            "title": "Archive import path traversal",
            "public_entrypoint": "POST /api/import-zip",
            "hidden_vulnerability_family": "Zip Slip path traversal",
            "cwe": "CWE-22",
            "difficulty": "medium",
            "target_language": "python",
        },
    )
    _write_json(proof_dir / "visibility-validation.json", {"status": "PASS"})
    _write_json(proof_dir / "arena" / "arena-receipt.json", {"status": "PASS"})
    _write_json(
        proof_dir / "tau-live" / "manifest.json",
        {
            "battle_id": "battle-004",
            "run_id": run_id,
            "status": "PASS",
            "mocked": False,
            "handoff_topology": "bounded_worker_matrix",
            "timing": {
                "initial_tau_started_elapsed_seconds": 1.63961,
                "initial_tau_ended_elapsed_seconds": 111.566487,
            },
            "teams": [
                {
                    "team": "red",
                    "worker_id": "red-0",
                    "lane_id": "payload-857-receipt",
                    "status": "PASS",
                    "subagent_receipt": "tau-live/red/red-0/tau-subagent-receipt.json",
                    "materialized": {"status": "PASS", "path": "tau-live/red/red-0/exploit.py"},
                },
                {
                    "team": "red",
                    "worker_id": "red-1",
                    "lane_id": "payload-857-red-1",
                    "status": "PASS",
                    "subagent_receipt": "tau-live/red/red-1/tau-subagent-receipt.json",
                    "materialized": {"status": "PASS", "path": "tau-live/red/red-1/exploit.py"},
                },
                {
                    "team": "blue",
                    "worker_id": "blue-0",
                    "status": "PASS",
                    "subagent_receipt": "tau-live/blue/blue-0/tau-subagent-receipt.json",
                    "materialized": {"status": "PASS", "path": "tau-live/blue/blue-0/patch.py"},
                },
            ],
        },
    )
    attempts = [
        _attempt("red-0", "payload-857-receipt", "blue-0"),
        _attempt("red-1", "payload-857-red-1", "blue-0"),
    ]
    attempts[0].update(
        {
            "started_elapsed_seconds": 139.504352,
            "ended_elapsed_seconds": 140.536077,
            "duration_elapsed_seconds": 1.031725,
            "timing_source": "judge_attempt_receipt",
        }
    )
    attempts[1].update(
        {
            "started_elapsed_seconds": 141.582963,
            "ended_elapsed_seconds": 142.60098,
            "duration_elapsed_seconds": 1.018017,
            "timing_source": "judge_attempt_receipt",
        }
    )
    _write_json(
        proof_dir / "judge" / "judge-receipt.json",
        {
            "status": "PASS",
            "verdict": "BLUE_SUCCESS",
            "attempts": attempts,
        },
    )
    _write_json(
        proof_dir / "scoreboard.json",
        {
            "status": "PASS",
            "verdict": "BLUE_SUCCESS",
            "red_score": 6,
            "blue_score": 7.2,
            "tdsr": 1.0,
            "asc": 1.0,
            "requested_workers": {"red": 2, "blue": 1},
            "red_materialized_count": 2,
            "blue_materialized_count": 1,
            "judged_pair_count": 2,
            "blue_success_count": 2,
            "allotted_seconds": 240,
            "elapsed_seconds": 184.760449,
            "remaining_seconds": 55.239551,
            "per_pair": attempts,
        },
    )
    if include_lineage:
        child_lane_id = "payload-857-missing-child" if invalid_lineage else "payload-857-red-1"
        _write_json(
            proof_dir / "lineage-receipts.json",
            {
                "status": "PASS",
                "spawns": [
                    {
                        "status": "PASS",
                        "receipt_id": "lineage-spawn-red-0-red-1",
                        "receipt_path": "lineage-receipts.json",
                        "parent_lane_id": "payload-857-receipt",
                        "child_lane_id": child_lane_id,
                        "parent_worker_id": "red-0",
                        "child_worker_id": "red-1",
                        "parent_tau_subagent_id": "tau-red-0",
                        "child_tau_subagent_id": "tau-red-1",
                        "child_payload_id": "payload-857-red-1",
                        "x": 58,
                        "child_x_start": 62,
                        "spawn_elapsed_seconds": 113.636948,
                        "child_start_elapsed_seconds": 139.503599,
                        "spawn_duration_elapsed_seconds": 25.866651,
                        "timing_source": "battle_control_plane_perf_counter",
                        "generation": 2,
                        "label": "SPAWN CHILD",
                        "time_label": "handoff",
                        "inherited_context": ["ZIP_SLIP_CONFIRMED", "Parent blocked by BLUE_SUCCESS"],
                        "leased_task": "Continue Red exploit from retained parent signal.",
                        "goal": "Spawn child Red lane from receipt-backed useful signal.",
                    }
                ],
            },
        )
    return proof_dir


def _write_tau_public_only_auth_blocked_proof(tmp_path: Path) -> Path:
    proof_dir = tmp_path / "auth-blocked-proof"
    run_id = "test-auth-blocked-001"
    generated_at = "2026-07-05T11:12:24Z"
    scillm_error_body = {
        "error": {
            "message": "All groups exhausted for model='gpt-5.5' (chain=['gpt-5.5']): No Codex OAuth token available.",
            "type": "provider_auth_error",
            "code": 401,
            "details": {
                "provider": "codex-oauth",
                "provider_auth_status": "not_configured_or_expired",
                "model_requested": "gpt-5.5",
                "project_agent_message": "Run `codex login` on the host, ensure ~/.codex/auth.json is mounted into the scillm proxy, then check GET /v1/scillm/auth before retrying.",
                "error_type": "provider_auth_error",
            },
        }
    }

    _write_json(
        proof_dir / "run-receipt.json",
        {
            "battle_id": "battle-004",
            "run_id": run_id,
            "created_at": generated_at,
            "status": "INSUFFICIENT_EVIDENCE",
            "verdict": "INSUFFICIENT_EVIDENCE",
            "mocked": False,
            "live": "brave_search_docker_arena_oracle_tau_harness",
            "lineage_request": {
                "requested": True,
                "mode": "spawn_red_child_after_blue_success",
                "condition": "parent lane must have a Judge BLUE_SUCCESS attempt before Tau child spawn is requested",
                "status": "NOT_PROVEN",
                "receipt": None,
            },
        },
    )
    _write_json(
        proof_dir / "arena" / "scenario.json",
        {
            "battle_id": "battle-004",
            "scenario_id": "arena-zip-slip-import-001",
            "title": "Archive import path traversal",
            "public_entrypoint": "POST /api/import-zip",
            "hidden_vulnerability_family": "Zip Slip path traversal",
            "cwe": "CWE-22",
            "difficulty": "medium",
            "target_language": "python",
        },
    )
    _write_json(proof_dir / "visibility-validation.json", {"status": "PASS"})
    _write_json(proof_dir / "arena" / "arena-receipt.json", {"status": "PASS"})
    _write_json(
        proof_dir / "tau-live" / "manifest.json",
        {
            "battle_id": "battle-004",
            "run_id": run_id,
            "status": "BLOCKED",
            "mocked": False,
            "handoff_topology": "bounded_worker_matrix",
            "teams": [
                {
                    "team": "red",
                    "worker_id": "red-0",
                    "lane_id": "payload-857-receipt",
                    "status": "BLOCKED",
                    "subagent_receipt": "tau-live/red/tau-subagent-receipt.json",
                    "scillm_call": "tau-live/red/scillm-call-receipt.json",
                    "materialized_artifact": {
                        "status": "BLOCKED",
                        "path": None,
                        "reason": "scillm_response_not_json_object",
                    },
                },
                {
                    "team": "blue",
                    "worker_id": "blue-0",
                    "status": "BLOCKED",
                    "subagent_receipt": "tau-live/blue/tau-subagent-receipt.json",
                    "scillm_call": "tau-live/blue/scillm-call-receipt.json",
                    "materialized_artifact": {
                        "status": "BLOCKED",
                        "path": None,
                        "reason": "scillm_response_not_json_object",
                    },
                },
            ],
        },
    )
    for team in ("red", "blue"):
        _write_json(
            proof_dir / "tau-live" / team / "scillm-call-receipt.json",
            {
                "schema": "tau.scillm_call_receipt.v1",
                "status": "BLOCKED",
                "parse_status": "BLOCKED",
                "http_status": 401,
                "model": "gpt-5.5",
                "surface": "scillm.chat_completions",
                "team": team,
                "mocked": False,
                "live": True,
                "error": "HTTP Error 401: Unauthorized",
                "attempts": [
                    {
                        "kind": "initial",
                        "transport_status": "HTTP_ERROR",
                        "http_status": 401,
                        "parse_status": "BLOCKED",
                        "raw_body_excerpt": json.dumps(scillm_error_body, sort_keys=True),
                    }
                ],
            },
        )
    _write_json(
        proof_dir / "judge" / "judge-receipt.json",
        {
            "schema": "battle.arena_tau_public_only_judge_receipt.v1",
            "status": "INSUFFICIENT_EVIDENCE",
            "verdict": "INSUFFICIENT_EVIDENCE",
            "reason": "missing_tau_executable_artifacts",
            "attempts": [],
            "red_artifact_count": 0,
            "blue_artifact_count": 0,
        },
    )
    _write_json(
        proof_dir / "scoreboard.json",
        {
            "schema": "battle.arena_tau_public_only_scoreboard.v1",
            "status": "INSUFFICIENT_EVIDENCE",
            "verdict": "INSUFFICIENT_EVIDENCE",
            "red_score": 0,
            "blue_score": 0,
            "tdsr": 0,
            "asc": 0,
            "red_worker_count": 1,
            "blue_worker_count": 1,
            "red_materialized_count": 0,
            "blue_materialized_count": 0,
            "judged_pair_count": 0,
            "blue_success_count": 0,
            "allotted_seconds": 240,
            "elapsed_seconds": 1.5,
            "remaining_seconds": 238.5,
            "attempts": [],
        },
    )
    return proof_dir


def _attempt(red_worker_id: str, red_lane_id: str, blue_worker_id: str) -> dict[str, Any]:
    return {
        "pair_id": f"{red_worker_id}__{blue_worker_id}",
        "status": "PASS",
        "verdict": "BLUE_SUCCESS",
        "red_worker_id": red_worker_id,
        "red_lane_id": red_lane_id,
        "blue_worker_id": blue_worker_id,
        "blue_action_id": "blue-receipt-backed-patch",
        "exploit_confirmed_before_patch": True,
        "exploit_blocked_after_patch": True,
        "exploit_still_succeeds_after_patch": False,
        "functionality_preserved": True,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
