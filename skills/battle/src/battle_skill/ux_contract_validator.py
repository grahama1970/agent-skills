"""Validate the normalized Battle UX JSON contract.

This module is intentionally independent of React. It checks that receipt-backed
Battle data gives the UX explicit values and guardrails instead of leaving the
renderer to infer lineage, replay state, or terminal outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.normalized_ux_fixture.v1.schema.json"
DEFAULT_HANDOFF_SUMMARY_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "battle.backend_ux_json_contract_summary.v1.schema.json"
)
DEFAULT_RENDERER_FIXTURE_RESOLUTION_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "battle.ux_renderer_fixture_resolution.v1.schema.json"
)
DEFAULT_RENDERER_BUNDLE_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.ux_renderer_bundle.v1.schema.json"
DEFAULT_RENDERER_VALUES_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.ux_renderer_values.v1.schema.json"
DEFAULT_UX_DATA_CONTRACT_INDEX_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.ux_data_contract_index.v1.schema.json"
DEFAULT_TRANSPORT_MANIFEST_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.transport_manifest.v1.schema.json"
DEFAULT_LIVE_EVENT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.live_event.v1.schema.json"
DEFAULT_SNAPSHOT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "battle.snapshot.v1.schema.json"
DEFAULT_SEMANTIC_OUTCOME_MATRIX_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "battle.semantic_outcome_matrix.v1.schema.json"
)
BATTLE_SKILL_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SCHEMA = "battle.normalized_ux_fixture.v1"
EXPECTED_UX_CONTRACT_SCHEMA = "battle.ux_contract.v1"
EXPECTED_PROOF_MODE = "receipt_backed_fixture"
EXPECTED_HANDOFF_SUMMARY_SCHEMA = "battle.backend_ux_json_contract_summary.v1"
EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA = "battle.ux_renderer_fixture_resolution.v1"
EXPECTED_RENDERER_BUNDLE_SCHEMA = "battle.ux_renderer_bundle.v1"
EXPECTED_RENDERER_VALUES_SCHEMA = "battle.ux_renderer_values.v1"
EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA = "battle.ux_data_contract_index.v1"
EXPECTED_TRANSPORT_MANIFEST_SCHEMA = "battle.transport_manifest.v1"
EXPECTED_LIVE_EVENT_SCHEMA = "battle.live_event.v1"
EXPECTED_SNAPSHOT_SCHEMA = "battle.snapshot.v1"
EXPECTED_SEMANTIC_OUTCOME_MATRIX_SCHEMA = "battle.semantic_outcome_matrix.v1"
EXPECTED_CANONICAL_SCENARIO = {
    "battle_id": "battle-004",
    "public_entrypoint": "/api/import-zip",
    "cwe": "CWE-22",
    "hidden_vulnerability_family": "Zip Slip path traversal",
}
EXPECTED_GOAL_SOURCE_PATH = "/home/graham/workspace/experiments/agent-skills/skills/battle/GOAL.md"
EXPECTED_HANDOFF_SUMMARY_PATH = "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-ux-json-contract-summary.json"
EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH = (
    "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-renderer-fixture-resolution.json"
)
EXPECTED_RENDERER_FIXTURE_RESOLUTION_COMMAND = (
    "cd skills/battle && ./run.sh validate-ux-renderer-fixture-resolution local/battle-004-renderer-fixture-resolution.json"
)
EXPECTED_RENDERER_BUNDLE_PATH = "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-renderer-bundle.json"
EXPECTED_RENDERER_BUNDLE_COMMAND = "cd skills/battle && ./run.sh validate-ux-renderer-bundle local/battle-004-renderer-bundle.json"
EXPECTED_RENDERER_VALUES_PATH = "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-ux-renderer-values.json"
EXPECTED_RENDERER_VALUES_COMMAND = "cd skills/battle && ./run.sh validate-ux-renderer-values local/battle-004-ux-renderer-values.json"
EXPECTED_UX_DATA_CONTRACT_INDEX_PATH = "/home/graham/workspace/experiments/agent-skills/skills/battle/local/battle-004-ux-data-contract-index.json"
EXPECTED_UX_DATA_CONTRACT_INDEX_COMMAND = (
    "cd skills/battle && ./run.sh validate-ux-data-contract-index local/battle-004-ux-data-contract-index.json"
)
EXPECTED_PARENT_SPAWN_PROOF_COMMAND = (
    "cd skills/battle && ./run.sh arena-parent-spawn-proof battle-004 --out /tmp/battle-004-parent-spawn --red-workers 2 --blue-workers 2"
)
REQUIRED_GOAL_SOURCE_PHRASES = {
    "Current Battle-agent responsibility:",
    "generate Arena/Tau/Judge proof receipts for canonical BATTLE-004;",
    "normalize those receipts into fail-closed JSON for the UX renderer;",
    "provide timeline/playhead/viewport values through `timeline`;",
    "provide parent/child spawn and collapse values through `lineage` and lane",
    "provide Docker replay button state through lane `replay.cta`.",
    "Do not invent UI-only density.",
    "BATTLE-004",
    "/api/import-zip",
    "CWE-22",
    "Zip Slip",
}
REQUIRED_SUMMARY_VALIDATION_COMMANDS = {
    "cd skills/battle && ./run.sh validate-ux-handoff-summary local/battle-004-ux-json-contract-summary.json",
    "cd skills/battle && ./run.sh resolve-ux-renderer-fixture local/battle-004-ux-json-contract-summary.json",
    EXPECTED_RENDERER_FIXTURE_RESOLUTION_COMMAND,
    EXPECTED_RENDERER_BUNDLE_COMMAND,
    EXPECTED_RENDERER_VALUES_COMMAND,
    EXPECTED_UX_DATA_CONTRACT_INDEX_COMMAND,
    "cd skills/battle && ./run.sh validate-ux-contract local/battle-004-parent-spawn.normalized.json",
    "cd skills/battle && ./run.sh validate-ux-contract local/battle-004-sparse.normalized.json",
}
HANDOFF_SUMMARY_FIXTURE_KEYS = (
    "authoritative_parent_spawn_fixture",
    "authoritative_sparse_fixture",
)
RECOMMENDED_RENDERER_FIXTURE_KEY = "authoritative_parent_spawn_fixture"
REQUIRED_AUTHORITATIVE_FIELDS = {
    "scenario",
    "battle_clock",
    "timeline",
    "lineage_request",
    "lineage",
    "spectator_shell",
    "lanes",
    "events",
    "proof_blockers",
    "bluePatchActions",
    "scoreboard",
    "receipts",
    "claims",
}
EXPECTED_RENDERER_BINDING_PATHS = {
    "battle_shell": {
        "title": "spectator_shell.battle_title",
        "subtitle": "spectator_shell.subtitle",
        "mode_badge": "spectator_shell.mode_badge",
        "truth_label": "spectator_shell.truth_label",
        "fact_chips": "spectator_shell.facts[]",
        "red_score": "spectator_shell.score.red.value",
        "blue_score": "spectator_shell.score.blue.value",
        "score_verdict": "spectator_shell.score.verdict",
        "receipt_ticker": "spectator_shell.event_ticker",
    },
    "round_time": {
        "display_value": "spectator_shell.facts[label=Round time].value",
        "clock_source": "battle_clock",
        "elapsed_seconds": "battle_clock.elapsed_seconds",
        "allotted_seconds": "battle_clock.allotted_seconds",
        "remaining_seconds": "battle_clock.remaining_seconds",
    },
    "scrollable_timeline": {
        "mode": "timeline.mode",
        "supports_pan": "timeline.supports_pan",
        "supports_zoom": "timeline.supports_zoom",
        "viewport": "timeline.viewport",
        "lane_count": "timeline.lane_count",
        "event_count": "timeline.event_count",
    },
    "moving_playhead": {
        "current_x": "timeline.playhead.current_x",
        "elapsed_seconds": "timeline.playhead.elapsed_seconds",
        "keyframes": "timeline.playhead.keyframes[]",
        "animation_semantics": "timeline.playhead.animation_semantics",
    },
    "elapsed_timeline_axis": {
        "model": "timeline_elapsed_axis_model",
        "x_axis_mode": "timeline_elapsed_axis_model.x_axis_mode",
        "x_position_is_elapsed_time": "timeline_elapsed_axis_model.x_position_is_elapsed_time",
        "keyframes": "timeline_elapsed_axis_model.keyframes[]",
        "elapsed_x": "timeline_elapsed_axis_model.keyframes[].x",
        "legacy_receipt_order_x": "timeline_elapsed_axis_model.keyframes[].receipt_order_x",
        "playhead": "timeline_elapsed_axis_model.playhead",
        "lane_start_model": "timeline_lane_start_model",
        "lane_start_elapsed_x": "timeline_lane_start_model.starts[].elapsed_line_must_start_at_x",
        "lane_end_elapsed_x": "timeline_lane_start_model.starts[].elapsed_line_end_x",
        "activity_model": "lane_activity_timeline_model",
        "activity_segment_elapsed_start_x": "lane_activity_timeline_model.lanes[].segments[].elapsed_start_x",
        "activity_segment_elapsed_end_x": "lane_activity_timeline_model.lanes[].segments[].elapsed_end_x",
        "render_rules": "timeline_elapsed_axis_model.render_rules[]",
    },
    "parent_spawn_and_collapse": {
        "request": "lineage_request",
        "request_status": "lineage_request.status",
        "request_condition": "lineage_request.condition",
        "lineage_mode": "lineage.mode",
        "spawn_count": "lineage.spawn_count",
        "spawn_records": "lineage.spawns[]",
        "groups": "lineage.groups[]",
        "parent_lane_children": "lanes[].children[]",
        "child_parent_id": "lanes[].parentId",
        "collapsible_flag": "lanes[].collapsible",
        "expanded_default": "lanes[].expandedByDefault",
    },
    "lane_activity_and_label_layout": {
        "lane_start": "lanes[].xStart",
        "lane_end": "lanes[].xEnd",
        "runner_position": "lanes[].runnerX",
        "between_marker_phases": "lanes[].activitySegments[]",
        "timeline_lane_start_model": "timeline_lane_start_model",
        "activity_timeline_model": "lane_activity_timeline_model",
        "event_markers": "lanes[].events[]",
        "label_band": "lanes[].events[].label_band",
        "marker_priority": "lanes[].events[].marker_priority",
        "collision_group": "lanes[].events[].collision_group",
    },
    "agent_detail_cockpit": {
        "selected_tau_identity": "lanes[].cockpit.selected_tau_exploit_subagent",
        "current_turn": "lanes[].cockpit.current_turn",
        "public_trace": "lanes[].cockpit.public_trace",
        "stdout": "lanes[].cockpit.output.stdout",
        "stderr": "lanes[].cockpit.output.stderr",
        "skills_tools": "lanes[].cockpit.skills_tools",
        "blue_outcome": "lanes[].cockpit.blue_outcome",
        "latest_receipt_id": "lanes[].cockpit.latest_receipt_id",
        "replay": "lanes[].cockpit.replay",
    },
    "docker_replay_cta": {
        "lane_replay": "lanes[].replay",
        "cta": "lanes[].replay.cta",
        "label": "lanes[].replay.cta.label",
        "visible": "lanes[].replay.cta.visible",
        "state": "lanes[].replay.cta.state",
        "can_execute_now": "lanes[].replay.can_execute_now",
        "disabled_reason": "lanes[].replay.cta.disabled_reason",
    },
}
REQUIRED_RENDER_GUARDS = {
    "Do not render child lanes unless lineage.spawn_count > 0 and child lane ids exist in lanes[].",
    "Use lineage_request to explain requested-but-unproven child spawn; do not render children from lineage_request alone.",
    "Do not render Blue kill, fastest crash, or promotion unless matching event_type is present.",
    "Do not show live replay execution unless lane.replay.can_execute_now is true.",
    "Use battle_clock.mode and timeline.mode labels; do not imply live streaming from receipt_backed_fixture.",
    "Use scoreboard.per_pair for Blue block counts; do not infer blocks from Blue patch presence alone.",
    "Use timeline.playhead as receipt replay state; do not synthesize a live playhead.",
    "Use timeline_elapsed_axis_model for elapsed-time/DAW-style placement; use timeline.playhead.keyframes[].x only for legacy receipt-order renderers.",
    "Use lane.cockpit for Agent Detail pane values; do not infer Tau identity or trace fields from display labels.",
    "Use lane.replay.cta to render Docker replay button state; receipt_only means visible but not executable.",
    "Use lane.activitySegments for between-marker action labels; do not invent exploit phases client-side.",
    "Use spectator_shell for header/fact/score/ticker text; do not hard-code mockup shell copy.",
}
REQUIRED_FORBIDDEN_INFERENCES = {
    "Blue kill attribution",
    "Fastest crash",
    "Survivor promotion",
    "Unbounded swarm execution",
    "Live stream execution",
    "Child lineage without lineage receipt",
}


class ContractError(ValueError):
    """Raised when a Battle UX fixture violates the data contract."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help="Portable JSON Schema used by UX implementers.",
    )
    parser.add_argument("fixture", type=Path, help="Normalized Battle UX fixture JSON.")
    args = parser.parse_args(argv)
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    validate_fixture(fixture)
    validate_fixture_schema(fixture, schema_path=args.schema)
    return 0


def validate_fixture_schema(fixture: dict[str, Any], *, schema_path: Path = DEFAULT_SCHEMA_PATH) -> None:
    _validate_json_schema_payload(payload=fixture, schema_path=schema_path)


def validate_handoff_summary_schema(
    summary: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_HANDOFF_SUMMARY_SCHEMA_PATH,
) -> None:
    _validate_json_schema_payload(payload=summary, schema_path=schema_path)


def validate_transport_manifest_schema(
    manifest: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_TRANSPORT_MANIFEST_SCHEMA_PATH,
) -> None:
    _validate_json_schema_payload(payload=manifest, schema_path=schema_path)


def validate_live_event_schema(
    event: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_LIVE_EVENT_SCHEMA_PATH,
) -> None:
    _validate_json_schema_payload(payload=event, schema_path=schema_path)


def validate_snapshot_schema(
    snapshot: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_SNAPSHOT_SCHEMA_PATH,
) -> None:
    _validate_json_schema_payload(payload=snapshot, schema_path=schema_path)


def validate_semantic_outcome_matrix_schema(
    matrix: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_SEMANTIC_OUTCOME_MATRIX_SCHEMA_PATH,
) -> None:
    _validate_json_schema_payload(payload=matrix, schema_path=schema_path)


def validate_semantic_outcome_matrix_path(
    matrix_path: Path,
    *,
    schema_path: Path = DEFAULT_SEMANTIC_OUTCOME_MATRIX_SCHEMA_PATH,
) -> dict[str, Any]:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    validate_semantic_outcome_matrix_schema(matrix, schema_path=schema_path)
    validate_semantic_outcome_matrix(matrix)
    return {
        "status": "PASS",
        "schema": EXPECTED_SEMANTIC_OUTCOME_MATRIX_SCHEMA,
        "matrix": str(matrix_path),
        "outcome_case_count": len(matrix.get("outcome_cases", [])) if isinstance(matrix.get("outcome_cases"), list) else 0,
        "profile_case_count": len(matrix.get("profile_cases", [])) if isinstance(matrix.get("profile_cases"), list) else 0,
        "mocked": False,
        "proof_mode": matrix.get("proof_mode"),
    }


def validate_semantic_outcome_matrix(matrix: dict[str, Any]) -> None:
    errors: list[str] = []
    _check(matrix.get("schema") == EXPECTED_SEMANTIC_OUTCOME_MATRIX_SCHEMA, "semantic outcome matrix schema is invalid", errors)
    _check(matrix.get("score_owner") == "scorekeeper", "semantic outcome matrix score_owner must be scorekeeper", errors)
    invariants = matrix.get("score_invariants") if isinstance(matrix.get("score_invariants"), dict) else {}
    for key, value in invariants.items():
        _check(value is True, f"semantic outcome invariant must hold: {key}", errors)
    outcome_cases = matrix.get("outcome_cases") if isinstance(matrix.get("outcome_cases"), list) else []
    by_class = {str(case.get("outcome_class")): case for case in outcome_cases if isinstance(case, dict)}
    required_classes = {
        "pre_spawn_blue_block",
        "confirmed_blue_kill_no_child",
        "confirmed_blue_kill_with_child",
        "post_spawn_child_contained",
        "preemptive_spawn_adaptation",
        "spawn_pressure_conceded",
        "red_breakthrough",
        "unresolved_pressure",
    }
    _check(set(by_class) >= required_classes, "semantic outcome matrix must cover every outcome class", errors)
    if required_classes <= set(by_class):
        _check(
            by_class["pre_spawn_blue_block"]["score_delta"]["blue"]
            > by_class["confirmed_blue_kill_no_child"]["score_delta"]["blue"],
            "not spawning/pre-spawn block must score more Blue points than killing",
            errors,
        )
        _check(
            by_class["post_spawn_child_contained"]["score_delta"]["blue"]
            > by_class["confirmed_blue_kill_with_child"]["score_delta"]["blue"],
            "post-spawn containment must outrank killing a parent after valid child spawn",
            errors,
        )
        _check(
            by_class["confirmed_blue_kill_with_child"]["score_delta"]["blue"]
            > by_class["spawn_pressure_conceded"]["score_delta"]["blue"],
            "kill with child must still outrank mere spawn pressure conceded",
            errors,
        )
        _check(
            by_class["preemptive_spawn_adaptation"]["score_delta"]["red"]
            > by_class["spawn_pressure_conceded"]["score_delta"]["red"],
            "preemptive spawn under suspected pressure must score more Red adaptation credit than post-block handoff",
            errors,
        )
        _check(
            by_class["spawn_pressure_conceded"]["score_delta"]["blue"]
            > by_class["preemptive_spawn_adaptation"]["score_delta"]["blue"],
            "receipt-backed post-block handoff must score more Blue pressure credit than suspected-pressure preemptive spawn",
            errors,
        )
    profile_cases = matrix.get("profile_cases") if isinstance(matrix.get("profile_cases"), list) else []
    by_profile_case = {str(case.get("case_id")): case for case in profile_cases if isinstance(case, dict)}
    expected_variants = {
        "heavy_durable": "crimson_hornbreaker",
        "adaptive_lineage": "plague_nurgling",
        "high_complexity_pivot": "purple_horn_imp",
    }
    for case_id, variant_id in expected_variants.items():
        case = by_profile_case.get(case_id)
        _check(isinstance(case, dict), f"profile calibration case missing: {case_id}", errors)
        if isinstance(case, dict):
            _check(case.get("variant_id") == variant_id, f"profile calibration {case_id} must map to {variant_id}", errors)
            _check(case.get("cosmetic_identity_only") is True, f"profile calibration {case_id} must remain cosmetic only", errors)
    if errors:
        raise ContractError("\n".join(errors))


def validate_transport_stream_path(
    stream_dir: Path,
    *,
    manifest_schema_path: Path = DEFAULT_TRANSPORT_MANIFEST_SCHEMA_PATH,
    live_event_schema_path: Path = DEFAULT_LIVE_EVENT_SCHEMA_PATH,
    snapshot_schema_path: Path = DEFAULT_SNAPSHOT_SCHEMA_PATH,
) -> dict[str, Any]:
    stream_root = stream_dir.expanduser().resolve()
    manifest_path = stream_root / "manifest.json"
    if not manifest_path.exists():
        raise ContractError(f"transport manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_transport_manifest_schema(manifest, schema_path=manifest_schema_path)

    events_name = str(manifest.get("events_jsonl") or "")
    snapshot_name = str(manifest.get("latest_snapshot") or "")
    events_path = stream_root / events_name
    snapshot_path = stream_root / snapshot_name
    if not events_path.exists():
        raise ContractError(f"transport events JSONL not found: {events_path}")
    if not snapshot_path.exists():
        raise ContractError(f"transport latest snapshot not found: {snapshot_path}")

    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"events.jsonl line {line_number} is not valid JSON: {exc}") from exc
        validate_live_event_schema(event, schema_path=live_event_schema_path)
        events.append(event)

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    validate_snapshot_schema(snapshot, schema_path=snapshot_schema_path)
    _validate_transport_stream_semantics(manifest=manifest, events=events, snapshot=snapshot)
    return {
        "status": "PASS",
        "schema": EXPECTED_TRANSPORT_MANIFEST_SCHEMA,
        "stream_dir": str(stream_root),
        "manifest": str(manifest_path),
        "events_jsonl": str(events_path),
        "latest_snapshot": str(snapshot_path),
        "event_count": len(events),
        "last_seq": events[-1]["seq"] if events else 0,
        "mocked": manifest.get("mocked"),
        "live_source": manifest.get("live_source"),
        "phase": manifest.get("stream_contract", {}).get("phase") if isinstance(manifest.get("stream_contract"), dict) else None,
    }


def _validate_transport_stream_semantics(*, manifest: dict[str, Any], events: list[dict[str, Any]], snapshot: dict[str, Any]) -> None:
    errors: list[str] = []
    _check(manifest.get("event_count") == len(events), "manifest.event_count must match events.jsonl line count", errors)
    _check(manifest.get("last_seq") == (events[-1]["seq"] if events else 0), "manifest.last_seq must match final event seq", errors)
    expected_seq = list(range(1, len(events) + 1))
    _check([event.get("seq") for event in events] == expected_seq, "events seq values must be append-only contiguous integers", errors)
    _check(snapshot.get("last_seq") == manifest.get("last_seq"), "snapshot.last_seq must match manifest.last_seq", errors)
    _check(snapshot.get("battle_id") == manifest.get("battle_id"), "snapshot.battle_id must match manifest.battle_id", errors)
    _check(snapshot.get("run_id") == manifest.get("run_id"), "snapshot.run_id must match manifest.run_id", errors)

    policy = manifest.get("replay_compression_policy") if isinstance(manifest.get("replay_compression_policy"), dict) else {}
    _check(policy.get("owner") == "ux", "transport replay compression owner must be ux", errors)
    _check(policy.get("backend_emits_cinematic_speed") is False, "backend must not emit cinematic speed", errors)
    _check("cinematic_speed" in {str(item) for item in policy.get("backend_must_not_emit", [])}, "transport policy must forbid cinematic_speed", errors)

    semantic_replay = snapshot.get("semantic_replay") if isinstance(snapshot.get("semantic_replay"), dict) else {}
    _check(semantic_replay.get("presentation_owner") == "ux", "snapshot semantic_replay.presentation_owner must be ux", errors)
    _check(semantic_replay.get("time_authority") == "receipt_elapsed_seconds", "snapshot semantic_replay.time_authority must be receipt_elapsed_seconds", errors)
    _check("cinematic_speed" in {str(item) for item in semantic_replay.get("backend_must_not_emit", [])}, "snapshot semantic replay must forbid cinematic_speed", errors)

    lanes = snapshot.get("lanes") if isinstance(snapshot.get("lanes"), list) else []
    lane_scores = {
        str(lane.get("id")): lane.get("score_semantics")
        for lane in lanes
        if isinstance(lane, dict) and isinstance(lane.get("score_semantics"), dict) and lane.get("id")
    }
    spawn_receipts = {
        str(spawn.get("receipt_id")): spawn
        for spawn in (snapshot.get("lineage", {}) or {}).get("spawns", [])
        if isinstance(spawn, dict) and spawn.get("receipt_id")
    }
    lifecycle_events = [event.get("lifecycle") for event in events if isinstance(event.get("lifecycle"), dict)]
    _check(len(lifecycle_events) == len(events), "every stream event must include lifecycle semantics", errors)
    terminal_outcomes = {
        "pre_spawn_blue_block",
        "confirmed_blue_kill_no_child",
        "confirmed_blue_kill_with_child",
        "post_spawn_child_contained",
        "preemptive_spawn_adaptation",
        "spawn_pressure_conceded",
        "red_breakthrough",
        "unresolved_pressure",
    }
    for event in events:
        lifecycle = event.get("lifecycle") if isinstance(event.get("lifecycle"), dict) else {}
        lane_id = str(lifecycle.get("lane_id") or "")
        score = lane_scores.get(lane_id)
        if score:
            _check(lifecycle.get("outcome_class") == score.get("outcome_class"), f"event {event.get('seq')} lifecycle outcome_class must match lane score semantics", errors)
            _check(lifecycle.get("score_delta") == score.get("score_delta"), f"event {event.get('seq')} lifecycle score_delta must match lane score semantics", errors)
        _check(lifecycle.get("outcome_class") in terminal_outcomes, f"event {event.get('seq')} lifecycle outcome_class is not fail-closed", errors)
        receipt_id = str(lifecycle.get("receipt_id") or "")
        if receipt_id in spawn_receipts:
            _check(lifecycle.get("spawn_type") == spawn_receipts[receipt_id].get("spawn_type"), f"event {event.get('seq')} spawn_type must match lineage receipt", errors)

    if errors:
        raise ContractError("\n".join(errors))


def _validate_json_schema_payload(*, payload: dict[str, Any], schema_path: Path) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency failure is environment-specific.
        raise ContractError("jsonschema is required for portable schema validation") from exc

    if not schema_path.exists():
        raise ContractError(f"schema file not found: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        formatted = []
        for error in errors[:20]:
            path = ".".join(str(part) for part in error.path) or "<root>"
            formatted.append(f"{path}: {error.message}")
        if len(errors) > 20:
            formatted.append(f"... {len(errors) - 20} additional JSON Schema error(s)")
        raise ContractError("\n".join(formatted))


def validate_handoff_summary(
    summary: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    summary_schema_path: Path = DEFAULT_HANDOFF_SUMMARY_SCHEMA_PATH,
    require_data_contract_index: bool = True,
    require_renderer_artifacts: bool = True,
) -> dict[str, Any]:
    """Validate the backend UX handoff summary against its referenced fixtures."""
    errors: list[str] = []
    summary_for_schema = summary
    if not require_data_contract_index:
        summary_for_schema = dict(summary)
        summary_for_schema["data_contract_index"] = {
            "schema": EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA,
            "json": EXPECTED_UX_DATA_CONTRACT_INDEX_PATH,
            "validation_command": EXPECTED_UX_DATA_CONTRACT_INDEX_COMMAND,
            "purpose": "Placeholder used only while regenerating the UX data contract index.",
        }
    try:
        validate_handoff_summary_schema(summary_for_schema, schema_path=summary_schema_path)
    except ContractError as exc:
        errors.append(f"summary JSON Schema violation: {exc}")
    _check(summary.get("schema") == EXPECTED_HANDOFF_SUMMARY_SCHEMA, f"summary.schema must be {EXPECTED_HANDOFF_SUMMARY_SCHEMA}", errors)
    _check(summary.get("battle_id") == EXPECTED_CANONICAL_SCENARIO["battle_id"], "summary.battle_id must be battle-004", errors)
    _validate_summary_source_contract(summary=summary, errors=errors)
    _validate_goal_source_contract(summary=summary, errors=errors)
    _validate_proof_generation_contract(contract=summary.get("proof_generation_contract"), errors=errors)

    boundary = summary.get("current_agent_boundary")
    if not isinstance(boundary, dict):
        errors.append("summary.current_agent_boundary must be an object")
    else:
        _check(boundary.get("owner") == "battle_backend_json_contract", "summary.current_agent_boundary.owner must be battle_backend_json_contract", errors)
        does_not_own = boundary.get("does_not_own")
        _check(isinstance(does_not_own, list), "summary.current_agent_boundary.does_not_own must be a list", errors)

    bindings = summary.get("renderer_binding_contract")
    if not isinstance(bindings, dict):
        errors.append("summary.renderer_binding_contract must be an object")
    else:
        _validate_renderer_binding_contract(bindings, errors=errors)
        parent_spawn = bindings.get("parent_spawn_and_collapse") if isinstance(bindings.get("parent_spawn_and_collapse"), dict) else {}
        _check(parent_spawn.get("request") == "lineage_request", "summary renderer binding must expose lineage_request", errors)
        _check(parent_spawn.get("request_status") == "lineage_request.status", "summary renderer binding must expose lineage_request.status", errors)
        _check(parent_spawn.get("spawn_records") == "lineage.spawns[]", "summary renderer binding must expose lineage.spawns[]", errors)

    render_guards = summary.get("required_render_guards")
    if not isinstance(render_guards, list):
        errors.append("summary.required_render_guards must be a list")
    else:
        missing = sorted(REQUIRED_RENDER_GUARDS - {str(item) for item in render_guards})
        _check(not missing, f"summary.required_render_guards missing required guards: {missing}", errors)

    validation_commands = summary.get("required_backend_validation_commands")
    if not isinstance(validation_commands, list):
        errors.append("summary.required_backend_validation_commands must be a list")
    else:
        missing = sorted(REQUIRED_SUMMARY_VALIDATION_COMMANDS - {str(item) for item in validation_commands})
        _check(not missing, f"summary.required_backend_validation_commands missing required commands: {missing}", errors)

    fixture_reports: dict[str, dict[str, Any]] = {}
    loaded_fixtures: dict[str, dict[str, Any]] = {}
    for fixture_key in HANDOFF_SUMMARY_FIXTURE_KEYS:
        fixture_summary = summary.get(fixture_key)
        if not isinstance(fixture_summary, dict):
            errors.append(f"summary.{fixture_key} must be an object")
            continue
        fixture_path_value = fixture_summary.get("normalized_json")
        if not isinstance(fixture_path_value, str) or not fixture_path_value:
            errors.append(f"summary.{fixture_key}.normalized_json must be a path string")
            continue
        fixture_path = Path(fixture_path_value)
        if not fixture_path.exists():
            errors.append(f"summary.{fixture_key}.normalized_json does not exist: {fixture_path}")
            continue
        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"summary.{fixture_key}.normalized_json is not valid JSON: {exc}")
            continue
        try:
            validate_fixture(fixture)
            validate_fixture_schema(fixture, schema_path=schema_path)
        except ContractError as exc:
            errors.append(f"summary.{fixture_key}.normalized_json violates Battle UX contract: {exc}")
            continue

        _validate_fixture_matches_source_contract(fixture_key=fixture_key, fixture=fixture, summary=summary, errors=errors)
        _compare_fixture_summary(fixture_key=fixture_key, fixture=fixture, fixture_summary=fixture_summary, summary=summary, errors=errors)
        loaded_fixtures[fixture_key] = fixture
        fixture_timeline = fixture.get("timeline") if isinstance(fixture.get("timeline"), dict) else {}
        fixture_playhead = fixture_timeline.get("playhead") if isinstance(fixture_timeline.get("playhead"), dict) else {}
        fixture_keyframes = fixture_playhead.get("keyframes") if isinstance(fixture_playhead.get("keyframes"), list) else []
        fixture_viewport = fixture_timeline.get("viewport") if isinstance(fixture_timeline.get("viewport"), dict) else {}
        fixture_reports[fixture_key] = {
            "normalized_json": str(fixture_path),
            "status": fixture.get("status"),
            "mocked": fixture.get("mocked"),
            "live_source": fixture.get("live_source"),
            "lineage_request_status": fixture.get("lineage_request", {}).get("status") if isinstance(fixture.get("lineage_request"), dict) else None,
            "lineage_mode": fixture.get("lineage", {}).get("mode") if isinstance(fixture.get("lineage"), dict) else None,
            "child_spawn_count": fixture.get("scoreboard", {}).get("child_spawn_count") if isinstance(fixture.get("scoreboard"), dict) else None,
            "timeline_mode": fixture_timeline.get("mode"),
            "timeline_lane_count": fixture_timeline.get("lane_count"),
            "timeline_event_count": fixture_timeline.get("event_count"),
            "timeline_supports_pan": fixture_timeline.get("supports_pan"),
            "timeline_supports_zoom": fixture_timeline.get("supports_zoom"),
            "playhead_current_x": fixture_playhead.get("current_x"),
            "playhead_keyframe_count": len(fixture_keyframes),
            "playhead_keyframe_x_values": [frame.get("x") for frame in fixture_keyframes if isinstance(frame, dict)],
            "viewport": {
                "initial_min_x": fixture_viewport.get("initial_min_x"),
                "initial_max_x": fixture_viewport.get("initial_max_x"),
                "min_zoom": fixture_viewport.get("min_zoom"),
                "max_zoom": fixture_viewport.get("max_zoom"),
                "proof_mode": fixture_viewport.get("proof_mode"),
            },
        }

    recommended_report = _validate_recommended_renderer_fixture(
        summary=summary,
        loaded_fixtures=loaded_fixtures,
        fixture_reports=fixture_reports,
        errors=errors,
    )
    if require_renderer_artifacts:
        _validate_renderer_fixture_resolution_summary(
            summary=summary,
            recommended_report=recommended_report,
            errors=errors,
        )
        _validate_renderer_bundle_summary(
            summary=summary,
            recommended_report=recommended_report,
            errors=errors,
        )
        _validate_renderer_values_summary(
            summary=summary,
            recommended_report=recommended_report,
            errors=errors,
        )
    index_report = None
    if require_data_contract_index and require_renderer_artifacts:
        index_report = _validate_data_contract_index_summary(
            summary=summary,
            recommended_report=recommended_report,
            errors=errors,
        )

    if errors:
        raise ContractError("\n".join(errors))
    return {
        "status": "PASS",
        "schema": summary.get("schema"),
        "battle_id": summary.get("battle_id"),
        "canonical_scenario": summary.get("canonical_scenario"),
        "proof_generation_contract": summary.get("proof_generation_contract"),
        "handoff_summary_json_schema": str(summary_schema_path),
        "goal_source_contract": summary.get("goal_source_contract"),
        "goal_source_checked": EXPECTED_GOAL_SOURCE_PATH,
        "goal_source_required_phrases": sorted(REQUIRED_GOAL_SOURCE_PHRASES),
        "agent_boundary": summary.get("current_agent_boundary"),
        "minimum_required_backend_validation_commands": sorted(REQUIRED_SUMMARY_VALIDATION_COMMANDS),
        "reported_backend_validation_commands": list(validation_commands) if isinstance(validation_commands, list) else [],
        "required_render_guard_count": len(REQUIRED_RENDER_GUARDS),
        "reported_render_guard_count": len(render_guards) if isinstance(render_guards, list) else 0,
        "renderer_binding_sections": sorted(EXPECTED_RENDERER_BINDING_PATHS),
        "recommended_renderer_fixture": recommended_report,
        "data_contract_index": index_report,
        "fixtures": fixture_reports,
    }


def _validate_renderer_fixture_resolution_summary(
    *,
    summary: dict[str, Any],
    recommended_report: dict[str, Any] | None,
    errors: list[str],
) -> None:
    resolution_summary = summary.get("renderer_fixture_resolution")
    if not isinstance(resolution_summary, dict):
        errors.append("summary.renderer_fixture_resolution must be an object")
        return
    _check(
        resolution_summary.get("schema") == EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA,
        f"summary.renderer_fixture_resolution.schema must be {EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA}",
        errors,
    )
    _check(
        resolution_summary.get("json") == EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH,
        f"summary.renderer_fixture_resolution.json must be {EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH}",
        errors,
    )
    _check(
        resolution_summary.get("validation_command") == EXPECTED_RENDERER_FIXTURE_RESOLUTION_COMMAND,
        f"summary.renderer_fixture_resolution.validation_command must be {EXPECTED_RENDERER_FIXTURE_RESOLUTION_COMMAND}",
        errors,
    )

    resolution_path_value = resolution_summary.get("json")
    if not isinstance(resolution_path_value, str) or not resolution_path_value:
        errors.append("summary.renderer_fixture_resolution.json must be a path string")
        return
    resolution_path = Path(resolution_path_value)
    if not resolution_path.exists():
        errors.append(f"summary.renderer_fixture_resolution.json does not exist: {resolution_path}")
        return
    try:
        resolution = json.loads(resolution_path.read_text(encoding="utf-8"))
        validate_renderer_fixture_resolution_schema(resolution)
        validate_renderer_fixture_resolution(resolution)
    except (json.JSONDecodeError, ContractError) as exc:
        errors.append(f"summary.renderer_fixture_resolution.json violates Battle UX renderer fixture resolution contract: {exc}")
        return

    if recommended_report:
        _check(
            resolution.get("normalized_json") == recommended_report.get("normalized_json"),
            "renderer fixture resolution normalized_json must match recommended_renderer_fixture",
            errors,
        )
        _check(
            resolution.get("fixture_key") == recommended_report.get("fixture_key"),
            "renderer fixture resolution fixture_key must match recommended_renderer_fixture",
            errors,
        )
        _check(
            resolution.get("fixture_child_spawn_count") == recommended_report.get("fixture_child_spawn_count"),
            "renderer fixture resolution fixture_child_spawn_count must match recommended_renderer_fixture",
            errors,
        )


def _validate_renderer_bundle_summary(
    *,
    summary: dict[str, Any],
    recommended_report: dict[str, Any] | None,
    errors: list[str],
) -> None:
    bundle_summary = summary.get("renderer_bundle")
    if not isinstance(bundle_summary, dict):
        errors.append("summary.renderer_bundle must be an object")
        return
    _check(
        bundle_summary.get("schema") == EXPECTED_RENDERER_BUNDLE_SCHEMA,
        f"summary.renderer_bundle.schema must be {EXPECTED_RENDERER_BUNDLE_SCHEMA}",
        errors,
    )
    _check(
        bundle_summary.get("json") == EXPECTED_RENDERER_BUNDLE_PATH,
        f"summary.renderer_bundle.json must be {EXPECTED_RENDERER_BUNDLE_PATH}",
        errors,
    )
    _check(
        bundle_summary.get("validation_command") == EXPECTED_RENDERER_BUNDLE_COMMAND,
        f"summary.renderer_bundle.validation_command must be {EXPECTED_RENDERER_BUNDLE_COMMAND}",
        errors,
    )

    bundle_path_value = bundle_summary.get("json")
    if not isinstance(bundle_path_value, str) or not bundle_path_value:
        errors.append("summary.renderer_bundle.json must be a path string")
        return
    bundle_path = Path(bundle_path_value)
    if not bundle_path.exists():
        errors.append(f"summary.renderer_bundle.json does not exist: {bundle_path}")
        return
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        validate_renderer_bundle(bundle)
    except (json.JSONDecodeError, ContractError) as exc:
        errors.append(f"summary.renderer_bundle.json violates Battle UX renderer bundle contract: {exc}")
        return

    if recommended_report:
        resolution = bundle.get("resolution") if isinstance(bundle.get("resolution"), dict) else {}
        fixture = bundle.get("fixture") if isinstance(bundle.get("fixture"), dict) else {}
        _check(
            bundle.get("normalized_fixture_source") == recommended_report.get("normalized_json"),
            "renderer bundle normalized_fixture_source must match recommended_renderer_fixture",
            errors,
        )
        _check(
            resolution.get("fixture_key") == recommended_report.get("fixture_key"),
            "renderer bundle resolution.fixture_key must match recommended_renderer_fixture",
            errors,
        )
        _check(
            resolution.get("fixture_child_spawn_count") == recommended_report.get("fixture_child_spawn_count"),
            "renderer bundle resolution.fixture_child_spawn_count must match recommended_renderer_fixture",
            errors,
        )
        _check(
            fixture.get("scoreboard", {}).get("child_spawn_count") == recommended_report.get("fixture_child_spawn_count")
            if isinstance(fixture.get("scoreboard"), dict)
            else False,
            "renderer bundle fixture child_spawn_count must match recommended_renderer_fixture",
            errors,
        )


def _validate_renderer_values_summary(
    *,
    summary: dict[str, Any],
    recommended_report: dict[str, Any] | None,
    errors: list[str],
) -> None:
    values_summary = summary.get("renderer_values")
    if not isinstance(values_summary, dict):
        errors.append("summary.renderer_values must be an object")
        return
    _check(
        values_summary.get("schema") == EXPECTED_RENDERER_VALUES_SCHEMA,
        f"summary.renderer_values.schema must be {EXPECTED_RENDERER_VALUES_SCHEMA}",
        errors,
    )
    _check(
        values_summary.get("json") == EXPECTED_RENDERER_VALUES_PATH,
        f"summary.renderer_values.json must be {EXPECTED_RENDERER_VALUES_PATH}",
        errors,
    )
    _check(
        values_summary.get("validation_command") == EXPECTED_RENDERER_VALUES_COMMAND,
        f"summary.renderer_values.validation_command must be {EXPECTED_RENDERER_VALUES_COMMAND}",
        errors,
    )

    values_path_value = values_summary.get("json")
    if not isinstance(values_path_value, str) or not values_path_value:
        errors.append("summary.renderer_values.json must be a path string")
        return
    values_path = Path(values_path_value)
    if not values_path.exists():
        errors.append(f"summary.renderer_values.json does not exist: {values_path}")
        return
    try:
        values = json.loads(values_path.read_text(encoding="utf-8"))
        validate_renderer_values(values)
    except (json.JSONDecodeError, ContractError) as exc:
        errors.append(f"summary.renderer_values.json violates Battle UX renderer values contract: {exc}")
        return

    _check(
        summary.get("proof_generation_contract") == values.get("proof_generation_contract"),
        "summary.proof_generation_contract must match renderer values proof_generation_contract",
        errors,
    )
    if recommended_report:
        _check(
            values.get("source_fixture") == recommended_report.get("normalized_json"),
            "renderer values source_fixture must match recommended_renderer_fixture",
            errors,
        )
        scoreboard = values.get("scoreboard") if isinstance(values.get("scoreboard"), dict) else {}
        timeline = values.get("timeline") if isinstance(values.get("timeline"), dict) else {}
        playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
        _check(
            scoreboard.get("child_spawn_count") == recommended_report.get("fixture_child_spawn_count"),
            "renderer values child_spawn_count must match recommended_renderer_fixture",
            errors,
        )
        _check(
            playhead.get("current_x") == recommended_report.get("fixture_playhead_current_x"),
            "renderer values playhead.current_x must match recommended_renderer_fixture",
            errors,
        )


def _validate_data_contract_index_summary(
    *,
    summary: dict[str, Any],
    recommended_report: dict[str, Any] | None,
    errors: list[str],
) -> dict[str, Any] | None:
    index_summary = summary.get("data_contract_index")
    if not isinstance(index_summary, dict):
        errors.append("summary.data_contract_index must be an object")
        return None
    _check(
        index_summary.get("schema") == EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA,
        f"summary.data_contract_index.schema must be {EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA}",
        errors,
    )
    _check(
        index_summary.get("json") == EXPECTED_UX_DATA_CONTRACT_INDEX_PATH,
        f"summary.data_contract_index.json must be {EXPECTED_UX_DATA_CONTRACT_INDEX_PATH}",
        errors,
    )
    _check(
        index_summary.get("validation_command") == EXPECTED_UX_DATA_CONTRACT_INDEX_COMMAND,
        f"summary.data_contract_index.validation_command must be {EXPECTED_UX_DATA_CONTRACT_INDEX_COMMAND}",
        errors,
    )

    index_path_value = index_summary.get("json")
    if not isinstance(index_path_value, str) or not index_path_value:
        errors.append("summary.data_contract_index.json must be a path string")
        return None
    index_path = Path(index_path_value)
    if not index_path.exists():
        errors.append(f"summary.data_contract_index.json does not exist: {index_path}")
        return None
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        validate_ux_data_contract_index(index)
    except (json.JSONDecodeError, ContractError) as exc:
        errors.append(f"summary.data_contract_index.json violates Battle UX data contract index: {exc}")
        return None

    _check(
        summary.get("proof_generation_contract") == index.get("proof_generation_contract"),
        "summary.proof_generation_contract must match data contract index proof_generation_contract",
        errors,
    )
    if recommended_report:
        _check(
            index.get("authoritative_renderer_values") == EXPECTED_RENDERER_VALUES_PATH,
            "data contract index authoritative_renderer_values must match renderer values artifact",
            errors,
        )
        _check(
            index.get("authoritative_normalized_fixture") == recommended_report.get("normalized_json"),
            "data contract index authoritative_normalized_fixture must match recommended_renderer_fixture",
            errors,
        )
        backed = index.get("receipt_backed_values") if isinstance(index.get("receipt_backed_values"), dict) else {}
        _check(
            backed.get("child_spawn_count") == recommended_report.get("fixture_child_spawn_count"),
            "data contract index child_spawn_count must match recommended_renderer_fixture",
            errors,
        )
        _check(
            backed.get("playhead_current_x") == recommended_report.get("fixture_playhead_current_x"),
            "data contract index playhead_current_x must match recommended_renderer_fixture",
            errors,
        )

    backed = index.get("receipt_backed_values") if isinstance(index.get("receipt_backed_values"), dict) else {}
    timing_contract = index.get("timing_contract") if isinstance(index.get("timing_contract"), dict) else {}
    return {
        "schema": index.get("schema"),
        "json": str(index_path),
        "authoritative_renderer_values": index.get("authoritative_renderer_values"),
        "authoritative_normalized_fixture": index.get("authoritative_normalized_fixture"),
        "child_spawn_count": backed.get("child_spawn_count"),
        "playhead_current_x": backed.get("playhead_current_x"),
        "timing_contract": timing_contract,
    }


def _validate_recommended_renderer_fixture(
    *,
    summary: dict[str, Any],
    loaded_fixtures: dict[str, dict[str, Any]],
    fixture_reports: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[str, Any] | None:
    recommended = summary.get("recommended_renderer_fixture")
    if not isinstance(recommended, dict):
        errors.append("summary.recommended_renderer_fixture must be an object")
        return None

    fixture_key = recommended.get("fixture_key")
    if fixture_key not in HANDOFF_SUMMARY_FIXTURE_KEYS:
        errors.append(f"summary.recommended_renderer_fixture.fixture_key must be one of {list(HANDOFF_SUMMARY_FIXTURE_KEYS)}")
        return None
    _check(
        fixture_key == RECOMMENDED_RENDERER_FIXTURE_KEY,
        f"summary.recommended_renderer_fixture.fixture_key must be {RECOMMENDED_RENDERER_FIXTURE_KEY}",
        errors,
    )

    fixture_summary = summary.get(str(fixture_key))
    if not isinstance(fixture_summary, dict):
        errors.append(f"summary.{fixture_key} must exist before it can be recommended")
        return None

    normalized_json = recommended.get("normalized_json")
    _check(
        normalized_json == fixture_summary.get("normalized_json"),
        "summary.recommended_renderer_fixture.normalized_json must match the selected fixture summary",
        errors,
    )
    _check(
        recommended.get("proof_mode") == EXPECTED_PROOF_MODE,
        f"summary.recommended_renderer_fixture.proof_mode must be {EXPECTED_PROOF_MODE}",
        errors,
    )
    _check(
        recommended.get("required_status") == "PASS",
        "summary.recommended_renderer_fixture.required_status must be PASS",
        errors,
    )
    _check(
        recommended.get("required_lineage_mode") == "receipt_backed",
        "summary.recommended_renderer_fixture.required_lineage_mode must be receipt_backed",
        errors,
    )

    child_spawn_count_min = recommended.get("required_child_spawn_count_min")
    _check(
        isinstance(child_spawn_count_min, int) and child_spawn_count_min >= 1,
        "summary.recommended_renderer_fixture.required_child_spawn_count_min must be an integer >= 1",
        errors,
    )

    fixture = loaded_fixtures.get(str(fixture_key))
    fixture_report = fixture_reports.get(str(fixture_key), {})
    if not isinstance(fixture, dict):
        errors.append(f"summary.recommended_renderer_fixture.fixture_key points to an unloaded or invalid fixture: {fixture_key}")
        return None

    lineage = fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {}
    scoreboard = fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}
    child_spawn_count = scoreboard.get("child_spawn_count")
    _check(fixture.get("status") == "PASS", "recommended renderer fixture must have fixture.status PASS", errors)
    _check(lineage.get("mode") == "receipt_backed", "recommended renderer fixture must have lineage.mode receipt_backed", errors)
    _check(
        isinstance(child_spawn_count, int)
        and isinstance(child_spawn_count_min, int)
        and child_spawn_count >= child_spawn_count_min,
        "recommended renderer fixture must meet required_child_spawn_count_min",
        errors,
    )

    return {
        "fixture_key": fixture_key,
        "normalized_json": normalized_json,
        "selection_reason": recommended.get("selection_reason"),
        "required_status": recommended.get("required_status"),
        "required_lineage_mode": recommended.get("required_lineage_mode"),
        "required_child_spawn_count_min": child_spawn_count_min,
        "proof_mode": recommended.get("proof_mode"),
        "fixture_status": fixture.get("status"),
        "fixture_lineage_mode": lineage.get("mode"),
        "fixture_child_spawn_count": child_spawn_count,
        "fixture_playhead_current_x": fixture_report.get("playhead_current_x"),
        "fixture_playhead_keyframe_x_values": fixture_report.get("playhead_keyframe_x_values"),
    }


def _refresh_fixture_summary(existing: dict[str, Any], *, fixture: dict[str, Any]) -> dict[str, Any]:
    refreshed = dict(existing)
    timeline = fixture.get("timeline") if isinstance(fixture.get("timeline"), dict) else {}
    playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    keyframes = playhead.get("keyframes") if isinstance(playhead.get("keyframes"), list) else []
    viewport = timeline.get("viewport") if isinstance(timeline.get("viewport"), dict) else {}
    lineage = fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {}
    groups = lineage.get("groups") if isinstance(lineage.get("groups"), list) else []
    lanes = fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else []
    lane_ids_with_activity = [
        str(lane.get("id"))
        for lane in lanes
        if isinstance(lane, dict) and lane.get("id") and isinstance(lane.get("activitySegments"), list) and lane.get("activitySegments")
    ]
    replay_lanes = [
        lane
        for lane in lanes
        if isinstance(lane, dict) and isinstance(lane.get("replay"), dict)
    ]

    refreshed.update(
        {
            "status": fixture.get("status"),
            "mocked": fixture.get("mocked"),
            "live_source": fixture.get("live_source"),
            "source_proof_dir": fixture.get("source_proof_dir"),
            "battle_clock": fixture.get("battle_clock"),
            "lineage_request": fixture.get("lineage_request"),
            "lineage": {
                "mode": lineage.get("mode"),
                "spawn_count": lineage.get("spawn_count"),
                "parent_lane_ids": lineage.get("parent_lane_ids"),
                "child_lane_ids": lineage.get("child_lane_ids"),
            },
            "scoreboard": {
                "verdict": (fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}).get("verdict"),
                "judged_pair_count": (fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}).get("judged_pair_count"),
                "blue_success_count": (fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}).get("blue_success_count"),
                "child_spawn_count": (fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}).get("child_spawn_count"),
            },
            "timeline": {
                "mode": timeline.get("mode"),
                "lane_count": timeline.get("lane_count"),
                "event_count": timeline.get("event_count"),
                "supports_pan": timeline.get("supports_pan"),
                "supports_zoom": timeline.get("supports_zoom"),
                "playhead": {
                    "mode": playhead.get("mode"),
                    "current_x": playhead.get("current_x"),
                    "elapsed_seconds": playhead.get("elapsed_seconds"),
                    "source_receipt_id": playhead.get("source_receipt_id"),
                    "animation_semantics": playhead.get("animation_semantics"),
                    "keyframe_count": len(keyframes),
                    "keyframe_x_values": [frame.get("x") for frame in keyframes if isinstance(frame, dict)],
                },
                "viewport": {
                    "initial_min_x": viewport.get("initial_min_x"),
                    "initial_max_x": viewport.get("initial_max_x"),
                    "min_zoom": viewport.get("min_zoom"),
                    "max_zoom": viewport.get("max_zoom"),
                    "proof_mode": viewport.get("proof_mode"),
                },
            },
        }
    )

    refreshed["collapsible_lineage_groups"] = {
        "group_count": len(groups),
        "groups": [
            {
                "group_id": group.get("group_id"),
                "parent_lane_id": group.get("parent_lane_id"),
                "child_lane_ids": group.get("child_lane_ids"),
                "collapsible": group.get("collapsible"),
                "expanded_by_default": group.get("expanded_by_default"),
            }
            for group in groups
            if isinstance(group, dict)
        ],
    }

    activity_segments = dict(refreshed.get("activity_segments") if isinstance(refreshed.get("activity_segments"), dict) else {})
    activity_segments["lane_ids"] = lane_ids_with_activity
    activity_segments["required"] = True
    if len(lane_ids_with_activity) > 1:
        parent_lane = next((lane for lane in lanes if isinstance(lane, dict) and not lane.get("parentId")), {})
        child_lane = next((lane for lane in lanes if isinstance(lane, dict) and lane.get("parentId")), {})
        activity_segments["sample_parent_phases"] = _activity_phases(parent_lane)
        activity_segments["sample_child_phases"] = _activity_phases(child_lane)
        activity_segments.pop("sample_phases", None)
    else:
        first_lane = lanes[0] if lanes and isinstance(lanes[0], dict) else {}
        activity_segments["sample_phases"] = _activity_phases(first_lane)
        activity_segments.pop("sample_parent_phases", None)
        activity_segments.pop("sample_child_phases", None)
    refreshed["activity_segments"] = activity_segments

    if replay_lanes:
        replay = replay_lanes[0].get("replay") if isinstance(replay_lanes[0], dict) else {}
        cta = replay.get("cta") if isinstance(replay, dict) and isinstance(replay.get("cta"), dict) else {}
        refreshed["replay_cta"] = {
            "lane_ids": [str(lane.get("id")) for lane in replay_lanes if isinstance(lane, dict) and lane.get("id")],
            "label": cta.get("label"),
            "state": cta.get("state"),
            "can_execute_now": replay.get("can_execute_now") if isinstance(replay, dict) else None,
            "required_disabled_reason": cta.get("disabled_reason"),
            "sample": cta,
        }
    else:
        refreshed["replay_cta"] = {
            "lane_ids": [],
            "note": "No replay CTA exists when no Judge BLUE_SUCCESS replay metadata exists.",
        }

    child_lanes = [lane for lane in lanes if isinstance(lane, dict) and lane.get("parentId")]
    if child_lanes:
        child = child_lanes[0]
        child_segments = child.get("activitySegments") if isinstance(child.get("activitySegments"), list) else []
        child_events = child.get("events") if isinstance(child.get("events"), list) else []
        refreshed["timeline"]["child_lane_timing"] = {
            "child_lane_id": child.get("id"),
            "xStart": child.get("xStart"),
            "event_x_values": [event.get("x") for event in child_events if isinstance(event, dict)],
            "activity_segment_bounds": [
                [segment.get("start_x"), segment.get("end_x")]
                for segment in child_segments
                if isinstance(segment, dict)
            ],
            "invariant": "Child lane events and activity segments must not occur before child lane xStart.",
        }
    else:
        refreshed["timeline"].pop("child_lane_timing", None)

    return refreshed


def _activity_phases(lane: Any) -> list[str]:
    if not isinstance(lane, dict):
        return []
    return [
        str(segment.get("phase"))
        for segment in lane.get("activitySegments", [])
        if isinstance(segment, dict) and segment.get("phase")
    ]


def validate_handoff_summary_path(
    summary_path: Path,
    *,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    summary_schema_path: Path = DEFAULT_HANDOFF_SUMMARY_SCHEMA_PATH,
    require_data_contract_index: bool = True,
    require_renderer_artifacts: bool = True,
) -> dict[str, Any]:
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"summary is not valid JSON: {summary_path}: {exc}") from exc
    report = validate_handoff_summary(
        summary,
        schema_path=schema_path,
        summary_schema_path=summary_schema_path,
        require_data_contract_index=require_data_contract_index,
        require_renderer_artifacts=require_renderer_artifacts,
    )
    report["summary"] = str(summary_path)
    return report


def resolve_renderer_fixture_from_summary_path(
    summary_path: Path,
    *,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    summary_schema_path: Path = DEFAULT_HANDOFF_SUMMARY_SCHEMA_PATH,
    resolution_schema_path: Path = DEFAULT_RENDERER_FIXTURE_RESOLUTION_SCHEMA_PATH,
    require_data_contract_index: bool = True,
) -> dict[str, Any]:
    """Return the exact normalized JSON fixture the UX renderer should load."""
    report = validate_handoff_summary_path(
        summary_path,
        schema_path=schema_path,
        summary_schema_path=summary_schema_path,
        require_data_contract_index=require_data_contract_index,
        require_renderer_artifacts=False,
    )
    resolution = renderer_fixture_resolution_from_report(report, summary_path=summary_path)
    validate_renderer_fixture_resolution_schema(resolution, schema_path=resolution_schema_path)
    validate_renderer_fixture_resolution(resolution)
    return resolution


def export_handoff_summary_from_current_fixtures(summary_path: Path) -> dict[str, Any]:
    """Refresh fixture-derived fields in the backend UX handoff summary.

    Renderer resolution, bundle, values, and index artifacts can be stale while
    fresh Arena/Tau/Judge receipts are being normalized. This exporter updates
    only fields whose source of truth is the selected normalized fixture JSON,
    then validates the summary without requiring dependent renderer artifacts.
    """
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"summary is not valid JSON: {summary_path}: {exc}") from exc

    for fixture_key in HANDOFF_SUMMARY_FIXTURE_KEYS:
        fixture_summary = summary.get(fixture_key)
        if not isinstance(fixture_summary, dict):
            raise ContractError(f"summary.{fixture_key} must be an object")
        fixture_path_value = fixture_summary.get("normalized_json")
        if not isinstance(fixture_path_value, str) or not fixture_path_value:
            raise ContractError(f"summary.{fixture_key}.normalized_json must be a path string")
        fixture_path = Path(fixture_path_value)
        if not fixture_path.exists():
            raise ContractError(f"summary.{fixture_key}.normalized_json does not exist: {fixture_path}")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        validate_fixture(fixture)
        validate_fixture_schema(fixture)
        summary[fixture_key] = _refresh_fixture_summary(fixture_summary, fixture=fixture)

    validate_handoff_summary(
        summary,
        require_data_contract_index=False,
        require_renderer_artifacts=False,
    )
    return summary


def renderer_fixture_resolution_from_report(report: dict[str, Any], *, summary_path: Path | str) -> dict[str, Any]:
    recommended = report.get("recommended_renderer_fixture")
    if not isinstance(recommended, dict):
        raise ContractError("validated handoff summary did not produce recommended_renderer_fixture")

    fixture_key = str(recommended.get("fixture_key") or "")
    fixtures = report.get("fixtures") if isinstance(report.get("fixtures"), dict) else {}
    fixture_report = fixtures.get(fixture_key) if isinstance(fixtures.get(fixture_key), dict) else {}

    return {
        "schema": EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA,
        "status": "PASS",
        "summary": str(summary_path),
        "battle_id": report.get("battle_id"),
        "canonical_scenario": report.get("canonical_scenario"),
        "fixture_key": fixture_key,
        "normalized_json": recommended.get("normalized_json"),
        "selection_reason": recommended.get("selection_reason"),
        "proof_mode": recommended.get("proof_mode"),
        "fixture_status": recommended.get("fixture_status"),
        "fixture_lineage_mode": recommended.get("fixture_lineage_mode"),
        "fixture_child_spawn_count": recommended.get("fixture_child_spawn_count"),
        "fixture_playhead_current_x": recommended.get("fixture_playhead_current_x"),
        "fixture_playhead_keyframe_x_values": recommended.get("fixture_playhead_keyframe_x_values"),
        "mocked": fixture_report.get("mocked"),
        "live_source": fixture_report.get("live_source"),
    }


def validate_renderer_fixture_resolution_schema(
    resolution: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_RENDERER_FIXTURE_RESOLUTION_SCHEMA_PATH,
) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover
        raise ContractError("jsonschema is required to validate Battle UX renderer fixture resolution schema") from exc

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(resolution), key=lambda error: list(error.path))
    if errors:
        detail = "\n".join(f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors)
        raise ContractError(f"Battle UX renderer fixture resolution schema validation failed:\n{detail}")


def validate_renderer_fixture_resolution(resolution: dict[str, Any]) -> None:
    errors: list[str] = []
    _check(
        resolution.get("schema") == EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA,
        f"schema must be {EXPECTED_RENDERER_FIXTURE_RESOLUTION_SCHEMA}",
        errors,
    )
    _check(resolution.get("status") == "PASS", "status must be PASS", errors)
    _check(resolution.get("battle_id") == "battle-004", "battle_id must be battle-004", errors)
    _check(resolution.get("fixture_key") == RECOMMENDED_RENDERER_FIXTURE_KEY, f"fixture_key must be {RECOMMENDED_RENDERER_FIXTURE_KEY}", errors)
    _check(resolution.get("fixture_status") == "PASS", "fixture_status must be PASS", errors)
    _check(resolution.get("fixture_lineage_mode") == "receipt_backed", "fixture_lineage_mode must be receipt_backed", errors)
    _check(_int(resolution.get("fixture_child_spawn_count")) >= 1, "fixture_child_spawn_count must be >= 1", errors)
    _check(resolution.get("mocked") is False, "mocked must be false", errors)

    scenario = resolution.get("canonical_scenario") if isinstance(resolution.get("canonical_scenario"), dict) else {}
    _check(scenario.get("public_entrypoint") == "/api/import-zip", "canonical_scenario.public_entrypoint must be /api/import-zip", errors)
    _check(scenario.get("cwe") == "CWE-22", "canonical_scenario.cwe must be CWE-22", errors)
    _check(
        scenario.get("hidden_vulnerability_family") == "Zip Slip path traversal",
        "canonical_scenario.hidden_vulnerability_family must be Zip Slip path traversal",
        errors,
    )

    keyframes = resolution.get("fixture_playhead_keyframe_x_values")
    current_x = _number_or_none(resolution.get("fixture_playhead_current_x"))
    if isinstance(keyframes, list) and keyframes:
        numeric_keyframes = [_number_or_none(value) for value in keyframes]
        _check(all(value is not None for value in numeric_keyframes), "fixture_playhead_keyframe_x_values must be numeric", errors)
        _check(numeric_keyframes == sorted(numeric_keyframes), "fixture_playhead_keyframe_x_values must be sorted", errors)
        _check(current_x == numeric_keyframes[-1], "fixture_playhead_current_x must equal the final keyframe", errors)
    else:
        errors.append("fixture_playhead_keyframe_x_values must be a non-empty list")

    if errors:
        raise ContractError("\n".join(errors))


def export_renderer_bundle_from_resolution_path(resolution_path: Path) -> dict[str, Any]:
    try:
        resolution = json.loads(resolution_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"renderer fixture resolution is not valid JSON: {resolution_path}: {exc}") from exc

    validate_renderer_fixture_resolution_schema(resolution)
    validate_renderer_fixture_resolution(resolution)

    fixture_path_value = resolution.get("normalized_json")
    if not isinstance(fixture_path_value, str) or not fixture_path_value:
        raise ContractError("renderer fixture resolution normalized_json must be a path string")
    fixture_path = Path(fixture_path_value)
    if not fixture_path.exists():
        raise ContractError(f"renderer fixture resolution normalized_json does not exist: {fixture_path}")

    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"renderer fixture normalized_json is not valid JSON: {fixture_path}: {exc}") from exc
    validate_fixture(fixture)
    validate_fixture_schema(fixture)

    bundle = {
        "schema": EXPECTED_RENDERER_BUNDLE_SCHEMA,
        "status": "PASS",
        "resolution_source": str(resolution_path),
        "normalized_fixture_source": str(fixture_path),
        "resolution": resolution,
        "fixture": fixture,
    }
    validate_renderer_bundle(bundle)
    return bundle


def validate_renderer_bundle_schema(
    bundle: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_RENDERER_BUNDLE_SCHEMA_PATH,
) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover
        raise ContractError("jsonschema is required to validate Battle UX renderer bundle schema") from exc

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(bundle), key=lambda error: list(error.path))
    if errors:
        detail = "\n".join(f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors)
        raise ContractError(f"Battle UX renderer bundle schema validation failed:\n{detail}")


def validate_renderer_bundle(bundle: dict[str, Any]) -> None:
    errors: list[str] = []
    try:
        validate_renderer_bundle_schema(bundle)
    except ContractError as exc:
        errors.append(str(exc))
    _check(bundle.get("schema") == EXPECTED_RENDERER_BUNDLE_SCHEMA, f"schema must be {EXPECTED_RENDERER_BUNDLE_SCHEMA}", errors)
    _check(bundle.get("status") == "PASS", "status must be PASS", errors)
    resolution = bundle.get("resolution") if isinstance(bundle.get("resolution"), dict) else {}
    fixture = bundle.get("fixture") if isinstance(bundle.get("fixture"), dict) else {}
    if not resolution:
        errors.append("resolution must be an object")
    else:
        try:
            validate_renderer_fixture_resolution_schema(resolution)
            validate_renderer_fixture_resolution(resolution)
        except ContractError as exc:
            errors.append(f"resolution invalid: {exc}")
    if not fixture:
        errors.append("fixture must be an object")
    else:
        try:
            validate_fixture(fixture)
            validate_fixture_schema(fixture)
        except ContractError as exc:
            errors.append(f"fixture invalid: {exc}")
    if resolution and fixture:
        _check(resolution.get("normalized_json") == bundle.get("normalized_fixture_source"), "normalized_fixture_source must match resolution.normalized_json", errors)
        _check(fixture.get("battle_id") == resolution.get("battle_id"), "fixture.battle_id must match resolution.battle_id", errors)
        _check(fixture.get("mocked") == resolution.get("mocked"), "fixture.mocked must match resolution.mocked", errors)
        _check(
            fixture.get("scoreboard", {}).get("child_spawn_count") == resolution.get("fixture_child_spawn_count")
            if isinstance(fixture.get("scoreboard"), dict)
            else False,
            "fixture child_spawn_count must match resolution",
            errors,
        )
        playhead = fixture.get("timeline", {}).get("playhead", {}) if isinstance(fixture.get("timeline"), dict) else {}
        _check(playhead.get("current_x") == resolution.get("fixture_playhead_current_x"), "fixture playhead.current_x must match resolution", errors)
    if errors:
        raise ContractError("\n".join(errors))


def export_renderer_values_from_bundle_path(bundle_path: Path) -> dict[str, Any]:
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"renderer bundle is not valid JSON: {bundle_path}: {exc}") from exc

    validate_renderer_bundle(bundle)
    fixture = bundle["fixture"]
    ux_contract = fixture.get("ux_contract") if isinstance(fixture.get("ux_contract"), dict) else {}
    elapsed_axis_model = _timeline_elapsed_axis_model(
        battle_clock=fixture.get("battle_clock") if isinstance(fixture.get("battle_clock"), dict) else {},
        timeline=fixture.get("timeline") if isinstance(fixture.get("timeline"), dict) else {},
    )
    values = {
        "schema": EXPECTED_RENDERER_VALUES_SCHEMA,
        "status": "PASS",
        "source_bundle": str(bundle_path),
        "source_fixture": str(bundle.get("normalized_fixture_source")),
        "battle_id": fixture.get("battle_id"),
        "scenario": fixture.get("scenario"),
        "proof_generation_contract": _proof_generation_contract(),
        "proof_mode": fixture.get("proof_mode"),
        "mocked": fixture.get("mocked"),
        "live_source": fixture.get("live_source"),
        "round_config": fixture.get("round_config"),
        "clock": fixture.get("clock"),
        "spectator_shell": fixture.get("spectator_shell"),
        "shell": fixture.get("spectator_shell"),
        "battle_clock": fixture.get("battle_clock"),
        "timeline": fixture.get("timeline"),
        "battle_timeline_control": fixture.get("battle_timeline_control"),
        "segments": fixture.get("segments"),
        "validation": fixture.get("validation"),
        "timeline_time_model": _timeline_time_model(
            battle_clock=fixture.get("battle_clock") if isinstance(fixture.get("battle_clock"), dict) else {},
            timeline=fixture.get("timeline") if isinstance(fixture.get("timeline"), dict) else {},
        ),
        "timeline_elapsed_axis_model": elapsed_axis_model,
        "timeline_viewport_model": _timeline_viewport_model(
            timeline=fixture.get("timeline") if isinstance(fixture.get("timeline"), dict) else {},
        ),
        "timeline_lane_start_model": _timeline_lane_start_model(
            lineage=fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {},
            lanes=fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else [],
            elapsed_axis_model=elapsed_axis_model,
        ),
        "lane_activity_timeline_model": _lane_activity_timeline_model(
            lanes=fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else [],
            elapsed_axis_model=elapsed_axis_model,
        ),
        "timeline_label_layout_model": _timeline_label_layout_model(
            lanes=fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else [],
        ),
        "lineage_request": fixture.get("lineage_request"),
        "lineage": fixture.get("lineage"),
        "lineage_render_model": _lineage_render_model(
            lineage=fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {},
            lanes=fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else [],
        ),
        "spawn_gate_model": _spawn_gate_model(
            lineage=fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {},
            lanes=fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else [],
            events=fixture.get("events") if isinstance(fixture.get("events"), list) else [],
            scoreboard=fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {},
        ),
        "selected_lane_model": _selected_lane_model(
            lineage=fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {},
            lanes=fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else [],
        ),
        "outcome_truth_constraints_model": _outcome_truth_constraints_model(fixture=fixture),
        "lanes": fixture.get("lanes"),
        "events": fixture.get("events"),
        "proof_blockers": fixture.get("proof_blockers"),
        "bluePatchActions": fixture.get("bluePatchActions"),
        "scoreboard": fixture.get("scoreboard"),
        "leaderboard": fixture.get("leaderboard"),
        "lane_phase_coverage": _lane_phase_coverage(fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else []),
        "receipts": fixture.get("receipts"),
        "renderer_binding_contract": fixture.get("renderer_binding_contract"),
        "required_render_guards": ux_contract.get("required_render_guards") if isinstance(ux_contract, dict) else [],
        "forbidden_inferences": ux_contract.get("forbidden_inferences") if isinstance(ux_contract, dict) else [],
        "receipt_backed_values": _renderer_receipt_backed_values(fixture=fixture, ux_contract=ux_contract),
    }
    validate_renderer_values(values)
    return values


def validate_renderer_values_schema(
    values: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_RENDERER_VALUES_SCHEMA_PATH,
) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover
        raise ContractError("jsonschema is required to validate Battle UX renderer values schema") from exc

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(values), key=lambda error: list(error.path))
    if errors:
        detail = "\n".join(f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors)
        raise ContractError(f"Battle UX renderer values schema validation failed:\n{detail}")


def validate_renderer_values(values: dict[str, Any], *, check_sources: bool = False) -> None:
    errors: list[str] = []
    try:
        validate_renderer_values_schema(values)
    except ContractError as exc:
        errors.append(str(exc))

    _check(values.get("schema") == EXPECTED_RENDERER_VALUES_SCHEMA, f"schema must be {EXPECTED_RENDERER_VALUES_SCHEMA}", errors)
    _check(values.get("status") == "PASS", "status must be PASS", errors)
    _check(values.get("battle_id") == "battle-004", "battle_id must be battle-004", errors)
    _validate_proof_generation_contract(contract=values.get("proof_generation_contract"), errors=errors)
    scenario = values.get("scenario") if isinstance(values.get("scenario"), dict) else {}
    _check(scenario.get("public_entrypoint") == "/api/import-zip", "scenario.public_entrypoint must be /api/import-zip", errors)
    _check(scenario.get("cwe") == "CWE-22", "scenario.cwe must be CWE-22", errors)
    _check(values.get("mocked") is False, "mocked must be false", errors)
    _check(values.get("spectator_shell") == values.get("shell"), "spectator_shell must match shell compatibility alias", errors)
    timeline = values.get("timeline") if isinstance(values.get("timeline"), dict) else {}
    playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    time_model = values.get("timeline_time_model") if isinstance(values.get("timeline_time_model"), dict) else {}
    lineage = values.get("lineage") if isinstance(values.get("lineage"), dict) else {}
    scoreboard = values.get("scoreboard") if isinstance(values.get("scoreboard"), dict) else {}
    lanes = values.get("lanes") if isinstance(values.get("lanes"), list) else []
    phase_coverage = values.get("lane_phase_coverage") if isinstance(values.get("lane_phase_coverage"), list) else []
    backed = values.get("receipt_backed_values") if isinstance(values.get("receipt_backed_values"), dict) else {}

    _check(timeline.get("scroll_axis") == "horizontal", "timeline.scroll_axis must be horizontal", errors)
    _check(timeline.get("supports_pan") is True, "timeline.supports_pan must be true", errors)
    _check(timeline.get("supports_zoom") is True, "timeline.supports_zoom must be true", errors)
    _check(playhead.get("can_animate") is True, "timeline.playhead.can_animate must be true", errors)
    _check(playhead.get("animation_semantics") == "receipt_replay_only", "timeline.playhead.animation_semantics must be receipt_replay_only", errors)
    _validate_timeline_time_model(values=values, errors=errors)
    _validate_timeline_elapsed_axis_model(values=values, errors=errors)
    _validate_timeline_viewport_model(values=values, errors=errors)
    _validate_timeline_lane_start_model(values=values, errors=errors)
    _validate_lane_activity_timeline_model(values=values, errors=errors)
    _validate_timeline_label_layout_model(values=values, errors=errors)
    _check(_int(lineage.get("spawn_count")) >= 1, "lineage.spawn_count must be at least 1", errors)
    _check(lineage.get("mode") == "receipt_backed", "lineage.mode must be receipt_backed", errors)
    _check(_int(scoreboard.get("child_spawn_count")) == _int(lineage.get("spawn_count")), "scoreboard child_spawn_count must match lineage.spawn_count", errors)
    _check(len(lanes) >= 2, "lanes must include parent and child lanes", errors)
    _check(_number_or_none(backed.get("playhead_current_x")) == _number_or_none(playhead.get("current_x")), "receipt_backed_values playhead_current_x must match timeline.playhead.current_x", errors)
    _check(_int(backed.get("child_spawn_count")) == _int(lineage.get("spawn_count")), "receipt_backed_values child_spawn_count must match lineage.spawn_count", errors)
    _validate_lineage_render_model(values=values, errors=errors)
    _validate_spawn_gate_model(values=values, errors=errors)
    _validate_selected_lane_model(values=values, errors=errors)
    _validate_outcome_truth_constraints_model(values=values, errors=errors)
    _validate_receipt_backed_value_summary(values=values, errors=errors)
    _check(phase_coverage == _lane_phase_coverage(lanes), "lane_phase_coverage must match lanes[].events/activitySegments phase fields", errors)
    _validate_lane_phase_coverage(lanes=lanes, lineage=lineage, phase_coverage=phase_coverage, errors=errors)
    if check_sources:
        _validate_renderer_values_sources(values=values, errors=errors)

    if errors:
        raise ContractError("\n".join(errors))


def export_ux_data_contract_index_from_summary_path(summary_path: Path) -> dict[str, Any]:
    validate_handoff_summary_path(summary_path, require_data_contract_index=False)
    resolution = resolve_renderer_fixture_from_summary_path(summary_path, require_data_contract_index=False)
    values_path = Path(EXPECTED_RENDERER_VALUES_PATH)
    values = json.loads(values_path.read_text(encoding="utf-8"))
    validate_renderer_values(values, check_sources=True)
    index = {
        "schema": EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA,
        "status": "PASS",
        "battle_id": EXPECTED_CANONICAL_SCENARIO["battle_id"],
        "current_agent_scope": "backend_json_contract_only",
        "purpose": "Backend-owned Battle-004 JSON source index for UX renderers; no React layout or visual parity claims.",
        "canonical_scenario": EXPECTED_CANONICAL_SCENARIO,
        "proof_generation_contract": _proof_generation_contract(),
        "authoritative_renderer_values": str(values_path),
        "authoritative_normalized_fixture": str(resolution["normalized_json"]),
        "supporting_artifacts": {
            "handoff_summary": EXPECTED_HANDOFF_SUMMARY_PATH,
            "renderer_fixture_resolution": EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH,
            "renderer_bundle": EXPECTED_RENDERER_BUNDLE_PATH,
            "renderer_values": EXPECTED_RENDERER_VALUES_PATH,
            "goal_source": EXPECTED_GOAL_SOURCE_PATH,
        },
        "artifact_digests": _ux_data_contract_artifact_digests(
            {
                "authoritative_renderer_values": EXPECTED_RENDERER_VALUES_PATH,
                "authoritative_normalized_fixture": str(resolution["normalized_json"]),
                "renderer_fixture_resolution": EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH,
                "renderer_bundle": EXPECTED_RENDERER_BUNDLE_PATH,
                "goal_source": EXPECTED_GOAL_SOURCE_PATH,
            }
        ),
        "required_validation_commands": sorted(REQUIRED_SUMMARY_VALIDATION_COMMANDS),
        "renderer_value_paths": _renderer_value_paths(),
        "receipt_backed_values": values.get("receipt_backed_values"),
        "timing_contract": _ux_data_contract_timing_contract(values),
        "render_boundary": {
            "ux_may_render": [
                "values from authoritative_renderer_values",
                "receipt replay playhead from timeline.playhead",
                "parent-child collapse from lineage.groups and lane parentId/children fields",
                "Docker replay CTA state from lanes[].replay.cta",
            ],
            "ux_must_not_infer": values.get("forbidden_inferences", []),
            "project_agent_must_not_provide": [
                "React layout",
                "visual mockup parity",
                "CDP screenshot acceptance",
                "UI-only density",
            ],
        },
        "mocked": values.get("mocked"),
        "live_source": values.get("live_source"),
    }
    validate_ux_data_contract_index(index)
    return index


def validate_ux_data_contract_index_schema(
    index: dict[str, Any],
    *,
    schema_path: Path = DEFAULT_UX_DATA_CONTRACT_INDEX_SCHEMA_PATH,
) -> None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover
        raise ContractError("jsonschema is required to validate Battle UX data contract index schema") from exc

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(index), key=lambda error: list(error.path))
    if errors:
        detail = "\n".join(f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors)
        raise ContractError(f"Battle UX data contract index schema validation failed:\n{detail}")


def validate_ux_data_contract_index(index: dict[str, Any]) -> None:
    errors: list[str] = []
    try:
        validate_ux_data_contract_index_schema(index)
    except ContractError as exc:
        errors.append(str(exc))

    _check(index.get("schema") == EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA, f"schema must be {EXPECTED_UX_DATA_CONTRACT_INDEX_SCHEMA}", errors)
    _check(index.get("status") == "PASS", "status must be PASS", errors)
    _check(index.get("battle_id") == "battle-004", "battle_id must be battle-004", errors)
    _check(index.get("current_agent_scope") == "backend_json_contract_only", "current_agent_scope must be backend_json_contract_only", errors)
    _check(index.get("mocked") is False, "mocked must be false", errors)
    _validate_proof_generation_contract(contract=index.get("proof_generation_contract"), errors=errors)

    canonical = index.get("canonical_scenario") if isinstance(index.get("canonical_scenario"), dict) else {}
    for key, expected in EXPECTED_CANONICAL_SCENARIO.items():
        _check(canonical.get(key) == expected, f"canonical_scenario.{key} must be {expected}", errors)

    artifacts = index.get("supporting_artifacts") if isinstance(index.get("supporting_artifacts"), dict) else {}
    _check(index.get("authoritative_renderer_values") == EXPECTED_RENDERER_VALUES_PATH, "authoritative_renderer_values must use the canonical renderer values path", errors)

    required_artifact_paths = {
        "handoff_summary": EXPECTED_HANDOFF_SUMMARY_PATH,
        "renderer_fixture_resolution": EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH,
        "renderer_bundle": EXPECTED_RENDERER_BUNDLE_PATH,
        "renderer_values": EXPECTED_RENDERER_VALUES_PATH,
        "goal_source": EXPECTED_GOAL_SOURCE_PATH,
    }
    for key, expected in required_artifact_paths.items():
        _check(artifacts.get(key) == expected, f"supporting_artifacts.{key} must be {expected}", errors)
        _check(_resolve_battle_path(str(artifacts.get(key) or "")).exists(), f"supporting_artifacts.{key} does not exist", errors)

    _validate_ux_data_contract_artifact_digests(index=index, errors=errors)

    commands = {str(command) for command in index.get("required_validation_commands") or []}
    missing_commands = sorted(REQUIRED_SUMMARY_VALIDATION_COMMANDS - commands)
    _check(not missing_commands, f"required_validation_commands missing required commands: {missing_commands}", errors)

    values_path = _resolve_battle_path(str(index.get("authoritative_renderer_values") or ""))
    if values_path.exists():
        try:
            values = json.loads(values_path.read_text(encoding="utf-8"))
            validate_renderer_values(values, check_sources=True)
            _check(index.get("authoritative_normalized_fixture") == values.get("source_fixture"), "authoritative_normalized_fixture must match renderer values source_fixture", errors)
            _check(
                index.get("proof_generation_contract") == values.get("proof_generation_contract"),
                "proof_generation_contract must match renderer values",
                errors,
            )
            _check(index.get("receipt_backed_values") == values.get("receipt_backed_values"), "receipt_backed_values must match renderer values", errors)
            _check(index.get("timing_contract") == _ux_data_contract_timing_contract(values), "timing_contract must match renderer values", errors)
            _validate_renderer_value_paths(index=index, values=values, errors=errors)
        except (json.JSONDecodeError, ContractError) as exc:
            errors.append(f"authoritative_renderer_values invalid: {exc}")
    else:
        errors.append(f"authoritative_renderer_values does not exist: {values_path}")

    boundary = index.get("render_boundary") if isinstance(index.get("render_boundary"), dict) else {}
    must_not = {str(item) for item in boundary.get("project_agent_must_not_provide") or []}
    for forbidden in ("React layout", "visual mockup parity", "CDP screenshot acceptance", "UI-only density"):
        _check(forbidden in must_not, f"render_boundary.project_agent_must_not_provide missing {forbidden}", errors)

    if errors:
        raise ContractError("\n".join(errors))


def _ux_data_contract_artifact_digests(paths: dict[str, str]) -> dict[str, dict[str, str]]:
    return {
        key: {
            "path": path,
            "sha256": _sha256_file(_resolve_battle_path(path)),
        }
        for key, path in sorted(paths.items())
    }


def _ux_data_contract_timing_contract(values: dict[str, Any]) -> dict[str, Any]:
    receipt_values = values.get("receipt_backed_values") if isinstance(values.get("receipt_backed_values"), dict) else {}
    time_model = values.get("timeline_time_model") if isinstance(values.get("timeline_time_model"), dict) else {}
    elapsed_axis_model = values.get("timeline_elapsed_axis_model") if isinstance(values.get("timeline_elapsed_axis_model"), dict) else {}
    return {
        "schema": "battle.ux_timing_contract.v1",
        "source": "/timeline_time_model",
        "elapsed_axis_source": "/timeline_elapsed_axis_model",
        "mode": time_model.get("mode"),
        "x_axis_mode": time_model.get("x_axis_mode"),
        "x_position_is_elapsed_time": time_model.get("x_position_is_elapsed_time"),
        "elapsed_axis_mode": elapsed_axis_model.get("mode"),
        "elapsed_axis_x_axis_mode": elapsed_axis_model.get("x_axis_mode"),
        "elapsed_axis_x_position_is_elapsed_time": elapsed_axis_model.get("x_position_is_elapsed_time"),
        "elapsed_axis_keyframe_count": elapsed_axis_model.get("keyframe_count"),
        "elapsed_axis_keyframes_are_monotonic": elapsed_axis_model.get("keyframes_are_monotonic"),
        "elapsed_axis_current_elapsed_seconds": receipt_values.get("elapsed_axis_current_elapsed_seconds"),
        "elapsed_axis_current_x": receipt_values.get("elapsed_axis_current_x"),
        "receipt_elapsed_keyframe_count": time_model.get("receipt_elapsed_keyframe_count"),
        "receipt_elapsed_keyframes_are_monotonic_by_x": time_model.get("receipt_elapsed_keyframes_are_monotonic_by_x"),
        "timed_lane_event_count": receipt_values.get("timed_lane_event_count"),
        "lane_event_count_for_timing": receipt_values.get("lane_event_count_for_timing"),
        "complete_elapsed_activity_segment_count": receipt_values.get("complete_elapsed_activity_segment_count"),
        "activity_segment_count_for_timing": receipt_values.get("activity_segment_count_for_timing"),
        "timed_playhead_keyframe_count": receipt_values.get("timed_playhead_keyframe_count"),
        "playhead_elapsed_monotonic_by_x": receipt_values.get("playhead_elapsed_monotonic_by_x"),
        "render_rules": time_model.get("render_rules", []),
        "elapsed_time_axis_requirements": time_model.get("elapsed_time_axis_requirements", []),
    }


def _renderer_value_paths() -> dict[str, str]:
    return {
        "proof_generation_contract": "/proof_generation_contract",
        "spectator_shell": "/spectator_shell",
        "shell": "/shell",
        "battle_clock": "/battle_clock",
        "timeline": "/timeline",
        "timeline_time_model": "/timeline_time_model",
        "timeline_elapsed_axis_model": "/timeline_elapsed_axis_model",
        "timeline_viewport_model": "/timeline_viewport_model",
        "timeline_lane_start_model": "/timeline_lane_start_model",
        "lane_activity_timeline_model": "/lane_activity_timeline_model",
        "timeline_label_layout_model": "/timeline_label_layout_model",
        "lineage": "/lineage",
        "lineage_render_model": "/lineage_render_model",
        "spawn_gate_model": "/spawn_gate_model",
        "selected_lane_model": "/selected_lane_model",
        "outcome_truth_constraints_model": "/outcome_truth_constraints_model",
        "lane_phase_coverage": "/lane_phase_coverage",
        "lanes": "/lanes",
        "events": "/events",
        "blue_patch_actions": "/bluePatchActions",
        "scoreboard": "/scoreboard",
        "leaderboard": "/leaderboard",
        "receipt_backed_values": "/receipt_backed_values",
        "replay_cta_values": "/selected_lane_model/replay_cta",
        "selected_lane_cockpit": "/selected_lane_model/cockpit",
    }


def _proof_generation_contract() -> dict[str, Any]:
    return {
        "schema": "battle.proof_generation_contract.v1",
        "purpose": "Canonical backend command for generating fresh BATTLE-004 parent-spawn receipts before regenerating UX JSON.",
        "canonical_command": EXPECTED_PARENT_SPAWN_PROOF_COMMAND,
        "battle_id": EXPECTED_CANONICAL_SCENARIO["battle_id"],
        "public_entrypoint": EXPECTED_CANONICAL_SCENARIO["public_entrypoint"],
        "cwe": EXPECTED_CANONICAL_SCENARIO["cwe"],
        "hidden_vulnerability_family": EXPECTED_CANONICAL_SCENARIO["hidden_vulnerability_family"],
        "red_workers": 2,
        "blue_workers": 2,
        "spawn_red_child_on_blue_success": True,
        "expected_lineage_mode": "receipt_backed",
        "expected_child_spawn_count_min": 1,
        "output_dir_is_example": True,
        "mocked": False,
        "live": True,
        "proof_mode": EXPECTED_PROOF_MODE,
    }


def _validate_proof_generation_contract(*, contract: Any, errors: list[str]) -> None:
    if not isinstance(contract, dict):
        errors.append("proof_generation_contract must be an object")
        return
    expected = _proof_generation_contract()
    for key, expected_value in expected.items():
        _check(contract.get(key) == expected_value, f"proof_generation_contract.{key} must be {expected_value}", errors)
    _check(
        "arena-parent-spawn-proof battle-004" in str(contract.get("canonical_command") or ""),
        "proof_generation_contract.canonical_command must run arena-parent-spawn-proof battle-004",
        errors,
    )


def _validate_renderer_value_paths(*, index: dict[str, Any], values: dict[str, Any], errors: list[str]) -> None:
    paths = index.get("renderer_value_paths") if isinstance(index.get("renderer_value_paths"), dict) else {}
    expected = _renderer_value_paths()
    _check(paths == expected, "renderer_value_paths must match canonical backend-owned renderer JSON pointer map", errors)
    for name, pointer in expected.items():
        try:
            resolved = _json_pointer_get(values, pointer)
        except KeyError:
            errors.append(f"renderer_value_paths.{name} does not resolve in authoritative_renderer_values: {pointer}")
            continue
        _check(resolved is not None, f"renderer_value_paths.{name} resolves to null: {pointer}", errors)


def _json_pointer_get(payload: Any, pointer: str) -> Any:
    if pointer == "":
        return payload
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    current = payload
    for raw_part in pointer.split("/")[1:]:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(pointer)
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as exc:
                raise KeyError(pointer) from exc
        else:
            raise KeyError(pointer)
    return current


def _validate_ux_data_contract_artifact_digests(*, index: dict[str, Any], errors: list[str]) -> None:
    digests = index.get("artifact_digests") if isinstance(index.get("artifact_digests"), dict) else {}
    expected_paths = {
        "authoritative_renderer_values": EXPECTED_RENDERER_VALUES_PATH,
        "authoritative_normalized_fixture": str(index.get("authoritative_normalized_fixture") or ""),
        "renderer_fixture_resolution": EXPECTED_RENDERER_FIXTURE_RESOLUTION_PATH,
        "renderer_bundle": EXPECTED_RENDERER_BUNDLE_PATH,
        "goal_source": EXPECTED_GOAL_SOURCE_PATH,
    }

    for key, expected_path in expected_paths.items():
        digest = digests.get(key) if isinstance(digests.get(key), dict) else {}
        _check(bool(digest), f"artifact_digests.{key} is required", errors)
        _check(digest.get("path") == expected_path, f"artifact_digests.{key}.path must be {expected_path}", errors)
        path = _resolve_battle_path(expected_path)
        if not path.exists():
            errors.append(f"artifact_digests.{key}.path does not exist: {path}")
            continue
        actual_sha256 = _sha256_file(path)
        _check(
            digest.get("sha256") == actual_sha256,
            f"artifact_digests.{key}.sha256 must match current artifact content",
            errors,
        )


def _renderer_receipt_backed_values(*, fixture: dict[str, Any], ux_contract: dict[str, Any]) -> dict[str, Any]:
    backed = dict(ux_contract.get("receipt_backed_values") if isinstance(ux_contract.get("receipt_backed_values"), dict) else {})
    timeline = fixture.get("timeline") if isinstance(fixture.get("timeline"), dict) else {}
    battle_clock = fixture.get("battle_clock") if isinstance(fixture.get("battle_clock"), dict) else {}
    lineage = fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {}
    lanes = fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else []
    phase_coverage = _lane_phase_coverage(lanes)
    time_model = _timeline_time_model(battle_clock=battle_clock, timeline=timeline)
    elapsed_axis_model = _timeline_elapsed_axis_model(battle_clock=battle_clock, timeline=timeline)
    viewport_model = _timeline_viewport_model(timeline=timeline)
    activity_model = _lane_activity_timeline_model(lanes=lanes, elapsed_axis_model=elapsed_axis_model)
    label_layout_model = _timeline_label_layout_model(lanes=lanes)
    timing_coverage = _timeline_timing_coverage(lanes=lanes, timeline=timeline)

    backed.update(
        {
            "timeline_x_axis_mode": time_model["x_axis_mode"],
            "timeline_x_position_is_elapsed_time": time_model["x_position_is_elapsed_time"],
            "elapsed_axis_x_axis_mode": elapsed_axis_model["x_axis_mode"],
            "elapsed_axis_x_position_is_elapsed_time": elapsed_axis_model["x_position_is_elapsed_time"],
            "elapsed_axis_keyframe_count": elapsed_axis_model["keyframe_count"],
            "elapsed_axis_keyframes_are_monotonic": elapsed_axis_model["keyframes_are_monotonic"],
            "elapsed_axis_current_elapsed_seconds": elapsed_axis_model["playhead"]["current_elapsed_seconds"],
            "elapsed_axis_current_x": elapsed_axis_model["playhead"]["current_x"],
            "timed_lane_event_count": timing_coverage["timed_lane_event_count"],
            "lane_event_count_for_timing": timing_coverage["lane_event_count"],
            "complete_elapsed_activity_segment_count": timing_coverage["complete_elapsed_activity_segment_count"],
            "activity_segment_count_for_timing": timing_coverage["activity_segment_count"],
            "timed_playhead_keyframe_count": timing_coverage["timed_playhead_keyframe_count"],
            "playhead_elapsed_monotonic_by_x": timing_coverage["playhead_elapsed_monotonic_by_x"],
            "round_elapsed_seconds": battle_clock.get("elapsed_seconds"),
            "round_allotted_seconds": battle_clock.get("allotted_seconds"),
            "round_remaining_seconds": battle_clock.get("remaining_seconds"),
            "timeline_viewport_initial_min_x": viewport_model["initial_window"]["min_x"],
            "timeline_viewport_initial_max_x": viewport_model["initial_window"]["max_x"],
            "timeline_viewport_min_zoom": viewport_model["zoom"]["min_zoom"],
            "timeline_viewport_max_zoom": viewport_model["zoom"]["max_zoom"],
            "timeline_playhead_keyframe_count": viewport_model["playhead_follow"]["keyframe_count"],
            "lane_phase_coverage_count": len(phase_coverage),
            "lane_start_model_count": len(_timeline_lane_start_model(lineage=lineage, lanes=lanes, elapsed_axis_model=elapsed_axis_model)["starts"]),
            "lane_activity_segment_count": activity_model["segment_count"],
            "timeline_label_count": label_layout_model["label_count"],
            "timeline_label_collision_group_count": label_layout_model["collision_group_count"],
            "lanes_with_research_count": sum(1 for entry in phase_coverage if entry.get("has_research") is True),
            "lanes_with_spawn_handoff_count": sum(1 for entry in phase_coverage if entry.get("has_spawn_handoff") is True),
            "parent_lane_ids": sorted({str(lane.get("id")) for lane in lanes if isinstance(lane, dict) and lane.get("children") and lane.get("id")}),
            "child_lane_ids": sorted({str(lane.get("id")) for lane in lanes if isinstance(lane, dict) and lane.get("parentId") and lane.get("id")}),
            "spawn_receipt_ids": sorted(
                {
                    str(spawn.get("receipt_id"))
                    for spawn in lineage.get("spawns", [])
                    if isinstance(spawn, dict) and spawn.get("receipt_id")
                }
            ),
        }
    )
    return backed


def _lineage_render_model(*, lineage: dict[str, Any], lanes: list[dict[str, Any]]) -> dict[str, Any]:
    lane_by_id = {str(lane.get("id")): lane for lane in lanes if isinstance(lane, dict) and lane.get("id")}
    groups: list[dict[str, Any]] = []
    connectors: list[dict[str, Any]] = []

    for group in lineage.get("groups", []) if isinstance(lineage.get("groups"), list) else []:
        if not isinstance(group, dict):
            continue
        parent_lane_id = str(group.get("parent_lane_id") or "")
        child_lane_ids = [str(child_id) for child_id in group.get("child_lane_ids", []) if child_id]
        groups.append(
            {
                "group_id": str(group.get("group_id") or f"lineage:{parent_lane_id}"),
                "parent_lane_id": parent_lane_id,
                "child_lane_ids": child_lane_ids,
                "lane_ids": [str(lane_id) for lane_id in group.get("lane_ids", []) if lane_id],
                "collapsible": group.get("collapsible") is True,
                "expanded_by_default": group.get("expanded_by_default") is True,
                "source_spawn_receipt_ids": [str(receipt_id) for receipt_id in group.get("spawn_receipt_ids", []) if receipt_id],
                "proof_mode": group.get("proof_mode"),
            }
        )

    for spawn in lineage.get("spawns", []) if isinstance(lineage.get("spawns"), list) else []:
        if not isinstance(spawn, dict):
            continue
        parent_lane_id = str(spawn.get("parent_lane_id") or "")
        child_lane_id = str(spawn.get("child_lane_id") or "")
        receipt_id = str(spawn.get("receipt_id") or "")
        parent_lane = lane_by_id.get(parent_lane_id, {})
        child_lane = lane_by_id.get(child_lane_id, {})
        parent_event = _find_lane_event(parent_lane, receipt_id=receipt_id, preferred_kind="handoff")
        child_event = _find_lane_event(child_lane, receipt_id=receipt_id, preferred_kind="handoff")
        parent_spawn_x = _number_or_none(spawn.get("spawn_x"))
        child_x_start = _number_or_none(spawn.get("child_x_start"))
        connectors.append(
            {
                "connector_id": f"{parent_lane_id}->{child_lane_id}",
                "parent_lane_id": parent_lane_id,
                "child_lane_id": child_lane_id,
                "parent_event_id": parent_event.get("id"),
                "child_event_id": child_event.get("id"),
                "parent_spawn_x": parent_spawn_x,
                "child_x_start": child_x_start,
                "parent_connector_x": _number_or_none(parent_event.get("x")) if parent_event else parent_spawn_x,
                "child_connector_x": _number_or_none(child_event.get("x")) if child_event else child_x_start,
                "label": str(spawn.get("label") or "SPAWN CHILD"),
                "source_receipt_id": receipt_id,
                "source_receipt_path": spawn.get("receipt_path"),
                "proof_mode": spawn.get("proof_mode"),
            }
        )

    return {
        "schema": "battle.lineage_render_model.v1",
        "mode": "receipt_backed_parent_child",
        "collapse_source": "lineage.groups",
        "connector_source": "lineage.spawns",
        "group_count": len(groups),
        "connector_count": len(connectors),
        "groups": groups,
        "connectors": connectors,
        "render_rules": [
            "Render parent and child lanes from lineage.groups only.",
            "Render connector origin from parent_event_id/source_receipt_id, not from the graph left edge.",
            "Render child lane start from child_x_start and matching child handoff event.",
        ],
    }


def _find_lane_event(lane: dict[str, Any], *, receipt_id: str, preferred_kind: str) -> dict[str, Any]:
    events = lane.get("events") if isinstance(lane.get("events"), list) else []
    for event in events:
        if isinstance(event, dict) and event.get("receiptId") == receipt_id and event.get("kind") == preferred_kind:
            return event
    for event in events:
        if isinstance(event, dict) and event.get("receiptId") == receipt_id:
            return event
    return {}


def _selected_lane_model(*, lineage: dict[str, Any], lanes: list[dict[str, Any]]) -> dict[str, Any]:
    lane_ids = [str(lane.get("id")) for lane in lanes if isinstance(lane, dict) and lane.get("id")]
    selected_lane_id = lane_ids[0] if lane_ids else ""
    selection_strategy = "first_lane"

    child_ids: list[str] = []
    for group in lineage.get("groups", []) if isinstance(lineage.get("groups"), list) else []:
        if isinstance(group, dict):
            child_ids.extend(str(child_id) for child_id in group.get("child_lane_ids", []) if child_id)
    for child_id in child_ids:
        if child_id in lane_ids:
            selected_lane_id = child_id
            selection_strategy = "first_receipt_backed_child_lane"
            break

    selected_lane_index = lane_ids.index(selected_lane_id) if selected_lane_id in lane_ids else 0
    selected_lane = lanes[selected_lane_index] if 0 <= selected_lane_index < len(lanes) and isinstance(lanes[selected_lane_index], dict) else {}
    return {
        "schema": "battle.selected_lane_model.v1",
        "selection_strategy": selection_strategy,
        "lane_id": selected_lane_id,
        "lane_index": selected_lane_index,
        "lane_path": f"/lanes/{selected_lane_index}",
        "cockpit_path": f"/lanes/{selected_lane_index}/cockpit",
        "replay_cta_path": f"/lanes/{selected_lane_index}/replay/cta",
        "cockpit": selected_lane.get("cockpit"),
        "replay_cta": (selected_lane.get("replay") if isinstance(selected_lane.get("replay"), dict) else {}).get("cta"),
        "proof_mode": selected_lane.get("proofMode") or selected_lane.get("proof_mode"),
        "render_rules": [
            "Select the first receipt-backed child lane when lineage groups contain children.",
            "Use lane_index and JSON pointers from this object; do not assume lane 0 is selected.",
            "Use cockpit and replay_cta copies here as backend-owned convenience values only.",
        ],
    }


def _validate_selected_lane_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("selected_lane_model") if isinstance(values.get("selected_lane_model"), dict) else {}
    lineage = values.get("lineage") if isinstance(values.get("lineage"), dict) else {}
    lanes = values.get("lanes") if isinstance(values.get("lanes"), list) else []
    expected = _selected_lane_model(lineage=lineage, lanes=lanes)

    _check(model == expected, "selected_lane_model must be derived from lineage.groups and lanes[]", errors)
    _check(model.get("schema") == "battle.selected_lane_model.v1", "selected_lane_model.schema must be battle.selected_lane_model.v1", errors)
    _check(model.get("selection_strategy") == "first_receipt_backed_child_lane", "selected_lane_model.selection_strategy must select the first receipt-backed child lane", errors)
    _check(isinstance(model.get("lane_id"), str) and bool(model.get("lane_id")), "selected_lane_model.lane_id must be present", errors)
    _check(_int(model.get("lane_index")) >= 0, "selected_lane_model.lane_index must be non-negative", errors)
    _check(isinstance(model.get("cockpit"), dict), "selected_lane_model.cockpit must be an object", errors)
    _check(isinstance(model.get("replay_cta"), dict), "selected_lane_model.replay_cta must be an object", errors)


def _outcome_truth_constraints_model(*, fixture: dict[str, Any]) -> dict[str, Any]:
    events = fixture.get("events") if isinstance(fixture.get("events"), list) else []
    lanes = fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else []
    lineage = fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {}
    scoreboard = fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}
    ux_contract = fixture.get("ux_contract") if isinstance(fixture.get("ux_contract"), dict) else {}
    forbidden_source = ux_contract.get("forbidden_inferences") if isinstance(ux_contract.get("forbidden_inferences"), list) else fixture.get("forbidden_inferences")
    forbidden_inferences = {
        str(item)
        for item in (forbidden_source if isinstance(forbidden_source, list) else [])
        if item
    }
    event_types = {str(event.get("event_type")) for event in events if isinstance(event, dict) and event.get("event_type")}
    blue_success_pairs = [
        pair
        for pair in scoreboard.get("per_pair", [])
        if isinstance(pair, dict) and pair.get("verdict") == "BLUE_SUCCESS"
    ]
    blue_block_events = [event for event in events if isinstance(event, dict) and event.get("event_type") == "blue.blocked_red"]
    replay_ctas = [
        replay.get("cta", {})
        for lane in lanes
        if isinstance(lane, dict)
        for replay in [lane.get("replay") if isinstance(lane.get("replay"), dict) else {}]
    ]
    live_replay_count = sum(1 for lane in lanes if isinstance(lane, dict) and (lane.get("replay") if isinstance(lane.get("replay"), dict) else {}).get("can_execute_now") is True)
    receipt_only_replay_count = sum(1 for cta in replay_ctas if isinstance(cta, dict) and cta.get("state") == "receipt_only")

    def forbidden_entry(*, inference: str, required_event_types: list[str]) -> dict[str, Any]:
        present = sorted(event_type for event_type in required_event_types if event_type in event_types)
        return {
            "allowed": bool(present) and inference not in forbidden_inferences,
            "inference": inference,
            "required_event_types": required_event_types,
            "present_event_types": present,
            "forbidden_inference_present": inference in forbidden_inferences,
            "render_policy": "render_only_when_allowed_true",
        }

    return {
        "schema": "battle.outcome_truth_constraints_model.v1",
        "mode": "receipt_backed_outcome_gates",
        "allowed": {
            "child_lineage": {
                "allowed": _int(lineage.get("spawn_count")) > 0,
                "count": _int(lineage.get("spawn_count")),
                "source": "lineage.spawns",
                "lane_ids": sorted({str(lane.get("id")) for lane in lanes if isinstance(lane, dict) and lane.get("parentId") and lane.get("id")}),
                "render_policy": "render_child_lanes_only_from_lineage_receipts",
            },
            "blue_blocks": {
                "allowed": bool(blue_block_events) and bool(blue_success_pairs),
                "event_count": len(blue_block_events),
                "blue_success_pair_count": len(blue_success_pairs),
                "source": "scoreboard.per_pair + events[blue.blocked_red]",
                "lane_ids": sorted({str(pair.get("red_lane_id")) for pair in blue_success_pairs if pair.get("red_lane_id")}),
                "render_policy": "render_blue_blocks_only_for_BLUE_SUCCESS_pairs",
            },
            "docker_replay_cta": {
                "allowed": any(isinstance(cta, dict) and cta.get("visible") is True for cta in replay_ctas),
                "receipt_only_count": receipt_only_replay_count,
                "executable_count": live_replay_count,
                "source": "lanes[].replay.cta",
                "render_policy": "show_cta_from_replay_cta_state_do_not_imply_execution",
            },
        },
        "forbidden": {
            "blue_kill": forbidden_entry(inference="Blue kill attribution", required_event_types=["blue.kill_confirmed"]),
            "fastest_crash": forbidden_entry(inference="Fastest crash", required_event_types=["tau.fastest_crash", "red.fastest_crash"]),
            "survivor_promotion": forbidden_entry(inference="Survivor promotion", required_event_types=["tau.promoted", "red.promoted"]),
            "live_replay_execution": {
                "allowed": live_replay_count > 0 and "Live stream execution" not in forbidden_inferences,
                "inference": "Live stream execution",
                "required_fields": ["lanes[].replay.can_execute_now"],
                "executable_count": live_replay_count,
                "forbidden_inference_present": "Live stream execution" in forbidden_inferences,
                "render_policy": "execute_only_when_allowed_true",
            },
        },
        "render_rules": [
            "Read outcome permissions from this model before rendering dramatic states.",
            "Do not render forbidden outcomes when allowed is false.",
            "Use allowed.blue_blocks.lane_ids rather than Blue patch presence for block counts.",
            "Use allowed.docker_replay_cta.executable_count before enabling live replay execution.",
        ],
    }


def _validate_outcome_truth_constraints_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("outcome_truth_constraints_model") if isinstance(values.get("outcome_truth_constraints_model"), dict) else {}
    expected = _outcome_truth_constraints_model(fixture=values)
    _check(model == expected, "outcome_truth_constraints_model must be derived from events, scoreboard, lineage, lanes, and ux_contract guards", errors)
    _check(model.get("schema") == "battle.outcome_truth_constraints_model.v1", "outcome_truth_constraints_model.schema must be battle.outcome_truth_constraints_model.v1", errors)
    _check(model.get("mode") == "receipt_backed_outcome_gates", "outcome_truth_constraints_model.mode must be receipt_backed_outcome_gates", errors)
    allowed = model.get("allowed") if isinstance(model.get("allowed"), dict) else {}
    forbidden = model.get("forbidden") if isinstance(model.get("forbidden"), dict) else {}
    child_lineage = allowed.get("child_lineage") if isinstance(allowed.get("child_lineage"), dict) else {}
    blue_blocks = allowed.get("blue_blocks") if isinstance(allowed.get("blue_blocks"), dict) else {}
    replay = allowed.get("docker_replay_cta") if isinstance(allowed.get("docker_replay_cta"), dict) else {}
    _check(child_lineage.get("allowed") is True and _int(child_lineage.get("count")) >= 1, "outcome_truth_constraints_model must allow receipt-backed child lineage", errors)
    _check(blue_blocks.get("allowed") is True and _int(blue_blocks.get("blue_success_pair_count")) >= 1, "outcome_truth_constraints_model must allow only receipt-backed Blue blocks", errors)
    _check(replay.get("allowed") is True and _int(replay.get("receipt_only_count")) >= 1, "outcome_truth_constraints_model must expose receipt-only Docker replay CTA", errors)
    for key in ("blue_kill", "fastest_crash", "survivor_promotion"):
        entry = forbidden.get(key) if isinstance(forbidden.get(key), dict) else {}
        _check(entry.get("allowed") is False, f"outcome_truth_constraints_model forbidden.{key} must be disallowed without receipts", errors)
        _check(entry.get("forbidden_inference_present") is True, f"outcome_truth_constraints_model forbidden.{key} must cite forbidden inference", errors)
    live_replay = forbidden.get("live_replay_execution") if isinstance(forbidden.get("live_replay_execution"), dict) else {}
    _check(live_replay.get("allowed") is False, "outcome_truth_constraints_model live replay execution must be disallowed without executable replay", errors)
    rules = {str(rule) for rule in model.get("render_rules", [])}
    _check(
        "Read outcome permissions from this model before rendering dramatic states." in rules,
        "outcome_truth_constraints_model.render_rules must require model-driven outcomes",
        errors,
    )


def _validate_lineage_render_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("lineage_render_model") if isinstance(values.get("lineage_render_model"), dict) else {}
    lineage = values.get("lineage") if isinstance(values.get("lineage"), dict) else {}
    lanes = values.get("lanes") if isinstance(values.get("lanes"), list) else []
    expected = _lineage_render_model(lineage=lineage, lanes=lanes)

    _check(model == expected, "lineage_render_model must be derived from lineage.spawns and lanes[].events", errors)
    _check(model.get("schema") == "battle.lineage_render_model.v1", "lineage_render_model.schema must be battle.lineage_render_model.v1", errors)
    _check(model.get("mode") == "receipt_backed_parent_child", "lineage_render_model.mode must be receipt_backed_parent_child", errors)
    _check(_int(model.get("group_count")) == _int(lineage.get("spawn_count")), "lineage_render_model.group_count must match lineage.spawn_count", errors)
    _check(_int(model.get("connector_count")) == _int(lineage.get("spawn_count")), "lineage_render_model.connector_count must match lineage.spawn_count", errors)
    connectors = model.get("connectors") if isinstance(model.get("connectors"), list) else []
    lane_ids = {str(lane.get("id")) for lane in lanes if isinstance(lane, dict) and lane.get("id")}
    for connector in connectors:
        if not isinstance(connector, dict):
            errors.append("lineage_render_model.connectors entries must be objects")
            continue
        parent_lane_id = str(connector.get("parent_lane_id") or "")
        child_lane_id = str(connector.get("child_lane_id") or "")
        _check(parent_lane_id in lane_ids, f"lineage_render_model connector parent lane missing: {parent_lane_id}", errors)
        _check(child_lane_id in lane_ids, f"lineage_render_model connector child lane missing: {child_lane_id}", errors)
        _check(isinstance(connector.get("parent_event_id"), str) and bool(connector.get("parent_event_id")), "lineage_render_model connector requires parent_event_id", errors)
        _check(isinstance(connector.get("child_event_id"), str) and bool(connector.get("child_event_id")), "lineage_render_model connector requires child_event_id", errors)
        _check(_number_or_none(connector.get("parent_connector_x")) == _number_or_none(connector.get("parent_spawn_x")), "lineage_render_model parent connector x must match spawn_x", errors)
        _check(_number_or_none(connector.get("child_connector_x")) == _number_or_none(connector.get("child_x_start")), "lineage_render_model child connector x must match child_x_start", errors)


def _spawn_gate_model(
    *,
    lineage: dict[str, Any],
    lanes: list[dict[str, Any]],
    events: list[dict[str, Any]],
    scoreboard: dict[str, Any],
) -> dict[str, Any]:
    lane_by_id = {str(lane.get("id")): lane for lane in lanes if isinstance(lane, dict) and lane.get("id")}
    pair_rows = scoreboard.get("per_pair") if isinstance(scoreboard.get("per_pair"), list) else []
    spawns = lineage.get("spawns") if isinstance(lineage.get("spawns"), list) else []
    gates: list[dict[str, Any]] = []
    for spawn_index, spawn in enumerate(spawns):
        if not isinstance(spawn, dict):
            continue
        parent_lane_id = str(spawn.get("parent_lane_id") or "")
        child_lane_id = str(spawn.get("child_lane_id") or "")
        receipt_id = str(spawn.get("receipt_id") or "")
        parent_lane = lane_by_id.get(parent_lane_id, {})
        child_lane = lane_by_id.get(child_lane_id, {})
        parent_events = parent_lane.get("events") if isinstance(parent_lane.get("events"), list) else []
        child_events = child_lane.get("events") if isinstance(child_lane.get("events"), list) else []
        lane_event_ids = {
            str(event.get("id"))
            for event in [*parent_events, *child_events]
            if isinstance(event, dict) and event.get("id")
        }
        parent_event_id = _first_matching_event_id(
            events=parent_events,
            receipt_id=receipt_id,
            fallback_prefix=f"{parent_lane_id}:spawn:",
        )
        child_event_id = _first_matching_event_id(
            events=child_events,
            receipt_id=receipt_id,
            fallback_prefix=f"{child_lane_id}:spawned-from:",
        )
        blue_success_pairs = [
            {
                "pair_id": str(pair.get("pair_id") or ""),
                "red_lane_id": str(pair.get("red_lane_id") or ""),
                "blue_worker_id": str(pair.get("blue_worker_id") or ""),
                "receipt_id": str(pair.get("receipt_id") or ""),
            }
            for pair in pair_rows
            if isinstance(pair, dict)
            and pair.get("verdict") == "BLUE_SUCCESS"
            and pair.get("red_lane_id") in {parent_lane_id, child_lane_id}
        ]
        required_sources = {
            "parent_lane_exists": bool(parent_lane),
            "child_lane_exists": bool(child_lane),
            "lineage_receipt_present": bool(receipt_id),
            "parent_spawn_event_present": bool(parent_event_id) and parent_event_id in lane_event_ids,
            "child_spawn_event_present": bool(child_event_id) and child_event_id in lane_event_ids,
            "blue_success_pair_count": len(blue_success_pairs),
        }
        renderable = all(
            bool(required_sources[key])
            for key in (
                "parent_lane_exists",
                "child_lane_exists",
                "lineage_receipt_present",
                "parent_spawn_event_present",
                "child_spawn_event_present",
            )
        )
        gates.append(
            {
                "gate_id": receipt_id or f"spawn-gate-{spawn_index + 1}",
                "gate_index": spawn_index,
                "renderable": renderable,
                "parent_lane_id": parent_lane_id,
                "child_lane_id": child_lane_id,
                "parent_event_id": parent_event_id,
                "child_event_id": child_event_id,
                "spawn_receipt_id": receipt_id,
                "spawn_receipt_path": str(spawn.get("receipt_path") or ""),
                "spawn_x": _number_or_none(spawn.get("spawn_x")),
                "child_x_start": _number_or_none(spawn.get("child_x_start")),
                "blue_success_pairs": blue_success_pairs,
                "required_sources": required_sources,
                "render_policy": "render_child_lane_only_when_renderable_true",
                "proof_mode": str(spawn.get("proof_mode") or PROOF_MODE),
            }
        )
    return {
        "schema": "battle.spawn_gate_model.v1",
        "mode": "receipt_backed_spawn_gates",
        "gate_count": len(gates),
        "renderable_gate_count": sum(1 for gate in gates if gate.get("renderable") is True),
        "gates": gates,
        "render_rules": [
            "Render parent-child lanes only from spawn_gate_model.gates where renderable is true.",
            "Use parent_event_id and child_event_id from this model for spawn affordances.",
            "Use required_sources to show why a requested spawn is not renderable.",
        ],
    }


def _first_matching_event_id(*, events: list[Any], receipt_id: str, fallback_prefix: str) -> str:
    for event in events:
        if isinstance(event, dict) and receipt_id and event.get("receiptId") == receipt_id and event.get("id"):
            return str(event["id"])
    for event in events:
        if isinstance(event, dict) and str(event.get("id") or "").startswith(fallback_prefix):
            return str(event["id"])
    return ""


def _validate_spawn_gate_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("spawn_gate_model") if isinstance(values.get("spawn_gate_model"), dict) else {}
    lineage = values.get("lineage") if isinstance(values.get("lineage"), dict) else {}
    lanes = values.get("lanes") if isinstance(values.get("lanes"), list) else []
    events = values.get("events") if isinstance(values.get("events"), list) else []
    scoreboard = values.get("scoreboard") if isinstance(values.get("scoreboard"), dict) else {}
    expected = _spawn_gate_model(lineage=lineage, lanes=lanes, events=events, scoreboard=scoreboard)

    _check(model == expected, "spawn_gate_model must be derived from lineage.spawns, lanes, events, and scoreboard", errors)
    _check(model.get("schema") == "battle.spawn_gate_model.v1", "spawn_gate_model.schema must be battle.spawn_gate_model.v1", errors)
    _check(model.get("mode") == "receipt_backed_spawn_gates", "spawn_gate_model.mode must be receipt_backed_spawn_gates", errors)
    _check(_int(model.get("gate_count")) == _int(lineage.get("spawn_count")), "spawn_gate_model.gate_count must match lineage.spawn_count", errors)
    _check(_int(model.get("renderable_gate_count")) >= 1, "spawn_gate_model must include at least one renderable spawn gate", errors)
    gates = model.get("gates") if isinstance(model.get("gates"), list) else []
    for gate in gates:
        if not isinstance(gate, dict):
            errors.append("spawn_gate_model.gates entries must be objects")
            continue
        _check(gate.get("renderable") is True, f"spawn_gate_model gate {gate.get('gate_id')} must be renderable for the canonical parent-spawn fixture", errors)
        sources = gate.get("required_sources") if isinstance(gate.get("required_sources"), dict) else {}
        for key in ("parent_lane_exists", "child_lane_exists", "lineage_receipt_present", "parent_spawn_event_present", "child_spawn_event_present"):
            _check(sources.get(key) is True, f"spawn_gate_model gate {gate.get('gate_id')} missing required source {key}", errors)
        _check(_int(sources.get("blue_success_pair_count")) >= 1, f"spawn_gate_model gate {gate.get('gate_id')} must cite BLUE_SUCCESS pair context", errors)
    rules = {str(rule) for rule in model.get("render_rules", [])}
    _check(
        "Render parent-child lanes only from spawn_gate_model.gates where renderable is true." in rules,
        "spawn_gate_model.render_rules must require renderable gates",
        errors,
    )


def _validate_receipt_backed_value_summary(*, values: dict[str, Any], errors: list[str]) -> None:
    backed = values.get("receipt_backed_values") if isinstance(values.get("receipt_backed_values"), dict) else {}
    time_model = values.get("timeline_time_model") if isinstance(values.get("timeline_time_model"), dict) else {}
    elapsed_axis_model = values.get("timeline_elapsed_axis_model") if isinstance(values.get("timeline_elapsed_axis_model"), dict) else {}
    viewport_model = values.get("timeline_viewport_model") if isinstance(values.get("timeline_viewport_model"), dict) else {}
    clock = values.get("battle_clock") if isinstance(values.get("battle_clock"), dict) else {}
    lineage = values.get("lineage") if isinstance(values.get("lineage"), dict) else {}
    lanes = values.get("lanes") if isinstance(values.get("lanes"), list) else []
    phase_coverage = values.get("lane_phase_coverage") if isinstance(values.get("lane_phase_coverage"), list) else []
    activity_model = values.get("lane_activity_timeline_model") if isinstance(values.get("lane_activity_timeline_model"), dict) else {}
    label_layout_model = values.get("timeline_label_layout_model") if isinstance(values.get("timeline_label_layout_model"), dict) else {}

    _check(backed.get("timeline_x_axis_mode") == time_model.get("x_axis_mode"), "receipt_backed_values timeline_x_axis_mode must match timeline_time_model.x_axis_mode", errors)
    _check(
        backed.get("timeline_x_position_is_elapsed_time") is time_model.get("x_position_is_elapsed_time"),
        "receipt_backed_values timeline_x_position_is_elapsed_time must match timeline_time_model",
        errors,
    )
    _check(backed.get("elapsed_axis_x_axis_mode") == elapsed_axis_model.get("x_axis_mode"), "receipt_backed_values elapsed_axis_x_axis_mode must match timeline_elapsed_axis_model", errors)
    _check(
        backed.get("elapsed_axis_x_position_is_elapsed_time") is elapsed_axis_model.get("x_position_is_elapsed_time"),
        "receipt_backed_values elapsed_axis_x_position_is_elapsed_time must match timeline_elapsed_axis_model",
        errors,
    )
    _check(backed.get("elapsed_axis_keyframe_count") == elapsed_axis_model.get("keyframe_count"), "receipt_backed_values elapsed_axis_keyframe_count must match timeline_elapsed_axis_model", errors)
    _check(
        backed.get("elapsed_axis_keyframes_are_monotonic") is elapsed_axis_model.get("keyframes_are_monotonic"),
        "receipt_backed_values elapsed_axis_keyframes_are_monotonic must match timeline_elapsed_axis_model",
        errors,
    )
    model_playhead = elapsed_axis_model.get("playhead") if isinstance(elapsed_axis_model.get("playhead"), dict) else {}
    _check(
        backed.get("elapsed_axis_current_elapsed_seconds") == model_playhead.get("current_elapsed_seconds"),
        "receipt_backed_values elapsed_axis_current_elapsed_seconds must match timeline_elapsed_axis_model",
        errors,
    )
    _check(backed.get("elapsed_axis_current_x") == model_playhead.get("current_x"), "receipt_backed_values elapsed_axis_current_x must match timeline_elapsed_axis_model", errors)
    _check(backed.get("round_elapsed_seconds") == clock.get("elapsed_seconds"), "receipt_backed_values round_elapsed_seconds must match battle_clock.elapsed_seconds", errors)
    _check(backed.get("round_allotted_seconds") == clock.get("allotted_seconds"), "receipt_backed_values round_allotted_seconds must match battle_clock.allotted_seconds", errors)
    _check(backed.get("round_remaining_seconds") == clock.get("remaining_seconds"), "receipt_backed_values round_remaining_seconds must match battle_clock.remaining_seconds", errors)
    initial_window = viewport_model.get("initial_window") if isinstance(viewport_model.get("initial_window"), dict) else {}
    zoom = viewport_model.get("zoom") if isinstance(viewport_model.get("zoom"), dict) else {}
    playhead_follow = viewport_model.get("playhead_follow") if isinstance(viewport_model.get("playhead_follow"), dict) else {}
    _check(backed.get("timeline_viewport_initial_min_x") == initial_window.get("min_x"), "receipt_backed_values timeline_viewport_initial_min_x must match timeline_viewport_model", errors)
    _check(backed.get("timeline_viewport_initial_max_x") == initial_window.get("max_x"), "receipt_backed_values timeline_viewport_initial_max_x must match timeline_viewport_model", errors)
    _check(backed.get("timeline_viewport_min_zoom") == zoom.get("min_zoom"), "receipt_backed_values timeline_viewport_min_zoom must match timeline_viewport_model", errors)
    _check(backed.get("timeline_viewport_max_zoom") == zoom.get("max_zoom"), "receipt_backed_values timeline_viewport_max_zoom must match timeline_viewport_model", errors)
    _check(backed.get("timeline_playhead_keyframe_count") == playhead_follow.get("keyframe_count"), "receipt_backed_values timeline_playhead_keyframe_count must match timeline_viewport_model", errors)
    _check(_int(backed.get("lane_phase_coverage_count")) == len(phase_coverage), "receipt_backed_values lane_phase_coverage_count must match lane_phase_coverage length", errors)
    _check(
        _int(backed.get("lane_start_model_count")) == len(_timeline_lane_start_model(lineage=lineage, lanes=lanes, elapsed_axis_model=elapsed_axis_model)["starts"]),
        "receipt_backed_values lane_start_model_count must match timeline_lane_start_model starts",
        errors,
    )
    _check(
        _int(backed.get("lane_activity_segment_count")) == _int(activity_model.get("segment_count")),
        "receipt_backed_values lane_activity_segment_count must match lane_activity_timeline_model",
        errors,
    )
    _check(
        _int(backed.get("timeline_label_count")) == _int(label_layout_model.get("label_count")),
        "receipt_backed_values timeline_label_count must match timeline_label_layout_model",
        errors,
    )
    _check(
        _int(backed.get("timeline_label_collision_group_count")) == _int(label_layout_model.get("collision_group_count")),
        "receipt_backed_values timeline_label_collision_group_count must match timeline_label_layout_model",
        errors,
    )
    _check(
        _int(backed.get("lanes_with_research_count")) == sum(1 for entry in phase_coverage if isinstance(entry, dict) and entry.get("has_research") is True),
        "receipt_backed_values lanes_with_research_count must match lane_phase_coverage",
        errors,
    )
    _check(
        _int(backed.get("lanes_with_spawn_handoff_count")) == sum(1 for entry in phase_coverage if isinstance(entry, dict) and entry.get("has_spawn_handoff") is True),
        "receipt_backed_values lanes_with_spawn_handoff_count must match lane_phase_coverage",
        errors,
    )
    parent_lane_ids = sorted({str(lane.get("id")) for lane in lanes if isinstance(lane, dict) and lane.get("children") and lane.get("id")})
    child_lane_ids = sorted({str(lane.get("id")) for lane in lanes if isinstance(lane, dict) and lane.get("parentId") and lane.get("id")})
    spawn_receipt_ids = sorted(
        {
            str(spawn.get("receipt_id"))
            for spawn in lineage.get("spawns", [])
            if isinstance(spawn, dict) and spawn.get("receipt_id")
        }
    )
    _check(backed.get("parent_lane_ids") == parent_lane_ids, "receipt_backed_values parent_lane_ids must match lanes with children", errors)
    _check(backed.get("child_lane_ids") == child_lane_ids, "receipt_backed_values child_lane_ids must match child lanes", errors)
    _check(backed.get("spawn_receipt_ids") == spawn_receipt_ids, "receipt_backed_values spawn_receipt_ids must match lineage.spawns", errors)


def _timeline_time_model(*, battle_clock: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    keyframes = playhead.get("keyframes") if isinstance(playhead.get("keyframes"), list) else []
    timed_keyframes = [frame for frame in keyframes if isinstance(frame, dict) and _number_or_none(frame.get("elapsed_seconds")) is not None]
    return {
        "schema": "battle.timeline_time_model.v1",
        "mode": "receipt_order_with_round_clock",
        "x_axis_mode": "receipt_order_percent",
        "x_position_is_elapsed_time": False,
        "x_axis_label": "Receipt order",
        "elapsed_time_axis_requirements": [
            "Every lane event must include a numeric elapsed_seconds value from the source receipt.",
            "Every lane activity segment must include numeric start_elapsed_seconds and end_elapsed_seconds values.",
            "Lineage spawn receipts must include numeric spawn_elapsed_seconds and child_start_elapsed_seconds values.",
            "Judge attempts must include numeric started_elapsed_seconds and ended_elapsed_seconds values.",
            "The adapter must validate monotonic elapsed timestamps before setting x_position_is_elapsed_time=true.",
        ],
        "receipt_elapsed_keyframe_count": len(timed_keyframes),
        "receipt_elapsed_keyframes_are_monotonic_by_x": _elapsed_keyframes_are_monotonic_by_x(keyframes),
        "round_clock_source": "battle_clock",
        "round_clock": {
            "elapsed_seconds": battle_clock.get("elapsed_seconds"),
            "allotted_seconds": battle_clock.get("allotted_seconds"),
            "remaining_seconds": battle_clock.get("remaining_seconds"),
            "source_receipt_id": battle_clock.get("source_receipt_id"),
            "proof_mode": battle_clock.get("proof_mode"),
        },
        "playhead": {
            "current_x": playhead.get("current_x"),
            "receipt_elapsed_seconds": playhead.get("elapsed_seconds"),
            "animation_semantics": playhead.get("animation_semantics"),
            "source_receipt_id": playhead.get("source_receipt_id"),
        },
        "render_rules": [
            "Render x positions as receipt-order positions, not wall-clock seconds.",
            "Render round elapsed/allotted/remaining time from round_clock.",
            "Animate the playhead as receipt replay only; do not present it as a live timer.",
        ],
    }


def _timeline_elapsed_axis_model(*, battle_clock: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    source_keyframes = playhead.get("keyframes") if isinstance(playhead.get("keyframes"), list) else []
    timed_keyframes = [
        frame
        for frame in source_keyframes
        if isinstance(frame, dict) and _number_or_none(frame.get("elapsed_seconds")) is not None
    ]
    sorted_keyframes = sorted(
        timed_keyframes,
        key=lambda frame: (
            _number_or_none(frame.get("elapsed_seconds")) or 0.0,
            _number_or_none(frame.get("x")) or 0.0,
            str(frame.get("lane_id") or ""),
            str(frame.get("event_id") or ""),
        ),
    )
    elapsed_values = [_number_or_none(frame.get("elapsed_seconds")) or 0.0 for frame in sorted_keyframes]
    max_elapsed = max(elapsed_values) if elapsed_values else 0.0
    allotted = _number_or_none(battle_clock.get("allotted_seconds"))
    axis_max = allotted if allotted is not None and allotted >= max_elapsed else max_elapsed
    if axis_max <= 0:
        axis_max = 100.0

    keyframes: list[dict[str, Any]] = []
    for frame in sorted_keyframes:
        elapsed = _number_or_none(frame.get("elapsed_seconds")) or 0.0
        keyframes.append(
            {
                "elapsed_seconds": elapsed,
                "x": round((elapsed / axis_max) * 100.0, 6),
                "receipt_order_x": frame.get("x"),
                "lane_id": frame.get("lane_id"),
                "event_id": frame.get("event_id"),
                "kind": frame.get("kind"),
                "label": frame.get("label"),
                "timing_source": frame.get("timing_source"),
                "proof_mode": frame.get("proof_mode"),
            }
        )

    current_frame = keyframes[-1] if keyframes else {}
    return {
        "schema": "battle.timeline_elapsed_axis_model.v1",
        "mode": "receipt_elapsed_axis",
        "x_axis_mode": "elapsed_seconds",
        "x_position_is_elapsed_time": True,
        "axis_min_elapsed_seconds": 0,
        "axis_max_elapsed_seconds": axis_max,
        "axis_source": "timeline.playhead.keyframes[].elapsed_seconds",
        "round_clock_elapsed_seconds": battle_clock.get("elapsed_seconds"),
        "round_clock_allotted_seconds": battle_clock.get("allotted_seconds"),
        "round_clock_remaining_seconds": battle_clock.get("remaining_seconds"),
        "keyframe_count": len(keyframes),
        "keyframes_are_monotonic": bool(keyframes) and [frame["elapsed_seconds"] for frame in keyframes] == sorted(frame["elapsed_seconds"] for frame in keyframes),
        "playhead": {
            "current_elapsed_seconds": current_frame.get("elapsed_seconds"),
            "current_x": current_frame.get("x"),
            "source_event_id": current_frame.get("event_id"),
            "animation_semantics": "receipt_elapsed_replay",
        },
        "keyframes": keyframes,
        "render_rules": [
            "Use timeline_elapsed_axis_model for DAW-style elapsed-time placement.",
            "Use keyframes[].x for elapsed-time playhead animation and keyframes[].receipt_order_x only for legacy receipt-order renderers.",
            "Do not use battle_clock.elapsed_seconds as the final playhead when receipt keyframes extend beyond the clock receipt.",
            "Do not render elapsed-time x positions unless keyframes_are_monotonic is true.",
        ],
    }


def _elapsed_axis_x(elapsed_seconds: Any, axis_max_elapsed_seconds: Any) -> float | None:
    elapsed = _number_or_none(elapsed_seconds)
    axis_max = _number_or_none(axis_max_elapsed_seconds)
    if elapsed is None or axis_max is None or axis_max <= 0:
        return None
    return round((elapsed / axis_max) * 100.0, 6)


def _timeline_timing_coverage(*, lanes: list[dict[str, Any]], timeline: dict[str, Any]) -> dict[str, Any]:
    lane_events = [
        event
        for lane in lanes
        if isinstance(lane, dict)
        for event in lane.get("events", [])
        if isinstance(event, dict)
    ]
    activity_segments = [
        segment
        for lane in lanes
        if isinstance(lane, dict)
        for segment in lane.get("activitySegments", [])
        if isinstance(segment, dict)
    ]
    playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    keyframes = playhead.get("keyframes") if isinstance(playhead.get("keyframes"), list) else []
    return {
        "lane_event_count": len(lane_events),
        "timed_lane_event_count": sum(1 for event in lane_events if _number_or_none(event.get("elapsed_seconds")) is not None),
        "activity_segment_count": len(activity_segments),
        "complete_elapsed_activity_segment_count": sum(
            1
            for segment in activity_segments
            if _number_or_none(segment.get("start_elapsed_seconds")) is not None
            and _number_or_none(segment.get("end_elapsed_seconds")) is not None
        ),
        "playhead_keyframe_count": len([frame for frame in keyframes if isinstance(frame, dict)]),
        "timed_playhead_keyframe_count": sum(
            1
            for frame in keyframes
            if isinstance(frame, dict) and _number_or_none(frame.get("elapsed_seconds")) is not None
        ),
        "playhead_elapsed_monotonic_by_x": _elapsed_keyframes_are_monotonic_by_x(keyframes),
    }


def _elapsed_keyframes_are_monotonic_by_x(keyframes: Any) -> bool:
    if not isinstance(keyframes, list):
        return False
    values: list[float] = []
    for frame in keyframes:
        if not isinstance(frame, dict):
            return False
        elapsed = _number_or_none(frame.get("elapsed_seconds"))
        if elapsed is None:
            return False
        values.append(elapsed)
    return bool(values) and values == sorted(values)


def _timeline_viewport_model(*, timeline: dict[str, Any]) -> dict[str, Any]:
    viewport = timeline.get("viewport") if isinstance(timeline.get("viewport"), dict) else {}
    playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    keyframes = [frame for frame in playhead.get("keyframes", []) if isinstance(frame, dict)]
    keyframe_x_values = [frame.get("x") for frame in keyframes]
    min_x = timeline.get("min_x")
    max_x = timeline.get("max_x")
    initial_min = viewport.get("initial_min_x")
    initial_max = viewport.get("initial_max_x")
    return {
        "schema": "battle.timeline_viewport_model.v1",
        "mode": "receipt_replay_scroll_viewport",
        "scroll_axis": timeline.get("scroll_axis"),
        "supports_pan": timeline.get("supports_pan"),
        "supports_zoom": timeline.get("supports_zoom"),
        "bounds": {
            "min_x": min_x,
            "max_x": max_x,
        },
        "initial_window": {
            "min_x": initial_min,
            "max_x": initial_max,
            "width_x": (
                _number_or_none(initial_max) - _number_or_none(initial_min)
                if _number_or_none(initial_max) is not None and _number_or_none(initial_min) is not None
                else None
            ),
            "source": "timeline.viewport",
            "proof_mode": viewport.get("proof_mode"),
        },
        "zoom": {
            "min_zoom": viewport.get("min_zoom"),
            "max_zoom": viewport.get("max_zoom"),
            "source": "timeline.viewport",
            "proof_mode": viewport.get("proof_mode"),
        },
        "playhead_follow": {
            "mode": "receipt_keyframe_follow",
            "current_x": playhead.get("current_x"),
            "keyframe_count": len(keyframes),
            "keyframe_x_values": keyframe_x_values,
            "source_receipt_id": playhead.get("source_receipt_id"),
            "animation_semantics": playhead.get("animation_semantics"),
            "follow_policy": "keep_current_keyframe_visible_without_claiming_live_time",
            "proof_mode": playhead.get("proof_mode"),
        },
        "pan_policy": {
            "clamp_to_bounds": True,
            "initial_window_source": "timeline.viewport.initial_min_x/max_x",
            "scroll_unit": "receipt_order_x",
        },
        "render_rules": [
            "Render the timeline as a horizontally scrollable receipt-order viewport.",
            "Clamp panning to bounds.min_x and bounds.max_x.",
            "Keep playhead_follow.current_x visible during receipt replay without presenting it as live time.",
            "Use playhead_follow.keyframe_x_values as the only backend-owned animation stops.",
        ],
    }


def _validate_timeline_viewport_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("timeline_viewport_model") if isinstance(values.get("timeline_viewport_model"), dict) else {}
    timeline = values.get("timeline") if isinstance(values.get("timeline"), dict) else {}
    expected = _timeline_viewport_model(timeline=timeline)
    _check(model == expected, "timeline_viewport_model must be derived from timeline.viewport and timeline.playhead", errors)
    _check(model.get("schema") == "battle.timeline_viewport_model.v1", "timeline_viewport_model.schema must be battle.timeline_viewport_model.v1", errors)
    _check(model.get("mode") == "receipt_replay_scroll_viewport", "timeline_viewport_model.mode must be receipt_replay_scroll_viewport", errors)
    _check(model.get("scroll_axis") == "horizontal", "timeline_viewport_model.scroll_axis must be horizontal", errors)
    _check(model.get("supports_pan") is True, "timeline_viewport_model.supports_pan must be true", errors)
    _check(model.get("supports_zoom") is True, "timeline_viewport_model.supports_zoom must be true", errors)
    bounds = model.get("bounds") if isinstance(model.get("bounds"), dict) else {}
    initial = model.get("initial_window") if isinstance(model.get("initial_window"), dict) else {}
    zoom = model.get("zoom") if isinstance(model.get("zoom"), dict) else {}
    playhead_follow = model.get("playhead_follow") if isinstance(model.get("playhead_follow"), dict) else {}
    _check(_number_or_none(bounds.get("min_x")) == _number_or_none(timeline.get("min_x")), "timeline_viewport_model.bounds.min_x must match timeline.min_x", errors)
    _check(_number_or_none(bounds.get("max_x")) == _number_or_none(timeline.get("max_x")), "timeline_viewport_model.bounds.max_x must match timeline.max_x", errors)
    initial_min_x = _number_or_none(initial.get("min_x"))
    initial_max_x = _number_or_none(initial.get("max_x"))
    min_zoom = _number_or_none(zoom.get("min_zoom"))
    max_zoom = _number_or_none(zoom.get("max_zoom"))
    _check(
        initial_min_x is not None and initial_max_x is not None and initial_min_x < initial_max_x,
        "timeline_viewport_model initial window must be increasing",
        errors,
    )
    _check(
        min_zoom is not None and max_zoom is not None and min_zoom < max_zoom,
        "timeline_viewport_model zoom bounds must be increasing",
        errors,
    )
    _check(playhead_follow.get("animation_semantics") == "receipt_replay_only", "timeline_viewport_model playhead animation must be receipt_replay_only", errors)
    _check(playhead_follow.get("follow_policy") == "keep_current_keyframe_visible_without_claiming_live_time", "timeline_viewport_model playhead follow policy must be fail-closed", errors)
    keyframe_x_values = playhead_follow.get("keyframe_x_values") if isinstance(playhead_follow.get("keyframe_x_values"), list) else []
    _check(_int(playhead_follow.get("keyframe_count")) == len(keyframe_x_values), "timeline_viewport_model keyframe_count must match keyframe_x_values", errors)
    if keyframe_x_values:
        _check(playhead_follow.get("current_x") == keyframe_x_values[-1], "timeline_viewport_model current_x must equal final keyframe", errors)
    pan_policy = model.get("pan_policy") if isinstance(model.get("pan_policy"), dict) else {}
    _check(pan_policy.get("clamp_to_bounds") is True, "timeline_viewport_model pan_policy must clamp to bounds", errors)
    rules = {str(rule) for rule in model.get("render_rules", [])}
    _check(
        "Render the timeline as a horizontally scrollable receipt-order viewport." in rules,
        "timeline_viewport_model.render_rules must require horizontal receipt-order scrolling",
        errors,
    )


def _timeline_lane_start_model(*, lineage: dict[str, Any], lanes: list[dict[str, Any]], elapsed_axis_model: dict[str, Any] | None = None) -> dict[str, Any]:
    axis_max = (elapsed_axis_model or {}).get("axis_max_elapsed_seconds")
    spawns_by_child = {
        str(spawn.get("child_lane_id")): spawn
        for spawn in lineage.get("spawns", [])
        if isinstance(spawn, dict) and spawn.get("child_lane_id")
    }
    starts: list[dict[str, Any]] = []
    for lane_index, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            continue
        lane_id = str(lane.get("id") or "")
        parent_lane_id = str(lane.get("parentId") or "")
        spawn = spawns_by_child.get(lane_id, {})
        is_child = bool(parent_lane_id)
        start_event = _find_lane_event(
            lane,
            receipt_id=str(spawn.get("receipt_id") or ""),
            preferred_kind="handoff",
        ) if is_child else {}
        first_segment = next(
            (
                segment
                for segment in lane.get("activitySegments", [])
                if isinstance(segment, dict) and _number_or_none(segment.get("start_elapsed_seconds")) is not None
            ),
            {},
        )
        visible_from_elapsed_seconds = (
            spawn.get("visible_from_elapsed_seconds")
            if is_child and _number_or_none(spawn.get("visible_from_elapsed_seconds")) is not None
            else spawn.get("spawn_elapsed_seconds")
            if is_child and _number_or_none(spawn.get("spawn_elapsed_seconds")) is not None
            else first_segment.get("start_elapsed_seconds")
        )
        first_active_segment_elapsed_seconds = (
            spawn.get("first_active_segment_elapsed_seconds")
            if is_child and _number_or_none(spawn.get("first_active_segment_elapsed_seconds")) is not None
            else spawn.get("child_start_elapsed_seconds")
            if is_child and _number_or_none(spawn.get("child_start_elapsed_seconds")) is not None
            else first_segment.get("start_elapsed_seconds")
        )
        elapsed_start_seconds = visible_from_elapsed_seconds
        elapsed_end_seconds = max(
            [
                value
                for value in (
                    _number_or_none(segment.get("end_elapsed_seconds"))
                    for segment in lane.get("activitySegments", [])
                    if isinstance(segment, dict)
                )
                if value is not None
            ],
            default=None,
        )
        starts.append(
            {
                "lane_id": lane_id,
                "lane_index": lane_index,
                "generation": lane.get("generation"),
                "parent_lane_id": parent_lane_id or None,
                "x_start": lane.get("xStart"),
                "x_end": lane.get("xEnd"),
                "runner_x": lane.get("runnerX"),
                "start_kind": "child_spawn_start" if is_child else "parent_lane_start",
                "start_source": "lineage.spawns[].child_x_start" if is_child else "lane.xStart",
                "line_must_start_at_x": spawn.get("child_x_start") if is_child else lane.get("xStart"),
                "elapsed_start_seconds": elapsed_start_seconds,
                "visible_from_elapsed_seconds": visible_from_elapsed_seconds,
                "first_active_segment_elapsed_seconds": first_active_segment_elapsed_seconds,
                "elapsed_end_seconds": elapsed_end_seconds,
                "elapsed_line_must_start_at_x": _elapsed_axis_x(elapsed_start_seconds, axis_max),
                "elapsed_line_end_x": _elapsed_axis_x(elapsed_end_seconds, axis_max),
                "elapsed_axis_source": "timeline_elapsed_axis_model",
                "source_receipt_id": spawn.get("receipt_id") if is_child else None,
                "source_receipt_path": spawn.get("receipt_path") if is_child else None,
                "source_event_id": start_event.get("id") if start_event else None,
                "pre_start_render_policy": "do_not_draw_exploit_progress_before_x_start",
                "proof_mode": spawn.get("proof_mode") if is_child else lane.get("proofMode"),
            }
        )

    return {
        "schema": "battle.timeline_lane_start_model.v1",
        "mode": "receipt_order_lane_starts",
        "start_count": len(starts),
        "starts": starts,
        "render_rules": [
            "Render each lane line from line_must_start_at_x; do not draw exploit progress before x_start.",
            "For elapsed-time/DAW placement, render each lane line from elapsed_line_must_start_at_x.",
            "Render child lanes from child_spawn_start/source_receipt_id, not from global time zero.",
            "Use lineage_render_model.connectors for parent-to-child origin.",
        ],
    }


def _lane_activity_timeline_model(*, lanes: list[dict[str, Any]], elapsed_axis_model: dict[str, Any] | None = None) -> dict[str, Any]:
    axis_max = (elapsed_axis_model or {}).get("axis_max_elapsed_seconds")
    lane_entries: list[dict[str, Any]] = []
    segment_count = 0
    phases: set[str] = set()

    for lane_index, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            continue
        lane_id = str(lane.get("id") or "")
        segments: list[dict[str, Any]] = []
        for segment_index, segment in enumerate(lane.get("activitySegments", [])):
            if not isinstance(segment, dict):
                continue
            phase = str(segment.get("phase") or "")
            if phase:
                phases.add(phase)
            segments.append(
                {
                    "segment_id": segment.get("id"),
                    "segment_index": segment_index,
                    "phase": phase,
                    "label": segment.get("label"),
                    "start_x": segment.get("start_x"),
                    "end_x": segment.get("end_x"),
                    "start_elapsed_seconds": segment.get("start_elapsed_seconds"),
                    "end_elapsed_seconds": segment.get("end_elapsed_seconds"),
                    "elapsed_start_x": _elapsed_axis_x(segment.get("start_elapsed_seconds"), axis_max),
                    "elapsed_end_x": _elapsed_axis_x(segment.get("end_elapsed_seconds"), axis_max),
                    "elapsed_axis_source": "timeline_elapsed_axis_model",
                    "source_event_id": segment.get("source_event_id"),
                    "proof_mode": segment.get("proof_mode"),
                }
            )
        segment_count += len(segments)
        lane_entries.append(
            {
                "lane_id": lane_id,
                "lane_index": lane_index,
                "parent_lane_id": lane.get("parentId"),
                "x_start": lane.get("xStart"),
                "x_end": lane.get("xEnd"),
                "segment_count": len(segments),
                "segments": segments,
            }
        )

    return {
        "schema": "battle.lane_activity_timeline_model.v1",
        "mode": "receipt_backed_activity_segments",
        "lane_count": len(lane_entries),
        "segment_count": segment_count,
        "phases": sorted(phases),
        "lanes": lane_entries,
        "render_rules": [
            "Render exploit activity labels from lane_activity_timeline_model.lanes[].segments only.",
            "Do not invent research, payload, mutate, trigger, patch, crash, or terminal phases client-side.",
            "Do not draw any segment before its lane x_start.",
            "For elapsed-time/DAW placement, render segments from elapsed_start_x to elapsed_end_x.",
            "Use source_event_id and proof_mode to connect visible activity to receipts.",
        ],
    }


def _validate_lane_activity_timeline_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("lane_activity_timeline_model") if isinstance(values.get("lane_activity_timeline_model"), dict) else {}
    lanes = values.get("lanes") if isinstance(values.get("lanes"), list) else []
    elapsed_axis_model = values.get("timeline_elapsed_axis_model") if isinstance(values.get("timeline_elapsed_axis_model"), dict) else {}
    axis_max = elapsed_axis_model.get("axis_max_elapsed_seconds")
    expected = _lane_activity_timeline_model(lanes=lanes, elapsed_axis_model=elapsed_axis_model)

    _check(model == expected, "lane_activity_timeline_model must be derived from lanes[].activitySegments[]", errors)
    _check(model.get("schema") == "battle.lane_activity_timeline_model.v1", "lane_activity_timeline_model.schema must be battle.lane_activity_timeline_model.v1", errors)
    _check(model.get("mode") == "receipt_backed_activity_segments", "lane_activity_timeline_model.mode must be receipt_backed_activity_segments", errors)
    lane_entries = model.get("lanes") if isinstance(model.get("lanes"), list) else []
    segments = [
        segment
        for lane in lane_entries
        if isinstance(lane, dict)
        for segment in lane.get("segments", [])
        if isinstance(segment, dict)
    ]
    _check(_int(model.get("lane_count")) == len(lane_entries), "lane_activity_timeline_model.lane_count must match lanes", errors)
    _check(_int(model.get("segment_count")) == len(segments), "lane_activity_timeline_model.segment_count must match segments", errors)
    _check(bool(segments), "lane_activity_timeline_model must include activity segments", errors)
    for lane in lane_entries:
        if not isinstance(lane, dict):
            continue
        lane_id = str(lane.get("lane_id") or "")
        lane_x_start = _number_or_none(lane.get("x_start"))
        previous_end = lane_x_start
        for segment in lane.get("segments", []) if isinstance(lane.get("segments"), list) else []:
            if not isinstance(segment, dict):
                errors.append(f"lane_activity_timeline_model lane {lane_id} segments entries must be objects")
                continue
            start_x = _number_or_none(segment.get("start_x"))
            end_x = _number_or_none(segment.get("end_x"))
            start_elapsed_seconds = _number_or_none(segment.get("start_elapsed_seconds"))
            end_elapsed_seconds = _number_or_none(segment.get("end_elapsed_seconds"))
            elapsed_start_x = _number_or_none(segment.get("elapsed_start_x"))
            elapsed_end_x = _number_or_none(segment.get("elapsed_end_x"))
            segment_id = str(segment.get("segment_id") or "")
            _check(isinstance(segment_id, str) and bool(segment_id), f"lane_activity_timeline_model lane {lane_id} requires segment_id", errors)
            _check(isinstance(segment.get("phase"), str) and bool(segment.get("phase")), f"lane_activity_timeline_model {segment_id} requires phase", errors)
            _check(isinstance(segment.get("label"), str) and bool(segment.get("label")), f"lane_activity_timeline_model {segment_id} requires label", errors)
            _check(segment.get("proof_mode") == "receipt_backed_fixture", f"lane_activity_timeline_model {segment_id} proof_mode must be receipt_backed_fixture", errors)
            _check(start_x is not None and end_x is not None and start_x < end_x, f"lane_activity_timeline_model {segment_id} must have increasing x bounds", errors)
            _check(start_elapsed_seconds is not None and end_elapsed_seconds is not None, f"lane_activity_timeline_model {segment_id} requires elapsed segment bounds", errors)
            _check(
                start_elapsed_seconds is not None and end_elapsed_seconds is not None and start_elapsed_seconds <= end_elapsed_seconds,
                f"lane_activity_timeline_model {segment_id} elapsed bounds must be non-decreasing",
                errors,
            )
            _check(elapsed_start_x == _elapsed_axis_x(start_elapsed_seconds, axis_max), f"lane_activity_timeline_model {segment_id} elapsed_start_x must match elapsed axis", errors)
            _check(elapsed_end_x == _elapsed_axis_x(end_elapsed_seconds, axis_max), f"lane_activity_timeline_model {segment_id} elapsed_end_x must match elapsed axis", errors)
            if lane_x_start is not None and start_x is not None:
                _check(start_x >= lane_x_start, f"lane_activity_timeline_model {segment_id} must not start before lane x_start", errors)
            if previous_end is not None and start_x is not None:
                _check(start_x >= previous_end, f"lane_activity_timeline_model lane {lane_id} segments must be sorted", errors)
            previous_end = end_x
    rules = {str(rule) for rule in model.get("render_rules", [])}
    _check(
        "Do not invent research, payload, mutate, trigger, patch, crash, or terminal phases client-side." in rules,
        "lane_activity_timeline_model.render_rules must forbid client-side phase invention",
        errors,
    )
    _check(
        "For elapsed-time/DAW placement, render segments from elapsed_start_x to elapsed_end_x." in rules,
        "lane_activity_timeline_model.render_rules must expose elapsed-axis segment bounds",
        errors,
    )


def _timeline_label_layout_model(*, lanes: list[dict[str, Any]]) -> dict[str, Any]:
    lane_entries: list[dict[str, Any]] = []
    collision_groups: dict[str, dict[str, Any]] = {}
    label_count = 0

    for lane_index, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            continue
        lane_id = str(lane.get("id") or "")
        labels: list[dict[str, Any]] = []
        for event in lane.get("events", []):
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("id") or "")
            label = str(event.get("label") or "")
            collision_group = str(event.get("collision_group") or "")
            if not event_id or not label or not collision_group:
                continue
            label_band = str(event.get("label_band") or "auto")
            marker_priority = _int(event.get("marker_priority"))
            label_entry = {
                "event_id": event_id,
                "kind": event.get("kind"),
                "label": label,
                "x": event.get("x"),
                "order_index": event.get("order_index"),
                "label_band": label_band,
                "collision_group": collision_group,
                "marker_priority": marker_priority,
                "receipt_id": event.get("receiptId"),
                "slot_key": f"{lane_id}:{collision_group}:{label_band}",
                "suppress_when_colliding": marker_priority < 60,
                "proof_mode": event.get("proofMode"),
            }
            labels.append(label_entry)
            label_count += 1

            group = collision_groups.setdefault(
                collision_group,
                {
                    "collision_group": collision_group,
                    "events": [],
                    "lane_ids": set(),
                    "bands": set(),
                },
            )
            group["events"].append(
                {
                    "event_id": event_id,
                    "lane_id": lane_id,
                    "label_band": label_band,
                    "marker_priority": marker_priority,
                    "x": event.get("x"),
                }
            )
            group["lane_ids"].add(lane_id)
            group["bands"].add(label_band)

        lane_entries.append(
            {
                "lane_id": lane_id,
                "lane_index": lane_index,
                "label_count": len(labels),
                "labels": labels,
            }
        )

    normalized_groups: list[dict[str, Any]] = []
    for group_key in sorted(collision_groups):
        group = collision_groups[group_key]
        events = sorted(
            group["events"],
            key=lambda item: (-_int(item.get("marker_priority")), str(item.get("lane_id") or ""), str(item.get("event_id") or "")),
        )
        normalized_groups.append(
            {
                "collision_group": group_key,
                "event_count": len(events),
                "lane_ids": sorted(str(lane_id) for lane_id in group["lane_ids"]),
                "event_ids": [str(event.get("event_id")) for event in events],
                "bands": sorted(str(band) for band in group["bands"]),
                "priority_order": [str(event.get("event_id")) for event in events],
                "layout_policy": "separate_by_label_band_then_priority",
                "proof_mode": "receipt_backed_fixture",
            }
        )

    return {
        "schema": "battle.timeline_label_layout_model.v1",
        "mode": "receipt_event_label_slots",
        "label_count": label_count,
        "collision_group_count": len(normalized_groups),
        "lanes": lane_entries,
        "collision_groups": normalized_groups,
        "render_rules": [
            "Use label_band and collision_group from this model; do not infer label stacking from pixel position alone.",
            "Within a collision_group, render higher marker_priority first and separate upper/lower bands.",
            "If every label cannot be placed cleanly, preserve markers and hide lower-priority text labels first.",
        ],
    }


def _validate_timeline_label_layout_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("timeline_label_layout_model") if isinstance(values.get("timeline_label_layout_model"), dict) else {}
    lanes = values.get("lanes") if isinstance(values.get("lanes"), list) else []
    expected = _timeline_label_layout_model(lanes=lanes)

    _check(model == expected, "timeline_label_layout_model must be derived from lanes[].events[]", errors)
    _check(model.get("schema") == "battle.timeline_label_layout_model.v1", "timeline_label_layout_model.schema must be battle.timeline_label_layout_model.v1", errors)
    _check(model.get("mode") == "receipt_event_label_slots", "timeline_label_layout_model.mode must be receipt_event_label_slots", errors)
    lane_entries = model.get("lanes") if isinstance(model.get("lanes"), list) else []
    groups = model.get("collision_groups") if isinstance(model.get("collision_groups"), list) else []
    labels = [
        label
        for lane in lane_entries
        if isinstance(lane, dict)
        for label in lane.get("labels", [])
        if isinstance(label, dict)
    ]
    _check(_int(model.get("label_count")) == len(labels), "timeline_label_layout_model.label_count must match labels", errors)
    _check(_int(model.get("collision_group_count")) == len(groups), "timeline_label_layout_model.collision_group_count must match collision_groups", errors)
    _check(bool(labels), "timeline_label_layout_model must include event labels", errors)
    for label in labels:
        event_id = str(label.get("event_id") or "")
        _check(label.get("label_band") in {"upper", "lower", "auto"}, f"timeline_label_layout_model {event_id} label_band must be upper/lower/auto", errors)
        _check(isinstance(label.get("collision_group"), str) and bool(label.get("collision_group")), f"timeline_label_layout_model {event_id} requires collision_group", errors)
        _check(_int(label.get("marker_priority")) >= 0, f"timeline_label_layout_model {event_id} requires marker_priority", errors)
        _check(isinstance(label.get("slot_key"), str) and bool(label.get("slot_key")), f"timeline_label_layout_model {event_id} requires slot_key", errors)
        _check(label.get("proof_mode") == "receipt_backed_fixture", f"timeline_label_layout_model {event_id} proof_mode must be receipt_backed_fixture", errors)
    for group in groups:
        if not isinstance(group, dict):
            errors.append("timeline_label_layout_model.collision_groups entries must be objects")
            continue
        event_ids = group.get("event_ids") if isinstance(group.get("event_ids"), list) else []
        priority_order = group.get("priority_order") if isinstance(group.get("priority_order"), list) else []
        _check(group.get("layout_policy") == "separate_by_label_band_then_priority", "timeline_label_layout_model collision group policy must separate by band and priority", errors)
        _check(priority_order == event_ids, "timeline_label_layout_model priority_order must match event_ids", errors)
    rules = {str(rule) for rule in model.get("render_rules", [])}
    _check(
        "Use label_band and collision_group from this model; do not infer label stacking from pixel position alone." in rules,
        "timeline_label_layout_model.render_rules must forbid pixel-only label stacking inference",
        errors,
    )


def _validate_timeline_lane_start_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("timeline_lane_start_model") if isinstance(values.get("timeline_lane_start_model"), dict) else {}
    lineage = values.get("lineage") if isinstance(values.get("lineage"), dict) else {}
    lanes = values.get("lanes") if isinstance(values.get("lanes"), list) else []
    elapsed_axis_model = values.get("timeline_elapsed_axis_model") if isinstance(values.get("timeline_elapsed_axis_model"), dict) else {}
    axis_max = elapsed_axis_model.get("axis_max_elapsed_seconds")
    expected = _timeline_lane_start_model(lineage=lineage, lanes=lanes, elapsed_axis_model=elapsed_axis_model)
    _check(model == expected, "timeline_lane_start_model must be derived from lanes[] and lineage.spawns[]", errors)
    _check(model.get("schema") == "battle.timeline_lane_start_model.v1", "timeline_lane_start_model.schema must be battle.timeline_lane_start_model.v1", errors)
    _check(model.get("mode") == "receipt_order_lane_starts", "timeline_lane_start_model.mode must be receipt_order_lane_starts", errors)
    starts = model.get("starts") if isinstance(model.get("starts"), list) else []
    _check(_int(model.get("start_count")) == len(lanes), "timeline_lane_start_model.start_count must match lanes length", errors)
    child_starts = [start for start in starts if isinstance(start, dict) and start.get("start_kind") == "child_spawn_start"]
    _check(bool(child_starts), "timeline_lane_start_model must include at least one child_spawn_start", errors)
    spawn_by_child = {
        str(spawn.get("child_lane_id")): spawn
        for spawn in lineage.get("spawns", [])
        if isinstance(spawn, dict) and spawn.get("child_lane_id")
    }
    for start in starts:
        if not isinstance(start, dict):
            errors.append("timeline_lane_start_model.starts entries must be objects")
            continue
        lane_id = str(start.get("lane_id") or "")
        elapsed_start_seconds = _number_or_none(start.get("elapsed_start_seconds"))
        elapsed_end_seconds = _number_or_none(start.get("elapsed_end_seconds"))
        elapsed_line_start_x = _number_or_none(start.get("elapsed_line_must_start_at_x"))
        elapsed_line_end_x = _number_or_none(start.get("elapsed_line_end_x"))
        _check(start.get("pre_start_render_policy") == "do_not_draw_exploit_progress_before_x_start", f"timeline_lane_start_model {lane_id} must forbid pre-start progress", errors)
        _check(elapsed_start_seconds is not None, f"timeline_lane_start_model {lane_id} requires elapsed_start_seconds", errors)
        _check(elapsed_end_seconds is not None, f"timeline_lane_start_model {lane_id} requires elapsed_end_seconds", errors)
        _check(elapsed_line_start_x == _elapsed_axis_x(elapsed_start_seconds, axis_max), f"timeline_lane_start_model {lane_id} elapsed_line_must_start_at_x must match elapsed axis", errors)
        _check(elapsed_line_end_x == _elapsed_axis_x(elapsed_end_seconds, axis_max), f"timeline_lane_start_model {lane_id} elapsed_line_end_x must match elapsed axis", errors)
        if start.get("start_kind") == "child_spawn_start":
            spawn = spawn_by_child.get(lane_id, {})
            _check(bool(spawn), f"timeline_lane_start_model child lane missing lineage spawn: {lane_id}", errors)
            _check(start.get("start_source") == "lineage.spawns[].child_x_start", f"timeline_lane_start_model child lane {lane_id} must source start from lineage spawn", errors)
            _check(_number_or_none(start.get("line_must_start_at_x")) == _number_or_none(spawn.get("child_x_start")), f"timeline_lane_start_model child lane {lane_id} start must match lineage child_x_start", errors)
            _check(_number_or_none(start.get("line_must_start_at_x")) == _number_or_none(start.get("x_start")), f"timeline_lane_start_model child lane {lane_id} line start must match lane xStart", errors)
            _check(elapsed_start_seconds == _number_or_none(spawn.get("spawn_elapsed_seconds")), f"timeline_lane_start_model child lane {lane_id} elapsed start must match lineage spawn_elapsed_seconds", errors)
            _check(
                _number_or_none(start.get("visible_from_elapsed_seconds")) == _number_or_none(spawn.get("spawn_elapsed_seconds")),
                f"timeline_lane_start_model child lane {lane_id} visible_from_elapsed_seconds must match lineage spawn_elapsed_seconds",
                errors,
            )
            _check(
                _number_or_none(start.get("first_active_segment_elapsed_seconds")) == _number_or_none(spawn.get("child_start_elapsed_seconds")),
                f"timeline_lane_start_model child lane {lane_id} first_active_segment_elapsed_seconds must match lineage child_start_elapsed_seconds",
                errors,
            )
            _check(start.get("source_receipt_id") == spawn.get("receipt_id"), f"timeline_lane_start_model child lane {lane_id} receipt must match lineage spawn", errors)
            _check(isinstance(start.get("source_event_id"), str) and bool(start.get("source_event_id")), f"timeline_lane_start_model child lane {lane_id} requires source_event_id", errors)
        else:
            _check(start.get("start_kind") == "parent_lane_start", f"timeline_lane_start_model lane {lane_id} start_kind must be parent_lane_start or child_spawn_start", errors)
            _check(start.get("start_source") == "lane.xStart", f"timeline_lane_start_model parent lane {lane_id} must source start from lane.xStart", errors)
            _check(_number_or_none(start.get("line_must_start_at_x")) == _number_or_none(start.get("x_start")), f"timeline_lane_start_model parent lane {lane_id} line start must match lane xStart", errors)
    rules = {str(rule) for rule in model.get("render_rules", [])}
    _check(
        "Render child lanes from child_spawn_start/source_receipt_id, not from global time zero." in rules,
        "timeline_lane_start_model.render_rules must forbid child lanes from global zero",
        errors,
    )
    _check(
        "For elapsed-time/DAW placement, render each lane line from elapsed_line_must_start_at_x." in rules,
        "timeline_lane_start_model.render_rules must expose elapsed-axis lane starts",
        errors,
    )


def _validate_timeline_time_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("timeline_time_model") if isinstance(values.get("timeline_time_model"), dict) else {}
    timeline = values.get("timeline") if isinstance(values.get("timeline"), dict) else {}
    battle_clock = values.get("battle_clock") if isinstance(values.get("battle_clock"), dict) else {}
    playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    clock = model.get("round_clock") if isinstance(model.get("round_clock"), dict) else {}
    model_playhead = model.get("playhead") if isinstance(model.get("playhead"), dict) else {}

    _check(model.get("schema") == "battle.timeline_time_model.v1", "timeline_time_model.schema must be battle.timeline_time_model.v1", errors)
    _check(model.get("mode") == "receipt_order_with_round_clock", "timeline_time_model.mode must be receipt_order_with_round_clock", errors)
    _check(model.get("x_axis_mode") == "receipt_order_percent", "timeline_time_model.x_axis_mode must be receipt_order_percent", errors)
    _check(model.get("x_position_is_elapsed_time") is False, "timeline_time_model.x_position_is_elapsed_time must be false", errors)
    requirements = model.get("elapsed_time_axis_requirements") if isinstance(model.get("elapsed_time_axis_requirements"), list) else []
    _check(
        "Every lane event must include a numeric elapsed_seconds value from the source receipt." in requirements,
        "timeline_time_model.elapsed_time_axis_requirements must require per-event elapsed_seconds receipts",
        errors,
    )
    _check(
        "The adapter must validate monotonic elapsed timestamps before setting x_position_is_elapsed_time=true." in requirements,
        "timeline_time_model.elapsed_time_axis_requirements must require monotonic timestamp validation",
        errors,
    )
    _check(model.get("round_clock_source") == "battle_clock", "timeline_time_model.round_clock_source must be battle_clock", errors)
    for key in ("elapsed_seconds", "allotted_seconds", "remaining_seconds", "source_receipt_id", "proof_mode"):
        _check(clock.get(key) == battle_clock.get(key), f"timeline_time_model.round_clock.{key} must match battle_clock.{key}", errors)
    _check(model_playhead.get("current_x") == playhead.get("current_x"), "timeline_time_model.playhead.current_x must match timeline.playhead.current_x", errors)
    _check(
        model_playhead.get("receipt_elapsed_seconds") == playhead.get("elapsed_seconds"),
        "timeline_time_model.playhead.receipt_elapsed_seconds must match timeline.playhead.elapsed_seconds",
        errors,
    )
    _check(
        model_playhead.get("animation_semantics") == "receipt_replay_only",
        "timeline_time_model.playhead.animation_semantics must be receipt_replay_only",
        errors,
    )
    rules = {str(rule) for rule in model.get("render_rules", [])}
    _check(
        "Render x positions as receipt-order positions, not wall-clock seconds." in rules,
        "timeline_time_model.render_rules must forbid elapsed-time x-axis inference",
        errors,
    )


def _validate_timeline_elapsed_axis_model(*, values: dict[str, Any], errors: list[str]) -> None:
    model = values.get("timeline_elapsed_axis_model") if isinstance(values.get("timeline_elapsed_axis_model"), dict) else {}
    timeline = values.get("timeline") if isinstance(values.get("timeline"), dict) else {}
    battle_clock = values.get("battle_clock") if isinstance(values.get("battle_clock"), dict) else {}
    expected = _timeline_elapsed_axis_model(battle_clock=battle_clock, timeline=timeline)

    _check(model == expected, "timeline_elapsed_axis_model must be derived from timeline.playhead.keyframes and battle_clock", errors)
    _check(model.get("schema") == "battle.timeline_elapsed_axis_model.v1", "timeline_elapsed_axis_model.schema must be battle.timeline_elapsed_axis_model.v1", errors)
    _check(model.get("mode") == "receipt_elapsed_axis", "timeline_elapsed_axis_model.mode must be receipt_elapsed_axis", errors)
    _check(model.get("x_axis_mode") == "elapsed_seconds", "timeline_elapsed_axis_model.x_axis_mode must be elapsed_seconds", errors)
    _check(model.get("x_position_is_elapsed_time") is True, "timeline_elapsed_axis_model.x_position_is_elapsed_time must be true", errors)
    _check(model.get("keyframes_are_monotonic") is True, "timeline_elapsed_axis_model keyframes must be monotonic by elapsed_seconds", errors)
    keyframes = model.get("keyframes") if isinstance(model.get("keyframes"), list) else []
    _check(len(keyframes) >= 2, "timeline_elapsed_axis_model must include at least two keyframes", errors)
    elapsed_values = [_number_or_none(frame.get("elapsed_seconds")) for frame in keyframes if isinstance(frame, dict)]
    _check(all(value is not None for value in elapsed_values), "timeline_elapsed_axis_model keyframes require elapsed_seconds", errors)
    _check(elapsed_values == sorted(elapsed_values), "timeline_elapsed_axis_model keyframes must be sorted by elapsed_seconds", errors)
    for frame in keyframes:
        if not isinstance(frame, dict):
            errors.append("timeline_elapsed_axis_model keyframes entries must be objects")
            continue
        _check(_number_or_none(frame.get("x")) is not None, "timeline_elapsed_axis_model keyframes[].x must be numeric", errors)
        _check(_number_or_none(frame.get("receipt_order_x")) is not None, "timeline_elapsed_axis_model keyframes[].receipt_order_x must preserve legacy x", errors)
    rules = {str(rule) for rule in model.get("render_rules", [])}
    _check(
        "Use timeline_elapsed_axis_model for DAW-style elapsed-time placement." in rules,
        "timeline_elapsed_axis_model.render_rules must identify elapsed-time placement",
        errors,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _lane_phase_coverage(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane_id = str(lane.get("id") or "")
        phases: list[str] = []
        phase_sources: dict[str, list[str]] = {}
        for field in ("activitySegments", "events"):
            items = lane.get(field) if isinstance(lane.get(field), list) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                phase = str(item.get("phase") or "")
                if not phase:
                    continue
                if phase not in phases:
                    phases.append(phase)
                source_id = str(item.get("id") or item.get("source_event_id") or "")
                if source_id:
                    phase_sources.setdefault(phase, []).append(source_id)
        coverage.append(
            {
                "lane_id": lane_id,
                "parent_id": lane.get("parentId"),
                "child_lane_ids": [str(child) for child in lane.get("children", [])] if isinstance(lane.get("children"), list) else [],
                "is_parent": bool(lane.get("children")),
                "is_child": bool(lane.get("parentId")),
                "x_start": lane.get("xStart"),
                "phases": phases,
                "phase_sources": phase_sources,
                "has_research": "research" in phases,
                "has_materialize": "materialize" in phases,
                "has_spawn_handoff": "handoff" in phases,
                "has_patch_gate": "patch_gate" in phases,
                "has_judge_replay": "judge_replay" in phases,
            }
        )
    return coverage


def _validate_lane_phase_coverage(
    *,
    lanes: list[dict[str, Any]],
    lineage: dict[str, Any],
    phase_coverage: list[dict[str, Any]],
    errors: list[str],
) -> None:
    coverage_by_lane = {str(item.get("lane_id")): item for item in phase_coverage if isinstance(item, dict) and item.get("lane_id")}
    parent_lanes = [lane for lane in lanes if isinstance(lane, dict) and lane.get("children")]
    child_lanes = [lane for lane in lanes if isinstance(lane, dict) and lane.get("parentId")]
    _check(bool(parent_lanes), "lane_phase_coverage requires at least one parent lane with children", errors)
    _check(bool(child_lanes), "lane_phase_coverage requires at least one child lane with parentId", errors)

    for lane in parent_lanes:
        lane_id = str(lane.get("id") or "")
        coverage = coverage_by_lane.get(lane_id, {})
        phases = set(coverage.get("phases") or [])
        missing = sorted({"materialize", "research", "payload", "useful_signal", "handoff", "patch_gate", "judge_replay"} - phases)
        _check(not missing, f"lane_phase_coverage parent lane {lane_id} missing phases: {missing}", errors)
        _check(coverage.get("has_research") is True, f"lane_phase_coverage parent lane {lane_id} must expose has_research=true", errors)
        _check(coverage.get("has_spawn_handoff") is True, f"lane_phase_coverage parent lane {lane_id} must expose has_spawn_handoff=true", errors)

    for lane in child_lanes:
        lane_id = str(lane.get("id") or "")
        parent_id = str(lane.get("parentId") or "")
        parent = next((candidate for candidate in lanes if isinstance(candidate, dict) and candidate.get("id") == parent_id), {})
        coverage = coverage_by_lane.get(lane_id, {})
        phases = set(coverage.get("phases") or [])
        missing = sorted({"handoff", "research", "payload", "useful_signal", "patch_gate"} - phases)
        _check(not missing, f"lane_phase_coverage child lane {lane_id} missing phases: {missing}", errors)
        _check(coverage.get("has_research") is True, f"lane_phase_coverage child lane {lane_id} must expose has_research=true", errors)
        _check(coverage.get("has_spawn_handoff") is True, f"lane_phase_coverage child lane {lane_id} must expose has_spawn_handoff=true", errors)
        if isinstance(parent, dict):
            _check(
                _int(lane.get("xStart")) >= _int(parent.get("xStart")),
                f"child lane {lane_id} must not start before parent lane {parent_id}",
                errors,
            )

    lane_by_id = {str(lane.get("id")): lane for lane in lanes if isinstance(lane, dict) and lane.get("id")}
    for spawn in lineage.get("spawns", []) if isinstance(lineage.get("spawns"), list) else []:
        if not isinstance(spawn, dict):
            continue
        child_id = str(spawn.get("child_lane_id") or "")
        child_lane = lane_by_id.get(child_id, {})
        spawn_x = _int(spawn.get("child_x_start") or spawn.get("spawn_x"))
        _check(child_id in lane_by_id, f"lineage spawn child lane {child_id} must exist in lanes", errors)
        _check(
            _int(child_lane.get("xStart")) >= spawn_x,
            f"child lane {child_id} must start at or after its lineage spawn x position",
            errors,
        )


def _validate_renderer_values_sources(*, values: dict[str, Any], errors: list[str]) -> None:
    source_bundle_path = _resolve_battle_path(str(values.get("source_bundle") or ""))
    source_fixture_path = _resolve_battle_path(str(values.get("source_fixture") or ""))
    _check(source_bundle_path.exists(), f"source_bundle does not exist: {source_bundle_path}", errors)
    _check(source_fixture_path.exists(), f"source_fixture does not exist: {source_fixture_path}", errors)
    if not source_bundle_path.exists() or not source_fixture_path.exists():
        return

    try:
        source_bundle = json.loads(source_bundle_path.read_text(encoding="utf-8"))
        source_fixture = json.loads(source_fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"renderer values source is not valid JSON: {exc}")
        return

    bundle_fixture = source_bundle.get("fixture") if isinstance(source_bundle.get("fixture"), dict) else {}
    _check(source_bundle.get("schema") == EXPECTED_RENDERER_BUNDLE_SCHEMA, "source_bundle.schema must be battle.ux_renderer_bundle.v1", errors)
    _check(str(source_bundle.get("normalized_fixture_source") or "") == str(source_fixture_path), "source_bundle.normalized_fixture_source must match source_fixture", errors)
    _check(bundle_fixture == source_fixture, "source_bundle.fixture must match source_fixture JSON", errors)

    for key in (
        "battle_id",
        "scenario",
        "proof_mode",
        "mocked",
        "live_source",
        "round_config",
        "clock",
        "battle_clock",
        "timeline",
        "battle_timeline_control",
        "segments",
        "validation",
        "lineage_request",
        "lineage",
        "lanes",
        "events",
        "proof_blockers",
        "bluePatchActions",
        "scoreboard",
        "leaderboard",
        "receipts",
        "renderer_binding_contract",
    ):
        _check(values.get(key) == source_fixture.get(key), f"renderer values {key} must match source_fixture", errors)


def _resolve_battle_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (BATTLE_SKILL_ROOT / path).resolve()


def validate_fixture(fixture: dict[str, Any]) -> None:
    errors: list[str] = []
    _check(fixture.get("schema") == EXPECTED_SCHEMA, "schema must be battle.normalized_ux_fixture.v1", errors)
    _check(fixture.get("proof_mode") == EXPECTED_PROOF_MODE, "proof_mode must be receipt_backed_fixture", errors)
    _check(isinstance(fixture.get("lanes"), list), "lanes must be a list", errors)
    _check(isinstance(fixture.get("events"), list), "events must be a list", errors)
    _check(isinstance(fixture.get("proof_blockers"), list), "proof_blockers must be a list", errors)
    _check(isinstance(fixture.get("scoreboard"), dict), "scoreboard must be an object", errors)
    _check(isinstance(fixture.get("lineage_request"), dict), "lineage_request must be an object", errors)
    _check(isinstance(fixture.get("lineage"), dict), "lineage must be an object", errors)
    _check(isinstance(fixture.get("ux_contract"), dict), "ux_contract must be an object", errors)
    _check(isinstance(fixture.get("battle_clock"), dict), "battle_clock must be an object", errors)
    _check(isinstance(fixture.get("timeline"), dict), "timeline must be an object", errors)
    _check(isinstance(fixture.get("spectator_shell"), dict), "spectator_shell must be an object", errors)
    _check(isinstance(fixture.get("renderer_binding_contract"), dict), "renderer_binding_contract must be an object", errors)
    _check(isinstance(fixture.get("sprite_theme"), dict), "sprite_theme must be an object", errors)
    _check(isinstance(fixture.get("semantic_replay"), dict), "semantic_replay must be an object", errors)

    scenario = fixture.get("scenario") if isinstance(fixture.get("scenario"), dict) else {}
    public_entrypoint = str(scenario.get("public_entrypoint") or "")
    _check(public_entrypoint.startswith("/"), "scenario.public_entrypoint must be a path, not a method-prefixed route", errors)
    _check(" " not in public_entrypoint, "scenario.public_entrypoint must not contain an HTTP method", errors)

    lanes = fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else []
    events = fixture.get("events") if isinstance(fixture.get("events"), list) else []
    leaderboard = fixture.get("leaderboard") if isinstance(fixture.get("leaderboard"), list) else []
    scoreboard = fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}
    lineage_request = fixture.get("lineage_request") if isinstance(fixture.get("lineage_request"), dict) else {}
    lineage = fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {}
    ux_contract = fixture.get("ux_contract") if isinstance(fixture.get("ux_contract"), dict) else {}
    battle_clock = fixture.get("battle_clock") if isinstance(fixture.get("battle_clock"), dict) else {}
    timeline = fixture.get("timeline") if isinstance(fixture.get("timeline"), dict) else {}
    spectator_shell = fixture.get("spectator_shell") if isinstance(fixture.get("spectator_shell"), dict) else {}
    renderer_bindings = fixture.get("renderer_binding_contract") if isinstance(fixture.get("renderer_binding_contract"), dict) else {}
    sprite_theme = fixture.get("sprite_theme") if isinstance(fixture.get("sprite_theme"), dict) else {}

    lane_by_id = {str(lane.get("id")): lane for lane in lanes if isinstance(lane, dict) and lane.get("id")}
    event_types = [str(event.get("event_type")) for event in events if isinstance(event, dict)]
    spawn_count = _int(lineage.get("spawn_count"))
    scoreboard_spawn_count = _int(scoreboard.get("child_spawn_count"))
    ux_values = ux_contract.get("receipt_backed_values") if isinstance(ux_contract.get("receipt_backed_values"), dict) else {}
    ux_spawn_count = _int(ux_values.get("child_spawn_count"))
    proof_blockers = fixture.get("proof_blockers") if isinstance(fixture.get("proof_blockers"), list) else []

    _check(ux_contract.get("schema") == EXPECTED_UX_CONTRACT_SCHEMA, "ux_contract.schema must be battle.ux_contract.v1", errors)
    _validate_ux_contract_metadata(ux_contract=ux_contract, errors=errors)
    _validate_lineage_request(lineage_request=lineage_request, spawn_count=spawn_count, errors=errors)
    _check(spawn_count == scoreboard_spawn_count == ux_spawn_count, "lineage, scoreboard, and ux_contract child spawn counts must match", errors)
    _check(_int(ux_values.get("lane_count")) == len(lanes), "ux_contract lane_count must match lanes[]", errors)
    _check(_int(ux_values.get("event_count")) == len(events), "ux_contract event_count must match events[]", errors)
    _check(_int(ux_values.get("judge_pair_count")) == len(scoreboard.get("per_pair") or []), "ux_contract judge_pair_count must match scoreboard.per_pair", errors)
    _check(_int(ux_values.get("proof_blocker_count")) == len(proof_blockers), "ux_contract proof_blocker_count must match proof_blockers[]", errors)
    _check(_int(ux_values.get("lineage_group_count")) == _lineage_group_count(lineage), "ux_contract lineage_group_count must match lineage.groups", errors)
    _check(bool(ux_values.get("child_spawn_requested")) == bool(lineage_request.get("requested")), "ux_contract child_spawn_requested must match lineage_request.requested", errors)
    _check(str(ux_values.get("child_spawn_request_status") or "") == str(lineage_request.get("status") or ""), "ux_contract child_spawn_request_status must match lineage_request.status", errors)
    playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    if isinstance(playhead, dict):
        _check(_number_or_none(ux_values.get("playhead_current_x")) == _number_or_none(playhead.get("current_x")), "ux_contract playhead_current_x must match timeline.playhead.current_x", errors)

    _validate_battle_clock(battle_clock=battle_clock, scoreboard=scoreboard, errors=errors)
    _validate_timeline(timeline=timeline, lanes=lanes, events=events, errors=errors)
    _validate_spectator_shell(
        shell=spectator_shell,
        battle_id=str(fixture.get("battle_id") or ""),
        scenario=scenario,
        scoreboard=scoreboard,
        battle_clock=battle_clock,
        events=events,
        errors=errors,
    )
    _validate_actor_visuals(lanes=lanes, sprite_theme=sprite_theme, errors=errors)
    _validate_semantic_scoring_and_replay(fixture=fixture, lanes=lanes, scoreboard=scoreboard, errors=errors)
    _validate_renderer_binding_contract(renderer_bindings, errors=errors)
    _validate_lane_event_layout(lanes=lanes, errors=errors)
    _validate_proof_blockers(proof_blockers=proof_blockers, events=events, errors=errors)

    spawns = lineage.get("spawns") if isinstance(lineage.get("spawns"), list) else []
    groups = lineage.get("groups") if isinstance(lineage.get("groups"), list) else []
    if spawn_count == 0:
        _check(lineage.get("mode") == "missing", "lineage.mode must be missing when spawn_count is zero", errors)
        _check(not groups, "lineage.groups must be empty when spawn_count is zero", errors)
        _check("tau.spawned_child" not in event_types, "tau.spawned_child requires a valid lineage receipt", errors)
        for lane in lanes:
            if isinstance(lane, dict):
                _check("parentId" not in lane, f"lane {lane.get('id')} has parentId without lineage", errors)
                _check("children" not in lane, f"lane {lane.get('id')} has children without lineage", errors)
    else:
        _check(lineage.get("mode") == "receipt_backed", "lineage.mode must be receipt_backed when spawn_count is positive", errors)
        _check(len(spawns) == spawn_count, "lineage.spawns length must equal spawn_count", errors)
        _check(bool(groups), "lineage.groups is required when spawn_count is positive", errors)
        _check("tau.spawned_child" in event_types, "positive lineage.spawn_count requires tau.spawned_child event", errors)
        for spawn in spawns:
            if not isinstance(spawn, dict):
                errors.append("lineage.spawns entries must be objects")
                continue
            _check(spawn.get("schema") == "battle.exploit_spawn.v1", "lineage spawn schema must be battle.exploit_spawn.v1", errors)
            parent_id = str(spawn.get("parent_lane_id") or "")
            child_id = str(spawn.get("child_lane_id") or "")
            parent = lane_by_id.get(parent_id)
            child = lane_by_id.get(child_id)
            _check(spawn.get("spawn_type") in {"strategic_pre_kill", "post_block_handoff", "parallel_pivot", "panic_spawn", "invalid_spawn"}, "lineage spawn_type is invalid", errors)
            _check(bool(spawn.get("parent_exploit_id")), "lineage spawn must include parent_exploit_id", errors)
            _check(bool(spawn.get("child_exploit_id")), "lineage spawn must include child_exploit_id", errors)
            _check(_number_or_none(spawn.get("spawn_confidence")) is not None, "lineage spawn must include numeric spawn_confidence", errors)
            _check(bool(spawn.get("spawn_reason")), "lineage spawn must include spawn_reason", errors)
            threat = spawn.get("threat_assessment") if isinstance(spawn.get("threat_assessment"), dict) else {}
            _check(threat.get("schema") == "battle.exploit_threat_assessment.v1", "lineage spawn threat_assessment schema must be battle.exploit_threat_assessment.v1", errors)
            _check(threat.get("confirmed_kill") is False, "lineage spawn cannot claim confirmed_kill without a kill receipt", errors)
            _check(threat.get("confirmed_blue_scan") in {True, False}, "lineage spawn threat_assessment confirmed_blue_scan must be boolean", errors)
            _check(_number_or_none(threat.get("confidence")) is not None, "lineage spawn threat_assessment confidence must be numeric", errors)
            _check(isinstance(threat.get("signals"), list), "lineage spawn threat_assessment signals must be a list", errors)
            inherited_state = spawn.get("inherited_state") if isinstance(spawn.get("inherited_state"), dict) else {}
            _check(bool(inherited_state), "lineage spawn must include inherited_state", errors)
            _check(bool(spawn.get("mutation_goal")), "lineage spawn must include mutation_goal", errors)
            _check(isinstance(spawn.get("source_receipts"), list) and bool(spawn.get("source_receipts")), "lineage spawn must include source_receipts", errors)
            _check(parent is not None, f"lineage parent lane missing: {parent_id}", errors)
            _check(child is not None, f"lineage child lane missing: {child_id}", errors)
            if isinstance(parent, dict) and isinstance(child, dict):
                _check(child.get("parentId") == parent_id, f"child lane {child_id} parentId must match lineage parent", errors)
                _check(child.get("parent_id") == parent_id, f"child lane {child_id} parent_id must match lineage parent", errors)
                _check(child_id in (parent.get("children") or []), f"parent lane {parent_id} must list child {child_id}", errors)
                _check(_int(child.get("generation")) > _int(parent.get("generation")), f"child lane {child_id} generation must exceed parent generation", errors)
                group_id = f"lineage:{parent_id}"
                _check(parent.get("lineageGroupId") == group_id, f"parent lane {parent_id} lineageGroupId must be {group_id}", errors)
                _check(child.get("lineageGroupId") == group_id, f"child lane {child_id} lineageGroupId must be {group_id}", errors)
                _check(parent.get("collapsible") is True, f"parent lane {parent_id} must be collapsible", errors)
                _check(child.get("collapsible") is False, f"child lane {child_id} must not be a collapsible group root", errors)
            _check(bool(spawn.get("receipt_id")), "lineage spawn must include receipt_id", errors)
        _validate_lineage_groups(groups=groups, lane_by_id=lane_by_id, errors=errors)

    pair_successes = {
        str(pair.get("red_lane_id"))
        for pair in (scoreboard.get("per_pair") or [])
        if isinstance(pair, dict) and pair.get("verdict") == "BLUE_SUCCESS"
    }
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") == "blue.blocked_red":
            targets = event.get("target_actor_ids") if isinstance(event.get("target_actor_ids"), list) else []
            _check(any(str(target) in pair_successes for target in targets), f"blue.blocked_red {event.get('id')} must target a BLUE_SUCCESS pair", errors)

    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        _validate_lane_cockpit(lane=lane, errors=errors)
        replay = lane.get("replay")
        if isinstance(replay, dict):
            _validate_replay_contract(lane=lane, replay=replay, errors=errors)

    forbidden_without_receipts = {
        "blue.kill_confirmed": "Blue kill attribution",
        "tau.fastest_crash": "Fastest crash",
        "red.fastest_crash": "Fastest crash",
        "tau.promoted": "Survivor promotion",
        "red.promoted": "Survivor promotion",
    }
    forbidden_inferences = ux_contract.get("forbidden_inferences") if isinstance(ux_contract.get("forbidden_inferences"), list) else []
    for event_type, inference in forbidden_without_receipts.items():
        if event_type in event_types:
            _check(inference not in forbidden_inferences, f"{event_type} cannot be both emitted and forbidden", errors)

    terminal_state_requirements = {
        "killed": {"blue.kill_confirmed", "tau.killed", "red.killed"},
        "fastest_crash": {"tau.fastest_crash", "red.fastest_crash"},
        "promoted": {"tau.promoted", "red.promoted"},
    }
    event_type_set = set(event_types)
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        for field in ("terminal", "runnerState"):
            state = str(lane.get(field) or "")
            required_events = terminal_state_requirements.get(state)
            if required_events:
                _check(
                    bool(event_type_set & required_events),
                    f"lane {lane.get('id')} {field}={state} requires one of {sorted(required_events)}",
                    errors,
                )
    for entry in leaderboard:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "")
        required_events = terminal_state_requirements.get(status)
        if required_events:
            _check(
                bool(event_type_set & required_events),
                f"leaderboard entry {entry.get('laneId')} status={status} requires one of {sorted(required_events)}",
                errors,
            )

    if errors:
        raise ContractError("\n".join(errors))


def _compare_fixture_summary(
    *,
    fixture_key: str,
    fixture: dict[str, Any],
    fixture_summary: dict[str, Any],
    summary: dict[str, Any],
    errors: list[str],
) -> None:
    lineage_request = fixture.get("lineage_request") if isinstance(fixture.get("lineage_request"), dict) else {}
    lineage = fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {}
    scoreboard = fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}
    fixture_lineage_request = fixture_summary.get("lineage_request") if isinstance(fixture_summary.get("lineage_request"), dict) else {}
    fixture_lineage = fixture_summary.get("lineage") if isinstance(fixture_summary.get("lineage"), dict) else {}
    fixture_scoreboard = fixture_summary.get("scoreboard") if isinstance(fixture_summary.get("scoreboard"), dict) else {}
    timeline = fixture.get("timeline") if isinstance(fixture.get("timeline"), dict) else {}
    fixture_timeline = fixture_summary.get("timeline") if isinstance(fixture_summary.get("timeline"), dict) else {}

    _check(fixture.get("battle_id") == summary.get("battle_id"), f"{fixture_key} battle_id must match summary battle_id", errors)
    _check(fixture.get("mocked") == fixture_summary.get("mocked"), f"{fixture_key} mocked must match fixture", errors)
    _check(fixture.get("live_source") == fixture_summary.get("live_source"), f"{fixture_key} live_source must match fixture", errors)
    _check(fixture.get("status") == fixture_summary.get("status"), f"{fixture_key} status must match fixture", errors)
    for key in ("requested", "mode", "status", "receipt"):
        _check(
            lineage_request.get(key) == fixture_lineage_request.get(key),
            f"{fixture_key} lineage_request.{key} must match fixture",
            errors,
        )
    for key in ("mode", "spawn_count", "parent_lane_ids", "child_lane_ids"):
        _check(
            lineage.get(key) == fixture_lineage.get(key),
            f"{fixture_key} lineage.{key} must match fixture",
            errors,
        )
    _check(
        scoreboard.get("child_spawn_count") == fixture_scoreboard.get("child_spawn_count"),
        f"{fixture_key} scoreboard.child_spawn_count must match fixture",
        errors,
    )
    _compare_timeline_summary(fixture_key=fixture_key, timeline=timeline, fixture_timeline=fixture_timeline, errors=errors)


def _compare_timeline_summary(
    *,
    fixture_key: str,
    timeline: dict[str, Any],
    fixture_timeline: dict[str, Any],
    errors: list[str],
) -> None:
    _check(timeline.get("mode") == fixture_timeline.get("mode"), f"{fixture_key} timeline.mode must match fixture", errors)
    _check(timeline.get("lane_count") == fixture_timeline.get("lane_count"), f"{fixture_key} timeline.lane_count must match fixture", errors)
    _check(timeline.get("event_count") == fixture_timeline.get("event_count"), f"{fixture_key} timeline.event_count must match fixture", errors)
    _check(timeline.get("supports_pan") == fixture_timeline.get("supports_pan"), f"{fixture_key} timeline.supports_pan must match fixture", errors)
    _check(timeline.get("supports_zoom") == fixture_timeline.get("supports_zoom"), f"{fixture_key} timeline.supports_zoom must match fixture", errors)

    playhead = timeline.get("playhead") if isinstance(timeline.get("playhead"), dict) else {}
    summary_playhead = fixture_timeline.get("playhead") if isinstance(fixture_timeline.get("playhead"), dict) else {}
    keyframes = playhead.get("keyframes") if isinstance(playhead.get("keyframes"), list) else []
    expected_keyframe_x_values = [frame.get("x") for frame in keyframes if isinstance(frame, dict)]
    _check(playhead.get("mode") == summary_playhead.get("mode"), f"{fixture_key} timeline.playhead.mode must match fixture", errors)
    _check(playhead.get("current_x") == summary_playhead.get("current_x"), f"{fixture_key} timeline.playhead.current_x must match fixture", errors)
    _check(playhead.get("elapsed_seconds") == summary_playhead.get("elapsed_seconds"), f"{fixture_key} timeline.playhead.elapsed_seconds must match fixture", errors)
    _check(playhead.get("source_receipt_id") == summary_playhead.get("source_receipt_id"), f"{fixture_key} timeline.playhead.source_receipt_id must match fixture", errors)
    _check(playhead.get("animation_semantics") == summary_playhead.get("animation_semantics"), f"{fixture_key} timeline.playhead.animation_semantics must match fixture", errors)
    _check(len(keyframes) == summary_playhead.get("keyframe_count"), f"{fixture_key} timeline.playhead.keyframe_count must match fixture", errors)
    _check(
        expected_keyframe_x_values == summary_playhead.get("keyframe_x_values"),
        f"{fixture_key} timeline.playhead.keyframe_x_values must match fixture",
        errors,
    )

    viewport = timeline.get("viewport") if isinstance(timeline.get("viewport"), dict) else {}
    summary_viewport = fixture_timeline.get("viewport") if isinstance(fixture_timeline.get("viewport"), dict) else {}
    for key in ("initial_min_x", "initial_max_x", "min_zoom", "max_zoom", "proof_mode"):
        _check(viewport.get(key) == summary_viewport.get(key), f"{fixture_key} timeline.viewport.{key} must match fixture", errors)


def _validate_summary_source_contract(*, summary: dict[str, Any], errors: list[str]) -> None:
    canonical = summary.get("canonical_scenario")
    if not isinstance(canonical, dict):
        errors.append("summary.canonical_scenario must be an object")
        return
    for key in ("public_entrypoint", "cwe", "hidden_vulnerability_family"):
        _check(
            canonical.get(key) == EXPECTED_CANONICAL_SCENARIO[key],
            f"summary.canonical_scenario.{key} must be {EXPECTED_CANONICAL_SCENARIO[key]}",
            errors,
        )
    _check(
        str(canonical.get("public_entrypoint") or "").startswith("/"),
        "summary.canonical_scenario.public_entrypoint must be path-only",
        errors,
    )


def _validate_goal_source_contract(*, summary: dict[str, Any], errors: list[str]) -> None:
    contract = summary.get("goal_source_contract")
    if not isinstance(contract, dict):
        errors.append("summary.goal_source_contract must be an object")
        return
    _check(contract.get("source") == EXPECTED_GOAL_SOURCE_PATH, f"summary.goal_source_contract.source must be {EXPECTED_GOAL_SOURCE_PATH}", errors)
    goal_source_path = Path(str(contract.get("source") or ""))
    if not goal_source_path.exists():
        errors.append(f"summary.goal_source_contract.source does not exist: {goal_source_path}")
    else:
        goal_text = goal_source_path.read_text(encoding="utf-8")
        missing_phrases = sorted(phrase for phrase in REQUIRED_GOAL_SOURCE_PHRASES if phrase not in goal_text)
        _check(not missing_phrases, f"summary.goal_source_contract.source missing required GOAL.md phrases: {missing_phrases}", errors)
    _check(contract.get("canonical_battle_id") == EXPECTED_CANONICAL_SCENARIO["battle_id"], "summary.goal_source_contract.canonical_battle_id must be battle-004", errors)
    _check(contract.get("canonical_public_entrypoint") == EXPECTED_CANONICAL_SCENARIO["public_entrypoint"], "summary.goal_source_contract.canonical_public_entrypoint must be /api/import-zip", errors)
    _check(contract.get("canonical_cwe") == EXPECTED_CANONICAL_SCENARIO["cwe"], "summary.goal_source_contract.canonical_cwe must be CWE-22", errors)
    _check(
        contract.get("canonical_vulnerability_family") == EXPECTED_CANONICAL_SCENARIO["hidden_vulnerability_family"],
        "summary.goal_source_contract.canonical_vulnerability_family must be Zip Slip path traversal",
        errors,
    )
    _check(contract.get("current_agent_scope") == "backend_json_contract_only", "summary.goal_source_contract.current_agent_scope must be backend_json_contract_only", errors)
    must_provide = contract.get("must_provide")
    if not isinstance(must_provide, list):
        errors.append("summary.goal_source_contract.must_provide must be a list")
    else:
        required_provide = {
            "Arena/Tau/Judge proof receipts for canonical BATTLE-004",
            "fail-closed normalized JSON for the UX renderer",
            "spectator_shell header/fact/score/ticker values",
            "timeline playhead/viewport values",
            "lineage and lane parent/child collapse values",
            "lane cockpit values",
            "lane replay CTA state",
        }
        missing = sorted(required_provide - {str(item) for item in must_provide})
        _check(not missing, f"summary.goal_source_contract.must_provide missing required items: {missing}", errors)
    must_not_provide = contract.get("must_not_provide")
    if not isinstance(must_not_provide, list):
        errors.append("summary.goal_source_contract.must_not_provide must be a list")
    else:
        required_must_not = {
            "React layout",
            "visual mockup parity",
            "dashboard styling",
            "CDP screenshot acceptance",
            "UI-only density",
            "invented child lanes, kills, fastest crash, promotion, live replay, or Blue block counts",
        }
        missing = sorted(required_must_not - {str(item) for item in must_not_provide})
        _check(not missing, f"summary.goal_source_contract.must_not_provide missing required items: {missing}", errors)


def _validate_fixture_matches_source_contract(
    *,
    fixture_key: str,
    fixture: dict[str, Any],
    summary: dict[str, Any],
    errors: list[str],
) -> None:
    canonical = summary.get("canonical_scenario") if isinstance(summary.get("canonical_scenario"), dict) else {}
    scenario = fixture.get("scenario") if isinstance(fixture.get("scenario"), dict) else {}
    _check(fixture.get("battle_id") == EXPECTED_CANONICAL_SCENARIO["battle_id"], f"{fixture_key} battle_id must be battle-004", errors)
    for key in ("public_entrypoint", "cwe", "hidden_vulnerability_family"):
        _check(
            scenario.get(key) == canonical.get(key) == EXPECTED_CANONICAL_SCENARIO[key],
            f"{fixture_key} scenario.{key} must match canonical_scenario.{key}",
            errors,
        )
    shell = fixture.get("spectator_shell") if isinstance(fixture.get("spectator_shell"), dict) else {}
    expected_title = f"{EXPECTED_CANONICAL_SCENARIO['battle_id'].upper()} · POST {EXPECTED_CANONICAL_SCENARIO['public_entrypoint']}"
    _check(shell.get("battle_title") == expected_title, f"{fixture_key} spectator_shell.battle_title must match canonical source", errors)


def _check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _validate_ux_contract_metadata(*, ux_contract: dict[str, Any], errors: list[str]) -> None:
    authoritative_fields = ux_contract.get("authoritative_fields")
    if not isinstance(authoritative_fields, dict):
        errors.append("ux_contract.authoritative_fields must be an object")
    else:
        missing = sorted(REQUIRED_AUTHORITATIVE_FIELDS - set(authoritative_fields))
        _check(not missing, f"ux_contract.authoritative_fields missing keys: {missing}", errors)

    render_guards = ux_contract.get("required_render_guards")
    if not isinstance(render_guards, list):
        errors.append("ux_contract.required_render_guards must be a list")
    else:
        missing = sorted(REQUIRED_RENDER_GUARDS - {str(item) for item in render_guards})
        _check(not missing, f"ux_contract.required_render_guards missing required guards: {missing}", errors)

    forbidden = ux_contract.get("forbidden_inferences")
    if not isinstance(forbidden, list):
        errors.append("ux_contract.forbidden_inferences must be a list")
    else:
        missing = sorted(REQUIRED_FORBIDDEN_INFERENCES - {str(item) for item in forbidden})
        _check(not missing, f"ux_contract.forbidden_inferences missing required items: {missing}", errors)


def _validate_proof_blockers(*, proof_blockers: list[Any], events: list[Any], errors: list[str]) -> None:
    for index, proof_blocker in enumerate(proof_blockers):
        label = f"proof_blockers[{index}]"
        if not isinstance(proof_blocker, dict):
            errors.append(f"{label} must be an object")
            continue
        blocker = proof_blocker.get("blocker")
        _check(proof_blocker.get("schema") == "battle.proof_blocker.v1", f"{label}.schema must be battle.proof_blocker.v1", errors)
        _check(proof_blocker.get("team") in {"red", "blue"}, f"{label}.team must be red or blue", errors)
        _check(bool(proof_blocker.get("worker_id")), f"{label}.worker_id is required", errors)
        _check(bool(proof_blocker.get("receipt_id")), f"{label}.receipt_id is required", errors)
        _check(bool(proof_blocker.get("receipt_path")), f"{label}.receipt_path is required", errors)
        _check(proof_blocker.get("proof_mode") == EXPECTED_PROOF_MODE, f"{label}.proof_mode must be {EXPECTED_PROOF_MODE}", errors)
        if proof_blocker.get("team") == "red":
            _check(bool(proof_blocker.get("lane_id")), f"{label}.lane_id is required for red blockers", errors)
        if proof_blocker.get("team") == "blue":
            _check(bool(proof_blocker.get("action_id")), f"{label}.action_id is required for blue blockers", errors)
        if not isinstance(blocker, dict):
            errors.append(f"{label}.blocker must be an object")
            continue
        _check(blocker.get("schema") == "battle.worker_blocker.v1", f"{label}.blocker.schema must be battle.worker_blocker.v1", errors)
        _check(bool(blocker.get("kind")), f"{label}.blocker.kind is required", errors)
        _check(bool(blocker.get("message")), f"{label}.blocker.message is required", errors)
        _check(bool(blocker.get("receipt_path")), f"{label}.blocker.receipt_path is required", errors)
        _check(blocker.get("proof_mode") == EXPECTED_PROOF_MODE, f"{label}.blocker.proof_mode must be {EXPECTED_PROOF_MODE}", errors)
        _check(str(blocker.get("receipt_path") or "") == str(proof_blocker.get("receipt_path") or ""), f"{label}.receipt_path must match blocker.receipt_path", errors)


def _validate_lineage_request(*, lineage_request: dict[str, Any], spawn_count: int, errors: list[str]) -> None:
    _check(
        lineage_request.get("schema") == "battle.lineage_request.v1",
        "lineage_request.schema must be battle.lineage_request.v1",
        errors,
    )
    _check(
        lineage_request.get("proof_mode") == EXPECTED_PROOF_MODE,
        "lineage_request.proof_mode must be receipt_backed_fixture",
        errors,
    )
    status = str(lineage_request.get("status") or "")
    requested = bool(lineage_request.get("requested"))
    receipt = lineage_request.get("receipt")
    _check(status in {"NOT_REQUESTED", "NOT_PROVEN", "PASS"}, "lineage_request.status must be NOT_REQUESTED, NOT_PROVEN, or PASS", errors)
    _check(isinstance(lineage_request.get("mode"), str) and bool(lineage_request.get("mode")), "lineage_request.mode is required", errors)
    _check(isinstance(lineage_request.get("condition"), str) and bool(lineage_request.get("condition")), "lineage_request.condition is required", errors)
    if status == "NOT_REQUESTED":
        _check(requested is False, "lineage_request.requested must be false when status is NOT_REQUESTED", errors)
        _check(receipt is None, "lineage_request.receipt must be null when status is NOT_REQUESTED", errors)
        _check(spawn_count == 0, "lineage_request NOT_REQUESTED cannot have child spawns", errors)
    elif status == "NOT_PROVEN":
        _check(requested is True, "lineage_request.requested must be true when status is NOT_PROVEN", errors)
        _check(spawn_count == 0, "lineage_request NOT_PROVEN cannot authorize child spawns", errors)
    elif status == "PASS":
        _check(requested is True, "lineage_request.requested must be true when status is PASS", errors)
        _check(isinstance(receipt, str) and bool(receipt), "lineage_request PASS requires a lineage receipt", errors)
        _check(spawn_count > 0, "lineage_request PASS requires positive lineage.spawn_count", errors)


def _validate_renderer_binding_contract(bindings: dict[str, Any], *, errors: list[str]) -> None:
    _check(
        bindings.get("schema") == "battle.renderer_binding_contract.v1",
        "renderer_binding_contract.schema must be battle.renderer_binding_contract.v1",
        errors,
    )
    _check(
        bindings.get("proof_mode") == EXPECTED_PROOF_MODE,
        "renderer_binding_contract.proof_mode must be receipt_backed_fixture",
        errors,
    )
    for section, expected_paths in EXPECTED_RENDERER_BINDING_PATHS.items():
        actual = bindings.get(section)
        if not isinstance(actual, dict):
            errors.append(f"renderer_binding_contract.{section} must be an object")
            continue
        for key, expected_path in expected_paths.items():
            _check(
                actual.get(key) == expected_path,
                f"renderer_binding_contract.{section}.{key} must be {expected_path}",
                errors,
            )
    moving_playhead = bindings.get("moving_playhead") if isinstance(bindings.get("moving_playhead"), dict) else {}
    render_rule = str(moving_playhead.get("render_rule") or "")
    _check(
        "receipt replay" in render_rule and "live stream" in render_rule,
        "renderer_binding_contract.moving_playhead.render_rule must preserve receipt replay boundary",
        errors,
    )
    elapsed_axis = bindings.get("elapsed_timeline_axis") if isinstance(bindings.get("elapsed_timeline_axis"), dict) else {}
    elapsed_render_rule = str(elapsed_axis.get("render_rule") or "")
    _check(
        "elapsed-time/DAW-style placement" in elapsed_render_rule and "legacy receipt-order renderers" in elapsed_render_rule,
        "renderer_binding_contract.elapsed_timeline_axis.render_rule must separate elapsed-axis placement from legacy receipt order",
        errors,
    )


def _validate_battle_clock(*, battle_clock: dict[str, Any], scoreboard: dict[str, Any], errors: list[str]) -> None:
    mode = battle_clock.get("mode")
    _check(mode in {"receipt_elapsed", "fixture_static", "missing"}, "battle_clock.mode must be receipt_elapsed, fixture_static, or missing", errors)
    _check(mode != "live_stream", "battle_clock.mode must not claim live_stream without live stream receipts", errors)
    _check(bool(battle_clock.get("source_receipt_id")), "battle_clock.source_receipt_id is required", errors)
    _check(battle_clock.get("proof_mode") == EXPECTED_PROOF_MODE, "battle_clock.proof_mode must be receipt_backed_fixture", errors)

    elapsed = _number_or_none(battle_clock.get("elapsed_seconds"))
    allotted = _number_or_none(battle_clock.get("allotted_seconds"))
    remaining = _number_or_none(battle_clock.get("remaining_seconds"))
    _check(elapsed is None or elapsed >= 0, "battle_clock.elapsed_seconds must be non-negative when present", errors)
    _check(allotted is None or allotted > 0, "battle_clock.allotted_seconds must be positive when present", errors)
    _check(remaining is None or remaining >= 0, "battle_clock.remaining_seconds must be non-negative when present", errors)
    if elapsed is not None and allotted is not None:
        if remaining is not None:
            expected_remaining = max(allotted - elapsed, 0.0)
            _check(abs(expected_remaining - remaining) <= 1.0, "battle_clock.remaining_seconds must match max(allotted_seconds - elapsed_seconds, 0) within tolerance", errors)

    score_elapsed = _number_or_none(scoreboard.get("elapsed_seconds"))
    score_allotted = _number_or_none(scoreboard.get("allotted_seconds"))
    score_remaining = _number_or_none(scoreboard.get("remaining_seconds"))
    if score_elapsed is not None and elapsed is not None:
        _check(abs(score_elapsed - elapsed) <= 0.001, "battle_clock.elapsed_seconds must match scoreboard.elapsed_seconds", errors)
    if score_allotted is not None and allotted is not None:
        _check(abs(score_allotted - allotted) <= 0.001, "battle_clock.allotted_seconds must match scoreboard.allotted_seconds", errors)
    if score_remaining is not None and remaining is not None:
        _check(abs(score_remaining - remaining) <= 0.001, "battle_clock.remaining_seconds must match scoreboard.remaining_seconds", errors)


def _validate_spectator_shell(
    *,
    shell: dict[str, Any],
    battle_id: str,
    scenario: dict[str, Any],
    scoreboard: dict[str, Any],
    battle_clock: dict[str, Any],
    events: list[Any],
    errors: list[str],
) -> None:
    _check(shell.get("schema") == "battle.spectator_shell.v1", "spectator_shell.schema must be battle.spectator_shell.v1", errors)
    _check(shell.get("proof_mode") == EXPECTED_PROOF_MODE, "spectator_shell.proof_mode must be receipt_backed_fixture", errors)
    public_entrypoint = str(scenario.get("public_entrypoint") or "")
    expected_title = f"{battle_id.upper()} · POST {public_entrypoint}"
    _check(shell.get("battle_title") == expected_title, "spectator_shell.battle_title must match battle id and public entrypoint", errors)
    subtitle = str(shell.get("subtitle") or "")
    _check(str(scenario.get("cwe") or "") in subtitle, "spectator_shell.subtitle must include scenario.cwe", errors)
    _check(str(scenario.get("hidden_vulnerability_family") or "") in subtitle, "spectator_shell.subtitle must include scenario vulnerability family", errors)
    _check(shell.get("mode_badge") == "RECEIPT-BACKED", "spectator_shell.mode_badge must be RECEIPT-BACKED", errors)
    _check(shell.get("truth_label") == "receipt-backed fixture", "spectator_shell.truth_label must be receipt-backed fixture", errors)

    facts = shell.get("facts")
    if not isinstance(facts, list):
        errors.append("spectator_shell.facts must be a list")
    else:
        facts_by_label = {str(item.get("label")): str(item.get("value")) for item in facts if isinstance(item, dict)}
        _check(facts_by_label.get("Target") == f"POST {public_entrypoint}", "spectator_shell Target fact must match scenario.public_entrypoint", errors)
        _check(facts_by_label.get("Round time") == _round_time_label(battle_clock), "spectator_shell Round time fact must match battle_clock", errors)

    score = shell.get("score")
    if not isinstance(score, dict):
        errors.append("spectator_shell.score must be an object")
    else:
        red = score.get("red") if isinstance(score.get("red"), dict) else {}
        blue = score.get("blue") if isinstance(score.get("blue"), dict) else {}
        _check(red.get("value") == _score_label(scoreboard.get("red_score")), "spectator_shell.score.red.value must match scoreboard.red_score", errors)
        _check(blue.get("value") == _score_label(scoreboard.get("blue_score")), "spectator_shell.score.blue.value must match scoreboard.blue_score", errors)
        _check(score.get("verdict") == scoreboard.get("verdict"), "spectator_shell.score.verdict must match scoreboard.verdict", errors)

    ticker = shell.get("event_ticker")
    if not isinstance(ticker, dict):
        errors.append("spectator_shell.event_ticker must be an object")
    else:
        _check(ticker.get("label") == "Receipt events", "spectator_shell.event_ticker.label must be Receipt events", errors)
        _check(_int(ticker.get("count")) == len(events), "spectator_shell.event_ticker.count must match events[]", errors)
        _check(ticker.get("live") is False, "spectator_shell.event_ticker.live must be false for receipt-backed fixtures", errors)
        _check(ticker.get("source") == "events", "spectator_shell.event_ticker.source must be events", errors)

    guards = shell.get("render_guards")
    if not isinstance(guards, list):
        errors.append("spectator_shell.render_guards must be a list")
    else:
        _check(
            "Do not label receipt replay as live execution." in {str(item) for item in guards},
            "spectator_shell.render_guards must forbid live execution wording",
            errors,
        )


def _validate_timeline(*, timeline: dict[str, Any], lanes: list[Any], events: list[Any], errors: list[str]) -> None:
    _check(timeline.get("mode") in {"receipt_order", "elapsed_seconds"}, "timeline.mode must be receipt_order or elapsed_seconds", errors)
    _check(_int(timeline.get("lane_count")) == len(lanes), "timeline.lane_count must match lanes[]", errors)
    _check(_int(timeline.get("event_count")) == len(events), "timeline.event_count must match events[]", errors)
    _check(isinstance(timeline.get("supports_zoom"), bool), "timeline.supports_zoom must be a boolean", errors)
    _check(isinstance(timeline.get("supports_pan"), bool), "timeline.supports_pan must be a boolean", errors)
    _check(timeline.get("scroll_axis") == "horizontal", "timeline.scroll_axis must be horizontal", errors)

    min_x = _number_or_none(timeline.get("min_x"))
    max_x = _number_or_none(timeline.get("max_x"))
    _check(min_x is not None and max_x is not None and min_x < max_x, "timeline min_x/max_x must be numeric and increasing", errors)

    playhead = timeline.get("playhead")
    if not isinstance(playhead, dict):
        errors.append("timeline.playhead must be an object")
    else:
        _check(playhead.get("mode") == "receipt_elapsed", "timeline.playhead.mode must be receipt_elapsed", errors)
        current_x = _number_or_none(playhead.get("current_x"))
        _check(current_x is not None and min_x <= current_x <= max_x, "timeline.playhead.current_x must be within min_x/max_x", errors)
        _check(playhead.get("source_receipt_id") in {"scoreboard", "run-receipt"}, "timeline.playhead.source_receipt_id must be scoreboard or run-receipt", errors)
        _check(playhead.get("can_animate") is True, "timeline.playhead.can_animate must be true for receipt replay", errors)
        _check(playhead.get("animation_semantics") == "receipt_replay_only", "timeline.playhead.animation_semantics must be receipt_replay_only", errors)
        _check(playhead.get("proof_mode") == EXPECTED_PROOF_MODE, "timeline.playhead.proof_mode must be receipt_backed_fixture", errors)
        elapsed = playhead.get("elapsed_seconds")
        _check(elapsed is None or isinstance(elapsed, (int, float)), "timeline.playhead.elapsed_seconds must be numeric or null", errors)
        keyframes = playhead.get("keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            errors.append("timeline.playhead.keyframes must be a non-empty list")
        else:
            keyframe_xs: list[float] = []
            lane_ids = {str(lane.get("id")) for lane in lanes if isinstance(lane, dict)}
            lane_event_by_id: dict[tuple[str, str], dict[str, Any]] = {}
            for lane in lanes:
                if not isinstance(lane, dict):
                    continue
                lane_id = str(lane.get("id") or "")
                lane_events = lane.get("events") if isinstance(lane.get("events"), list) else []
                for lane_event in lane_events:
                    if isinstance(lane_event, dict) and lane_event.get("id"):
                        lane_event_by_id[(lane_id, str(lane_event.get("id")))] = lane_event
            for frame in keyframes:
                if not isinstance(frame, dict):
                    errors.append("timeline.playhead.keyframes entries must be objects")
                    continue
                frame_x = _number_or_none(frame.get("x"))
                _check(
                    frame_x is not None and min_x is not None and max_x is not None and min_x <= frame_x <= max_x,
                    "timeline.playhead.keyframes[].x must be within min_x/max_x",
                    errors,
                )
                if frame_x is not None:
                    keyframe_xs.append(frame_x)
                frame_lane_id = str(frame.get("lane_id") or "")
                frame_event_id = str(frame.get("event_id") or "")
                _check(frame_lane_id in lane_ids, "timeline.playhead.keyframes[].lane_id must reference a lane", errors)
                _check(isinstance(frame.get("event_id"), str) and bool(frame.get("event_id")), "timeline.playhead.keyframes[].event_id must be present", errors)
                _check(frame.get("proof_mode") == EXPECTED_PROOF_MODE, "timeline.playhead.keyframes[].proof_mode must be receipt_backed_fixture", errors)
                source_event = lane_event_by_id.get((frame_lane_id, frame_event_id))
                _check(source_event is not None, "timeline.playhead.keyframes[].event_id must reference a lane event", errors)
                if isinstance(source_event, dict):
                    _check(_number_or_none(source_event.get("x")) == frame_x, "timeline.playhead.keyframes[].x must match source lane event x", errors)
                    _check(str(source_event.get("kind") or "") == str(frame.get("kind") or ""), "timeline.playhead.keyframes[].kind must match source lane event kind", errors)
                    _check(str(source_event.get("label") or "") == str(frame.get("label") or ""), "timeline.playhead.keyframes[].label must match source lane event label", errors)
            _check(keyframe_xs == sorted(keyframe_xs), "timeline.playhead.keyframes must be sorted by x", errors)
            if keyframe_xs and current_x is not None:
                _check(keyframe_xs[-1] == current_x, "timeline.playhead.current_x must equal the final keyframe x", errors)

    viewport = timeline.get("viewport")
    if not isinstance(viewport, dict):
        errors.append("timeline.viewport must be an object")
    else:
        initial_min = _number_or_none(viewport.get("initial_min_x"))
        initial_max = _number_or_none(viewport.get("initial_max_x"))
        _check(initial_min is not None and initial_max is not None and initial_min < initial_max, "timeline.viewport initial bounds must be numeric and increasing", errors)
        if min_x is not None and max_x is not None and initial_min is not None and initial_max is not None:
            _check(min_x <= initial_min < initial_max <= max_x, "timeline.viewport initial bounds must be within min_x/max_x", errors)
        min_zoom = _number_or_none(viewport.get("min_zoom"))
        max_zoom = _number_or_none(viewport.get("max_zoom"))
        _check(min_zoom is not None and max_zoom is not None and 0 < min_zoom < max_zoom, "timeline.viewport zoom bounds must be positive and increasing", errors)
        _check(viewport.get("proof_mode") == EXPECTED_PROOF_MODE, "timeline.viewport.proof_mode must be receipt_backed_fixture", errors)

    order_indexes: list[int] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        order_index = event.get("order_index")
        _check(isinstance(order_index, int), f"event {event.get('id')} order_index must be an integer", errors)
        if isinstance(order_index, int):
            order_indexes.append(order_index)
        elapsed = event.get("elapsed_seconds")
        _check(elapsed is None or isinstance(elapsed, (int, float)), f"event {event.get('id')} elapsed_seconds must be numeric or null", errors)
    if order_indexes:
        _check(order_indexes == sorted(order_indexes), "event order_index values must be sorted in timeline order", errors)


def _validate_lane_event_layout(*, lanes: list[Any], errors: list[str]) -> None:
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane_id = lane.get("id")
        lane_x_start = _number_or_none(lane.get("xStart"))
        is_child_lane = bool(lane.get("parentId"))
        lane_events = lane.get("events")
        activity_segments = lane.get("activitySegments")
        if not isinstance(lane_events, list):
            errors.append(f"lane {lane_id} events must be a list")
            continue
        lane_event_order_indexes = [
            event.get("order_index")
            for event in lane_events
            if isinstance(event, dict) and isinstance(event.get("order_index"), int)
        ]
        _check(
            len(lane_event_order_indexes) == len(lane_events) and lane_event_order_indexes == sorted(lane_event_order_indexes),
            f"lane {lane_id} events must be sorted by order_index",
            errors,
        )
        if not isinstance(activity_segments, list) or not activity_segments:
            errors.append(f"lane {lane_id} activitySegments must be a non-empty list")
        else:
            previous_end: float | None = None
            lane_x_end = _number_or_none(lane.get("xEnd"))
            for segment in activity_segments:
                if not isinstance(segment, dict):
                    errors.append(f"lane {lane_id} activitySegments entries must be objects")
                    continue
                start_x = _number_or_none(segment.get("start_x"))
                end_x = _number_or_none(segment.get("end_x"))
                _check(start_x is not None and end_x is not None and start_x < end_x, f"lane {lane_id} activity segment bounds must be numeric and increasing", errors)
                if lane_x_start is not None and start_x is not None:
                    _check(start_x >= lane_x_start, f"lane {lane_id} activity segment must not start before lane xStart", errors)
                if lane_x_end is not None and end_x is not None:
                    _check(end_x <= lane_x_end, f"lane {lane_id} activity segment must not end after lane xEnd", errors)
                if previous_end is not None and start_x is not None:
                    _check(start_x >= previous_end, f"lane {lane_id} activitySegments must be sorted", errors)
                if end_x is not None:
                    previous_end = end_x
                _check(isinstance(segment.get("phase"), str) and bool(segment.get("phase")), f"lane {lane_id} activity segment phase must be present", errors)
                _check(isinstance(segment.get("label"), str) and bool(segment.get("label")), f"lane {lane_id} activity segment label must be present", errors)
                _check(segment.get("proof_mode") == EXPECTED_PROOF_MODE, f"lane {lane_id} activity segment proof_mode must be receipt_backed_fixture", errors)
        for event in lane_events:
            if not isinstance(event, dict):
                errors.append(f"lane {lane_id} events entries must be objects")
                continue
            label_band = event.get("label_band")
            _check(label_band in {"upper", "lower", "auto"}, f"lane event {event.get('id')} label_band must be upper, lower, or auto", errors)
            priority = event.get("marker_priority")
            _check(isinstance(priority, int) and 0 <= priority <= 100, f"lane event {event.get('id')} marker_priority must be an integer from 0 to 100", errors)
            collision_group = event.get("collision_group")
            _check(isinstance(collision_group, str) and collision_group.startswith("x"), f"lane event {event.get('id')} collision_group must be an x-bucket string", errors)
            event_x = _number_or_none(event.get("x"))
            lane_x_end = _number_or_none(lane.get("xEnd"))
            if lane_x_start is not None and event_x is not None:
                _check(event_x >= lane_x_start, f"lane event {event.get('id')} must not occur before lane xStart", errors)
            if lane_x_end is not None and event_x is not None:
                _check(event_x <= lane_x_end, f"lane event {event.get('id')} must not occur after lane xEnd", errors)
            if is_child_lane and lane_x_start is not None and event_x is not None:
                _check(event_x >= lane_x_start, f"child lane event {event.get('id')} must not occur before lane xStart", errors)


def _validate_actor_visuals(*, lanes: list[Any], sprite_theme: dict[str, Any], errors: list[str]) -> None:
    _check(sprite_theme.get("schema") == "battle.sprite_theme.v1", "sprite_theme.schema must be battle.sprite_theme.v1", errors)
    _check(sprite_theme.get("renderer") == "pixijs", "sprite_theme.renderer must be pixijs", errors)
    variants = sprite_theme.get("variants") if isinstance(sprite_theme.get("variants"), dict) else {}
    _check(bool(variants), "sprite_theme.variants must not be empty", errors)
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane_id = str(lane.get("id") or "")
        visual = lane.get("actor_visual") if isinstance(lane.get("actor_visual"), dict) else {}
        _check(visual.get("schema") == "battle.actor_visual.v1", f"lane {lane_id} actor_visual.schema must be battle.actor_visual.v1", errors)
        _check(visual.get("lane_id") == lane_id, f"lane {lane_id} actor_visual.lane_id must match lane.id", errors)
        _check(visual.get("team") == lane.get("team"), f"lane {lane_id} actor_visual.team must match lane.team", errors)
        variant_id = str(visual.get("variant_id") or "")
        _check(bool(variant_id), f"lane {lane_id} actor_visual.variant_id is required", errors)
        _check(variant_id in variants, f"lane {lane_id} actor_visual.variant_id must exist in sprite_theme.variants", errors)
        timeline = visual.get("state_timeline") if isinstance(visual.get("state_timeline"), list) else []
        _check(bool(timeline), f"lane {lane_id} actor_visual.state_timeline must not be empty", errors)
        for transition in timeline:
            if not isinstance(transition, dict):
                errors.append(f"lane {lane_id} actor_visual.state_timeline entries must be objects")
                continue
            _check(_number_or_none(transition.get("at_seconds")) is not None, f"lane {lane_id} actor_visual transition requires at_seconds", errors)
            _check(isinstance(transition.get("state"), str) and bool(transition.get("state")), f"lane {lane_id} actor_visual transition requires state", errors)
            _check(isinstance(transition.get("source_event_id"), str) and bool(transition.get("source_event_id")), f"lane {lane_id} actor_visual transition requires source_event_id", errors)
            if transition.get("state") in {"blocked", "killed", "fastest_crash", "promoted"}:
                _check(
                    isinstance(transition.get("source_receipt_id"), str) and bool(transition.get("source_receipt_id")),
                    f"lane {lane_id} terminal actor_visual state {transition.get('state')} requires source_receipt_id",
                    errors,
                )


def _validate_semantic_scoring_and_replay(*, fixture: dict[str, Any], lanes: list[Any], scoreboard: dict[str, Any], errors: list[str]) -> None:
    semantic_replay = fixture.get("semantic_replay") if isinstance(fixture.get("semantic_replay"), dict) else {}
    _check(semantic_replay.get("schema") == "battle.semantic_replay.v1", "semantic_replay.schema must be battle.semantic_replay.v1", errors)
    _check(semantic_replay.get("time_authority") == "receipt_elapsed_seconds", "semantic_replay.time_authority must be receipt_elapsed_seconds", errors)
    _check(semantic_replay.get("presentation_owner") == "ux", "semantic_replay.presentation_owner must be ux", errors)
    _check("cinematic_speed" in {str(item) for item in (semantic_replay.get("backend_must_not_emit") or [])}, "semantic_replay must forbid backend cinematic speed", errors)
    replay_events = semantic_replay.get("events") if isinstance(semantic_replay.get("events"), list) else []
    _check(_int(semantic_replay.get("event_count")) == len(replay_events), "semantic_replay.event_count must match events length", errors)

    semantic_scoring = scoreboard.get("semantic_scoring") if isinstance(scoreboard.get("semantic_scoring"), dict) else {}
    _check(semantic_scoring.get("schema") == "battle.semantic_scoring.v1", "scoreboard.semantic_scoring.schema must be battle.semantic_scoring.v1", errors)
    _check(semantic_scoring.get("score_owner") == "scorekeeper", "scoreboard.semantic_scoring.score_owner must be scorekeeper", errors)
    rules = semantic_scoring.get("rules") if isinstance(semantic_scoring.get("rules"), dict) else {}
    pre_multiplier = _number_or_none(rules.get("pre_spawn_block_blue_multiplier"))
    kill_multiplier = _number_or_none(rules.get("explicit_kill_blue_multiplier"))
    post_multiplier = _number_or_none(rules.get("post_spawn_containment_blue_multiplier"))
    _check(
        pre_multiplier is not None and post_multiplier is not None and pre_multiplier > post_multiplier,
        "semantic scoring must value pre-spawn Blue blocks above post-spawn containment",
        errors,
    )
    _check(
        pre_multiplier is not None and kill_multiplier is not None and pre_multiplier > kill_multiplier,
        "semantic scoring must value no-spawn Blue prevention above explicit kill",
        errors,
    )

    lane_scores = semantic_scoring.get("lanes") if isinstance(semantic_scoring.get("lanes"), list) else []
    _check(len(lane_scores) == len(lanes), "scoreboard.semantic_scoring.lanes must match lanes length", errors)
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane_id = str(lane.get("id") or "")
        profile = lane.get("exploit_profile") if isinstance(lane.get("exploit_profile"), dict) else {}
        score = lane.get("score_semantics") if isinstance(lane.get("score_semantics"), dict) else {}
        replay = lane.get("replay_semantics") if isinstance(lane.get("replay_semantics"), dict) else {}
        visual = lane.get("actor_visual") if isinstance(lane.get("actor_visual"), dict) else {}
        _check(profile.get("schema") == "battle.exploit_profile.v1", f"lane {lane_id} exploit_profile.schema must be battle.exploit_profile.v1", errors)
        _check(profile.get("lane_id") == lane_id, f"lane {lane_id} exploit_profile.lane_id must match lane.id", errors)
        for key in ("strength", "complexity", "durability", "lineage_pressure", "score_weight"):
            value = _number_or_none(profile.get(key))
            _check(value is not None and 0 <= value <= 1, f"lane {lane_id} exploit_profile.{key} must be 0..1", errors)
        _check(score.get("schema") == "battle.semantic_scoring.v1", f"lane {lane_id} score_semantics.schema must be battle.semantic_scoring.v1", errors)
        _check(score.get("lane_id") == lane_id, f"lane {lane_id} score_semantics.lane_id must match lane.id", errors)
        _check(
            score.get("outcome_tier")
            in {
                "UNRESOLVED",
                "PRE_SPAWN_BLOCK",
                "POST_SPAWN_CONTAINMENT",
                "PREEMPTIVE_SPAWN_ADAPTATION",
                "SPAWN_PRESSURE_CONCEDED",
                "KILLED_CONFIRMED",
                "RED_BREAKTHROUGH",
            },
            f"lane {lane_id} score_semantics.outcome_tier is invalid",
            errors,
        )
        _check(
            score.get("outcome_class")
            in {
                "unresolved_pressure",
                "pre_spawn_blue_block",
                "confirmed_blue_kill_no_child",
                "confirmed_blue_kill_with_child",
                "post_spawn_child_contained",
                "preemptive_spawn_adaptation",
                "spawn_pressure_conceded",
                "red_breakthrough",
            },
            f"lane {lane_id} score_semantics.outcome_class is invalid",
            errors,
        )
        _check(
            score.get("spawn_state") in {"not_spawned", "spawned_child", "post_spawn"},
            f"lane {lane_id} score_semantics.spawn_state is invalid",
            errors,
        )
        multiplier = score.get("multipliers") if isinstance(score.get("multipliers"), dict) else {}
        _check(_number_or_none(score.get("score_weight")) is not None, f"lane {lane_id} score_semantics.score_weight must be numeric", errors)
        _check(_number_or_none(multiplier.get("red")) is not None, f"lane {lane_id} score_semantics.multipliers.red must be numeric", errors)
        _check(_number_or_none(multiplier.get("blue")) is not None, f"lane {lane_id} score_semantics.multipliers.blue must be numeric", errors)
        delta = score.get("score_delta") if isinstance(score.get("score_delta"), dict) else {}
        _check(_number_or_none(delta.get("red")) is not None, f"lane {lane_id} score_semantics.score_delta.red must be numeric", errors)
        _check(_number_or_none(delta.get("blue")) is not None, f"lane {lane_id} score_semantics.score_delta.blue must be numeric", errors)
        _check(replay.get("schema") == "battle.replay_semantics.v1", f"lane {lane_id} replay_semantics.schema must be battle.replay_semantics.v1", errors)
        _check(replay.get("presentation_owner") == "ux", f"lane {lane_id} replay_semantics.presentation_owner must be ux", errors)
        if str(profile.get("tier") or "") == "adaptive_lineage":
            _check(visual.get("variant_id") == "plague_nurgling", f"lane {lane_id} adaptive lineage exploit must map to plague_nurgling", errors)
        if str(profile.get("tier") or "") == "heavy_durable":
            _check(visual.get("variant_id") == "crimson_hornbreaker", f"lane {lane_id} heavy durable exploit must map to crimson_hornbreaker", errors)


def _validate_lane_cockpit(*, lane: dict[str, Any], errors: list[str]) -> None:
    lane_id = str(lane.get("id") or "")
    cockpit = lane.get("cockpit")
    if not isinstance(cockpit, dict):
        errors.append(f"lane {lane_id} cockpit must be an object")
        return

    _check(cockpit.get("schema") == "battle.lane_cockpit.v1", f"lane {lane_id} cockpit.schema must be battle.lane_cockpit.v1", errors)
    _check(cockpit.get("proof_mode") == EXPECTED_PROOF_MODE, f"lane {lane_id} cockpit.proof_mode must be receipt_backed_fixture", errors)
    _check(
        cockpit.get("proof_label") in {"LIVE PROOF", "FIXTURE TRACE", "FIXTURE SKILL TRACE", "MOCKED SKILL", "PROOF PENDING", "MISSING PROOF"},
        f"lane {lane_id} cockpit proof_label is invalid",
        errors,
    )

    selected = cockpit.get("selected_tau_exploit_subagent")
    if not isinstance(selected, dict):
        errors.append(f"lane {lane_id} cockpit.selected_tau_exploit_subagent must be an object")
    else:
        _check(selected.get("actor_id") == lane_id, f"lane {lane_id} cockpit selected actor_id must match lane id", errors)
        _check(bool(selected.get("payload_id")), f"lane {lane_id} cockpit selected payload_id is required", errors)
        missing_tau_id = selected.get("missing_tau_id") is True
        tau_subagent_id = str(selected.get("tau_subagent_id") or "")
        _check(missing_tau_id or bool(tau_subagent_id), f"lane {lane_id} cockpit tau_subagent_id is required unless missing_tau_id is true", errors)
        _check(_int(selected.get("generation")) == _int(lane.get("generation")), f"lane {lane_id} cockpit generation must match lane generation", errors)

    current_turn = cockpit.get("current_turn")
    if not isinstance(current_turn, dict):
        errors.append(f"lane {lane_id} cockpit.current_turn must be an object")
    else:
        for key in ("loop_index", "phase", "current_action", "status"):
            _check(key in current_turn, f"lane {lane_id} cockpit.current_turn.{key} is required", errors)

    trace = cockpit.get("public_trace")
    if not isinstance(trace, dict):
        errors.append(f"lane {lane_id} cockpit.public_trace must be an object")
    else:
        for key in ("observation", "hypothesis", "action", "result", "learned", "next_move"):
            value = trace.get(key)
            _check(isinstance(value, str) and bool(value), f"lane {lane_id} cockpit.public_trace.{key} must be a non-empty string or 'not emitted'", errors)

    output = cockpit.get("output")
    if not isinstance(output, dict):
        errors.append(f"lane {lane_id} cockpit.output must be an object")
    else:
        _check(isinstance(output.get("stdout"), list) and bool(output.get("stdout")), f"lane {lane_id} cockpit.output.stdout must be a non-empty list", errors)
        _check(isinstance(output.get("stderr"), list) and bool(output.get("stderr")), f"lane {lane_id} cockpit.output.stderr must be a non-empty list", errors)

    skills = cockpit.get("skills_tools")
    if not isinstance(skills, list):
        errors.append(f"lane {lane_id} cockpit.skills_tools must be a list")
    else:
        for skill in skills:
            if not isinstance(skill, dict):
                errors.append(f"lane {lane_id} cockpit.skills_tools entries must be objects")
                continue
            _check(skill.get("kind") in {"skill", "tool", "unregistered"}, f"lane {lane_id} cockpit skill kind is invalid", errors)
            _check(
                skill.get("proof_label") in {"LIVE PROOF", "FIXTURE SKILL TRACE", "MOCKED SKILL", "PROOF PENDING", "MISSING PROOF"},
                f"lane {lane_id} cockpit skill proof_label is invalid",
                errors,
            )
            _check(skill.get("proof_mode") == EXPECTED_PROOF_MODE, f"lane {lane_id} cockpit skill proof_mode must be receipt_backed_fixture", errors)

    blue_outcome = cockpit.get("blue_outcome")
    if not isinstance(blue_outcome, dict):
        errors.append(f"lane {lane_id} cockpit.blue_outcome must be an object")
    else:
        for key in ("detected", "blocked", "killed", "forced_handoff"):
            _check(isinstance(blue_outcome.get(key), bool), f"lane {lane_id} cockpit.blue_outcome.{key} must be boolean", errors)
        _check(blue_outcome.get("proof_mode") == EXPECTED_PROOF_MODE, f"lane {lane_id} cockpit.blue_outcome.proof_mode must be receipt_backed_fixture", errors)
        _check(blue_outcome.get("killed") is not True, f"lane {lane_id} cockpit must not claim killed without kill receipt support", errors)

    _check(isinstance(cockpit.get("memory_project_knowledge_events"), list), f"lane {lane_id} cockpit.memory_project_knowledge_events must be a list", errors)
    _check(isinstance(cockpit.get("learned"), str) and bool(cockpit.get("learned")), f"lane {lane_id} cockpit.learned must be a string", errors)
    _check(isinstance(cockpit.get("next_move"), str) and bool(cockpit.get("next_move")), f"lane {lane_id} cockpit.next_move must be a string", errors)
    _check(bool(cockpit.get("latest_receipt_id")), f"lane {lane_id} cockpit.latest_receipt_id is required", errors)

    lane_replay = lane.get("replay")
    cockpit_replay = cockpit.get("replay")
    if lane_replay is None:
        _check(cockpit_replay is None, f"lane {lane_id} cockpit.replay must be null when lane.replay is null", errors)
    elif not isinstance(lane_replay, dict):
        errors.append(f"lane {lane_id} replay must be an object or null")
    elif not isinstance(cockpit_replay, dict):
        errors.append(f"lane {lane_id} cockpit.replay must mirror lane.replay")
    else:
        for key in ("label", "kind", "receipt_id", "can_execute_now", "endpoint", "command_receipt_id"):
            _check(cockpit_replay.get(key) == lane_replay.get(key), f"lane {lane_id} cockpit.replay.{key} must match lane.replay.{key}", errors)
        _check(cockpit_replay.get("cta") == lane_replay.get("cta"), f"lane {lane_id} cockpit.replay.cta must match lane.replay.cta", errors)


def _int(value: Any) -> int:
    return int(value) if isinstance(value, int) else 0


def _round_time_label(clock: dict[str, Any]) -> str:
    return f"{_seconds_label(clock.get('elapsed_seconds'))} / {_seconds_label(clock.get('allotted_seconds'))}"


def _seconds_label(value: Any) -> str:
    number = _number_or_none(value)
    if number is None:
        return "n/a"
    seconds = max(0, int(number))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _score_label(value: Any) -> str:
    number = _number_or_none(value)
    if number is None:
        return "0"
    if float(number).is_integer():
        return str(int(number))
    return f"{float(number):.1f}"


def _lineage_group_count(lineage: dict[str, Any]) -> int:
    groups = lineage.get("groups")
    return len(groups) if isinstance(groups, list) else 0


def _validate_lineage_groups(*, groups: list[Any], lane_by_id: dict[str, Any], errors: list[str]) -> None:
    for group in groups:
        if not isinstance(group, dict):
            errors.append("lineage.groups entries must be objects")
            continue
        group_id = str(group.get("group_id") or "")
        parent_id = str(group.get("parent_lane_id") or "")
        child_ids = [str(child_id) for child_id in group.get("child_lane_ids", [])] if isinstance(group.get("child_lane_ids"), list) else []
        lane_ids = [str(lane_id) for lane_id in group.get("lane_ids", [])] if isinstance(group.get("lane_ids"), list) else []
        _check(group_id == f"lineage:{parent_id}", f"lineage group {group_id} must be keyed by parent lane", errors)
        _check(parent_id in lane_by_id, f"lineage group parent lane missing: {parent_id}", errors)
        _check(all(child_id in lane_by_id for child_id in child_ids), f"lineage group {group_id} has missing child lane", errors)
        _check(lane_ids == [parent_id, *child_ids], f"lineage group {group_id} lane_ids must list parent followed by children", errors)
        _check(group.get("collapsible") is True, f"lineage group {group_id} must be collapsible", errors)
        _check(group.get("expanded_by_default") is True, f"lineage group {group_id} must be expanded_by_default", errors)
        _check(_int(group.get("lane_count")) == len(lane_ids), f"lineage group {group_id} lane_count must match lane_ids", errors)
        _check(group.get("proof_mode") == EXPECTED_PROOF_MODE, f"lineage group {group_id} proof_mode must be receipt_backed_fixture", errors)


def _validate_replay_contract(*, lane: dict[str, Any], replay: dict[str, Any], errors: list[str]) -> None:
    lane_id = lane.get("id")
    cta = replay.get("cta")
    _check(replay.get("label") == "REPLAY IN DOCKER", f"lane {lane_id} replay label must be REPLAY IN DOCKER", errors)
    _check(replay.get("proof_mode") == EXPECTED_PROOF_MODE, f"lane {lane_id} replay proof_mode must be receipt_backed_fixture", errors)
    if replay.get("can_execute_now") is True:
        _check(bool(replay.get("endpoint") or replay.get("command_receipt_id")), f"lane {lane_id} executable replay requires endpoint or command receipt", errors)
    if not isinstance(cta, dict):
        errors.append(f"lane {lane_id} replay.cta must be an object")
        return
    _check(cta.get("visible") is True, f"lane {lane_id} replay.cta.visible must be true when replay metadata exists", errors)
    _check(cta.get("label") == "REPLAY IN DOCKER", f"lane {lane_id} replay.cta.label must be REPLAY IN DOCKER", errors)
    _check(cta.get("icon") == "container", f"lane {lane_id} replay.cta.icon must be container", errors)
    _check(cta.get("state") in {"receipt_only", "executable"}, f"lane {lane_id} replay.cta.state must be receipt_only or executable", errors)
    _check(cta.get("proof_mode") == EXPECTED_PROOF_MODE, f"lane {lane_id} replay.cta.proof_mode must be receipt_backed_fixture", errors)
    if replay.get("can_execute_now") is True:
        _check(cta.get("state") == "executable", f"lane {lane_id} executable replay requires replay.cta.state executable", errors)
        _check(cta.get("disabled_reason") is None, f"lane {lane_id} executable replay must not have replay.cta.disabled_reason", errors)
    else:
        _check(cta.get("state") == "receipt_only", f"lane {lane_id} non-executable replay requires replay.cta.state receipt_only", errors)
        _check(bool(cta.get("disabled_reason")), f"lane {lane_id} receipt-only replay requires replay.cta.disabled_reason", errors)


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
