"""Generate receipt-backed Battle UX data from Battle proof directories.

Supported inputs:
    * deterministic Arena Red/Blue/Judge proof directories
    * public-only Tau handoff proof directories, including bounded worker matrix runs

The adapter is fail-closed. It renders only receipt-backed facts. Missing Judge
attempts, missing materialized artifacts, missing Blue block receipts, missing
child-spawn receipts, missing fastest-crash receipts, and missing Blue kill
receipts do not become UI claims.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Annotated, Any

import typer

from .ux_contract_validator import (
    ContractError,
    _lane_activity_timeline_model,
    _lane_phase_coverage,
    _lineage_render_model,
    _outcome_truth_constraints_model,
    _selected_lane_model,
    _spawn_gate_model,
    _timeline_elapsed_axis_model,
    _timeline_label_layout_model,
    _timeline_lane_start_model,
    _timeline_time_model,
    _timeline_viewport_model,
    validate_fixture,
)


PROOF_MODE = "receipt_backed_fixture"
CANONICAL_BATTLE004_ALLOTTED_SECONDS = 1200.0
DEFAULT_LANE_ID = "payload-857-receipt"
DEFAULT_PAYLOAD_ID = "payload-857"
DEFAULT_LANE_NAME = "Archive Escape"
DEFAULT_BLUE_ACTION_ID = "blue-receipt-backed-patch"
SEMANTIC_SCORE_VERSION = "battle.semantic_scoring.v1"
EXPLOIT_PROFILE_VERSION = "battle.exploit_profile.v1"
REPLAY_SEMANTICS_VERSION = "battle.replay_semantics.v1"
ACTOR_STATE_VOCABULARY = [
    "idle",
    "walk",
    "run",
    "research",
    "payload",
    "mutate",
    "handoff",
    "spawn",
    "hit",
    "blocked",
    "killed",
    "fastest_crash",
    "promoted",
    "stale_pending",
]
SPRITE_VARIANT_ORDER = [
    "blue_lizard",
    "green_horn",
    "nurgling",
    "purple_horn_imp",
    "red_human",
    "skull_horn",
    "slug_demon",
    "typhus",
    "crimson_chainsword_berserker",
    "crimson_hornbreaker",
    "crimson_chainsaw_demon",
    "plague_nurgling",
]
LANE_VARIANT_DEFAULTS = {
    "payload-857": "crimson_chainsword_berserker",
    "payload-857-A": "crimson_chainsaw_demon",
    "payload-857-receipt": "crimson_hornbreaker",
    "payload-857-red-1": "plague_nurgling",
    "payload-231": "purple_horn_imp",
    "payload-404": "skull_horn",
    "payload-118": "blue_lizard",
    "payload-620": "typhus",
    "payload-912": "crimson_chainsword_berserker",
    "payload-912-A": "plague_nurgling",
    "payload-912-B": "crimson_hornbreaker",
    "payload-912-C": "purple_horn_imp",
    "payload-912-D": "crimson_chainsaw_demon",
}

app = typer.Typer(add_completion=False, help="Generate Battle UX data from receipt artifacts.")


@app.callback(invoke_without_command=True)
def main(
    input_dir: Annotated[
        Path,
        typer.Option("--input", exists=True, file_okay=False, dir_okay=True, readable=True, help="Battle proof directory."),
    ],
    battle_id: Annotated[str, typer.Option("--battle-id", help="Expected Battle id for the generated fixture.")],
    out: Annotated[Path, typer.Option("--out", help="Output normalized JSON path.")],
    print_json: Annotated[bool, typer.Option("--json", help="Print the normalized JSON fixture to stdout.")] = False,
    ts_out: Annotated[Path | None, typer.Option("--ts-out", help="Optional generated TypeScript module path.")] = None,
) -> None:
    """Read a proof directory and write normalized Battle UX data."""
    fixture = generate_fixture_files(proof_dir=input_dir, battle_id=battle_id, out=out, ts_out=ts_out)
    if print_json:
        typer.echo(json.dumps(fixture, indent=2, sort_keys=True))


def generate_fixture_files(*, proof_dir: Path, battle_id: str, out: Path, ts_out: Path | None = None) -> dict[str, Any]:
    """Generate, validate, and write normalized Battle UX fixture files."""
    fixture = adapt_proof_dir(proof_dir=proof_dir, battle_id=battle_id)
    try:
        validate_fixture(fixture)
    except ContractError as exc:
        raise typer.BadParameter(f"generated Battle UX fixture violates contract:\n{exc}") from exc
    _write_json(out, fixture)
    if ts_out is not None:
        _write_typescript(ts_out, fixture)
    return fixture


def generate_transport_files(*, fixture: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    """Write file-backed stream/snapshot artifacts for PixiJS or replay consumers.

    The transport artifacts remain renderer-neutral. They expose semantic Battle
    events, lane segments, and the full normalized snapshot, but no Pixi object
    ids, frame ids, easing, or pixel positions.
    """
    stream_dir = out_dir.expanduser().resolve()
    stream_dir.mkdir(parents=True, exist_ok=True)
    envelopes = _live_event_envelopes(fixture)
    events_path = stream_dir / "events.jsonl"
    events_path.write_text(
        "".join(f"{json.dumps(event, sort_keys=True)}\n" for event in envelopes),
        encoding="utf-8",
    )
    snapshot = _snapshot_envelope(fixture=fixture, last_seq=len(envelopes))
    snapshot_path = stream_dir / "latest-snapshot.json"
    _write_json(snapshot_path, snapshot)
    manifest = {
        "schema": "battle.transport_manifest.v1",
        "battle_id": fixture.get("battle_id"),
        "run_id": _fixture_run_id(fixture),
        "mode": "file_backed_replay_stream",
        "mocked": fixture.get("mocked"),
        "live_source": fixture.get("live_source"),
        "event_count": len(envelopes),
        "last_seq": len(envelopes),
        "events_jsonl": "events.jsonl",
        "latest_snapshot": "latest-snapshot.json",
        "normalized_fixture_schema": fixture.get("schema"),
        "proof_mode": fixture.get("proof_mode"),
        "renderer_boundary": {
            "backend_emits": [
                "clock",
                "semantic_events",
                "segments",
                "lanes",
                "lineage",
                "receipts",
                "actor_visual_identity_when_present",
            ],
            "backend_must_not_emit": [
                "pixi_object_ids",
                "sprite_frame_indices",
                "canvas_pixels",
                "easing_names",
                "particle_parameters",
            ],
        },
    }
    manifest_path = stream_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return {
        "schema": "battle.transport_generation.v1",
        "status": "PASS",
        "stream_dir": str(stream_dir),
        "manifest": str(manifest_path),
        "events_jsonl": str(events_path),
        "latest_snapshot": str(snapshot_path),
        "event_count": len(envelopes),
        "last_seq": len(envelopes),
    }


def adapt_proof_dir(*, proof_dir: Path, battle_id: str) -> dict[str, Any]:
    """Return a normalized UX fixture from a supported proof directory."""
    proof_root = proof_dir.expanduser().resolve()
    if _is_tau_public_only_proof(proof_root):
        return adapt_tau_public_only_proof(proof_root=proof_root, battle_id=battle_id)
    if _is_arena_battle_proof(proof_root):
        return adapt_arena_battle_proof(proof_root=proof_root, battle_id=battle_id)
    raise typer.BadParameter(
        f"unsupported proof directory layout: {proof_root}; expected Arena Red/Blue/Judge receipts or Tau public-only receipts"
    )


def adapt_arena_battle_proof(*, proof_root: Path, battle_id: str) -> dict[str, Any]:
    """Normalize deterministic Arena Red/Blue/Judge proof receipts."""
    run_receipt = _read_required_json(proof_root / "run-receipt.json")
    scoreboard = _read_required_json(proof_root / "scoreboard.json")
    red_receipt = _read_required_json(proof_root / "red-receipt.json")
    blue_receipt = _read_required_json(proof_root / "blue-receipt.json")
    judge_receipt = _read_required_json(proof_root / "judge" / "judge-receipt.json")
    scenario = _read_required_json(proof_root / "arena" / "scenario.json")
    arena_receipt = _read_required_json(proof_root / "arena" / "arena-receipt.json")
    language_contract = _read_optional_json(proof_root / "language-contract.json")
    monitor_index = _read_optional_json(proof_root / "monitor-index.json")
    lineage_path = proof_root / "lineage-receipts.json"
    lineage_spawns = _lineage_spawns(lineage_path)
    lineage_request = _lineage_request(run_receipt=run_receipt, lineage_path=lineage_path, valid_spawns=lineage_spawns)

    actual_battle_id = _first_str(run_receipt.get("battle_id"), scoreboard.get("battle_id"), scenario.get("battle_id"), battle_id)
    _assert_battle_id(actual_battle_id, battle_id)

    red_confirmed = bool(red_receipt.get("exploit_confirmed") or judge_receipt.get("exploit_confirmed_before_patch"))
    blue_patch = blue_receipt.get("status") == "PASS"
    exploit_blocked = bool(judge_receipt.get("exploit_blocked_after_patch"))
    functionality_preserved = bool(judge_receipt.get("functionality_preserved"))
    verdict = _first_str(judge_receipt.get("verdict"), scoreboard.get("verdict"), run_receipt.get("verdict"), "UNKNOWN")

    red_entries = [
        _red_entry(
            worker_id="red-0",
            lane_id=DEFAULT_LANE_ID,
            status="PASS" if red_confirmed else "BLOCKED",
            materialized_path=str(red_receipt.get("submission_artifact") or ""),
            subagent_receipt="red-receipt.json",
            reason=None if red_confirmed else "red_exploit_not_confirmed",
        )
    ]
    blue_entries = [
        _blue_entry(
            worker_id="blue-0",
            action_id=DEFAULT_BLUE_ACTION_ID,
            status="PASS" if blue_patch else "BLOCKED",
            materialized_path=str(blue_receipt.get("patch_artifact") or ""),
            subagent_receipt="blue-receipt.json",
            reason=None if blue_patch else "blue_patch_not_available",
        )
    ]
    attempts = _attempts_from_judge(judge_receipt=judge_receipt, red_entries=red_entries, blue_entries=blue_entries)
    facts = _base_facts(
        proof_root=proof_root,
        battle_id=actual_battle_id,
        run_id=_first_str(run_receipt.get("run_id"), scoreboard.get("run_id"), red_receipt.get("run_id"), "receipt-backed-run"),
        generated_at=_first_str(run_receipt.get("created_at"), judge_receipt.get("created_at"), red_receipt.get("created_at"), "1970-01-01T00:00:00Z"),
        status=_first_str(run_receipt.get("status"), scoreboard.get("status"), judge_receipt.get("status"), "UNKNOWN"),
        verdict=verdict,
        live_source=_first_str(run_receipt.get("live"), arena_receipt.get("live"), "receipt_artifacts"),
        mocked=bool(run_receipt.get("mocked", False) or arena_receipt.get("mocked", False)),
        scenario=scenario,
        language_contract=language_contract,
        monitor_index=monitor_index,
        source_kind="arena_red_blue_judge",
    )
    facts.update(
        {
            "red_entries": red_entries,
            "blue_entries": blue_entries,
            "attempts": attempts,
            "red_stdout": _read_receipt_stdout(red_receipt) or _read_optional_text(proof_root / "red" / "red-exploit.stdout.txt"),
            "red_stderr": _read_receipt_stderr(red_receipt) or _read_optional_text(proof_root / "red" / "red-exploit.stderr.txt"),
            "judge_stdout": _read_receipt_stdout(judge_receipt) or _read_optional_text(proof_root / "judge" / "judge-exploit-safe.stdout.txt"),
            "judge_stderr": _read_receipt_stderr(judge_receipt) or _read_optional_text(proof_root / "judge" / "judge-exploit-safe.stderr.txt"),
            "functionality_stdout": _read_optional_text(proof_root / "judge" / "judge-functionality.stdout.txt"),
            "scoreboard": scoreboard,
            "lineage_spawns": lineage_spawns,
            "lineage_request": lineage_request,
            "receipt_refs": [
                *_arena_receipts(include_language=(proof_root / "language-contract.json").exists(), include_monitor=bool(monitor_index)),
                *_lineage_receipts(lineage_spawns),
            ],
        }
    )
    return _fixture_from_facts(facts)


def adapt_tau_public_only_proof(*, proof_root: Path, battle_id: str) -> dict[str, Any]:
    """Normalize public-only Tau handoff proof receipts."""
    run_receipt = _read_required_json(proof_root / "run-receipt.json")
    manifest = _read_required_json(proof_root / "tau-live" / "manifest.json")
    visibility = _read_optional_json(proof_root / "visibility-validation.json")
    judge_receipt = _read_optional_json(proof_root / "judge" / "judge-receipt.json")
    scenario = _read_optional_json(proof_root / "arena" / "scenario.json")
    arena_receipt = _read_optional_json(proof_root / "arena" / "arena-receipt.json")
    scoreboard = _read_optional_json(proof_root / "scoreboard.json")
    lineage_path = proof_root / "lineage-receipts.json"
    lineage_spawns = _lineage_spawns(lineage_path)
    lineage_request = _lineage_request(run_receipt=run_receipt, lineage_path=lineage_path, valid_spawns=lineage_spawns)

    actual_battle_id = _first_str(run_receipt.get("battle_id"), manifest.get("battle_id"), scenario.get("battle_id"), battle_id)
    _assert_battle_id(actual_battle_id, battle_id)

    red_entries = _manifest_entries(manifest, "red", proof_root=proof_root)
    blue_entries = _manifest_entries(manifest, "blue", proof_root=proof_root)
    attempts = _attempts_from_tau_judge(judge_receipt=judge_receipt, red_entries=red_entries, blue_entries=blue_entries)

    facts = _base_facts(
        proof_root=proof_root,
        battle_id=actual_battle_id,
        run_id=_first_str(run_receipt.get("run_id"), manifest.get("run_id"), "tau-public-only-run"),
        generated_at=_first_str(run_receipt.get("created_at"), "1970-01-01T00:00:00Z"),
        status=_first_str(run_receipt.get("status"), manifest.get("status"), judge_receipt.get("status"), "UNKNOWN"),
        verdict=_first_str(judge_receipt.get("verdict"), scoreboard.get("verdict"), run_receipt.get("verdict"), "INSUFFICIENT_EVIDENCE"),
        live_source=_first_str(run_receipt.get("live"), "brave_search_docker_arena_oracle_tau_harness"),
        mocked=bool(run_receipt.get("mocked", False) or manifest.get("mocked", False)),
        scenario=scenario,
        language_contract={},
        monitor_index={},
        source_kind="tau_public_only",
    )
    facts.update(
        {
            "red_entries": red_entries or [_red_entry("red-0", DEFAULT_LANE_ID, "BLOCKED", "", "tau-live/red/tau-subagent-receipt.json", "missing_red_team")],
            "blue_entries": blue_entries,
            "attempts": attempts,
            "red_stdout": _joined_blocked_reasons(red_entries, "red"),
            "red_stderr": "not emitted",
            "judge_stdout": _first_str(judge_receipt.get("reason"), scoreboard.get("verdict"), run_receipt.get("verdict"), ""),
            "judge_stderr": "not emitted",
            "functionality_stdout": "",
            "scoreboard": scoreboard,
            "lineage_spawns": lineage_spawns,
            "lineage_request": lineage_request,
            "receipt_refs": [
                *_tau_public_receipts(red_entries=red_entries, blue_entries=blue_entries, visibility=visibility),
                *_lineage_receipts(lineage_spawns),
            ],
            "tau_manifest_status": manifest.get("status"),
            "tau_timing": manifest.get("timing") if isinstance(manifest.get("timing"), dict) else {},
            "visibility_status": visibility.get("status"),
            "arena_status": arena_receipt.get("status"),
        }
    )
    return _fixture_from_facts(facts)


def _fixture_from_facts(facts: dict[str, Any]) -> dict[str, Any]:
    lanes = [_lane_from_red(facts=facts, red=red) for red in facts["red_entries"]]
    lanes = _apply_lineage_to_lanes(lanes=lanes, facts=facts)
    _attach_elapsed_timing(lanes=lanes, facts=facts)
    _attach_activity_segments(lanes)
    _attach_exploit_profiles(lanes=lanes, facts=facts)
    _attach_lane_score_semantics(lanes=lanes, facts=facts)
    _attach_lane_replay_semantics(lanes=lanes)
    _attach_actor_visuals(lanes)
    events = _with_timeline_order(_events(facts=facts))
    blue_actions = _blue_patch_actions(facts=facts)
    leaderboard = [_leaderboard_entry(facts=facts, lane=lane) for lane in lanes]
    battle_clock = _battle_clock(facts=facts)
    round_config = _round_config(facts=facts, battle_clock=battle_clock)
    clock = _canonical_clock(facts=facts, battle_clock=battle_clock, round_config=round_config)
    timeline_control = _battle_timeline_control(clock=clock, timeline=_timeline(facts=facts, lanes=lanes, events=events))
    scoreboard = _scoreboard_payload(facts, lanes=lanes)
    proof_blockers = _proof_blockers(facts=facts)
    fixture = {
        "schema": "battle.normalized_ux_fixture.v1",
        "battle_id": facts["battle_id"],
        "mode": "receipt_replay",
        "source_proof_dir": facts["source_proof_dir"],
        "proof_mode": PROOF_MODE,
        "generated_at": facts["generated_at"],
        "mocked": facts["mocked"],
        "live_source": facts["live_source"],
        "status": facts["status"],
        "scenario": {
            "scenario_id": facts["scenario_id"],
            "title": facts["scenario_title"],
            "public_entrypoint": facts["public_entrypoint"],
            "hidden_vulnerability_family": facts["vulnerability_family"],
            "cwe": facts["cwe"],
            "difficulty": facts["difficulty"],
            "target_language": facts["target_language"],
            "runtime_image": facts["runtime_image"],
        },
        "round_config": round_config,
        "clock": clock,
        "battle_clock": battle_clock,
        "timeline": timeline_control["_legacy_timeline"],
        "battle_timeline_control": {
            key: value for key, value in timeline_control.items() if key != "_legacy_timeline"
        },
        "sprite_theme": _sprite_theme_for_lanes(lanes),
        "semantic_replay": _semantic_replay(lanes=lanes),
        "segments": _snapshot_segments(lanes),
        "lineage_request": facts["lineage_request"],
        "lineage": _lineage_payload(facts=facts, lanes=lanes),
        "spectator_shell": _spectator_shell(facts=facts, battle_clock=battle_clock, scoreboard=scoreboard, events=events),
        "renderer_binding_contract": _renderer_binding_contract(),
        "ux_contract": _ux_contract(facts=facts, lanes=lanes, events=events, proof_blockers=proof_blockers),
        "claims": _claims(facts=facts),
        "lanes": lanes,
        "events": events,
        "proof_blockers": proof_blockers,
        "leaderboard": leaderboard,
        "receipts": facts["receipt_refs"],
        "bluePatchActions": blue_actions,
        "scoreboard": scoreboard,
    }
    fixture["validation"] = _fixture_validation(fixture)
    _attach_renderer_models(fixture)
    return fixture


def _attach_renderer_models(fixture: dict[str, Any]) -> None:
    battle_clock = fixture.get("battle_clock") if isinstance(fixture.get("battle_clock"), dict) else {}
    timeline = fixture.get("timeline") if isinstance(fixture.get("timeline"), dict) else {}
    lineage = fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {}
    lanes = fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else []
    events = fixture.get("events") if isinstance(fixture.get("events"), list) else []
    scoreboard = fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}
    elapsed_axis_model = _timeline_elapsed_axis_model(battle_clock=battle_clock, timeline=timeline)
    fixture.update(
        {
            "timeline_time_model": _timeline_time_model(battle_clock=battle_clock, timeline=timeline),
            "timeline_elapsed_axis_model": elapsed_axis_model,
            "timeline_viewport_model": _timeline_viewport_model(timeline=timeline),
            "timeline_lane_start_model": _timeline_lane_start_model(
                lineage=lineage,
                lanes=lanes,
                elapsed_axis_model=elapsed_axis_model,
            ),
            "lane_activity_timeline_model": _lane_activity_timeline_model(
                lanes=lanes,
                elapsed_axis_model=elapsed_axis_model,
            ),
            "timeline_label_layout_model": _timeline_label_layout_model(lanes=lanes),
            "lineage_render_model": _lineage_render_model(lineage=lineage, lanes=lanes),
            "spawn_gate_model": _spawn_gate_model(
                lineage=lineage,
                lanes=lanes,
                events=events,
                scoreboard=scoreboard,
            ),
            "selected_lane_model": _selected_lane_model(lineage=lineage, lanes=lanes),
            "outcome_truth_constraints_model": _outcome_truth_constraints_model(fixture=fixture),
            "lane_phase_coverage": _lane_phase_coverage(lanes),
        }
    )
    _sync_timeline_control_to_elapsed_axis(fixture)


def _sync_timeline_control_to_elapsed_axis(fixture: dict[str, Any]) -> None:
    """Align legacy timeline_control playhead with the elapsed-axis replay model."""
    control = fixture.get("battle_timeline_control")
    axis = fixture.get("timeline_elapsed_axis_model")
    if not isinstance(control, dict) or not isinstance(axis, dict):
        return
    playhead = control.get("playhead")
    axis_playhead = axis.get("playhead")
    if not isinstance(playhead, dict) or not isinstance(axis_playhead, dict):
        return
    current = _number_or_none(axis_playhead.get("current_elapsed_seconds"))
    current_x = _number_or_none(axis_playhead.get("current_x"))
    if current is None:
        return
    legacy_clock_seconds = playhead.get("current_seconds")
    playhead["current_seconds"] = current
    if current_x is not None:
        playhead["current_pct"] = current_x
    playhead["source"] = "timeline_elapsed_axis_model.playhead.current_elapsed_seconds"
    playhead["legacy_clock_current_seconds"] = legacy_clock_seconds
    playhead["semantics"] = "receipt_elapsed_axis_playhead"


def _base_facts(
    *,
    proof_root: Path,
    battle_id: str,
    run_id: str,
    generated_at: str,
    status: str,
    verdict: str,
    live_source: str,
    mocked: bool,
    scenario: dict[str, Any],
    language_contract: dict[str, Any],
    monitor_index: dict[str, Any],
    source_kind: str,
) -> dict[str, Any]:
    return {
        "battle_id": battle_id,
        "run_id": run_id,
        "generated_at": generated_at,
        "source_proof_dir": str(proof_root),
        "status": status,
        "verdict": verdict,
        "live_source": live_source,
        "mocked": mocked,
        "scenario_id": _first_str(scenario.get("scenario_id"), monitor_index.get("scenario"), "arena-zip-slip-import-001"),
        "scenario_title": _first_str(scenario.get("title"), monitor_index.get("title"), "Archive import path traversal"),
        "public_entrypoint": _public_entrypoint(_first_str(scenario.get("public_entrypoint"), "/api/import-zip")),
        "vulnerability_family": _first_str(scenario.get("hidden_vulnerability_family"), language_contract.get("hidden_bug_class"), "Zip Slip path traversal"),
        "cwe": _first_str(scenario.get("cwe"), "CWE-22"),
        "difficulty": _first_str(scenario.get("difficulty"), "medium"),
        "target_language": _first_str(scenario.get("target_language"), language_contract.get("target_language"), "python"),
        "runtime_image": _first_str(language_contract.get("runtime_image"), "python:3.12-slim"),
        "source_kind": source_kind,
        "lineage_spawns": [],
        "lineage_request": _default_lineage_request(),
    }


def _lane_from_red(*, facts: dict[str, Any], red: dict[str, Any]) -> dict[str, Any]:
    lane_id = red["lane_id"]
    best_attempt = _best_attempt_for_lane(facts["attempts"], lane_id)
    blue_success = best_attempt.get("verdict") == "BLUE_SUCCESS"
    red_pass = red["status"] == "PASS"
    blue_entry = _blue_for_attempt(facts["blue_entries"], best_attempt)
    blue_pass = bool(blue_entry and blue_entry.get("status") == "PASS")
    terminal = "blocked" if blue_success else "none"
    signal_label = "EXPLOIT_CONFIRMED" if red_pass else "RED_ARTIFACT_BLOCKED"
    judge_label = "BLUE_SUCCESS" if blue_success else "INSUFFICIENT_EVIDENCE"
    replay = _replay_for_lane(facts=facts, lane_id=lane_id, attempt=best_attempt)
    return {
        "id": lane_id,
        "name": DEFAULT_LANE_NAME if lane_id == DEFAULT_LANE_ID else f"{DEFAULT_LANE_NAME} {red['worker_id']}",
        "payloadId": DEFAULT_PAYLOAD_ID if lane_id == DEFAULT_LANE_ID else f"{DEFAULT_PAYLOAD_ID}-{red['worker_id']}",
        "generation": 1,
        "team": "red",
        "xStart": 7,
        "xEnd": 84,
        "runnerX": 82 if blue_success else 50,
        "runnerState": "blocked" if blue_success else "research",
        "runnerVerb": "blocked by Blue" if blue_success else "insufficient evidence",
        "lineColor": "red",
        "terminal": terminal,
        "events": [
            _lane_event(f"{lane_id}:arena", "research", 14, "ARENA SCENARIO", "public", "arena-receipt"),
            _lane_event(f"{lane_id}:red", "payload", 33, "RED EXPLOIT", "materialized" if red_pass else "blocked", _receipt_id_for_red(red)),
            _lane_event(f"{lane_id}:useful", "useful", 50, signal_label, "before patch", _receipt_id_for_red(red), animation="pause_terminal"),
            *(
                [_lane_event(f"{lane_id}:blue", "blue_blast", 67, "PATCH", "blue", _receipt_id_for_blue(blue_entry), blue_source_id=blue_entry["action_id"], animation="blue_sonic_blast")]
                if blue_pass
                else []
            ),
            _lane_event(f"{lane_id}:judge", "blocked", 82, judge_label, "judge", "judge-receipt", animation="blue_sonic_blast"),
        ],
        "inheritedContext": [
            f"{facts['cwe']} {facts['vulnerability_family']}",
            f"Public entrypoint {facts['public_entrypoint']}",
            f"Red worker {red['worker_id']} status {red['status']}",
            f"Blue worker {blue_entry.get('worker_id') if blue_entry else 'none'} status {blue_entry.get('status') if blue_entry else 'missing'}",
            f"Judge verdict {best_attempt.get('verdict', facts['verdict'])}",
        ],
        "mutationRationale": (
            "Receipt-backed BATTLE-004 Tau worker lane. The lane only shows worker and Judge events present in receipts. "
            "No child spawn, Blue kill, fastest crash, or promotion is shown."
        ),
        "stdout": [
            facts.get("red_stdout") or _first_str(red.get("reason"), "not emitted"),
            facts.get("judge_stdout") or _first_str(best_attempt.get("verdict"), "not emitted"),
        ],
        "stderr": [facts.get("red_stderr") or "not emitted", facts.get("judge_stderr") or "not emitted"],
        "receipts": [receipt["receipt_id"] for receipt in facts["receipt_refs"]],
        "proofMode": PROOF_MODE,
        "scenario": {
            "battle_id": facts["battle_id"],
            "public_entrypoint": facts["public_entrypoint"],
            "hidden_vulnerability_family": facts["vulnerability_family"],
            "scenario_id": facts["scenario_id"],
        },
        "replay": replay,
        "cockpit": _cockpit_for_lane(
            facts=facts,
            red=red,
            lane_id=lane_id,
            attempt=best_attempt,
            blue_entry=blue_entry,
            red_pass=red_pass,
            blue_success=blue_success,
            replay=replay,
        ),
    }


def _cockpit_for_lane(
    *,
    facts: dict[str, Any],
    red: dict[str, Any],
    lane_id: str,
    attempt: dict[str, Any],
    blue_entry: dict[str, Any] | None,
    red_pass: bool,
    blue_success: bool,
    replay: dict[str, Any] | None,
) -> dict[str, Any]:
    worker_id = str(red.get("worker_id") or lane_id)
    payload_id = DEFAULT_PAYLOAD_ID if lane_id == DEFAULT_LANE_ID else f"{DEFAULT_PAYLOAD_ID}-{worker_id}"
    tau_subagent_id = _first_str(red.get("tau_subagent_id"), worker_id, f"fixture-tau-{payload_id}")
    blue_status = "blocked" if blue_success else "proof_pending"
    latest_receipt_id = _receipt_id_for_red(red)
    if blue_success:
        latest_receipt_id = "judge-receipt"
    public_trace = {
        "observation": f"{facts['cwe']} {facts['vulnerability_family']} at {facts['public_entrypoint']}.",
        "hypothesis": "A materialized Red exploit can exercise the archive import path traversal before Blue patch replay.",
        "action": "Materialize Red worker artifact, replay against materialized Blue patch, and preserve Judge pair verdict.",
        "result": "BLUE_SUCCESS" if blue_success else ("EXPLOIT_CONFIRMED" if red_pass else "INSUFFICIENT_EVIDENCE"),
        "learned": "EXPLOIT_CONFIRMED" if red_pass else "not emitted",
        "next_move": (
            "Render parent/child handoff only from lineage receipts; do not infer fastest crash or promotion."
            if blue_success
            else "Wait for a Judge replay receipt or materialization proof before showing terminal outcome."
        ),
    }
    skill_label = "MOCKED SKILL" if facts.get("mocked") else "FIXTURE SKILL TRACE"
    return {
        "schema": "battle.lane_cockpit.v1",
        "proof_mode": PROOF_MODE,
        "proof_label": "FIXTURE TRACE",
        "selected_tau_exploit_subagent": {
            "actor_id": lane_id,
            "payload_id": payload_id,
            "tau_subagent_id": tau_subagent_id,
            "tau_run_id": facts["run_id"],
            "tau_turn_id": f"{facts['run_id']}:{worker_id}:red",
            "worker_id": worker_id,
            "generation": 1,
            "missing_tau_id": False,
        },
        "current_turn": {
            "loop_index": 1,
            "phase": "red_exploit",
            "current_action": "Materialize Red exploit artifact.",
            "status": "PASS" if red_pass else "BLOCKED",
        },
        "public_trace": public_trace,
        "output": {
            "stdout": [
                facts.get("red_stdout") or _first_str(red.get("reason"), "not emitted"),
                facts.get("judge_stdout") or _first_str(attempt.get("verdict"), "not emitted"),
            ],
            "stderr": [facts.get("red_stderr") or "not emitted", facts.get("judge_stderr") or "not emitted"],
        },
        "skills_tools": [
            {
                "name": "scillm.chat_completions" if facts["source_kind"] == "tau_public_only" else "docker-replay",
                "kind": "tool",
                "status": "ok" if red_pass else "pending",
                "proof_label": skill_label,
                "receipt_id": _receipt_id_for_red(red),
                "proof_mode": PROOF_MODE,
            },
            {
                "name": "docker-replay",
                "kind": "tool",
                "status": "ok" if blue_success else "pending",
                "proof_label": "FIXTURE SKILL TRACE",
                "receipt_id": "judge-receipt",
                "proof_mode": PROOF_MODE,
            },
        ],
        "memory_project_knowledge_events": [],
        "learned": public_trace["learned"],
        "next_move": public_trace["next_move"],
        "blue_outcome": {
            "detected": bool(blue_entry),
            "blocked": blue_success,
            "killed": False,
            "forced_handoff": False,
            "status": blue_status,
            "receipt_id": "judge-receipt" if blue_success else None,
            "proof_mode": PROOF_MODE,
        },
        "latest_receipt_id": latest_receipt_id,
        "replay": deepcopy(replay),
    }


def _apply_lineage_to_lanes(*, lanes: list[dict[str, Any]], facts: dict[str, Any]) -> list[dict[str, Any]]:
    lane_by_id = {str(lane["id"]): lane for lane in lanes}
    valid_spawns = _valid_lineage_spawns(facts=facts, lane_by_id=lane_by_id)
    if not valid_spawns:
        return lanes

    children_by_parent: dict[str, list[str]] = {}
    for spawn in valid_spawns:
        parent_lane_id = spawn["parent_lane_id"]
        child_lane_id = spawn["child_lane_id"]
        children_by_parent.setdefault(parent_lane_id, []).append(child_lane_id)

        parent = lane_by_id[parent_lane_id]
        child = lane_by_id[child_lane_id]
        spawn_x = int(spawn.get("x") or spawn.get("spawn_x") or 58)
        child_x_start = int(spawn.get("child_x_start") or spawn_x)
        inherited_context = [str(value) for value in spawn.get("inherited_context", []) if value]

        parent.setdefault("children", [])
        parent["children"] = sorted({*parent.get("children", []), child_lane_id})
        parent["lineageGroupId"] = f"lineage:{parent_lane_id}"
        parent["collapsible"] = True
        parent["expandedByDefault"] = True
        parent["expanded"] = True
        parent["runnerState"] = "blocked_handoff"
        parent["runnerVerb"] = "handoff"
        parent["terminal"] = "blocked_handoff"
        parent["xEnd"] = max(int(parent.get("xEnd", 0)), spawn_x)
        parent["runnerX"] = max(int(parent.get("runnerX", 0)), spawn_x)
        parent["events"].append(
            _lane_event(
                f"{parent_lane_id}:spawn:{child_lane_id}",
                "handoff",
                spawn_x,
                str(spawn.get("label") or "SPAWN CHILD"),
                str(spawn.get("time_label") or "handoff"),
                str(spawn["receipt_id"]),
                animation="child_ignite",
            )
        )
        parent["mutationRationale"] = (
            "Receipt-backed parent handoff spawned child lane(s). "
            "No fastest crash, survivor promotion, Blue kill, or killed state is inferred without separate receipts."
        )
        parent_cockpit = parent.get("cockpit") if isinstance(parent.get("cockpit"), dict) else {}
        if parent_cockpit:
            parent_cockpit["next_move"] = "Handoff spawned a child lane from the lineage receipt; continue inspection on the child lane."
            parent_cockpit["latest_receipt_id"] = str(spawn["receipt_id"])
            public_trace = parent_cockpit.get("public_trace") if isinstance(parent_cockpit.get("public_trace"), dict) else {}
            public_trace["result"] = "SPAWN CHILD"
            public_trace["next_move"] = parent_cockpit["next_move"]
            parent_cockpit["public_trace"] = public_trace
            blue_outcome = parent_cockpit.get("blue_outcome") if isinstance(parent_cockpit.get("blue_outcome"), dict) else {}
            blue_outcome["forced_handoff"] = True
            blue_outcome["status"] = "blocked_handoff"
            blue_outcome["receipt_id"] = str(spawn["receipt_id"])
            parent_cockpit["blue_outcome"] = blue_outcome

        child["parentId"] = parent_lane_id
        child["parent_id"] = parent_lane_id
        child["lineageGroupId"] = f"lineage:{parent_lane_id}"
        child["collapsible"] = False
        child["expandedByDefault"] = True
        child["generation"] = int(spawn.get("generation") or max(int(parent.get("generation", 1)) + 1, 2))
        child["lineColor"] = "green" if child.get("terminal") == "blocked" else "purple"
        child["xStart"] = child_x_start
        if not isinstance(child.get("replay"), dict) and isinstance(parent.get("replay"), dict):
            child["replay"] = deepcopy(parent["replay"])
            child["replay"]["red_lane_id"] = child_lane_id
            child["replay"]["inherited_from_parent_lane_id"] = parent_lane_id
            child["replay"]["inheritance_reason"] = "Child lane has no separate Judge replay receipt; show parent receipt-only Docker replay CTA."
            child_cockpit_for_replay = child.get("cockpit") if isinstance(child.get("cockpit"), dict) else {}
            if child_cockpit_for_replay:
                child_cockpit_for_replay["replay"] = deepcopy(child["replay"])
        _rebase_child_lane_events(child, child_x_start)
        child_event_x = [int(event.get("x", child_x_start)) for event in child.get("events", []) if isinstance(event, dict)]
        child["xEnd"] = max([child_x_start + 24, *child_event_x])
        child["runnerX"] = max([child_x_start + 18, *child_event_x])
        child["inheritedContext"] = [*inherited_context, *child.get("inheritedContext", [])]
        child["events"].insert(
            0,
            _lane_event(
                f"{child_lane_id}:spawned-from:{parent_lane_id}",
                "handoff",
                child_x_start,
                "SPAWNED",
                str(spawn.get("time_label") or "handoff"),
                str(spawn["receipt_id"]),
                animation="child_ignite",
            ),
        )
        child["mutationRationale"] = (
            f"Receipt-backed child lane spawned from {parent_lane_id}. "
            "Subsequent state is limited to this child's own Red/Blue/Judge receipts."
        )
        child_cockpit = child.get("cockpit") if isinstance(child.get("cockpit"), dict) else {}
        if child_cockpit:
            selected = child_cockpit.get("selected_tau_exploit_subagent") if isinstance(child_cockpit.get("selected_tau_exploit_subagent"), dict) else {}
            selected["generation"] = child["generation"]
            selected["parent_lane_id"] = parent_lane_id
            selected["spawn_receipt_id"] = str(spawn["receipt_id"])
            child_cockpit["selected_tau_exploit_subagent"] = selected
            child_cockpit["current_turn"] = {
                "loop_index": child["generation"],
                "phase": "child_red_exploit",
                "current_action": "Continue Red exploit from receipt-backed parent handoff.",
                "status": "PASS",
            }
            public_trace = child_cockpit.get("public_trace") if isinstance(child_cockpit.get("public_trace"), dict) else {}
            public_trace["observation"] = f"Spawned from parent lane {parent_lane_id} at x={child_x_start}."
            public_trace["action"] = "Continue exploit using inherited parent context from lineage receipt."
            public_trace["next_move"] = "Judge this child lane only from its own Red/Blue pair receipts."
            child_cockpit["public_trace"] = public_trace
            child_cockpit["latest_receipt_id"] = str(spawn["receipt_id"])
            child_cockpit["next_move"] = public_trace["next_move"]

    for parent_lane_id, child_ids in children_by_parent.items():
        lane_by_id[parent_lane_id]["summary"] = f"{len(child_ids)} child lane(s) receipt-backed"
    return lanes


def _rebase_child_lane_events(child: dict[str, Any], child_x_start: int) -> None:
    offsets = {
        "research": 4,
        "payload": 14,
        "useful": 24,
        "blue_blast": 34,
        "blocked": 44,
        "handoff": 0,
    }
    for event in child.get("events", []):
        if not isinstance(event, dict):
            continue
        kind = str(event.get("kind") or "")
        next_x = min(98, child_x_start + offsets.get(kind, 10))
        event["x"] = next_x
        event["order_index"] = next_x
        event["collision_group"] = _collision_group_for_x(next_x)


def _attach_activity_segments(lanes: list[dict[str, Any]]) -> None:
    for lane in lanes:
        lane["events"] = _sorted_lane_events(lane.get("events", []))
        lane["activitySegments"] = _activity_segments_for_lane(lane)


def _attach_exploit_profiles(*, lanes: list[dict[str, Any]], facts: dict[str, Any]) -> None:
    spawn_count = len(_valid_lineage_spawns(facts=facts))
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane["exploit_profile"] = _exploit_profile_for_lane(lane=lane, spawn_count=spawn_count)


def _exploit_profile_for_lane(*, lane: dict[str, Any], spawn_count: int) -> dict[str, Any]:
    is_child = bool(lane.get("parentId"))
    has_payload = any(isinstance(event, dict) and event.get("kind") in {"payload", "useful"} for event in lane.get("events", []))
    is_blocked = str(lane.get("terminal") or "") in {"blocked", "blocked_handoff"}
    lineage_pressure = 0.0
    if is_child:
        lineage_pressure = 0.65
    elif spawn_count > 0 and lane.get("children"):
        lineage_pressure = 0.45

    strength = 0.82 if has_payload else 0.35
    complexity = 0.58 + (0.22 if is_child else 0.10) + min(0.10, lineage_pressure * 0.10)
    durability = 0.62 + (0.10 if is_blocked else 0.0) + (0.06 if is_child else 0.0)
    reproducibility = 0.84 if has_payload else 0.40
    stealth = 0.42 + (0.10 if is_child else 0.0)
    score_weight = round((strength * 0.35) + (complexity * 0.25) + (durability * 0.25) + (reproducibility * 0.15), 3)
    tier = _exploit_tier(score_weight=score_weight, lineage_pressure=lineage_pressure)
    return {
        "schema": EXPLOIT_PROFILE_VERSION,
        "lane_id": str(lane.get("id") or ""),
        "strength": round(min(strength, 1.0), 3),
        "complexity": round(min(complexity, 1.0), 3),
        "durability": round(min(durability, 1.0), 3),
        "stealth": round(min(stealth, 1.0), 3),
        "reproducibility": round(min(reproducibility, 1.0), 3),
        "lineage_pressure": round(min(lineage_pressure, 1.0), 3),
        "score_weight": score_weight,
        "tier": tier,
        "evidence_source": "receipt_events_and_lineage",
        "proof_scope": {
            "receipt_backed_inputs": True,
            "heuristic_profile": True,
            "does_not_prove": [
                "Exploit profile is a deterministic scoring projection, not independent exploit truth.",
                "Sprite tier does not prove Battle outcome.",
            ],
        },
    }


def _exploit_tier(*, score_weight: float, lineage_pressure: float) -> str:
    if lineage_pressure >= 0.6:
        return "adaptive_lineage"
    if score_weight >= 0.78:
        return "heavy_durable"
    if score_weight >= 0.62:
        return "standard_exploit"
    return "fragile_probe"


def _attach_lane_score_semantics(*, lanes: list[dict[str, Any]], facts: dict[str, Any]) -> None:
    spawn_count = len(_valid_lineage_spawns(facts=facts))
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane["score_semantics"] = _lane_score_semantics(lane=lane, spawn_count=spawn_count)
        cockpit = lane.get("cockpit") if isinstance(lane.get("cockpit"), dict) else {}
        if cockpit:
            cockpit["score_semantics"] = deepcopy(lane["score_semantics"])


def _lane_score_semantics(*, lane: dict[str, Any], spawn_count: int) -> dict[str, Any]:
    profile = lane.get("exploit_profile") if isinstance(lane.get("exploit_profile"), dict) else {}
    profile_weight = float(_number_or_none(profile.get("score_weight")) or 0.5)
    is_child = bool(lane.get("parentId"))
    is_blocked = str(lane.get("terminal") or "") in {"blocked", "blocked_handoff"}
    if not is_blocked:
        tier = "UNRESOLVED"
        blue_delta = 0.0
        red_delta = round(4.0 * profile_weight, 3)
    elif spawn_count == 0:
        tier = "PRE_SPAWN_BLOCK"
        blue_delta = round(12.0 * profile_weight, 3)
        red_delta = round(2.0 * profile_weight, 3)
    elif is_child:
        tier = "POST_SPAWN_CONTAINMENT"
        blue_delta = round(7.0 * profile_weight, 3)
        red_delta = round(3.5 * profile_weight, 3)
    else:
        tier = "SPAWN_PRESSURE_CONCEDED"
        blue_delta = round(4.0 * profile_weight, 3)
        red_delta = round(4.5 * profile_weight, 3)
    return {
        "schema": SEMANTIC_SCORE_VERSION,
        "lane_id": str(lane.get("id") or ""),
        "outcome_tier": tier,
        "score_basis": "judge_receipts_lineage_and_exploit_profile",
        "score_delta": {
            "red": red_delta,
            "blue": blue_delta,
        },
        "rules": {
            "pre_spawn_block_is_highest_blue_credit": True,
            "spawn_pressure_reduces_blue_credit": True,
            "functionality_preservation_required_for_full_blue_credit": True,
            "sprite_choice_does_not_create_score_truth": True,
        },
        "proof_mode": PROOF_MODE,
    }


def _attach_lane_replay_semantics(*, lanes: list[dict[str, Any]]) -> None:
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane["replay_semantics"] = _lane_replay_semantics(lane)


def _lane_replay_semantics(lane: dict[str, Any]) -> dict[str, Any]:
    profile = lane.get("exploit_profile") if isinstance(lane.get("exploit_profile"), dict) else {}
    score_semantics = lane.get("score_semantics") if isinstance(lane.get("score_semantics"), dict) else {}
    events = [
        {
            "source_time_seconds": _number_or_none(event.get("elapsed_seconds")),
            "phase": _replay_phase_for_event(event),
            "importance": _replay_importance_for_event(event),
            "lineage_pressure": profile.get("lineage_pressure", 0),
            "score_delta": score_semantics.get("score_delta", {}),
            "receipt_id": _first_str(event.get("receipt_id"), event.get("receiptId"), ""),
            "source_event_id": _first_str(event.get("id"), ""),
            "proof_mode": PROOF_MODE,
        }
        for event in lane.get("events", [])
        if isinstance(event, dict) and _number_or_none(event.get("elapsed_seconds")) is not None
    ]
    return {
        "schema": REPLAY_SEMANTICS_VERSION,
        "lane_id": str(lane.get("id") or ""),
        "time_authority": "receipt_elapsed_seconds",
        "presentation_owner": "ux",
        "backend_must_not_emit": ["cinematic_speed", "easing", "camera_path", "pixi_frame_timing"],
        "events": events,
        "proof_mode": PROOF_MODE,
    }


def _replay_phase_for_event(event: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "")
    if kind == "blue_blast":
        return "blue_defense_intervention"
    if kind == "blocked":
        return "judge_block_verdict"
    if kind == "handoff":
        return "lineage_spawn_pressure"
    if kind in {"payload", "useful"}:
        return "red_exploit_pressure"
    return kind or "receipt_event"


def _replay_importance_for_event(event: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "")
    if kind in {"blocked", "handoff"}:
        return "major"
    if kind in {"payload", "useful", "blue_blast"}:
        return "visible"
    return "background"


def _attach_actor_visuals(lanes: list[dict[str, Any]]) -> None:
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane["actor_visual"] = _actor_visual_for_lane(lane)


def _actor_visual_for_lane(lane: dict[str, Any]) -> dict[str, Any]:
    lane_id = str(lane.get("id") or "lane")
    is_child = bool(lane.get("parentId"))
    profile = lane.get("exploit_profile") if isinstance(lane.get("exploit_profile"), dict) else {}
    variant_id = _variant_id_for_lane(lane_id=lane_id, exploit_profile=profile)
    archetype = "chaos_marine_child" if is_child or variant_id in {"plague_nurgling", "nurgling"} else "chaos_marine_heavy"
    transitions = _actor_state_timeline(lane)
    initial_state = transitions[0]["state"] if transitions else ("spawn" if is_child else "idle")
    return {
        "schema": "battle.actor_visual.v1",
        "actor_id": lane_id,
        "lane_id": lane_id,
        "role": "red_exploit",
        "team": "red",
        "archetype": archetype,
        "variant_id": variant_id,
        "variant_source": "exploit_profile_tier",
        "style_family": "vintage_16bit_genesis",
        "facing": "right",
        "scale_class": "heavy_64",
        "initial_state": initial_state,
        "state_source": "canonical_events",
        "state_timeline": transitions,
        "proof_scope": {
            "cosmetic_identity_only": True,
            "terminal_states_receipt_gated": True,
            "does_not_prove": [
                "Sprite selection does not prove Battle outcome.",
            ],
        },
    }


def _actor_state_timeline(lane: dict[str, Any]) -> list[dict[str, Any]]:
    lane_id = str(lane.get("id") or "lane")
    transitions: list[dict[str, Any]] = []
    events = _sorted_lane_events(lane.get("events", []))
    for event in events:
        if not isinstance(event, dict):
            continue
        elapsed = _number_or_none(event.get("elapsed_seconds"))
        if elapsed is None:
            continue
        state = _actor_state_for_event(event=event, lane=lane)
        transition = {
            "at_seconds": elapsed,
            "state": state,
            "source_event_id": str(event.get("id") or f"{lane_id}:event"),
        }
        receipt_id = _first_str(event.get("receipt_id"), event.get("receiptId"), "")
        if receipt_id:
            transition["source_receipt_id"] = receipt_id
        segment_id = _segment_id_for_event(lane=lane, event_id=str(event.get("id") or ""))
        if segment_id:
            transition["segment_id"] = segment_id
        transition["provisional"] = False
        transitions.append(transition)
    if not transitions:
        start = _number_or_none(lane.get("start_elapsed_seconds")) or 0.0
        transitions.append(
            {
                "at_seconds": start,
                "state": "spawn" if lane.get("parentId") else "idle",
                "source_event_id": f"{lane_id}:actor-visual-default",
                "provisional": False,
            }
        )
    return transitions


def _actor_state_for_event(*, event: dict[str, Any], lane: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "")
    event_id = str(event.get("id") or "")
    if kind == "handoff" and "spawned-from" in event_id:
        return "spawn"
    if kind == "handoff":
        return "handoff"
    if kind == "research":
        return "research"
    if kind in {"payload", "useful"}:
        return "payload"
    if kind in {"blue_blast", "blocked"}:
        return "blocked"
    runner_state = str(lane.get("runnerState") or "")
    if runner_state in ACTOR_STATE_VOCABULARY:
        return runner_state
    return "run"


def _segment_id_for_event(*, lane: dict[str, Any], event_id: str) -> str | None:
    for segment in lane.get("activitySegments", []):
        if isinstance(segment, dict) and segment.get("source_event_id") == event_id:
            return str(segment.get("id") or "")
    return None


def _variant_id_for_lane(*, lane_id: str, exploit_profile: dict[str, Any] | None = None) -> str:
    profile = exploit_profile if isinstance(exploit_profile, dict) else {}
    tier = str(profile.get("tier") or "")
    lineage_pressure = _number_or_none(profile.get("lineage_pressure")) or 0.0
    strength = _number_or_none(profile.get("strength")) or 0.0
    complexity = _number_or_none(profile.get("complexity")) or 0.0
    durability = _number_or_none(profile.get("durability")) or 0.0
    if tier == "adaptive_lineage" or lineage_pressure >= 0.6:
        return "plague_nurgling"
    if tier == "heavy_durable" or (strength >= 0.75 and durability >= 0.70):
        return "crimson_hornbreaker"
    if complexity >= 0.75:
        return "purple_horn_imp"
    if lane_id in LANE_VARIANT_DEFAULTS:
        return LANE_VARIANT_DEFAULTS[lane_id]
    index = sum(ord(char) for char in lane_id) % len(SPRITE_VARIANT_ORDER)
    return SPRITE_VARIANT_ORDER[index]


def _sprite_theme_for_lanes(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    used_variant_ids = sorted(
        {
            str(lane.get("actor_visual", {}).get("variant_id"))
            for lane in lanes
            if isinstance(lane, dict)
            and isinstance(lane.get("actor_visual"), dict)
            and lane.get("actor_visual", {}).get("variant_id")
        }
    )
    return {
        "schema": "battle.sprite_theme.v1",
        "style_family": "vintage_16bit_genesis",
        "renderer": "pixijs",
        "state_vocabulary": ACTOR_STATE_VOCABULARY,
        "variants": {variant_id: _sprite_theme_variant(variant_id) for variant_id in used_variant_ids},
        "effect_sheets": {},
        "rules": {
            "backend_never_emits_animation_names": True,
            "backend_never_emits_frame_indices": True,
            "terminal_animations_receipt_gated": True,
            "nearest_neighbor_scaling": True,
            "transparent_background": True,
        },
        "proof_scope": {
            "cosmetic_identity_only": True,
            "does_not_prove": [
                "Sprite theme selection does not prove Battle outcome.",
            ],
        },
    }


def _sprite_theme_variant(variant_id: str) -> dict[str, Any]:
    return {
        "sprite_id": variant_id,
        "display_name": variant_id.replace("_", " ").title(),
        "team": "red",
        "archetype": "child" if variant_id in {"plague_nurgling", "nurgling"} else "heavy",
        "spritesheet_alias": f"battle-runner-{variant_id}",
        "src": f"/battle-sprites/pixijs/{variant_id}.json",
        "frame_width": 64,
        "frame_height": 64,
        "scale": 1,
        "anchor": {
            "x": 0.5,
            "y": 0.85,
        },
        "state_animation_map": {state: state for state in ACTOR_STATE_VOCABULARY if state != "stale_pending"}
        | {"stale_pending": "idle"},
    }


def _snapshot_segments(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for lane in lanes:
        lane_id = str(lane.get("id") or "")
        for segment in lane.get("activitySegments", []):
            if not isinstance(segment, dict):
                continue
            segments.append(
                {
                    "schema": "battle.segment.v1",
                    "id": str(segment.get("id") or f"{lane_id}:segment"),
                    "lane_id": lane_id,
                    "kind": str(segment.get("phase") or "receipt_event"),
                    "label": str(segment.get("label") or ""),
                    "start_seconds": _number_or_none(segment.get("start_elapsed_seconds")),
                    "end_seconds": _number_or_none(segment.get("end_elapsed_seconds")),
                    "start_x": segment.get("start_x"),
                    "end_x": segment.get("end_x"),
                    "source_event_id": segment.get("source_event_id"),
                    "interpolation": "receipt_backed_segment",
                    "proof_mode": PROOF_MODE,
                }
            )
    return segments


def _semantic_replay(*, lanes: list[dict[str, Any]]) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        replay = lane.get("replay_semantics") if isinstance(lane.get("replay_semantics"), dict) else {}
        lane_events = replay.get("events") if isinstance(replay.get("events"), list) else []
        for event in lane_events:
            if isinstance(event, dict):
                events.append({**event, "lane_id": str(lane.get("id") or "")})
    events.sort(key=lambda event: (_number_or_none(event.get("source_time_seconds")) or 0.0, str(event.get("source_event_id") or "")))
    return {
        "schema": "battle.semantic_replay.v1",
        "time_authority": "receipt_elapsed_seconds",
        "presentation_owner": "ux",
        "replay_mode": "compressed_spectator_replay",
        "backend_emits": ["source_time_seconds", "phase", "importance", "lineage_pressure", "score_delta", "receipt_id"],
        "backend_must_not_emit": ["cinematic_speed", "easing", "camera_path", "pixi_frame_timing"],
        "event_count": len(events),
        "events": events,
        "proof_mode": PROOF_MODE,
    }


def _fixture_validation(fixture: dict[str, Any]) -> dict[str, Any]:
    lanes = fixture.get("lanes") if isinstance(fixture.get("lanes"), list) else []
    events = fixture.get("events") if isinstance(fixture.get("events"), list) else []
    lineage = fixture.get("lineage") if isinstance(fixture.get("lineage"), dict) else {}
    child_lanes = [lane for lane in lanes if isinstance(lane, dict) and lane.get("parentId")]
    spawn_events = [event for event in events if isinstance(event, dict) and event.get("event_type") == "tau.spawned_child"]
    terminal_events = [
        event
        for event in events
        if isinstance(event, dict)
        and str(event.get("event_type") or "").startswith("judge.")
        or (isinstance(event, dict) and event.get("event_type") == "blue.blocked_red")
    ]
    errors: list[str] = []
    if child_lanes and not spawn_events:
        errors.append("child lane exists without tau.spawned_child event")
    if child_lanes and int(lineage.get("spawn_count") or 0) < len(child_lanes):
        errors.append("lineage.spawn_count is lower than derived child lane count")
    return {
        "schema": "battle.fixture_validation.v1",
        "derived_from_canonical_events": True,
        "terminal_claims_receipt_backed": all(bool(event.get("evidence") or event.get("receipts")) for event in terminal_events),
        "child_lineage_receipt_backed": not child_lanes or bool(spawn_events),
        "fail_closed": not errors,
        "errors": errors,
        "warnings": [],
        "proof_mode": PROOF_MODE,
    }


def _sorted_lane_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    return sorted(
        [event for event in events if isinstance(event, dict)],
        key=lambda event: (
            int(event.get("order_index") if isinstance(event.get("order_index"), int) else event.get("x") or 0),
            int(event.get("marker_priority") if isinstance(event.get("marker_priority"), int) else 0) * -1,
            str(event.get("id") or ""),
        ),
    )


def _activity_segments_for_lane(lane: dict[str, Any]) -> list[dict[str, Any]]:
    lane_id = str(lane.get("id") or "lane")
    lane_start = int(lane.get("xStart") or 0)
    lane_end = int(lane.get("xEnd") or lane.get("runnerX") or lane_start)
    lane_start_elapsed = _number_or_none(lane.get("start_elapsed_seconds"))
    lane_end_elapsed = _number_or_none(lane.get("end_elapsed_seconds"))
    events = [
        event
        for event in lane.get("events", [])
        if isinstance(event, dict) and isinstance(event.get("x"), int)
    ]
    events = sorted(events, key=lambda event: (int(event["x"]), str(event.get("id") or "")))

    points: list[tuple[int, dict[str, Any] | None]] = [(lane_start, None)]
    for event in events:
        x = max(lane_start, min(lane_end, int(event["x"])))
        points.append((x, event))
    if not points or points[-1][0] != lane_end:
        points.append((lane_end, None))

    segments: list[dict[str, Any]] = []
    for index, ((start_x, source_event), (end_x, _next_event)) in enumerate(zip(points, points[1:]), start=1):
        if end_x <= start_x:
            continue
        phase, label = _activity_phase(source_event)
        segments.append(
            {
                "id": f"{lane_id}:segment:{index:02d}",
                "phase": phase,
                "label": label,
                "start_x": start_x,
                "end_x": end_x,
                "start_elapsed_seconds": (
                    _number_or_none(source_event.get("elapsed_seconds"))
                    if isinstance(source_event, dict)
                    else lane_start_elapsed if start_x == lane_start else None
                ),
                "end_elapsed_seconds": (
                    _number_or_none(_next_event.get("elapsed_seconds"))
                    if isinstance(_next_event, dict)
                    else lane_end_elapsed if end_x == lane_end else None
                ),
                "source_event_id": source_event.get("id") if isinstance(source_event, dict) else None,
                "proof_mode": PROOF_MODE,
            }
        )
    return segments


def _activity_phase(event: dict[str, Any] | None) -> tuple[str, str]:
    if not isinstance(event, dict):
        return "materialize", "spawn / materialize"
    kind = str(event.get("kind") or "")
    if kind == "research":
        return "research", "research"
    if kind == "payload":
        return "payload", "payload"
    if kind == "useful":
        return "useful_signal", "useful signal"
    if kind == "blue_blast":
        return "patch_gate", "Blue patch gate"
    if kind == "blocked":
        return "judge_replay", "Judge replay"
    if kind == "handoff":
        return "handoff", "handoff / child spawn"
    return "receipt_event", kind or "receipt event"


def _events(*, facts: dict[str, Any]) -> list[dict[str, Any]]:
    scenario_payload = {"public_entrypoint": facts["public_entrypoint"], "hidden_vulnerability_family": facts["vulnerability_family"], "cwe": facts["cwe"]}
    events = [
        _event(
            "battle-004-run-started",
            facts["generated_at"],
            facts["battle_id"],
            "system",
            "battle-orchestrator",
            "battle_orchestrator",
            "battle.run_started",
            "BATTLE-004 proof loaded.",
            scenario=scenario_payload,
            ui=_ui("research", "scan_research", "visible", "Receipt-backed BATTLE-004 proof loaded.", "BATTLE-004 receipt-backed proof loaded"),
            evidence=_evidence("run-receipt", "run-receipt.json"),
        ),
        _event(
            "battle-004-scenario-loaded",
            facts["generated_at"],
            facts["battle_id"],
            "system",
            "battle-arena",
            "battle_orchestrator",
            "battle.scenario_loaded",
            f"Arena created {facts['scenario_id']} for POST {facts['public_entrypoint']}.",
            scenario=scenario_payload,
            turn=_turn(0, "arena", f"Create {facts['vulnerability_family']} scenario and Docker oracle.", "PASS"),
            ui=_ui("research", "scan_research", "spectator", f"Arena scenario created for {facts['public_entrypoint']}.", "Arena scenario created"),
            evidence=_evidence("arena-receipt", "arena/arena-receipt.json"),
        ),
    ]

    for red in facts["red_entries"]:
        events.append(_red_event(facts=facts, red=red))
    events.extend(_spawn_events(facts=facts))
    for blue in facts["blue_entries"]:
        if blue["status"] == "PASS":
            events.append(_blue_event(facts=facts, blue=blue))
    for attempt in facts["attempts"]:
        if attempt.get("verdict") == "BLUE_SUCCESS":
            events.append(_block_event(facts=facts, attempt=attempt))
    events.append(_verdict_event(facts=facts))
    return events


def _spawn_events(*, facts: dict[str, Any]) -> list[dict[str, Any]]:
    lane_ids = {red["lane_id"] for red in facts["red_entries"]}
    events: list[dict[str, Any]] = []
    for spawn in facts.get("lineage_spawns", []):
        if spawn.get("parent_lane_id") not in lane_ids or spawn.get("child_lane_id") not in lane_ids:
            continue
        events.append(
            _event(
                f"{spawn['parent_lane_id']}-spawned-{spawn['child_lane_id']}",
                facts["generated_at"],
                facts["battle_id"],
                "red",
                str(spawn["parent_lane_id"]),
                "tau_exploit_subagent" if facts["source_kind"] == "tau_public_only" else "exploit_agent",
                "tau.spawned_child",
                f"Receipt-backed parent lane {spawn['parent_lane_id']} spawned child lane {spawn['child_lane_id']}.",
                parent_id=str(spawn["parent_lane_id"]),
                parent_actor_id=str(spawn["parent_lane_id"]),
                spawned_children=[str(spawn["child_lane_id"])],
                payload_id=str(spawn.get("child_payload_id") or DEFAULT_PAYLOAD_ID),
                tau_run_id=facts["run_id"],
                tau_turn_id=f"{facts['run_id']}:{spawn['child_lane_id']}:spawn",
                handoff={
                    "handoff_schema": "tau.agent_handoff.v1",
                    "handoff_id": str(spawn["receipt_id"]),
                    "parent_tau_subagent_id": str(spawn.get("parent_tau_subagent_id") or spawn.get("parent_worker_id") or spawn["parent_lane_id"]),
                    "child_tau_subagent_ids": [str(spawn.get("child_tau_subagent_id") or spawn.get("child_worker_id") or spawn["child_lane_id"])],
                    "inherited_context": [str(value) for value in spawn.get("inherited_context", []) if value],
                    "leased_task": str(spawn.get("leased_task") or "Continue Red exploit from retained parent signal."),
                    "goal": str(spawn.get("goal") or "Spawn child Red lane from receipt-backed useful signal."),
                    "receipt_id": str(spawn["receipt_id"]),
                    "proof_mode": PROOF_MODE,
                },
                turn=_turn(2, "spawn_child", "Spawn child exploit lane from parent handoff receipt.", "PASS"),
                ui=_ui("blocked_handoff", "child_ignite", "hero", "Parent exploit spawned a receipt-backed child lane.", "Receipt-backed child lane spawned", sound_cue="spawn_rise"),
                evidence=_evidence(str(spawn["receipt_id"]), str(spawn.get("receipt_path") or "lineage-receipts.json")),
                receipts=[_receipt(str(spawn["receipt_id"]), "lineage_spawn", str(spawn.get("receipt_path") or "lineage-receipts.json"), "Receipt-backed parent-child spawn.")],
            )
        )
    return events


def _red_event(*, facts: dict[str, Any], red: dict[str, Any]) -> dict[str, Any]:
    red_pass = red["status"] == "PASS"
    return _event(
        f"{red['worker_id']}-red-exploit" if red_pass else f"{red['worker_id']}-red-blocked",
        facts["generated_at"],
        facts["battle_id"],
        "red",
        red["lane_id"],
        "tau_exploit_subagent" if facts["source_kind"] == "tau_public_only" else "exploit_agent",
        "red.learned" if red_pass else "tau.artifact_blocked",
        f"Red worker {red['worker_id']} materialized exploit artifact." if red_pass else f"Red worker {red['worker_id']} blocked: {_entry_blocked_reason(red)}",
        payload_id=DEFAULT_PAYLOAD_ID if red["lane_id"] == DEFAULT_LANE_ID else f"{DEFAULT_PAYLOAD_ID}-{red['worker_id']}",
        tau_run_id=facts["run_id"],
        tau_turn_id=f"{facts['run_id']}:{red['worker_id']}:red",
        turn=_turn(1, "red_exploit", "Materialize Red exploit artifact.", "PASS" if red_pass else "BLOCKED"),
        output={"stdout_excerpt": _excerpt(facts.get("red_stdout", ""), _first_str(red.get("reason"), "not emitted")), "stderr_excerpt": _excerpt(facts.get("red_stderr", ""), "not emitted")},
        skills=[_skill("scillm.chat_completions" if facts["source_kind"] == "tau_public_only" else "docker-replay", "Red worker proof receipt.", _receipt_id_for_red(red), facts["generated_at"])],
        ui=_ui("retry" if red_pass else "research", "retry_charge" if red_pass else "pause_terminal", "hero", "Red exploit artifact materialized." if red_pass else "Red artifact blocked.", "Red exploit materialized" if red_pass else "Red artifact blocked", sound_cue="retry_tick" if red_pass else "none"),
        evidence=_worker_evidence(_receipt_id_for_red(red), red.get("subagent_receipt") or "red-receipt.json", red),
    )


def _blue_event(*, facts: dict[str, Any], blue: dict[str, Any]) -> dict[str, Any]:
    targets = sorted({attempt["red_lane_id"] for attempt in facts["attempts"] if attempt.get("blue_worker_id") == blue["worker_id"]}) or [red["lane_id"] for red in facts["red_entries"]]
    return _event(
        f"{blue['worker_id']}-blue-patch",
        facts["generated_at"],
        facts["battle_id"],
        "blue",
        blue["action_id"],
        "tau_patch_subagent" if facts["source_kind"] == "tau_public_only" else "patch_agent",
        "blue.patch_deployed",
        f"Blue worker {blue['worker_id']} materialized patch artifact.",
        target_actor_ids=targets,
        tau_run_id=facts["run_id"],
        tau_turn_id=f"{facts['run_id']}:{blue['worker_id']}:blue",
        turn=_turn(2, "blue_patch", "Materialize Blue patch artifact.", "PASS"),
        output={"stdout_excerpt": "blue patch artifact present", "stderr_excerpt": "not emitted"},
        skills=[_skill("scillm.chat_completions" if facts["source_kind"] == "tau_public_only" else "file-overwrite", "Blue worker proof receipt.", _receipt_id_for_blue(blue), facts["generated_at"])],
        ui={"blue_animation": "patch_wave_deploy", "sound_cue": "blue_patch_deploy", "importance": "hero", "spectator_caption": "Blue patch artifact materialized.", "notification": "Blue patch materialized"},
        evidence=_evidence(_receipt_id_for_blue(blue), blue.get("subagent_receipt") or "blue-receipt.json"),
    )


def _block_event(*, facts: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    return _event(
        f"{attempt['pair_id']}-blue-success",
        facts["generated_at"],
        facts["battle_id"],
        "blue",
        attempt["blue_action_id"],
        "patch_agent",
        "blue.blocked_red",
        f"Judge verified {attempt['blue_worker_id']} blocked {attempt['red_worker_id']}.",
        target_actor_ids=[attempt["red_lane_id"]],
        tau_run_id=facts["run_id"],
        pair_id=attempt.get("pair_id"),
        red_worker_id=attempt.get("red_worker_id"),
        red_lane_id=attempt.get("red_lane_id"),
        blue_worker_id=attempt.get("blue_worker_id"),
        blue_action_id=attempt.get("blue_action_id"),
        judge_attempt={
            "pair_id": attempt.get("pair_id"),
            "red_worker_id": attempt.get("red_worker_id"),
            "red_lane_id": attempt.get("red_lane_id"),
            "blue_worker_id": attempt.get("blue_worker_id"),
            "blue_action_id": attempt.get("blue_action_id"),
            "verdict": attempt.get("verdict"),
            "status": attempt.get("status"),
        },
        receipts=[{
            **_receipt("judge-receipt", "judge", "judge/judge-receipt.json", "Judge receipt for Red/Blue worker pair."),
            "pair_id": attempt.get("pair_id"),
            "red_worker_id": attempt.get("red_worker_id"),
            "red_lane_id": attempt.get("red_lane_id"),
            "blue_worker_id": attempt.get("blue_worker_id"),
            "blue_action_id": attempt.get("blue_action_id"),
        }],
        turn=_turn(3, "judge_replay", "Run Red exploit after Blue patch and verify functionality.", "PASS"),
        output={"stdout_excerpt": _judge_output(facts), "stderr_excerpt": _excerpt(facts.get("judge_stderr", ""), "not emitted")},
        skills=[_skill("docker-replay", "Judge replayed exploit after patch and verified functionality.", "judge-receipt", facts["generated_at"])],
        ui={"runner_state": "blocked", "runner_animation": "runner_hit_by_blast", "blue_animation": "blue_sonic_blast", "impact_animation": "blue_sonic_blast", "sound_cue": "blue_blast", "importance": "hero", "spectator_caption": "Blue blocked Red exploit in Judge replay.", "notification": "Blue blocks Red exploit"},
        evidence=_evidence("judge-receipt", "judge/judge-receipt.json"),
    )


def _verdict_event(*, facts: dict[str, Any]) -> dict[str, Any]:
    pass_state = any(attempt.get("verdict") == "BLUE_SUCCESS" for attempt in facts["attempts"])
    event_type = "judge.verdict" if pass_state else "judge.insufficient_evidence"
    return _event(
        "scoreboard-blue-success" if pass_state else "judge-insufficient-evidence",
        facts["generated_at"],
        facts["battle_id"],
        "judge",
        "battle-scorekeeper",
        "scorekeeper",
        event_type,
        _scoreboard_summary(facts) if pass_state else f"Judge verdict {facts['verdict']}; executable pair proof is missing.",
        target_actor_ids=[red["lane_id"] for red in facts["red_entries"]] + [blue["action_id"] for blue in facts["blue_entries"]],
        turn=_turn(4, "verdict", "Write scoreboard and terminal run receipt.", facts["status"]),
        ui=_ui("blocked" if pass_state else "research", "runner_hit_by_blast" if pass_state else "pause_terminal", "hero", f"{facts['verdict']} · Judge replay proof.", f"{facts['verdict']} · Judge replay proof"),
        evidence=_evidence("scoreboard", "scoreboard.json"),
    )


def _manifest_entries(manifest: dict[str, Any], team: str, *, proof_root: Path) -> list[dict[str, Any]]:
    teams = manifest.get("teams") if isinstance(manifest.get("teams"), list) else []
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(teams):
        if not isinstance(item, dict) or item.get("team") != team:
            continue
        worker_id = str(item.get("worker_id") or f"{team}-{index}")
        materialized = item.get("materialized_artifact")
        if not isinstance(materialized, dict):
            materialized = item.get("materialized")
        if not isinstance(materialized, dict):
            materialized = {}
        status = _first_str(materialized.get("status"), item.get("status"), "BLOCKED")
        blocker = _worker_blocker_from_manifest_item(proof_root=proof_root, item=item)
        if team == "red":
            entries.append(
                _red_entry(
                    worker_id=worker_id,
                    lane_id=str(item.get("lane_id") or (DEFAULT_LANE_ID if len(entries) == 0 else f"payload-857-{worker_id}")),
                    status=status,
                    materialized_path=str(materialized.get("path") or ""),
                    subagent_receipt=str(item.get("subagent_receipt") or f"tau-live/red/{worker_id}/tau-subagent-receipt.json"),
                    reason=_first_str(materialized.get("reason"), item.get("error")),
                    blocker=blocker,
                )
            )
        else:
            entries.append(
                _blue_entry(
                    worker_id=worker_id,
                    action_id=f"blue-{worker_id}-patch" if worker_id != "blue-0" else DEFAULT_BLUE_ACTION_ID,
                    status=status,
                    materialized_path=str(materialized.get("path") or ""),
                    subagent_receipt=str(item.get("subagent_receipt") or f"tau-live/blue/{worker_id}/tau-subagent-receipt.json"),
                    reason=_first_str(materialized.get("reason"), item.get("error")),
                    blocker=blocker,
                )
            )
    return entries


def _attempts_from_tau_judge(*, judge_receipt: dict[str, Any], red_entries: list[dict[str, Any]], blue_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts = judge_receipt.get("attempts")
    if isinstance(attempts, list):
        return [_normalize_attempt(attempt, red_entries, blue_entries) for attempt in attempts if isinstance(attempt, dict)]
    if judge_receipt.get("status") == "PASS" and red_entries and blue_entries:
        return _attempts_from_judge(judge_receipt=judge_receipt, red_entries=red_entries, blue_entries=blue_entries)
    return []


def _attempts_from_judge(*, judge_receipt: dict[str, Any], red_entries: list[dict[str, Any]], blue_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not red_entries or not blue_entries:
        return []
    red = red_entries[0]
    blue = blue_entries[0]
    verdict = _first_str(judge_receipt.get("verdict"), "INSUFFICIENT_EVIDENCE")
    if judge_receipt.get("exploit_blocked_after_patch") is True:
        verdict = "BLUE_SUCCESS"
    return [
        {
            "pair_id": f"{red['worker_id']}__{blue['worker_id']}",
            "status": _first_str(judge_receipt.get("status"), "UNKNOWN"),
            "verdict": verdict,
            "red_worker_id": red["worker_id"],
            "red_lane_id": red["lane_id"],
            "blue_worker_id": blue["worker_id"],
            "blue_action_id": blue["action_id"],
            "exploit_confirmed_before_patch": bool(judge_receipt.get("exploit_confirmed_before_patch")),
            "exploit_blocked_after_patch": bool(judge_receipt.get("exploit_blocked_after_patch")),
            "functionality_preserved": bool(judge_receipt.get("functionality_preserved")),
        }
    ]


def _normalize_attempt(attempt: dict[str, Any], red_entries: list[dict[str, Any]], blue_entries: list[dict[str, Any]]) -> dict[str, Any]:
    red_worker_id = _first_str(attempt.get("red_worker_id"), red_entries[0]["worker_id"] if red_entries else "red-0")
    blue_worker_id = _first_str(attempt.get("blue_worker_id"), blue_entries[0]["worker_id"] if blue_entries else "blue-0")
    red = next((entry for entry in red_entries if entry["worker_id"] == red_worker_id), red_entries[0] if red_entries else _red_entry(red_worker_id, DEFAULT_LANE_ID, "BLOCKED", "", "", "missing"))
    blue = next((entry for entry in blue_entries if entry["worker_id"] == blue_worker_id), blue_entries[0] if blue_entries else _blue_entry(blue_worker_id, DEFAULT_BLUE_ACTION_ID, "BLOCKED", "", "", "missing"))
    normalized = {
        "pair_id": _first_str(attempt.get("pair_id"), f"{red_worker_id}__{blue_worker_id}"),
        "status": _first_str(attempt.get("status"), "UNKNOWN"),
        "verdict": _first_str(attempt.get("verdict"), "INSUFFICIENT_EVIDENCE"),
        "red_worker_id": red_worker_id,
        "red_lane_id": _first_str(attempt.get("red_lane_id"), red["lane_id"]),
        "blue_worker_id": blue_worker_id,
        "blue_action_id": _first_str(attempt.get("blue_action_id"), blue["action_id"]),
        "exploit_confirmed_before_patch": bool(attempt.get("exploit_confirmed_before_patch")),
        "exploit_blocked_after_patch": bool(attempt.get("exploit_blocked_after_patch")),
        "functionality_preserved": bool(attempt.get("functionality_preserved")),
    }
    for key in ("started_elapsed_seconds", "ended_elapsed_seconds", "duration_elapsed_seconds"):
        value = _number_or_none(attempt.get(key))
        if value is not None:
            normalized[key] = value
    timing_source = _first_str(attempt.get("timing_source"), "")
    if timing_source:
        normalized["timing_source"] = timing_source
    return normalized


def _red_entry(
    worker_id: str,
    lane_id: str,
    status: str,
    materialized_path: str,
    subagent_receipt: str,
    reason: str | None,
    blocker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {"team": "red", "worker_id": worker_id, "lane_id": lane_id, "status": status, "path": materialized_path, "subagent_receipt": subagent_receipt, "reason": reason}
    if blocker:
        entry["blocker"] = blocker
    return entry


def _blue_entry(
    worker_id: str,
    action_id: str,
    status: str,
    materialized_path: str,
    subagent_receipt: str,
    reason: str | None,
    blocker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {"team": "blue", "worker_id": worker_id, "action_id": action_id, "status": status, "path": materialized_path, "subagent_receipt": subagent_receipt, "reason": reason}
    if blocker:
        entry["blocker"] = blocker
    return entry


def _blue_patch_actions(*, facts: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for blue in facts["blue_entries"]:
        if blue["status"] != "PASS":
            continue
        targets = sorted({attempt["red_lane_id"] for attempt in facts["attempts"] if attempt.get("blue_worker_id") == blue["worker_id"]}) or [red["lane_id"] for red in facts["red_entries"]]
        actions.append(
            {
                "id": blue["action_id"],
                "name": "Receipt-backed Patch" if blue["worker_id"] == "blue-0" else f"Receipt-backed Patch {blue['worker_id']}",
                "agentName": "tau-blue" if facts["source_kind"] == "tau_public_only" else "deterministic-blue-language-selector",
                "xStart": 56,
                "xEnd": 82,
                "targetLaneIds": targets,
                "state": "deployed",
                "receiptId": _receipt_id_for_blue(blue),
                "proofMode": PROOF_MODE,
                "summary": f"Blue patch artifact present for {facts['vulnerability_family']}.",
            }
        )
    return actions


def _leaderboard_entry(*, facts: dict[str, Any], lane: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": int(lane["generation"]),
        "laneId": lane["id"],
        "name": lane["name"],
        "status": lane["terminal"] if lane["terminal"] == "blocked" else "blocked",
        "time": "judge",
        "proofMode": PROOF_MODE,
        "summary": f"{facts['verdict']}: {lane['runnerVerb']}.",
    }


def _claims(*, facts: dict[str, Any]) -> dict[str, list[str]]:
    proves = ["Arena created a receipt-backed scenario with entry point, runtime, and language constraints."]
    if facts["source_kind"] == "tau_public_only":
        proves.append("Tau consumed public-only Red and Blue handoffs and wrote subagent receipts.")
    if any(red["status"] == "PASS" for red in facts["red_entries"]):
        proves.append("At least one Red exploit artifact was materialized.")
    if any(blue["status"] == "PASS" for blue in facts["blue_entries"]):
        proves.append("At least one Blue patch artifact was materialized.")
    if any(attempt.get("verdict") == "BLUE_SUCCESS" for attempt in facts["attempts"]):
        proves.append("Judge replay verified BLUE_SUCCESS for at least one Red/Blue pair.")
    if _has_valid_lineage(facts):
        proves.append("A parent Red lane spawned a child Red lane from an explicit lineage receipt.")
    does_not_prove = [
        "Unbounded Battle swarm execution.",
        "Multi-round Battle orchestration.",
        "Blue kill attribution.",
        "Fastest crash or survivor promotion.",
    ]
    if not _has_valid_lineage(facts):
        does_not_prove.insert(2, "Child-spawn lineage.")
    return {
        "proves": proves,
        "does_not_prove": does_not_prove,
    }


def _scoreboard_payload(facts: dict[str, Any], lanes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    scoreboard = facts["scoreboard"] if isinstance(facts["scoreboard"], dict) else {}
    blue_success_count = sum(1 for attempt in facts["attempts"] if attempt.get("verdict") == "BLUE_SUCCESS")
    semantic_scoring = _semantic_scoring_payload(lanes or [])
    return {
        "red_score": scoreboard.get("red_score"),
        "blue_score": scoreboard.get("blue_score"),
        "tdsr": scoreboard.get("tdsr"),
        "asc": scoreboard.get("asc"),
        "verdict": facts["verdict"],
        "requested_red_workers": scoreboard.get("requested_workers", {}).get("red") if isinstance(scoreboard.get("requested_workers"), dict) else len(facts["red_entries"]),
        "requested_blue_workers": scoreboard.get("requested_workers", {}).get("blue") if isinstance(scoreboard.get("requested_workers"), dict) else len(facts["blue_entries"]),
        "red_lane_count": len(facts["red_entries"]),
        "blue_action_count": len(facts["blue_entries"]),
        "child_spawn_count": len(_valid_lineage_spawns(facts=facts)),
        "red_materialized_count": scoreboard.get("red_materialized_count", sum(1 for red in facts["red_entries"] if red.get("status") == "PASS")),
        "blue_materialized_count": scoreboard.get("blue_materialized_count", sum(1 for blue in facts["blue_entries"] if blue.get("status") == "PASS")),
        "judged_pair_count": scoreboard.get("judged_pair_count", len(facts["attempts"])),
        "blue_success_count": scoreboard.get("blue_success_count", blue_success_count),
        "per_pair": scoreboard.get("per_pair", facts["attempts"]),
        "semantic_scoring": semantic_scoring,
    }


def _semantic_scoring_payload(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    lane_scores = [
        deepcopy(lane.get("score_semantics"))
        for lane in lanes
        if isinstance(lane, dict) and isinstance(lane.get("score_semantics"), dict)
    ]
    red_delta = round(sum(float(_number_or_none(score.get("score_delta", {}).get("red")) or 0.0) for score in lane_scores), 3)
    blue_delta = round(sum(float(_number_or_none(score.get("score_delta", {}).get("blue")) or 0.0) for score in lane_scores), 3)
    outcome_tiers = sorted({str(score.get("outcome_tier")) for score in lane_scores if score.get("outcome_tier")})
    return {
        "schema": SEMANTIC_SCORE_VERSION,
        "score_owner": "scorekeeper",
        "status": "advisory_contract",
        "does_not_override_legacy_scoreboard_totals": True,
        "rules": {
            "pre_spawn_block_blue_multiplier": 12.0,
            "post_spawn_containment_blue_multiplier": 7.0,
            "spawn_pressure_parent_blue_multiplier": 4.0,
            "pre_spawn_block_is_more_valuable_than_post_spawn_block": True,
            "killed_requires_explicit_kill_receipt": True,
            "functionality_preservation_required_for_full_blue_credit": True,
        },
        "semantic_totals": {
            "red": red_delta,
            "blue": blue_delta,
        },
        "outcome_tiers": outcome_tiers,
        "lanes": lane_scores,
        "proof_mode": PROOF_MODE,
    }


def _lineage_spawns(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    receipt = _read_required_json(path)
    if _first_str(receipt.get("status"), "BLOCKED") not in {"PASS", "CONFIRMED"}:
        return []
    items = receipt.get("spawns")
    if not isinstance(items, list):
        items = receipt.get("lineage")
    if not isinstance(items, list):
        items = receipt.get("children")
    if not isinstance(items, list):
        return []

    spawns: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        spawn_status = _first_str(item.get("spawn_status"), item.get("lineage_status"), receipt.get("status"), "BLOCKED")
        if spawn_status not in {"PASS", "CONFIRMED"}:
            continue
        parent_lane_id = _first_str(item.get("parent_lane_id"), item.get("parent_id"), "")
        child_lane_id = _first_str(item.get("child_lane_id"), item.get("child_id"), "")
        receipt_id = _first_str(item.get("receipt_id"), item.get("handoff_id"), f"lineage-spawn-{index}")
        if not parent_lane_id or not child_lane_id or not receipt_id:
            continue
        inherited_context = item.get("inherited_context")
        if not isinstance(inherited_context, list):
            inherited_context = item.get("inheritedContext")
        if not isinstance(inherited_context, list):
            inherited_context = []
        spawns.append(
            {
                "parent_lane_id": parent_lane_id,
                "child_lane_id": child_lane_id,
                "parent_worker_id": _first_str(item.get("parent_worker_id"), item.get("parent_tau_subagent_id"), ""),
                "child_worker_id": _first_str(item.get("child_worker_id"), item.get("child_tau_subagent_id"), ""),
                "parent_tau_subagent_id": _first_str(item.get("parent_tau_subagent_id"), item.get("parent_worker_id"), ""),
                "child_tau_subagent_id": _first_str(item.get("child_tau_subagent_id"), item.get("child_worker_id"), ""),
                "child_payload_id": _first_str(item.get("child_payload_id"), item.get("payload_id"), ""),
                "receipt_id": receipt_id,
                "receipt_path": _first_str(item.get("receipt_path"), item.get("artifact_ref"), "lineage-receipts.json"),
                "x": _int_or_none(item.get("x")) or _int_or_none(item.get("spawn_x")) or 58,
                "child_x_start": _int_or_none(item.get("child_x_start")) or _int_or_none(item.get("x")) or _int_or_none(item.get("spawn_x")) or 58,
                "generation": _int_or_none(item.get("generation")) or 2,
                "label": _first_str(item.get("label"), "SPAWN CHILD"),
                "time_label": _first_str(item.get("time_label"), item.get("timeLabel"), "handoff"),
                "spawn_status": spawn_status,
                "child_status": _first_str(item.get("child_status"), item.get("status"), ""),
                "inherited_context": inherited_context,
                "leased_task": _first_str(item.get("leased_task"), ""),
                "goal": _first_str(item.get("goal"), ""),
                **_elapsed_fields(item, "spawn_elapsed_seconds", "child_start_elapsed_seconds", "spawn_duration_elapsed_seconds"),
                **({"timing_source": _first_str(item.get("timing_source"), "")} if _first_str(item.get("timing_source"), "") else {}),
            }
        )
    return spawns


def _default_lineage_request() -> dict[str, Any]:
    return {
        "schema": "battle.lineage_request.v1",
        "requested": False,
        "mode": "not_requested",
        "condition": "Child lineage was not requested for this proof rung.",
        "status": "NOT_REQUESTED",
        "receipt": None,
        "proof_mode": PROOF_MODE,
    }


def _lineage_request(*, run_receipt: dict[str, Any], lineage_path: Path, valid_spawns: list[dict[str, Any]]) -> dict[str, Any]:
    raw = run_receipt.get("lineage_request")
    if isinstance(raw, dict):
        requested = bool(raw.get("requested"))
        receipt = raw.get("receipt")
        receipt_value = str(receipt) if isinstance(receipt, str) and receipt else None
        return {
            "schema": "battle.lineage_request.v1",
            "requested": requested,
            "mode": _first_str(raw.get("mode"), "spawn_red_child_after_blue_success" if requested else "not_requested"),
            "condition": _first_str(
                raw.get("condition"),
                "parent lane must have a Judge BLUE_SUCCESS attempt before Tau child spawn is requested"
                if requested
                else "Child lineage was not requested for this proof rung.",
            ),
            "status": _first_str(
                raw.get("status"),
                "PASS" if receipt_value and valid_spawns else "NOT_PROVEN" if requested else "NOT_REQUESTED",
            ),
            "receipt": receipt_value,
            "proof_mode": PROOF_MODE,
        }

    if lineage_path.exists():
        return {
            "schema": "battle.lineage_request.v1",
            "requested": True,
            "mode": "legacy_lineage_receipt_present",
            "condition": "A lineage receipt artifact was present; only valid PASS/CONFIRMED spawn records can create child lanes.",
            "status": "PASS" if valid_spawns else "NOT_PROVEN",
            "receipt": lineage_path.name,
            "proof_mode": PROOF_MODE,
        }

    return _default_lineage_request()


def _valid_lineage_spawns(*, facts: dict[str, Any], lane_by_id: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if lane_by_id is None:
        lane_ids = {red["lane_id"] for red in facts["red_entries"]}
    else:
        lane_ids = set(lane_by_id)
    spawns = facts.get("lineage_spawns")
    if not isinstance(spawns, list):
        return []
    return [
        spawn
        for spawn in spawns
        if isinstance(spawn, dict)
        and spawn.get("parent_lane_id") in lane_ids
        and spawn.get("child_lane_id") in lane_ids
        and spawn.get("parent_lane_id") != spawn.get("child_lane_id")
        and spawn.get("receipt_id")
    ]


def _has_valid_lineage(facts: dict[str, Any]) -> bool:
    return bool(_valid_lineage_spawns(facts=facts))


def _lineage_payload(*, facts: dict[str, Any], lanes: list[dict[str, Any]]) -> dict[str, Any]:
    lane_by_id = {str(lane["id"]): lane for lane in lanes if isinstance(lane, dict) and lane.get("id")}
    valid_spawns = _valid_lineage_spawns(facts=facts, lane_by_id=lane_by_id)
    spawns: list[dict[str, Any]] = []
    for spawn in valid_spawns:
        parent_id = str(spawn["parent_lane_id"])
        child_id = str(spawn["child_lane_id"])
        spawns.append(
            {
                "receipt_id": str(spawn["receipt_id"]),
                "receipt_path": str(spawn.get("receipt_path") or "lineage-receipts.json"),
                "parent_lane_id": parent_id,
                "child_lane_id": child_id,
                "parent_worker_id": str(spawn.get("parent_worker_id") or ""),
                "child_worker_id": str(spawn.get("child_worker_id") or ""),
                "parent_tau_subagent_id": str(spawn.get("parent_tau_subagent_id") or ""),
                "child_tau_subagent_id": str(spawn.get("child_tau_subagent_id") or ""),
                "generation": int(spawn.get("generation") or lane_by_id[child_id].get("generation") or 2),
                "spawn_x": int(spawn.get("x") or 58),
                "child_x_start": int(spawn.get("child_x_start") or spawn.get("x") or lane_by_id[child_id].get("xStart") or 58),
                **_elapsed_fields(spawn, "spawn_elapsed_seconds", "child_start_elapsed_seconds", "spawn_duration_elapsed_seconds"),
                "visible_from_elapsed_seconds": _number_or_none(spawn.get("spawn_elapsed_seconds")),
                "first_active_segment_elapsed_seconds": _number_or_none(spawn.get("child_start_elapsed_seconds")),
                **({"timing_source": _first_str(spawn.get("timing_source"), "")} if _first_str(spawn.get("timing_source"), "") else {}),
                "label": str(spawn.get("label") or "SPAWN CHILD"),
                "time_label": str(spawn.get("time_label") or "handoff"),
                "inherited_context": [str(item) for item in spawn.get("inherited_context", []) if item is not None],
                "leased_task": str(spawn.get("leased_task") or ""),
                "goal": str(spawn.get("goal") or ""),
                "proof_mode": PROOF_MODE,
            }
        )
    return {
        "mode": "receipt_backed" if spawns else "missing",
        "spawn_count": len(spawns),
        "parent_lane_ids": sorted({spawn["parent_lane_id"] for spawn in spawns}),
        "child_lane_ids": sorted({spawn["child_lane_id"] for spawn in spawns}),
        "groups": _lineage_groups(lanes=lanes, spawns=spawns),
        "spawns": spawns,
        "proof_mode": PROOF_MODE,
        "does_not_prove": [] if spawns else ["Child-spawn lineage."],
    }


def _best_attempt_for_lane(attempts: list[dict[str, Any]], lane_id: str) -> dict[str, Any]:
    for attempt in attempts:
        if attempt.get("red_lane_id") == lane_id and attempt.get("verdict") == "BLUE_SUCCESS":
            return attempt
    for attempt in attempts:
        if attempt.get("red_lane_id") == lane_id:
            return attempt
    return {}


def _blue_for_attempt(blue_entries: list[dict[str, Any]], attempt: dict[str, Any]) -> dict[str, Any] | None:
    worker_id = attempt.get("blue_worker_id")
    for blue in blue_entries:
        if blue["worker_id"] == worker_id:
            return blue
    return blue_entries[0] if blue_entries else None


def _receipt_id_for_red(red: dict[str, Any]) -> str:
    return "red-tau-subagent-receipt" if red["worker_id"] == "red-0" else f"{red['worker_id']}-tau-subagent-receipt"


def _receipt_id_for_blue(blue: dict[str, Any] | None) -> str:
    if not blue:
        return "blue-receipt"
    return "blue-tau-subagent-receipt" if blue["worker_id"] == "blue-0" else f"{blue['worker_id']}-tau-subagent-receipt"


def _scillm_receipt_id_for_worker(worker_id: str) -> str:
    return f"{worker_id}-scillm-call-receipt"


def _blocker_receipt_path(worker: dict[str, Any]) -> str:
    blocker = worker.get("blocker")
    if not isinstance(blocker, dict):
        return ""
    return str(blocker.get("receipt_path") or "")


def _battle_clock(*, facts: dict[str, Any]) -> dict[str, Any]:
    started_at = facts.get("generated_at")
    scoreboard = facts.get("scoreboard") if isinstance(facts.get("scoreboard"), dict) else {}
    elapsed = scoreboard.get("elapsed_seconds")
    return {
        "schema": "battle.clock.legacy_receipt_elapsed.v1",
        "mode": "receipt_elapsed",
        "started_at": started_at,
        "ended_at": scoreboard.get("ended_at"),
        "elapsed_seconds": elapsed if isinstance(elapsed, (int, float)) else None,
        "allotted_seconds": scoreboard.get("allotted_seconds"),
        "remaining_seconds": scoreboard.get("remaining_seconds"),
        "current_seconds": elapsed if isinstance(elapsed, (int, float)) else None,
        "source_receipt_id": "scoreboard" if scoreboard else "run-receipt",
        "proof_mode": PROOF_MODE,
    }


def _round_config(*, facts: dict[str, Any], battle_clock: dict[str, Any]) -> dict[str, Any]:
    scoreboard = facts.get("scoreboard") if isinstance(facts.get("scoreboard"), dict) else {}
    scoreboard_config = scoreboard.get("round_config") if isinstance(scoreboard.get("round_config"), dict) else {}
    canonical = _number_or_none(scoreboard_config.get("canonical_allotted_seconds"))
    if canonical is None:
        canonical = CANONICAL_BATTLE004_ALLOTTED_SECONDS if facts.get("battle_id") == "battle-004" else _number_or_none(battle_clock.get("allotted_seconds"))
    if canonical is None:
        canonical = CANONICAL_BATTLE004_ALLOTTED_SECONDS

    resolved = _number_or_none(scoreboard_config.get("resolved_allotted_seconds"))
    if resolved is None:
        resolved = _number_or_none(battle_clock.get("allotted_seconds")) or canonical

    source = _first_str(scoreboard_config.get("time_limit_source"), scoreboard.get("time_limit_source"), "")
    if not source:
        source = "cli_override" if resolved != canonical else "scenario_default"

    config = {
        "schema": "battle.round_config.v1",
        "battle_id": str(facts.get("battle_id") or ""),
        "canonical_allotted_seconds": canonical,
        "resolved_allotted_seconds": resolved,
        "time_limit_source": source,
        "proof_mode": PROOF_MODE,
    }
    override_reason = _first_str(scoreboard_config.get("override_reason"), "")
    if source == "cli_override":
        config["override_reason"] = override_reason or "dev_smoke_test"
    return config


def _canonical_clock(*, facts: dict[str, Any], battle_clock: dict[str, Any], round_config: dict[str, Any]) -> dict[str, Any]:
    elapsed = _number_or_none(battle_clock.get("elapsed_seconds"))
    allotted = _number_or_none(round_config.get("resolved_allotted_seconds"))
    remaining = _number_or_none(battle_clock.get("remaining_seconds"))
    if remaining is None and elapsed is not None and allotted is not None:
        remaining = max(allotted - elapsed, 0.0)
    return {
        "schema": "battle.clock.v1",
        "mode": "receipt_replay",
        "source": "receipt_timestamps",
        "started_at": battle_clock.get("started_at"),
        "server_now": None,
        "ended_at": battle_clock.get("ended_at"),
        "allotted_seconds": allotted,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "current_seconds": elapsed,
        "source_receipt_id": battle_clock.get("source_receipt_id") or "scoreboard",
        "proof_mode": PROOF_MODE,
        "round_config": {
            "canonical_allotted_seconds": round_config.get("canonical_allotted_seconds"),
            "resolved_allotted_seconds": round_config.get("resolved_allotted_seconds"),
            "time_limit_source": round_config.get("time_limit_source"),
        },
    }


def _battle_timeline_control(*, clock: dict[str, Any], timeline: dict[str, Any]) -> dict[str, Any]:
    allotted = _number_or_none(clock.get("allotted_seconds")) or CANONICAL_BATTLE004_ALLOTTED_SECONDS
    current = _number_or_none(clock.get("current_seconds")) or 0.0
    current_pct = round(min(max(current / allotted * 100.0, 0.0), 100.0), 4) if allotted > 0 else 0.0
    return {
        "schema": "battle.timeline_control.v1",
        "clock_mode": "receipt_replay",
        "time_domain": {
            "start_seconds": 0,
            "end_seconds": allotted,
            "allotted_seconds": allotted,
        },
        "playhead": {
            "current_seconds": current,
            "current_pct": current_pct,
            "can_animate": True,
            "source": "clock.current_seconds",
            "proof_mode": PROOF_MODE,
        },
        "viewport_defaults": {
            "follow_mode": "scroll_after_threshold",
            "follow_threshold_pct": 0.72,
            "can_override_locally": True,
        },
        "controls": {
            "can_play": True,
            "can_pause": True,
            "can_scrub": True,
            "can_zoom": True,
            "can_pan": True,
        },
        "render_guards": {
            "derive_x_positions_from_elapsed_seconds": True,
            "do_not_draw_lane_progress_before_lane_start": True,
            "do_not_reveal_terminal_outcome_before_receipt_time": True,
            "child_lane_requires_lineage_receipt": True,
            "terminal_outcome_requires_judge_receipt": True,
            "auto_scroll_only_while_playback_active": True,
        },
        "transport_target": {
            "phase": "generated_replay_snapshot",
            "future_stream": "append_only_jsonl_or_sse",
            "snapshot_schema": "battle.normalized_ux_fixture.v1",
        },
        "_legacy_timeline": timeline,
    }


def _attach_elapsed_timing(*, lanes: list[dict[str, Any]], facts: dict[str, Any]) -> None:
    """Attach receipt-backed elapsed timing without changing receipt-order x positions."""
    tau_timing = facts.get("tau_timing") if isinstance(facts.get("tau_timing"), dict) else {}
    initial_start = _number_or_none(tau_timing.get("initial_tau_started_elapsed_seconds"))
    initial_end = _number_or_none(tau_timing.get("initial_tau_ended_elapsed_seconds"))
    spawns_by_parent = {str(spawn.get("parent_lane_id")): spawn for spawn in facts.get("lineage_spawns", []) if isinstance(spawn, dict)}
    spawns_by_child = {str(spawn.get("child_lane_id")): spawn for spawn in facts.get("lineage_spawns", []) if isinstance(spawn, dict)}
    attempts_by_lane = _attempt_timing_by_lane(facts.get("attempts", []))

    for lane in lanes:
        lane_id = str(lane.get("id") or "")
        attempt = attempts_by_lane.get(lane_id, {})
        spawn_for_parent = spawns_by_parent.get(lane_id, {})
        spawn_for_child = spawns_by_child.get(lane_id, {})
        spawn_visible_elapsed = _number_or_none(spawn_for_child.get("spawn_elapsed_seconds")) if spawn_for_child else None
        child_active_elapsed = _number_or_none(spawn_for_child.get("child_start_elapsed_seconds")) if spawn_for_child else None
        lane_start_elapsed = spawn_visible_elapsed if spawn_for_child else initial_start
        lane_end_elapsed = _number_or_none(attempt.get("ended_elapsed_seconds"))
        if lane_end_elapsed is None and spawn_for_child:
            spawn_duration = _number_or_none(spawn_for_child.get("spawn_duration_elapsed_seconds"))
            if child_active_elapsed is not None and spawn_duration is not None:
                lane_end_elapsed = round(child_active_elapsed + spawn_duration, 6)
        if lane_start_elapsed is not None:
            lane["start_elapsed_seconds"] = lane_start_elapsed
        if spawn_for_child:
            if spawn_visible_elapsed is not None:
                lane["visible_from_elapsed_seconds"] = spawn_visible_elapsed
            if child_active_elapsed is not None:
                lane["first_active_segment_elapsed_seconds"] = child_active_elapsed
        if lane_end_elapsed is not None:
            lane["end_elapsed_seconds"] = lane_end_elapsed
        if lane_start_elapsed is not None and lane_end_elapsed is not None and lane_end_elapsed >= lane_start_elapsed:
            lane["duration_elapsed_seconds"] = round(lane_end_elapsed - lane_start_elapsed, 6)

        for event in lane.get("events", []):
            if not isinstance(event, dict):
                continue
            elapsed, timing_source = _event_elapsed_timing(
                event=event,
                lane_id=lane_id,
                initial_end=initial_end,
                lane_start_elapsed=lane_start_elapsed,
                attempt=attempt,
                spawn_for_parent=spawn_for_parent,
                spawn_for_child=spawn_for_child,
            )
            if elapsed is not None:
                event["elapsed_seconds"] = elapsed
                event["timing_source"] = timing_source


def _event_elapsed_timing(
    *,
    event: dict[str, Any],
    lane_id: str,
    initial_end: float | None,
    lane_start_elapsed: float | None,
    attempt: dict[str, Any],
    spawn_for_parent: dict[str, Any],
    spawn_for_child: dict[str, Any],
) -> tuple[float | None, str]:
    kind = str(event.get("kind") or "")
    if kind == "research":
        return lane_start_elapsed, "lineage_spawn_receipt" if spawn_for_child else "tau_manifest"
    if kind in {"payload", "useful"}:
        if spawn_for_child:
            return _number_or_none(spawn_for_child.get("child_start_elapsed_seconds")), "lineage_spawn_receipt"
        return initial_end, "tau_manifest"
    if kind == "handoff":
        if spawn_for_parent and event.get("id") == f"{lane_id}:spawn:{spawn_for_parent.get('child_lane_id')}":
            return _number_or_none(spawn_for_parent.get("spawn_elapsed_seconds")), "lineage_spawn_receipt"
        if spawn_for_child:
            return _number_or_none(spawn_for_child.get("spawn_elapsed_seconds")), "lineage_spawn_receipt"
    if kind == "blue_blast":
        elapsed = _number_or_none(attempt.get("started_elapsed_seconds"))
        if elapsed is not None:
            return elapsed, "judge_attempt_receipt"
        if spawn_for_child:
            child_start_elapsed = _number_or_none(spawn_for_child.get("child_start_elapsed_seconds"))
            spawn_duration = _number_or_none(spawn_for_child.get("spawn_duration_elapsed_seconds"))
            if child_start_elapsed is not None and spawn_duration is not None:
                return round(child_start_elapsed + spawn_duration, 6), "lineage_spawn_receipt"
    if kind == "blocked":
        elapsed = _number_or_none(attempt.get("ended_elapsed_seconds"))
        if elapsed is not None:
            return elapsed, "judge_attempt_receipt"
        if spawn_for_child:
            child_start_elapsed = _number_or_none(spawn_for_child.get("child_start_elapsed_seconds"))
            spawn_duration = _number_or_none(spawn_for_child.get("spawn_duration_elapsed_seconds"))
            if child_start_elapsed is not None and spawn_duration is not None:
                return round(child_start_elapsed + spawn_duration, 6), "lineage_spawn_receipt"
    return None, ""


def _attempt_timing_by_lane(attempts: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(attempts, list):
        return {}
    selected: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        lane_id = str(attempt.get("red_lane_id") or "")
        if not lane_id:
            continue
        current = selected.get(lane_id)
        current_end = _number_or_none(current.get("ended_elapsed_seconds")) if isinstance(current, dict) else None
        next_end = _number_or_none(attempt.get("ended_elapsed_seconds"))
        if current is None or (next_end is not None and (current_end is None or next_end < current_end)):
            selected[lane_id] = attempt
    return selected


def _timeline(*, facts: dict[str, Any], lanes: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    keyframes = _playhead_keyframes(lanes)
    current_x = _timeline_playhead_x(lanes, keyframes)
    viewport_min = max(0, current_x - 45)
    viewport_max = min(100, max(current_x + 15, viewport_min + 40))
    if viewport_max == 100:
        viewport_min = max(0, viewport_max - 55)
    scoreboard = facts.get("scoreboard") if isinstance(facts.get("scoreboard"), dict) else {}
    elapsed_seconds = scoreboard.get("elapsed_seconds")
    return {
        "mode": "receipt_order",
        "min_x": 0,
        "max_x": 100,
        "event_count": len(events),
        "lane_count": len(lanes),
        "supports_zoom": True,
        "supports_pan": True,
        "scroll_axis": "horizontal",
        "playhead": {
            "mode": "receipt_elapsed",
            "current_x": current_x,
            "elapsed_seconds": elapsed_seconds if isinstance(elapsed_seconds, (int, float)) else None,
            "source_receipt_id": "scoreboard" if scoreboard else "run-receipt",
            "can_animate": True,
            "animation_semantics": "receipt_replay_only",
            "keyframes": keyframes,
            "proof_mode": PROOF_MODE,
        },
        "viewport": {
            "initial_min_x": viewport_min,
            "initial_max_x": viewport_max,
            "min_zoom": 0.75,
            "max_zoom": 4.0,
            "proof_mode": PROOF_MODE,
        },
    }


def _playhead_keyframes(lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyframes: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for lane in lanes:
        lane_id = str(lane.get("id") or "")
        for event in lane.get("events", []):
            if not isinstance(event, dict) or not isinstance(event.get("x"), int):
                continue
            x = int(event["x"])
            event_id = str(event.get("id") or "")
            key = (x, lane_id, event_id)
            if key in seen:
                continue
            seen.add(key)
            keyframes.append(
                {
                    "x": x,
                    **({"elapsed_seconds": event.get("elapsed_seconds")} if isinstance(event.get("elapsed_seconds"), (int, float)) else {}),
                    **({"timing_source": str(event.get("timing_source"))} if event.get("timing_source") else {}),
                    "lane_id": lane_id,
                    "event_id": event_id,
                    "kind": str(event.get("kind") or ""),
                    "label": str(event.get("label") or ""),
                    "proof_mode": PROOF_MODE,
                }
            )
    return sorted(keyframes, key=lambda frame: (int(frame["x"]), str(frame["lane_id"]), str(frame["event_id"])))


def _ux_contract(*, facts: dict[str, Any], lanes: list[dict[str, Any]], events: list[dict[str, Any]], proof_blockers: list[dict[str, Any]]) -> dict[str, Any]:
    valid_lineage = _valid_lineage_spawns(facts=facts)
    blocked_lanes = sorted(
        {
            str(attempt.get("red_lane_id"))
            for attempt in facts["attempts"]
            if attempt.get("verdict") == "BLUE_SUCCESS" and attempt.get("red_lane_id")
        }
    )
    return {
        "schema": "battle.ux_contract.v1",
        "mode": "receipt_backed",
        "proof_mode": PROOF_MODE,
        "authoritative_fields": {
            "scenario": "Battle identity, public entrypoint, CWE, runtime, and target language.",
            "battle_clock": "Receipt elapsed/allotted/remaining time. Do not synthesize live timers.",
            "timeline": "Timeline bounds, pan/zoom capability, viewport defaults, and receipt replay playhead state/keyframes.",
            "lineage_request": "Whether child spawn was requested and whether a lineage receipt was produced. This does not authorize child rendering by itself.",
            "lineage": "Parent/child spawn relationships. Render children only when lineage.mode == receipt_backed.",
            "spectator_shell": "Header, fact chips, score labels, round-time label, and receipt event ticker text.",
            "lanes": "Red lane identities, parentId/children, runner state, events, activitySegments, stdout/stderr, replay metadata.",
            "events": "Receipt-backed public event stream, including tau.spawned_child when present.",
            "bluePatchActions": "Materialized Blue patch artifacts only.",
            "scoreboard": "Judge/scorekeeper counts and pair verdicts.",
            "proof_blockers": "Receipt-backed causes for blocked worker materialization or missing proof density.",
            "receipts": "Inspectable proof references.",
            "claims": "Human-readable proof and non-proof boundaries.",
        },
        "required_render_guards": [
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
        ],
        "receipt_backed_values": {
            "lane_count": len(lanes),
            "event_count": len(events),
            "child_spawn_count": len(valid_lineage),
            "child_spawn_requested": bool(facts["lineage_request"].get("requested")),
            "child_spawn_request_status": str(facts["lineage_request"].get("status") or "NOT_REQUESTED"),
            "blue_blocked_lane_ids": blocked_lanes,
            "judge_pair_count": len(facts["attempts"]),
            "lineage_group_count": len({str(lane.get("lineageGroupId")) for lane in lanes if lane.get("lineageGroupId")}),
            "playhead_current_x": _timeline_playhead_x(lanes),
            "proof_blocker_count": len(proof_blockers),
        },
        "forbidden_inferences": [
            "Blue kill attribution",
            "Fastest crash",
            "Survivor promotion",
            "Unbounded swarm execution",
            "Live stream execution",
            "Child lineage without lineage receipt",
        ],
    }


def _renderer_binding_contract() -> dict[str, Any]:
    return {
        "schema": "battle.renderer_binding_contract.v1",
        "proof_mode": PROOF_MODE,
        "purpose": "Exact JSON paths the UX renderer should bind to. This is backend-owned data shape, not visual design direction.",
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
            "render_rule": "Animate only as receipt replay when timeline.playhead.can_animate is true; never label as live stream unless proof_mode/live_source changes.",
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
            "render_rule": "Use this section for elapsed-time/DAW-style placement; use timeline.playhead.keyframes[].x only for legacy receipt-order renderers.",
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
        "proof_blockers": {
            "blocked_worker_reasons": "proof_blockers[]",
            "blocker_kind": "proof_blockers[].blocker.kind",
            "blocker_message": "proof_blockers[].blocker.message",
            "blocker_receipt": "proof_blockers[].receipt_id",
        },
    }


def _with_timeline_order(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        copy = dict(event)
        copy.setdefault("order_index", index)
        copy.setdefault("elapsed_seconds", None)
        ordered.append(copy)
    return ordered


def _timeline_current_x(lanes: list[dict[str, Any]]) -> int:
    positions = [
        int(lane.get("runnerX", lane.get("xEnd", 0)))
        for lane in lanes
        if isinstance(lane.get("runnerX", lane.get("xEnd", 0)), int)
    ]
    if not positions:
        return 0
    return max(0, min(100, max(positions)))


def _timeline_playhead_x(lanes: list[dict[str, Any]], keyframes: list[dict[str, Any]] | None = None) -> int:
    frames = keyframes if keyframes is not None else _playhead_keyframes(lanes)
    if frames:
        return max(0, min(100, int(frames[-1]["x"])))
    return _timeline_current_x(lanes)


def _spectator_shell(
    *,
    facts: dict[str, Any],
    battle_clock: dict[str, Any],
    scoreboard: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    target_label = f"POST {facts['public_entrypoint']}"
    latest_event = events[-1] if events else {}
    latest_text = _first_str(
        latest_event.get("ui", {}).get("notification") if isinstance(latest_event.get("ui"), dict) else None,
        latest_event.get("summary") if isinstance(latest_event, dict) else None,
        "No receipt events emitted.",
    )
    return {
        "schema": "battle.spectator_shell.v1",
        "proof_mode": PROOF_MODE,
        "battle_title": f"{facts['battle_id'].upper()} · {target_label}",
        "subtitle": f"{facts['cwe']} · {facts['vulnerability_family']} · receipt-backed Battle proof",
        "mode_badge": "RECEIPT-BACKED",
        "truth_label": "receipt-backed fixture",
        "facts": [
            {"label": "Arena", "value": _first_str(facts.get("scenario_id"), "ZIP_SLIP_ARB")},
            {"label": "Objective", "value": "Prevent archive path traversal"},
            {"label": "Target", "value": target_label},
            {"label": "Difficulty", "value": str(facts.get("difficulty") or "unknown").upper()},
            {"label": "Round time", "value": _round_time_label(battle_clock)},
        ],
        "score": {
            "red": {"label": "Red Team", "sub": "Exploit Agents", "value": _score_label(scoreboard.get("red_score"))},
            "blue": {"label": "Blue Team", "sub": "Patch Agents", "value": _score_label(scoreboard.get("blue_score"))},
            "verdict": _first_str(scoreboard.get("verdict"), facts.get("verdict"), "INSUFFICIENT_EVIDENCE"),
        },
        "event_ticker": {
            "label": "Receipt events",
            "count": len(events),
            "latest_text": latest_text,
            "live": False,
            "source": "events",
        },
        "render_guards": [
            "Render shell text from spectator_shell; do not hard-code mockup copy.",
            "Do not label receipt replay as live execution.",
            "Round time is a receipt value from battle_clock.",
        ],
    }


def _round_time_label(clock: dict[str, Any]) -> str:
    elapsed = _seconds_label(clock.get("elapsed_seconds"))
    allotted = _seconds_label(clock.get("allotted_seconds"))
    return f"{elapsed} / {allotted}"


def _seconds_label(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    seconds = max(0, int(value))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _score_label(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "0"
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):.1f}"


def _lineage_groups(*, lanes: list[dict[str, Any]], spawns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lane_ids = {str(lane.get("id")) for lane in lanes if isinstance(lane, dict) and lane.get("id")}
    groups: list[dict[str, Any]] = []
    parent_ids = sorted({str(spawn.get("parent_lane_id")) for spawn in spawns if spawn.get("parent_lane_id")})
    for parent_id in parent_ids:
        child_ids = sorted(
            {
                str(spawn.get("child_lane_id"))
                for spawn in spawns
                if spawn.get("parent_lane_id") == parent_id and spawn.get("child_lane_id") in lane_ids
            }
        )
        groups.append(
            {
                "group_id": f"lineage:{parent_id}",
                "parent_lane_id": parent_id,
                "child_lane_ids": child_ids,
                "lane_ids": [parent_id, *child_ids],
                "collapsible": True,
                "expanded_by_default": True,
                "spawn_receipt_ids": [
                    str(spawn["receipt_id"])
                    for spawn in spawns
                    if spawn.get("parent_lane_id") == parent_id and spawn.get("receipt_id")
                ],
                "lane_count": 1 + len(child_ids),
                "proof_mode": PROOF_MODE,
            }
        )
    return groups


def _replay_for_lane(*, facts: dict[str, Any], lane_id: str, attempt: dict[str, Any]) -> dict[str, Any] | None:
    if not attempt or attempt.get("verdict") != "BLUE_SUCCESS":
        return None
    pair_id = _first_str(attempt.get("pair_id"), f"{attempt.get('red_worker_id', 'red')}__{attempt.get('blue_worker_id', 'blue')}")
    can_execute_now = False
    return {
        "label": "REPLAY IN DOCKER",
        "kind": "receipt_only",
        "receipt_id": "judge-receipt",
        "attempt_id": pair_id,
        "pair_id": pair_id,
        "red_worker_id": attempt.get("red_worker_id"),
        "red_lane_id": lane_id,
        "blue_worker_id": attempt.get("blue_worker_id"),
        "blue_action_id": attempt.get("blue_action_id"),
        "can_execute_now": can_execute_now,
        "endpoint": None,
        "command_receipt_id": None,
        "cta": _replay_cta(can_execute_now=can_execute_now),
        "proof_mode": PROOF_MODE,
    }


def _replay_cta(*, can_execute_now: bool) -> dict[str, Any]:
    if can_execute_now:
        return {
            "visible": True,
            "label": "REPLAY IN DOCKER",
            "state": "executable",
            "icon": "container",
            "disabled_reason": None,
            "tooltip": "Run the selected receipt-backed Docker replay.",
            "proof_mode": PROOF_MODE,
        }
    return {
        "visible": True,
        "label": "REPLAY IN DOCKER",
        "state": "receipt_only",
        "icon": "container",
        "disabled_reason": "No executable replay endpoint or command receipt is attached to this selected lane.",
        "tooltip": "Judge replay receipt is available; live container execution is not attached.",
        "proof_mode": PROOF_MODE,
    }


def _proof_blockers(*, facts: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for team, entries in (("red", facts.get("red_entries")), ("blue", facts.get("blue_entries"))):
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            blocker = entry.get("blocker")
            if not isinstance(blocker, dict):
                continue
            worker_id = str(entry.get("worker_id") or "")
            receipt_path = str(blocker.get("receipt_path") or "")
            key = (team, worker_id, receipt_path)
            if key in seen:
                continue
            seen.add(key)
            receipt_id = _scillm_receipt_id_for_worker(worker_id) if receipt_path else _receipt_id_for_red(entry) if team == "red" else _receipt_id_for_blue(entry)
            blockers.append(
                {
                    "schema": "battle.proof_blocker.v1",
                    "team": team,
                    "worker_id": worker_id,
                    "lane_id": str(entry.get("lane_id") or "") if team == "red" else None,
                    "action_id": str(entry.get("action_id") or "") if team == "blue" else None,
                    "status": str(entry.get("status") or "BLOCKED"),
                    "reason": _entry_blocked_reason(entry),
                    "blocker": blocker,
                    "receipt_id": receipt_id,
                    "receipt_path": receipt_path,
                    "proof_mode": PROOF_MODE,
                }
            )
    return blockers


def _arena_receipts(*, include_language: bool, include_monitor: bool) -> list[dict[str, Any]]:
    refs = [
        _receipt("run-receipt", "battle_run", "run-receipt.json", "BATTLE-004 Arena Red/Blue/Judge run receipt."),
        _receipt("scoreboard", "scoreboard", "scoreboard.json", "Scoreboard records verdict and scores."),
        _receipt("arena-receipt", "arena", "arena/arena-receipt.json", "Arena created the scenario."),
        _receipt("red-receipt", "red_team", "red-receipt.json", "Red receipt records exploit evidence."),
        _receipt("blue-receipt", "blue_team", "blue-receipt.json", "Blue receipt records patch evidence."),
        _receipt("judge-receipt", "judge", "judge/judge-receipt.json", "Judge receipt records replay verdict."),
    ]
    if include_language:
        refs.insert(3, _receipt("language-contract", "language_contract", "language-contract.json", "Language and runtime contract."))
    if include_monitor:
        refs.append(_receipt("monitor-index", "monitor_index", "monitor-index.json", "Monitor index lists proof artifacts."))
    return refs


def _tau_public_receipts(*, red_entries: list[dict[str, Any]], blue_entries: list[dict[str, Any]], visibility: dict[str, Any]) -> list[dict[str, Any]]:
    refs = [
        _receipt("run-receipt", "battle_run", "run-receipt.json", "Tau public-only run receipt."),
        _receipt("tau-live-manifest", "tau_live_manifest", "tau-live/manifest.json", "Tau Red/Blue handoff manifest."),
        _receipt("judge-receipt", "judge", "judge/judge-receipt.json", "Judge receipt for Tau artifacts."),
    ]
    if visibility:
        refs.insert(2, _receipt("visibility-validation", "visibility_validation", "visibility-validation.json", "Public-only visibility validation."))
    for red in red_entries:
        refs.append(_receipt(_receipt_id_for_red(red), "tau_subagent", red.get("subagent_receipt") or "tau-live/red/tau-subagent-receipt.json", f"Tau Red subagent receipt {red['worker_id']}."))
        scillm_path = _blocker_receipt_path(red)
        if scillm_path:
            refs.append(_receipt(_scillm_receipt_id_for_worker(red["worker_id"]), "scillm_call", scillm_path, f"Scillm call receipt for Red worker {red['worker_id']}."))
    for blue in blue_entries:
        refs.append(_receipt(_receipt_id_for_blue(blue), "tau_subagent", blue.get("subagent_receipt") or "tau-live/blue/tau-subagent-receipt.json", f"Tau Blue subagent receipt {blue['worker_id']}."))
        scillm_path = _blocker_receipt_path(blue)
        if scillm_path:
            refs.append(_receipt(_scillm_receipt_id_for_worker(blue["worker_id"]), "scillm_call", scillm_path, f"Scillm call receipt for Blue worker {blue['worker_id']}."))
    return refs


def _lineage_receipts(spawns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spawn in spawns:
        receipt_id = str(spawn.get("receipt_id") or "")
        if not receipt_id or receipt_id in seen:
            continue
        seen.add(receipt_id)
        refs.append(
            _receipt(
                receipt_id,
                "lineage_spawn",
                str(spawn.get("receipt_path") or "lineage-receipts.json"),
                f"Parent lane {spawn.get('parent_lane_id')} spawned child lane {spawn.get('child_lane_id')}.",
            )
        )
    return refs


def _receipt(receipt_id: str, receipt_type: str, path: str, summary: str) -> dict[str, Any]:
    return {"receipt_id": receipt_id, "receipt_type": receipt_type, "receipt_path": path, "artifact_ref": path, "summary": summary, "proof_mode": PROOF_MODE}


def _lane_event(event_id: str, kind: str, x: int, label: str, time_label: str, receipt_id: str, *, blue_source_id: str | None = None, animation: str | None = None) -> dict[str, Any]:
    event = {
        "id": event_id,
        "kind": kind,
        "x": x,
        "label": label,
        "timeLabel": time_label,
        "proven": True,
        "proofMode": PROOF_MODE,
        "receiptId": receipt_id,
        "order_index": int(x),
        "elapsed_seconds": None,
        "label_band": _label_band_for_kind(kind),
        "marker_priority": _marker_priority_for_kind(kind),
        "collision_group": _collision_group_for_x(x),
    }
    if blue_source_id:
        event["blueSourceId"] = blue_source_id
    if animation:
        event["animation"] = animation
    return event


def _label_band_for_kind(kind: str) -> str:
    return {
        "research": "upper",
        "payload": "lower",
        "useful": "upper",
        "blue_blast": "upper",
        "blocked": "lower",
        "handoff": "lower",
    }.get(kind, "auto")


def _marker_priority_for_kind(kind: str) -> int:
    return {
        "useful": 90,
        "handoff": 85,
        "blue_blast": 80,
        "blocked": 70,
        "payload": 50,
        "research": 40,
    }.get(kind, 10)


def _collision_group_for_x(x: int) -> str:
    bucket = max(0, min(100, int(x))) // 10
    return f"x{bucket:02d}"


def _event(event_id: str, ts: str, battle_id: str, team: str, actor_id: str, actor_kind: str, event_type: str, summary: str, **extra: Any) -> dict[str, Any]:
    event = {"id": event_id, "ts": ts, "battle_id": battle_id, "team": team, "actor_id": actor_id, "actor_kind": actor_kind, "event_type": event_type, "summary": summary, "proof_mode": PROOF_MODE}
    event.update(extra)
    event.setdefault("ui", {"importance": "visible", "spectator_caption": summary, "notification": summary})
    event.setdefault("receipts", [])
    return event


def _turn(loop_index: int, phase: str, current_action: str, status: Any) -> dict[str, Any]:
    return {"loop_index": loop_index, "phase": phase, "current_action": current_action, "status": _first_str(status, "UNKNOWN")}


def _ui(runner_state: str, runner_animation: str, importance: str, caption: str, notification: str, *, sound_cue: str = "none") -> dict[str, Any]:
    return {"runner_state": runner_state, "runner_animation": runner_animation, "sound_cue": sound_cue, "importance": importance, "spectator_caption": caption, "notification": notification}


def _skill(name: str, summary: str, receipt_id: str, timestamp: str) -> dict[str, Any]:
    return {"name": name, "kind": "tool", "status": "ok", "timestamp": timestamp, "summary": summary, "receipt_id": receipt_id, "proof_mode": PROOF_MODE}


def _evidence(receipt_id: str, receipt_path: str) -> dict[str, Any]:
    return {"receipt_id": receipt_id, "receipt_path": receipt_path, "artifact_ref": receipt_path, "proof_mode": PROOF_MODE}


def _worker_evidence(receipt_id: str, receipt_path: str, worker: dict[str, Any]) -> dict[str, Any]:
    evidence = _evidence(receipt_id, receipt_path)
    blocker = worker.get("blocker")
    if isinstance(blocker, dict):
        evidence["blocker"] = blocker
    return evidence


def _scoreboard_summary(facts: dict[str, Any]) -> str:
    scoreboard = facts["scoreboard"] if isinstance(facts["scoreboard"], dict) else {}
    return f"Scoreboard verdict {facts['verdict']}: red_score {scoreboard.get('red_score', 'unknown')}, blue_score {scoreboard.get('blue_score', 'unknown')}, TDSR {scoreboard.get('tdsr', 'unknown')}."


def _judge_output(facts: dict[str, Any]) -> str:
    parts = [_excerpt(facts.get("judge_stdout", ""), "")]
    if facts.get("functionality_stdout"):
        parts.append(f"functionality stdout: {_excerpt(facts['functionality_stdout'], '')}")
    return "; ".join(part for part in parts if part) or "judge: exploit blocked after patch; functionality preserved"


def _joined_blocked_reasons(entries: list[dict[str, Any]], team: str) -> str:
    if not entries:
        return f"no {team} workers emitted"
    return "; ".join(f"{entry['worker_id']}={entry['status']}:{_entry_blocked_reason(entry)}" for entry in entries)


def _entry_blocked_reason(entry: dict[str, Any]) -> str:
    blocker = entry.get("blocker")
    if isinstance(blocker, dict):
        kind = _first_str(blocker.get("kind"), blocker.get("error_type"), "blocked")
        message = _first_str(blocker.get("message"), blocker.get("reason"), "")
        if message:
            return f"{kind}: {message}"
        return kind
    return _first_str(entry.get("reason"), "ok")


def _worker_blocker_from_manifest_item(*, proof_root: Path, item: dict[str, Any]) -> dict[str, Any] | None:
    scillm_call = item.get("scillm_call")
    if not isinstance(scillm_call, str) or not scillm_call:
        return None
    path = Path(scillm_call)
    if not path.is_absolute():
        path = proof_root / path
    receipt = _read_optional_json(path)
    if not receipt:
        return None

    http_status = receipt.get("http_status")
    status = _first_str(receipt.get("status"), receipt.get("parse_status"), "")
    raw_excerpt = _first_raw_body_excerpt(receipt)
    error_payload = _parse_json_object(raw_excerpt)
    error = error_payload.get("error") if isinstance(error_payload.get("error"), dict) else {}
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    if not error and _first_str(status).upper() == "PASS" and (not isinstance(http_status, int) or 200 <= http_status < 300):
        return None
    message = _first_str(error.get("message"), receipt.get("error"), receipt.get("parse_error"), status)
    return {
        "schema": "battle.worker_blocker.v1",
        "kind": _first_str(error.get("type"), details.get("error_type"), status, "worker_blocked"),
        "message": message,
        "http_status": http_status,
        "provider": details.get("provider"),
        "provider_auth_status": details.get("provider_auth_status"),
        "model_requested": details.get("model_requested") or receipt.get("model"),
        "project_agent_message": details.get("project_agent_message"),
        "receipt_path": str(path),
        "proof_mode": PROOF_MODE,
    }


def _first_raw_body_excerpt(receipt: dict[str, Any]) -> str:
    attempts = receipt.get("attempts")
    if isinstance(attempts, list):
        for attempt in attempts:
            if isinstance(attempt, dict) and isinstance(attempt.get("raw_body_excerpt"), str):
                return str(attempt["raw_body_excerpt"])
    return ""


def _parse_json_object(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_arena_battle_proof(proof_root: Path) -> bool:
    return all(
        path.exists()
        for path in [
            proof_root / "run-receipt.json",
            proof_root / "scoreboard.json",
            proof_root / "red-receipt.json",
            proof_root / "blue-receipt.json",
            proof_root / "judge" / "judge-receipt.json",
            proof_root / "arena" / "scenario.json",
            proof_root / "arena" / "arena-receipt.json",
        ]
    )


def _is_tau_public_only_proof(proof_root: Path) -> bool:
    return (proof_root / "run-receipt.json").exists() and (proof_root / "tau-live" / "manifest.json").exists()


def _read_required_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise typer.BadParameter(f"required JSON receipt not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise typer.BadParameter(f"required JSON receipt is not an object: {path}")
    return data


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_required_json(path)


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_receipt_stdout(receipt: dict[str, Any]) -> str:
    return _read_first_command_text(receipt, "stdout_path")


def _read_receipt_stderr(receipt: dict[str, Any]) -> str:
    return _read_first_command_text(receipt, "stderr_path")


def _read_first_command_text(receipt: dict[str, Any], key: str) -> str:
    commands = receipt.get("commands_run")
    if not isinstance(commands, list):
        return ""
    for command in commands:
        if not isinstance(command, dict):
            continue
        value = command.get(key)
        if isinstance(value, str) and value:
            return _read_optional_text(Path(value))
    return ""


def _public_entrypoint(value: str) -> str:
    text = value.strip()
    if not text or text.startswith("[local-artifact-ref"):
        return "/api/import-zip"
    if " " in text:
        method, path = text.split(None, 1)
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} and path.startswith("/"):
            return path
    return text


def _first_str(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text:
            return text
    return ""


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    if isinstance(value, str) and value.strip():
        try:
            return round(float(value), 6)
        except ValueError:
            return None
    return None


def _elapsed_fields(source: dict[str, Any], *keys: str) -> dict[str, float]:
    fields: dict[str, float] = {}
    for key in keys:
        value = _number_or_none(source.get(key))
        if value is not None:
            fields[key] = value
    return fields


def _live_event_envelopes(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    observed_at = _first_str(fixture.get("generated_at"), "1970-01-01T00:00:00Z")
    run_id = _fixture_run_id(fixture)
    envelopes: list[dict[str, Any]] = []

    for event in fixture.get("events", []):
        if not isinstance(event, dict):
            continue
        seq = len(envelopes) + 1
        event_id = _first_str(event.get("id"), f"event-{seq:04d}")
        at_seconds = _event_seconds(event, seq=seq)
        envelopes.append(
            {
                "schema": "battle.live_event.v1",
                "run_id": run_id,
                "battle_id": fixture.get("battle_id"),
                "seq": seq,
                "event_id": event_id,
                "at_seconds": at_seconds,
                "observed_at": _first_str(event.get("ts"), observed_at),
                "event_type": _first_str(event.get("event_type"), "battle.event"),
                "payload": _live_event_payload(event),
            }
        )

    for segment in fixture.get("segments", []):
        if not isinstance(segment, dict):
            continue
        seq = len(envelopes) + 1
        segment_id = _first_str(segment.get("id"), f"segment-{seq:04d}")
        envelopes.append(
            {
                "schema": "battle.live_event.v1",
                "run_id": run_id,
                "battle_id": fixture.get("battle_id"),
                "seq": seq,
                "event_id": segment_id,
                "at_seconds": _number_or_none(segment.get("start_seconds")) or float(seq),
                "observed_at": observed_at,
                "event_type": "battle.segment_declared",
                "payload": {
                    "schema": "battle.segment_update.v1",
                    "segment_id": segment_id,
                    "lane_id": segment.get("lane_id"),
                    "kind": segment.get("kind"),
                    "label": segment.get("label"),
                    "start_seconds": segment.get("start_seconds"),
                    "end_seconds": segment.get("end_seconds"),
                    "source_event_id": segment.get("source_event_id"),
                    "interpolation": segment.get("interpolation"),
                    "proof_mode": segment.get("proof_mode", PROOF_MODE),
                    "renderer_boundary": "Pixi may interpolate runner motion only inside this declared segment.",
                },
            }
        )

    return envelopes


def _snapshot_envelope(*, fixture: dict[str, Any], last_seq: int) -> dict[str, Any]:
    return {
        "schema": "battle.snapshot.v1",
        "battle_id": fixture.get("battle_id"),
        "run_id": _fixture_run_id(fixture),
        "last_seq": last_seq,
        "generated_at": fixture.get("generated_at"),
        "mode": fixture.get("mode", "receipt_replay"),
        "clock": fixture.get("clock"),
        "battle_clock": fixture.get("battle_clock"),
        "round_config": fixture.get("round_config"),
        "battle_timeline_control": fixture.get("battle_timeline_control"),
        "events": _renderer_safe_copy(fixture.get("events", [])),
        "segments": _renderer_safe_copy(fixture.get("segments", [])),
        "lanes": _renderer_safe_copy(fixture.get("lanes", [])),
        "lineage": _renderer_safe_copy(fixture.get("lineage")),
        "scoreboard": _renderer_safe_copy(fixture.get("scoreboard")),
        "claims": _renderer_safe_copy(fixture.get("claims")),
        "validation": _renderer_safe_copy(fixture.get("validation")),
        "normalized_fixture_schema": fixture.get("schema"),
        "normalized_fixture_path": "battle.normalized_ux_fixture.json",
        "renderer_boundary": {
            "backend_authority": "clock/events/segments/lanes/lineage/receipts",
            "pixi_authority": "pixels/camera/scroll/easing/sprite frame playback/effects",
        },
    }


def _live_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    receipt_id = _receipt_id_from_event(event)
    payload = {
        "source_event": _renderer_safe_copy(event),
        "lane_id": event.get("actor_id"),
        "actor_id": event.get("actor_id"),
        "actor_kind": event.get("actor_kind"),
        "team": event.get("team"),
        "status_after": _status_after_from_event(event),
        "receipt_id": receipt_id,
        "proof_mode": event.get("proof_mode", PROOF_MODE),
    }
    for key in ("parent_id", "parent_actor_id", "spawned_children", "target_actor_ids", "pair_id", "red_lane_id", "blue_action_id"):
        if key in event:
            payload[key] = event[key]
    return payload


def _event_seconds(event: dict[str, Any], *, seq: int) -> float:
    for key in ("at_seconds", "elapsed_seconds"):
        value = _number_or_none(event.get(key))
        if value is not None:
            return value
    order = _number_or_none(event.get("order_index"))
    if order is not None:
        return order
    return float(seq)


def _fixture_run_id(fixture: dict[str, Any]) -> str:
    scoreboard = fixture.get("scoreboard") if isinstance(fixture.get("scoreboard"), dict) else {}
    spectator_shell = fixture.get("spectator_shell") if isinstance(fixture.get("spectator_shell"), dict) else {}
    for event in fixture.get("events", []):
        if isinstance(event, dict):
            run_id = _first_str(event.get("tau_run_id"))
            if run_id:
                return run_id
    return _first_str(scoreboard.get("run_id"), spectator_shell.get("run_id"), fixture.get("battle_id"), "battle-run")


def _renderer_safe_copy(value: Any) -> Any:
    """Remove renderer-owned legacy hints from transport artifacts."""
    prohibited = {
        "animation",
        "runner_animation",
        "blue_animation",
        "impact_animation",
        "sound_cue",
        "sprite_frame",
        "sprite_frame_index",
        "pixi_object_id",
        "easing",
        "particle_parameters",
        "canvas_x",
        "canvas_y",
    }
    if isinstance(value, dict):
        return {
            key: _renderer_safe_copy(child)
            for key, child in value.items()
            if key not in prohibited
        }
    if isinstance(value, list):
        return [_renderer_safe_copy(child) for child in value]
    return value


def _receipt_id_from_event(event: dict[str, Any]) -> str | None:
    evidence = event.get("evidence")
    if isinstance(evidence, dict):
        receipt_id = _first_str(evidence.get("receipt_id"))
        if receipt_id:
            return receipt_id
    receipts = event.get("receipts")
    if isinstance(receipts, list):
        for receipt in receipts:
            if isinstance(receipt, dict):
                receipt_id = _first_str(receipt.get("receipt_id"))
                if receipt_id:
                    return receipt_id
    return None


def _status_after_from_event(event: dict[str, Any]) -> str:
    turn = event.get("turn")
    if isinstance(turn, dict):
        status = _first_str(turn.get("status"))
        if status:
            return status
    event_type = _first_str(event.get("event_type"))
    return {
        "tau.spawned_child": "spawned_child",
        "blue.blocked_red": "blocked",
        "blue.patch_deployed": "patch_deployed",
        "red.learned": "materialized",
        "tau.artifact_blocked": "blocked",
        "judge.verdict": "terminal",
        "judge.insufficient_evidence": "insufficient_evidence",
    }.get(event_type, "observed")


def _excerpt(text: str, fallback: str, *, limit: int = 240) -> str:
    cleaned = text.strip()
    if not cleaned:
        return fallback
    return cleaned[:limit]


def _assert_battle_id(actual: str, expected: str) -> None:
    if actual != expected:
        raise typer.BadParameter(f"battle id mismatch: expected {expected}, proof contains {actual}")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_typescript(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=False)
    path.write_text(
        "// AUTO-GENERATED by battle_skill.battle_event_adapter. Do not edit by hand.\n"
        "// Regenerate from a Battle proof directory with --ts-out.\n\n"
        f"export const generatedBattleFixture = {payload} as const;\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    app()
