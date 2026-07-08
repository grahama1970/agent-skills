#!/usr/bin/env python3
"""Check dry-run provider-specific packet routing fixtures."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from write_video_provider_packet import write_json, write_provider_packet


PASS_STATUS = "PASS_VIDEO_PROVIDER_PACKET_ROUTING"
BLOCKED_STATUS = "BLOCKED_VIDEO_PROVIDER_PACKET_ROUTING"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_fixture(fixture_path: Path, fixtures_root: Path, output_root: Path) -> dict[str, Any]:
    fixture = read_json(fixture_path)
    fixture_name = str(fixture_path.parent.relative_to(fixtures_root))
    out_dir = output_root / "video-provider-packet-fixture-results" / fixture_name
    scene_path = out_dir / "video_scene_contract.v1.json"
    scorecard_path = out_dir / "video_provider_scorecard.v1.json"
    media_lock_path = out_dir / "media_lock_manifest.v1.json"
    packet_root = out_dir / "provider_packet"
    write_json(scene_path, fixture.get("scene_contract") or {})
    write_json(scorecard_path, fixture.get("scorecard") or {})
    write_json(media_lock_path, fixture.get("media_lock") or {})
    result = write_provider_packet(scene_path, scorecard_path, media_lock_path, packet_root)
    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    errors: list[str] = []
    if expected.get("status") and result["status"] != expected["status"]:
        errors.append(f"status_mismatch:{result['status']}:expected:{expected['status']}")
    if expected.get("provider_route") and result["provider_route"] != expected["provider_route"]:
        errors.append(f"provider_route_mismatch:{result['provider_route']}:expected:{expected['provider_route']}")
    for blocker in expected.get("blockers") or []:
        if blocker not in result["blockers"]:
            errors.append(f"missing_blocker:{blocker}")
    packet = read_json(Path(result["packet_path"]))
    mapping = read_json(Path(result["provider_payload_mapping_receipt_path"]))
    for field in ("provider_live", "paid_call_authorized", "submitted", "provider_ready", "live_submit_ready"):
        if packet.get(field) is not False:
            errors.append(f"packet_{field}_not_false")
        if mapping.get(field) is not False:
            errors.append(f"mapping_{field}_not_false")
    if mapping.get("actual_provider_call_attempts") != 0:
        errors.append("mapping_actual_provider_call_attempts_not_zero")
    return {
        "fixture": fixture_name,
        "status": result["status"],
        "provider_id": result["provider_id"],
        "provider_route": result["provider_route"],
        "blockers": result["blockers"],
        "packet_path": result["packet_path"],
        "provider_payload_mapping_receipt_path": result["provider_payload_mapping_receipt_path"],
        "errors": errors,
    }


def run_fixtures(fixtures_root: Path, receipt_out: Path) -> dict[str, Any]:
    results = [
        run_fixture(path, fixtures_root, receipt_out.parent)
        for path in sorted(fixtures_root.glob("*/fixture.json"))
    ]
    errors = [f"{result['fixture']}:{error}" for result in results for error in result["errors"]]
    observed_routes = sorted({str(result["provider_route"]) for result in results if result["provider_route"]})
    observed_blockers = sorted({blocker for result in results for blocker in result["blockers"]})
    if len(results) != 3:
        errors.append(f"fixture_count_mismatch:{len(results)}:expected:3")
    for route in ("fal-kling", "fal-seedance"):
        if route not in observed_routes:
            errors.append(f"missing_observed_route:{route}")
    if "BLOCKED_FAL_API_DOCS_NOT_OBSERVED:kling" not in observed_blockers:
        errors.append("missing_expected_observed_blocker:BLOCKED_FAL_API_DOCS_NOT_OBSERVED:kling")
    receipt = {
        "schema": "persona_dream.video_provider_packet_routing_checker_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "fixture_count": len(results),
        "observed_provider_routes": observed_routes,
        "observed_blockers": observed_blockers,
        "errors": errors,
        "results": results,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "paid_call_authorized": False,
        "provider_accessible_url_created": False,
        "submitted": False,
        "provider_ready": False,
        "live_submit_ready": False,
        "mocked": False,
        "claims": {
            "proves": [
                "provider packet routing fixtures wrote dry-run provider-specific packets and payload mapping receipts",
                "missing fal API/docs refresh evidence blocked provider packet mapping",
                "no provider, paid, URL, submit, or live-ready state was claimed",
            ],
            "does_not_prove": [
                "current fal provider schema compatibility",
                "provider-accessible media URLs",
                "paid-call authorization",
                "manual acceptance",
                "live provider readiness",
                "live video generation",
            ],
        },
    }
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-root", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run_fixtures(args.fixtures_root.resolve(), args.receipt_out.resolve())
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
