#!/usr/bin/env python3
"""provider_packet - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def validate_packet(packet_dir: Path, root: Path | None = None) -> dict[str, Any]:
    packet_dir = packet_dir.resolve()
    root = root.resolve() if root else packet_dir.parent.resolve()
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    provider_path = packet_dir / "provider_request_dry_run.json"
    lock_path = packet_dir / "referenced_artifacts.lock.json"
    readiness_path = packet_dir / "readiness_receipt.json"

    for path in [provider_path, lock_path, readiness_path]:
        add(f"exists:{path.name}", path.exists() and path.stat().st_size > 0, str(path))

    provider: dict[str, Any] = {}
    lock: dict[str, Any] = {}
    readiness: dict[str, Any] = {}
    if provider_path.exists():
        provider = read_json(provider_path)
        add(
            "provider_schema",
            provider.get("schema") == "persona_dream.provider_request_dry_run.v1",
            provider.get("schema"),
        )
        add("paid_call_performed_false", provider.get("paid_call_performed") is False, provider.get("paid_call_performed"))
        add("live_call_authorized_false", provider.get("live_call_authorized") is False, provider.get("live_call_authorized"))
        for field in ["prompt_path", "storyboard_board", "scene_directions_path", "scene_payloads_path"]:
            value = provider.get(field)
            add(f"provider_path_exists:{field}", bool(value) and Path(value).exists(), value)
        scene_payloads_path = provider.get("scene_payloads_path")
        if scene_payloads_path and Path(scene_payloads_path).exists():
            try:
                scene_payloads = read_json(Path(scene_payloads_path))
            except Exception as exc:
                add("scene_payloads_json_readable", False, str(exc))
                scene_payloads = {}
            panels = scene_payloads.get("panels", []) if isinstance(scene_payloads, dict) else []
            add("scene_payloads_schema", scene_payloads.get("schema") == "persona_dream.kling_scene_payloads.v1", scene_payloads.get("schema"))
            add("scene_payloads_have_panels", isinstance(panels, list) and bool(panels), len(panels) if isinstance(panels, list) else type(panels).__name__)
            for field in ["emotional_behavior", "camera", "timing", "provider_text"]:
                missing = [
                    panel.get("panel")
                    for panel in panels
                    if not panel.get(field)
                ]
                add(f"scene_payloads_have_{field}", not missing, missing)
        references = provider.get("reference_images", [])
        add("reference_images_present", isinstance(references, list) and bool(references), references)
        missing_refs = [path for path in references if not Path(path).exists()]
        add("reference_images_exist", not missing_refs, missing_refs)

    if lock_path.exists():
        lock = read_json(lock_path)
        add(
            "lock_schema",
            lock.get("schema") == "persona_dream.referenced_artifacts_lock.v1",
            lock.get("schema"),
        )
        artifacts = lock.get("artifacts", [])
        add("locked_artifacts_present", isinstance(artifacts, list) and bool(artifacts), len(artifacts) if isinstance(artifacts, list) else type(artifacts).__name__)
        missing_locked = [item for item in artifacts if not Path(item.get("path", "")).exists()]
        add("locked_artifact_paths_exist", not missing_locked, missing_locked)
        bad_hashes = []
        for item in artifacts:
            path = Path(item.get("path", ""))
            expected = item.get("sha256")
            if path.exists() and expected and sha256(path) != expected:
                bad_hashes.append({"path": str(path), "expected": expected})
        add("locked_artifact_hashes_match", not bad_hashes, bad_hashes)

    if readiness_path.exists():
        readiness = read_json(readiness_path)
        add(
            "readiness_schema",
            readiness.get("schema") == "persona_dream.readiness_receipt.v1",
            readiness.get("schema"),
        )
        add("readiness_paid_false", readiness.get("paid_call_performed") is False, readiness.get("paid_call_performed"))
        add("readiness_live_false", readiness.get("live_call_authorized") is False, readiness.get("live_call_authorized"))
        add("readiness_status_blocked_or_accepted", readiness.get("status") in {"BLOCKED", "PROVIDER_PACKET_ACCEPTED"}, readiness.get("status"))
        manual_missing = [
            check for check in readiness.get("checks", [])
            if str(check.get("name", "")).startswith("manual_") and check.get("ok") is False
        ]
        if manual_missing:
            add("manual_gates_keep_packet_blocked", readiness.get("status") == "BLOCKED", manual_missing)

    ok = all(check["ok"] for check in checks)
    receipt = {
        "schema": "provider_packet.validation_receipt.v1",
        "artifact_id": "provider_packet_validation",
        "status": "ACCEPTED_AUTOMATED" if ok else "FAILED_AUTOMATED_CHECK",
        "created_at": now_iso(),
        "packet_dir": str(packet_dir),
        "root": str(root),
        "checks": checks,
        "passed": sum(1 for check in checks if check["ok"]),
        "failed": sum(1 for check in checks if not check["ok"]),
        "paid_call_performed": False,
        "live_call_performed": False,
        "non_claims": [
            "This validates dry-run packet structure only.",
            "This does not authorize or perform a paid provider call.",
        ],
    }
    write_json(packet_dir / "provider_packet_validation_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate dry-run provider packet artifacts.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--packet-dir", type=Path, required=True)
    validate.add_argument("--root", type=Path, default=None)
    args = parser.parse_args()

    if args.command == "validate":
        receipt = validate_packet(args.packet_dir, args.root)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        if receipt["status"] != "ACCEPTED_AUTOMATED":
            sys.exit(1)


if __name__ == "__main__":
    main()
