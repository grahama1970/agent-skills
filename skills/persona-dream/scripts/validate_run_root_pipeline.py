#!/usr/bin/env python3
"""Report the first blocker from dream packet to one-scene Kling packet.

This validator is local-only. It does not trust report prose, does not contact
providers, and does not submit live or paid calls.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import jsonschema
from validate_dream_packet import validate_dream_packet
from validate_panel_repair_gate import validate_receipt as validate_panel_repair_gate_receipt
from validate_panel_source_receipt import validate_panel_source_receipt
from validate_provider_media_local_staging import validate_provider_media_local_staging
from validate_provider_media_publication_authorization import validate_provider_media_publication_authorization
from validate_provider_media_publication_work_order import validate_provider_media_publication_work_order
from validate_story_contract import validate_story_contract
from validate_storyboard_panel_receipt import validate_storyboard_panel_receipt
from validate_visual_review_receipt import validate_visual_review_receipt


ROOT = Path(__file__).resolve().parents[1]
KLING_SCENE_PACKET_SCHEMA = ROOT / "schemas/kling_scene_packet.schema.json"
PROVIDER_MEDIA_LOCK_SCHEMA = ROOT / "schemas/provider_media_lock_receipt.schema.json"
@dataclass(frozen=True)
class PhaseResult:
    phase: str
    status: str
    path: str | None = None
    blocker: str | None = None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}: {exc}") from exc


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _first_existing(run_root: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        path = run_root / rel
        if path.exists():
            return path
    return None


def _first_existing_or_glob(run_root: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        if any(char in rel for char in "*?[]"):
            matches = sorted(run_root.glob(rel))
            if matches:
                return matches[0]
            continue
        path = run_root / rel
        if path.exists():
            return path
    return None


def _missing(phase: str, candidates: list[str]) -> PhaseResult:
    return PhaseResult(
        phase=phase,
        status="BLOCKED",
        blocker="missing_artifact",
        path=" | ".join(candidates),
    )


def _load_optional_scene_packet(run_root: Path) -> dict[str, Any] | None:
    path = run_root / "receipts/kling_scene_packet.json"
    if not path.exists():
        return None
    packet = _read_json(path)
    if not isinstance(packet, dict):
        raise ValueError("receipts/kling_scene_packet.json must be an object")
    return packet


def _source_artifact_candidates(
    packet: dict[str, Any] | None,
    key: str,
    fallback: list[str],
) -> list[str]:
    if packet:
        source_artifacts = packet.get("source_artifacts")
        if isinstance(source_artifacts, dict) and isinstance(source_artifacts.get(key), str):
            return [source_artifacts[key], *fallback]
    return fallback


def _validate_json_artifact(run_root: Path, phase: str, candidates: list[str]) -> PhaseResult:
    path = _first_existing(run_root, candidates)
    if path is None:
        return _missing(phase, candidates)
    doc = _read_json(path)
    if not isinstance(doc, dict):
        return PhaseResult(phase, "BLOCKED", _rel(path, run_root), "artifact_json_not_object")
    return PhaseResult(phase, "PASS", _rel(path, run_root))


def _validate_visual_review(run_root: Path, packet: dict[str, Any] | None) -> PhaseResult:
    candidates = _source_artifact_candidates(
        packet,
        "visual_review_receipt",
        ["receipts/visual_review_receipt.json", "visual_review_receipt.json"],
    )
    path = _first_existing(run_root, candidates)
    if path is None:
        return _missing("visual_review_receipt", candidates)

    result = validate_visual_review_receipt(path, run_root=run_root)
    blocker = result.get("first_blocker")
    if blocker:
        return PhaseResult(
            "visual_review_receipt",
            "BLOCKED",
            _rel(path, run_root),
            str(blocker.get("reason")),
        )
    return PhaseResult("visual_review_receipt", "PASS", _rel(path, run_root))


def _validate_panel_source(run_root: Path, packet: dict[str, Any] | None) -> PhaseResult:
    candidates = _source_artifact_candidates(
        packet,
        "panel_source_receipt",
        ["receipts/panel_source_receipt.json", "panel_source_receipt.json"],
    )
    path = _first_existing(run_root, candidates)
    if path is None:
        return _missing("panel_source_receipt", candidates)

    result = validate_panel_source_receipt(path, run_root=run_root)
    blocker = result.get("first_blocker")
    if blocker:
        return PhaseResult(
            "panel_source_receipt",
            "BLOCKED",
            _rel(path, run_root),
            str(blocker.get("reason")),
        )
    return PhaseResult("panel_source_receipt", "PASS", _rel(path, run_root))


def _panel_repair_gate_candidates(run_root: Path, packet: dict[str, Any] | None) -> list[str]:
    candidates = _source_artifact_candidates(
        packet,
        "panel_repair_gate_receipt",
        ["receipts/panel_repair_gate_receipt.json", "panel_repair_gate_receipt.json"],
    )
    panel_source = _first_existing(
        run_root,
        _source_artifact_candidates(
            packet,
            "panel_source_receipt",
            ["receipts/panel_source_receipt.json", "panel_source_receipt.json"],
        ),
    )
    if panel_source is not None:
        try:
            source_doc = _read_json(panel_source)
        except ValueError:
            source_doc = None
        if isinstance(source_doc, dict):
            producer = source_doc.get("producer")
            receipt = producer.get("receipt") if isinstance(producer, dict) else None
            if isinstance(receipt, str) and not receipt.startswith("missing:"):
                candidates = [receipt, *candidates]
    return candidates


def _first_panel_repair_gate_path(run_root: Path, packet: dict[str, Any] | None) -> Path | None:
    return _first_existing(run_root, _panel_repair_gate_candidates(run_root, packet))


def _validate_panel_repair_gate(
    run_root: Path,
    packet: dict[str, Any] | None,
    *,
    require_provider_eligible: bool = True,
) -> PhaseResult:
    candidates = _panel_repair_gate_candidates(run_root, packet)
    path = _first_existing(run_root, candidates)
    if path is None:
        return _missing("panel_repair_gate", candidates)

    try:
        receipt = _read_json(path)
    except ValueError as exc:
        return PhaseResult("panel_repair_gate", "BLOCKED", _rel(path, run_root), f"schema_or_parse:{exc}")
    if not isinstance(receipt, dict):
        return PhaseResult("panel_repair_gate", "BLOCKED", _rel(path, run_root), "receipt_json_not_object")

    effective_require_provider_eligible = require_provider_eligible or (
        receipt.get("provider_eligibility") is True or receipt.get("status") == "PASS_PANEL_REVIEWED"
    )
    errors = validate_panel_repair_gate_receipt(
        receipt,
        require_provider_eligible=effective_require_provider_eligible,
        base_dir=path.parent,
    )
    if errors:
        return PhaseResult("panel_repair_gate", "BLOCKED", _rel(path, run_root), ";".join(errors))
    return PhaseResult("panel_repair_gate", "PASS", _rel(path, run_root))


def _validate_storyboard_panel(run_root: Path, packet: dict[str, Any] | None) -> PhaseResult:
    candidates = _source_artifact_candidates(
        packet,
        "storyboard_panel",
        ["receipts/storyboard_panel_receipt.json", "artifacts/panel_001.json", "panel_001.json", "storyboard.json"],
    )
    path = _first_existing(run_root, candidates)
    if path is None:
        return _missing("storyboard_panel", candidates)

    result = validate_storyboard_panel_receipt(path, run_root=run_root)
    blocker = result.get("first_blocker")
    if blocker:
        return PhaseResult(
            "storyboard_panel",
            "BLOCKED",
            _rel(path, run_root),
            str(blocker.get("reason")),
        )
    return PhaseResult("storyboard_panel", "PASS", _rel(path, run_root))


def _validate_story_contract(run_root: Path, packet: dict[str, Any] | None) -> PhaseResult:
    candidates = _source_artifact_candidates(
        packet,
        "story_contract",
        ["story_contract.json", "artifacts/story_contract.json"],
    )
    path = _first_existing(run_root, candidates)
    if path is None:
        return _missing("story_contract", candidates)

    try:
        result = validate_story_contract(path, run_root=run_root)
    except Exception as exc:
        return PhaseResult("story_contract", "BLOCKED", _rel(path, run_root), f"schema_or_parse:{exc}")
    blocker = result.get("first_blocker")
    if blocker:
        return PhaseResult(
            "story_contract",
            "BLOCKED",
            _rel(path, run_root),
            str(blocker.get("reason")),
        )
    return PhaseResult("story_contract", "PASS", _rel(path, run_root))


def _validate_dream_packet(run_root: Path, packet: dict[str, Any] | None) -> PhaseResult:
    candidates = _source_artifact_candidates(
        packet,
        "dream_packet",
        ["dream_packet.json", "artifacts/dream_packet.json"],
    )
    path = _first_existing(run_root, candidates)
    if path is None:
        return _missing("dream_packet", candidates)

    try:
        result = validate_dream_packet(path, run_root=run_root)
    except Exception as exc:
        return PhaseResult("dream_packet", "BLOCKED", _rel(path, run_root), f"schema_or_parse:{exc}")
    blocker = result.get("first_blocker")
    if blocker:
        return PhaseResult(
            "dream_packet",
            "BLOCKED",
            _rel(path, run_root),
            str(blocker.get("reason")),
        )
    return PhaseResult("dream_packet", "PASS", _rel(path, run_root))


def _looks_provider_accessible(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.hostname in {
        None,
        "",
        "example.invalid",
        "localhost",
        "127.0.0.1",
    }:
        return False
    return not parsed.hostname.endswith(".invalid")


def _validate_provider_media(packet: dict[str, Any] | None) -> PhaseResult:
    if packet is None:
        return _missing("provider_media_lock", ["receipts/kling_scene_packet.json"])

    dry_run_fields = packet.get("provider_dry_run_fields")
    images = dry_run_fields.get("image_list") if isinstance(dry_run_fields, dict) else None
    if not isinstance(images, list) or not images:
        return PhaseResult("provider_media_lock", "BLOCKED", "receipts/kling_scene_packet.json", "missing_provider_image_list")

    bad_urls: list[str] = []
    for image in images:
        if not isinstance(image, dict) or not isinstance(image.get("image"), str):
            bad_urls.append(str(image))
            continue
        if not _looks_provider_accessible(image["image"]):
            bad_urls.append(image["image"])
    if bad_urls:
        return PhaseResult(
            "provider_media_lock",
            "BLOCKED",
            "receipts/kling_scene_packet.json",
            "provider_media_url_not_live_accessible:" + ",".join(bad_urls),
        )

    image_list = packet.get("image_list")
    if not isinstance(image_list, list) or not image_list:
        return PhaseResult("provider_media_lock", "BLOCKED", "receipts/kling_scene_packet.json", "missing_image_hash_manifest")
    missing_hash = [
        str(item.get("path"))
        for item in image_list
        if not isinstance(item, dict) or not isinstance(item.get("hash"), str) or not item["hash"].startswith("sha256:")
    ]
    if missing_hash:
        return PhaseResult(
            "provider_media_lock",
            "BLOCKED",
            "receipts/kling_scene_packet.json",
            "missing_or_invalid_image_hash:" + ",".join(missing_hash),
        )

    return PhaseResult("provider_media_lock", "PASS", "receipts/kling_scene_packet.json")


def _validate_local_provider_media_lock(run_root: Path) -> PhaseResult:
    path = run_root / "receipts/provider_media_lock_receipt.json"
    if not path.exists():
        return _missing("local_provider_media_lock", ["receipts/provider_media_lock_receipt.json"])

    schema = _read_json(PROVIDER_MEDIA_LOCK_SCHEMA)
    receipt = _read_json(path)
    jsonschema.Draft202012Validator(schema).validate(receipt)

    if receipt.get("status") != "LOCAL_MEDIA_LOCK_READY":
        return PhaseResult(
            "local_provider_media_lock",
            "BLOCKED",
            _rel(path, run_root),
            f"local_media_lock_not_ready:{receipt.get('status')}",
        )
    if receipt.get("provider_accessible") is not False:
        return PhaseResult(
            "local_provider_media_lock",
            "BLOCKED",
            _rel(path, run_root),
            "local_media_lock_must_not_claim_provider_accessible",
        )
    return PhaseResult("local_provider_media_lock", "PASS", _rel(path, run_root))


def _validate_provider_media_local_staging(run_root: Path, packet: dict[str, Any] | None) -> PhaseResult:
    candidates = _source_artifact_candidates(
        packet,
        "provider_media_local_staging_receipt",
        [
            "receipts/provider_media_local_staging_receipt.json",
            "storyboard/panel_repair_gate/provider_media_publication_work_orders/*local_staging_receipt.json",
        ],
    )
    path = _first_existing_or_glob(run_root, candidates)
    if path is None:
        return _missing("provider_media_local_staging", candidates)

    result = validate_provider_media_local_staging(path)
    blocker = result.get("first_blocker")
    if blocker:
        return PhaseResult(
            "provider_media_local_staging",
            "BLOCKED",
            _rel(path, run_root),
            str(blocker.get("reason")),
        )
    return PhaseResult("provider_media_local_staging", "PASS", _rel(path, run_root))


def _validate_provider_media_publication_authorization(run_root: Path, packet: dict[str, Any] | None) -> PhaseResult:
    preflight_candidates = _source_artifact_candidates(
        packet,
        "provider_media_publication_preflight_receipt",
        ["receipts/provider_media_publication_preflight.json"],
    )
    preflight_path = _first_existing(run_root, preflight_candidates)
    if preflight_path is None:
        return _missing("provider_media_publication_authorization", preflight_candidates)

    auth_candidates = _source_artifact_candidates(
        packet,
        "provider_media_publication_authorization_receipt",
        ["receipts/provider_media_publication_authorization.json"],
    )
    auth_path = _first_existing(run_root, auth_candidates)

    result: dict[str, Any]
    if auth_path is not None:
        try:
            auth_doc = _read_json(auth_path)
        except ValueError as exc:
            return PhaseResult(
                "provider_media_publication_authorization",
                "BLOCKED",
                _rel(auth_path, run_root),
                f"schema_or_parse:{exc}",
            )
        if isinstance(auth_doc, dict) and auth_doc.get("schema") == "persona_dream.provider_media_publication_authorization_validation.v1":
            result = auth_doc
        else:
            result = validate_provider_media_publication_authorization(
                preflight_receipt_path=preflight_path,
                authorization_receipt_path=auth_path,
            )
    else:
        result = validate_provider_media_publication_authorization(preflight_receipt_path=preflight_path)
    blocker = result.get("first_blocker")
    if result.get("status") != "PASS_PROVIDER_MEDIA_PUBLICATION_AUTHORIZATION":
        return PhaseResult(
            "provider_media_publication_authorization",
            "BLOCKED",
            _rel(auth_path or preflight_path, run_root),
            str(blocker.get("reason")) if isinstance(blocker, dict) else str(result.get("status")),
        )
    return PhaseResult("provider_media_publication_authorization", "PASS", _rel(auth_path or preflight_path, run_root))


def _validate_provider_media_publication_work_order(run_root: Path, packet: dict[str, Any] | None) -> PhaseResult:
    candidates = _source_artifact_candidates(
        packet,
        "provider_media_publication_work_order",
        [
            "receipts/provider_media_publication_work_order.json",
            "storyboard/panel_repair_gate/provider_media_publication_work_orders/*publication_request.json",
        ],
    )
    path = _first_existing_or_glob(run_root, candidates)
    if path is None:
        return _missing("provider_media_publication_work_order", candidates)

    result = validate_provider_media_publication_work_order(path)
    blocker = result.get("first_blocker")
    if blocker:
        return PhaseResult(
            "provider_media_publication_work_order",
            "BLOCKED",
            _rel(path, run_root),
            str(blocker.get("reason")),
        )
    return PhaseResult("provider_media_publication_work_order", "PASS", _rel(path, run_root))


def _provider_media_public_probe_candidates(run_root: Path, packet: dict[str, Any] | None) -> list[Path]:
    candidates: list[Path] = []
    source_artifacts = packet.get("source_artifacts") if isinstance(packet, dict) else None
    if isinstance(source_artifacts, dict) and isinstance(source_artifacts.get("provider_media_probe_receipt"), str):
        value = source_artifacts["provider_media_probe_receipt"]
        candidates.append(Path(value) if Path(value).is_absolute() else run_root / value)

    panel_repair_gate = _first_panel_repair_gate_path(run_root, packet)
    if panel_repair_gate is not None:
        try:
            receipt = _read_json(panel_repair_gate)
        except ValueError:
            receipt = None
        if isinstance(receipt, dict) and isinstance(receipt.get("provider_media_probe_receipt"), str):
            value = receipt["provider_media_probe_receipt"]
            candidates.append(Path(value) if Path(value).is_absolute() else panel_repair_gate.parent / value)

    candidates.extend(
        [
            run_root / "receipts/provider_media_url_probe_receipt.json",
            *sorted(run_root.glob("storyboard/panel_repair_gate/final_provider_eligibility_work_orders/*/provider_media_url_probe_receipt.json")),
        ]
    )
    return candidates


def _validate_provider_media_public_probe(run_root: Path, packet: dict[str, Any] | None) -> PhaseResult:
    candidates = _provider_media_public_probe_candidates(run_root, packet)
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        display = [str(candidate if candidate.is_absolute() else run_root / candidate) for candidate in candidates]
        return _missing("provider_media_public_probe", display or ["receipts/provider_media_url_probe_receipt.json"])

    try:
        receipt = _read_json(path)
    except ValueError as exc:
        return PhaseResult("provider_media_public_probe", "BLOCKED", _rel(path, run_root), f"schema_or_parse:{exc}")
    if not isinstance(receipt, dict):
        return PhaseResult("provider_media_public_probe", "BLOCKED", _rel(path, run_root), "receipt_json_not_object")
    if receipt.get("schema") != "persona_dream.provider_media_url_probe_receipt.v1":
        return PhaseResult("provider_media_public_probe", "BLOCKED", _rel(path, run_root), f"wrong_schema:{receipt.get('schema')}")
    if receipt.get("status") != "PASS_PROVIDER_MEDIA_URL_PROBE":
        blockers = receipt.get("blockers")
        blocker_text = ",".join(str(blocker) for blocker in blockers) if isinstance(blockers, list) else str(receipt.get("status"))
        return PhaseResult("provider_media_public_probe", "BLOCKED", _rel(path, run_root), f"provider_media_public_probe_not_pass:{blocker_text}")
    if receipt.get("http_status") != 200:
        return PhaseResult("provider_media_public_probe", "BLOCKED", _rel(path, run_root), f"http_status_not_200:{receipt.get('http_status')}")
    if receipt.get("observed_sha256") != receipt.get("expected_sha256"):
        return PhaseResult("provider_media_public_probe", "BLOCKED", _rel(path, run_root), "sha256_mismatch")
    return PhaseResult("provider_media_public_probe", "PASS", _rel(path, run_root))


def _validate_kling_scene_packet(run_root: Path) -> PhaseResult:
    path = run_root / "receipts/kling_scene_packet.json"
    if not path.exists():
        return _missing("kling_scene_packet", ["receipts/kling_scene_packet.json"])

    schema = _read_json(KLING_SCENE_PACKET_SCHEMA)
    packet = _read_json(path)
    jsonschema.Draft202012Validator(schema).validate(packet)

    if packet.get("schema") != "kling.scene_packet.v1":
        return PhaseResult("kling_scene_packet", "BLOCKED", _rel(path, run_root), "wrong_scene_packet_schema")
    if packet.get("paid_call_authorized") is not False:
        return PhaseResult("kling_scene_packet", "BLOCKED", _rel(path, run_root), "paid_call_authorized_not_false")
    if not packet.get("live_call_block_reason"):
        return PhaseResult("kling_scene_packet", "BLOCKED", _rel(path, run_root), "missing_live_call_block_reason")

    return PhaseResult("kling_scene_packet", "PASS", _rel(path, run_root))


def validate_run_root(run_root: Path, *, direction: str = "forward") -> dict[str, Any]:
    run_root = run_root.resolve()
    if not run_root.exists():
        return {
            "schema": "persona_dream.run_root_pipeline_validation.v1",
            "run_root": str(run_root),
            "status": "BLOCKED",
            "first_blocker": {"phase": "run_root", "reason": "missing_run_root"},
            "phases": [],
            "mocked": "no",
            "live": "no",
        }

    packet = _load_optional_scene_packet(run_root)
    forward_results = [
        _validate_dream_packet(run_root, packet),
        _validate_story_contract(run_root, packet),
        _validate_storyboard_panel(run_root, packet),
        _validate_panel_repair_gate(
            run_root,
            packet,
            require_provider_eligible=packet is not None,
        ),
    ]
    if packet is None:
        forward_results.extend(
            [
                _validate_visual_review(run_root, packet),
                _validate_provider_media_publication_work_order(run_root, packet),
                _validate_provider_media_local_staging(run_root, packet),
                _validate_provider_media_publication_authorization(run_root, packet),
                _validate_provider_media_public_probe(run_root, packet),
            ]
        )
    forward_results.extend(
        [
            _validate_panel_source(run_root, packet),
            _validate_visual_review(run_root, packet) if packet is not None else None,
            _validate_provider_media(packet),
            _validate_kling_scene_packet(run_root),
        ]
    )
    forward_results = [result for result in forward_results if result is not None]
    backward_results = [
        _validate_kling_scene_packet(run_root),
        _validate_local_provider_media_lock(run_root),
        _validate_provider_media_publication_work_order(run_root, packet),
        _validate_provider_media_local_staging(run_root, packet),
        _validate_provider_media_publication_authorization(run_root, packet),
        _validate_provider_media_public_probe(run_root, packet),
        _validate_panel_source(run_root, packet),
        _validate_panel_repair_gate(run_root, packet),
        _validate_visual_review(run_root, packet),
        _validate_storyboard_panel(run_root, packet),
        _validate_story_contract(run_root, packet),
        _validate_dream_packet(run_root, packet),
    ]
    phase_results = backward_results if direction == "backward" else forward_results

    first_blocker = next((phase for phase in phase_results if phase.status != "PASS"), None)
    status = "BLOCKED" if first_blocker else "DRY_RUN_REVIEW_PACKET_READY"

    return {
        "schema": "persona_dream.run_root_pipeline_validation.v1",
        "run_root": str(run_root),
        "direction": direction,
        "status": status,
        "first_blocker": None
        if first_blocker is None
        else {
            "phase": first_blocker.phase,
            "reason": first_blocker.blocker,
            "path": first_blocker.path,
        },
        "phases": [
            {
                "phase": phase.phase,
                "status": phase.status,
                "path": phase.path,
                "blocker": phase.blocker,
            }
            for phase in phase_results
        ],
        "mocked": "yes" if "fixtures" in run_root.parts else "no",
        "live": "no",
        "exercised": "local run-root files, JSON parse, Kling scene packet schema, dream packet gate, story contract gate, storyboard panel gate, panel repair provider-eligibility gate, panel source provenance gate, provider media publication work-order gate, provider media local staging gate, provider media publication authorization gate, visual review gate, provider URL/hash gate",
        "unverified": "live memory, Look Lock/Script DNA execution, live panel image generation/review, provider media hosting reachability, paid approval, Kling task submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path, help="Run root to inspect")
    parser.add_argument(
        "--direction",
        choices=["forward", "backward"],
        default="forward",
        help="Check from dream_packet forward or from Kling packet backward",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args(argv)

    try:
        result = validate_run_root(args.run_root, direction=args.direction)
    except Exception as exc:
        result = {
            "schema": "persona_dream.run_root_pipeline_validation.v1",
            "run_root": str(args.run_root),
            "status": "BLOCKED",
            "first_blocker": {"phase": "schema_or_parse", "reason": str(exc)},
            "phases": [],
            "mocked": "unknown",
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        blocker = result.get("first_blocker")
        if blocker:
            print(f"{result['status']} {blocker['phase']}: {blocker['reason']}")
        else:
            print(result["status"])
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
