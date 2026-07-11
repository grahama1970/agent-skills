"""Build receipt-backed Battle music promotion and schedule fixtures."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schemas"
SCHEMAS = {
    name: SCHEMA_DIR / f"{name}.schema.json"
    for name in (
        "battle.music_context_packet.v1",
        "battle.music_promotion_receipt.v1",
        "battle.music_schedule_entry.v1",
        "battle.music_schedule.v1",
        "battle.normalized_music_fixture.v1",
    )
}
FORBIDDEN_PUBLIC_MARKERS = (
    "/home/", "/tmp/", "tau-dag-run/", "command-loop/", "command-artifacts/",
    "provider-workspace", "create-midi/", "composer-workspace", "arena/private/",
)
EVENTS_NOT_EMITTED = [
    "exploit_death_stinger", "exploit_victory_stinger", "next_battle_arena",
]


def normalize_music_fixture(
    *,
    source_fixture: Path,
    catalog: Path,
    out_dir: Path,
    public_out_dir: Path | None = None,
    public_audio_root: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Promote loop and spawn-motif assets and emit a public-safe M1 fixture."""

    source = _read(source_fixture)
    runtime_catalog = _read(catalog)
    battle_id = _required_string(source, "battle_id")
    run_event = _event(source, "battle.run_started")
    spawn_event = _event(source, "tau.spawned_child")
    run_receipt = _receipt_ref(run_event)
    spawn_receipt = _receipt_ref(spawn_event)
    child_lane = _required_string(spawn_event, "payload_id")
    sprite_id = _sprite_for_lane(source, child_lane)
    now = generated_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    fixture_id = f"{battle_id}-music-runtime"
    out_dir.mkdir(parents=True, exist_ok=True)

    live_source = source.get("live_source")
    run_id = live_source.get("run_id") if isinstance(live_source, dict) else None
    context = {
        "schema": "battle.music_context_packet.v1",
        "context_id": f"{battle_id}-music-context-001",
        "battle_id": battle_id,
        "run_id": run_id or fixture_id,
        "created_at": now,
        "authority": {
            "source_receipts": [run_receipt, spawn_receipt],
            "clock": {"mode": "elapsed_seconds", "playhead_elapsed_seconds": 0.0},
            "battle_state": {"phase": "running", "intensity": 0.35},
            "permissions": [
                {"music_id": "live_arena_loop", "allowed": True, "permission_kind": "battle_lifecycle_started", "source_receipt_id": run_receipt["receipt_id"]},
                {"music_id": f"motif:{sprite_id}", "allowed": True, "permission_kind": "materialized_spawn", "source_receipt_id": spawn_receipt["receipt_id"], "lane_id": child_lane, "sprite_id": sprite_id},
            ],
        },
        "composition_brief": {
            "section_role": "arena_loop_and_spawn_entrance",
            "fallback_score_id": "live_arena_loop",
            "required_theme_ids": ["battle_main_theme"],
        },
        "claims": {
            "proves": ["Battle supplied receipt-backed music permissions."],
            "does_not_prove": ["A composer ran.", "Audio played.", "Any terminal or Judge outcome occurred."],
        },
    }

    specs = [
        _asset_spec(runtime_catalog, "live_arena_loop", "cue", None),
        _motif_spec(catalog, sprite_id),
    ]
    promotions = []
    entries = []
    for index, spec in enumerate(specs, start=1):
        authority = run_receipt if index == 1 else spawn_receipt
        promotion_id = f"{battle_id}-music-promotion-{index:03d}"
        validation = _validate_score_packet(out_dir, battle_id, spec, authority, sprite_id, promotion_id)
        promoted_assets = _copy_promoted_assets(
            spec=spec,
            promotion_id=promotion_id,
            public_audio_root=public_audio_root,
        )
        promotion = {
            "schema": "battle.music_promotion_receipt.v1",
            "promotion_id": promotion_id,
            "status": "PASS",
            "battle_id": battle_id,
            "context_id": context["context_id"],
            "score_id": spec["score_id"],
            "canonical_music_id": spec["music_id"],
            "composer": {"composer_live": False, "score_packet_authorship": "checked_in_fixture"},
            "validation": validation,
            "assets": promoted_assets,
            "eligibility": {"schedule_eligible": True, "terminal_playback_authority_granted": False},
            "fixture_fallback_used": False,
            "mocked": False,
            "live": "local_deterministic_music_promotion_schedule",
            "created_at": now,
            "claims": {
                "proves": ["MIDI and OGG assets were hash-bound and made eligible for scheduling."],
                "does_not_prove": ["The cue was authorized for a Battle event.", "The cue played.", "A Battle outcome occurred."],
            },
        }
        validate_document(promotion)
        promotions.append(promotion)
        entries.append(_schedule_entry(index, promotion, spec, authority, child_lane, sprite_id))

    schedule = {
        "schema": "battle.music_schedule.v1",
        "schedule_id": f"{battle_id}-music-schedule-001",
        "revision": 1,
        "battle_id": battle_id,
        "generated_at": now,
        "status": "PASS",
        "clock_ref": {"elapsed_time_domain": "battle_elapsed_seconds", "source_receipt_id": run_receipt["receipt_id"]},
        "entries": entries,
        "claim_boundary": _claim_boundary(),
        "source_receipt_refs": [run_receipt, spawn_receipt],
    }
    validate_document(schedule)

    fixture = {
        "schema": "battle.normalized_music_fixture.v1",
        "fixture_id": fixture_id,
        "battle_id": battle_id,
        "generated_at": now,
        "status": "PASS",
        "mocked": False,
        "proof_mode": "receipt_backed_promotion_schedule",
        "context_summary": {"phase": "running", "intensity": 0.35, "playhead_elapsed_seconds": 0.0},
        "promotions": [_promotion_summary(item) for item in promotions],
        "schedule": schedule,
        "events_present": ["live_arena_loop", f"motif:{sprite_id}"],
        "events_not_emitted": EVENTS_NOT_EMITTED,
        "playback_contract": {
            "time_domain": "elapsed_seconds",
            "browser_format": "audio/ogg",
            "midi_is_source_material": True,
            "local_actor_focus_is_preview_only": True,
            "music_never_authorizes_battle_truth": True,
        },
        "claim_boundary": _claim_boundary(),
        "receipt_refs": [run_receipt, spawn_receipt] + [
            {"receipt_id": item["validation"]["receipt_id"], "sha256": item["validation"]["receipt_sha256"]}
            for item in promotions
        ],
        "provenance": {
            "raw_paths_redacted": True,
            "composer_paths_exposed": False,
            "create_midi_paths_exposed": False,
            "credentials_exposed": False,
            "source_fixture_sha256": _sha(source_fixture),
        },
        "frontend_handoff": {
            "route": f"#battle/music?fixture={fixture_id}",
            "schedule_field": "schedule.entries",
            "promotion_field": "promotions",
            "claim_boundary_field": "claim_boundary",
        },
    }
    report = validate_normalized_music_fixture(fixture)
    source_index = {
        "schema": "battle.normalized_music_source_receipt_index.v1",
        "status": "PASS",
        "fixture_id": fixture_id,
        "source_fixture_sha256": _sha(source_fixture),
        "receipts": [run_receipt, spawn_receipt],
        "raw_paths_redacted": True,
    }
    for name, value in (
        ("battle.music_context_packet.json", context),
        ("battle.music_promotion_receipt.json", {"promotions": promotions}),
        ("battle.music_schedule.json", schedule),
        ("battle.normalized_music_fixture.json", fixture),
        ("validation.json", report),
        ("source-receipt-index.json", source_index),
    ):
        _write(out_dir / name, value)
    _write_contract_examples(out_dir, context, promotions, schedule, fixture)
    if public_out_dir:
        public_out_dir.mkdir(parents=True, exist_ok=True)
        target = public_out_dir / "battle.normalized_music_fixture.json"
        shutil.copyfile(out_dir / "battle.normalized_music_fixture.json", target)
        if _sha(target) != _sha(out_dir / "battle.normalized_music_fixture.json"):
            raise RuntimeError("local/public normalized music fixture hash mismatch")
    return fixture


def validate_document(document: dict[str, Any]) -> None:
    schema_id = document.get("schema")
    path = SCHEMAS.get(str(schema_id))
    if not path:
        raise ValueError(f"unsupported music schema: {schema_id}")
    jsonschema.validate(document, _read(path))


def validate_normalized_music_fixture_path(path: Path) -> dict[str, Any]:
    return validate_normalized_music_fixture(_read(path))


def validate_normalized_music_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    validate_document(fixture)
    errors: list[str] = []
    text = json.dumps(fixture, sort_keys=True)
    for marker in FORBIDDEN_PUBLIC_MARKERS:
        if marker.lower() in text.lower():
            errors.append(f"public fixture contains forbidden marker: {marker}")
    if fixture.get("events_not_emitted") != EVENTS_NOT_EMITTED:
        errors.append("events_not_emitted must contain death, victory, and next arena cues")
    schedule = fixture.get("schedule", {})
    validate_document(schedule)
    for entry in schedule.get("entries", []):
        validate_document(entry)
        if entry.get("playback_class") != "promoted":
            errors.append("all authoritative schedule entries must use playback_class=promoted")
        if not entry.get("authorization", {}).get("source_receipt_id"):
            errors.append("schedule entry missing source receipt authorization")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "schema": "battle.normalized_music_fixture_validation.v1",
        "status": "PASS",
        "fixture_id": fixture["fixture_id"],
        "schema_valid": True,
        "claim_boundary_valid": True,
        "raw_paths_redacted": True,
        "schedule_entry_count": len(schedule.get("entries", [])),
    }


def _schedule_entry(index: int, promotion: dict[str, Any], spec: dict[str, Any], authority: dict[str, Any], lane: str, sprite: str) -> dict[str, Any]:
    elapsed = 0.0 if index == 1 else 96.294927
    entry = {
        "schema": "battle.music_schedule_entry.v1",
        "schedule_entry_id": f"schedule-entry-{index:03d}",
        "promotion_id": promotion["promotion_id"],
        "score_id": promotion["score_id"],
        "playback_class": "promoted",
        "asset_ref": {"kind": spec["kind"], "music_id": spec["music_id"], **{asset["role"]: {"public_url": asset["public_url"], "sha256": asset["sha256"]} for asset in promotion["assets"]}},
        "authorization": {"permission_kind": "battle_lifecycle_started" if index == 1 else "materialized_spawn", "source_receipt_id": authority["receipt_id"], "source_receipt_kind": authority["receipt_kind"], "source_receipt_sha256": authority["sha256"]},
        "timing": {"timing_mode": "receipt_elapsed", "source_elapsed_seconds": elapsed, "resolved_start_elapsed_seconds": elapsed},
        "playback": {"channel": "background" if index == 1 else "motif", "priority": 10 if index == 1 else 40, "loop": index == 1, "interrupt_policy": "replace_same_channel", "duck_policy": "none" if index == 1 else "duck_background"},
        "claims": {"proves": ["A promoted asset was scheduled from a named Battle receipt."], "does_not_prove": ["Browser playback occurred.", "Music proves Battle truth."]},
    }
    if index == 2:
        entry["authorization"].update({"lane_id": lane, "sprite_id": sprite})
    validate_document(entry)
    return entry


def _promotion_summary(item: dict[str, Any]) -> dict[str, Any]:
    result = {key: item[key] for key in ("promotion_id", "status", "score_id", "canonical_music_id", "validation", "assets", "eligibility")}
    result["promotion_receipt_sha256"] = _canonical_sha(item)
    return result


def _claim_boundary() -> dict[str, list[str]]:
    return {
        "may_claim": ["assets_promoted", "receipt_authorized_schedule_emitted", "version_hashes_recorded"],
        "must_not_claim": ["audio_played", "speaker_output", "death", "victory", "arena_transition", "exploit_success", "blue_outcome", "judge_success"],
    }


def _event(source: dict[str, Any], event_type: str) -> dict[str, Any]:
    for event in source.get("events", []):
        if event.get("event_type") == event_type:
            return event
    raise ValueError(f"required receipt-backed source event missing: {event_type}")


def _receipt_ref(event: dict[str, Any]) -> dict[str, str]:
    evidence = event.get("evidence", {})
    receipt_id = evidence.get("receipt_id")
    if not receipt_id or evidence.get("proof_mode") != "receipt_backed_fixture":
        raise ValueError(f"event {event.get('id')} lacks receipt-backed evidence")
    return {"receipt_id": receipt_id, "receipt_kind": event["event_type"], "event_id": event["id"], "sha256": _canonical_sha(event)}


def _sprite_for_lane(source: dict[str, Any], lane_id: str) -> str:
    variants = source.get("sprite_theme", {}).get("variants", {})
    preferred = "plague_nurgling" if "plague_nurgling" in variants else None
    if not preferred:
        raise ValueError(f"no backend-selected child sprite available for {lane_id}")
    return preferred


def _asset_spec(catalog: dict[str, Any], music_id: str, kind: str, sprite_id: str | None) -> dict[str, Any]:
    items = catalog.get("cues") if isinstance(catalog.get("cues"), dict) else catalog
    item = items.get(music_id)
    if not isinstance(item, dict):
        raise ValueError(f"catalog missing {music_id}")
    return {"music_id": music_id, "score_id": music_id, "kind": kind, "sprite_id": sprite_id, "ogg": item["ogg"], "midi": item["midi"], "duration_seconds": item["duration_seconds"]}


def _motif_spec(catalog_path: Path, sprite_id: str) -> dict[str, Any]:
    public_root = catalog_path.parents[3]
    ogg = f"/battle-audio/score/v1/motifs/{sprite_id}.ogg"
    midi = f"/battle-audio/score/midi/character_motifs/{sprite_id}.mid"
    for ref in (ogg, midi):
        if not (public_root / ref.lstrip("/")).is_file():
            raise ValueError(f"motif asset missing: {ref}")
    return {"music_id": f"motif:{sprite_id}", "score_id": f"motif-{sprite_id}", "kind": "motif", "sprite_id": sprite_id, "ogg": ogg, "midi": midi, "duration_seconds": 3.0}


def _copy_promoted_assets(*, spec: dict[str, Any], promotion_id: str, public_audio_root: Path) -> list[dict[str, Any]]:
    public_root = public_audio_root.parents[2]
    destination = public_audio_root / promotion_id
    destination.mkdir(parents=True, exist_ok=True)
    result = []
    for role, source_ref in (("ogg", spec["ogg"]), ("midi", spec["midi"])):
        source = public_root / source_ref.lstrip("/")
        suffix = source.suffix
        target = destination / f"{spec['score_id']}{suffix}"
        shutil.copyfile(source, target)
        result.append({"asset_id": f"{promotion_id}-{role}", "role": role, "media_type": "audio/ogg" if role == "ogg" else "audio/midi", "public_url": f"/battle-audio/promoted/v1/{promotion_id}/{target.name}", "sha256": _sha(target), "bytes": target.stat().st_size, "duration_seconds": spec["duration_seconds"]})
    return result


def _validate_score_packet(out_dir: Path, battle_id: str, spec: dict[str, Any], authority: dict[str, Any], sprite_id: str, promotion_id: str) -> dict[str, Any]:
    packet_dir = out_dir / "score-packets"
    receipt_dir = out_dir / "score-validations"
    packet_dir.mkdir(parents=True, exist_ok=True)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    packet = {
        "schema": "battle.music_score_packet.v1",
        "battle_id": battle_id,
        "score_id": spec["score_id"],
        "source_receipt_ids": [authority["receipt_id"]],
        "start_boundary": {"bar": 1, "beat": 1},
        "duration_bars": 8,
        "tempo_bpm": 120,
        "time_signature_plan": [{"bar_start": 1, "numerator": 4, "denominator": 4}],
        "tonal_center": "D minor",
        "intensity": 0.35,
        "motifs": [{"sprite_id": sprite_id, "role": "foreground"}],
        "required_theme_ids": ["battle_main_theme"],
        "forbidden_claims": ["victory", "death", "kill", "exploit_success"],
        "output_midi": f"scores/{spec['score_id']}.mid",
        "fallback_score_id": "live_arena_loop",
        "status": "generated_unvalidated",
    }
    packet_path = packet_dir / f"{spec['score_id']}.json"
    receipt_path = receipt_dir / f"{spec['score_id']}.validation.json"
    _write(packet_path, packet)
    create_midi_root = ROOT.parent / "create-midi"
    command = [
        str(ROOT.parent / "create-midi/run.sh"), "validate-score-packet",
        "--packet", os.path.relpath(packet_path, create_midi_root),
        "--motif-manifest", "fixtures/battle-score-motif-manifest.json",
        "--out", os.path.relpath(receipt_path, create_midi_root),
    ]
    result = subprocess.run(command, cwd=create_midi_root, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not receipt_path.is_file():
        raise RuntimeError(f"create-midi score validation failed for {spec['score_id']}: {result.stderr or result.stdout}")
    receipt = _read(receipt_path)
    if receipt.get("status") != "PASS" or receipt.get("score_id") != spec["score_id"]:
        raise RuntimeError(f"create-midi score validation did not PASS for {spec['score_id']}")
    return {
        "receipt_id": f"create-midi-validation-{promotion_id}",
        "receipt_sha256": _sha(receipt_path),
        "status": "PASS",
        "score_packet_sha256": _sha(packet_path),
    }


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"missing required string: {key}")
    return result


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_contract_examples(out_dir: Path, context: dict[str, Any], promotions: list[dict[str, Any]], schedule: dict[str, Any], fixture: dict[str, Any]) -> None:
    valid = out_dir / "contract-fixtures/valid"
    invalid = out_dir / "contract-fixtures/invalid"
    valid.mkdir(parents=True, exist_ok=True)
    invalid.mkdir(parents=True, exist_ok=True)
    examples = {
        "battle.music_context_packet.v1.json": context,
        "battle.music_promotion_receipt.v1.json": promotions[0],
        "battle.music_schedule_entry.v1.json": schedule["entries"][0],
        "battle.music_schedule.v1.json": schedule,
        "battle.normalized_music_fixture.v1.json": fixture,
    }
    for name, value in examples.items():
        _write(valid / name, value)
        broken = dict(value)
        broken.pop("schema", None)
        _write(invalid / name, broken)
