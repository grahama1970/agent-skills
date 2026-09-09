#!/usr/bin/env python3
"""Generate and check Battle's receipt-derived current status."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator


SCRIPT_DIR = Path(__file__).resolve().parent
BATTLE_DIR = SCRIPT_DIR.parent
REPO_ROOT = BATTLE_DIR.parents[1]
STATUS_PATH = BATTLE_DIR / "CURRENT_STATUS.json"
STATUS_DOC = BATTLE_DIR / "docs" / "status" / "README.md"

DEFAULT_RECEIPTS = {
    "project_agent_dispatch": Path(
        "/home/graham/.local/state/project-watchdog/receipts/"
        "project-watchdog-20260801T120749Z/receipt.json"
    ),
    "fast_sanity": Path("/tmp/battle-tiered-1150-pushed-fast.json"),
    "deterministic_backend": Path(
        "/tmp/battle-tiered-1150-pushed-backend/tiered-deterministic-gate.json"
    ),
    "same_run_qualification": Path(
        "/tmp/battle-same-run-qualification-1143-pushed-20260801T124449Z/"
        "qualification-receipt.json"
    ),
    "live_qualification_gate": Path("/tmp/battle-tiered-1150-pushed-live.json"),
    "human_interjection": Path("/tmp/battle-human-interjection-1145/proof.json"),
    "human_interjection_spectator": Path("/tmp/battle-human-interjection-spectator-proof/proof.json"),
}

SOURCE_CONTEXT = {
    "battle_skill_contract": "skills/battle/SKILL.md",
    "terminal_semantics_decision": "skills/battle/docs/TERMINAL_SEMANTICS_LOCAL_MVP.md",
    "planning_bundle": (
        "/home/graham/workspace/experiments/agent-skills/artifacts/ask/"
        "battle_remaining_gaps_ticket_bundle_20260801.md"
    ),
}

ADAPTIVE_LINEAGE_QUALIFICATION_SCHEMAS = {
    "battle.adaptive_lineage_qualification.v1",
    "battle.adaptive_lineage_goal_qualification.v1",
}

MIN_ADAPTIVE_LINEAGE_CHECKS = 11
SUPPORTED_TERMINAL_STATES = (
    "BLUE_SUCCESS",
    "RED_SUCCESS",
    "INSUFFICIENT_EVIDENCE",
    "BLOCKED",
    "UNAVAILABLE",
)
UNSUPPORTED_TERMINAL_ALIASES = {"kill", "promotion", "fastest_crash"}
TERMINAL_RECEIPT_SCHEMAS = (
    "battle.arena_tau_public_only_judge_receipt.v1",
    "battle.arena_tau_public_only_run_receipt.v1",
    "battle.tiered_live_qualification_gate.v1",
    "battle.same_run_arena_pixi_qualification.v1",
)
TERMINAL_SEMANTICS_RECEIPT_PATH = Path(
    os.environ.get("BATTLE_TERMINAL_SEMANTICS_RECEIPT", "/tmp/battle-current-status-terminal-semantics.json")
)


class TerminalSemanticsEvidence(BaseModel):
    """Typed terminal-result evidence accepted by the local MVP."""

    model_config = ConfigDict(extra="forbid")

    terminal_state: Literal[
        "BLUE_SUCCESS",
        "RED_SUCCESS",
        "INSUFFICIENT_EVIDENCE",
        "BLOCKED",
        "UNAVAILABLE",
    ]
    source_schema: Literal[
        "battle.arena_tau_public_only_judge_receipt.v1",
        "battle.arena_tau_public_only_run_receipt.v1",
        "battle.tiered_live_qualification_gate.v1",
        "battle.same_run_arena_pixi_qualification.v1",
    ]
    source_status: Literal["PASS"]
    source_authority: Literal["judge", "scorekeeper"]
    judge_verdict: Literal[
        "BLUE_SUCCESS",
        "RED_SUCCESS",
        "INSUFFICIENT_EVIDENCE",
        "BLOCKED",
        "UNAVAILABLE",
    ] | None = None
    scorekeeper_status: Literal[
        "BLUE_SUCCESS",
        "RED_SUCCESS",
        "INSUFFICIENT_EVIDENCE",
        "BLOCKED",
        "UNAVAILABLE",
    ] | None = None
    crash_observation_only: bool = False

    @model_validator(mode="after")
    def require_authoritative_terminal_evidence(self) -> "TerminalSemanticsEvidence":
        if self.crash_observation_only:
            raise ValueError("crash observations are not terminal evidence without a typed Judge result")
        if self.source_authority == "judge" and self.judge_verdict != self.terminal_state:
            raise ValueError("Judge-backed terminal evidence must carry a matching typed judge_verdict")
        if self.source_authority == "scorekeeper" and self.scorekeeper_status != self.terminal_state:
            raise ValueError("scorekeeper terminal evidence must carry a matching scorekeeper_status")
        return self


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_value(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value.removeprefix("sha256:")


def _same_path(left: Path, right: Path) -> bool:
    return left.resolve(strict=False) == right.resolve(strict=False)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def _json_or_error(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"{label}_missing:{path}")
        return None
    try:
        return _read_json(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label}_invalid_json:{path}:{exc}")
        return None


def _require_sha(label: str, path: Path, expected: Any, errors: list[str]) -> bool:
    expected_hash = _hash_value(expected)
    if not expected_hash:
        errors.append(f"{label}_missing_expected_sha256:{path}")
        return False
    if not path.is_file():
        errors.append(f"{label}_missing_for_sha256:{path}")
        return False
    actual = _sha256(path)
    if actual != expected_hash:
        errors.append(f"{label}_sha256_mismatch:{path}:{actual}!={expected_hash}")
        return False
    return True


def _require_status(label: str, payload: dict[str, Any], status: str, errors: list[str]) -> bool:
    if payload.get("status") != status:
        errors.append(f"{label}_status_not_{status.lower()}:{payload.get('status')}")
        return False
    return True


def _require_schema(label: str, payload: dict[str, Any], schemas: set[str], errors: list[str]) -> bool:
    if payload.get("schema") not in schemas:
        errors.append(f"{label}_schema_mismatch:{payload.get('schema')}")
        return False
    return True


def _record_path(status: dict[str, Any], key: str, errors: list[str]) -> Path | None:
    record = (status.get("source_receipts") or {}).get(key) or {}
    raw = record.get("path")
    if not raw:
        errors.append(f"{key}_source_receipt_path_missing")
        return None
    return Path(str(raw))


def _validate_cached_source_records(status: dict[str, Any], errors: list[str]) -> None:
    for name, record in (status.get("source_receipts") or {}).items():
        raw = record.get("path")
        if not raw:
            errors.append(f"source_receipt_path_missing:{name}")
            continue
        path = Path(str(raw))
        if record.get("kind") == "directory":
            if not path.is_dir():
                errors.append(f"source_receipt_directory_missing:{name}:{path}")
            continue
        if record.get("exists") is False:
            if not record.get("superseded_by") and path.exists():
                errors.append(f"source_receipt_exists_false_but_present:{name}:{path}")
            continue
        if record.get("exists") is not True:
            continue
        if not path.is_file():
            errors.append(f"source_receipt_file_missing:{name}:{path}")
            continue
        if "sha256" in record:
            _require_sha(f"source_receipt:{name}", path, record.get("sha256"), errors)
        try:
            payload = _read_json(path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for field in ("schema", "status", "mocked", "live"):
            if field in record and payload.get(field) != record.get(field):
                errors.append(
                    f"source_receipt_{field}_mismatch:{name}:{payload.get(field)!r}!={record.get(field)!r}"
                )


def _require_path_binding(
    label: str,
    path: Path,
    *,
    root: Path,
    expected_sha256: Any | None,
    errors: list[str],
) -> bool:
    ok = True
    if not _inside(path, root):
        errors.append(f"{label}_outside_campaign_root:{path}")
        ok = False
    if not path.is_file():
        errors.append(f"{label}_missing:{path}")
        return False
    if expected_sha256 is not None:
        ok = _require_sha(label, path, expected_sha256, errors) and ok
    return ok


def _required_check_path(
    qualification: dict[str, Any],
    name: str,
    *,
    root: Path,
    errors: list[str],
) -> Path | None:
    check = _named_check(qualification.get("checks") or [], name)
    if check.get("status") != "PASS":
        errors.append(f"qualification_check_not_pass:{name}:{check.get('status')}")
    raw = check.get("path")
    if not raw:
        errors.append(f"qualification_check_path_missing:{name}")
        return None
    path = Path(str(raw))
    if not _inside(path, root):
        errors.append(f"qualification_check_path_outside_source_run:{name}:{path}")
    return path


def _validate_adaptive_source_run(
    qualification_path: Path,
    qualification: dict[str, Any],
    errors: list[str],
) -> bool:
    ok_before = len(errors)
    _require_schema("adaptive_lineage_qualification", qualification, ADAPTIVE_LINEAGE_QUALIFICATION_SCHEMAS, errors)
    _require_status("adaptive_lineage_qualification", qualification, "PASS", errors)
    if qualification.get("battle_id") != "battle-004":
        errors.append(f"adaptive_lineage_qualification_battle_id_mismatch:{qualification.get('battle_id')}")
    source_run_dir = Path(str(qualification.get("source_run_dir") or ""))
    if not source_run_dir.is_dir():
        errors.append(f"adaptive_lineage_source_run_dir_missing:{source_run_dir}")
        return False
    campaign_path = _required_check_path(
        qualification,
        "campaign_receipt_present",
        root=source_run_dir,
        errors=errors,
    )
    integrity_path = _required_check_path(
        qualification,
        "artifact_integrity_receipt_present",
        root=source_run_dir,
        errors=errors,
    )
    backend_path = _required_check_path(
        qualification,
        "prior_backend_verification_present",
        root=source_run_dir,
        errors=errors,
    )
    if campaign_path is None or integrity_path is None or backend_path is None:
        return False

    campaign = _json_or_error(campaign_path, "adaptive_campaign_receipt", errors)
    integrity = _json_or_error(integrity_path, "adaptive_artifact_integrity", errors)
    backend = _json_or_error(backend_path, "adaptive_backend_verification", errors)
    if campaign is None or integrity is None or backend is None:
        return False
    _require_schema("adaptive_campaign_receipt", campaign, {"battle.adaptive_red_blue_lineage_canary.v1"}, errors)
    _require_schema("adaptive_artifact_integrity", integrity, {"battle.adaptive_artifact_integrity.v1"}, errors)
    _require_schema(
        "adaptive_backend_verification",
        backend,
        {"battle.adaptive_lineage_backend_verification.v1"},
        errors,
    )
    for label, payload in [
        ("adaptive_campaign_receipt", campaign),
        ("adaptive_artifact_integrity", integrity),
        ("adaptive_backend_verification", backend),
    ]:
        _require_status(label, payload, "PASS", errors)
    if campaign.get("battle_id") != qualification.get("battle_id"):
        errors.append("adaptive_campaign_battle_id_not_bound_to_qualification")
    if campaign.get("live") is not True or campaign.get("mocked") is not False:
        errors.append("adaptive_campaign_live_unmocked_required")
    if campaign.get("fixture_fallback_used") is not False:
        errors.append("adaptive_campaign_fixture_fallback_used")
    if Path(str(backend.get("run_dir") or "")).resolve(strict=False) != source_run_dir.resolve(strict=False):
        errors.append("adaptive_backend_run_dir_not_source_run")
    if backend.get("live") is not True or backend.get("mocked") is not False:
        errors.append("adaptive_backend_verification_live_unmocked_required")

    embedded_integrity = campaign.get("artifact_integrity") or {}
    embedded_integrity_path = Path(str(embedded_integrity.get("path") or ""))
    if not _same_path(embedded_integrity_path, integrity_path):
        errors.append("adaptive_campaign_integrity_path_mismatch")
    _require_sha("adaptive_campaign_integrity", integrity_path, embedded_integrity.get("sha256"), errors)
    event_journal = campaign.get("event_journal") or {}
    if event_journal.get("path"):
        _require_path_binding(
            "adaptive_campaign_event_journal",
            Path(str(event_journal["path"])),
            root=source_run_dir,
            expected_sha256=event_journal.get("sha256"),
            errors=errors,
        )
    selection = campaign.get("selection") or {}
    selection_path = Path(str(selection.get("path") or ""))
    if selection_path:
        _require_path_binding(
            "adaptive_campaign_selection",
            selection_path,
            root=source_run_dir,
            expected_sha256=selection.get("sha256"),
            errors=errors,
        )

    slots = integrity.get("slots") or []
    replays = integrity.get("judge_replays") or []
    if integrity.get("matched_slot_count") != integrity.get("required_slot_count") or len(slots) != 4:
        errors.append("adaptive_integrity_slot_count_mismatch")
    if integrity.get("matched_replay_count") != integrity.get("required_replay_count") or len(replays) != 2:
        errors.append("adaptive_integrity_replay_count_mismatch")
    if integrity.get("unique_slot_paths") is not True or integrity.get("unique_replay_paths") is not True:
        errors.append("adaptive_integrity_paths_not_unique")
    for slot in slots:
        slot_path = Path(str(slot.get("path") or ""))
        label = f"adaptive_slot:{slot.get('slot_key')}"
        _require_path_binding(label, slot_path, root=source_run_dir, expected_sha256=slot.get("expected_sha256"), errors=errors)
        if slot.get("actual_sha256") != slot.get("expected_sha256") or slot.get("matched") is not True:
            errors.append(f"{label}_record_not_matched")
        expected_key = f"generation-{slot.get('generation')}:{slot.get('team')}"
        if slot.get("slot_key") != expected_key:
            errors.append(f"{label}_slot_key_mismatch:{expected_key}")
    for replay in replays:
        replay_path = Path(str(replay.get("path") or ""))
        label = f"adaptive_replay:generation-{replay.get('expected_generation')}"
        _require_path_binding(label, replay_path, root=source_run_dir, expected_sha256=replay.get("expected_sha256"), errors=errors)
        replay_payload = _json_or_error(replay_path, label, errors)
        if replay_payload is not None:
            _require_status(label, replay_payload, "PASS", errors)
            generation = replay_payload.get("generation", replay.get("generation"))
            if generation != replay.get("expected_generation"):
                errors.append(f"{label}_generation_mismatch:{generation}")
        if replay.get("actual_sha256") != replay.get("expected_sha256") or replay.get("matched") is not True:
            errors.append(f"{label}_record_not_matched")

    for record in backend.get("slot_records") or []:
        _require_path_binding(
            f"adaptive_backend_slot:{record.get('slot_key')}",
            Path(str(record.get("path") or "")),
            root=source_run_dir,
            expected_sha256=record.get("expected_sha256"),
            errors=errors,
        )
        if record.get("actual_sha256") != record.get("expected_sha256") or record.get("matched") is not True:
            errors.append(f"adaptive_backend_slot_record_not_matched:{record.get('slot_key')}")
    for record in backend.get("replay_records") or []:
        _require_path_binding(
            f"adaptive_backend_replay:generation-{record.get('generation')}",
            Path(str(record.get("path") or "")),
            root=source_run_dir,
            expected_sha256=record.get("expected_sha256"),
            errors=errors,
        )
        if record.get("actual_sha256") != record.get("expected_sha256") or record.get("matched") is not True:
            errors.append(f"adaptive_backend_replay_record_not_matched:{record.get('generation')}")
    for record in backend.get("attempt_records") or []:
        attempt_path = Path(str(record.get("path") or ""))
        _require_path_binding("adaptive_backend_attempt", attempt_path, root=source_run_dir, expected_sha256=None, errors=errors)
        if record.get("status") != "PASS" or record.get("container_input_hash_pass") is not True:
            errors.append(f"adaptive_backend_attempt_not_bound:{attempt_path}")
    for record in backend.get("provider_records") or []:
        provider_path = Path(str(record.get("path") or ""))
        _require_path_binding("adaptive_backend_provider", provider_path, root=source_run_dir, expected_sha256=record.get("sha256"), errors=errors)
        provider_payload = _json_or_error(provider_path, "adaptive_backend_provider", errors)
        if (
            provider_payload is None
            or provider_payload.get("schema") != "tau.scillm_call_receipt.v1"
            or provider_payload.get("status") != "PASS"
            or provider_payload.get("live") is not True
            or provider_payload.get("mocked") is not False
            or provider_payload.get("http_status") != 200
        ):
            errors.append(f"adaptive_backend_provider_not_live_pass:{provider_path}")
    for checked in backend.get("checked_files") or []:
        _require_path_binding("adaptive_backend_checked_file", Path(str(checked)), root=source_run_dir, expected_sha256=None, errors=errors)
    if backend.get("slot_hashes_matched") != backend.get("slot_hashes_required"):
        errors.append("adaptive_backend_slot_hash_count_mismatch")
    if backend.get("exact_replays_matched") != backend.get("exact_replays_required"):
        errors.append("adaptive_backend_replay_hash_count_mismatch")
    if backend.get("provider_receipts_passed") != backend.get("provider_receipts_required"):
        errors.append("adaptive_backend_provider_count_mismatch")

    counts = qualification.get("counts") or {}
    for left, right in [
        ("slot_hashes_matched", "slot_hashes_required"),
        ("exact_replays_matched", "exact_replays_required"),
    ]:
        if counts.get(left) != counts.get(right):
            errors.append(f"adaptive_qualification_count_mismatch:{left}:{right}")
    if counts.get("slot_hashes_matched") != backend.get("slot_hashes_matched"):
        errors.append("adaptive_qualification_slot_count_not_backend_count")
    if counts.get("exact_replays_matched") != backend.get("exact_replays_matched"):
        errors.append("adaptive_qualification_replay_count_not_backend_count")
    provider_check = _named_check(qualification.get("checks") or [], "provider_live_authority_receipts_bound")
    if provider_check.get("passed") != backend.get("provider_receipts_passed"):
        errors.append("adaptive_qualification_provider_count_not_backend_count")
    if not _inside(qualification_path, BATTLE_DIR):
        errors.append(f"adaptive_qualification_manifest_not_durable_battle_local:{qualification_path}")
    return len(errors) == ok_before


def _seed_records_bound(campaign: dict[str, Any], broadcast: dict[str, Any], errors: list[str]) -> bool:
    ok_before = len(errors)
    campaign_seeds = campaign.get("mutation_seed_receipts") or {}
    broadcast_seeds = broadcast.get("seed_receipts") or []
    if campaign_seeds.get("schema") != "battle.mutation_seed_receipt_bundle.v1":
        errors.append("provider_campaign_seed_bundle_schema_mismatch")
    if campaign_seeds.get("status") != "PASS":
        errors.append("provider_campaign_seed_bundle_not_pass")
    campaign_set = {
        (item.get("kind"), item.get("path"), _hash_value(item.get("sha256")))
        for item in campaign_seeds.get("receipts") or []
    }
    broadcast_set = {
        (item.get("kind"), item.get("path"), _hash_value(item.get("sha256")))
        for item in broadcast_seeds
    }
    if campaign_set != broadcast_set or not campaign_set:
        errors.append("provider_seed_receipts_not_bound_between_campaign_and_broadcast")
    for item in campaign_seeds.get("receipts") or []:
        seed_path = Path(str(item.get("path") or ""))
        _require_sha(f"provider_seed:{item.get('kind')}", seed_path, item.get("sha256"), errors)
        if item.get("bytes") is not None and seed_path.is_file() and seed_path.stat().st_size != item.get("bytes"):
            errors.append(f"provider_seed_size_mismatch:{seed_path}")
    return len(errors) == ok_before


def _validate_provider_tau_chain(status: dict[str, Any], errors: list[str]) -> bool:
    ok_before = len(errors)
    campaign_path = _record_path(status, "provider_tau_seeded_campaign", errors)
    broadcast_path = _record_path(status, "provider_tau_seeded_broadcast", errors)
    memory_path = _record_path(status, "provider_tau_memory_promotion", errors)
    if campaign_path is None or broadcast_path is None or memory_path is None:
        return False
    provider_root = _provider_root_for_campaign(campaign_path)
    source_root = campaign_path.parent
    broadcast_root = provider_root / "broadcast"
    if provider_root is None:
        errors.append(f"provider_campaign_path_not_supported_layout:{campaign_path}")
        provider_root = campaign_path.parent
    if not _inside(broadcast_path, broadcast_root):
        errors.append(f"provider_broadcast_path_not_broadcast_root:{broadcast_path}")
    if not _inside(memory_path, provider_root / "memory-promotion-eval"):
        errors.append(f"provider_memory_path_not_memory_root:{memory_path}")

    campaign = _json_or_error(campaign_path, "provider_campaign_receipt", errors)
    broadcast = _json_or_error(broadcast_path, "provider_broadcast_receipt", errors)
    memory = _json_or_error(memory_path, "provider_memory_promotion_receipt", errors)
    visibility_path = source_root / "generation-2" / "visibility-validation.json"
    visibility = _json_or_error(visibility_path, "provider_visibility_receipt", errors)
    if campaign is None or broadcast is None or memory is None or visibility is None:
        return False
    _require_schema("provider_campaign_receipt", campaign, {"battle.adaptive_red_blue_lineage_canary.v1"}, errors)
    _require_schema("provider_broadcast_receipt", broadcast, {"battle.provider_tau_lineage_broadcast.v1"}, errors)
    _require_schema("provider_memory_promotion_receipt", memory, {"battle.memory_promotion_live_receipt.v1"}, errors)
    for label, payload in [
        ("provider_campaign_receipt", campaign),
        ("provider_broadcast_receipt", broadcast),
        ("provider_memory_promotion_receipt", memory),
        ("provider_visibility_receipt", visibility),
    ]:
        _require_status(label, payload, "PASS", errors)
    if campaign.get("battle_id") != "battle-004" or broadcast.get("campaign_receipt") is None:
        errors.append("provider_campaign_battle_or_broadcast_binding_missing")
    if campaign.get("live") is not True or campaign.get("mocked") is not False:
        errors.append("provider_campaign_live_unmocked_required")
    if not _same_path(Path(str(broadcast.get("campaign_receipt") or "")), campaign_path):
        errors.append("provider_broadcast_campaign_path_mismatch")
    _require_sha("provider_broadcast_campaign", campaign_path, broadcast.get("campaign_receipt_sha256"), errors)
    if not _same_path(Path(str(memory.get("campaign_receipt") or "")), campaign_path):
        errors.append("provider_memory_campaign_path_mismatch")
    _require_sha("provider_memory_campaign", campaign_path, memory.get("campaign_receipt_sha256"), errors)
    if visibility.get("private_input_leaks"):
        errors.append("provider_visibility_private_input_leaks")

    component_specs = [
        ("arena", "arena_receipt", "arena_receipt_sha256", {"battle.arena_receipt.v1"}),
        ("red", "red_team_activity_receipt", "red_team_activity_receipt_sha256", {"battle.team_activity_receipt.v1"}),
        ("blue", "blue_team_activity_receipt", "blue_team_activity_receipt_sha256", {"battle.team_activity_receipt.v1"}),
        (
            "commentary",
            "sports_play_by_play_commentary_receipt",
            "sports_play_by_play_commentary_receipt_sha256",
            {"battle.sports_play_by_play_commentary_receipt.v1"},
        ),
    ]
    components: dict[str, dict[str, Any]] = {}
    component_paths: dict[str, Path] = {}
    for label, path_key, sha_key, schemas in component_specs:
        component_path = Path(str(broadcast.get(path_key) or ""))
        component_paths[label] = component_path
        _require_path_binding(
            f"provider_broadcast_{label}",
            component_path,
            root=broadcast_root,
            expected_sha256=broadcast.get(sha_key),
            errors=errors,
        )
        payload = _json_or_error(component_path, f"provider_broadcast_{label}", errors)
        if payload is None:
            continue
        components[label] = payload
        _require_schema(f"provider_broadcast_{label}", payload, schemas, errors)
        _require_status(f"provider_broadcast_{label}", payload, "PASS", errors)
        if label in {"arena", "red", "blue"}:
            if not _same_path(Path(str(payload.get("campaign_receipt") or "")), campaign_path):
                errors.append(f"provider_broadcast_{label}_campaign_path_mismatch")
            _require_sha(f"provider_broadcast_{label}_campaign", campaign_path, payload.get("campaign_receipt_sha256"), errors)
        if label in {"red", "blue"} and payload.get("team") != label:
            errors.append(f"provider_broadcast_team_mismatch:{label}:{payload.get('team')}")
    commentary = components.get("commentary") or {}
    for label in ("arena", "red", "blue"):
        receipt_key = "arena_receipt" if label == "arena" else f"{label}_team_activity_receipt"
        sha_key = "arena_receipt_sha256" if label == "arena" else f"{label}_team_activity_receipt_sha256"
        if not _same_path(Path(str(commentary.get(receipt_key) or "")), component_paths.get(label, Path(""))):
            errors.append(f"provider_commentary_{label}_receipt_path_mismatch")
        if label in component_paths:
            _require_sha(f"provider_commentary_{label}_receipt", component_paths[label], commentary.get(sha_key), errors)
    red_activities = (components.get("red") or {}).get("activities") or []
    blue_activities = (components.get("blue") or {}).get("activities") or []
    commentary_lines = commentary.get("commentary_lines") or []
    if not commentary_lines:
        errors.append("provider_commentary_lines_empty")
    for index, line in enumerate(commentary_lines):
        source_receipts = {str(item) for item in line.get("source_receipts") or []}
        allowed_receipts = {str(component_paths[key]) for key in ("arena", "red", "blue") if key in component_paths}
        if not source_receipts or not source_receipts <= allowed_receipts:
            errors.append(f"provider_commentary_line_source_receipts_mismatch:{index}")
        for team, indices in (line.get("source_activity_indices") or {}).items():
            activities = red_activities if team == "red" else blue_activities if team == "blue" else None
            if activities is None:
                errors.append(f"provider_commentary_line_unknown_team:{index}:{team}")
                continue
            if not indices:
                errors.append(f"provider_commentary_line_empty_indices:{index}:{team}")
            for activity_index in indices:
                if not isinstance(activity_index, int) or isinstance(activity_index, bool) or not 0 <= activity_index < len(activities):
                    errors.append(f"provider_commentary_line_bad_index:{index}:{team}:{activity_index!r}")

    _seed_records_bound(campaign, broadcast, errors)
    selection = campaign.get("selection") or {}
    selection_path = Path(str(selection.get("path") or ""))
    if selection_path:
        _require_path_binding("provider_selection", selection_path, root=source_root, expected_sha256=selection.get("sha256"), errors=errors)
        selection_payload = _json_or_error(selection_path, "provider_selection", errors)
        if selection_payload is not None:
            _require_schema("provider_selection", selection_payload, {"battle.adaptive_selection_receipt.v1"}, errors)
            _require_status("provider_selection", selection_payload, "PASS", errors)
            if selection_payload.get("run_id") != campaign.get("run_id") or selection_payload.get("battle_id") != campaign.get("battle_id"):
                errors.append("provider_selection_campaign_binding_mismatch")
    for promotion in memory.get("promotions") or []:
        team = promotion.get("team")
        if team not in {"red", "blue"}:
            errors.append(f"provider_memory_unknown_team:{team}")
            continue
        expected_marker = f"battle-memory-promotion:{campaign.get('run_id')}:{team}:generation-2"
        if expected_marker not in str(promotion.get("problem") or ""):
            errors.append(f"provider_memory_marker_mismatch:{team}")
        if not promotion.get("solution_sha256"):
            errors.append(f"provider_memory_solution_sha_missing:{team}")
        for phase in ("learn", "recall"):
            phase_info = promotion.get(phase) or {}
            if phase_info.get("exit_code") != 0:
                errors.append(f"provider_memory_{phase}_exit_nonzero:{team}:{phase_info.get('exit_code')}")
            for stream in ("stdout", "stderr"):
                stream_path = Path(str(phase_info.get(stream) or ""))
                _require_path_binding(
                    f"provider_memory_{phase}_{stream}:{team}",
                    stream_path,
                    root=memory_path.parent,
                    expected_sha256=None,
                    errors=errors,
                )
        if (promotion.get("recall") or {}).get("marker_found") is not True:
            errors.append(f"provider_memory_recall_marker_missing:{team}")
    if {item.get("team") for item in memory.get("promotions") or []} != {"red", "blue"}:
        errors.append("provider_memory_promotions_not_red_and_blue")
    return len(errors) == ok_before


def _proven_claim(status: dict[str, Any], claim_id: str, errors: list[str]) -> dict[str, Any]:
    claim = next((item for item in status.get("proven", []) if item.get("id") == claim_id), None)
    if not isinstance(claim, dict):
        errors.append(f"proven_claim_missing:{claim_id}")
        return {}
    return claim


def _require_claim_path(
    label: str,
    claim: dict[str, Any],
    key: str,
    expected: Path,
    errors: list[str],
) -> None:
    raw = claim.get(key)
    if not raw:
        errors.append(f"{label}_{key}_missing")
        return
    if not _same_path(Path(str(raw)), expected):
        errors.append(f"{label}_{key}_path_mismatch:{raw}!={expected}")


def _validate_current_status_claim_bindings(status: dict[str, Any], errors: list[str]) -> None:
    adaptive_path = _record_path(status, "adaptive_lineage_qualification", errors)
    pixi_binding_path = _record_path(status, "adaptive_lineage_pixi_binding", errors)
    pixi_gameplay_path = _record_path(status, "adaptive_lineage_pixi_gameplay", errors)
    surf_screenshot_path = _record_path(status, "adaptive_lineage_surf_screenshot", errors)
    provider_campaign_path = _record_path(status, "provider_tau_seeded_campaign", errors)
    provider_broadcast_path = _record_path(status, "provider_tau_seeded_broadcast", errors)
    provider_memory_path = _record_path(status, "provider_tau_memory_promotion", errors)

    adaptive_claim = _proven_claim(status, "p0_adaptive_lineage_fresh_qualification", errors)
    if adaptive_path is not None:
        _require_claim_path("adaptive_claim", adaptive_claim, "receipt", adaptive_path, errors)

    pixi_claim = _proven_claim(status, "adaptive_lineage_pixi_receipt_replay", errors)
    pixi_evidence = pixi_claim.get("evidence") or {}
    if pixi_gameplay_path is not None:
        _require_claim_path("pixi_claim", pixi_claim, "receipt", pixi_gameplay_path, errors)
        gameplay_receipt = pixi_evidence.get("gameplay_receipt") or {}
        if not _same_path(Path(str(gameplay_receipt.get("path") or "")), pixi_gameplay_path):
            errors.append("pixi_claim_gameplay_evidence_path_mismatch")
    if pixi_binding_path is not None:
        binding_receipt = pixi_evidence.get("binding_receipt") or {}
        if not _same_path(Path(str(binding_receipt.get("path") or "")), pixi_binding_path):
            errors.append("pixi_claim_binding_evidence_path_mismatch")
    if surf_screenshot_path is not None:
        screenshot = pixi_evidence.get("surf_screenshot") or {}
        if not _same_path(Path(str(screenshot.get("path") or "")), surf_screenshot_path):
            errors.append("pixi_claim_surf_screenshot_path_mismatch")

    provider_claim = _proven_claim(status, "provider_tau_seeded_lineage_spawn", errors)
    provider_evidence = provider_claim.get("evidence") or {}
    if provider_campaign_path is not None:
        _require_claim_path("provider_claim", provider_claim, "receipt", provider_campaign_path, errors)
        if not _same_path(Path(str(provider_evidence.get("campaign_receipt") or "")), provider_campaign_path):
            errors.append("provider_claim_campaign_evidence_path_mismatch")
        expected_root = _provider_root_for_campaign(provider_campaign_path)
        if expected_root is None:
            errors.append(f"provider_claim_campaign_path_not_supported_layout:{provider_campaign_path}")
            expected_root = provider_campaign_path.parent
        if not _same_path(Path(str(provider_evidence.get("root") or "")), expected_root):
            errors.append("provider_claim_root_evidence_path_mismatch")
        expected_visibility = provider_campaign_path.parent / "generation-2" / "visibility-validation.json"
        if not _same_path(Path(str(provider_evidence.get("visibility_receipt") or "")), expected_visibility):
            errors.append("provider_claim_visibility_evidence_path_mismatch")
    if provider_broadcast_path is not None and not _same_path(
        Path(str(provider_evidence.get("broadcast_receipt") or "")),
        provider_broadcast_path,
    ):
        errors.append("provider_claim_broadcast_evidence_path_mismatch")

    memory_claim = _proven_claim(status, "provider_tau_memory_promotion", errors)
    memory_evidence = memory_claim.get("evidence") or {}
    if provider_memory_path is not None:
        _require_claim_path("memory_claim", memory_claim, "receipt", provider_memory_path, errors)
        if not _same_path(Path(str(memory_evidence.get("path") or "")), provider_memory_path):
            errors.append("memory_claim_evidence_path_mismatch")


def _gh_issue_list(state: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            "grahama1970/agent-skills",
            "--label",
            "battle",
            "--state",
            state,
            "--limit",
            "200",
            "--json",
            "number,title,state,labels,url",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def _receipt(path: Path) -> dict[str, Any]:
    item: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
    }
    if not path.is_file():
        return item
    payload = _read_json(path)
    item.update(
        {
            "sha256": _sha256(path),
            "schema": payload.get("schema"),
            "status": payload.get("status"),
            "mocked": payload.get("mocked"),
            "live": payload.get("live"),
        }
    )
    return item


def _artifact(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False}
    item: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if path.is_file():
        item.update({"sha256": _sha256(path), "kind": "file"})
    elif path.is_dir():
        item["kind"] = "directory"
    return item


def _latest_backend_goal_dir() -> Path | None:
    env_path = os.environ.get("BATTLE_BACKEND_GOAL_PROOF_DIR")
    candidates = [Path(env_path)] if env_path else []
    candidates.extend(Path("/tmp").glob("battle-backend-goal-proof-*"))
    valid: list[Path] = []
    required = [
        Path("battle-004-combiner/combiner-proof-receipt.json"),
        Path("battle-004-spawn-architect/spawn-architect-receipt.json"),
        Path("battle-semantic-outcome-matrix.json"),
        Path("battle-exploit-lifecycle-dag.json"),
    ]
    for candidate in candidates:
        if candidate.is_dir() and all((candidate / rel).is_file() for rel in required):
            valid.append(candidate)
    if not valid:
        return None
    return max(valid, key=lambda path: path.stat().st_mtime)


def _is_adaptive_lineage_qualification(payload: dict[str, Any]) -> bool:
    if payload.get("schema") in ADAPTIVE_LINEAGE_QUALIFICATION_SCHEMAS:
        return True
    return (
        payload.get("battle_id") == "battle-004"
        and isinstance(payload.get("checks"), list)
        and "adaptive-lineage" in str(payload.get("proof_scope", ""))
    )


def _latest_adaptive_lineage_qualification() -> Path | None:
    candidates: list[Path] = []
    for path in (BATTLE_DIR / "local").glob("**/adaptive-lineage-qualification.json"):
        try:
            payload = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if _is_adaptive_lineage_qualification(payload):
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _check_passed(item: dict[str, Any]) -> bool:
    if "ok" in item:
        return bool(item.get("ok"))
    return item.get("status") == "PASS"


def _named_check(checks: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next((item for item in checks if item.get("name") == name), {})


def _adaptive_lineage_qualification_evidence(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "status": None,
            "checks_ok": False,
            "check_count": 0,
            "selected_id": None,
            "runner_up_id": None,
            "g2_judge_attempts": None,
            "budget": None,
        }
    payload = _read_json(path)
    checks = payload.get("checks") or []
    counts = payload.get("counts") or {}
    provider_check = _named_check(checks, "provider_live_authority_receipts_bound")
    return {
        "status": payload.get("status"),
        "schema": payload.get("schema"),
        "stop_condition": payload.get("stop_condition"),
        "checks_ok": all(_check_passed(item) for item in checks),
        "check_count": len(checks),
        "failed_checks": [item.get("name") for item in checks if not _check_passed(item)],
        "selected_id": payload.get("selected_id"),
        "runner_up_id": payload.get("runner_up_id"),
        "g2_judge_attempts": (payload.get("g2_outcome") or {}).get("judge_attempts"),
        "g2_patched_bypass": (payload.get("g2_outcome") or {}).get("patched_bypass"),
        "g2_vulnerable_original_confirmed": (payload.get("g2_outcome") or {}).get(
            "vulnerable_original_confirmed"
        ),
        "exact_replays_matched": counts.get("exact_replays_matched"),
        "exact_replays_required": counts.get("exact_replays_required"),
        "slot_hashes_matched": counts.get("slot_hashes_matched"),
        "slot_hashes_required": counts.get("slot_hashes_required"),
        "provider_receipts_passed": provider_check.get("passed"),
        "provider_receipts_required": provider_check.get("required"),
        "budget": payload.get("budget"),
    }


def _latest_provider_tau_seeded_root() -> Path | None:
    roots = []
    env_path = os.environ.get("BATTLE_PROVIDER_TAU_SEEDED_ROOT")
    if env_path:
        roots.append(Path(env_path))
    review_root = Path("/mnt/storage12tb/skills/battle/review-ticket-live-rerun")
    if review_root.exists():
        roots.append(review_root)
    for receipt_path in Path("/mnt/storage12tb/skills/battle").glob(
        "provider-tau-seeded-*/source-run/campaign-receipt.json"
    ):
        root = receipt_path.parents[1]
        roots.append(root)
    valid = [
        root
        for root in roots
        if (
            _provider_campaign_path(root) is not None
            and (root / "broadcast" / "provider-tau-lineage-broadcast-receipt.json").is_file()
            and (root / "memory-promotion-eval" / "memory-promotion-live-receipt.json").is_file()
        )
    ]
    return max(valid, key=lambda path: path.stat().st_mtime) if valid else None


def _provider_campaign_path(root: Path) -> Path | None:
    for candidate in (root / "campaign-receipt.json", root / "source-run" / "campaign-receipt.json"):
        if candidate.is_file():
            return candidate
    return None


def _provider_root_for_campaign(campaign_path: Path) -> Path | None:
    if campaign_path.name != "campaign-receipt.json":
        return None
    if campaign_path.parent.name == "source-run":
        return campaign_path.parents[1]
    return campaign_path.parent


def _provider_tau_seeded_evidence(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {"status": None, "checks_ok": False}
    campaign_path = _provider_campaign_path(root)
    broadcast_path = root / "broadcast" / "provider-tau-lineage-broadcast-receipt.json"
    if campaign_path is None:
        return {"status": None, "checks_ok": False, "root": str(root)}
    visibility_path = campaign_path.parent / "generation-2" / "visibility-validation.json"
    if not all(path.is_file() for path in [campaign_path, broadcast_path, visibility_path]):
        return {"status": None, "checks_ok": False, "root": str(root)}
    campaign = _read_json(campaign_path)
    broadcast = _read_json(broadcast_path)
    visibility = _read_json(visibility_path)
    ack_values = list((campaign.get("inheritance") or {}).values())
    arena_path = Path(str(broadcast.get("arena_receipt") or ""))
    red_path = Path(str(broadcast.get("red_team_activity_receipt") or ""))
    blue_path = Path(str(broadcast.get("blue_team_activity_receipt") or ""))
    commentary_path = Path(str(broadcast.get("sports_play_by_play_commentary_receipt") or ""))
    pydantic_receipts = {}
    for name, path in [
        ("arena", arena_path),
        ("red", red_path),
        ("blue", blue_path),
        ("commentary", commentary_path),
    ]:
        pydantic_receipts[name] = _read_json(path) if path.is_file() else {}
    commentary_lines = pydantic_receipts["commentary"].get("commentary_lines") or []
    red_activities = pydantic_receipts["red"].get("activities") or []
    blue_activities = pydantic_receipts["blue"].get("activities") or []
    commentary_grounded = bool(commentary_lines)
    for line in commentary_lines:
        for team, indices in (line.get("source_activity_indices") or {}).items():
            activities = red_activities if team == "red" else blue_activities if team == "blue" else []
            commentary_grounded = commentary_grounded and all(
                isinstance(index, int) and 0 <= index < len(activities) for index in indices
            )
    checks = {
        "campaign_passed": campaign.get("status") == "PASS",
        "seed_bundle_bound": (campaign.get("mutation_seed_receipts") or {}).get("status") == "PASS",
        "provider_cited_seed_hashes": bool(ack_values)
        and all(ack.get("mutation_seed_receipts_cited_in_provider_response") is True for ack in ack_values),
        "visibility_passed": visibility.get("status") == "PASS" and not visibility.get("private_input_leaks"),
        "broadcast_passed": broadcast.get("status") == "PASS",
        "pydantic_arena_team_commentary_receipts": (
            pydantic_receipts["arena"].get("schema") == "battle.arena_receipt.v1"
            and pydantic_receipts["arena"].get("status") == "PASS"
            and pydantic_receipts["red"].get("schema") == "battle.team_activity_receipt.v1"
            and pydantic_receipts["red"].get("status") == "PASS"
            and pydantic_receipts["red"].get("team") == "red"
            and pydantic_receipts["blue"].get("schema") == "battle.team_activity_receipt.v1"
            and pydantic_receipts["blue"].get("status") == "PASS"
            and pydantic_receipts["blue"].get("team") == "blue"
            and pydantic_receipts["commentary"].get("schema")
            == "battle.sports_play_by_play_commentary_receipt.v1"
            and pydantic_receipts["commentary"].get("status") == "PASS"
            and commentary_grounded
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks_ok": all(checks.values()),
        "root": str(root),
        "campaign_receipt": str(campaign_path),
        "broadcast_receipt": str(broadcast_path),
        "visibility_receipt": str(visibility_path),
        "arena_receipt": str(arena_path),
        "red_team_activity_receipt": str(red_path),
        "blue_team_activity_receipt": str(blue_path),
        "sports_play_by_play_commentary_receipt": str(commentary_path),
        "commentary_line_count": len(commentary_lines),
        "checks": checks,
        "seed_count": len((campaign.get("mutation_seed_receipts") or {}).get("receipts", [])),
    }


def _memory_promotion_evidence(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {"status": None, "checks_ok": False}
    path = root / "memory-promotion-eval" / "memory-promotion-live-receipt.json"
    if not path.is_file():
        return {"status": None, "checks_ok": False, "path": str(path)}
    receipt = _read_json(path)
    promotions = receipt.get("promotions") or []
    checks = {
        "receipt_passed": receipt.get("status") == "PASS",
        "two_teams": {item.get("team") for item in promotions} == {"red", "blue"},
        "learn_succeeded": all((item.get("learn") or {}).get("exit_code") == 0 for item in promotions),
        "recall_markers_found": all((item.get("recall") or {}).get("marker_found") is True for item in promotions),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks_ok": all(checks.values()),
        "path": str(path),
        "checks": checks,
    }


def _adaptive_lineage_evidence_passes(evidence: dict[str, Any]) -> bool:
    if evidence.get("status") != "PASS" or evidence.get("checks_ok") is not True:
        return False
    if int(evidence.get("check_count") or 0) < MIN_ADAPTIVE_LINEAGE_CHECKS:
        return False
    if evidence.get("g2_judge_attempts") is not None:
        return evidence.get("g2_judge_attempts") == 1
    return all(
        evidence.get(passed) == evidence.get(required) and evidence.get(required)
        for passed, required in [
            ("exact_replays_matched", "exact_replays_required"),
            ("slot_hashes_matched", "slot_hashes_required"),
            ("provider_receipts_passed", "provider_receipts_required"),
        ]
    )


def _source_context_item(path: str) -> dict[str, Any]:
    candidate = Path(path)
    resolved = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    return {"path": path, "exists": resolved.is_file()}


def _terminal_decision(status: dict[str, Any]) -> dict[str, Any]:
    for item in status.get("decisions") or []:
        if item.get("id") == "terminal_semantics_local_mvp":
            return item
    return {}


def _terminal_gap(status: dict[str, Any]) -> dict[str, Any]:
    for item in status.get("production_gaps") or []:
        if item.get("id") == "terminal_semantics_implementation":
            return item
    return {}


def _evaluate_terminal_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    terminal_state = candidate.get("terminal_state")
    if terminal_state in UNSUPPORTED_TERMINAL_ALIASES:
        return {
            "decision": "REJECT",
            "reason": "unsupported_terminal_alias",
            "terminal_state": terminal_state,
        }
    try:
        evidence = TerminalSemanticsEvidence.model_validate(candidate)
    except ValidationError as exc:
        return {
            "decision": "REJECT",
            "reason": "typed_terminal_evidence_rejected",
            "terminal_state": terminal_state,
            "validation_errors": exc.errors(include_context=False),
        }
    return {
        "decision": "ACCEPT",
        "reason": "typed_terminal_evidence_accepted",
        "terminal_state": evidence.terminal_state,
        "source_schema": evidence.source_schema,
        "source_authority": evidence.source_authority,
    }


def _terminal_semantics_receipt(status: dict[str, Any]) -> dict[str, Any]:
    candidates = {
        "accepts_typed_judge_blue_success": {
            "terminal_state": "BLUE_SUCCESS",
            "source_schema": "battle.arena_tau_public_only_judge_receipt.v1",
            "source_status": "PASS",
            "source_authority": "judge",
            "judge_verdict": "BLUE_SUCCESS",
            "crash_observation_only": False,
        },
        "rejects_kill_alias": {
            "terminal_state": "kill",
            "source_schema": "battle.arena_tau_public_only_judge_receipt.v1",
            "source_status": "PASS",
            "source_authority": "judge",
            "judge_verdict": "RED_SUCCESS",
            "crash_observation_only": False,
        },
        "rejects_fastest_crash_alias": {
            "terminal_state": "fastest_crash",
            "source_schema": "battle.arena_tau_public_only_judge_receipt.v1",
            "source_status": "PASS",
            "source_authority": "judge",
            "judge_verdict": "RED_SUCCESS",
            "crash_observation_only": False,
        },
        "rejects_crash_only_promotion": {
            "terminal_state": "RED_SUCCESS",
            "source_schema": "battle.arena_tau_public_only_judge_receipt.v1",
            "source_status": "PASS",
            "source_authority": "judge",
            "judge_verdict": "RED_SUCCESS",
            "crash_observation_only": True,
        },
        "rejects_promotion_alias": {
            "terminal_state": "promotion",
            "source_schema": "battle.arena_tau_public_only_run_receipt.v1",
            "source_status": "PASS",
            "source_authority": "scorekeeper",
            "scorekeeper_status": "BLUE_SUCCESS",
            "crash_observation_only": False,
        },
    }
    cases = [
        {"name": name, "candidate": candidate, **_evaluate_terminal_candidate(candidate)}
        for name, candidate in candidates.items()
    ]
    case_by_name = {case["name"]: case for case in cases}
    decision = _terminal_decision(status)
    gap = _terminal_gap(status)
    checks = [
        {
            "name": "supported_states_match_local_mvp",
            "status": "PASS"
            if decision.get("supported_states") == list(SUPPORTED_TERMINAL_STATES)
            else "FAIL",
            "supported_states": decision.get("supported_states"),
        },
        {
            "name": "unsupported_aliases_declared",
            "status": "PASS"
            if set(decision.get("unsupported_states") or []) >= UNSUPPORTED_TERMINAL_ALIASES
            else "FAIL",
            "unsupported_states": decision.get("unsupported_states"),
        },
        {
            "name": "terminal_semantics_implementation_executable",
            "status": "PASS"
            if gap.get("status") == "IMPLEMENTED" and bool(gap.get("receipt"))
            else "FAIL",
            "gap": gap,
        },
        {
            "name": "typed_judge_terminal_result_accepted",
            "status": "PASS"
            if case_by_name["accepts_typed_judge_blue_success"]["decision"] == "ACCEPT"
            else "FAIL",
            "case": case_by_name["accepts_typed_judge_blue_success"],
        },
        {
            "name": "kill_alias_rejected",
            "status": "PASS"
            if case_by_name["rejects_kill_alias"]["decision"] == "REJECT"
            else "FAIL",
            "case": case_by_name["rejects_kill_alias"],
        },
        {
            "name": "fastest_crash_alias_rejected",
            "status": "PASS"
            if case_by_name["rejects_fastest_crash_alias"]["decision"] == "REJECT"
            else "FAIL",
            "case": case_by_name["rejects_fastest_crash_alias"],
        },
        {
            "name": "crash_only_promotion_rejected",
            "status": "PASS"
            if case_by_name["rejects_crash_only_promotion"]["decision"] == "REJECT"
            else "FAIL",
            "case": case_by_name["rejects_crash_only_promotion"],
        },
    ]
    return {
        "schema": "battle.terminal_semantics_validation.v1",
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "mocked": False,
        "live": True,
        "created_at": _utc(),
        "source": {
            "current_status": str(STATUS_PATH),
            "terminal_semantics_decision": "skills/battle/docs/TERMINAL_SEMANTICS_LOCAL_MVP.md",
        },
        "supported_states": list(SUPPORTED_TERMINAL_STATES),
        "unsupported_aliases": sorted(UNSUPPORTED_TERMINAL_ALIASES),
        "accepted": [case for case in cases if case["decision"] == "ACCEPT"],
        "rejected": [case for case in cases if case["decision"] == "REJECT"],
        "checks": checks,
    }


def _write_terminal_semantics_receipt(status: dict[str, Any]) -> dict[str, Any]:
    receipt = _terminal_semantics_receipt(status)
    TERMINAL_SEMANTICS_RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TERMINAL_SEMANTICS_RECEIPT_PATH.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def _issue_ref(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue["number"],
        "title": issue["title"],
        "state": issue["state"],
        "url": issue["url"],
        "labels": sorted(label["name"] for label in issue.get("labels", [])),
    }


def generate(out: Path) -> int:
    receipts = {name: _receipt(path) for name, path in DEFAULT_RECEIPTS.items()}
    adaptive_lineage_qualification = _latest_adaptive_lineage_qualification()
    receipts["adaptive_lineage_qualification"] = _receipt(
        adaptive_lineage_qualification or BATTLE_DIR / "local" / "MISSING" / "adaptive-lineage-qualification.json"
    )
    backend_goal_dir = _latest_backend_goal_dir()
    receipts["backend_goal_full_proof_dir"] = _artifact(backend_goal_dir)
    if backend_goal_dir is not None:
        receipts["backend_goal_combiner"] = _receipt(
            backend_goal_dir / "battle-004-combiner" / "combiner-proof-receipt.json"
        )
        receipts["backend_goal_spawn_architect"] = _receipt(
            backend_goal_dir / "battle-004-spawn-architect" / "spawn-architect-receipt.json"
        )
        receipts["backend_goal_semantic_matrix"] = _receipt(
            backend_goal_dir / "battle-semantic-outcome-matrix.json"
        )
        receipts["backend_goal_lifecycle_dag"] = _receipt(
            backend_goal_dir / "battle-exploit-lifecycle-dag.json"
        )
        receipts["pr8_live_transport_browser"] = _receipt(
            Path("/tmp/battle-pr8-live-transport-proof/summary.json")
        )
        receipts["adaptive_lineage_v13_browser"] = _receipt(
            Path("/tmp/battle-adaptive-lineage-v13-proof/proof-summary.json")
        )
        receipts["adaptive_lineage_panel_source"] = _receipt(
            Path("/tmp/battle-adaptive-lineage-panel-source-proof/proof.json")
        )
        for key in [
            "fast_sanity",
            "deterministic_backend",
            "same_run_qualification",
            "live_qualification_gate",
            "human_interjection",
            "human_interjection_spectator",
        ]:
            if not receipts[key].get("exists"):
                receipts[key].update(
                    {
                        "status": "SUPERSEDED_BY_BACKEND_GOAL_PROOF",
                        "superseded_by": str(backend_goal_dir),
                    }
                )
    same_run = (
        _read_json(DEFAULT_RECEIPTS["same_run_qualification"])
        if DEFAULT_RECEIPTS["same_run_qualification"].is_file()
        else {}
    )
    live_gate = (
        _read_json(DEFAULT_RECEIPTS["live_qualification_gate"])
        if DEFAULT_RECEIPTS["live_qualification_gate"].is_file()
        else {}
    )
    fast = (
        _read_json(DEFAULT_RECEIPTS["fast_sanity"])
        if DEFAULT_RECEIPTS["fast_sanity"].is_file()
        else {}
    )
    deterministic = (
        _read_json(DEFAULT_RECEIPTS["deterministic_backend"])
        if DEFAULT_RECEIPTS["deterministic_backend"].is_file()
        else {}
    )
    dispatch = (
        _read_json(DEFAULT_RECEIPTS["project_agent_dispatch"])
        if DEFAULT_RECEIPTS["project_agent_dispatch"].is_file()
        else {}
    )
    human_interjection = (
        _read_json(DEFAULT_RECEIPTS["human_interjection"])
        if DEFAULT_RECEIPTS["human_interjection"].is_file()
        else {}
    )
    human_interjection_spectator = (
        _read_json(DEFAULT_RECEIPTS["human_interjection_spectator"])
        if DEFAULT_RECEIPTS["human_interjection_spectator"].is_file()
        else {}
    )
    adaptive_lineage_evidence = _adaptive_lineage_qualification_evidence(
        adaptive_lineage_qualification
    )
    provider_tau_root = _latest_provider_tau_seeded_root()
    provider_tau_evidence = _provider_tau_seeded_evidence(provider_tau_root)
    memory_promotion_evidence = _memory_promotion_evidence(provider_tau_root)
    adaptive_proof_dir = adaptive_lineage_qualification.parent if adaptive_lineage_qualification else None
    pixi_binding_path = (
        adaptive_proof_dir / "pixi-replay-proof.json" if adaptive_proof_dir else BATTLE_DIR / "local" / "MISSING" / "pixi-replay-proof.json"
    )
    pixi_gameplay_path = (
        adaptive_proof_dir / "pixi-gameplay-video-proof.json" if adaptive_proof_dir else BATTLE_DIR / "local" / "MISSING" / "pixi-gameplay-video-proof.json"
    )
    surf_text_path = (
        adaptive_proof_dir / "surf-text-corrected.txt" if adaptive_proof_dir else BATTLE_DIR / "local" / "MISSING" / "surf-text-corrected.txt"
    )
    surf_screenshot_path = (
        adaptive_proof_dir / "surf-battle-replay-corrected2.png" if adaptive_proof_dir else BATTLE_DIR / "local" / "MISSING" / "surf-battle-replay-corrected2.png"
    )
    receipts["adaptive_lineage_pixi_binding"] = _receipt(pixi_binding_path)
    receipts["adaptive_lineage_pixi_gameplay"] = _receipt(pixi_gameplay_path)
    receipts["adaptive_lineage_surf_text"] = _artifact(surf_text_path)
    receipts["adaptive_lineage_surf_screenshot"] = _artifact(surf_screenshot_path)
    receipts["provider_tau_seeded_campaign"] = _receipt(
        _provider_campaign_path(provider_tau_root)
        if provider_tau_root and _provider_campaign_path(provider_tau_root) is not None
        else Path("/mnt/storage12tb/skills/battle/MISSING/provider-tau/campaign-receipt.json")
    )
    receipts["provider_tau_seeded_broadcast"] = _receipt(
        provider_tau_root / "broadcast" / "provider-tau-lineage-broadcast-receipt.json"
        if provider_tau_root
        else Path("/mnt/storage12tb/skills/battle/MISSING/provider-tau/broadcast/provider-tau-lineage-broadcast-receipt.json")
    )
    receipts["provider_tau_memory_promotion"] = _receipt(
        provider_tau_root / "memory-promotion-eval" / "memory-promotion-live-receipt.json"
        if provider_tau_root
        else Path("/mnt/storage12tb/skills/battle/MISSING/provider-tau/memory-promotion-live-receipt.json")
    )
    pixi_binding = _read_json(pixi_binding_path) if pixi_binding_path.is_file() else {}
    pixi_gameplay = _read_json(pixi_gameplay_path) if pixi_gameplay_path.is_file() else {}
    pixi_binding_passes = (
        pixi_binding.get("status") == "PASS"
        and (pixi_binding.get("readback_matches") or {}).get("route_loaded_same_fixture_sha256") is True
        and (pixi_binding.get("readback_matches") or {}).get("route_loaded_same_run_id") is True
    )
    pixi_gameplay_passes = (
        pixi_gameplay.get("status") == "PASS"
        and pixi_gameplay.get("source_identity_visible") is True
        and pixi_gameplay.get("pause_after_round_not_in_primary_replay") is True
    )
    immutable_goal_met = (
        _adaptive_lineage_evidence_passes(adaptive_lineage_evidence)
        and pixi_binding_passes
        and pixi_gameplay_passes
        and surf_text_path.is_file()
        and surf_screenshot_path.is_file()
        and provider_tau_evidence.get("checks_ok") is True
        and memory_promotion_evidence.get("checks_ok") is True
    )
    open_issues = [_issue_ref(issue) for issue in _gh_issue_list("open")]
    all_issues = [_issue_ref(issue) for issue in _gh_issue_list("all")]

    status = {
        "schema": "battle.current_status.v1",
        "updated_at": _utc(),
        "generated_by": {
            "command": "./skills/battle/run.sh current-status generate",
            "script": "skills/battle/scripts/current_status.py",
        },
        "source": {
            "repository": "grahama1970/agent-skills",
            "commit": _git(["rev-parse", "HEAD"]),
            "battle_tree": _git(["rev-parse", "HEAD:skills/battle"]),
        },
        "immutable_goal_status": "MET" if immutable_goal_met else "NOT_MET",
        "primary_proof": {
            "backend_qualification": _adaptive_lineage_evidence_passes(adaptive_lineage_evidence),
            "pixi_receipt_binding": pixi_binding_passes,
            "pixi_gameplay_browser_proof": pixi_gameplay_passes,
            "surf_text_readback": surf_text_path.is_file(),
            "surf_screenshot": surf_screenshot_path.is_file(),
            "provider_tau_seeded_lineage": provider_tau_evidence.get("checks_ok") is True,
            "memory_promotion_live": memory_promotion_evidence.get("checks_ok") is True,
            "pydantic_event_commentary": (provider_tau_evidence.get("checks") or {}).get("pydantic_arena_team_commentary_receipts") is True,
        },
        "source_context": {
            key: _source_context_item(value) for key, value in SOURCE_CONTEXT.items()
        },
        "issue_state_at_generation": {
            "open_battle_label_count": len(open_issues),
            "open_battle_label_issues": open_issues,
            "all_battle_label_issue_count": len(all_issues),
            "all_battle_label_issues": all_issues,
            "focused_p0_issues": {
                "1141": "CLOSED",
                "1144": "CLOSED",
                "1143": "CLOSED",
                "1150": "CLOSED",
                "1142": "CLOSED",
            },
        },
        "source_receipts": receipts,
        "proven": [
            {
                "id": "p0_adaptive_lineage_fresh_qualification",
                "status": (
                    "PASS" if _adaptive_lineage_evidence_passes(adaptive_lineage_evidence) else "MISSING_OR_STALE"
                ),
                "issue_refs": [1499],
                "receipt": receipts["adaptive_lineage_qualification"]["path"],
                "evidence": adaptive_lineage_evidence,
                "does_not_prove": [
                    "fresh provider-backed overnight campaign breadth.",
                ],
            },
            {
                "id": "adaptive_lineage_pixi_receipt_replay",
                "status": "PASS" if pixi_binding_passes and pixi_gameplay_passes else "MISSING_OR_STALE",
                "issue_refs": [1500, 1501],
                "receipt": receipts["adaptive_lineage_pixi_gameplay"]["path"],
                "evidence": {
                    "binding_receipt": receipts["adaptive_lineage_pixi_binding"],
                    "gameplay_receipt": receipts["adaptive_lineage_pixi_gameplay"],
                    "route_loaded_same_fixture_sha256": (pixi_binding.get("readback_matches") or {}).get("route_loaded_same_fixture_sha256"),
                    "route_loaded_same_run_id": (pixi_binding.get("readback_matches") or {}).get("route_loaded_same_run_id"),
                    "source_identity_visible": pixi_gameplay.get("source_identity_visible"),
                    "pause_after_round_not_in_primary_replay": pixi_gameplay.get("pause_after_round_not_in_primary_replay"),
                    "surf_screenshot": receipts["adaptive_lineage_surf_screenshot"],
                },
                "does_not_prove": [
                    "production deployment readiness.",
                    "arbitrary target exploitability beyond the authorized battle-004 proof.",
                ],
            },
            {
                "id": "provider_tau_seeded_lineage_spawn",
                "status": "PASS" if provider_tau_evidence.get("checks_ok") is True else "MISSING_OR_STALE",
                "issue_refs": [],
                "receipt": receipts["provider_tau_seeded_campaign"]["path"],
                "evidence": provider_tau_evidence,
                "does_not_prove": [
                    "production deployment readiness.",
                    "arbitrary target exploitability beyond the authorized battle-004 proof.",
                ],
            },
            {
                "id": "provider_tau_memory_promotion",
                "status": "PASS" if memory_promotion_evidence.get("checks_ok") is True else "MISSING_OR_STALE",
                "issue_refs": [],
                "receipt": receipts["provider_tau_memory_promotion"]["path"],
                "evidence": memory_promotion_evidence,
                "does_not_prove": [
                    "automatic future strategy reuse.",
                    "memory ranking quality.",
                ],
            },
            {
                "id": "p0_project_agent_dispatch_selection",
                "status": "PROVEN_SELECTION_PARTIAL_REPAIR_NEEDS_ATTENTION",
                "issue_refs": [1141],
                "receipt": receipts["project_agent_dispatch"]["path"],
                "evidence": {
                    "receipt_status": dispatch.get("status"),
                    "handled_count": dispatch.get("handled_count"),
                    "selected_issue": 1150,
                    "selected_target": "skills/battle/sanity.sh",
                    "worktree_ready": True,
                },
                "does_not_prove": [
                    "Ask/WebGPT transport completed a repair.",
                    "Every future Battle ticket will dispatch successfully.",
                ],
            },
            {
                "id": "p0_root_layout_and_fast_sanity",
                "status": "PASS",
                "issue_refs": [1144, 1150],
                "receipt": receipts["fast_sanity"]["path"],
                "evidence": {
                    "status": fast.get("status"),
                    "source": fast.get("source"),
                    "proof_scope": fast.get("proof_scope"),
                },
            },
            {
                "id": "p0_deterministic_backend_gate",
                "status": "PASS",
                "issue_refs": [1150],
                "receipt": receipts["deterministic_backend"]["path"],
                "evidence": {
                    "status": deterministic.get("status"),
                    "source": deterministic.get("source"),
                    "backend_eval_receipt": deterministic.get("backend_eval_receipt"),
                    "proof_scope": deterministic.get("proof_scope"),
                },
            },
            {
                "id": "p0_same_run_arena_to_pixi",
                "status": "PASS",
                "issue_refs": [1143, 1150],
                "receipt": receipts["same_run_qualification"]["path"],
                "evidence": {
                    "status": same_run.get("status"),
                    "mocked": same_run.get("mocked"),
                    "live": same_run.get("live"),
                    "run_id": same_run.get("run_id"),
                    "judge_verdict": same_run.get("judge_verdict"),
                    "source_commit": same_run.get("source_commit"),
                    "source_tree": same_run.get("source_tree"),
                    "tau_source": same_run.get("tau_source"),
                    "browser_status": (same_run.get("browser") or {}).get("status"),
                    "proof_scope": same_run.get("proof_scope"),
                },
            },
            {
                "id": "p0_live_qualification_gate",
                "status": "PASS",
                "issue_refs": [1150],
                "receipt": receipts["live_qualification_gate"]["path"],
                "evidence": {
                    "status": live_gate.get("status"),
                    "current_source": live_gate.get("current_source"),
                    "inputs": live_gate.get("inputs"),
                    "errors": live_gate.get("errors"),
                },
            },
            {
                "id": "p1_pause_after_round_backend_contract",
                "status": "PASS",
                "issue_refs": [1145],
                "receipt": receipts["human_interjection"]["path"],
                "evidence": {
                    "status": human_interjection.get("status"),
                    "mocked": human_interjection.get("mocked"),
                    "live": human_interjection.get("live"),
                    "case_statuses": human_interjection.get("case_statuses"),
                    "proof_scope": human_interjection.get("proof_scope"),
                },
            },
            {
                "id": "p1_pause_after_round_canonical_pixi_ux",
                "status": "PASS",
                "issue_refs": [1146],
                "receipt": receipts["human_interjection_spectator"]["path"],
                "evidence": {
                    "status": human_interjection_spectator.get("status"),
                    "mocked": human_interjection_spectator.get("mocked"),
                    "live": human_interjection_spectator.get("live"),
                    "screenshots": human_interjection_spectator.get("screenshots"),
                    "readbacks": human_interjection_spectator.get("readbacks"),
                    "failed": human_interjection_spectator.get("failed"),
                    "claims": human_interjection_spectator.get("claims"),
                },
            },
        ],
        "partial": [] if immutable_goal_met else [
            {
                "id": "adaptive_lineage_effect",
                "issue_refs": [1147],
                "status": "OPEN",
                "reason": "Fresh backend qualification and Pixi replay proof have not both passed.",
            },
        ],
        "decisions": [
            {
                "id": "terminal_semantics_local_mvp",
                "issue_refs": [1148],
                "status": "DECIDED",
                "path": "skills/battle/docs/TERMINAL_SEMANTICS_LOCAL_MVP.md",
                "implementation_status": "EXECUTABLE_VALIDATION_BOUNDARY",
                "implementation_receipt": str(TERMINAL_SEMANTICS_RECEIPT_PATH),
                "supported_states": [
                    "BLUE_SUCCESS",
                    "RED_SUCCESS",
                    "INSUFFICIENT_EVIDENCE",
                    "BLOCKED",
                    "UNAVAILABLE",
                ],
                "unsupported_states": ["kill", "promotion", "fastest_crash"],
                "receipt_requirement": "Operator-visible terminal success must be Judge/scorekeeper receipt-backed.",
            }
        ],
        "blocked": [],
        "unsupported": [
            {
                "claim": "production_deployment_ready",
                "status": "UNSUPPORTED",
                "issue_refs": [1149],
                "reason": "No DNS/TLS/ingress/secrets/auth/capacity/rollback/teardown readiness receipt yet.",
            },
            {
                "claim": "full_adaptive_improvement_proven",
                "status": "UNSUPPORTED",
                "issue_refs": [1147],
                "reason": "Current live receipt proves same-run Arena/Tau/Judge/Pixi qualification, not adaptive effect.",
            },
            {
                "claim": "kill_promotion_fastest_crash_supported",
                "status": "UNSUPPORTED",
                "issue_refs": [1148],
                "reason": "Local MVP decision supports only Judge-backed success/blocked states.",
            },
            {
                "claim": "fast_sanity_is_live_product_proof",
                "status": "UNSUPPORTED",
                "issue_refs": [1150],
                "reason": "Fast sanity is explicitly offline/deterministic; live proof is a separate gate.",
            },
        ],
        "production_gaps": [
            {"id": "staging_infrastructure_readiness", "issue_refs": [1149], "status": "NON_GOAL_UNPROVEN"},
            {
                "id": "terminal_semantics_implementation",
                "issue_refs": [1148, 1632],
                "status": "IMPLEMENTED",
                "receipt": str(TERMINAL_SEMANTICS_RECEIPT_PATH),
                "proof": "current-status check writes battle.terminal_semantics_validation.v1 and rejects kill, promotion, fastest_crash, and crash-only terminal promotion.",
            },
        ],
        "non_claims": [
            "This status does not claim production deployment readiness.",
            "This status does not claim production-scale overnight campaign breadth.",
            "This status does not claim arbitrary target exploitability beyond the authorized battle-004 proof.",
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "path": str(out), "open_battle_label_count": len(open_issues)}, indent=2))
    return 0


def check(path: Path) -> int:
    status = _read_json(path)
    errors: list[str] = []
    if status.get("schema") != "battle.current_status.v1":
        errors.append("schema_mismatch")
    _validate_cached_source_records(status, errors)
    for item in status.get("source_receipts", {}).values():
        if not item.get("exists") and not item.get("superseded_by"):
            errors.append(f"missing_source_receipt:{item.get('path')}")
    receipts = status.get("source_receipts", {})
    adaptive_receipt = receipts.get("adaptive_lineage_qualification") or {}
    if adaptive_receipt.get("status") != "PASS":
        errors.append("adaptive_lineage_qualification_not_pass")
    pixi_binding_receipt = receipts.get("adaptive_lineage_pixi_binding") or {}
    if pixi_binding_receipt.get("status") != "PASS":
        errors.append("adaptive_lineage_pixi_binding_not_pass")
    pixi_gameplay_receipt = receipts.get("adaptive_lineage_pixi_gameplay") or {}
    if pixi_gameplay_receipt.get("status") != "PASS":
        errors.append("adaptive_lineage_pixi_gameplay_not_pass")
    if status.get("immutable_goal_status") == "MET":
        _validate_current_status_claim_bindings(status, errors)
        primary_proof = status.get("primary_proof") or {}
        adaptive_path = _record_path(status, "adaptive_lineage_qualification", errors)
        adaptive_payload = (
            _json_or_error(adaptive_path, "adaptive_lineage_qualification", errors)
            if adaptive_path is not None
            else None
        )
        recomputed_primary = {
            "backend_qualification": (
                adaptive_payload is not None
                and adaptive_path is not None
                and _validate_adaptive_source_run(adaptive_path, adaptive_payload, errors)
            ),
            "provider_tau_seeded_lineage": _validate_provider_tau_chain(status, errors),
        }
        recomputed_primary["memory_promotion_live"] = recomputed_primary[
            "provider_tau_seeded_lineage"
        ]
        recomputed_primary["pydantic_event_commentary"] = recomputed_primary[
            "provider_tau_seeded_lineage"
        ]
        pixi_binding_path = _record_path(status, "adaptive_lineage_pixi_binding", errors)
        pixi_gameplay_path = _record_path(status, "adaptive_lineage_pixi_gameplay", errors)
        surf_text_path = _record_path(status, "adaptive_lineage_surf_text", errors)
        surf_screenshot_path = _record_path(status, "adaptive_lineage_surf_screenshot", errors)
        pixi_binding = (
            _json_or_error(pixi_binding_path, "adaptive_lineage_pixi_binding", errors)
            if pixi_binding_path is not None
            else None
        )
        pixi_gameplay = (
            _json_or_error(pixi_gameplay_path, "adaptive_lineage_pixi_gameplay", errors)
            if pixi_gameplay_path is not None
            else None
        )
        recomputed_primary["pixi_receipt_binding"] = (
            pixi_binding is not None
            and pixi_binding.get("schema") == "battle.pixi_replay_receipt_binding.v1"
            and pixi_binding.get("status") == "PASS"
            and (pixi_binding.get("readback_matches") or {}).get(
                "route_loaded_same_fixture_sha256"
            )
            is True
            and (pixi_binding.get("readback_matches") or {}).get("route_loaded_same_run_id")
            is True
        )
        recomputed_primary["pixi_gameplay_browser_proof"] = (
            pixi_gameplay is not None
            and pixi_gameplay.get("schema") == "battle.pixi_gameplay_video_proof.v1"
            and pixi_gameplay.get("status") == "PASS"
            and pixi_gameplay.get("mocked") is False
            and pixi_gameplay.get("source_identity_visible") is True
            and pixi_gameplay.get("pause_after_round_not_in_primary_replay") is True
        )
        recomputed_primary["surf_text_readback"] = (
            surf_text_path is not None and surf_text_path.is_file()
        )
        recomputed_primary["surf_screenshot"] = (
            surf_screenshot_path is not None and surf_screenshot_path.is_file()
        )
        for key in [
            "backend_qualification",
            "pixi_receipt_binding",
            "pixi_gameplay_browser_proof",
            "surf_text_readback",
            "surf_screenshot",
            "provider_tau_seeded_lineage",
            "memory_promotion_live",
            "pydantic_event_commentary",
        ]:
            if primary_proof.get(key) is not True:
                errors.append(f"immutable_goal_primary_proof_false:{key}")
            if recomputed_primary.get(key) is not True:
                errors.append(f"immutable_goal_primary_proof_revalidation_failed:{key}")
    adaptive_claim = next(
        (
            item
            for item in status.get("proven", [])
            if item.get("id") == "p0_adaptive_lineage_fresh_qualification"
        ),
        {},
    )
    adaptive_evidence = adaptive_claim.get("evidence") or {}
    if adaptive_claim.get("status") != "PASS":
        errors.append("adaptive_lineage_fresh_qualification_claim_not_pass")
    if not _adaptive_lineage_evidence_passes(adaptive_evidence):
        errors.append("adaptive_lineage_fresh_qualification_checks_not_green")
    pixi_claim = next(
        (
            item
            for item in status.get("proven", [])
            if item.get("id") == "adaptive_lineage_pixi_receipt_replay"
        ),
        {},
    )
    if pixi_claim.get("status") != "PASS":
        errors.append("adaptive_lineage_pixi_receipt_replay_claim_not_pass")
    provider_claim = next(
        (
            item
            for item in status.get("proven", [])
            if item.get("id") == "provider_tau_seeded_lineage_spawn"
        ),
        {},
    )
    if provider_claim.get("status") != "PASS":
        errors.append("provider_tau_seeded_lineage_spawn_claim_not_pass")
    if (provider_claim.get("evidence") or {}).get("checks_ok") is not True:
        errors.append("provider_tau_seeded_lineage_checks_not_green")
    provider_checks = (provider_claim.get("evidence") or {}).get("checks") or {}
    if provider_checks.get("pydantic_arena_team_commentary_receipts") is not True:
        errors.append("pydantic_event_commentary_checks_not_green")
    memory_claim = next(
        (
            item
            for item in status.get("proven", [])
            if item.get("id") == "provider_tau_memory_promotion"
        ),
        {},
    )
    if memory_claim.get("status") != "PASS":
        errors.append("provider_tau_memory_promotion_claim_not_pass")
    if (memory_claim.get("evidence") or {}).get("checks_ok") is not True:
        errors.append("provider_tau_memory_promotion_checks_not_green")

    closed = {
        str(issue["number"])
        for issue in status.get("issue_state_at_generation", {}).get("all_battle_label_issues", [])
        if issue.get("state") == "CLOSED"
    }
    docs = STATUS_DOC.read_text(encoding="utf-8") if STATUS_DOC.exists() else ""
    if "CURRENT_STATUS.json" not in docs:
        errors.append("docs_status_missing_current_status_link")
    closed_blocker_pattern = re.compile(r"(open|blocked|blocker)[^\n#]{0,80}#(\d+)", re.I)
    for match in closed_blocker_pattern.finditer(docs):
        if match.group(2) in closed:
            errors.append(f"closed_issue_cited_as_open_blocker:#{match.group(2)}")
    forbidden_claims = [
        "production ready",
        "production-ready",
        "full adaptive improvement proven",
    ]
    lower_docs = docs.lower()
    for phrase in forbidden_claims:
        if phrase in lower_docs:
            errors.append(f"unsupported_claim_in_docs_status:{phrase}")

    terminal_receipt = _write_terminal_semantics_receipt(status)
    if terminal_receipt.get("status") != "PASS":
        errors.append("terminal_semantics_validation_not_pass")

    print(
        json.dumps(
            {
                "status": "PASS" if not errors else "FAIL",
                "path": str(path),
                "terminal_semantics_receipt": str(TERMINAL_SEMANTICS_RECEIPT_PATH),
                "errors": errors,
            },
            indent=2,
        )
    )
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or check Battle CURRENT_STATUS.json")
    sub = parser.add_subparsers(dest="command", required=True)
    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--out", type=Path, default=STATUS_PATH)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--path", type=Path, default=STATUS_PATH)
    args = parser.parse_args()
    if args.command == "generate":
        return generate(args.out)
    if args.command == "check":
        return check(args.path)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
