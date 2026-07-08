#!/usr/bin/env python3
"""Local Tau-style gate for Persona Dream Kling dry-run packets."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONVERTER = ROOT / "scripts/convert_accepted_storyboard_to_kling.py"
VALIDATOR = ROOT / "scripts/validate_kling_scene_packet.py"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storyboard-packet", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--receipt-out", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output_root = args.output_root.resolve()
    validation_receipt = output_root / "kling_scene_packet_validation_receipt.json"
    converter_cmd = [
        sys.executable,
        str(CONVERTER),
        "--storyboard-packet",
        str(args.storyboard_packet.resolve()),
        "--output-root",
        str(output_root),
        "--json",
    ]
    validator_cmd = [
        sys.executable,
        str(VALIDATOR),
        str(output_root / "kling_scene_packet.json"),
        "--receipt-out",
        str(validation_receipt),
        "--json",
    ]

    converter_result = run_command(converter_cmd, ROOT)
    validator_result = None
    validator_receipt_data: dict[str, Any] | None = None
    if converter_result["returncode"] == 0:
        validator_result = run_command(validator_cmd, ROOT)
        if validation_receipt.exists():
            validator_receipt_data = read_json(validation_receipt)

    blockers: list[str] = []
    if converter_result["returncode"] != 0:
        blockers.append("BLOCKED_KLING_DRY_RUN_CONVERTER")
    if validator_result is None:
        blockers.append("BLOCKED_KLING_SCENE_PACKET_VALIDATOR_NOT_RUN")
    elif validator_result["returncode"] != 0:
        blockers.append("BLOCKED_KLING_SCENE_PACKET_VALIDATOR")
    if validator_receipt_data and validator_receipt_data.get("status") != "PASS_KLING_SCENE_PACKET_DRY_RUN":
        blockers.extend(blocker.get("status", "BLOCKED_KLING_SCENE_PACKET_VALIDATOR") for blocker in validator_receipt_data.get("blockers", []))

    status = "PASS_KLING_DRY_RUN_TAU_GATE" if not blockers else "BLOCKED_KLING_DRY_RUN_TAU_GATE"
    receipt = {
        "schema": "persona_dream.kling.dry_run_tau_gate_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "verdict": "PASS_KLING_SCENE_PACKET_DRY_RUN" if not blockers else "FAIL_CLOSED",
        "tau_route": [
            "review-checker",
            "kling-dry-run-converter",
            "kling-scene-packet-validator",
            "human",
        ],
        "mocked": False,
        "provider_live": False,
        "live_kling_call_started": False,
        "submitted": validator_receipt_data.get("submitted") if validator_receipt_data else False,
        "paid_call_authorized": validator_receipt_data.get("paid_call_authorized") if validator_receipt_data else False,
        "accepted_frame_count": validator_receipt_data.get("accepted_frame_count") if validator_receipt_data else 0,
        "provider_facing_image_count": validator_receipt_data.get("provider_facing_image_count") if validator_receipt_data else 0,
        "element_count": validator_receipt_data.get("element_count") if validator_receipt_data else 0,
        "multi_prompt_count": validator_receipt_data.get("multi_prompt_count") if validator_receipt_data else 0,
        "token_linter_status": validator_receipt_data.get("token_binding_status") if validator_receipt_data else "NOT_RUN",
        "media_lock_status": validator_receipt_data.get("media_lock_status") if validator_receipt_data else "NOT_RUN",
        "live_submit_status": validator_receipt_data.get("live_submit_status") if validator_receipt_data else "NOT_RUN",
        "artifacts": {
            "output_root": str(output_root),
            "scene_packet": str(output_root / "kling_scene_packet.json"),
            "validation_receipt": str(validation_receipt),
            "gate_receipt": str(args.receipt_out.resolve()),
        },
        "commands": {
            "converter": {
                "command": converter_result["command"],
                "returncode": converter_result["returncode"],
            },
            "validator": {
                "command": validator_result["command"] if validator_result else validator_cmd,
                "returncode": validator_result["returncode"] if validator_result else None,
            },
        },
        "blockers": sorted(set(blockers)),
        "claims": {
            "proves": [
                "accepted storyboard packet was converted into a local Kling dry-run packet" if converter_result["returncode"] == 0 else "Kling dry-run converter was attempted",
                "standalone validator checked the Kling scene packet" if validator_receipt_data else "standalone validator did not produce a receipt",
                "no Kling provider call was made",
                "paid_call_authorized and submitted remained false" if not blockers else "dry-run flags were inspected",
            ],
            "does_not_prove": [
                "current Kling provider schema compatibility",
                "provider-accessible media URLs",
                "reference upload readiness",
                "voice readiness",
                "cost approval",
                "manual acceptance",
                "live Kling generation",
            ],
        },
    }
    write_json(args.receipt_out, receipt)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if status == "PASS_KLING_DRY_RUN_TAU_GATE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
